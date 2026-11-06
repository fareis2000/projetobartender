"""Motor Financeiro de Pagamentos Pix, QR Code Vetorial e Estornos — Bartender.OS v3.0.

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Abstrai toda a geração de cobranças Pix dinâmicas, validação de status bancário, estornos
automatizados e renderização vetorial de QR Codes (`SVG`), operando em dois modos:

1. **Modo Mercado Pago Oficial (`provider == 'mercadopago'`):**
   - Cria cobranças Pix reais via `POST https://api.mercadopago.com/v1/payments` usando o
     `Access Token` da própria conta Mercado Pago do bar (liquidação direta no caixa do bar).
   - **Split Inteligente com Fallback Resiliente:** Se a plataforma SaaS tiver configurado
     comissão (`platform_fee_cents > 0`) e o token for OAuth Marketplace (`APP_USR-...`),
     envia `application_fee` automaticamente. Caso o bar tenha colado um Access Token comum
     sem vínculo OAuth Marketplace e a API recuse o parâmetro, o módulo **refaz a chamada
     automaticamente sem `application_fee`** com nova chave de idempotência (`{order_id}-direct`),
     garantindo zero perda de vendas no balcão!
   - **Idempotência Bancária (`X-Idempotency-Key`):** Evita cobranças ou estornos duplicados
     mesmo sob oscilação de internet móvel.
2. **Modo Pix Simulado Homologado (`provider == 'simulated'`):**
   - Gera um payload **EMV® QRCPS-MPM (BRCode Pix Copia e Cola)** estruturalmente autêntico
     com cálculo real de checksum polinomial `CRC16-CCITT (0x1021)` e QR Code SVG embutido,
     permitindo demonstrações comerciais B2B realistas sem movimentar dinheiro real.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import uuid
from dataclasses import dataclass

import httpx
import segno


_UUID_PUBKEY_RE = re.compile(
    r"^(APP_USR|TEST)-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def normalize_mp_access_token(raw: str | None) -> str:
    """Normaliza um Access Token colado pelo dono do bar (remove espaços, aspas e prefixo `Bearer `)."""
    if not raw:
        return ""
    clean = raw.strip().strip("\"'`").strip()
    if clean.lower().startswith("authorization:"):
        clean = clean[len("authorization:") :].strip()
    while clean.lower().startswith("bearer "):
        clean = clean[len("bearer ") :].strip()
    return clean.strip("\"'`").strip()


def validate_mp_access_token_format(raw: str | None) -> tuple[bool, str, str]:
    """Valida se a credencial informada tem formato autêntico de `Access Token` do Mercado Pago.

    Retorna `(is_valid, normalized_token, error_message_pt)`.
    Detecta e explica imediatamente erros comuns de cópia/colagem (URL da página, `Public Key` curta,
    `Client Secret` OAuth de 32 caracteres ou autofill acidental do navegador).
    """
    clean = normalize_mp_access_token(raw)
    if not clean:
        return (False, "", "O Access Token do Mercado Pago está vazio.")

    if clean.lower().startswith(("http://", "https://")) or "://" in clean:
        return (
            False,
            clean,
            "O valor colado é um link/endereço web (URL) e não um Access Token. "
            "Abra 'Credenciais de produção' no Mercado Pago Developers e clique no botão de copiar "
            "ao lado de 'Access Token' (ele começa com APP_USR-).",
        )

    if _UUID_PUBKEY_RE.match(clean):
        return (
            False,
            clean,
            "Você colou a 'Public Key' (chave pública curta de ~44 caracteres). "
            "Copie o 2º campo logo abaixo dela chamado 'Access Token' (começa com APP_USR- e tem ~70 caracteres).",
        )

    if any(ch.isspace() for ch in clean):
        return (
            False,
            clean,
            "O Access Token contém espaços ou quebras de linha inválidas. Copie apenas o valor de 'Access Token'.",
        )

    if not (clean.startswith("APP_USR-") or clean.startswith("TEST-")) or len(clean) < 48:
        return (
            False,
            clean,
            "Formato inválido de Access Token. No painel Mercado Pago Developers, abra 'Credenciais de produção' "
            "e copie o campo 'Access Token' (ele começa obrigatoriamente com APP_USR- ou TEST- e possui ~70 caracteres).",
        )

    return (True, clean, "")


async def verify_mercadopago_token(raw_token: str | None) -> dict[str, object]:
    """Valida formato + autenticidade ao vivo do `Access Token` na API oficial do Mercado Pago (`/users/me`)."""
    ok, clean_token, reason = validate_mp_access_token_format(raw_token)
    if not ok:
        raise ValueError(reason)

    headers = {"Authorization": f"Bearer {clean_token}"}
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        resp = await client.get("https://api.mercadopago.com/users/me", headers=headers)

    if resp.status_code in (401, 403):
        raise ValueError(
            "O Mercado Pago recusou este Access Token (401/403 — chave expirada, revogada ou incorreta). "
            "Gere/copie novamente o 'Access Token' em 'Credenciais de produção' no Mercado Pago Developers."
        )
    if resp.status_code >= 400:
        raise ValueError(f"Não foi possível validar o token no Mercado Pago ({resp.status_code}).")

    data = resp.json()
    first_name = str(data.get("first_name") or "").strip()
    last_name = str(data.get("last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip() or str(data.get("nickname") or "Conta Verificada")
    return {
        "ok": True,
        "account_id": str(data.get("id") or ""),
        "nickname": str(data.get("nickname") or ""),
        "email": str(data.get("email") or ""),
        "first_name": full_name,
        "is_test": clean_token.startswith("TEST-"),
    }


@dataclass
class PixChargeResult:
    """Resultado normalizado da criação de uma cobrança Pix (seja Simulada ou Mercado Pago Real).

    Atributos:
        provider: Provedor efetivamente utilizado (`simulated` ou `mercadopago`).
        external_id: ID da transação no provedor (`sim_...` ou ID numérico do Mercado Pago).
        qr_code_text: Código Pix Copia e Cola completo (padrão EMV BRCode `000201...`).
        qr_code_data_uri: Imagem do QR Code pronta para `<img src="...">` (`SVG` ou `PNG` Base64).
        expires_at_iso: Timestamp ISO-8601 UTC limite para pagamento da cobrança.
    """

    provider: str
    external_id: str
    qr_code_text: str
    qr_code_data_uri: str
    expires_at_iso: str


def generate_qr_svg_data_uri(content: str, scale: int = 6, dark: str = "#2d1810", light: str = "#fffaf2") -> str:
    """Renderiza qualquer texto/URL em um QR Code SVG compacto codificado como `data:image/svg+xml`."""
    qr = segno.make(content, micro=False)
    return qr.svg_data_uri(scale=scale, border=2, dark=dark, light=light)


def generate_qr_svg_bytes(content: str, scale: int = 8) -> bytes:
    """Gera os bytes brutos de um arquivo `.svg` vetorial de alta nitidez para impressão de placas de balcão."""
    qr = segno.make(content, micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=2, dark="#2d1810", light="#ffffff")
    return buf.getvalue()


def _emv_field(tag: str, value: str) -> str:
    """Formata um campo TLV (*Tag-Length-Value*) de 2 dígitos decimais do padrão EMV BRCode do Banco Central."""
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    """Calcula o dígito verificador hexadecimal de 4 caracteres `CRC-16/CCITT-FALSE` (polinômio `0x1021`, init `0xFFFF`).

    Exigido no campo final `6304` da especificação oficial do Pix (Banco Central do Brasil).
    """
    crc = 0xFFFF
    for ch in payload.encode("ascii", errors="ignore"):
        crc ^= ch << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def build_simulated_brcode(amount_cents: int, bar_name: str, txid: str) -> str:
    """Gera código Pix Copia e Cola no formato EMV BRCode válido para demonstração/testes.

    Monta os campos obrigatórios do arranjo Pix (`00` Payload Format, `01` Point of Initiation
    dinâmico `12`, `26` GUI `BR.GOV.BCB.PIX` + chave sandbox, `53` moeda BRL `986`, `54` valor
    em reais, `58` país `BR`, `59` recebedor, `60` cidade, `62` TXID e `63` CRC16).
    """
    merchant_acc = _emv_field("00", "BR.GOV.BCB.PIX") + _emv_field("01", "pix-sandbox@bartender.os")
    clean_bar = "".join(c for c in bar_name.upper() if c.isalnum() or c == " ")[:25].strip() or "BARTENDER OS"
    clean_txid = "".join(c for c in txid if c.isalnum())[:25] or "SIMPIX01"
    amount_str = f"{amount_cents / 100:.2f}"

    body = (
        _emv_field("00", "01")
        + _emv_field("01", "12")
        + _emv_field("26", merchant_acc)
        + _emv_field("52", "0000")
        + _emv_field("53", "986")
        + _emv_field("54", amount_str)
        + _emv_field("58", "BR")
        + _emv_field("59", clean_bar)
        + _emv_field("60", "SAO PAULO")
        + _emv_field("62", _emv_field("05", clean_txid))
        + "6304"
    )
    return body + _crc16_ccitt(body)


async def create_pix_charge(
    *,
    provider: str,
    mp_access_token: str,
    order_id: str,
    order_number: int,
    bar_id: str,
    bar_name: str,
    drink_name: str,
    amount_cents: int,
    platform_fee_cents: int,
    expiration_seconds: int = 300,
    public_base_url: str = "",
) -> PixChargeResult:
    """Cria uma cobrança Pix imediata para um pedido validado (Simulador Local ou API Mercado Pago).

    Se `public_base_url` for um endereço `https://` público, registra automaticamente a
    `notification_url` de Webhook dedicada do bar (`/api/webhooks/mercadopago/{bar_id}`).
    Mesmo sem HTTPS público (ex: rede local ou túnel temporário), o worker de manutenção em
    `machine_runtime.py` + o polling ativo no retorno do cliente garantem confirmação rápida!
    """
    now = dt.datetime.now(dt.timezone.utc)
    expires_at = now + dt.timedelta(seconds=expiration_seconds)
    expires_iso = expires_at.isoformat()

    clean_token = normalize_mp_access_token(mp_access_token)

    # Caminho 1: Modo Simulado (ou fallback seguro caso o bar esteja em modo simulado)
    if provider == "simulated":
        ext_id = f"sim_{uuid.uuid4().hex[:16]}"
        brcode = build_simulated_brcode(amount_cents, bar_name, f"ORD{order_number}{order_id[:8]}")
        data_uri = generate_qr_svg_data_uri(brcode)
        return PixChargeResult(
            provider="simulated",
            external_id=ext_id,
            qr_code_text=brcode,
            qr_code_data_uri=data_uri,
            expires_at_iso=expires_iso,
        )

    is_valid_tok, clean_token, tok_err = validate_mp_access_token_format(clean_token)
    if not is_valid_tok:
        raise RuntimeError(
            f"Credencial Mercado Pago inválida no painel do bar: {tok_err} "
            "Acesse /painel → Conta Pix / Mercado Pago para corrigir ou ative o Modo Pix Simulado."
        )

    # Integração Real Mercado Pago Pix API (/v1/payments)
    # IMPORTANTE: O Mercado Pago exige que `date_of_expiration` do Pix tenha no mínimo 30 minutos;
    # valores menores (ex: 5 min) são aceitos no POST inicial mas cancelados/expirados assincronamente
    # 2 segundos depois pelo motor do Mercado Pago (`status_detail: expired`), fazendo o banco pagador
    # recusar o QR Code ("Pix não aceito pelo banco recebedor"). Usamos no mínimo 35 min (2100s) na API!
    mp_expires_at = now + dt.timedelta(seconds=max(expiration_seconds, 2100))
    mp_exp = mp_expires_at.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    payload: dict[str, object] = {
        "transaction_amount": round(amount_cents / 100.0, 2),
        "description": f"Pedido #{order_number} · {drink_name} ({bar_name})"[:120],
        "payment_method_id": "pix",
        "external_reference": order_id,
        "date_of_expiration": mp_exp,
        "payer": {
            "email": f"pedido.{order_id[:8]}@bartenderos.com",
            "first_name": "Cliente",
            "last_name": bar_name[:25],
        },
    }

    # Split opcional caso o token seja OAuth Marketplace e haja comissão da plataforma configurada
    if platform_fee_cents > 0 and clean_token.startswith("APP_USR-"):
        # Nota: Mercado Pago aceita application_fee quando o token foi gerado via OAuth Marketplace.
        # Tentamos primeiro com application_fee se aplicável; se a conta for token simples direto, fazemos fallback limpo.
        payload["application_fee"] = round(platform_fee_cents / 100.0, 2)

    # Registra Webhook automático apenas em domínios HTTPS válidos aceitos pelo Mercado Pago
    if public_base_url.startswith("https://"):
        payload["notification_url"] = f"{public_base_url}/api/webhooks/mercadopago/{bar_id}"

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "X-Idempotency-Key": order_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=12.0, trust_env=False) as client:
        resp = await client.post("https://api.mercadopago.com/v1/payments", json=payload, headers=headers)
        if resp.status_code >= 400 and "application_fee" in payload:
            # Conta com Access Token padrão sem Marketplace OAuth: recria cobrança 100% direta no bar
            payload.pop("application_fee", None)
            headers["X-Idempotency-Key"] = f"{order_id}-direct"
            resp = await client.post("https://api.mercadopago.com/v1/payments", json=payload, headers=headers)

        if resp.status_code >= 400:
            detail = resp.text[:240]
            try:
                err_json = resp.json()
                detail = err_json.get("message") or detail
            except Exception:
                pass
            if "without key enabled" in str(detail).lower():
                raise RuntimeError(
                    "Sua conta Mercado Pago ainda não tem nenhuma Chave Pix ativa para gerar QR Code. "
                    "Abra o app Mercado Pago no celular → Área Pix → Minhas chaves → Cadastrar chave aleatória "
                    "(leva 15s e não mexe nas suas chaves do Nubank) e tente novamente!"
                )
            if resp.status_code == 401:
                raise RuntimeError(
                    f"Mercado Pago recusou o Access Token (401: {detail}). "
                    "Confira no /painel → Conta Pix / Mercado Pago se você copiou o 'Access Token' (APP_USR-...) "
                    "em 'Credenciais de produção' e se sua conta Mercado Pago possui pelo menos 1 chave Pix cadastrada."
                )
            raise RuntimeError(f"Erro ao gerar Pix no Mercado Pago ({resp.status_code}): {detail}")

        data = resp.json()
        ext_id = str(data.get("id", ""))
        tx_data = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
        qr_code_text = str(tx_data.get("qr_code") or "")
        qr_b64 = str(tx_data.get("qr_code_base64") or "")
        if qr_b64:
            data_uri = f"data:image/png;base64,{qr_b64}"
        elif qr_code_text:
            # Se o Mercado Pago enviar apenas o código Copia e Cola textual, renderizamos o SVG localmente
            data_uri = generate_qr_svg_data_uri(qr_code_text)
        else:
            raise RuntimeError("Mercado Pago não retornou o código Pix Copia e Cola.")

        return PixChargeResult(
            provider="mercadopago",
            external_id=ext_id,
            qr_code_text=qr_code_text,
            qr_code_data_uri=data_uri,
            expires_at_iso=expires_iso,
        )


async def check_mercadopago_payment_status(mp_access_token: str, payment_id: str) -> str:
    """Retorna 'approved', 'pending', 'cancelled', 'rejected' ou 'refunded'.

    Utilizada tanto para autenticar notificações Webhook recebidas (evitando spoofing de webhook
    falso, já que sempre consultamos a fonte oficial `/v1/payments/{id}`) quanto pelo loop de
    conciliação automática em background.
    """
    clean_token = normalize_mp_access_token(mp_access_token)
    if not clean_token or not payment_id or payment_id.startswith("sim_"):
        return "pending"
    headers = {"Authorization": f"Bearer {clean_token}"}
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        resp = await client.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
        if resp.status_code >= 400:
            return "pending"
        data = resp.json()
        return str(data.get("status") or "pending").lower()


async def refund_pix_payment(provider: str, mp_access_token: str, payment_id: str | None) -> bool:
    """Dispara o estorno integral (devolução Pix instantânea ao banco do cliente) com chave de idempotência.

    Permite ao dono do bar resolver em 1 clique no `/painel` qualquer eventualidade operacional
    (ex: cliente desistiu ou acabou o gelo), devolvendo o Pix diretamente pela API `/refunds`.
    """
    if provider == "simulated" or not payment_id or payment_id.startswith("sim_"):
        return True
    clean_token = normalize_mp_access_token(mp_access_token)
    if not clean_token:
        raise RuntimeError("Access Token do Mercado Pago ausente para realizar estorno.")
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "X-Idempotency-Key": f"refund-{payment_id}",
    }
    async with httpx.AsyncClient(timeout=12.0, trust_env=False) as client:
        resp = await client.post(
            f"https://api.mercadopago.com/v1/payments/{payment_id}/refunds",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Falha ao estornar no Mercado Pago ({resp.status_code}): {resp.text[:180]}")
        return True


async def cancel_mercadopago_payment(mp_access_token: str, payment_id: str | None) -> None:
    """Invalida proativamente um QR Code Pix pendente no Mercado Pago quando o cliente cancela o pedido."""
    clean_token = normalize_mp_access_token(mp_access_token)
    if not clean_token or not payment_id or payment_id.startswith("sim_"):
        return
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "X-Idempotency-Key": f"cancel-{payment_id}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            await client.put(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                json={"status": "cancelled"},
                headers=headers,
            )
    except Exception:
        pass
