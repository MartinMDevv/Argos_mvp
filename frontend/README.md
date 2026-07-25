# Argos · frontend 🦚

El panel de Argos: **React 19 + TypeScript + Vite + Tailwind v4**.
Consola de inteligencia de mercado cripto (BTC/ETH), con la piel del boceto: paleta "pavo real"
(teal + oro), tipografía Adwaita Sans + JetBrains Mono, estilo Linear.

## Correr

```bash
npm install     # (solo la 1ª vez)
npm run dev     # http://localhost:5173
```

Otros: `npm run build` (typecheck + bundle) · `npm run preview` (probar el build).

## Cómo está organizado

- `src/index.css` → **sistema de diseño**: tokens (tema oscuro/claro), `@font-face`, estilos de componentes.
- `src/App.tsx` → estado global (vista Panel/Mercados, chat, activos fijados, tema).
- `src/data/coins.ts` → datos **mock** de BTC/ETH (se reemplazan por datos reales del backend en Fase 1–2).
- `src/lib/useTheme.ts` → hook de tema claro/oscuro.
- `src/components/` → piezas de UI (Sidebar, MarketHeader, PanelView, MercadosView, ChatIsland, gráficos, etc.).
- `src/assets/fonts/` → fuentes subseteadas (`.woff2`).

Mapa completo de componentes y del sistema de diseño: [`../docs/ARQUITECTURA.md`](../docs/ARQUITECTURA.md).

## Convenciones

- Imports con alias **`@` → `src`** (ej. `import { COINS } from '@/data/coins'`).
- Comentarios en español.
- ⚠️ El logo del pavo real (`components/Peacock.tsx`) es un **placeholder** dibujado en SVG →
  reemplazar por un vector pulido cuando esté.
