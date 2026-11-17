# 📐 Contratos e Tipagem Estática (`frontend/src/types/`)

Definições centrais em **TypeScript estrito** (`bartender.ts`) que espelham 1 para 1 os modelos **Pydantic v2** do backend Python (`backend/app/models.py`).

---

## 💼 Por Que Contratos Espelhados Importam na Engenharia do Produto?

Em sistemas que comandam atuadores físicos (motores e válvulas de líquidos), um simples erro de digitação em um campo JSON (ex.: enviar `amarela` em vez de `amarelo`, ou confundir `progress` em string com número) poderia causar falhas silenciosas no meio de um evento.

Ao centralizar todos os tipos em `bartender.ts` e validar o build com `tsc -b`:
- **Zero Erros de Integração em Tempo de Execução:** Qualquer mudança futura em um modelo ou rota é acusada imediatamente durante a compilação antes de chegar à bancada.
- **Autocompletar Inteligente & Manutenção Rápida:** Novos desenvolvedores ou integradores de sistemas de pagamento/PDV enxergam instantaneamente todas as propriedades disponíveis em cada payload REST e evento WebSocket.

---

## 📄 Resumo dos Tipos e Interfaces (`bartender.ts`)

### Tipos Literais (Unions Seguras)
| Tipo | Valores Permitidos | Equivalente no Backend (`models.py`) |
| :--- | :--- | :--- |
| **`PumpId`** | `'amarelo' \| 'vermelho' \| 'verde' \| 'azul'` | `PumpId` (chaves físicas do `bombas.ino`) |
| **`ConnectionMode`** | `'auto' \| 'wifi' \| 'serial' \| 'simulator'` | `ConnectionMode` |
| **`PrepState`** | `'idle' \| 'dispensing' \| 'completed' \| 'stopped' \| 'error'` | `PrepState` |

### Interfaces Principais de Domínio e Telemetria
| Interface | Finalidade |
| :--- | :--- |
| **`PumpConfig`** | Metadados completos de uma bomba física: `id`, `label`, `ingredient`, `description`, pino `gpio`, vazão calibrada `flow_rate_ml_s`, cor `color_hex` e flag `is_mixer`. |
| **`DoseStep`** | Etapa atômica de uma receita contendo `pump`, volume `ml` e intervalo pós-bomba `pause_ms`. |
| **`DrinkRecipe`** | Receita completa do cardápio enriquecida pelo backend com `total_ml` e `estimated_seconds`. |
| **`CustomDrinkPayload`** | Corpo enviado ao disparar uma bebida autoral (`name` + mililitros das 4 bombas). |
| **`PreparationStatus`** | Estado em tempo real do preparo (`progress` de `0` a `100`, `current_pump`, `elapsed_seconds`, `total_seconds`, `transport` e `message`). |
| **`HardwareHealth`** | Diagnóstico físico do ESP32 (`active_transport`, `wifi_reachable`, `wifi_ip`, `wifi_rssi`, `available_serial_ports` e `detail`). |
| **`SystemSnapshot`** | Envelope raiz transmitido em cada frame do WebSocket `/api/ws`, unindo `status` + `hardware`. |
| **`ConnectionConfigPayload`** | Dados persistidos ao atualizar o modo ou endereço de conexão no painel administrativo. |
