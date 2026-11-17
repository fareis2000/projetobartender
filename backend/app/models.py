"""Contratos de dados, schemas REST/WebSocket e validações de segurança com Pydantic v2.

Papel na Arquitetura:
---------------------
Define todos os modelos de entrada e saída compartilhados entre o servidor Python, a
documentação automática OpenAPI/Swagger (`/docs`) e o cliente TypeScript (`frontend/src/types/bartender.ts`).

Valor Técnico e de Segurança Física:
------------------------------------
Em sistemas ciberfísicos (software que aciona bombas reais de líquidos), a validação de
dados é uma barreira crítica de segurança física:
  - Impede vazões inválidas (`<= 1.0` ou `> 200.0 ml/s`) que causariam divisão por zero ou
    tempos de acionamento absurdos nos relés;
  - Bloqueia pedidos personalizados abaixo de `10 ml` (acionamento curto demais para vencer
    a inércia hidráulica) ou acima de `450 ml` (prevenção contra transbordamento do copo no balcão).
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

# Identificadores canônicos das 4 bombas físicas (espelham as chaves no firmware bombas.ino)
PumpId = Literal["amarelo", "vermelho", "verde", "azul"]

# Modos de operação suportados pelo orquestrador híbrido ESP32Controller
ConnectionMode = Literal["auto", "wifi", "serial", "simulator"]

# Estados possíveis do ciclo de vida de preparo de uma bebida na interface e WebSocket
PrepState = Literal["idle", "dispensing", "completed", "stopped", "error"]


class PumpConfig(BaseModel):
    """Representa a configuração física, estética e hidráulica de uma bomba dosadora.

    Atributos:
        id (PumpId): Chave interna imutável da bomba (`amarelo`, `vermelho`, `verde`, `azul`).
        label (str): Rótulo amigável exibido no painel técnico (ex.: `'Bomba 1 · Amarela'`).
        ingredient (str): Nome comercial da bebida/xarope atualmente conectado à mangueira.
        description (str): Breve descrição sensorial exibida no estúdio "Monte seu Drink".
        gpio (int): Pino GPIO correspondente no ESP32-WROOM-32 (`16`, `17`, `18` ou `19`).
        flow_rate_ml_s (float): Vazão real calibrada em mililitros por segundo (`1.0 < vazão <= 200.0`).
        color_hex (str): Cor hexadecimal usada para renderizar camadas no copo vetorial e sliders.
        is_mixer (bool): Indica se a bomba é uma base diluidora/gaseificada (permite slider maior até 350 ml).
    """

    id: PumpId
    label: str
    ingredient: str
    description: str
    gpio: int
    flow_rate_ml_s: float = Field(gt=1.0, le=200.0)
    color_hex: str
    is_mixer: bool = False


class PumpUpdateRequest(BaseModel):
    """Payload parcial (`PUT /api/pumps/{pump_id}`) para troca de garrafa ou recalibração de vazão.

    Todos os campos são opcionais para permitir atualização granular sem sobrescrever metadados fixos.
    """

    ingredient: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=120)
    flow_rate_ml_s: float | None = Field(default=None, gt=1.0, le=200.0)


class DoseStep(BaseModel):
    """Representa uma etapa atômica de dosagem dentro de uma receita sequencial.

    Atributos:
        pump (PumpId): Bomba que será acionada nesta etapa.
        ml (float): Volume alvo em mililitros (`0 < ml <= 500`).
        pause_ms (int): Pausa de estabilização hidráulica em milissegundos após desligar a bomba
            (`0` a `10000 ms`), evitando picos simultâneos de corrente na fonte 12V e respingos.
    """

    pump: PumpId
    ml: float = Field(gt=0, le=500)
    pause_ms: int = Field(default=1000, ge=0, le=10000)


class DrinkRecipe(BaseModel):
    """Modelo completo de um coquetel do cardápio com metadados visuais e métricas calculadas.

    Os campos `total_ml` e `estimated_seconds` são recalculados dinamicamente pelo `catalog.py`
    sempre que a calibração de vazão (`flow_rate_ml_s`) de qualquer bomba é alterada.
    """

    id: str
    code: str
    name: str
    subtitle: str
    description: str
    category: str
    badge: str
    accent_from: str
    accent_to: str
    glass_color: str
    steps: list[DoseStep]
    total_ml: float = 0.0
    estimated_seconds: float = 0.0


class CustomDrinkRequest(BaseModel):
    """Payload enviado pelo estúdio interativo 'Monte seu Drink' (`POST /api/dispense/custom`).

    Inclui validação cruzada (`validate_total_volume`) sobre a soma dos 4 ingredientes para
    garantir operação limpa e impedir transbordamento físico do copo.
    """

    name: str = Field(default="Mix Personalizado", min_length=1, max_length=40)
    amarelo: float = Field(default=0, ge=0, le=450)
    vermelho: float = Field(default=0, ge=0, le=450)
    verde: float = Field(default=0, ge=0, le=450)
    azul: float = Field(default=0, ge=0, le=450)

    @model_validator(mode="after")
    def validate_total_volume(self) -> "CustomDrinkRequest":
        """Valida os limites mínimo (10 ml) e máximo (450 ml) do volume combinado do copo."""
        total = self.amarelo + self.vermelho + self.verde + self.azul
        if total < 10:
            raise ValueError("Selecione pelo menos 10 ml no total para preparar o drink.")
        if total > 450:
            raise ValueError("O volume máximo de segurança por copo é de 450 ml.")
        return self


class ConnectionConfig(BaseModel):
    """Configuração persistente dos parâmetros de conexão com o microcontrolador ESP32/ESP8266."""

    mode: ConnectionMode = "auto"
    esp32_host: str = "bartender.local"
    esp32_port: int = Field(default=80, ge=1, le=65535)
    serial_port: str = "COM3"
    serial_baud: int = 115200


class PreparationStatus(BaseModel):
    """Telemetria instantânea do preparo em andamento, transmitida via REST e WebSocket (`/api/ws`).

    Alimenta a animação do jato líquido, a barra de progresso percentual e o cronômetro
    no `PreparationModal` de todos os dispositivos conectados simultaneamente.
    """

    state: PrepState = "idle"
    drink_id: str | None = None
    drink_name: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    current_pump: PumpId | None = None
    current_step_index: int = 0
    total_steps: int = 0
    message: str = "Pronto para preparar seu próximo drink"
    transport: Literal["wifi", "serial", "simulator"] | None = None
    elapsed_seconds: float = 0.0
    total_seconds: float = 0.0


class HardwareHealth(BaseModel):
    """Diagnóstico completo de conectividade e saúde do hardware ESP32.

    Informa qual transporte efetivo foi selecionado pelo algoritmo de fallback (`active_transport`),
    além de intensidade de sinal Wi-Fi (`wifi_rssi` em dBm), IP resolvido e portas COM enumeradas.
    """

    mode: ConnectionMode
    active_transport: Literal["wifi", "serial", "simulator", "disconnected"]
    wifi_reachable: bool = False
    wifi_ip: str | None = None
    wifi_rssi: int | None = None
    serial_connected: bool = False
    available_serial_ports: list[str] = []
    esp32_host: str
    esp32_port: int
    serial_port: str
    serial_baud: int
    detail: str = ""
    connected_ssid: str | None = None
    esp_target_ssid: str | None = None
    server_lan_ip: str | None = None
    discovered_via: str | None = None


class NetworkSyncResult(BaseModel):
    """Resultado de uma varredura e sincronização ativa da rede atual com o ESP32/ESP8266."""

    ok: bool = True
    connected_ssid: str | None = None
    esp_target_ssid: str | None = None
    wifi_password_found: bool = False
    server_lan_ip: str = "127.0.0.1"
    lan_ips: list[str] = []
    secrets_updated: bool = False
    serial_provisioned: bool = False
    esp_discovered: bool = False
    esp_ip: str | None = None
    discovered_via: str | None = None
    hardware: HardwareHealth
    message: str = ""



class SystemSnapshot(BaseModel):
    """Envelope unificado emitido no WebSocket combinando telemetria de preparo e saúde física."""

    status: PreparationStatus
    hardware: HardwareHealth
