from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from .auth import hash_password, verify_password, Principal
from .config import settings
from .models import (
    BarAnalyticsOut,
    BarCreateRequest,
    BarSettingsOut,
    BarSettingsUpdateRequest,
    BarSummaryOut,
    BarSuperAdminUpdateRequest,
    BottleCreateRequest,
    BottleOut,
    BottleUpdateRequest,
    DoseStep,
    DrinkCreateRequest,
    DrinkOut,
    DrinkUpdateRequest,
    MachineCreateRequest,
    MachineUpdateRequest,
    OrderItemBreakdown,
    OrderOut,
    PUMP_IDS_ORDERED,
    PlatformOverviewOut,
    PublicMachineSummary,
    PumpId,
    PumpSlotOut,
    PumpSlotUpdateRequest,
)

_DB_LOCK = threading.RLock()

DEFAULT_PUMP_META: dict[PumpId, tuple[str, int, float]] = {
    "amarelo": ("Bomba 1 · Amarela", 16, 30.5),
    "vermelho": ("Bomba 2 · Vermelha", 17, 32.3),
    "verde": ("Bomba 3 · Verde", 18, 32.3),
    "azul": ("Bomba 4 · Azul (Base)", 19, 35.9),
}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def _parse_iso(val: str | None) -> dt.datetime | None:
    if not val:
        return None
    try:
        parsed = dt.datetime.fromisoformat(val)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = db_path or settings.db_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK:
        conn = sqlite3.connect(str(target), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db(db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS platform_admins (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bars (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                owner_name TEXT NOT NULL,
                owner_email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                payment_provider TEXT NOT NULL DEFAULT 'simulated',
                mp_access_token TEXT NOT NULL DEFAULT '',
                mp_webhook_secret TEXT NOT NULL DEFAULT '',
                platform_fee_percent REAL NOT NULL DEFAULT 0.0,
                next_order_number INTEGER NOT NULL DEFAULT 101,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bottles (
                id TEXT PRIMARY KEY,
                bar_id TEXT NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                color_hex TEXT NOT NULL DEFAULT '#f97316',
                is_alcoholic INTEGER NOT NULL DEFAULT 0,
                is_mixer INTEGER NOT NULL DEFAULT 0,
                bottle_volume_ml REAL NOT NULL DEFAULT 1000.0,
                cost_cents INTEGER NOT NULL DEFAULT 0,
                loss_pct REAL NOT NULL DEFAULT 3.0,
                price_per_liter_cents INTEGER NOT NULL DEFAULT 10000,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS machines (
                id TEXT PRIMARY KEY,
                bar_id TEXT NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                api_token TEXT NOT NULL,
                cup_fee_cents INTEGER NOT NULL DEFAULT 0,
                min_order_cents INTEGER NOT NULL DEFAULT 300,
                max_cup_ml INTEGER NOT NULL DEFAULT 450,
                allow_custom_builder INTEGER NOT NULL DEFAULT 1,
                connection_mode TEXT NOT NULL DEFAULT 'auto',
                esp32_host TEXT NOT NULL DEFAULT 'bartender.local',
                esp32_port INTEGER NOT NULL DEFAULT 80,
                serial_port TEXT NOT NULL DEFAULT 'COM3',
                serial_baud INTEGER NOT NULL DEFAULT 115200,
                last_seen_at TEXT,
                last_ip TEXT,
                last_rssi INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS machine_pumps (
                machine_id TEXT NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
                pump_id TEXT NOT NULL,
                label TEXT NOT NULL,
                gpio INTEGER NOT NULL,
                bottle_id TEXT REFERENCES bottles(id) ON DELETE SET NULL,
                flow_rate_ml_s REAL NOT NULL DEFAULT 32.0,
                remaining_ml REAL NOT NULL DEFAULT 1000.0,
                min_reserve_ml REAL NOT NULL DEFAULT 25.0,
                PRIMARY KEY (machine_id, pump_id)
            );

            CREATE TABLE IF NOT EXISTS drinks (
                id TEXT PRIMARY KEY,
                bar_id TEXT NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                subtitle TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Clássicos da Casa',
                badge TEXT NOT NULL DEFAULT 'Especial',
                accent_from TEXT NOT NULL DEFAULT '#ea580c',
                accent_to TEXT NOT NULL DEFAULT '#f97316',
                glass_color TEXT NOT NULL DEFAULT '#f97316',
                pricing_mode TEXT NOT NULL DEFAULT 'auto_ml',
                fixed_price_cents INTEGER NOT NULL DEFAULT 1500,
                discount_pct REAL NOT NULL DEFAULT 0.0,
                active INTEGER NOT NULL DEFAULT 1,
                steps_json TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                order_number INTEGER NOT NULL,
                bar_id TEXT NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
                machine_id TEXT NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
                customer_session_id TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                drink_id TEXT,
                drink_name TEXT NOT NULL,
                is_custom INTEGER NOT NULL DEFAULT 0,
                is_alcoholic INTEGER NOT NULL DEFAULT 0,
                steps_json TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total_ml REAL NOT NULL,
                subtotal_cents INTEGER NOT NULL,
                cup_fee_cents INTEGER NOT NULL,
                total_cents INTEGER NOT NULL,
                cost_total_cents INTEGER NOT NULL DEFAULT 0,
                platform_fee_cents INTEGER NOT NULL DEFAULT 0,
                bar_net_cents INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                cup_confirmed_at TEXT,
                payment_provider TEXT NOT NULL,
                payment_external_id TEXT,
                pix_qr_code TEXT NOT NULL DEFAULT '',
                pix_qr_base64 TEXT NOT NULL DEFAULT '',
                pix_expires_at TEXT,
                turn_expires_at TEXT,
                paid_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_orders_machine_status ON orders(machine_id, status);
            CREATE INDEX IF NOT EXISTS idx_orders_bar_created ON orders(bar_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(machine_id, customer_session_id);
            """
        )

        # Seed Super-Admin se não existir
        sa_count = conn.execute("SELECT COUNT(*) FROM platform_admins").fetchone()[0]
        if sa_count == 0:
            conn.execute(
                "INSERT INTO platform_admins (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (
                    "sa-root",
                    settings.superadmin_email,
                    hash_password(settings.superadmin_password),
                    utcnow_iso(),
                ),
            )

        # Seed Bar Inicial de Demonstração se não houver nenhum bar
        bar_count = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        if bar_count == 0:
            _seed_demo_bar(conn)


def _seed_demo_bar(conn: sqlite3.Connection) -> None:
    now = utcnow_iso()
    bar_id = "bar-tropical"
    conn.execute(
        """
        INSERT INTO bars (
            id, name, slug, owner_name, owner_email, password_hash,
            active, payment_provider, mp_access_token, platform_fee_percent, next_order_number, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 'simulated', '', 5.0, 101, ?)
        """,
        (
            bar_id,
            "Bar Tropical Demo",
            "bar-tropical",
            "Dono Bar Tropical",
            settings.default_bar_email,
            hash_password(settings.default_bar_password),
            now,
        ),
    )

    # Garrafas padrão precificadas por garrafa (dono pode editar/excluir à vontade!)
    demo_bottles = [
        (
            "btl-citrus",
            "Xarope Citrus & Maracujá",
            "Xarope cítrico artesanal de limão siciliano e maracujá",
            "#f59e0b",
            0,
            0,
            750.0,
            4500,  # R$ 45,00 de custo
            3.0,
            12000,  # R$ 120,00/L = R$ 0,12/ml (50ml = R$ 6,00)
        ),
        (
            "btl-morango",
            "Xarope Morango & Hibisco",
            "Redução intensa de morango silvestre e frutas vermelhas",
            "#ef4444",
            0,
            0,
            750.0,
            4800,  # R$ 48,00 de custo
            3.0,
            13000,  # R$ 130,00/L = R$ 0,13/ml (50ml = R$ 6,50)
        ),
        (
            "btl-maca",
            "Xarope Maçã Verde & Menta",
            "Xarope botânico refrescante de maçã verde com hortelã",
            "#10b981",
            0,
            0,
            750.0,
            4800,
            3.0,
            13000,  # R$ 0,13/ml
        ),
        (
            "btl-soda",
            "Água com Gás Cristal",
            "Base gaseificada super gelada para completar o copo",
            "#0ea5e9",
            0,
            1,
            2000.0,
            800,  # R$ 8,00 por 2L
            2.0,
            1800,  # R$ 18,00/L = R$ 0,018/ml (200ml = R$ 3,60)
        ),
        (
            "btl-gin",
            "Gin Tanqueray London Dry",
            "Destilado botânico premium (disponível no estoque p/ troca de bomba)",
            "#6366f1",
            1,
            0,
            750.0,
            9500,  # R$ 95,00 de custo
            4.0,
            30000,  # R$ 300,00/L = R$ 0,30/ml (50ml = R$ 15,00)
        ),
        (
            "btl-vodka",
            "Vodka Absolut Original",
            "Vodka sueca pura (disponível no estoque p/ drinks alcoólicos)",
            "#8b5cf6",
            1,
            0,
            1000.0,
            8500,  # R$ 85,00 de custo
            3.0,
            24000,  # R$ 240,00/L = R$ 0,24/ml (50ml = R$ 12,00)
        ),
    ]

    for b_id, name, desc, color, is_alc, is_mix, vol, cost, loss, ppl in demo_bottles:
        conn.execute(
            """
            INSERT INTO bottles (
                id, bar_id, name, description, color_hex, is_alcoholic, is_mixer,
                bottle_volume_ml, cost_cents, loss_pct, price_per_liter_cents, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (b_id, bar_id, name, desc, color, is_alc, is_mix, vol, cost, loss, ppl, now),
        )

    # Máquina #01 (QR Code: /m/maq-01)
    machine_id = "mach-01"
    conn.execute(
        """
        INSERT INTO machines (
            id, bar_id, slug, name, api_token, cup_fee_cents, min_order_cents,
            max_cup_ml, allow_custom_builder, connection_mode, esp32_host, esp32_port,
            serial_port, serial_baud, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            machine_id,
            bar_id,
            "maq-01",
            "Máquina #01 · Balcão Principal",
            settings.esp32_api_token or f"iot_{secrets.token_urlsafe(18)}",
            150,  # R$ 1,50 taxa de copo/gelo (configurável pelo dono!)
            500,  # R$ 5,00 mínimo
            settings.max_cup_ml,
            settings.esp32_mode if settings.esp32_mode in ("cloud_iot", "auto", "wifi", "serial", "simulator") else "auto",
            settings.esp32_host,
            settings.esp32_port,
            settings.serial_port,
            settings.serial_baud,
            now,
        ),
    )

    pump_bottle_map: dict[PumpId, tuple[str, float]] = {
        "amarelo": ("btl-citrus", 750.0),
        "vermelho": ("btl-morango", 750.0),
        "verde": ("btl-maca", 750.0),
        "azul": ("btl-soda", 2000.0),
    }
    for pid in PUMP_IDS_ORDERED:
        label, gpio, flow = DEFAULT_PUMP_META[pid]
        btl_id, init_ml = pump_bottle_map[pid]
        conn.execute(
            """
            INSERT INTO machine_pumps (
                machine_id, pump_id, label, gpio, bottle_id, flow_rate_ml_s, remaining_ml, min_reserve_ml
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 25.0)
            """,
            (machine_id, pid, label, gpio, btl_id, flow, init_ml),
        )

    # Drinks iniciais salvos no banco (100% editáveis e excluíveis no CRUD!)
    seed_drinks = [
        (
            "drk-red",
            "Red Robotics",
            "Soda Italiana de Morango & Hibisco",
            "Camada vibrante de morango silvestre completada com água gaseificada bem gelada.",
            "Clássicos da Casa",
            "Mais Pedido",
            "#e11d48",
            "#f97316",
            "#f43f5e",
            "auto_ml",
            1490,
            0.0,
            [{"pump": "vermelho", "ml": 70, "pause_ms": 1500}, {"pump": "azul", "ml": 220, "pause_ms": 0}],
        ),
        (
            "drk-yellow",
            "Yellow Web",
            "Limonada Tropical & Maracujá",
            "Leve, solar e cítrico na medida certa para refrescar a noite.",
            "Clássicos da Casa",
            "Cítrico Solar",
            "#ea580c",
            "#eab308",
            "#f59e0b",
            "auto_ml",
            1590,
            0.0,
            [{"pump": "amarelo", "ml": 90, "pause_ms": 1500}, {"pump": "azul", "ml": 240, "pause_ms": 0}],
        ),
        (
            "drk-green",
            "Green Games",
            "Refresco Botânico de Maçã Verde",
            "Frescor de maçã verde com toque herbal de hortelã e borbulhas.",
            "Clássicos da Casa",
            "Botânico",
            "#059669",
            "#14b8a6",
            "#10b981",
            "auto_ml",
            1590,
            0.0,
            [{"pump": "verde", "ml": 90, "pause_ms": 1500}, {"pump": "azul", "ml": 240, "pause_ms": 0}],
        ),
        (
            "drk-sunset",
            "Pôr do Sol Tropical",
            "Duo de Maracujá & Frutas Vermelhas",
            "Camadas douradas e avermelhadas em equilíbrio perfeito com soda.",
            "Especiais Tropicais",
            "Assinatura da Casa",
            "#ea580c",
            "#e11d48",
            "#fb7185",
            "auto_ml",
            1790,
            5.0,  # 5% desconto combo da casa!
            [
                {"pump": "amarelo", "ml": 50, "pause_ms": 1200},
                {"pump": "vermelho", "ml": 50, "pause_ms": 1200},
                {"pump": "azul", "ml": 240, "pause_ms": 0},
            ],
        ),
    ]
    for idx, (d_id, name, sub, desc, cat, badge, af, at, gc, pmode, fixed_c, disc, steps) in enumerate(seed_drinks):
        conn.execute(
            """
            INSERT INTO drinks (
                id, bar_id, name, subtitle, description, category, badge,
                accent_from, accent_to, glass_color, pricing_mode, fixed_price_cents,
                discount_pct, active, steps_json, sort_order, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (d_id, bar_id, name, sub, desc, cat, badge, af, at, gc, pmode, fixed_c, disc, json.dumps(steps), idx, now),
        )


# ======================== AUTHENTICATION QUERIES ========================

def authenticate_user(email: str, password: str) -> Principal:
    clean_email = email.strip().lower()
    with get_conn() as conn:
        sa = conn.execute("SELECT * FROM platform_admins WHERE lower(email) = ?", (clean_email,)).fetchone()
        if sa and verify_password(password, sa["password_hash"]):
            return Principal(sub=sa["id"], email=sa["email"], role="superadmin")

        bar = conn.execute("SELECT * FROM bars WHERE lower(owner_email) = ?", (clean_email,)).fetchone()
        if bar and verify_password(password, bar["password_hash"]):
            if not bar["active"]:
                raise HTTPException(status_code=403, detail="Esta conta de bar está temporariamente suspensa.")
            return Principal(
                sub=bar["id"],
                email=bar["owner_email"],
                role="bar_owner",
                bar_id=bar["id"],
                bar_name=bar["name"],
            )

    raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")


# ======================== SUPERADMIN MULTI-BAR CRUD ========================

def get_platform_overview() -> PlatformOverviewOut:
    with get_conn() as conn:
        bars_rows = conn.execute("SELECT * FROM bars ORDER BY created_at DESC").fetchall()
        summaries: list[BarSummaryOut] = []
        tot_machines = 0
        tot_orders = 0
        tot_gross = 0
        tot_fees = 0

        for b in bars_rows:
            m_cnt = conn.execute("SELECT COUNT(*) FROM machines WHERE bar_id = ?", (b["id"],)).fetchone()[0]
            ord_agg = conn.execute(
                """
                SELECT COUNT(*) AS cnt,
                       COALESCE(SUM(total_cents), 0) AS gross,
                       COALESCE(SUM(platform_fee_cents), 0) AS fees
                FROM orders
                WHERE bar_id = ? AND status IN ('PAID_QUEUED', 'READY_FOR_CUP', 'PAUSED_TURN', 'DISPENSING', 'COMPLETED')
                """,
                (b["id"],),
            ).fetchone()
            p_cnt = int(ord_agg["cnt"])
            gross = int(ord_agg["gross"])
            fees = int(ord_agg["fees"])
            tot_machines += m_cnt
            tot_orders += p_cnt
            tot_gross += gross
            tot_fees += fees

            summaries.append(
                BarSummaryOut(
                    id=b["id"],
                    name=b["name"],
                    slug=b["slug"],
                    owner_name=b["owner_name"],
                    owner_email=b["owner_email"],
                    active=bool(b["active"]),
                    payment_provider=b["payment_provider"],
                    has_mp_token=bool(b["mp_access_token"].strip()),
                    platform_fee_percent=float(b["platform_fee_percent"]),
                    machines_count=m_cnt,
                    paid_orders_count=p_cnt,
                    gross_revenue_cents=gross,
                    platform_fees_cents=fees,
                    created_at=b["created_at"],
                )
            )

        return PlatformOverviewOut(
            total_bars=len(summaries),
            active_bars=sum(1 for s in summaries if s.active),
            total_machines=tot_machines,
            total_paid_orders=tot_orders,
            total_gross_cents=tot_gross,
            total_platform_fees_cents=tot_fees,
            bars=summaries,
        )


def create_bar_tenant(req: BarCreateRequest) -> BarSummaryOut:
    now = utcnow_iso()
    bar_id = f"bar-{uuid.uuid4().hex[:10]}"
    machine_id = f"mach-{uuid.uuid4().hex[:10]}"
    clean_email = req.owner_email.strip().lower()

    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM bars WHERE slug = ?", (req.slug,)).fetchone():
            raise HTTPException(status_code=409, detail=f"O identificador de bar '{req.slug}' já está em uso.")
        if conn.execute("SELECT 1 FROM bars WHERE lower(owner_email) = ?", (clean_email,)).fetchone():
            raise HTTPException(status_code=409, detail=f"O e-mail '{clean_email}' já está cadastrado.")
        if conn.execute("SELECT 1 FROM machines WHERE slug = ?", (req.initial_machine_slug,)).fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"O código de QR Code '{req.initial_machine_slug}' já pertence a outra máquina.",
            )

        conn.execute(
            """
            INSERT INTO bars (
                id, name, slug, owner_name, owner_email, password_hash,
                active, payment_provider, mp_access_token, platform_fee_percent, next_order_number, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 'simulated', '', ?, 101, ?)
            """,
            (
                bar_id,
                req.name.strip(),
                req.slug.strip(),
                req.owner_name.strip(),
                clean_email,
                hash_password(req.owner_password),
                req.platform_fee_percent,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO machines (
                id, bar_id, slug, name, api_token, cup_fee_cents, min_order_cents,
                max_cup_ml, allow_custom_builder, connection_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, 500, 450, 1, 'cloud_iot', ?)
            """,
            (
                machine_id,
                bar_id,
                req.initial_machine_slug.strip(),
                req.initial_machine_name.strip(),
                f"iot_{secrets.token_urlsafe(18)}",
                now,
            ),
        )

        for pid in PUMP_IDS_ORDERED:
            label, gpio, flow = DEFAULT_PUMP_META[pid]
            conn.execute(
                """
                INSERT INTO machine_pumps (
                    machine_id, pump_id, label, gpio, bottle_id, flow_rate_ml_s, remaining_ml, min_reserve_ml
                ) VALUES (?, ?, ?, ?, NULL, ?, 0.0, 25.0)
                """,
                (machine_id, pid, label, gpio, flow),
            )

    overview = get_platform_overview()
    for item in overview.bars:
        if item.id == bar_id:
            return item
    raise RuntimeError("Erro ao recuperar bar recém-criado.")


def update_bar_superadmin(bar_id: str, req: BarSuperAdminUpdateRequest) -> BarSummaryOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bars WHERE id = ?", (bar_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bar não encontrado.")

        new_email = req.owner_email.strip().lower() if req.owner_email else row["owner_email"]
        if new_email != row["owner_email"]:
            if conn.execute("SELECT 1 FROM bars WHERE lower(owner_email) = ? AND id != ?", (new_email, bar_id)).fetchone():
                raise HTTPException(status_code=409, detail="E-mail já utilizado por outro bar.")

        pw_hash = hash_password(req.owner_password) if req.owner_password else row["password_hash"]
        conn.execute(
            """
            UPDATE bars
            SET name = ?, owner_name = ?, owner_email = ?, password_hash = ?, active = ?, platform_fee_percent = ?
            WHERE id = ?
            """,
            (
                req.name.strip() if req.name is not None else row["name"],
                req.owner_name.strip() if req.owner_name is not None else row["owner_name"],
                new_email,
                pw_hash,
                int(req.active) if req.active is not None else row["active"],
                req.platform_fee_percent if req.platform_fee_percent is not None else row["platform_fee_percent"],
                bar_id,
            ),
        )

    overview = get_platform_overview()
    for item in overview.bars:
        if item.id == bar_id:
            return item
    raise HTTPException(status_code=404, detail="Bar não encontrado.")


def delete_bar_tenant(bar_id: str) -> None:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM bars WHERE id = ?", (bar_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Bar não encontrado.")


# ======================== BAR SETTINGS ========================

def _mask_token(tok: str) -> str:
    clean = tok.strip()
    if not clean:
        return ""
    if len(clean) <= 10:
        return "****"
    return f"{clean[:8]}••••••••{clean[-4:]}"


def get_bar_settings(bar_id: str, base_url_fallback: str = "") -> BarSettingsOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bars WHERE id = ?", (bar_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bar não encontrado.")
        tok = str(row["mp_access_token"] or "")
        return BarSettingsOut(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            owner_name=row["owner_name"],
            owner_email=row["owner_email"],
            payment_provider=row["payment_provider"],
            has_mp_token=bool(tok.strip()),
            mp_token_masked=_mask_token(tok),
            mp_webhook_secret_configured=bool(str(row["mp_webhook_secret"] or "").strip()),
            platform_fee_percent=float(row["platform_fee_percent"]),
            public_base_url=settings.public_base_url or base_url_fallback,
        )


def update_bar_settings(bar_id: str, req: BarSettingsUpdateRequest, base_url_fallback: str = "") -> BarSettingsOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bars WHERE id = ?", (bar_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bar não encontrado.")

        mp_tok = req.mp_access_token.strip() if req.mp_access_token is not None else row["mp_access_token"]
        wh_sec = req.mp_webhook_secret.strip() if req.mp_webhook_secret is not None else row["mp_webhook_secret"]
        pw_hash = hash_password(req.new_password) if req.new_password else row["password_hash"]
        provider = req.payment_provider if req.payment_provider is not None else row["payment_provider"]

        if provider == "mercadopago" and not mp_tok:
            raise HTTPException(
                status_code=400,
                detail="Informe o Access Token do Mercado Pago antes de ativar o modo Mercado Pago Real.",
            )

        conn.execute(
            """
            UPDATE bars
            SET name = ?, owner_name = ?, payment_provider = ?, mp_access_token = ?, mp_webhook_secret = ?, password_hash = ?
            WHERE id = ?
            """,
            (
                req.name.strip() if req.name is not None else row["name"],
                req.owner_name.strip() if req.owner_name is not None else row["owner_name"],
                provider,
                mp_tok,
                wh_sec,
                pw_hash,
                bar_id,
            ),
        )
    return get_bar_settings(bar_id, base_url_fallback)


# ======================== BOTTLES CRUD ========================

def _row_to_bottle_out(row: sqlite3.Row, installed_count: int = 0) -> BottleOut:
    vol = float(row["bottle_volume_ml"])
    loss = float(row["loss_pct"])
    usable = round(vol * (1.0 - loss / 100.0), 1)
    ppl = int(row["price_per_liter_cents"])
    cost = int(row["cost_cents"])
    est_rev = int(round(usable * ppl / 1000.0))
    return BottleOut(
        id=row["id"],
        bar_id=row["bar_id"],
        name=row["name"],
        description=row["description"],
        color_hex=row["color_hex"],
        is_alcoholic=bool(row["is_alcoholic"]),
        is_mixer=bool(row["is_mixer"]),
        bottle_volume_ml=vol,
        usable_volume_ml=usable,
        cost_cents=cost,
        loss_pct=loss,
        price_per_liter_cents=ppl,
        price_per_ml_cents_float=round(ppl / 1000.0, 4),
        dose_50ml_cents=int(round(50.0 * ppl / 1000.0)),
        estimated_bottle_revenue_cents=est_rev,
        estimated_bottle_profit_cents=est_rev - cost,
        installed_in_pumps=installed_count,
        created_at=row["created_at"],
    )


def list_bottles(bar_id: str) -> list[BottleOut]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bottles WHERE bar_id = ? ORDER BY is_mixer ASC, name ASC",
            (bar_id,),
        ).fetchall()
        out: list[BottleOut] = []
        for r in rows:
            cnt = conn.execute(
                """
                SELECT COUNT(*) FROM machine_pumps mp
                JOIN machines m ON m.id = mp.machine_id
                WHERE m.bar_id = ? AND mp.bottle_id = ?
                """,
                (bar_id, r["id"]),
            ).fetchone()[0]
            out.append(_row_to_bottle_out(r, int(cnt)))
        return out


def create_bottle(bar_id: str, req: BottleCreateRequest) -> BottleOut:
    btl_id = f"btl-{uuid.uuid4().hex[:10]}"
    now = utcnow_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO bottles (
                id, bar_id, name, description, color_hex, is_alcoholic, is_mixer,
                bottle_volume_ml, cost_cents, loss_pct, price_per_liter_cents, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                btl_id,
                bar_id,
                req.name.strip(),
                req.description.strip(),
                req.color_hex,
                int(req.is_alcoholic),
                int(req.is_mixer),
                req.bottle_volume_ml,
                req.cost_cents,
                req.loss_pct,
                req.price_per_liter_cents,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM bottles WHERE id = ?", (btl_id,)).fetchone()
        return _row_to_bottle_out(row, 0)


def update_bottle(bar_id: str, bottle_id: str, req: BottleUpdateRequest) -> BottleOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bottles WHERE id = ? AND bar_id = ?", (bottle_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Garrafa não encontrada neste bar.")

        conn.execute(
            """
            UPDATE bottles
            SET name = ?, description = ?, color_hex = ?, is_alcoholic = ?, is_mixer = ?,
                bottle_volume_ml = ?, cost_cents = ?, loss_pct = ?, price_per_liter_cents = ?
            WHERE id = ? AND bar_id = ?
            """,
            (
                req.name.strip() if req.name is not None else row["name"],
                req.description.strip() if req.description is not None else row["description"],
                req.color_hex if req.color_hex is not None else row["color_hex"],
                int(req.is_alcoholic) if req.is_alcoholic is not None else row["is_alcoholic"],
                int(req.is_mixer) if req.is_mixer is not None else row["is_mixer"],
                req.bottle_volume_ml if req.bottle_volume_ml is not None else row["bottle_volume_ml"],
                req.cost_cents if req.cost_cents is not None else row["cost_cents"],
                req.loss_pct if req.loss_pct is not None else row["loss_pct"],
                req.price_per_liter_cents if req.price_per_liter_cents is not None else row["price_per_liter_cents"],
                bottle_id,
                bar_id,
            ),
        )
        updated = conn.execute("SELECT * FROM bottles WHERE id = ?", (bottle_id,)).fetchone()
        cnt = conn.execute("SELECT COUNT(*) FROM machine_pumps WHERE bottle_id = ?", (bottle_id,)).fetchone()[0]
        return _row_to_bottle_out(updated, int(cnt))


def delete_bottle(bar_id: str, bottle_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM bottles WHERE id = ? AND bar_id = ?", (bottle_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Garrafa não encontrada.")
        # ON DELETE SET NULL em machine_pumps desacopla automaticamente bombas que usavam a garrafa
        conn.execute("DELETE FROM bottles WHERE id = ? AND bar_id = ?", (bottle_id, bar_id))


# ======================== MACHINES & PUMPS ========================

def _get_reserved_ml_by_pump(conn: sqlite3.Connection, machine_id: str) -> dict[PumpId, float]:
    reserved: dict[PumpId, float] = {p: 0.0 for p in PUMP_IDS_ORDERED}
    rows = conn.execute(
        """
        SELECT steps_json FROM orders
        WHERE machine_id = ? AND status IN ('PAID_QUEUED', 'READY_FOR_CUP', 'PAUSED_TURN', 'DISPENSING')
        """,
        (machine_id,),
    ).fetchall()
    for r in rows:
        try:
            steps = json.loads(r["steps_json"])
            for s in steps:
                pid = s.get("pump")
                if pid in reserved:
                    reserved[pid] += float(s.get("ml", 0.0))
        except Exception:
            pass
    return reserved


def get_machine_pumps_with_bottles(conn: sqlite3.Connection, machine_id: str) -> list[PumpSlotOut]:
    reserved_map = _get_reserved_ml_by_pump(conn, machine_id)
    rows = conn.execute(
        """
        SELECT mp.*,
               b.name AS b_name, b.description AS b_desc, b.color_hex AS b_color,
               b.is_alcoholic AS b_alc, b.is_mixer AS b_mix,
               b.bottle_volume_ml AS b_vol, b.price_per_liter_cents AS b_ppl,
               b.cost_cents AS b_cost, b.loss_pct AS b_loss
        FROM machine_pumps mp
        LEFT JOIN bottles b ON b.id = mp.bottle_id
        WHERE mp.machine_id = ?
        """,
        (machine_id,),
    ).fetchall()

    by_id: dict[str, PumpSlotOut] = {}
    for r in rows:
        pid: PumpId = r["pump_id"]
        has_bottle = r["bottle_id"] is not None and r["b_name"] is not None
        rem = float(r["remaining_ml"])
        min_res = float(r["min_reserve_ml"])
        in_flight = reserved_map.get(pid, 0.0)
        avail = max(0.0, round(rem - min_res - in_flight, 1)) if has_bottle else 0.0
        ppl = int(r["b_ppl"] or 0) if has_bottle else 0

        by_id[pid] = PumpSlotOut(
            pump_id=pid,
            label=r["label"],
            gpio=int(r["gpio"]),
            flow_rate_ml_s=float(r["flow_rate_ml_s"]),
            remaining_ml=round(rem, 1),
            min_reserve_ml=round(min_res, 1),
            available_ml=avail,
            bottle_id=r["bottle_id"] if has_bottle else None,
            ingredient=r["b_name"] if has_bottle else "Sem Garrafa Instalada",
            description=r["b_desc"] if has_bottle else "Vincule uma garrafa no painel do bar",
            color_hex=r["b_color"] if has_bottle else "#9ca3af",
            is_alcoholic=bool(r["b_alc"]) if has_bottle else False,
            is_mixer=bool(r["b_mix"]) if has_bottle else False,
            bottle_volume_ml=float(r["b_vol"] or 1000.0),
            price_per_liter_cents=ppl,
            price_per_10ml_cents=round(ppl / 100.0, 2),
        )

    return [by_id[p] for p in PUMP_IDS_ORDERED if p in by_id]


def list_public_machines() -> list[PublicMachineSummary]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.slug, m.name, b.name AS bar_name
            FROM machines m
            JOIN bars b ON b.id = m.bar_id
            WHERE b.active = 1
            ORDER BY b.name ASC, m.name ASC
            """
        ).fetchall()
        return [PublicMachineSummary(slug=r["slug"], name=r["name"], bar_name=r["bar_name"]) for r in rows]


def get_machine_row_by_slug(slug: str) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT m.*, b.name AS bar_name, b.slug AS bar_slug, b.active AS bar_active,
                   b.payment_provider, b.mp_access_token, b.platform_fee_percent
            FROM machines m
            JOIN bars b ON b.id = m.bar_id
            WHERE m.slug = ?
            """,
            (slug,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Máquina '{slug}' não encontrada.")
        if not row["bar_active"]:
            raise HTTPException(status_code=403, detail="Este estabelecimento está temporariamente inativo.")
        return row


def get_machine_row_by_id(bar_id: str, machine_id: str) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM machines WHERE id = ? AND bar_id = ?", (machine_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Máquina não encontrada neste bar.")
        return row


def list_bar_machine_rows(bar_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM machines WHERE bar_id = ? ORDER BY created_at ASC",
            (bar_id,),
        ).fetchall()


def create_machine(bar_id: str, req: MachineCreateRequest) -> sqlite3.Row:
    now = utcnow_iso()
    machine_id = f"mach-{uuid.uuid4().hex[:10]}"
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM machines WHERE slug = ?", (req.slug,)).fetchone():
            raise HTTPException(status_code=409, detail=f"O QR Code '{req.slug}' já está em uso por outra máquina.")
        conn.execute(
            """
            INSERT INTO machines (
                id, bar_id, slug, name, api_token, cup_fee_cents, min_order_cents,
                max_cup_ml, allow_custom_builder, connection_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                machine_id,
                bar_id,
                req.slug.strip(),
                req.name.strip(),
                f"iot_{secrets.token_urlsafe(18)}",
                req.cup_fee_cents,
                req.min_order_cents,
                req.max_cup_ml,
                int(req.allow_custom_builder),
                req.connection_mode,
                now,
            ),
        )
        for pid in PUMP_IDS_ORDERED:
            label, gpio, flow = DEFAULT_PUMP_META[pid]
            conn.execute(
                """
                INSERT INTO machine_pumps (
                    machine_id, pump_id, label, gpio, bottle_id, flow_rate_ml_s, remaining_ml, min_reserve_ml
                ) VALUES (?, ?, ?, ?, NULL, ?, 0.0, 25.0)
                """,
                (machine_id, pid, label, gpio, flow),
            )
        return conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()


def update_machine(bar_id: str, machine_id: str, req: MachineUpdateRequest) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM machines WHERE id = ? AND bar_id = ?", (machine_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Máquina não encontrada.")
        conn.execute(
            """
            UPDATE machines
            SET name = ?, cup_fee_cents = ?, min_order_cents = ?, max_cup_ml = ?,
                allow_custom_builder = ?, connection_mode = ?, esp32_host = ?,
                esp32_port = ?, serial_port = ?, serial_baud = ?
            WHERE id = ? AND bar_id = ?
            """,
            (
                req.name.strip() if req.name is not None else row["name"],
                req.cup_fee_cents if req.cup_fee_cents is not None else row["cup_fee_cents"],
                req.min_order_cents if req.min_order_cents is not None else row["min_order_cents"],
                req.max_cup_ml if req.max_cup_ml is not None else row["max_cup_ml"],
                int(req.allow_custom_builder) if req.allow_custom_builder is not None else row["allow_custom_builder"],
                req.connection_mode if req.connection_mode is not None else row["connection_mode"],
                req.esp32_host.strip() if req.esp32_host is not None else row["esp32_host"],
                req.esp32_port if req.esp32_port is not None else row["esp32_port"],
                req.serial_port.strip() if req.serial_port is not None else row["serial_port"],
                req.serial_baud if req.serial_baud is not None else row["serial_baud"],
                machine_id,
                bar_id,
            ),
        )
        return conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()


def update_pump_slot(bar_id: str, machine_id: str, pump_id: PumpId, req: PumpSlotUpdateRequest) -> list[PumpSlotOut]:
    with get_conn() as conn:
        m_row = conn.execute("SELECT id FROM machines WHERE id = ? AND bar_id = ?", (machine_id, bar_id)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail="Máquina não encontrada.")
        p_row = conn.execute(
            "SELECT * FROM machine_pumps WHERE machine_id = ? AND pump_id = ?",
            (machine_id, pump_id),
        ).fetchone()
        if not p_row:
            raise HTTPException(status_code=404, detail="Bomba inválida.")

        fields_set = req.model_fields_set
        new_bottle_id = p_row["bottle_id"]
        new_remaining = float(p_row["remaining_ml"])

        if "bottle_id" in fields_set:
            if req.bottle_id:
                btl = conn.execute(
                    "SELECT * FROM bottles WHERE id = ? AND bar_id = ?",
                    (req.bottle_id, bar_id),
                ).fetchone()
                if not btl:
                    raise HTTPException(status_code=404, detail="Garrafa selecionada não pertence a este bar.")
                new_bottle_id = btl["id"]
                if "remaining_ml" not in fields_set and p_row["bottle_id"] != new_bottle_id:
                    new_remaining = float(btl["bottle_volume_ml"])
            else:
                new_bottle_id = None
                new_remaining = 0.0

        if req.remaining_ml is not None:
            new_remaining = req.remaining_ml

        conn.execute(
            """
            UPDATE machine_pumps
            SET bottle_id = ?, flow_rate_ml_s = ?, remaining_ml = ?, min_reserve_ml = ?
            WHERE machine_id = ? AND pump_id = ?
            """,
            (
                new_bottle_id,
                req.flow_rate_ml_s if req.flow_rate_ml_s is not None else p_row["flow_rate_ml_s"],
                new_remaining,
                req.min_reserve_ml if req.min_reserve_ml is not None else p_row["min_reserve_ml"],
                machine_id,
                pump_id,
            ),
        )
        return get_machine_pumps_with_bottles(conn, machine_id)


def refill_pump_bottle(bar_id: str, machine_id: str, pump_id: PumpId, custom_ml: float | None = None) -> list[PumpSlotOut]:
    with get_conn() as conn:
        m_row = conn.execute("SELECT id FROM machines WHERE id = ? AND bar_id = ?", (machine_id, bar_id)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail="Máquina não encontrada.")
        p_row = conn.execute(
            """
            SELECT mp.bottle_id, b.bottle_volume_ml
            FROM machine_pumps mp
            LEFT JOIN bottles b ON b.id = mp.bottle_id
            WHERE mp.machine_id = ? AND mp.pump_id = ?
            """,
            (machine_id, pump_id),
        ).fetchone()
        if not p_row or not p_row["bottle_id"]:
            raise HTTPException(status_code=400, detail="Vincule uma garrafa à bomba antes de reabastecer.")

        target_ml = custom_ml if custom_ml is not None else float(p_row["bottle_volume_ml"] or 1000.0)
        conn.execute(
            "UPDATE machine_pumps SET remaining_ml = ? WHERE machine_id = ? AND pump_id = ?",
            (target_ml, machine_id, pump_id),
        )
        return get_machine_pumps_with_bottles(conn, machine_id)


def record_iot_heartbeat(machine_slug: str, api_token: str, ip: str, rssi: int) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM machines WHERE slug = ?", (machine_slug,)).fetchone()
        if not row or not secrets.compare_digest(str(row["api_token"]), api_token.strip()):
            raise HTTPException(status_code=401, detail="Credencial IoT da máquina inválida.")
        conn.execute(
            "UPDATE machines SET last_seen_at = ?, last_ip = ?, last_rssi = ? WHERE id = ?",
            (utcnow_iso(), ip[:45], int(rssi), row["id"]),
        )
        return conn.execute("SELECT * FROM machines WHERE id = ?", (row["id"],)).fetchone()


def deduct_dispensed_volume(machine_id: str, steps: list[DoseStep]) -> None:
    with get_conn() as conn:
        for s in steps:
            conn.execute(
                """
                UPDATE machine_pumps
                SET remaining_ml = MAX(0.0, remaining_ml - ?)
                WHERE machine_id = ? AND pump_id = ?
                """,
                (float(s.ml), machine_id, s.pump),
            )


# ======================== DRINKS FULL CRUD ========================

def _compute_drink_out(
    row: sqlite3.Row,
    pumps_by_id: dict[PumpId, PumpSlotOut],
    bottle_cost_map: dict[str, tuple[int, float]],
    cup_fee_cents: int,
    min_order_cents: int,
) -> DrinkOut:
    raw_steps = json.loads(row["steps_json"])
    steps = [DoseStep(**s) for s in raw_steps]

    total_ml = 0.0
    est_sec = 0.0
    raw_ml_cents = 0
    cost_cents = 0
    is_alc = False
    available = True
    unavail_reason: str | None = None

    req_by_pump: dict[PumpId, float] = {}
    for s in steps:
        total_ml += s.ml
        req_by_pump[s.pump] = req_by_pump.get(s.pump, 0.0) + s.ml
        slot = pumps_by_id.get(s.pump)
        flow = slot.flow_rate_ml_s if slot else 32.0
        est_sec += (s.ml / max(flow, 1.0)) + (s.pause_ms / 1000.0)

        if not slot or not slot.bottle_id:
            available = False
            unavail_reason = f"{slot.label if slot else s.pump} está sem garrafa instalada"
        else:
            if slot.is_alcoholic:
                is_alc = True
            raw_ml_cents += int(round(s.ml * slot.price_per_liter_cents / 1000.0))
            b_cost, b_usable = bottle_cost_map.get(slot.bottle_id, (0, 1000.0))
            cost_cents += int(round(s.ml * (b_cost / max(b_usable, 1.0))))

    if available:
        for pid, needed_ml in req_by_pump.items():
            slot = pumps_by_id.get(pid)
            if slot and slot.available_ml < needed_ml:
                available = False
                unavail_reason = f"Estoque insuficiente de {slot.ingredient} (restam {int(slot.available_ml)} ml)"
                break

    raw_with_cup = raw_ml_cents + cup_fee_cents
    pmode = row["pricing_mode"]
    disc = float(row["discount_pct"] or 0.0)

    if pmode == "fixed":
        final_cents = max(100, int(row["fixed_price_cents"]))
    else:
        discounted = int(round(raw_with_cup * (1.0 - disc / 100.0)))
        final_cents = max(min_order_cents, discounted)

    return DrinkOut(
        id=row["id"],
        bar_id=row["bar_id"],
        name=row["name"],
        subtitle=row["subtitle"],
        description=row["description"],
        category=row["category"],
        badge=row["badge"],
        accent_from=row["accent_from"],
        accent_to=row["accent_to"],
        glass_color=row["glass_color"],
        pricing_mode=pmode,
        fixed_price_cents=int(row["fixed_price_cents"]),
        discount_pct=disc,
        active=bool(row["active"]),
        steps=steps,
        total_ml=round(total_ml, 1),
        estimated_seconds=round(est_sec, 1),
        raw_ml_price_cents=raw_with_cup,
        final_price_cents=final_cents,
        estimated_cost_cents=cost_cents,
        estimated_profit_cents=final_cents - cost_cents,
        is_alcoholic=is_alc,
        available=available,
        unavailable_reason=unavail_reason,
    )


def _get_bottle_cost_map(conn: sqlite3.Connection, bar_id: str) -> dict[str, tuple[int, float]]:
    rows = conn.execute(
        "SELECT id, cost_cents, bottle_volume_ml, loss_pct FROM bottles WHERE bar_id = ?",
        (bar_id,),
    ).fetchall()
    out: dict[str, tuple[int, float]] = {}
    for r in rows:
        usable = float(r["bottle_volume_ml"]) * (1.0 - float(r["loss_pct"]) / 100.0)
        out[r["id"]] = (int(r["cost_cents"]), max(usable, 1.0))
    return out


def list_drinks_for_machine(bar_id: str, machine_id: str, only_active: bool = False) -> list[DrinkOut]:
    with get_conn() as conn:
        m_row = conn.execute("SELECT * FROM machines WHERE id = ? AND bar_id = ?", (machine_id, bar_id)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail="Máquina não encontrada.")
        pumps = get_machine_pumps_with_bottles(conn, machine_id)
        pumps_map = {p.pump_id: p for p in pumps}
        cost_map = _get_bottle_cost_map(conn, bar_id)

        query = "SELECT * FROM drinks WHERE bar_id = ?"
        if only_active:
            query += " AND active = 1"
        query += " ORDER BY sort_order ASC, created_at ASC"
        rows = conn.execute(query, (bar_id,)).fetchall()
        return [
            _compute_drink_out(
                r,
                pumps_map,
                cost_map,
                int(m_row["cup_fee_cents"]),
                int(m_row["min_order_cents"]),
            )
            for r in rows
        ]


def list_bar_drinks(bar_id: str) -> list[DrinkOut]:
    with get_conn() as conn:
        first_m = conn.execute(
            "SELECT id FROM machines WHERE bar_id = ? ORDER BY created_at ASC LIMIT 1",
            (bar_id,),
        ).fetchone()
    if not first_m:
        return []
    return list_drinks_for_machine(bar_id, first_m["id"], only_active=False)


def create_drink(bar_id: str, req: DrinkCreateRequest) -> DrinkOut:
    drink_id = f"drk-{uuid.uuid4().hex[:10]}"
    now = utcnow_iso()
    steps_payload = [s.model_dump() for s in req.steps]
    with get_conn() as conn:
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM drinks WHERE bar_id = ?",
            (bar_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO drinks (
                id, bar_id, name, subtitle, description, category, badge,
                accent_from, accent_to, glass_color, pricing_mode, fixed_price_cents,
                discount_pct, active, steps_json, sort_order, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                drink_id,
                bar_id,
                req.name.strip(),
                req.subtitle.strip(),
                req.description.strip(),
                req.category.strip(),
                req.badge.strip(),
                req.accent_from,
                req.accent_to,
                req.glass_color,
                req.pricing_mode,
                req.fixed_price_cents,
                req.discount_pct,
                int(req.active),
                json.dumps(steps_payload),
                int(max_sort) + 1,
                now,
            ),
        )
    for d in list_bar_drinks(bar_id):
        if d.id == drink_id:
            return d
    raise RuntimeError("Erro ao carregar drink criado.")


def update_drink(bar_id: str, drink_id: str, req: DrinkUpdateRequest) -> DrinkOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ? AND bar_id = ?", (drink_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Drink não encontrado neste bar.")

        steps_str = json.dumps([s.model_dump() for s in req.steps]) if req.steps is not None else row["steps_json"]
        conn.execute(
            """
            UPDATE drinks
            SET name = ?, subtitle = ?, description = ?, category = ?, badge = ?,
                accent_from = ?, accent_to = ?, glass_color = ?, pricing_mode = ?,
                fixed_price_cents = ?, discount_pct = ?, active = ?, steps_json = ?
            WHERE id = ? AND bar_id = ?
            """,
            (
                req.name.strip() if req.name is not None else row["name"],
                req.subtitle.strip() if req.subtitle is not None else row["subtitle"],
                req.description.strip() if req.description is not None else row["description"],
                req.category.strip() if req.category is not None else row["category"],
                req.badge.strip() if req.badge is not None else row["badge"],
                req.accent_from if req.accent_from is not None else row["accent_from"],
                req.accent_to if req.accent_to is not None else row["accent_to"],
                req.glass_color if req.glass_color is not None else row["glass_color"],
                req.pricing_mode if req.pricing_mode is not None else row["pricing_mode"],
                req.fixed_price_cents if req.fixed_price_cents is not None else row["fixed_price_cents"],
                req.discount_pct if req.discount_pct is not None else row["discount_pct"],
                int(req.active) if req.active is not None else row["active"],
                steps_str,
                drink_id,
                bar_id,
            ),
        )
    for d in list_bar_drinks(bar_id):
        if d.id == drink_id:
            return d
    raise HTTPException(status_code=404, detail="Drink não encontrado.")


def delete_drink(bar_id: str, drink_id: str) -> None:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM drinks WHERE id = ? AND bar_id = ?", (drink_id, bar_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Drink não encontrado neste bar.")


# ======================== ORDERS & VIRTUAL QUEUE ========================

def _row_to_order_out(conn: sqlite3.Connection, row: sqlite3.Row) -> OrderOut:
    m_row = conn.execute("SELECT slug, name FROM machines WHERE id = ?", (row["machine_id"],)).fetchone()
    now = utcnow()

    pix_exp = _parse_iso(row["pix_expires_at"])
    sec_pix = max(0, int((pix_exp - now).total_seconds())) if pix_exp and row["status"] == "PENDING_PAYMENT" else 0

    turn_exp = _parse_iso(row["turn_expires_at"])
    sec_turn = max(0, int((turn_exp - now).total_seconds())) if turn_exp and row["status"] == "READY_FOR_CUP" else 0

    q_pos = 0
    if row["status"] == "READY_FOR_CUP":
        q_pos = 1
    elif row["status"] == "PAID_QUEUED":
        ahead = conn.execute(
            """
            SELECT COUNT(*) FROM orders
            WHERE machine_id = ?
              AND (
                status IN ('DISPENSING', 'READY_FOR_CUP')
                OR (status = 'PAID_QUEUED' AND paid_at < ?)
              )
            """,
            (row["machine_id"], row["paid_at"] or row["created_at"]),
        ).fetchone()[0]
        q_pos = int(ahead) + 1

    steps = [DoseStep(**s) for s in json.loads(row["steps_json"])]
    items = [OrderItemBreakdown(**it) for it in json.loads(row["items_json"])]

    return OrderOut(
        id=row["id"],
        order_number=int(row["order_number"]),
        bar_id=row["bar_id"],
        machine_id=row["machine_id"],
        machine_slug=m_row["slug"] if m_row else "",
        machine_name=m_row["name"] if m_row else "",
        customer_session_id=row["customer_session_id"],
        customer_name=row["customer_name"],
        drink_id=row["drink_id"],
        drink_name=row["drink_name"],
        is_custom=bool(row["is_custom"]),
        is_alcoholic=bool(row["is_alcoholic"]),
        steps=steps,
        items=items,
        total_ml=float(row["total_ml"]),
        subtotal_cents=int(row["subtotal_cents"]),
        cup_fee_cents=int(row["cup_fee_cents"]),
        total_cents=int(row["total_cents"]),
        cost_total_cents=int(row["cost_total_cents"]),
        platform_fee_cents=int(row["platform_fee_cents"]),
        bar_net_cents=int(row["bar_net_cents"]),
        status=row["status"],
        queue_position=q_pos,
        seconds_until_pix_expiry=sec_pix,
        seconds_until_turn_expiry=sec_turn,
        payment_provider=row["payment_provider"],
        payment_external_id=row["payment_external_id"],
        pix_qr_code=row["pix_qr_code"],
        pix_qr_base64=row["pix_qr_base64"],
        created_at=row["created_at"],
        paid_at=row["paid_at"],
        completed_at=row["completed_at"],
    )


def expire_and_advance_queue(machine_id: str) -> bool:
    """Expira cobranças Pix vencidas, pausa turnos sem resposta em 75s e promove o próximo da fila."""
    changed = False
    now = utcnow()
    now_iso = now.isoformat()

    with get_conn() as conn:
        # 1. Expira Pix pendentes vencidos
        cur1 = conn.execute(
            """
            UPDATE orders
            SET status = 'EXPIRED'
            WHERE machine_id = ? AND status = 'PENDING_PAYMENT' AND pix_expires_at IS NOT NULL AND pix_expires_at < ?
            """,
            (machine_id, now_iso),
        )
        if cur1.rowcount > 0:
            changed = True

        # 2. Pausa cliente em READY_FOR_CUP que demorou além da janela sem confirmar o copo (evita travar o bar)
        cur2 = conn.execute(
            """
            UPDATE orders
            SET status = 'PAUSED_TURN', turn_expires_at = NULL
            WHERE machine_id = ? AND status = 'READY_FOR_CUP' AND turn_expires_at IS NOT NULL AND turn_expires_at < ?
            """,
            (machine_id, now_iso),
        )
        if cur2.rowcount > 0:
            changed = True

        # 3. Se não houver ninguém DISPENSING nem READY_FOR_CUP, promove o próximo PAID_QUEUED
        busy = conn.execute(
            "SELECT 1 FROM orders WHERE machine_id = ? AND status IN ('DISPENSING', 'READY_FOR_CUP') LIMIT 1",
            (machine_id,),
        ).fetchone()
        if not busy:
            nxt = conn.execute(
                """
                SELECT id FROM orders
                WHERE machine_id = ? AND status = 'PAID_QUEUED'
                ORDER BY paid_at ASC, created_at ASC
                LIMIT 1
                """,
                (machine_id,),
            ).fetchone()
            if nxt:
                turn_exp = (now + dt.timedelta(seconds=settings.turn_window_seconds)).isoformat()
                conn.execute(
                    "UPDATE orders SET status = 'READY_FOR_CUP', turn_expires_at = ? WHERE id = ?",
                    (turn_exp, nxt["id"]),
                )
                changed = True

    return changed


def get_machine_queue_stats(machine_id: str) -> tuple[int, str | None, int | None]:
    expire_and_advance_queue(machine_id)
    with get_conn() as conn:
        q_len = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE machine_id = ? AND status IN ('PAID_QUEUED', 'READY_FOR_CUP', 'DISPENSING')",
            (machine_id,),
        ).fetchone()[0]
        ready = conn.execute(
            "SELECT id, order_number FROM orders WHERE machine_id = ? AND status = 'READY_FOR_CUP' LIMIT 1",
            (machine_id,),
        ).fetchone()
        return (
            int(q_len),
            str(ready["id"]) if ready else None,
            int(ready["order_number"]) if ready else None,
        )


def get_active_customer_order(machine_id: str, customer_session_id: str | None) -> OrderOut | None:
    if not customer_session_id:
        return None
    expire_and_advance_queue(machine_id)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM orders
            WHERE machine_id = ?
              AND customer_session_id = ?
              AND status IN ('PENDING_PAYMENT', 'PAID_QUEUED', 'READY_FOR_CUP', 'PAUSED_TURN', 'DISPENSING')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (machine_id, customer_session_id),
        ).fetchone()
        return _row_to_order_out(conn, row) if row else None


def get_order_by_id(order_id: str) -> OrderOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        machine_id = row["machine_id"]
    expire_and_advance_queue(machine_id)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _row_to_order_out(conn, row)


def prepare_validated_order_draft(
    *,
    machine_slug: str,
    customer_session_id: str,
    customer_name: str,
    drink_id: str | None,
    custom_name: str | None,
    custom_volumes: dict[PumpId, float] | None,
) -> tuple[sqlite3.Row, dict[str, object]]:
    """Valida estoque real das garrafas, calcula centavos exatos por ml e aloca número do pedido."""
    with get_conn() as conn:
        m_row = conn.execute(
            """
            SELECT m.*, b.name AS bar_name, b.payment_provider, b.mp_access_token, b.platform_fee_percent, b.active AS bar_active
            FROM machines m
            JOIN bars b ON b.id = m.bar_id
            WHERE m.slug = ?
            """,
            (machine_slug,),
        ).fetchone()
        if not m_row or not m_row["bar_active"]:
            raise HTTPException(status_code=404, detail="Máquina indisponível.")

        bar_id = m_row["bar_id"]
        machine_id = m_row["id"]
        max_cup_ml = int(m_row["max_cup_ml"])
        cup_fee = int(m_row["cup_fee_cents"])
        min_order = int(m_row["min_order_cents"])

        # Cancela eventual cobrança PENDING_PAYMENT anterior da mesma sessão para não acumular lixo
        conn.execute(
            "UPDATE orders SET status = 'CANCELED' WHERE machine_id = ? AND customer_session_id = ? AND status = 'PENDING_PAYMENT'",
            (machine_id, customer_session_id),
        )

        pumps = get_machine_pumps_with_bottles(conn, machine_id)
        pumps_map = {p.pump_id: p for p in pumps}
        cost_map = _get_bottle_cost_map(conn, bar_id)

        steps: list[DoseStep] = []
        is_custom = drink_id is None
        final_drink_name = "Mix Personalizado"
        fixed_override_cents: int | None = None
        discount_pct = 0.0

        if not is_custom:
            d_row = conn.execute(
                "SELECT * FROM drinks WHERE id = ? AND bar_id = ? AND active = 1",
                (drink_id, bar_id),
            ).fetchone()
            if not d_row:
                raise HTTPException(status_code=404, detail="Este drink não está mais disponível no cardápio.")
            final_drink_name = d_row["name"]
            steps = [DoseStep(**s) for s in json.loads(d_row["steps_json"])]
            if d_row["pricing_mode"] == "fixed":
                fixed_override_cents = int(d_row["fixed_price_cents"])
            else:
                discount_pct = float(d_row["discount_pct"] or 0.0)
        else:
            if not m_row["allow_custom_builder"]:
                raise HTTPException(status_code=403, detail="O modo 'Monte seu Drink' está desativado nesta máquina.")
            assert custom_volumes is not None
            final_drink_name = (custom_name or "Mix Personalizado").strip() or "Mix Personalizado"
            non_zero = [(pid, float(custom_volumes.get(pid, 0.0))) for pid in PUMP_IDS_ORDERED if float(custom_volumes.get(pid, 0.0)) > 0]
            for idx, (pid, ml) in enumerate(non_zero):
                is_last = idx == len(non_zero) - 1
                steps.append(DoseStep(pump=pid, ml=ml, pause_ms=0 if is_last else 1200))

        total_ml = sum(s.ml for s in steps)
        if total_ml < 10:
            raise HTTPException(status_code=400, detail="O pedido mínimo é de 10 ml.")
        if total_ml > max_cup_ml:
            raise HTTPException(status_code=400, detail=f"O volume máximo de segurança do copo é de {max_cup_ml} ml.")

        # Verifica garrafas e estoque por bomba
        needed_by_pump: dict[PumpId, float] = {}
        for s in steps:
            needed_by_pump[s.pump] = needed_by_pump.get(s.pump, 0.0) + s.ml

        items: list[OrderItemBreakdown] = []
        raw_liquids_cents = 0
        cost_total_cents = 0
        is_alcoholic = False

        for pid in PUMP_IDS_ORDERED:
            ml = needed_by_pump.get(pid, 0.0)
            if ml <= 0:
                continue
            slot = pumps_map.get(pid)
            if not slot or not slot.bottle_id:
                raise HTTPException(status_code=400, detail=f"{slot.label if slot else pid} está sem garrafa vinculada.")
            if slot.available_ml < ml:
                raise HTTPException(
                    status_code=409,
                    detail=f"Estoque insuficiente de {slot.ingredient} na máquina (disponível: {int(slot.available_ml)} ml).",
                )
            if slot.is_alcoholic:
                is_alcoholic = True

            line_price = int(round(ml * slot.price_per_liter_cents / 1000.0))
            b_cost, b_usable = cost_map.get(slot.bottle_id, (0, 1000.0))
            line_cost = int(round(ml * (b_cost / max(b_usable, 1.0))))
            raw_liquids_cents += line_price
            cost_total_cents += line_cost

            items.append(
                OrderItemBreakdown(
                    pump=pid,
                    bottle_id=slot.bottle_id,
                    ingredient=slot.ingredient,
                    color_hex=slot.color_hex,
                    ml=round(ml, 1),
                    price_cents=line_price,
                    cost_cents=line_cost,
                )
            )

        if fixed_override_cents is not None:
            total_cents = max(100, fixed_override_cents)
            subtotal_cents = max(0, total_cents - cup_fee)
        else:
            subtotal_cents = raw_liquids_cents
            gross_before_min = int(round((subtotal_cents + cup_fee) * (1.0 - discount_pct / 100.0)))
            total_cents = max(min_order, gross_before_min)

        fee_pct = float(m_row["platform_fee_percent"] or 0.0)
        platform_fee_cents = int(round(total_cents * fee_pct / 100.0))
        bar_net_cents = total_cents - platform_fee_cents

        ord_num = int(conn.execute("SELECT next_order_number FROM bars WHERE id = ?", (bar_id,)).fetchone()[0])
        conn.execute("UPDATE bars SET next_order_number = next_order_number + 1 WHERE id = ?", (bar_id,))

        draft = {
            "id": f"ord-{uuid.uuid4().hex[:12]}",
            "order_number": ord_num,
            "bar_id": bar_id,
            "machine_id": machine_id,
            "customer_session_id": customer_session_id,
            "customer_name": customer_name.strip(),
            "drink_id": drink_id,
            "drink_name": final_drink_name,
            "is_custom": is_custom,
            "is_alcoholic": is_alcoholic,
            "steps": steps,
            "items": items,
            "total_ml": round(total_ml, 1),
            "subtotal_cents": subtotal_cents,
            "cup_fee_cents": cup_fee,
            "total_cents": total_cents,
            "cost_total_cents": cost_total_cents,
            "platform_fee_cents": platform_fee_cents,
            "bar_net_cents": bar_net_cents,
        }
        return m_row, draft


def insert_pending_order(draft: dict[str, object], provider: str, ext_id: str, qr_text: str, qr_uri: str, expires_iso: str) -> OrderOut:
    now_iso = utcnow_iso()
    steps: list[DoseStep] = draft["steps"]  # type: ignore[assignment]
    items: list[OrderItemBreakdown] = draft["items"]  # type: ignore[assignment]

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                id, order_number, bar_id, machine_id, customer_session_id, customer_name,
                drink_id, drink_name, is_custom, is_alcoholic, steps_json, items_json,
                total_ml, subtotal_cents, cup_fee_cents, total_cents, cost_total_cents,
                platform_fee_cents, bar_net_cents, status, payment_provider, payment_external_id,
                pix_qr_code, pix_qr_base64, pix_expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_PAYMENT', ?, ?, ?, ?, ?, ?)
            """,
            (
                draft["id"],
                draft["order_number"],
                draft["bar_id"],
                draft["machine_id"],
                draft["customer_session_id"],
                draft["customer_name"],
                draft["drink_id"],
                draft["drink_name"],
                int(bool(draft["is_custom"])),
                int(bool(draft["is_alcoholic"])),
                json.dumps([s.model_dump() for s in steps]),
                json.dumps([it.model_dump() for it in items]),
                draft["total_ml"],
                draft["subtotal_cents"],
                draft["cup_fee_cents"],
                draft["total_cents"],
                draft["cost_total_cents"],
                draft["platform_fee_cents"],
                draft["bar_net_cents"],
                provider,
                ext_id,
                qr_text,
                qr_uri,
                expires_iso,
                now_iso,
            ),
        )
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (draft["id"],)).fetchone()
        return _row_to_order_out(conn, row)


def confirm_order_payment(order_id: str) -> tuple[OrderOut, bool]:
    """Marca pedido como pago (idempotente) e avança fila da máquina."""
    became_paid = False
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        machine_id = row["machine_id"]
        if row["status"] in ("PENDING_PAYMENT", "EXPIRED"):
            conn.execute(
                "UPDATE orders SET status = 'PAID_QUEUED', paid_at = ? WHERE id = ?",
                (utcnow_iso(), order_id),
            )
            became_paid = True

    expire_and_advance_queue(machine_id)
    return get_order_by_id(order_id), became_paid


def confirm_order_payment_by_external_id(bar_id: str, external_id: str) -> tuple[OrderOut | None, bool]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM orders WHERE bar_id = ? AND payment_external_id = ?",
            (bar_id, external_id),
        ).fetchone()
    if not row:
        return None, False
    return confirm_order_payment(row["id"])


def cancel_pending_order(order_id: str, customer_session_id: str) -> OrderOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if row["customer_session_id"] != customer_session_id:
            raise HTTPException(status_code=403, detail="Sessão inválida para cancelar este pedido.")
        if row["status"] != "PENDING_PAYMENT":
            raise HTTPException(status_code=409, detail="Este pedido já foi pago ou encerrado.")
        conn.execute("UPDATE orders SET status = 'CANCELED' WHERE id = ?", (order_id,))
    return get_order_by_id(order_id)


def resume_or_extend_customer_turn(order_id: str, customer_session_id: str) -> OrderOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if row["customer_session_id"] != customer_session_id:
            raise HTTPException(status_code=403, detail="Sessão inválida.")
        machine_id = row["machine_id"]

        if row["status"] == "READY_FOR_CUP":
            new_exp = (utcnow() + dt.timedelta(seconds=settings.turn_window_seconds)).isoformat()
            conn.execute("UPDATE orders SET turn_expires_at = ? WHERE id = ?", (new_exp, order_id))
        elif row["status"] == "PAUSED_TURN":
            # Volta para o topo da fila (paid_at preservado é mais antigo)
            conn.execute("UPDATE orders SET status = 'PAID_QUEUED' WHERE id = ?", (order_id,))

    expire_and_advance_queue(machine_id)
    return get_order_by_id(order_id)


def list_pending_mp_orders() -> list[tuple[str, str, str]]:
    """Retorna lista de (order_id, payment_external_id, mp_access_token) aguardando confirmação."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT o.id, o.payment_external_id, b.mp_access_token
            FROM orders o
            JOIN bars b ON b.id = o.bar_id
            WHERE o.status = 'PENDING_PAYMENT'
              AND o.payment_provider = 'mercadopago'
              AND o.payment_external_id IS NOT NULL
            """
        ).fetchall()
        return [(r["id"], r["payment_external_id"], r["mp_access_token"]) for r in rows if r["mp_access_token"]]


def mark_order_dispensing(order_id: str, customer_session_id: str) -> OrderOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if row["customer_session_id"] != customer_session_id:
            raise HTTPException(status_code=403, detail="Este pedido pertence a outro celular.")

    expire_and_advance_queue(row["machine_id"])
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row["status"] != "READY_FOR_CUP":
            if row["status"] == "PAUSED_TURN":
                raise HTTPException(
                    status_code=409,
                    detail="Seu tempo de vez expirou. Toque em 'Estou na Máquina' para reativar sua vez!",
                )
            raise HTTPException(
                status_code=409,
                detail="Aguarde sua vez na fila antes de acionar as bombas.",
            )
        now_iso = utcnow_iso()
        conn.execute(
            "UPDATE orders SET status = 'DISPENSING', cup_confirmed_at = ?, turn_expires_at = NULL WHERE id = ?",
            (now_iso, order_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _row_to_order_out(conn, updated)


def finalize_order_after_dispense(order_id: str, success: bool) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            return
        machine_id = row["machine_id"]
        if success:
            steps = [DoseStep(**s) for s in json.loads(row["steps_json"])]
            for s in steps:
                conn.execute(
                    "UPDATE machine_pumps SET remaining_ml = MAX(0.0, remaining_ml - ?) WHERE machine_id = ? AND pump_id = ?",
                    (float(s.ml), machine_id, s.pump),
                )
            conn.execute(
                "UPDATE orders SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                (utcnow_iso(), order_id),
            )
        else:
            # Caso hardware falhe antes de concluir, devolve para READY_FOR_CUP ou FAILED_DISPENSE
            conn.execute("UPDATE orders SET status = 'FAILED_DISPENSE' WHERE id = ?", (order_id,))

    expire_and_advance_queue(machine_id)


def list_bar_orders(bar_id: str, limit: int = 80) -> list[OrderOut]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE bar_id = ? ORDER BY created_at DESC LIMIT ?",
            (bar_id, limit),
        ).fetchall()
        return [_row_to_order_out(conn, r) for r in rows]


def mark_order_refunded(bar_id: str, order_id: str) -> tuple[OrderOut, str, str, str | None]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT o.*, b.mp_access_token
            FROM orders o
            JOIN bars b ON b.id = o.bar_id
            WHERE o.id = ? AND o.bar_id = ?
            """,
            (order_id, bar_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado neste bar.")
        if row["status"] in ("PENDING_PAYMENT", "CANCELED", "EXPIRED", "REFUNDED"):
            raise HTTPException(status_code=400, detail=f"Não é possível estornar pedido com status {row['status']}.")

        provider = row["payment_provider"]
        mp_tok = row["mp_access_token"]
        ext_id = row["payment_external_id"]
        machine_id = row["machine_id"]

        conn.execute("UPDATE orders SET status = 'REFUNDED', turn_expires_at = NULL WHERE id = ?", (order_id,))
    expire_and_advance_queue(machine_id)
    return get_order_by_id(order_id), provider, mp_tok, ext_id


def retry_failed_order(bar_id: str, order_id: str) -> OrderOut:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ? AND bar_id = ?", (order_id, bar_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if row["status"] != "FAILED_DISPENSE":
            raise HTTPException(status_code=400, detail="Apenas pedidos com falha de preparo podem ser reenviados à fila.")
        conn.execute("UPDATE orders SET status = 'PAID_QUEUED' WHERE id = ?", (order_id,))
        machine_id = row["machine_id"]
    expire_and_advance_queue(machine_id)
    return get_order_by_id(order_id)


def get_bar_analytics(bar_id: str) -> BarAnalyticsOut:
    with get_conn() as conn:
        paid = conn.execute(
            """
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(total_cents), 0) AS gross,
                   COALESCE(SUM(cost_total_cents), 0) AS cost,
                   COALESCE(SUM(platform_fee_cents), 0) AS fees,
                   COALESCE(SUM(bar_net_cents - cost_total_cents), 0) AS profit
            FROM orders
            WHERE bar_id = ? AND status IN ('PAID_QUEUED', 'READY_FOR_CUP', 'PAUSED_TURN', 'DISPENSING', 'COMPLETED')
            """,
            (bar_id,),
        ).fetchone()

        completed_agg = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_ml), 0.0) AS ml FROM orders WHERE bar_id = ? AND status = 'COMPLETED'",
            (bar_id,),
        ).fetchone()

        pending_cnt = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE bar_id = ? AND status = 'PENDING_PAYMENT'",
            (bar_id,),
        ).fetchone()[0]

        refunded_cnt = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE bar_id = ? AND status = 'REFUNDED'",
            (bar_id,),
        ).fetchone()[0]

        return BarAnalyticsOut(
            paid_orders_count=int(paid["cnt"]),
            completed_orders_count=int(completed_agg["cnt"]),
            pending_orders_count=int(pending_cnt),
            refunded_orders_count=int(refunded_cnt),
            gross_revenue_cents=int(paid["gross"]),
            total_cost_cents=int(paid["cost"]),
            platform_fees_cents=int(paid["fees"]),
            net_profit_cents=int(paid["profit"]),
            total_ml_dispensed=round(float(completed_agg["ml"]), 1),
        )
