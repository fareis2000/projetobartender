"""Módulo de Autenticação, Criptografia de Senhas e Isolamento Multi-Tenant (JWT + RBAC).

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Implementa toda a camada de segurança e controle de acesso baseado em papéis (`RBAC`) da
plataforma SaaS Multi-Bares **sem dependências externas pesadas de criptografia**, usando
exclusivamente a biblioteca padrão auditada do Python (`hashlib`, `hmac`, `secrets`):

1. **Armazenamento Seguro de Credenciais (`PBKDF2-HMAC-SHA256`):**
   - Cada senha recebe um `salt` aleatório exclusivo de 128 bits (`16 bytes` hex) e passa
     por **200.000 iterações** de derivação `PBKDF2`, protegendo contas de bares e da
     plataforma contra ataques de força bruta ou *rainbow tables*.
2. **Tokens Stateless JWT (`HS256`):**
   - Implementação limpa do padrão RFC 7519 com assinatura `HMAC-SHA256` e comparação em
     tempo constante (`hmac.compare_digest`), imune a ataques de temporização (*timing attacks*).
3. **Isolamento Estrito de Dados por Tenant (`resolve_target_bar_id`):**
   - Garante que um dono de bar (`bar_owner`) acesse única e exclusivamente os dados do seu
     próprio `bar_id` embutido no token assinado, enquanto permite ao `superadmin` prestar
     suporte técnico a qualquer cliente da rede enviando o cabeçalho explícito `X-Bar-Id`.
"""
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

# Papéis de acesso suportados na plataforma SaaS:
# - "superadmin": Administrador global da rede/franquia Bartender.OS
# - "bar_owner": Operador/proprietário de um estabelecimento (tenant) específico
RoleType = Literal["superadmin", "bar_owner"]


@dataclass
class Principal:
    """Representa a identidade autenticada extraída e validada a partir do token JWT.

    Atributos:
        sub: Identificador único do sujeito no banco (`sa-root` ou `bar-...`).
        email: Endereço de e-mail autenticado do usuário.
        role: Papel de autorização (`superadmin` ou `bar_owner`).
        bar_id: ID do estabelecimento vinculado (obrigatório para `bar_owner`, `None` para `superadmin`).
        bar_name: Nome comercial do bar vinculado para exibição imediata na UI.
    """

    sub: str
    email: str
    role: RoleType
    bar_id: str | None = None
    bar_name: str | None = None


def hash_password(password: str, salt: str | None = None) -> str:
    """Gera o hash seguro de uma senha em texto puro usando PBKDF2-HMAC-SHA256.

    Formato persistido no banco: `pbkdf2_sha256$<salt_hex>$<derived_key_hex>`.
    Utiliza 200.000 iterações conforme recomendações modernas da OWASP.
    """
    salt_hex = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
    )
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Valida uma senha candidata contra o hash armazenado no SQLite em tempo constante.

    Previne vazamento de informação lateral (*timing attack*) por meio de `hmac.compare_digest`
    e captura qualquer malformação do hash retornando `False` com segurança.
    """
    try:
        algo, salt_hex, expected_hex = stored_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, salt=salt_hex)
        return hmac.compare_digest(candidate, stored_hash)
    except Exception:
        return False


def _b64url_encode(raw: bytes) -> str:
    """Codifica bytes em Base64 URL-Safe sem padding (`=`), conforme especificação JWT (RFC 7515)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Decodifica um segmento Base64 URL-Safe restaurando automaticamente o padding necessário."""
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def create_access_token(principal: Principal, ttl_seconds: int | None = None) -> str:
    """Emite um token JWT assinado via HMAC-SHA256 (`HS256`) contendo as claims do usuário.

    Inclui timestamps padrão `iat` (*Issued At*) e `exp` (*Expiration Time*), além do escopo
    de tenant (`bar_id`) para autorização stateless rápida em cada requisição da API.
    """
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
    # Serializa JSON compacto (sem espaços extras) antes da codificação Base64URL
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Principal:
    """Valida integridade criptográfica, expiração e papel de um token JWT recebido.

    Lança `HTTPException(401)` com mensagem amigável em português caso o formato seja inválido,
    a assinatura não corresponda ao `jwt_secret` do servidor ou o tempo de sessão tenha expirado.
    """
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

    # Comparação resistente a timing attacks entre assinatura recebida e esperada
    if not hmac.compare_digest(actual_sig, expected_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token não autorizado.")

    try:
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Payload de token corrompido.") from exc

    # Rejeita tokens cujo timestamp `exp` já venceu
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
    """Dependência FastAPI que extrai e valida o Bearer Token do cabeçalho HTTP `Authorization`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória. Faça login no painel.",
        )
    raw_token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(raw_token)


def require_superadmin(principal: Principal = Depends(get_current_principal)) -> Principal:
    """Guarda de autorização FastAPI exclusiva para rotas globais do Super-Admin (`/api/superadmin/*`)."""
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
    """Permite ao dono do bar acessar apenas seu bar, e ao Super-Admin inspecionar qualquer bar via X-Bar-Id.

    Regra Crítica de Segurança Multi-Tenant:
    - Se `role == 'bar_owner'`, o cabeçalho `X-Bar-Id` é **ignorado** e o `bar_id` retornado vem
      obrigatoriamente do payload JWT assinado, impedindo qualquer tentativa de escalonamento horizontal
      (*IDOR* entre bares concorrentes).
    - Se `role == 'superadmin'`, exige-se `X-Bar-Id` explícito para evitar alterações acidentais sem alvo.
    """
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
