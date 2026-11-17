"""Módulos da aplicação Bartender Automático.

Arquitetura Interna (`backend.app` — Bartender.OS v3.0):
--------------------------------------------------------
- `config.py`: Carregamento de variáveis `.env`, diretórios de dados e auto-geração de segredo JWT.
- `auth.py`: Segurança multi-tenant com hash de senhas `PBKDF2-HMAC-SHA256` (200.000 iterações),
  emissão/validação de tokens JWT `HS256` nativos e guardas de escopo (`superadmin` vs `bar_owner`).
- `models.py`: Contratos estritos Pydantic v2 para autenticação, multi-bares, garrafas (`R$/ml`),
  bombas com estoque vivo, receitas de drinks, fila de pedidos Pix, analytics e Cloud Sync IoT.
- `database.py`: Persistência transacional SQLite em modo `WAL` com lock reentrante, cálculo em
  centavos sem erro de ponto flutuante, reserva de estoque em trânsito e máquina de fila virtual.
- `payments.py`: Integração oficial com Mercado Pago Pix (`/v1/payments` + Split `application_fee`
  com fallback transparente + estornos `/refunds`) e gerador EMV BRCode `CRC16-CCITT` + QR SVG.
- `machine_runtime.py`: Orquestrador assíncrono de hardware por máquina (`Cloud IoT`, `Wi-Fi LAN`,
  `USB Serial` e `Simulador Volumétrico`), broadcast WebSocket e worker de conciliação/expiração.
- `main.py`: Aplicação FastAPI unificando todas as rotas REST, Webhook Pix, IoT Sync, WebSockets
  e entrega estática da SPA React compilada.
"""
