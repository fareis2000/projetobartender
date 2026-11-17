# 🌐 Camada Cliente da API REST (`frontend/src/api/`)

Encapsulamento limpo, tipado e livre de bibliotecas externas pesadas (usa `fetch` nativo moderno) para toda a comunicação HTTP entre o navegador/totem e o servidor **FastAPI**.

---

## 💼 Benefícios Técnicos e de Operação em Rede Local

1. **Portabilidade Total de Rede (Zero IP Hardcoded no Frontend):**
   Todas as requisições em `client.ts` utilizam **caminhos relativos** (`/api/...`). Isso significa que o mesmo build compilado funciona sem nenhuma modificação em:
   - `http://localhost:8000` (totem local na própria máquina Windows/Linux);
   - `http://192.168.1.10:8000` (celulares de convidados conectados no Wi-Fi do evento);
   - `http://192.168.4.1` / redes isoladas de feiras;
   - `https://meu-bar.dominio.com` (caso exposto via túnel HTTPS seguro com proxy reverso).
2. **Mensagens de Erro Humanizadas para o Público:**
   O helper `requestJson<T>()` intercepta respostas não-OK (`404`, `409 Conflict`, `422 Unprocessable Entity`, `503 Service Unavailable`), extrai automaticamente o campo `detail` retornado pelo FastAPI/Pydantic e entrega mensagens claras em português no banner superior (ex.: *"Já existe um drink sendo preparado no momento."*), junto com um botão direto **"Ajustar Conexão"**.

---

## 📄 Arquivo: `client.ts`

Exporta o objeto singleton **`bartenderApi`** com 8 métodos assíncronos fortemente tipados:

| Método TypeScript | Endpoint HTTP | Retorno (`Promise<T>`) | Uso na Interface |
| :--- | :--- | :--- | :--- |
| `getDrinks()` | `GET /api/drinks` | `DrinkRecipe[]` | Carrega o cardápio com `total_ml` e `estimated_seconds` atualizados. |
| `getPumps()` | `GET /api/pumps` | `PumpConfig[]` | Carrega nomes das garrafas, cores hexadecimais, GPIOs e vazões (`ml/s`). |
| `updatePump(id, payload)` | `PUT /api/pumps/{id}` | `PumpConfig` | Salva troca de ingrediente ou nova calibração de vazão no painel ⚙️. |
| `getStatus(probe?)` | `GET /api/status` | `SystemSnapshot` | Sincroniza estado inicial da tela (`probe=true` força checagem física). |
| `getConnection()` | `GET /api/connection` | `HardwareHealth` | Botão **"Testar Agora"** da gaveta de diagnóstico do ESP32. |
| `updateConnection(cfg)` | `PUT /api/connection` | `HardwareHealth` | Alterna entre `auto`, `wifi`, `serial` e `simulator` ou muda IP/COM. |
| `dispensePreset(drinkId)` | `POST /api/dispense/{id}` | `PreparationStatus` | Inicia o preparo de um drink clássico ou especial do cardápio. |
| `dispenseCustom(payload)` | `POST /api/dispense/custom` | `PreparationStatus` | Envia a criação personalizada do estúdio *"Monte seu Drink"*. |
| `emergencyStop()` | `POST /api/stop` | `PreparationStatus` | Aciona o botão vermelho de **Parada de Emergência** desligando as bombas. |
