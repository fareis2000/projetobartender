"""Ponto de entrada unificado para iniciar o servidor FastAPI (Bartender Automático)."""
import sys
import uvicorn

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[Bartender v2.0] Iniciando servidor FastAPI + ESP32...")
    print("[Web App]        http://localhost:8000")
    print("[Docs API]       http://localhost:8000/docs")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
