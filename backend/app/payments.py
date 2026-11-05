from __future__ import annotations

import datetime as dt
import io
import uuid
from dataclasses import dataclass

import httpx
import segno


@dataclass
class PixChargeResult:
    provider: str
    external_id: str
    qr_code_text: str
    qr_code_data_uri: str
    expires_at_iso: str


def generate_qr_svg_data_uri(content: str, scale: int = 6, dark: str = "#2d1810", light: str = "#fffaf2") -> str:
    qr = segno.make(content, micro=False)
    return qr.svg_data_uri(scale=scale, border=2, dark=dark, light=light)


def generate_qr_svg_bytes(content: str, scale: int = 8) -> bytes:
    qr = segno.make(content, micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=2, dark="#2d1810", light="#ffffff")
    return buf.getvalue()


def _emv_field(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
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
    """Gera código Pix Copia e Cola no formato EMV BRCode válido para demonstração/testes."""
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
    now = dt.datetime.now(dt.timezone.utc)
    expires_at = now + dt.timedelta(seconds=expiration_seconds)
    expires_iso = expires_at.isoformat()

    if provider == "simulated" or not mp_access_token.strip():
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

    # Integração Real Mercado Pago Pix API (/v1/payments)
    mp_exp = expires_at.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    payload: dict[str, object] = {
        "transaction_amount": round(amount_cents / 100.0, 2),
        "description": f"Pedido #{order_number} · {drink_name} ({bar_name})"[:120],
        "payment_method_id": "pix",
        "external_reference": order_id,
        "date_of_expiration": mp_exp,
        "payer": {
            "email": f"pedido.{order_id[:8]}@bartenderos.app",
            "first_name": "Cliente",
            "last_name": bar_name[:25],
        },
    }

    # Split opcional caso o token seja OAuth Marketplace e haja comissão da plataforma configurada
    if platform_fee_cents > 0 and mp_access_token.startswith("APP_USR-"):
        # Nota: Mercado Pago aceita application_fee quando o token foi gerado via OAuth Marketplace.
        # Tentamos primeiro com application_fee se aplicável; se a conta for token simples direto, fazemos fallback limpo.
        payload["application_fee"] = round(platform_fee_cents / 100.0, 2)

    if public_base_url.startswith("https://"):
        payload["notification_url"] = f"{public_base_url}/api/webhooks/mercadopago/{bar_id}"

    headers = {
        "Authorization": f"Bearer {mp_access_token.strip()}",
        "X-Idempotency-Key": order_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
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
            raise RuntimeError(f"Erro ao gerar Pix no Mercado Pago ({resp.status_code}): {detail}")

        data = resp.json()
        ext_id = str(data.get("id", ""))
        tx_data = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
        qr_code_text = str(tx_data.get("qr_code") or "")
        qr_b64 = str(tx_data.get("qr_code_base64") or "")
        if qr_b64:
            data_uri = f"data:image/png;base64,{qr_b64}"
        elif qr_code_text:
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
    """Retorna 'approved', 'pending', 'cancelled', 'rejected' ou 'refunded'."""
    if not mp_access_token.strip() or not payment_id or payment_id.startswith("sim_"):
        return "pending"
    headers = {"Authorization": f"Bearer {mp_access_token.strip()}"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
        if resp.status_code >= 400:
            return "pending"
        data = resp.json()
        return str(data.get("status") or "pending").lower()


async def refund_pix_payment(provider: str, mp_access_token: str, payment_id: str | None) -> bool:
    if provider == "simulated" or not payment_id or payment_id.startswith("sim_"):
        return True
    if not mp_access_token.strip():
        raise RuntimeError("Access Token do Mercado Pago ausente para realizar estorno.")
    headers = {
        "Authorization": f"Bearer {mp_access_token.strip()}",
        "X-Idempotency-Key": f"refund-{payment_id}",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.post(
            f"https://api.mercadopago.com/v1/payments/{payment_id}/refunds",
            headers=headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Falha ao estornar no Mercado Pago ({resp.status_code}): {resp.text[:180]}")
        return True
