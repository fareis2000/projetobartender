"""Motor de Descoberta Automática de Rede, Scanner LAN/UDP e Provisionamento Zero-Config do ESP.

Papel na Arquitetura:
---------------------
Elimina completamente a dependência de redes Wi-Fi fixas, IPs estáticos, resolução mDNS frágil
(`bartender.local`) ou portas USB fixas (`COM3`). Este módulo permite que o Bartender.OS opere
em **qualquer rede** (roteador doméstico, Wi-Fi de eventos/universidades, Hotspot 4G/5G de celular
Android/iPhone ou modo Access Point direto `192.168.4.1`):

1. **Detecção Direta da Rede Conectada no Servidor (`get_current_network_info`):**
   - Inspeciona em tempo real a interface Wi-Fi ativa do sistema operacional (`netsh wlan`),
     identificando o `SSID` atual, sinal, banda (`2.4 GHz` vs `5 GHz`) e credenciais salvas.
   - Se o notebook estiver conectado na banda `5 GHz` do roteador (ex.: `DR.PC_5G`), localiza
     automaticamente o perfil irmão `2.4 GHz` (`DR.PC`) compatível com o rádio do ESP8266/ESP32!
   - Identifica todas as sub-redes IPv4 ativas da máquina priorizando interfaces Wi-Fi/LAN reais
     sobre adaptadores virtuais (WSL, Docker, Hyper-V, VPN).

2. **Localização Automática do ESP na Rede Atual em 4 Camadas (`discover_esp_on_network`):**
   - **Camada 1 — Broadcast UDP (`porta 4210`, `< 200ms`):** Envia pacote `BARTENDER_DISCOVER`
     em todas as sub-redes ativas; o ESP responde instantaneamente com seu IP e modelo.
   - **Camada 2 — Candidatos Diretos:** Último IP válido em cache, SoftAP (`192.168.4.1`) e mDNS.
   - **Camada 3 — Tabela ARP do Sistema (`arp -a`):** Testa em paralelo todos os vizinhos IPv4
     já conhecidos pelo roteador/hotspot na sub-rede atual (`< 350ms`).
   - **Camada 4 — Varredura Assíncrona Paralela da Sub-rede (`/24` Sweep):** Testa concorrentemente
     os IPs da rede atual (`Semaphore(64)`, timeout `0.35s`) em busca da assinatura JSON `/status`
     do Bartender, encontrando o ESP em ~1,2s mesmo em redes que bloqueiam mDNS e broadcast UDP!

3. **Auto-Detecção de Porta USB Serial e Provisionamento Automático (`find_best_serial_port`):**
   - Detecta qualquer porta `COMx` / `/dev/ttyUSBx` onde o conversor USB-Serial (`CH340`, `CP210x`,
     `FTDI`, `ESP32`) tenha sido plugado, sem travar caso o Windows mude de `COM3` para `COM4`/`COM5`.
   - Sincroniza automaticamente `bombas/secrets.h` e pode enviar o Wi-Fi atual do PC para o ESP
     via USB Serial ou HTTP (`/config/wifi`), garantindo conexão sem regravar código.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

import httpx
import serial
import serial.tools.list_ports

UDP_DISCOVERY_PORT = 4210
_DISCOVERY_CACHE_TTL = 20.0


@dataclass
class WifiProfileCredential:
    """Representa um par SSID + senha de uma rede Wi-Fi conhecida pelo computador."""

    ssid: str
    password: str
    is_current: bool = False
    is_24ghz_twin: bool = False


@dataclass
class CurrentNetworkInfo:
    """Retrato completo da rede à qual o servidor está conectado neste momento."""

    connected_ssid: str | None = None
    esp_target_ssid: str | None = None
    esp_target_password: str | None = None
    radio_type: str | None = None
    channel: int | None = None
    signal_pct: int | None = None
    is_5ghz: bool = False
    is_5ghz_only: bool = False
    primary_ip: str | None = None
    active_ips: list[str] = field(default_factory=list)
    subnets: list[str] = field(default_factory=list)
    known_profiles: list[WifiProfileCredential] = field(default_factory=list)
    updated: bool = True

    def get(self, key: str, default: object = None) -> object:
        """Permite acesso compatível com dict (`.get()`) além de atributos tipados."""
        aliases = {
            "wifi_password": self.esp_target_password,
            "lan_ips": self.active_ips,
            "saved_profiles": self.known_profiles,
            "known_networks_count": len(self.known_profiles),
        }
        if key in aliases:
            val = aliases[key]
            return default if val is None else val
        val = getattr(self, key, default)
        return default if val is None else val


@dataclass
class DiscoveredEsp:
    """Resultado da localização automática de uma placa ESP8266/ESP32 na rede local."""

    ip: str
    port: int = 80
    rssi: int | None = None
    device: str = "ESP"
    method: str = "http"

    def get(self, key: str, default: object = None) -> object:
        """Permite acesso compatível com dict (`.get()`) além de atributos tipados."""
        if key == "discovered_via":
            return self.method
        val = getattr(self, key, default)
        return default if val is None else val

    def __getitem__(self, key: str) -> object:
        return self.get(key)


def _run_cmd_text(args: list[str], timeout: float = 2.5) -> str:
    """Executa um comando de sistema silenciosamente decodificando saída em UTF-8/CP850/CP1252."""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
            check=False,
        )
        raw = proc.stdout or b""
        for enc in ("utf-8", "cp850", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


_WIFI_PASSWORD_CACHE: dict[str, str] = {}


def _extract_wifi_profile_password(profile_name: str) -> str | None:
    """Extrai a senha em texto claro de um perfil Wi-Fi salvo no Windows (`key=clear`)."""
    if os.name != "nt" or not profile_name.strip():
        return None
    if profile_name in _WIFI_PASSWORD_CACHE:
        return _WIFI_PASSWORD_CACHE[profile_name]
    for attempt in range(2):
        out = _run_cmd_text(["netsh", "wlan", "show", "profile", f"name={profile_name}", "key=clear"])
        for line in out.splitlines():
            low = line.lower()
            if ("conte" in low and "chave" in low) or ("key content" in low):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    pwd = parts[1].strip()
                    if pwd:
                        _WIFI_PASSWORD_CACHE[profile_name] = pwd
                        return pwd
        if attempt == 0:
            time.sleep(0.05)
    return None


def _list_saved_wifi_profiles_windows() -> list[str]:
    """Lista os nomes de todos os perfis Wi-Fi salvos no Windows na ordem de preferência."""
    if os.name != "nt":
        return []
    out = _run_cmd_text(["netsh", "wlan", "show", "profiles"])
    profiles: list[str] = []
    for line in out.splitlines():
        low = line.lower()
        if ":" in line and ("perfis" in low or "perfil" in low or "profile" in low):
            _, val = line.split(":", 1)
            name = val.strip()
            if name and not name.startswith("<") and name not in profiles:
                profiles.append(name)
    return profiles


def _list_visible_24ghz_ssids_windows() -> list[str]:
    """Lista os SSIDs visíveis no ar neste exato momento na faixa 2.4 GHz (canais 1 a 14)."""
    if os.name != "nt":
        return []
    out = _run_cmd_text(["netsh", "wlan", "show", "networks", "mode=bssid"])
    visible: list[str] = []
    current_ssid: str | None = None
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.upper().startswith("SSID ") and ":" in line:
            _, val = line.split(":", 1)
            current_ssid = val.strip()
        elif ("canal" in line.lower() or "channel" in line.lower()) and ":" in line and current_ssid:
            _, ch_str = line.split(":", 1)
            ch_str = ch_str.strip()
            if ch_str.isdigit() and int(ch_str) <= 14:
                if current_ssid not in visible:
                    visible.append(current_ssid)
    return visible


def _strip_5g_suffix(ssid: str) -> list[str]:
    """Gera candidatos de nome da rede 2.4 GHz a partir de um SSID 5 GHz (ex.: `DR.PC_5G` -> `DR.PC`)."""
    candidates: list[str] = []
    patterns = [
        r"[_\s-]?5g(hz)?$",
        r"[_\s-]?5\.0g(hz)?$",
        r"[_\s-]?5$",
    ]
    suffixes = (
        "-2G",
        "_2G",
        "-2.4G",
        "_2.4G",
        "-2.4GHz",
        "_2.4GHz",
        "-2GHz",
        "_2GHz",
        " 2.4G",
        " 2.4GHz",
        " 2G",
        " 2GHz",
        "",
    )
    for pat in patterns:
        base = re.sub(pat, "", ssid, flags=re.IGNORECASE).strip()
        if base and base != ssid:
            for suffix in suffixes:
                cand = f"{base}{suffix}"
                if cand not in candidates:
                    candidates.append(cand)
    return candidates


def _is_virtual_or_unwanted_ip(ip_str: str) -> bool:
    """Filtra IPs de loopback, link-local ou switches virtuais internos (Docker/WSL) quando possível."""
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except ValueError:
        return True
    if addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified:
        return True
    # 192.168.56.x é o Host-Only padrão do VirtualBox
    if ip_str.startswith("192.168.56."):
        return True
    return False


def _score_lan_ip(ip_str: str) -> int:
    """Atribui prioridade ao IP local (prioriza Wi-Fi/Hotspot real sobre sub-redes virtuais 172.16-31)."""
    if ip_str.startswith("192.168.4."):
        # Conectado diretamente no SoftAP do ESP!
        return 100
    if ip_str.startswith("192.168.43.") or ip_str.startswith("172.20.10.") or ip_str.startswith("192.168.137."):
        # Hotspots móveis (Android / Xiaomi / iPhone / Windows Mobile Hotspot)
        return 95
    if ip_str.startswith("192.168."):
        return 90
    if ip_str.startswith("10."):
        return 80
    if ip_str.startswith("172."):
        # 172.16..31 fora de 172.20.10 costuma ser WSL/Hyper-V/Docker no Windows
        return 40
    return 50


def get_active_lan_ips() -> list[str]:
    """Descobre todos os endereços IPv4 ativos do computador na rede atual, ordenados por relevância."""
    found: list[str] = []

    # 1. Sondagem de tabela de roteamento UDP para alvos públicos e privados comuns (sem enviar tráfego)
    probe_targets = [
        ("8.8.8.8", 80),
        ("1.1.1.1", 80),
        ("192.168.4.1", 80),
        ("192.168.0.1", 80),
        ("192.168.1.1", 80),
        ("192.168.43.1", 80),
        ("172.20.10.1", 80),
        ("10.0.0.1", 80),
    ]
    for target_host, target_port in probe_targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target_host, target_port))
                ip = s.getsockname()[0]
                if ip and not _is_virtual_or_unwanted_ip(ip) and ip not in found:
                    found.append(ip)
        except OSError:
            continue

    # 2. Resolução das interfaces locais pelo hostname do sistema
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0])
            if ip and not _is_virtual_or_unwanted_ip(ip) and ip not in found:
                found.append(ip)
    except OSError:
        pass

    # 3. Parsing complementar do ipconfig no Windows apenas se nenhum IP foi resolvido via socket
    if os.name == "nt" and not found:
        out = _run_cmd_text(["ipconfig"])
        for match in re.findall(r"(?:IPv4|Endere.o IPv4)[^:]*:\s*(\d{1,3}(?:\.\d{1,3}){3})", out, flags=re.IGNORECASE):
            if not _is_virtual_or_unwanted_ip(match) and match not in found:
                found.append(match)

    found.sort(key=_score_lan_ip, reverse=True)
    return found


def get_primary_lan_ip() -> str | None:
    """Retorna o endereço IPv4 principal da rede ativa atual (ou `None` se totalmente desconectado)."""
    ips = get_active_lan_ips()
    return ips[0] if ips else None


_CACHED_NET_INFO: CurrentNetworkInfo | None = None
_CACHED_NET_TS: float = 0.0


def get_current_network_info(
    include_passwords: bool = True,
    force_refresh: bool = False,
) -> CurrentNetworkInfo:
    """Inspeciona a rede Wi-Fi/LAN atualmente conectada no computador e suas credenciais."""
    global _CACHED_NET_INFO, _CACHED_NET_TS
    now = time.monotonic()
    if (
        not force_refresh
        and _CACHED_NET_INFO is not None
        and (now - _CACHED_NET_TS) < _DISCOVERY_CACHE_TTL
        and (not include_passwords or bool(_CACHED_NET_INFO.known_profiles))
    ):
        return _CACHED_NET_INFO

    active_ips = get_active_lan_ips()
    subnets: list[str] = []
    for ip in active_ips:
        prefix = ".".join(ip.split(".")[:3])
        if prefix not in subnets:
            subnets.append(prefix)

    info = CurrentNetworkInfo(
        primary_ip=active_ips[0] if active_ips else None,
        active_ips=active_ips,
        subnets=subnets,
    )

    if os.name == "nt":
        wlan_out = _run_cmd_text(["netsh", "wlan", "show", "interfaces"])
        for raw_line in wlan_out.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, val = [p.strip() for p in line.split(":", 1)]
            key_low = key.lower()
            if key_low == "ssid" and val:
                info.connected_ssid = val
            elif ("tipo de r" in key_low or "radio type" in key_low) and val:
                info.radio_type = val
            elif key_low in ("canal", "channel") and val.isdigit():
                info.channel = int(val)
            elif key_low in ("sinal", "signal") and val.endswith("%"):
                num = val.rstrip("%").strip()
                if num.isdigit():
                    info.signal_pct = int(num)

        if info.connected_ssid:
            ssid_up = info.connected_ssid.upper()
            info.is_5ghz = (
                (info.channel is not None and info.channel > 14)
                or ssid_up.endswith("5G")
                or ssid_up.endswith("5GHZ")
            )

        saved_names = _list_saved_wifi_profiles_windows()
        visible_24g = _list_visible_24ghz_ssids_windows()
        twin_candidates = _strip_5g_suffix(info.connected_ssid) if (info.connected_ssid and info.is_5ghz) else []

        # Se estiver em uma rede 5GHz (incompatível com ESP8266/ESP32 clássico), prioriza o perfil irmão 2.4GHz
        # que esteja realmente visível no ar agora (ex.: DR.PC-2G), ou salvo no Windows (ex.: DR.PC)
        chosen_esp_ssid = info.connected_ssid
        for cand in twin_candidates:
            for vis in visible_24g:
                if vis.lower() == cand.lower():
                    chosen_esp_ssid = vis
                    break
            if chosen_esp_ssid != info.connected_ssid:
                break
        if chosen_esp_ssid == info.connected_ssid and twin_candidates:
            base_lower = twin_candidates[-1].lower()
            for vis in visible_24g:
                if vis.lower().startswith(base_lower) and "5g" not in vis.lower():
                    chosen_esp_ssid = vis
                    break
        if chosen_esp_ssid == info.connected_ssid:
            for cand in twin_candidates:
                for saved in saved_names:
                    if saved.lower() == cand.lower():
                        chosen_esp_ssid = saved
                        break
                if chosen_esp_ssid != info.connected_ssid:
                    break
        if chosen_esp_ssid == info.connected_ssid and twin_candidates:
            chosen_esp_ssid = twin_candidates[-1]

        info.esp_target_ssid = chosen_esp_ssid
        if chosen_esp_ssid:
            info.is_5ghz_only = bool(
                info.is_5ghz
                and chosen_esp_ssid == info.connected_ssid
                and all(vis.lower() != chosen_esp_ssid.lower() for vis in visible_24g)
            )

        if include_passwords:
            ordered_names: list[str] = []
            for priority_name in (chosen_esp_ssid, info.connected_ssid, *saved_names):
                if priority_name and priority_name not in ordered_names and not priority_name.lower().startswith("bartender-"):
                    ordered_names.append(priority_name)

            target_slice = ordered_names[:16]
            pwd_map: dict[str, str | None] = {}
            if target_slice:
                with ThreadPoolExecutor(max_workers=min(3, len(target_slice))) as pool:
                    results = list(pool.map(_extract_wifi_profile_password, target_slice))
                for name, pwd in zip(target_slice, results):
                    pwd_map[name] = pwd

            if chosen_esp_ssid:
                info.esp_target_password = pwd_map.get(chosen_esp_ssid)
            if not info.esp_target_password and info.connected_ssid:
                info.esp_target_password = pwd_map.get(info.connected_ssid)

            seen_profile_pairs: set[tuple[str, str]] = set()
            for prof_name in target_slice:
                pwd = pwd_map.get(prof_name) or (
                    info.esp_target_password if prof_name == chosen_esp_ssid else None
                )
                pair = (prof_name, pwd or "")
                if pair not in seen_profile_pairs:
                    seen_profile_pairs.add(pair)
                    info.known_profiles.append(
                        WifiProfileCredential(
                            ssid=prof_name,
                            password=pwd or "",
                            is_current=(prof_name == info.connected_ssid),
                            is_24ghz_twin=(prof_name == chosen_esp_ssid and prof_name != info.connected_ssid),
                        )
                    )
                # Se o perfil salvo for 5GHz (ex.: DR.PC_5G), gera automaticamente os irmãos 2.4GHz
                # (ex.: DR.PC-2G, DR.PC_2G, DR.PC) com a senha do 5GHz para o Multi-WiFi do ESP!
                if pwd and (prof_name.upper().endswith("5G") or prof_name.upper().endswith("5GHZ")):
                    for twin_cand in _strip_5g_suffix(prof_name)[:4]:
                        twin_pair = (twin_cand, pwd)
                        if twin_pair not in seen_profile_pairs:
                            seen_profile_pairs.add(twin_pair)
                            info.known_profiles.append(
                                WifiProfileCredential(
                                    ssid=twin_cand,
                                    password=pwd,
                                    is_current=False,
                                    is_24ghz_twin=True,
                                )
                            )

    _CACHED_NET_INFO = info
    _CACHED_NET_TS = now
    return info


def discover_esp_via_udp(
    *,
    timeout: float = 0.45,
    sync_url: str = "",
    api_token: str = "",
) -> DiscoveredEsp | None:
    """Localiza instantaneamente o ESP na rede local via Broadcast UDP na porta `4210`.

    Se `sync_url` for informado (v3), o pacote de descoberta já entrega ao ESP a URL atualizada
    do servidor na rede atual (`BARTENDER_DISCOVER|<sync_url>|<api_token>`), eliminando a
    necessidade de configurar IP fixo no firmware!
    """
    active_ips = get_active_lan_ips()
    broadcast_targets: set[str] = {"255.255.255.255", "192.168.4.255"}
    for ip in active_ips:
        parts = ip.split(".")
        if len(parts) == 4:
            broadcast_targets.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")

    message = f"BARTENDER_DISCOVER|{sync_url}|{api_token}".encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        half_wait = max(0.15, timeout / 2.0)
        sock.settimeout(half_wait)

        for attempt in range(2):
            for bcast in broadcast_targets:
                try:
                    sock.sendto(message, (bcast, UDP_DISCOVERY_PORT))
                except OSError:
                    continue

            deadline = time.monotonic() + half_wait
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(1024)
                except OSError:
                    break
                text = data.decode("utf-8", errors="ignore").strip()
                if not text.startswith("{"):
                    continue
                try:
                    payload = json.loads(text)
                    if payload.get("ok") and (
                        payload.get("service") == "bartender-esp" or "pumps" in payload or "device" in payload
                    ):
                        esp_ip = str(payload.get("ip") or addr[0])
                        if esp_ip in ("0.0.0.0", "", "192.168.4.1") and addr[0] != "192.168.4.1":
                            esp_ip = addr[0]
                        return DiscoveredEsp(
                            ip=esp_ip,
                            port=int(payload.get("port") or 80),
                            rssi=payload.get("rssi"),
                            device=str(payload.get("device") or "ESP"),
                            method="udp_broadcast",
                        )
                except Exception:
                    continue
            if attempt == 0:
                time.sleep(0.04)
    finally:
        sock.close()

    return None


def get_arp_neighbor_ips(subnets: list[str] | None = None) -> list[str]:
    """Lê a tabela ARP do sistema operacional (`arp -a`) e extrai os IPs vizinhos ativos na LAN."""
    out = _run_cmd_text(["arp", "-a"])
    if not out:
        return []
    allowed_prefixes = subnets if subnets is not None else [
        ".".join(ip.split(".")[:3]) for ip in get_active_lan_ips()
    ]
    neighbors: list[str] = []
    for match in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", out):
        try:
            addr = ipaddress.IPv4Address(match)
        except ValueError:
            continue
        if addr.is_multicast or addr.is_loopback or addr.is_unspecified:
            continue
        last_octet = int(match.split(".")[3])
        if last_octet in (0, 255):
            continue
        prefix = ".".join(match.split(".")[:3])
        if allowed_prefixes and prefix not in allowed_prefixes and match != "192.168.4.1":
            continue
        if match not in neighbors:
            neighbors.append(match)
    return neighbors


async def _probe_single_candidate(
    client: httpx.AsyncClient,
    ip: str,
    port: int,
    method_label: str,
) -> DiscoveredEsp | None:
    """Testa se um endereço IPv4 responde com a telemetria JSON do firmware Bartender (`GET /status`)."""
    try:
        resp = await client.get(f"http://{ip}:{port}/status")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("ok") is True and ("pumps" in data or "state" in data):
                reported_ip = str(data.get("ip") or "").strip()
                effective_ip = ip if ip == "192.168.4.1" or not reported_ip or reported_ip in ("0.0.0.0", "192.168.4.1") else reported_ip
                return DiscoveredEsp(
                    ip=effective_ip,
                    port=port,
                    rssi=data.get("rssi"),
                    device=str(data.get("device") or "ESP"),
                    method=method_label,
                )
    except Exception:
        pass
    return None


async def push_cloud_config_to_esp(
    esp_ip: str,
    cloud_sync_url_or_port: str | int = 80,
    api_token_pos: str = "",
    *,
    port: int = 80,
    cloud_sync_url: str = "",
    api_token: str = "",
) -> bool:
    """Informa automaticamente ao ESP (via HTTP LAN `POST /config/cloud`) a URL atual do servidor."""
    if isinstance(cloud_sync_url_or_port, int):
        effective_port = cloud_sync_url_or_port
        effective_url = cloud_sync_url
    else:
        effective_port = port
        effective_url = cloud_sync_url or str(cloud_sync_url_or_port)
    effective_token = api_token or api_token_pos
    if not esp_ip or not effective_url:
        return False
    headers = {"X-Bartender-Token": effective_token} if effective_token else {}
    try:
        async with httpx.AsyncClient(timeout=1.5, headers=headers, trust_env=False) as client:
            resp = await client.post(
                f"http://{esp_ip}:{effective_port}/config/cloud",
                json={"cloud_sync_url": effective_url, "api_token": effective_token},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def push_wifi_config_to_esp_http(
    esp_ip: str,
    ssid_or_port: str | int = 80,
    password_pos: str = "",
    *,
    port: int = 80,
    ssid: str = "",
    password: str = "",
    cloud_sync_url: str = "",
    api_token: str = "",
) -> bool:
    """Envia as credenciais da rede Wi-Fi atual do servidor diretamente para o ESP via HTTP (`/config/wifi`)."""
    if isinstance(ssid_or_port, int):
        effective_port = ssid_or_port
        effective_ssid = ssid
        effective_pass = password
    else:
        effective_port = port
        effective_ssid = ssid or str(ssid_or_port)
        effective_pass = password or password_pos
    if not esp_ip or not effective_ssid:
        return False
    headers = {"X-Bartender-Token": api_token} if api_token else {}
    try:
        # O ESP executa tentarConexaoWifi() de forma síncrona (~7.5-10.5s) antes de devolver HTTP 200
        async with httpx.AsyncClient(timeout=14.0, headers=headers, trust_env=False) as client:
            resp = await client.post(
                f"http://{esp_ip}:{effective_port}/config/wifi",
                json={
                    "ssid": effective_ssid,
                    "password": effective_pass,
                    "cloud_sync_url": cloud_sync_url,
                    "api_token": api_token,
                },
            )
            return resp.status_code == 200
    except Exception:
        return False


def _ensure_wlan_profile_windows(ssid: str, password: str) -> None:
    """Garante que o perfil Wi-Fi do SoftAP do ESP exista no Windows antes do `netsh wlan connect`."""
    if os.name != "nt" or not ssid:
        return
    import tempfile

    xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM><security>
        <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
        <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{password}</keyMaterial></sharedKey>
    </security></MSM>
</WLANProfile>"""
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml)
            tmp_path = f.name
        _run_cmd_text(["netsh", "wlan", "add", "profile", f"filename={tmp_path}"])
    except Exception:
        pass
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


_LAST_PROVISIONED_ESP_IP: str | None = None


async def auto_provision_esp_via_softap_bridge(
    *,
    current_pc_ssid: str,
    target_24g_ssid: str,
    target_password: str,
    esp_port: int = 80,
    api_token: str = "",
    cloud_sync_url: str = "",
) -> bool:
    """Se o ESP estiver em uma rede desconhecida (modo AP `Bartender-ESP32`), conecta o PC
    temporariamente ao AP do ESP, envia o SSID/Senha da rede nova e reconecta o PC à rede original!
    """
    global _LAST_PROVISIONED_ESP_IP
    if os.name != "nt" or not current_pc_ssid or not target_24g_ssid:
        return False
    if current_pc_ssid.lower().startswith("bartender-"):
        return False

    vis_out = await asyncio.to_thread(_run_cmd_text, ["netsh", "wlan", "show", "networks"])
    ap_name: str | None = None
    for candidate_ap in ("Bartender-ESP32", "Bartender-Config"):
        if candidate_ap.lower() in vis_out.lower():
            ap_name = candidate_ap
            break
    if not ap_name:
        return False

    saved_profiles = await asyncio.to_thread(_list_saved_wifi_profiles_windows)
    if ap_name not in saved_profiles:
        await asyncio.to_thread(_ensure_wlan_profile_windows, ap_name, "12345678")

    provisioned = False
    try:
        # 1. Conecta temporariamente na rede SoftAP do ESP (Bartender-ESP32 / Bartender-Config)
        await asyncio.to_thread(_run_cmd_text, ["netsh", "wlan", "connect", f"name={ap_name}"])
        ap_reachable = False
        async with httpx.AsyncClient(timeout=1.0, trust_env=False) as client:
            for _ in range(18):
                await asyncio.sleep(0.5)
                try:
                    st = await client.get(f"http://192.168.4.1:{esp_port}/status")
                    if st.status_code == 200:
                        ap_reachable = True
                        break
                except Exception:
                    continue

        if ap_reachable:
            ok = await push_wifi_config_to_esp_http(
                "192.168.4.1",
                target_24g_ssid,
                target_password,
                port=esp_port,
                api_token=api_token,
                cloud_sync_url=cloud_sync_url,
            )
            if ok:
                provisioned = True
                async with httpx.AsyncClient(timeout=1.2, trust_env=False) as client:
                    for _ in range(5):
                        await asyncio.sleep(0.6)
                        try:
                            st = await client.get(f"http://192.168.4.1:{esp_port}/status")
                            if st.status_code == 200:
                                st_ip = str(st.json().get("ip") or "").strip()
                                if st_ip and st_ip not in ("0.0.0.0", "192.168.4.1"):
                                    _LAST_PROVISIONED_ESP_IP = st_ip
                                    break
                        except Exception:
                            continue
    finally:
        # 2. Sempre devolve o PC para a rede Wi-Fi original do evento/casa e aguarda DHCP
        await asyncio.to_thread(_run_cmd_text, ["netsh", "wlan", "connect", f"name={current_pc_ssid}"])
        for _ in range(12):
            await asyncio.sleep(0.5)
            ips = await asyncio.to_thread(get_active_lan_ips)
            if any(not ip.startswith("192.168.4.") for ip in ips):
                break
        await asyncio.sleep(1.0)

    return provisioned


async def discover_esp_on_network(
    *,
    esp_port: int = 80,
    port: int | None = None,
    preferred_host: str = "bartender.local",
    configured_host: str | None = None,
    cached_ip: str | None = None,
    api_token: str = "",
    sync_url: str = "",
    deep_scan: bool = True,
    allow_subnet_scan: bool | None = None,
) -> DiscoveredEsp | None:
    """Localiza automaticamente o ESP8266/ESP32 em qualquer rede sem depender de IP fixo.

    Executa 4 etapas progressivas de baixíssima latência:
      1. Broadcast UDP na porta `4210` (`~250ms`) — descobre o ESP em qualquer sub-rede ativa.
      2. Candidatos diretos (`cached_ip`, `preferred_host`, SoftAP `192.168.4.1`, mDNS `.local`).
      3. Vizinhos ativos na tabela ARP do sistema (`arp -a`) em paralelo (`~350ms`).
      4. Se `deep_scan=True`, varredura assíncrona concorrente (`/24`) nas sub-redes ativas do PC.
    """
    if port is not None:
        esp_port = port
    if configured_host is not None:
        preferred_host = configured_host
    if allow_subnet_scan is not None:
        deep_scan = allow_subnet_scan
    # Etapa 1: Descoberta instantânea via Broadcast UDP
    udp_hit = await asyncio.to_thread(
        discover_esp_via_udp,
        timeout=0.45,
        sync_url=sync_url,
        api_token=api_token,
    )
    if udp_hit is not None:
        if sync_url:
            await push_cloud_config_to_esp(
                udp_hit.ip,
                udp_hit.port,
                cloud_sync_url=sync_url,
                api_token=api_token,
            )
        return udp_hit

    # Etapa 2: Candidatos diretos (IP em cache, host configurado, SoftAP 192.168.4.1 e mDNS)
    direct_candidates: list[tuple[str, str]] = []
    if _LAST_PROVISIONED_ESP_IP and _LAST_PROVISIONED_ESP_IP not in ("", "0.0.0.0", "192.168.4.1"):
        direct_candidates.append((_LAST_PROVISIONED_ESP_IP, "softap_bridge_ip"))
    if cached_ip and cached_ip not in ("", "0.0.0.0") and all(cached_ip != c[0] for c in direct_candidates):
        direct_candidates.append((cached_ip, "cached_ip"))

    clean_host = (preferred_host or "").strip()
    if clean_host:
        if clean_host.lower().endswith(".local"):
            try:
                resolved = await asyncio.wait_for(
                    asyncio.to_thread(socket.gethostbyname, clean_host),
                    timeout=1.0,
                )
                if resolved and all(resolved != c[0] for c in direct_candidates):
                    direct_candidates.append((resolved, "mdns"))
            except Exception:
                pass
        elif all(clean_host != c[0] for c in direct_candidates):
            direct_candidates.append((clean_host, "configured_host"))

    active_ips = get_active_lan_ips()
    if any(ip.startswith("192.168.4.") for ip in active_ips) and all(
        "192.168.4.1" != c[0] for c in direct_candidates
    ):
        direct_candidates.append(("192.168.4.1", "softap"))

    headers = {"X-Bartender-Token": api_token} if api_token else {}
    if direct_candidates:
        async with httpx.AsyncClient(timeout=0.75, headers=headers, trust_env=False) as client:
            for cand_ip, label in direct_candidates:
                hit = await _probe_single_candidate(client, cand_ip, esp_port, label)
                if hit is not None:
                    if sync_url:
                        await push_cloud_config_to_esp(hit.ip, hit.port, cloud_sync_url=sync_url, api_token=api_token)
                    return hit

    # Etapa 3: Sondagem paralela dos vizinhos na tabela ARP da rede atual
    subnets = [".".join(ip.split(".")[:3]) for ip in active_ips]
    arp_ips = await asyncio.to_thread(get_arp_neighbor_ips, subnets)
    tested_ips = {c[0] for c in direct_candidates} | set(active_ips)
    arp_to_test = [ip for ip in arp_ips if ip not in tested_ips]

    if arp_to_test:
        async with httpx.AsyncClient(timeout=0.75, headers=headers, trust_env=False) as client:
            tasks = [_probe_single_candidate(client, ip, esp_port, "arp_table") for ip in arp_to_test]
            for res in await asyncio.gather(*tasks):
                if res is not None:
                    if sync_url:
                        await push_cloud_config_to_esp(res.ip, res.port, cloud_sync_url=sync_url, api_token=api_token)
                    return res
        tested_ips.update(arp_to_test)

    if not deep_scan or not subnets:
        return None

    # Etapa 4: Varredura assíncrona rápida da sub-rede atual (/24)
    # Limita às 2 interfaces principais (ex.: Wi-Fi/Hotspot atual) para concluir em ~1,2 segundo
    sweep_ips: list[str] = []
    for prefix in subnets[:2]:
        for host_num in range(1, 255):
            ip_cand = f"{prefix}.{host_num}"
            if ip_cand not in tested_ips:
                sweep_ips.append(ip_cand)

    if not sweep_ips:
        return None

    sem = asyncio.Semaphore(128)
    found_event = asyncio.Event()
    winner: list[DiscoveredEsp] = []

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(0.55, connect=0.38),
        headers=headers,
        trust_env=False,
        limits=httpx.Limits(max_connections=128, max_keepalive_connections=16),
    ) as client:
        async def _worker(ip_addr: str) -> None:
            if found_event.is_set():
                return
            async with sem:
                if found_event.is_set():
                    return
                res = await _probe_single_candidate(client, ip_addr, esp_port, "subnet_scan")
                if res is not None and not found_event.is_set():
                    winner.append(res)
                    found_event.set()

        await asyncio.gather(*(_worker(ip) for ip in sweep_ips))

    if winner:
        hit = winner[0]
        if sync_url:
            await push_cloud_config_to_esp(hit.ip, hit.port, cloud_sync_url=sync_url, api_token=api_token)
        return hit

    return None


def list_all_serial_ports() -> list[str]:
    """Enumera todas as portas seriais (`COM*` / `/dev/tty*`) visíveis no sistema operacional."""
    try:
        return [p.device for p in serial.tools.list_ports.comports()]
    except Exception:
        return []


def find_best_serial_port(preferred_port: str = "COM3") -> str | None:
    """Detecta automaticamente a porta USB Serial do ESP em qualquer porta USB do PC.

    Se `preferred_port` estiver presente, usa-a; caso contrário, identifica chips conversores
    USB-UART (`CH340`, `CP210x`, `CH9102`, `FTDI`, `ESP`, `USB Serial`) ou faz fallback para a
    primeira porta ativa encontrada.
    """
    try:
        port_objs = list(serial.tools.list_ports.comports())
    except Exception:
        return None

    all_devices = [p.device for p in port_objs]
    if not all_devices:
        return None

    if preferred_port in all_devices:
        return preferred_port

    usb_keywords = ("cp210", "ch340", "ch341", "ch910", "ftdi", "usb", "uart", "silicon labs", "esp", "wch")
    scored: list[tuple[int, str]] = []
    for p in port_objs:
        desc = f"{p.description or ''} {p.manufacturer or ''} {p.hwid or ''}".lower()
        score = 10
        if any(k in desc for k in usb_keywords):
            score += 50
        if "bluetooth" in desc:
            score -= 40
        scored.append((score, p.device))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def provision_esp_via_serial_sync(
    serial_port: str,
    serial_baud: int = 115200,
    ssid: str = "",
    password: str = "",
    cloud_sync_url: str = "",
) -> dict[str, object]:
    """Envia a rede Wi-Fi atual do servidor e a URL de Cloud Sync para o ESP via cabo USB Serial."""
    result: dict[str, object] = {"ok": False, "serial_port": serial_port}
    try:
        with serial.Serial(serial_port, serial_baud, timeout=0.6) as ser:
            time.sleep(0.35)
            ser.reset_input_buffer()
            if ssid:
                cmd_wifi = f"WIFI:{ssid}\t{password}\n".encode("utf-8")
                ser.write(cmd_wifi)
                ser.flush()
                time.sleep(0.2)
            if cloud_sync_url:
                cmd_cloud = f"CLOUD:{cloud_sync_url}\n".encode("utf-8")
                ser.write(cmd_cloud)
                ser.flush()
                time.sleep(0.15)
            ser.write(b"NETINFO\n")
            ser.flush()
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line.startswith("NETINFO:") or line.startswith("{"):
                    result["response"] = line
                    break
            result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _c_escape(val: str) -> str:
    """Escapa caracteres especiais (`\\` e `"`) para geração segura de literais C/C++ em `secrets.h`."""
    return val.replace("\\", "\\\\").replace('"', '\\"')


def sync_secrets_h_with_current_network(
    secrets_path: Path,
    *,
    api_token: str = "",
    cloud_sync_url: str = "",
    is_v3: bool = False,
) -> CurrentNetworkInfo:
    """Atualiza `bombas/secrets.h` automaticamente com a rede Wi-Fi conectada no PC e lista Multi-WiFi.

    Preserva qualquer rede anterior caso o computador esteja momentaneamente desconectado do Wi-Fi,
    e grava a tabela `SECRET_KNOWN_WIFI_LIST` para que o firmware conecte automaticamente em qualquer
    uma das redes conhecidas (casa, celular/hotspot, universidade, feira ou evento).
    """
    net_info = get_current_network_info(include_passwords=True)

    # Lê valores anteriores do secrets.h caso o PC esteja sem Wi-Fi no momento
    prev_ssid = ""
    prev_pass = ""
    prev_token = api_token
    prev_cloud = cloud_sync_url
    if secrets_path.exists():
        try:
            existing = secrets_path.read_text(encoding="utf-8", errors="ignore")
            m_ssid = re.search(r'#define\s+SECRET_WIFI_SSID\s+"([^"]*)"', existing)
            m_pass = re.search(r'#define\s+SECRET_WIFI_PASSWORD\s+"([^"]*)"', existing)
            m_tok = re.search(r'#define\s+SECRET_API_TOKEN\s+"([^"]*)"', existing)
            m_cld = re.search(r'#define\s+SECRET_CLOUD_SYNC_URL\s+"([^"]*)"', existing)
            if m_ssid:
                prev_ssid = m_ssid.group(1)
            if m_pass:
                prev_pass = m_pass.group(1)
            if not prev_token and m_tok:
                prev_token = m_tok.group(1)
            if not prev_cloud and m_cld:
                prev_cloud = m_cld.group(1)
        except Exception:
            pass

    target_ssid = net_info.esp_target_ssid or prev_ssid or ""
    target_pass = (
        net_info.esp_target_password
        if net_info.esp_target_password is not None
        else (prev_pass if target_ssid == prev_ssid else "")
    )

    # Monta lista de redes conhecidas para o Multi-WiFi embarcado
    known_entries: list[tuple[str, str]] = []
    if target_ssid:
        known_entries.append((target_ssid, target_pass))
    for prof in net_info.known_profiles:
        if all(prof.ssid != s for s, _ in known_entries):
            known_entries.append((prof.ssid, prof.password))
    if prev_ssid and all(prev_ssid != s for s, _ in known_entries):
        known_entries.append((prev_ssid, prev_pass))

    macro_items = ", \\\n  ".join(
        f'{{ "{_c_escape(s)}", "{_c_escape(p)}" }}' for s, p in known_entries[:16]
    )
    if not macro_items:
        macro_items = '{ "", "" }'

    if not is_v3 and (cloud_sync_url or "projetobartender-v3" in str(secrets_path).lower()):
        is_v3 = True

    ap_ssid = "Bartender-ESP32" if not is_v3 else "Bartender-Config"

    lines = [
        "#pragma once",
        "",
        "/*",
        " * ============================================================================",
        " * CREDENCIAIS SINCRONIZADAS AUTOMATICAMENTE PELO SERVIDOR BARTENDER.OS",
        " * ============================================================================",
        " * Este arquivo e atualizado automaticamente com a rede Wi-Fi ativa do PC",
        " * e todas as redes salvas (Multi-WiFi), permitindo que o ESP conecte em",
        " * qualquer ambiente (roteador, hotspot de celular ou evento) sem rede fixa!",
        " * ============================================================================",
        " */",
        "",
        "// Rede Wi-Fi principal detectada automaticamente na conexao atual do Servidor",
        f'#define SECRET_WIFI_SSID      "{_c_escape(target_ssid)}"',
        f'#define SECRET_WIFI_PASSWORD  "{_c_escape(target_pass)}"',
        "",
        "// Lista Multi-WiFi de redes conhecidas (o ESP escaneia e conecta em qualquer uma disponivel!)",
        "#define SECRET_KNOWN_WIFI_LIST \\",
        f"  {macro_items}",
        "",
        "// Rede Wi-Fi propria do ESP (sempre acessivel em http://192.168.4.1 se sem roteador)",
        f'#define SECRET_AP_SSID        "{ap_ssid}"',
        '#define SECRET_AP_PASSWORD    "12345678"',
        "",
        "// Token opcional de autenticacao HTTP/IoT",
        f'#define SECRET_API_TOKEN      "{_c_escape(prev_token)}"',
    ]

    if is_v3:
        lines.extend(
            [
                "",
                "// URL de Sincronizacao IoT (tambem atualizada automaticamente via UDP Discovery na LAN!)",
                f'#define SECRET_CLOUD_SYNC_URL "{_c_escape(prev_cloud)}"',
            ]
        )

    lines.append("")
    if os.getenv("ESP32_MODE") == "simulator":
        return net_info
    new_content = "\n".join(lines)
    try:
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        current_content = (
            secrets_path.read_text(encoding="utf-8", errors="ignore")
            if secrets_path.exists()
            else None
        )
        if current_content != new_content:
            secrets_path.write_text(new_content, encoding="utf-8")
    except Exception:
        pass

    return net_info
