# Bartender Automático v2.0 · ESP32 Edition

Sistema profissional de coquetelaria automatizada com dosagem volumétrica controlada por **ESP32-WROOM-32**, backend assíncrono em **FastAPI (Python)** e interface web moderna em **React + Vite + TypeScript + Tailwind CSS**.

---

## Arquitetura do Sistema

- **`frontend/`** — Interface web responsiva (React 19, Vite, TypeScript, Tailwind CSS v4, Lucide Icons):
  - **Cardápio de Drinks**: Receitas clássicas e autorais com visualização em camadas do copo, proporções exatas em `ml` e tempo estimado.
  - **Estúdio "Monte seu Drink"**: Criação de receitas personalizadas ao mililitro nas 4 bombas, com preview dinâmico do copo e trava de segurança contra transbordamento (`450 ml`).
  - **Telemetria em Tempo Real (WebSocket)**: Barra de progresso ao vivo e botão de **Parada de Emergência**.
  - **Painel de Hardware & Calibração**: Configuração de IP/mDNS do ESP32, porta USB Serial, bebidas instaladas e vazão (`ml/s`) de cada bomba.
- **`backend/`** — Servidor **FastAPI** assíncrono:
  - Comunicação híbrida automática: **Wi-Fi HTTP JSON (`bartender.local`)** → **Fallback USB Serial (`115200` baud)** → **Modo Simulador em Tempo Real**.
  - Streaming de progresso via WebSocket (`/api/ws`) e documentação interativa Swagger em `/docs`.
- **`bombas/bombas.ino`** — Firmware adaptado para **ESP32-WROOM-32 (DevKit V1 30/38 pinos)**:
  - Máquina de estados 100% **não-bloqueante (`millis()`)** — aceita `/status` e `/stop` instantaneamente durante o preparo.
  - Servidor HTTP nativo na porta `80` + mDNS (`http://bartender.local`) + suporte simultâneo via USB Serial.
  - Persistência de calibração das vazões (`ml/s`) na memória Flash interna (`Preferences` / NVS).
- **`esquema/`** — Arquivos de esquema elétrico do projeto (KiCad 9 e Fritzing).

---

## Mapeamento de Pinos (Arduino UNO → ESP32-WROOM-32)

> **Importante:** Nos módulos **ESP32-WROOM-32**, os pinos **GPIO 6 a 11** são ligados internamente à memória SPI Flash e **não podem ser usados** (causam *bootloop* imediato). O pino **GPIO 3** é o `RX0` da USB Serial. Por isso, o pinout foi migrado para GPIOs 100% seguros e livres de pulsos espúrios no boot:

| Função / Atuador | Pino Antigo (Arduino UNO) | Novo Pino (ESP32-WROOM-32) | Vazão Padrão |
| :--- | :---: | :---: | :---: |
| **Bomba 1 · Amarela** (Relé IN1) | D2 | **GPIO 16** | `30.5 ml/s` |
| **Bomba 2 · Vermelha** (Relé IN2) | D3 | **GPIO 17** | `32.3 ml/s` |
| **Bomba 3 · Verde** (Relé IN3) | D4 | **GPIO 18** | `32.3 ml/s` |
| **Bomba 4 · Azul / Base** (Relé IN4) | D5 | **GPIO 19** | `35.9 ml/s` |
| **LED Antena / Status** | D6 | **GPIO 21** | — |
| **Buzzer Passivo (Melodia)** | D7 | **GPIO 22** | — |
| **Comunicação Sem Fio** | HC-05 (D12/D13) | **Wi-Fi Nativo ESP32** | — |

### Notas Elétricas (3.3V do ESP32)
1. **Módulo Relé Óptico de 4 Canais (Ativo em LOW)**: Mantenha `RELE_ATIVO_EM_LOW = true` em `bombas/bombas.ino`. Alimente o `JD-VCC` do módulo relé com `5V` e compartilhe o `GND`.
2. **Driver ULN2803A** (presente em `esquema/esquema.kicad_sch`): Funciona diretamente com lógica `3.3V` na entrada e chaveia `12V` na saída! Caso utilize o `ULN2803A` sem inversão, basta alterar `RELE_ATIVO_EM_LOW = false` no topo de `bombas/bombas.ino`.

---

## Como Executar o Projeto

### 1. Gravar o Firmware no ESP32
1. Abra `bombas/bombas.ino` na **Arduino IDE** (com o pacote oficial **esp32 by Espressif Systems** instalado).
2. Edite `WIFI_SSID` e `WIFI_PASSWORD` no topo do arquivo (caso não conecte em 10s, o ESP32 cria automaticamente a rede Wi-Fi `Bartender-ESP32`, senha `12345678`, IP `192.168.4.1`).
3. Selecione a placa **ESP32 Dev Module** e faça o upload (`115200` baud).

### 2. Rodar o Servidor Completo (Produção / Uso Direto)
Na pasta `projetobartender/`:
```powershell
.\.venv\Scripts\python server.py
```
Acesse **`http://localhost:8000`** no navegador (ou pelo celular na mesma rede Wi-Fi usando o IP do seu PC!).

### 3. Modo Desenvolvimento (Hot-Reload no Frontend)
Em dois terminais dentro de `projetobartender/`:

**Terminal 1 (Backend FastAPI na porta 8000):**
```powershell
.\.venv\Scripts\python server.py
```

**Terminal 2 (Frontend Vite na porta 5173):**
```powershell
cd frontend
npm run dev
```
Acesse **`http://localhost:5173`**.

