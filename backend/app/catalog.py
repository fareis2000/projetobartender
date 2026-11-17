"""Catálogo de receitas tropicais, configuração padrão das 4 bombas e persistência local JSON.

Papel na Arquitetura:
---------------------
Gerencia o inventário líquido da máquina (`DEFAULT_PUMPS` + `backend/data/pumps.json`) e o
cardápio oficial de drinks (`BASE_RECIPES`), enriquecendo cada receita em tempo real com o
volume total (`total_ml`) e a duração exata estimada (`estimated_seconds`) calculada a partir
das vazões calibradas atuais de cada bomba.

Valor Comercial / Operação em Eventos:
--------------------------------------
  - Zero dependência de SGBD externo (PostgreSQL/MySQL/MongoDB): toda a calibração e os nomes
    das bebidas nas garrafas são persistidos em `pumps.json` (legível por humanos e fácil de fazer backup).
  - Flexibilidade de cardápio: se a equipe do bar trocar uma garrafa ou recalibrar uma mangueira
    pelo painel ⚙️, todos os tempos estimados e rótulos de ingredientes nos cards do site são
    atualizados instantaneamente sem reiniciar o servidor.
"""
from __future__ import annotations

import json
from pathlib import Path
from .config import DATA_DIR
from .models import DoseStep, DrinkRecipe, PumpConfig, PumpId, PumpUpdateRequest

# Caminho do arquivo JSON local onde nomes de ingredientes e vazões calibradas são salvos
PUMPS_FILE: Path = DATA_DIR / "pumps.json"

# Mapeamento oficial calibrado do repositório original + GPIOs seguros do ESP32-WROOM-32
# Nota de Hardware: GPIOs 16, 17, 18 e 19 evitam os pinos de Flash SPI (6-11) e pinos de strapping,
# garantindo boot limpo sem acionamento involuntário dos relés.
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

# Catálogo base de coquetéis prontos ("Clássicos da Casa" + "Especiais Tropicais").
# Observe que a Bomba 4 (`azul`, base gaseificada) entra sempre na última etapa com `pause_ms=0`
# para misturar naturalmente os xaropes mais densos depositados no fundo do copo.
BASE_RECIPES: list[DrinkRecipe] = [
    DrinkRecipe(
        id="red",
        code="RED",
        name="Red Robotics",
        subtitle="Soda Italiana de Morango & Hibisco",
        description=(
            "Algoritmo líquido com controle de sabor e visual vibrante. "
            "Entradas, processamento e saída em perfeita sincronia refrescante."
        ),
        category="Clássicos da Casa",
        badge="Frutas Vermelhas",
        accent_from="#e11d48",
        accent_to="#f97316",
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
        subtitle="Limonada Tropical & Maracujá",
        description=(
            "Leve, solar e fácil de gostar. Um drink cítrico que te guia, "
            "gole após gole, como uma brisa de verão."
        ),
        category="Clássicos da Casa",
        badge="Cítrico Solar",
        accent_from="#ea580c",
        accent_to="#eab308",
        glass_color="#f59e0b",
        steps=[
            DoseStep(pump="amarelo", ml=100, pause_ms=1500),
            DoseStep(pump="azul", ml=250, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="green",
        code="GREEN",
        name="Green Games",
        subtitle="Refresco de Maçã Verde & Hortelã",
        description=(
            "Começa suave, cresce em frescor botânico e termina com aquela "
            "vontade de jogar — ou brindar — mais uma vez."
        ),
        category="Clássicos da Casa",
        badge="Botânico",
        accent_from="#059669",
        accent_to="#14b8a6",
        glass_color="#10b981",
        steps=[
            DoseStep(pump="verde", ml=101, pause_ms=1500),
            DoseStep(pump="azul", ml=250, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="mix",
        code="MIX",
        name="Mix Basics",
        subtitle="Pôr do Sol de Frutas & Citrus",
        description=(
            "Uma receita montada em camadas douradas e avermelhadas. "
            "Cada fruta entra em cena e o resultado é puro verão."
        ),
        category="Clássicos da Casa",
        badge="Favorito da Praia",
        accent_from="#ea580c",
        accent_to="#e11d48",
        glass_color="#fb7185",
        steps=[
            DoseStep(pump="amarelo", ml=50, pause_ms=1500),
            DoseStep(pump="vermelho", ml=50, pause_ms=1500),
            DoseStep(pump="azul", ml=270, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="brisa-tropical",
        code="BRISA_TROPICAL",
        name="Brisa de Verão",
        subtitle="Maracujá, Maçã Verde & Água com Gás",
        description=(
            "Encontro refrescante entre o toque ácido do maracujá e o frescor "
            "da maçã verde com hortelã e borbulhas geladas."
        ),
        category="Especiais Tropicais",
        badge="Refrescância Máxima",
        accent_from="#16a34a",
        accent_to="#eab308",
        glass_color="#84cc16",
        steps=[
            DoseStep(pump="amarelo", ml=55, pause_ms=1200),
            DoseStep(pump="verde", ml=55, pause_ms=1200),
            DoseStep(pump="azul", ml=230, pause_ms=0),
        ],
    ),
    DrinkRecipe(
        id="entardecer-tropical",
        code="ENTARDECER",
        name="Entardecer Tropical",
        subtitle="Coquetel Completo das 4 Frutas",
        description=(
            "Todas as notas tropicais do bar em equilíbrio: cítricos dourados, "
            "morango silvestre, maçã verde e soda cristalina."
        ),
        category="Especiais Tropicais",
        badge="Assinatura Tropical",
        accent_from="#f97316",
        accent_to="#db2777",
        glass_color="#fb7185",
        steps=[
            DoseStep(pump="amarelo", ml=35, pause_ms=1000),
            DoseStep(pump="vermelho", ml=40, pause_ms=1000),
            DoseStep(pump="verde", ml=35, pause_ms=1000),
            DoseStep(pump="azul", ml=240, pause_ms=0),
        ],
    ),
]


def load_pumps() -> dict[PumpId, PumpConfig]:
    """Carrega a configuração das 4 bombas mesclando o padrão de fábrica com `pumps.json`.

    Caso `backend/data/pumps.json` não exista ou esteja corrompido, retorna cópias profundas
    seguras de `DEFAULT_PUMPS` (auto-healing), garantindo que o servidor nunca falhe na partida.

    Returns:
        dict[PumpId, PumpConfig]: Mapa das 4 bombas indexado por `PumpId`.
    """
    # Inicia com cópia isolada dos padrões de fábrica para evitar mutação acidental em memória
    pumps = {k: v.model_copy(deep=True) for k, v in DEFAULT_PUMPS.items()}
    if PUMPS_FILE.exists():
        try:
            raw = json.loads(PUMPS_FILE.read_text(encoding="utf-8"))
            for pid, data in raw.items():
                if pid in pumps:
                    # Valida cada entrada com Pydantic antes de aceitar o override persistido
                    pumps[pid] = PumpConfig(**data)
        except Exception:
            # Se o JSON manual contiver erro sintático ou valor fora de faixa, mantém DEFAULT_PUMPS
            pass
    return pumps


def save_pumps(pumps: dict[PumpId, PumpConfig]) -> None:
    """Persiste o estado atual das 4 bombas em `backend/data/pumps.json` formatado em UTF-8.

    Args:
        pumps (dict[PumpId, PumpConfig]): Dicionário completo das bombas a ser gravado em disco.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {pid: cfg.model_dump() for pid, cfg in pumps.items()}
    PUMPS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def update_pump_config(pump_id: PumpId, req: PumpUpdateRequest) -> PumpConfig:
    """Atualiza nome do ingrediente, descrição e/ou vazão calibrada (`ml/s`) de uma bomba específica.

    Args:
        pump_id (PumpId): Identificador da bomba (`amarelo`, `vermelho`, `verde` ou `azul`).
        req (PumpUpdateRequest): Campos parciais enviados pelo operador no painel de calibração.

    Returns:
        PumpConfig: Configuração resultante da bomba já validada e salva em `pumps.json`.
    """
    pumps = load_pumps()
    current = pumps[pump_id]
    # Sobrescreve apenas os atributos efetivamente enviados (ignora campos `None`)
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
    """Calcula dinamicamente o volume total (`ml`) e a duração física (`s`) de uma receita.

    Fórmula volumétrica aplicada por etapa:
        tempo_etapa (s) = (volume_ml / vazao_ml_s) + (pausa_ms / 1000.0)

    Args:
        recipe (DrinkRecipe): Receita base contendo a lista de etapas (`steps`).
        pumps (dict[PumpId, PumpConfig]): Configuração vigente das bombas com as vazões calibradas.

    Returns:
        DrinkRecipe: Nova instância de `DrinkRecipe` preenchida com `total_ml` e `estimated_seconds`.
    """
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
    """Retorna todas as receitas do cardápio com volumes e tempos recalculados para a calibração atual.

    Returns:
        list[DrinkRecipe]: Lista completa de drinks prontos para exibição na vitrine do frontend.
    """
    pumps = load_pumps()
    return [compute_recipe_metrics(r, pumps) for r in BASE_RECIPES]


def get_drink_by_id(drink_id: str) -> DrinkRecipe | None:
    """Busca uma receita específica pelo seu identificador único (`id`).

    Args:
        drink_id (str): Slug da receita (ex.: `'red'`, `'yellow'`, `'brisa-tropical'`).

    Returns:
        DrinkRecipe | None: Receita encontrada com métricas calculadas ou `None` caso inexistente.
    """
    for d in get_catalog():
        if d.id == drink_id:
            return d
    return None
