"""Pacote principal da API FastAPI do Bartender Automático.

Papel na Arquitetura:
---------------------
Marca o diretório `backend/` como um pacote Python importável a partir da raiz do projeto
(`backend.app.main:app`), permitindo que o inicializador unificado `server.py` e o servidor
ASGI Uvicorn localizem os submódulos de negócio, persistência JSON e controle de hardware ESP32.
"""
