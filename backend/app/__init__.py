"""Módulos da aplicação Bartender Automático.

Papel na Arquitetura:
---------------------
Agrupa o núcleo da aplicação backend (`backend/app`), estruturado em camadas claras e desacopladas:
  - `config.py`: Carregamento de variáveis de ambiente (`.env`) e resolução de diretórios do sistema.
  - `models.py`: Contratos de dados tipados e validações de segurança volumétrica via Pydantic v2.
  - `catalog.py`: Receitas de drinks, cálculo dinâmico de tempo/volume e persistência JSON das bombas.
  - `esp32_client.py`: Orquestrador assíncrono com controle de concorrência (`asyncio.Lock`) e
    fallback triplo automático (`Wi-Fi HTTP` -> `USB Serial` -> `Simulador Volumétrico`).
  - `main.py`: Servidor FastAPI com rotas REST, streaming em tempo real via WebSocket (`/api/ws`)
    e hospedagem integrada da SPA React compilada (`frontend/dist`).
"""
