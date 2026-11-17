# 🍹 Interface Web & Totem Touch (`frontend/`)

Aplicação Single-Page (SPA) moderna construída em **React 19 + TypeScript 5.8 + Vite 6 + Tailwind CSS v4**, projetada com estética editorial **"Resort Tropical"** para máxima conversão, engajamento de público e ergonomia tátil em eventos.

---

## 💼 Argumentos de UX & Vendas Técnicas

Em feiras, casamentos e ativações corporativas, a interface digital **é a cara do produto**. Uma tela técnica demais intimida o convidado; uma tela lenta gera fila no bar. O frontend do **Bartender.OS v2.0** entrega diferenciais comerciais imediatos:

1. **Zero Atrito para Convidados (Sem Instalar App):**
   Basta tocar no tablet do totem ou apontar a câmera do celular para um QR Code com o IP local do bar (`http://192.168.x.x:8000`) — a aplicação abre em menos de `1 segundo` direto no navegador do iOS ou Android.
2. **Copo Vetorial Vivo em Tempo Real (Sem Fotos Estáticas):**
   Se o contratante do evento pedir para trocar *"Morango"* por *"Cranberry"* ou criar um drink nas cores da marca dele, **não é preciso fotografar novos drinks**: o motor vetorial SVG renderiza instantaneamente as camadas proporcionais, o brilho do vidro, o gelo e o jato líquido colorido.
3. **Sincronia Multi-Tela via WebSocket (`/api/ws`):**
   Quando um pedido começa, **todas as telas conectadas** (o tablet do balcão, o celular do convidado e uma eventual TV/telão HDMI atrás do bar) exibem simultaneamente a animação do preparo de `0%` a `100%`, criando um efeito vitrine que atrai curiosos ao estande.
4. **Bundle Ultraleve e 100% Autônomo:**
   Toda a arte botânica e dos copos é escrita em SVG puro inline, eliminando carregamento pesado de imagens externas e garantindo fluidez de `60 FPS` mesmo sem internet no local.

---

## 🛠️ Stack Tecnológica e Scripts (`package.json`)

| Tecnologia | Versão | Papel no Projeto |
| :--- | :---: | :--- |
| **React** | `^19.1.0` | Renderização declarativa reativa e hooks de estado/WebSocket. |
| **TypeScript** | `~5.8.3` | Verificação estática estrita (`tsc -b`) de todos os contratos da API. |
| **Vite** | `^6.3.5` | Bundler ultrarrápido + proxy reverso de desenvolvimento (`/api` e `ws`). |
| **Tailwind CSS** | `^4.1.7` | Estilização utilitária moderna compilada nativamente via `@tailwindcss/vite`. |
| **Lucide React** | `^0.511.0` | Ícones vetoriais nítidos para indicadores de Wi-Fi, USB, volume e segurança. |

### Comandos Disponíveis (dentro de `frontend/`)

```powershell
# 1. Instalar dependências Node.js
npm install

# 2. Modo Desenvolvimento com Hot-Reload em http://localhost:5173
#    (redireciona /api e WebSocket automaticamente para localhost:8000)
npm run dev

# 3. Validar TypeScript e gerar build otimizado de produção em frontend/dist/
npm run build

# 4. Pré-visualizar localmente o build estático gerado
npm run preview
```

---

## 📂 Estrutura de Pastas do Frontend

- **[`src/`](./src/README.md)** — Entrada da aplicação (`main.tsx`), orquestrador principal (`App.tsx`) e sistema visual (`index.css`).
  - **[`src/api/`](./src/api/README.md)** — Cliente HTTP REST tipado (`client.ts`).
  - **[`src/components/`](./src/components/README.md)** — Biblioteca dos 7 componentes visuais e interativos do bar.
  - **[`src/types/`](./src/types/README.md)** — Interfaces e tipos TypeScript (`bartender.ts`).
- **`index.html`** — Casca HTML5 em `pt-BR` com carregamento das famílias tipográficas *Fraunces* e *Plus Jakarta Sans*.
- **`vite.config.ts`** — Configuração de plugins e proxy HTTP + WebSocket para o FastAPI (`localhost:8000`).
- **`tsconfig.json`** — Regras estritas do compilador TypeScript.
