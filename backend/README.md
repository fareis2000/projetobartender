# ⚙️ Backend SaaS Multi-Tenant — Bartender.OS v3.0 (`backend/`)

Servidor assíncrono de alta confiabilidade construído em **Python + FastAPI + SQLite WAL**, projetado para operar dezenas de bares e máquinas de autosserviço simultaneamente a partir de uma única instância na nuvem (ou servidor local de evento) com **custo de infraestrutura próximo de zero**.

---

## 🎯 Diferenciais de Engenharia para Escala Comercial B2B

1. **Monólito Modular Unificado (Zero Complexidade de Deploy):**
   - Um único processo ASGI (`Uvicorn`) serve a API REST Multi-Tenant, os canais WebSocket em tempo real por máquina, os Webhooks do Mercado Pago, o endpoint de Cloud Sync IoT para placas `ESP8266`/`ESP32` e os arquivos estáticos compilados do React (`frontend/dist`).
   - Dispensa Redis, RabbitMQ ou clusters pesados para operar dezenas de estabelecimentos com latência sub-10ms.
2. **Segurança Financeira e Isolamento Multi-Tenant:**
   - **Cálculos 100% em Centavos Inteiros (`int`):** Elimina divergências de ponto flutuante entre o valor exibido no cardápio, o código Pix cobrado no banco e o relatório de lucro líquido do bar.
   - **Credenciais Bancárias por Estabelecimento:** Cada dono de bar cadastra seu próprio `Access Token` do Mercado Pago no painel; o dinheiro cai direto na conta do bar, eliminando risco regulatório de subadquirência para o operador do SaaS.
3. **Resiliência Dupla na Confirmação do Pix (Webhook + Polling Ativo):**
   - Em nuvem com domínio `https://` (`PUBLIC_BASE_URL`), o Mercado Pago notifica instantaneamente `/api/webhooks/mercadopago/{bar_id}`, que valida a transação diretamente na API oficial do banco antes de liberar o drink (imune a webhooks falsificados).
   - Caso o servidor esteja rodando em ambiente local/homologação sem HTTPS externo, o worker `_maintenance_loop` (a cada `2.5s`) **e** o gatilho de retorno do aplicativo bancário (`GET /api/public/orders/{id}`) consultam o status automaticamente — garantindo aprovação rápida em qualquer cenário de rede!

---

## 📂 Estrutura do Diretório `backend/`

```text
backend/
├── __init__.py          # Inicializador do pacote Python do servidor v3.0
├── .env.example         # Template documentado de variáveis de ambiente e portas
├── requirements.txt     # Dependências enxutas e auditadas (FastAPI, Uvicorn, HTTPX, PySerial, Segno, Pytest)
├── app/                 # Núcleo da aplicação (Auth, Models, Database, Payments, Runtime IoT, Main API)
├── data/                # Persistência transacional SQLite WAL (bartender_v3.db) e segredo .jwt_secret
└── tests/               # Suíte automatizada de testes de integração comercial E2E (pytest)
```

- Documentação interna das rotas e módulos: **[`app/README.md`](./app/README.md)**
- Documentação de banco de dados, backup e segredos: **[`data/README.md`](./data/README.md)**
- Documentação de qualidade e testes E2E: **[`tests/README.md`](./tests/README.md)**

---

## 🔧 Variáveis de Ambiente (`backend/.env`)

Copie `backend/.env.example` para `backend/.env` para personalizar sua instalação (em desenvolvimento ou demonstração local, **nenhuma configuração manual é obrigatória** — o sistema sobe pronto com padrões seguros):

| Variável | Padrão | Função Operacional e Comercial |
| :--- | :--- | :--- |
| `PORT` | `8010` | Porta TCP do servidor HTTP + WebSocket (isolada da porta `8000` da v2). |
| `PUBLIC_BASE_URL` | *(inferido do Host)* | Domínio público HTTPS de produção (ex.: `https://app.bartenderos.com.br`). Usado na geração de QR Codes SVG imprimíveis e URLs de Webhook do Mercado Pago. |
| `JWT_SECRET` | *(auto-gerado)* | Segredo `HMAC-SHA256` das sessões. Se omitido, gera e salva chave de 48 bytes em `backend/data/.jwt_secret`. |
| `JWT_TTL_SECONDS` | `604800` (7 dias) | Tempo de vida do token JWT dos painéis `/painel` e `/superadmin`. |
| `BARTENDER_DB_PATH` | `backend/data/bartender_v3.db` | Caminho do banco SQLite Multi-Tenant. |
| `SUPERADMIN_EMAIL` | `superadmin@bartender.os` | E-mail inicial do gestor da rede SaaS criado no primeiro boot. |
| `SUPERADMIN_PASSWORD` | `admin123` | Senha inicial do Super-Admin (troque imediatamente em produção!). |
| `DEFAULT_BAR_EMAIL` | `dono@bartropical.com` | E-mail do estabelecimento demonstrativo criado no primeiro boot. |
| `DEFAULT_BAR_PASSWORD` | `bar123` | Senha inicial do estabelecimento demonstrativo. |
| `PIX_EXPIRATION_SECONDS` | `300` (5 min) | Janela de validade para pagamento de cada QR Code Pix gerado. |
| `TURN_WINDOW_SECONDS` | `75` | Tempo máximo para o cliente da vez confirmar o copo na plataforma antes de pausar seu turno (`PAUSED_TURN`) e liberar a fila. |
| `ESP32_MODE` | `auto` | Transporte padrão da máquina demo (`cloud_iot`, `auto`, `wifi`, `serial`, `simulator`). |
| `MAX_CUP_ML` | `450` | Trava padrão de segurança volumétrica máxima por copo (`ml`). |

---

## 🚀 Execução, Documentação Interativa e Deploy em Produção

### 1. Subindo em Desenvolvimento / Demonstração Local
A partir da raiz `projetobartender-v3/`:

```powershell
.\.venv\Scripts\python.exe server.py
```

Acesse a documentação interativa OpenAPI/Swagger gerada automaticamente em:
- **Swagger UI:** `http://localhost:8010/docs`
- **ReDoc:** `http://localhost:8010/redoc`

### 2. Recomendações para Deploy Comercial em Nuvem (VPS / Cloud)
- Execute com **1 worker assíncrono Uvicorn** (`--workers 1`), pois o `MachineRuntimeManager` mantém em memória os eventos de sincronização sub-segundo (`asyncio.Event`) das placas ESP8266/ESP32 e as filas de broadcast WebSocket. Um único loop `asyncio` suporta milhares de conexões simultâneas com folga.
- Posicione atrás de um proxy reverso TLS como **Caddy** ou **Nginx** com HTTPS automático Let's Encrypt e defina `PUBLIC_BASE_URL=https://seu-dominio.com.br` no `backend/.env`.
- Certifique-se de habilitar suporte a `Upgrade: websocket` no proxy reverso para a rota `/api/ws/machines/*`.
