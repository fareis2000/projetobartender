# 📐 `src/types/` — Contratos TypeScript & Máquina de Estados de Domínio

Centraliza todas as interfaces e tipos estritos (`strict: true`) do frontend em [`bartender.ts`](./bartender.ts), espelhando **1:1** os modelos Pydantic do backend FastAPI.

---

## 🛡️ Por Que Tipagem Estrita Importa Comercialmente Aqui

Em um sistema que movimenta **pagamentos reais via Pix** e **aciona bombas físicas de líquidos**, ambiguidades de tipo causam prejuízo financeiro direto ou derramamento no balcão. Por isso:
1. **Todos os valores monetários trafegam em centavos inteiros (`*_cents`):** Evita divergências de arredondamento IEEE-754 entre o valor exibido no celular e o QR Code EMV gerado no Banco Central.
2. **Identificação física determinística (`PumpId`):** Restringe em tempo de compilação qualquer referência de bomba ao conjunto literal `'amarelo' | 'vermelho' | 'verde' | 'azul'`.
3. **Máquina de Estados Explícita (`OrderStatus`):** Garante que a UI trate todos os cenários operacionais reais de um bar movimentado (fila, pausa de vez, confirmação de copo, falha física e estorno).

---

## 🔄 Diagrama da Máquina de Estados do Pedido (`OrderStatus`)

```mermaid
stateDiagram-v2
    [*] --> PENDING_PAYMENT: Cliente pede Preset ou Custom ml
    PENDING_PAYMENT --> CANCELED: Cliente cancela
    PENDING_PAYMENT --> EXPIRED: Timeout do QR Code Pix
    PENDING_PAYMENT --> PAID_QUEUED: Pix confirmado (maquina ocupada)
    PENDING_PAYMENT --> READY_FOR_CUP: Pix confirmado (maquina livre)

    PAID_QUEUED --> READY_FOR_CUP: Chegou a vez na fila
    READY_FOR_CUP --> PAUSED_TURN: Cliente demorou (nao trava a fila!)
    PAUSED_TURN --> PAID_QUEUED: Cliente tocou Retomar Vez
    PAUSED_TURN --> READY_FOR_CUP: Retomou com maquina livre

    READY_FOR_CUP --> DISPENSING: Checkbox Copo Posicionado confirmado
    DISPENSING --> COMPLETED: 100% dos ml servidos
    DISPENSING --> FAILED_DISPENSE: Parada emergencia / erro hardware
    FAILED_DISPENSE --> PAID_QUEUED: Dono clicou Reenviar a Fila

    PAID_QUEUED --> REFUNDED: Estorno Pix pelo Bar
    READY_FOR_CUP --> REFUNDED: Estorno Pix pelo Bar
    PAUSED_TURN --> REFUNDED: Estorno Pix pelo Bar
    FAILED_DISPENSE --> REFUNDED: Estorno Pix pelo Bar
    COMPLETED --> REFUNDED: Estorno comercial pos-venda
```

---

## 📚 Grupos de Interfaces em [`bartender.ts`](./bartender.ts)

| Domínio | Principais Tipos & Interfaces | Papel no Ecossistema |
| :--- | :--- | :--- |
| **Autenticação & RBAC** | `PrincipalUser`, `AuthTokenResponse` | Separa permissões entre `'bar_owner'` (escopo de 1 bar) e `'superadmin'` (escopo multi-tenant global). |
| **Insumos & Precificação** | `Bottle`, `BottlePayload`, `DrinkPricingMode` | Modela perda técnica de mangueira (`loss_pct`), preço base por litro (`price_per_liter_cents`) e lucro estimado por garrafa. |
| **Engenharia de Cardápio** | `DoseStep`, `DrinkRecipe`, `DrinkPayload` | Sequência de bombas + `ml` + `pause_ms`, CMV por copo, margem estimada e disponibilidade automática por estoque. |
| **Hardware & IoT** | `ConnectionMode`, `PrepState`, `PumpSlot`, `PreparationStatus`, `HardwareHealth`, `Machine` | Conecta parâmetros de GPIO, vazão (`flow_rate_ml_s`), conectividade Cloud IoT / LAN / USB Serial e barra de progresso ao vivo. |
| **Checkout Pix & Fila** | `PaymentProvider`, `OrderStatus`, `OrderItemBreakdown`, `Order` | Controla `pix_qr_code` (Copia e Cola), `pix_qr_base64`, posição na fila, contadores regressivos e Split (`platform_fee_cents` vs `bar_net_cents`). |
| **Tempo Real & Contexto** | `MachinePublicContext`, `MachineRealtimeSnapshot`, `PublicMachineSummary` | Payloads otimizados para abertura rápida do QR Code e streaming WebSocket de baixa latência. |
| **Gestão B2B & SaaS** | `BarSettings`, `BarAnalytics`, `BarSummary`, `PlatformOverview` | Suporta DRE em tempo real do bar, configuração segura Mercado Pago e governança financeira da rede inteira. |
