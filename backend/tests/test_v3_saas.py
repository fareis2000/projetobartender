"""Suíte de Testes de Integração Ponta a Ponta (E2E) — Bartender.OS v3.0 SaaS.

Função Arquitetural e Garantia de Qualidade Comercial:
------------------------------------------------------
Valida de forma determinística e isolada (em banco SQLite temporário `tmp_path`) todo o
fluxo crítico de geração de receita, segurança de fila e multi-tenancy da plataforma:

1. **Autoatendimento Público & QR Code Vetorial (`/m/maq-01` + `qr.svg`):**
   - Garante que o seed inicial entrega 4 bombas calibradas, 4 drinks ativos e arte SVG válida.
2. **Autenticação JWT + CRUD Real de Garrafas (`R$/ml`) e Drinks:**
   - Comprova o cálculo automático de volume útil descontando perda (`loss_pct`), valor da dose
     de `50 ml`, exclusão real de receitas padrão e precificação dinâmica por mililitro + taxa de copo.
3. **Concorrência na Fila Pix + Trava Anti-Desperdício de Copo:**
   - Dois clientes (`Fábio` e `Maria`) compram simultaneamente; valida geração de código Pix EMV
     BRCode (`000201...`), ordenação justa (`READY_FOR_CUP` #1 vs `PAID_QUEUED` #2), bloqueio HTTP `400`
     sem confirmação de copo, bloqueio HTTP `409` contra tentativa de furar fila, abatimento exato de
     estoque em `ml` após dosagem e promoção automática do próximo cliente da fila!
4. **Onboarding Multi-Bares (`Super-Admin`) & Cloud Sync IoT (`ESP32`/`ESP8266`):**
   - Cria um segundo estabelecimento independente (`Quiosque Praia Clube`), autentica seu proprietário
     e valida o batimento de sincronização IoT autenticado via `X-Machine-Token`.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from fastapi.testclient import TestClient


def test_full_v3_commercial_workflow(tmp_path: Path):
    """Executa o fluxo comercial completo Multi-Bares + Pix + Fila Inteligente + Cloud IoT Sync."""
    # Redireciona o banco SQLite para um arquivo descartável exclusivo deste teste e força o simulador
    db_file = tmp_path / "test_v3.db"
    os.environ["BARTENDER_DB_PATH"] = str(db_file)
    os.environ["ESP32_MODE"] = "simulator"

    from backend.app.config import settings
    settings.db_path = db_file

    from backend.app.main import app

    with TestClient(app) as client:
        # 1. Verifica contexto público da máquina demo (/m/maq-01)
        ctx = client.get("/api/public/m/maq-01?session_id=sess-customer-1")
        assert ctx.status_code == 200
        data = ctx.json()
        assert data["machine_slug"] == "maq-01"
        assert len(data["pumps"]) == 4
        assert len(data["drinks"]) == 4

        # QR Code SVG imprimível
        qr_res = client.get("/api/public/m/maq-01/qr.svg")
        assert qr_res.status_code == 200
        assert "image/svg+xml" in qr_res.headers["content-type"]

        # 2. Login como Dono do Bar Tropical
        login_res = client.post(
            "/api/auth/login",
            json={"email": "dono@bartropical.com", "password": "bar123"},
        )
        assert login_res.status_code == 200
        bar_token = login_res.json()["access_token"]
        headers_bar = {"Authorization": f"Bearer {bar_token}"}

        # 3. CRUD Completo de Garrafas (precificação R$/ml)
        btl_res = client.post(
            "/api/bar/bottles",
            headers=headers_bar,
            json={
                "name": "Rum Bacardi Carta Blanca",
                "description": "Rum caribenho leve",
                "color_hex": "#eab308",
                "is_alcoholic": True,
                "is_mixer": False,
                "bottle_volume_ml": 1000,
                "cost_cents": 6000,
                "loss_pct": 5.0,
                "price_per_liter_cents": 20000,  # R$ 0,20/ml -> 50ml = R$ 10,00 (1000 cents)
            },
        )
        assert btl_res.status_code == 201
        rum = btl_res.json()
        assert rum["dose_50ml_cents"] == 1000
        assert rum["usable_volume_ml"] == 950.0

        # Atualiza garrafa
        upd_btl = client.put(
            f"/api/bar/bottles/{rum['id']}",
            headers=headers_bar,
            json={"price_per_liter_cents": 22000},
        )
        assert upd_btl.status_code == 200
        assert upd_btl.json()["dose_50ml_cents"] == 1100

        # Exclui garrafa
        del_btl = client.delete(f"/api/bar/bottles/{rum['id']}", headers=headers_bar)
        assert del_btl.status_code == 204

        # 4. CRUD Completo Real de Drinks (incluindo excluir drink existente!)
        drinks_before = client.get("/api/bar/drinks", headers=headers_bar).json()
        assert len(drinks_before) == 4
        victim_drink_id = drinks_before[-1]["id"]
        del_drk = client.delete(f"/api/bar/drinks/{victim_drink_id}", headers=headers_bar)
        assert del_drk.status_code == 204

        new_drk = client.post(
            "/api/bar/drinks",
            headers=headers_bar,
            json={
                "name": "Mojito Morango Express",
                "subtitle": "Morango, Maçã Verde & Soda",
                "description": "Drink autoral criado pelo dono do bar.",
                "category": "Autorais",
                "badge": "Novo",
                "accent_from": "#e11d48",
                "accent_to": "#10b981",
                "glass_color": "#f43f5e",
                "pricing_mode": "auto_ml",
                "fixed_price_cents": 1800,
                "discount_pct": 0.0,
                "active": True,
                "steps": [
                    {"pump": "vermelho", "ml": 50, "pause_ms": 500},
                    {"pump": "azul", "ml": 150, "pause_ms": 0},
                ],
            },
        )
        assert new_drk.status_code == 201
        created_drink = new_drk.json()
        # Preço esperado: 50ml * R$0,13 (650c) + 150ml * R$0,018 (270c) + taxa copo 150c = 1070 centavos (R$ 10,70)
        assert created_drink["final_price_cents"] == 1070

        # 5. Fila Virtual + Pix + Pergunta Obrigatória de Copo na Plataforma
        # Cliente A monta drink customizado por ml
        ord1_res = client.post(
            "/api/public/m/maq-01/orders/custom",
            json={
                "name": "Mix do Fábio",
                "customer_session_id": "sess-fabio-111",
                "customer_name": "Fábio",
                "amarelo": 50,  # 50 * 0,12 = 600c
                "vermelho": 0,
                "verde": 0,
                "azul": 100,  # 100 * 0,018 = 180c (+ 150c copo = 930c)
            },
        )
        assert ord1_res.status_code == 201
        ord1 = ord1_res.json()
        assert ord1["total_cents"] == 930
        assert ord1["status"] == "PENDING_PAYMENT"
        assert ord1["pix_qr_code"].startswith("000201")

        # Cliente B pede drink pronto ao mesmo tempo
        ord2_res = client.post(
            "/api/public/m/maq-01/orders/preset",
            json={
                "drink_id": created_drink["id"],
                "customer_session_id": "sess-maria-222",
                "customer_name": "Maria",
            },
        )
        assert ord2_res.status_code == 201
        ord2 = ord2_res.json()

        # Cliente A e Cliente B pagam o Pix
        pay1 = client.post(f"/api/public/orders/{ord1['id']}/simulate-pay").json()
        pay2 = client.post(f"/api/public/orders/{ord2['id']}/simulate-pay").json()

        # Cliente A chegou primeiro -> READY_FOR_CUP (posição 1); Cliente B aguarda na fila -> PAID_QUEUED (posição 2)!
        assert pay1["status"] == "READY_FOR_CUP"
        assert pay1["queue_position"] == 1
        assert pay2["status"] == "PAID_QUEUED"
        assert pay2["queue_position"] == 2

        # Tentar servir SEM confirmar copo na plataforma deve falhar (400)
        bad_cup = client.post(
            f"/api/public/orders/{ord1['id']}/confirm-cup-and-dispense",
            json={"customer_session_id": "sess-fabio-111", "cup_on_platform_confirmed": False},
        )
        assert bad_cup.status_code == 400

        # Cliente B tentando furar a fila antes do Cliente A deve ser bloqueado (409)
        skip_line = client.post(
            f"/api/public/orders/{ord2['id']}/confirm-cup-and-dispense",
            json={"customer_session_id": "sess-maria-222", "cup_on_platform_confirmed": True},
        )
        assert skip_line.status_code == 409

        # Cliente A confirma que o copo está na plataforma -> bombas iniciam!
        good_cup = client.post(
            f"/api/public/orders/{ord1['id']}/confirm-cup-and-dispense",
            json={"customer_session_id": "sess-fabio-111", "cup_on_platform_confirmed": True},
        )
        assert good_cup.status_code == 200
        assert good_cup.json()["status"] == "DISPENSING"

        # Aguarda simulador rápido concluir (~5s para 150ml a ~32ml/s)
        deadline = time.time() + 12.0
        while time.time() < deadline:
            chk1 = client.get(f"/api/public/orders/{ord1['id']}").json()
            if chk1["status"] == "COMPLETED":
                break
            time.sleep(0.3)

        chk1 = client.get(f"/api/public/orders/{ord1['id']}").json()
        assert chk1["status"] == "COMPLETED"

        # Verifica desconto de ml na garrafa da Bomba Amarela (750 -> 700ml) e promoção automática de Maria p/ READY_FOR_CUP!
        ctx_after = client.get("/api/public/m/maq-01").json()
        amarelo_slot = next(p for p in ctx_after["pumps"] if p["pump_id"] == "amarelo")
        assert amarelo_slot["remaining_ml"] == 700.0

        chk2 = client.get(f"/api/public/orders/{ord2['id']}").json()
        assert chk2["status"] == "READY_FOR_CUP"
        assert chk2["queue_position"] == 1

        # 6. Super-Admin Multi-Bares: cria um segundo bar cliente!
        sa_login = client.post(
            "/api/auth/login",
            json={"email": "superadmin@bartender.os", "password": "admin123"},
        )
        assert sa_login.status_code == 200
        sa_headers = {"Authorization": f"Bearer {sa_login.json()['access_token']}"}

        new_bar = client.post(
            "/api/superadmin/bars",
            headers=sa_headers,
            json={
                "name": "Quiosque Praia Clube",
                "slug": "quiosque-praia",
                "owner_name": "Carlos",
                "owner_email": "carlos@praiaclube.com",
                "owner_password": "praia123",
                "platform_fee_percent": 6.0,
                "initial_machine_name": "Máquina Deck Piscina",
                "initial_machine_slug": "maq-piscina-01",
            },
        )
        assert new_bar.status_code == 201
        assert new_bar.json()["machines_count"] == 1

        # Verifica IoT Sync da nova máquina usando o token dela
        carlos_login = client.post(
            "/api/auth/login",
            json={"email": "carlos@praiaclube.com", "password": "praia123"},
        ).json()
        carlos_machines = client.get(
            "/api/bar/machines",
            headers={"Authorization": f"Bearer {carlos_login['access_token']}"},
        ).json()
        iot_token = carlos_machines[0]["api_token"]

        iot_sync = client.post(
            "/api/iot/maq-piscina-01/sync",
            headers={"X-Machine-Token": iot_token},
            json={"state": "idle", "progress": 0, "ip": "192.168.15.42", "rssi": -54, "device": "ESP32"},
        )
        assert iot_sync.status_code == 200
        assert iot_sync.json()["command"] == "none"

        # 7. Proteção contra colagem acidental de URL ou Public Key no Access Token Mercado Pago
        bad_url_tok = client.put(
            "/api/bar/settings",
            headers=headers_bar,
            json={"payment_provider": "mercadopago", "mp_access_token": "http://localhost:8010/painel"},
        )
        assert bad_url_tok.status_code == 400
        assert "URL" in bad_url_tok.json()["detail"]

        bad_pubkey = client.put(
            "/api/bar/settings",
            headers=headers_bar,
            json={
                "payment_provider": "mercadopago",
                "mp_access_token": "APP_USR-12345678-1234-1234-1234-1234567890ab",
            },
        )
        assert bad_pubkey.status_code == 400
        assert "Public Key" in bad_pubkey.json()["detail"]

        valid_bearer_prefixed = client.put(
            "/api/bar/settings",
            headers=headers_bar,
            json={
                "payment_provider": "mercadopago",
                "mp_access_token": "Bearer APP_USR-5819283746192837-110521-abcdef0123456789abcdef0123456789-998877665",
            },
        )
        assert valid_bearer_prefixed.status_code == 200
        assert valid_bearer_prefixed.json()["mp_token_masked"].startswith("APP_USR-")
