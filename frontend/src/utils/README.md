# 🧮 `src/utils/` — Formatação Monetária BRL, Sessão sem Atrito & Navegação SPA

Utilitários transversais puros e leves em [`format.ts`](./format.ts) usados por todas as páginas, componentes e pelo cliente HTTP da aplicação.

---

## 🎯 Problemas de Negócio Resolvidos Aqui

1. **Transparência Total no Preço por Mililitro (`formatPerMl`):**
   Em insumos de base como água tônica, refrigerante ou energético, `1 ml` custa menos de 10 centavos (ex.: `R$ 35,00` por litro = `R$ 0,035/ml`). Se formatássemos sempre com 2 casas decimais, o cliente veria um enganoso `R$ 0,04/ml`. A função `formatPerMl` detecta valores `< R$ 0,10` e ativa automaticamente **3 casas decimais** via `Intl.NumberFormat('pt-BR')`, transmitindo precisão e justiça comercial no construtor *"Monte por ml"*.
2. **Checkout Anônimo Persistente (`getOrCreateCustomerSessionId`):**
   Ninguém em uma festa quer preencher cadastro com CPF/e-mail/senha para comprar um Gin Tônica. Geramos localmente um ID `cust_<random><timestamp>` persistido no `localStorage` (`bartender_v3_customer_session`). Isso garante:
   - Retomada automática do pedido se o navegador recarregar ou voltar do app do banco;
   - Proteção contra terceiros mal-intencionados tentando cancelar ou liberar a bebida de outra senha na fila.
3. **Suporte Multi-Tenant "Impersonation" (`getInspectBarId` / `setInspectBarId`):**
   Permite que o Super-Admin inspecione qualquer bar cliente armazenando temporariamente o ID alvo (`bartender_v3_inspect_bar_id`), que é limpo automaticamente junto ao logout (`setStoredAuthToken(null)`).

---

## 🔧 Referência Rápida das Funções em [`format.ts`](./format.ts)

| Função | Assinatura | Descrição |
| :--- | :--- | :--- |
| `formatBrl` | `(cents: number) => string` | Converte centavos inteiros para Real Brasileiro (ex.: `1690` -> `"R$ 16,90"`). |
| `formatPerMl` | `(pricePerLiterCents: number) => string` | Divide centavos/L por `100_000` e formata em BRL com 2 ou 3 casas decimais conforme a grandeza. |
| `getOrCreateCustomerSessionId` | `() => string` | Retorna ou cria a chave anônima persistente do consumidor no `localStorage`. |
| `getStoredAuthToken` | `() => string \| null` | Lê o token JWT administrativo salvo localmente. |
| `setStoredAuthToken` | `(token: string \| null) => void` | Salva o JWT ou limpa simultaneamente `AUTH_TOKEN_KEY` + `INSPECT_BAR_KEY` no logout. |
| `getInspectBarId` | `() => string \| null` | Obtém o `bar_id` atualmente sob inspeção remota pelo Super-Admin. |
| `setInspectBarId` | `(barId: string \| null) => void` | Ativa ou encerra o modo de inspeção de um bar específico. |
| `navigateTo` | `(path: string) => void` | Executa `window.history.pushState` e despacha `PopStateEvent('popstate')` para troca instantânea de tela em `App.tsx`. |
