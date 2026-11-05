from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException, Header, status

from .config import settings

RoleType = Literal["superadmin", "bar_owner"]


@dataclass
class Principal:
    sub: str
    email: str
    role: RoleType
    bar_id: str | None = None
    bar_name: str | None = None


def hash_password(password: str, salt: str | None = None) -> str:
    salt_hex = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
    )
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, salt_hex, expected_hex = stored_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, salt=salt_hex)
        return hmac.compare_digest(candidate, stored_hash)
    except Exception:
        return False


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def create_access_token(principal: Principal, ttl_seconds: int | None = None) -> str:
    now = int(time.time())
    exp = now + (ttl_seconds or settings.jwt_ttl_seconds)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": principal.sub,
        "email": principal.email,
        "role": principal.role,
        "bar_id": principal.bar_id,
        "bar_name": principal.bar_name,
        "iat": now,
        "exp": exp,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Principal:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
    h_b64, p_b64, sig_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    expected_sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura inválida.") from exc

    if not hmac.compare_digest(actual_sig, expected_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token não autorizado.")

    try:
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Payload de token corrompido.") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada. Faça login novamente.")

    role = payload.get("role")
    if role not in ("superadmin", "bar_owner"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Permissão desconhecida.")

    return Principal(
        sub=str(payload["sub"]),
        email=str(payload["email"]),
        role=role,
        bar_id=payload.get("bar_id"),
        bar_name=payload.get("bar_name"),
    )


def get_current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória. Faça login no painel.",
        )
    raw_token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(raw_token)


def require_superadmin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao Super-Admin da plataforma.",
        )
    return principal


def resolve_target_bar_id(
    principal: Principal = Depends(get_current_principal),
    x_bar_id: str | None = Header(default=None),
) -> str:
    """Permite ao dono do bar acessar apenas seu bar, e ao Super-Admin inspecionar qualquer bar via X-Bar-Id."""
    if principal.role == "bar_owner":
        if not principal.bar_id:
            raise HTTPException(status_code=403, detail="Conta sem bar vinculado.")
        return principal.bar_id
    if x_bar_id:
        return x_bar_id.strip()
    raise HTTPException(
        status_code=400,
        detail="Super-Admin deve informar o cabeçalho X-Bar-Id para gerenciar um bar específico.",
    )
