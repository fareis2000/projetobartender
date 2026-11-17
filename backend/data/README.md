# 🗄️ Camada de Dados, Segredos Locais & Multi-Tenancy (`backend/data/`)

Este diretório armazena os artefatos persistentes gerados automaticamente pelo **Bartender.OS v3.0** em tempo de execução. Por conter dados financeiros, hashes de credenciais e chaves criptográficas de sessão, seus arquivos binários/secretos **não são versionados no Git**.

---

## 📦 Arquivos Gerados Automaticamente nesta Pasta

| Arquivo | Criado em | Função Técnica e Segurança |
| :--- | :--- | :--- |
| `bartender_v3.db` *(+ `-wal` / `-shm`)* | `database.init_db()` | Banco relacional **SQLite 3** operando em modo **`WAL` (*Write-Ahead Logging*)** com `PRAGMA foreign_keys = ON`. Suporta leituras simultâneas de cardápio enquanto grava pagamentos Pix e batimentos IoT com atomicidade `ACID`. |
| `.jwt_secret` | `config._load_or_create_jwt_secret()` | Chave criptográfica URL-safe de `48 bytes` (`384 bits` de entropia) gerada via `secrets.token_urlsafe(48)` no primeiro boot caso `JWT_SECRET` não esteja definido no `.env`. Garante que os logins dos donos de bares sobrevivam a reinícios do servidor. |

> [!CAUTION]
> **Regra de Segurança em Produção:** Nunca compartilhe nem faça commit de `bartender_v3.db` ou `.jwt_secret`. A tabela `bars` armazena o `mp_access_token` de recebimento Pix de cada estabelecimento cliente, e `.jwt_secret` assina os tokens de autenticação da plataforma.

---

## 🏛️ Modelagem Relacional Multi-Tenant (ERD)

Todo o isolamento lógico entre bares concorrentes é garantido pela chave estrangeira obrigatória `bar_id` com integridade referencial em cascata (`ON DELETE CASCADE`):

```mermaid
erDiagram
    PLATFORM_ADMINS {
        text id PK
        text email UK
        text password_hash
        text created_at
    }

    BARS {
        text id PK
        text name
        text slug UK
        text owner_name
        text owner_email UK
        text password_hash
        integer active
        text payment_provider
        text mp_access_token
        text mp_webhook_secret
        real platform_fee_percent
        integer next_order_number
        text created_at
    }

    BOTTLES {
        text id PK
        text bar_id FK
        text name
        text color_hex
        integer is_alcoholic
        integer is_mixer
        real bottle_volume_ml
        integer cost_cents
        real loss_pct
        integer price_per_liter_cents
        text created_at
    }

    MACHINES {
        text id PK
        text bar_id FK
        text slug UK
        text name
        text api_token
        integer cup_fee_cents
        integer min_order_cents
        integer max_cup_ml
        integer allow_custom_builder
        text connection_mode
        text last_seen_at
        text last_ip
        integer last_rssi
    }

    MACHINE_PUMPS {
        text machine_id PK, FK
        text pump_id PK
        text label
        integer gpio
        text bottle_id FK
        real flow_rate_ml_s
        real remaining_ml
        real min_reserve_ml
    }

    DRINKS {
        text id PK
        text bar_id FK
        text name
        text category
        text pricing_mode
        integer fixed_price_cents
        real discount_pct
        integer active
        text steps_json
        integer sort_order
    }

    ORDERS {
        text id PK
        integer order_number
        text bar_id FK
        text machine_id FK
        text customer_session_id
        text drink_name
        real total_ml
        integer subtotal_cents
        integer cup_fee_cents
        integer total_cents
        integer cost_total_cents
        integer platform_fee_cents
        integer bar_net_cents
        text status
        text payment_provider
        text payment_external_id
        text pix_expires_at
        text turn_expires_at
        text paid_at
        text completed_at
    }

    BARS ||--o{ BOTTLES : "possui estoque (CASCADE)"
    BARS ||--o{ MACHINES : "opera máquinas (CASCADE)"
    BARS ||--o{ DRINKS : "publica cardápio (CASCADE)"
    BARS ||--o{ ORDERS : "fatura pedidos (CASCADE)"
    MACHINES ||--|{ MACHINE_PUMPS : "contém 4 bombas (CASCADE)"
    BOTTLES |o--o{ MACHINE_PUMPS : "abastece (SET NULL)"
    MACHINES ||--o{ ORDERS : "processa fila (CASCADE)"
```

### Índices de Alta Performance para Operação Noturna de Alto Giro:
1. `idx_orders_machine_status (machine_id, status)`: Acelera em `O(log N)` o cálculo da fila virtual, reserva de mililitros em trânsito e avanço de turnos a cada `2.5s`.
2. `idx_orders_bar_created (bar_id, created_at DESC)`: Garante carregamento instantâneo do histórico de vendas e DRE no painel `/painel`.
3. `idx_orders_session (machine_id, customer_session_id)`: Restaura imediatamente o pedido ativo quando o cliente retorna do aplicativo do banco para o navegador 4G.

---

## 💾 Como Fazer Backup Seguro (Zero Downtime)

Como o banco roda em modo **SQLite `WAL`**, durante a operação podem existir temporariamente os arquivos auxiliares `bartender_v3.db-wal` e `bartender_v3.db-shm`. Para gerar um arquivo único consistente de backup com o bar em pleno funcionamento, utilize a API nativa de backup online do próprio Python:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; src=sqlite3.connect('backend/data/bartender_v3.db'); dst=sqlite3.connect('backup_bartender_v3.db'); src.backup(dst); dst.close(); src.close(); print('Backup concluido com sucesso!')"
```

Para restaurar em outro servidor, basta copiar `backup_bartender_v3.db` para `backend/data/bartender_v3.db` (com o processo `server.py` parado) — todo o histórico multi-bares, receitas, garrafas e tokens IoT das placas ESP voltarão intactos!
