# 🖥️ Backend Python Assíncrono (`backend/`)

Servidor central de orquestração, segurança volumétrica, telemetria em tempo real e entrega web unificada do **Bartender.OS v2.0**.

---

## 💼 Argumentos de Vendas Técnicas & Operação em Eventos

1. **Arquitetura "Single-Box" sem Dependências Pesadas:**
   Diferente de soluções comerciais que exigem servidores em nuvem (mensalidades recorrentes de `R$ 200,00` a `R$ 800,00`), bancos de dados PostgreSQL ou containers Docker complexos, este backend roda nativamente em qualquer **Mini-PC Windows/Linux, Notebook ou Raspberry Pi** ao lado do bar, entregando **API REST + WebSocket + Interface React** em uma única porta (`8000`).
2. **Continuidade Absoluta de Negócio (Offline-First):**
   Em feiras, sítios de casamento ou praias onde a internet móvel falha, o servidor continua operando a `100%` na rede Wi-Fi local ou via cabo USB direto no ESP32.
3. **Baixíssimo Consumo de Hardware:**
   Construído sobre **FastAPI + Uvicorn (ASGI)**, consome menos de `70 MB` de RAM em operação contínua de 12 horas, suportando dezenas de celulares conectados simultaneamente acompanhando o preparo via WebSocket sem degradar a precisão das bombas.

---

## 📂 Estrutura desta Pasta

| Item | Tipo | Responsabilidade Técnica |
| :--- | :---: | :--- |
| **[`app/`](./app/README.md)** | Diretório | Código-fonte da API FastAPI, schemas Pydantic, catálogo de receitas e driver híbrido `ESP32Controller`. |
| **[`data/`](./data/README.md)** | Diretório | Armazenamento persistente em JSON plano (`connection.json` e `pumps.json`) para calibrações e preferências de rede. |
| **`__init__.py`** | Módulo | Marca `backend` como pacote Python importável pelo inicializador raiz `server.py`. |
| **`requirements.txt`** | Manifesto | Lista enxuta de 6 dependências industriais (`fastapi`, `uvicorn[standard]`, `httpx`, `pyserial`, `pydantic`, `python-dotenv`). |
| **`.env.example`** | Template | Modelo seguro de variáveis de ambiente para criação do arquivo privado `.env` na raiz do projeto. |

---

## 🔐 Configuração de Ambiente (`.env.example`)

Nunca grave credenciais reais em arquivos versionados. Para configurar uma nova instalação comercial, copie `backend/.env.example` para `projetobartender/.env`:

| Variável | Valor Padrão | Papel na Operação |
| :--- | :---: | :--- |
| `ESP32_MODE` | `auto` | Modo inicial de conexão (`auto`, `wifi`, `serial` ou `simulator`). |
| `ESP32_HOST` | `bartender.local` | Hostname mDNS ou IP fixo do ESP32 na rede local (`192.168.x.x` ou `192.168.4.1` em SoftAP). |
| `ESP32_PORT` | `80` | Porta HTTP do servidor web embarcado no ESP32. |
| `ESP32_API_TOKEN` | *(vazio)* | Segredo compartilhado enviado no header `X-Bartender-Token` (deve coincidir com `SECRET_API_TOKEN` em `bombas/secrets.h`). |
| `SERIAL_PORT` | `COM3` | Porta USB Serial usada automaticamente caso o Wi-Fi não esteja disponível. |
| `SERIAL_BAUD` | `115200` | Taxa de comunicação serial padrão do firmware ESP32/ESP8266. |
| `MAX_CUP_ML` | `450` | Limite físico máximo em mililitros por pedido para impedir transbordamento do copo. |

---

## 🚀 Como Executar e Validar

A partir da raiz `projetobartender/`:

```powershell
# Instalar dependências no ambiente virtual isolado
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.txt

# Iniciar servidor unificado (API + WebSocket + SPA na porta 8000)
.\.venv\Scripts\python server.py
```

- **Painel Principal:** `http://localhost:8000`
- **Swagger UI (Testes Técnicos & Integração com PDV/Fichas):** `http://localhost:8000/docs`
- **ReDoc (Especificação OpenAPI):** `http://localhost:8000/redoc`

> 💡 **Potencial de Integração B2B:** Graças à especificação OpenAPI 3.1 gerada automaticamente em `/docs`, sistemas externos de **comanda eletrônica, pagamento Pix/NFC ou leitura de QR Code** podem disparar drinks facilmente chamando `POST /api/dispense/{drink_id}`!
