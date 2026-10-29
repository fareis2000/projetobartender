"""Ponto de entrada unificado para iniciar o servidor FastAPI (Bartender Automático)."""
import uvicorn

if __name__ == "__main__":
    print("🚀 Iniciando Bartender Automático v2.0 (FastAPI + ESP32)")
    print("🌐 Acesse: http://localhost:8000  |  Documentação API: http://localhost:8000/docs")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
