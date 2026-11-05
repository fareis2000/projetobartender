# 🍹 Bartender.OS v3.0 — Plataforma Comercial Multi-Bares, Pix & CRUD (`R$/ml`)

> **Isolamento de Branch:** Esta pasta (`projetobartender-v3`) opera na branch dedicada **`v3-saas-pagamentos`** (porta `8010`), mantendo a versão Alpha do evento (`projetobartender`, branch `v2-esp32`, porta `8000`) **100% congelada e independente**.

Plataforma completa de autosserviço de drinks com **QR Code exclusivo por máquina**, **pagamento Pix direto no celular do cliente** (Mercado Pago Oficial + Modo Pix Simulado para testes), **fila virtual inteligente com confirmação obrigatória de copo na plataforma**, e **CRUD completo para múltiplos bares** gerenciarem **garrafas (`R$/ml`)** e **receitas do cardápio**.

---

## ✨ Como Funciona na Prática

1. **Cliente escaneia o QR Code da Máquina (`/m/maq-01`) usando o próprio 4G/5G:**
   - Sem precisar conectar no Wi-Fi do bar e sem totem/maquininha física.
   - A tela sincroniza automaticamente com os ingredientes, preços por `ml` e nível de estoque real daquela máquina específica.
2. **Pagamento Pix Mobile (`Copia e Cola` + QR Code):**
   - O cliente escolhe um drink pronto ou monta sua combinação em `ml` vendo o preço subir em tempo real.
   - Clica em **Pagar com Pix**, copia o código em 1 toque, paga no app do banco e retorna para a tela (reconexão instantânea via `visibilitychange` + WebSocket).
3. **Fila Inteligente + Pergunta Obrigatória do Copo:**
   - Vários clientes podem pagar ao mesmo tempo sem travar vendas.
   - Na vez do cliente, o celular vibra e exige a confirmação explícita: **"Seu copo já está posicionado na plataforma?"** antes de liberar o acionamento das bombas.
   - Se o cliente demorar mais de 75s longe da máquina, a vez dele entra em *espera protegida* (sem perder o pagamento!) para a fila continuar andando.
4. **Painel do Dono do Bar (`/painel`) — CRUD Real Completo:**
   - **CRUD de Garrafas (`Criar, Editar, Excluir`):** Precifique pela dose de `50 ml`, pelo faturamento total da garrafa ou por multiplicador de *markup* (`2x`, `3x`, `4x`) — o sistema calcula o `R$/ml` e o lucro líquido automaticamente.
   - **CRUD de Drinks (`Criar, Editar, Pausar, Excluir`):** Liberdade total para excluir drinks padrão e criar receitas próprias com preço automático pelos `ml` ou preço fixo manual.
   - **Máquinas, 4 Bombas & Estoque Vivo:** Escolha qual garrafa do CRUD está espetada em cada bomba, acompanhe quantos `ml` restam (travando vendas automaticamente antes de acabar!) e baixe o **QR Code em SVG** pronto para impressão.
   - **Recebimento Pix / Mercado Pago:** Alterne entre *Modo Pix Simulado* e *Mercado Pago Oficial* colando o `Access Token` do próprio bar (com suporte opcional a `%` de Split para a plataforma).
5. **Painel Super-Admin Multi-Bares (`/superadmin`):**
   - Cadastre novos bares clientes, defina a `%` de Split/Comissão da plataforma, gere a primeira máquina de cada bar vendido e acompanhe o volume transacionado.

---

## 🚀 Como Iniciar (1 Clique ou Terminal)

Dê dois cliques em **`iniciar_bartender.bat`** dentro de `projetobartender-v3/` ou execute no PowerShell:

```powershell
.\.venv\Scripts\python.exe server.py
```

### Acessos Rápidos Locais (Porta `8010`):
| Área | URL | Credenciais Padrão (Demo) |
| :--- | :--- | :--- |
| **Visão do Cliente (QR Máquina #01)** | `http://localhost:8010/m/maq-01` | Livre (Autosserviço) |
| **Painel do Dono do Bar (CRUD)** | `http://localhost:8010/painel` | `dono@bartropical.com` / `bar123` |
| **Painel Super-Admin (Multi-Bares)** | `http://localhost:8010/superadmin` | `superadmin@bartender.os` / `admin123` |
| **Swagger / Documentação da API** | `http://localhost:8010/docs` | — |

---

## 🔌 Conexão da Máquina no Wi-Fi Local do Bar (`bombas/bombas.ino`)

O firmware híbrido (`ESP8266 NodeMCU` e `ESP32-WROOM-32`) conecta apenas no **Wi-Fi 2.4 GHz local do bar** e sincroniza automaticamente com o servidor (`SECRET_CLOUD_SYNC_URL`) a cada `450ms–800ms`:
1. No `/painel` → aba **Máquinas, Bombas & QR Code**, abra *"Ver credenciais Wi-Fi IoT"*.
2. Copie `SECRET_API_TOKEN` e `SECRET_CLOUD_SYNC_URL` para `bombas/secrets.h` junto com o Wi-Fi do bar e grave na placa.
3. Pronto: nenhum computador precisa ficar ligado dentro do bar!
