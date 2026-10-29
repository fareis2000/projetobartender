from __future__ import annotations

import json
from pathlib import Path
from .config import DATA_DIR
from .models import DoseStep, DrinkRecipe, PumpConfig, PumpId, PumpUpdateRequest

PUMPS_FILE: Path = DATA_DIR / "pumps.json"

# Mapeamento oficial calibrado do repositório original + GPIOs seguros do ESP32-WROOM-32
DEFAULT_PUMPS: dict[PumpId, PumpConfig] = {
    "amarelo": PumpConfig(
        id="amarelo",
        label="Bomba 1 · Amarela",
        ingredient="Citrus / Maracujá",
        description="Xarope cítrico aromático de limão siciliano e maracujá",
        gpio=16,
        flow_rate_ml_s=30.5,
        color_hex="#f59e0b",
        is_mixer=False,
    ),
    "vermelho": PumpConfig(
        id="vermelho",
        label="Bomba 2 · Vermelha",
        ingredient="Morango & Frutas Vermelhas",
        description="Xarope intenso de morango silvestre e grenadine",
        gpio=17,
        flow_rate_ml_s=32.3,
        color_hex="#ef4444",
        is_mixer=False,
    ),
    "verde": PumpConfig(
        id="verde",
        label="Bomba 3 · Verde",
        ingredient="Maçã Verde & Menta",
        description="Xarope refrescante de maçã verde com toque herbal",
        gpio=18,
        flow_rate_ml_s=32.3,
        color_hex="#10b981",
        is_mixer=False,
    ),
    "azul": PumpConfig(
        id="azul",
        label="Bomba 4 · Azul (Base)",
        ingredient="Água com Gás / Soda",
        description="Base gaseificada gelada para completar e dar leveza",
        gpio=19,
        flow_rate_ml_s=35.9,
        color_hex="#0ea5e9",
        is_mixer=True,
    ),
}

BASE_RECIPES: list[DrinkRecipe] = [
    DrinkRecipe(
        id="red",
        code="RED",
        name="Red Robotics",
        subtitle="Soda Italiana de Morango",
        description=(
            "Algoritmo líquido com controle de sabor e visual high-tech. "
            "Entradas, processamento e saída em perfeita sincronia."
        ),
        category="Clássicos Tech",
        badge="Clássico #01",
        accent_from="#ef4444",
        accent_to="#ec4899",
        glass_color="#f43f5e",
        steps=[
            DoseStep(pump="vermelho", ml=70, pause_ms=1500),
            DoseStep(pump="azul", ml=220, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="yellow",
        code="YELLOW",
        name="Yellow Web",
        subtitle="Limonada & Citrus Fizz",
        description=(
            "Leve, fluida e fácil de gostar. Um drink que te guia, "
            "gole após gole, como uma navegação bem feita."
        ),
        category="Clássicos Tech",
        badge="Refrescante",
        accent_from="#f59e0b",
        accent_to="#eab308",
        glass_color="#fbbf24",
        steps=[
            DoseStep(pump="amarelo", ml=100, pause_ms=1500),
            DoseStep(pump="azul", ml=250, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="green",
        code="GREEN",
        name="Green Games",
        subtitle="Soda de Maçã Verde",
        description=(
            "Começa suave, cresce em cor e energia e termina com aquela "
            "vontade de jogar — ou beber — mais uma vez."
        ),
        category="Clássicos Tech",
        badge="Energia",
        accent_from="#10b981",
        accent_to="#06b6d4",
        glass_color="#34d399",
        steps=[
            DoseStep(pump="verde", ml=101, pause_ms=1500),
            DoseStep(pump="azul", ml=250, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="mix",
        code="MIX",
        name="Mix Basics",
        subtitle="Blend Sunset Citrus & Berry",
        description=(
            "Uma receita montada em etapas com um algoritmo vencedor. "
            "Cada sabor entra no jogo, o sistema roda e o resultado é hexa."
        ),
        category="Clássicos Tech",
        badge="Favorito da Casa",
        accent_from="#f97316",
        accent_to="#ef4444",
        glass_color="#fb7185",
        steps=[
            DoseStep(pump="amarelo", ml=50, pause_ms=1500),
            DoseStep(pump="vermelho", ml=50, pause_ms=1500),
            DoseStep(pump="azul", ml=270, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="cyber-tropics",
        code="CYBER_TROPICS",
        name="Cyber Tropics",
        subtitle="Fusão Cítrica & Maçã Verde",
        description=(
            "Combinação vibrante entre acidez cítrica e frescor de maçã verde, "
            "finalizada com água gaseificada."
        ),
        category="Autorais ESP32",
        badge="Novo",
        accent_from="#84cc16",
        accent_to="#10b981",
        glass_color="#a3e635",
        steps=[
            DoseStep(pump="amarelo", ml=55, pause_ms=1200),
            DoseStep(pump="verde", ml=55, pause_ms=1200),
            DoseStep(pump="azul", ml=230, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="full-stack",
        code="FULL_STACK",
        name="Full-Stack RGB",
        subtitle="Tríade Completa + Soda",
        description=(
            "As quatro bombas trabalhando em harmonia: notas cítricas, frutas "
            "vermelhas e maçã verde equilibradas ao mililitro."
        ),
        category="Autorais ESP32",
        badge="4 Bombas",
        accent_from="#8b5cf6",
        accent_to="#ec4899",
        glass_color="#c084fc",
        steps=[
            DoseStep(pump="amarelo", ml=35, pause_ms=1000),
            DoseStep(pump="vermelho", ml=40, pause_ms=1000),
            DoseStep(pump="verde", ml=35, pause_ms=1000),
            DoseStep(pump="azul", ml=240, pause_ms=0),
        ],
    ),
]


def load_pumps() -> dict[PumpId, PumpConfig]:
    pumps = {k: v.model_copy(deep=True) for k, v in DEFAULT_PUMPS.items()}
    if PUMPS_FILE.exists():
        try:
            raw = json.loads(PUMPS_FILE.read_text(encoding="utf-8"))
            for pid, data in raw.items():
                if pid in pumps:
                    pumps[pid] = PumpConfig(**data)
        except Exception:
            pass
    return pumps


def save_pumps(pumps: dict[PumpId, PumpConfig]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {pid: cfg.model_dump() for pid, cfg in pumps.items()}
    PUMPS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def update_pump_config(pump_id: PumpId, req: PumpUpdateRequest) -> PumpConfig:
    pumps = load_pumps()
    current = pumps[pump_id]
    updated = current.model_copy(
        update={
            k: v
            for k, v in req.model_dump(exclude_none=True).items()
        }
    )
    pumps[pump_id] = updated
    save_pumps(pumps)
    return updated


def compute_recipe_metrics(recipe: DrinkRecipe, pumps: dict[PumpId, PumpConfig]) -> DrinkRecipe:
    total_ml = sum(s.ml for s in recipe.steps)
    est_sec = 0.0
    for s in recipe.steps:
        flow = pumps[s.pump].flow_rate_ml_s
        est_sec += (s.ml / flow) + (s.pause_ms / 1000.0)
    return recipe.model_copy(
        update={
            "total_ml": round(total_ml, 1),
            "estimated_seconds": round(est_sec, 1),
        }
    )


def get_catalog() -> list[DrinkRecipe]:
    pumps = load_pumps()
    return [compute_recipe_metrics(r, pumps) for r in BASE_RECIPES]


def get_drink_by_id(drink_id: str) -> DrinkRecipe | None:
    for d in get_catalog():
        if d.id == drink_id:
            return d
    return None

