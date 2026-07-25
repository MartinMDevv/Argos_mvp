# ARQUITECTURA — cómo está distribuido Argos

> Mapa del repo: qué carpeta hace qué y cómo se conectan. Para *correrlo*, ver
> [`./COMO_CORRER.md`](./COMO_CORRER.md). Reglas y contexto: [`./AGENTS.md`](./AGENTS.md).

Argos es un **monolito modular**: tres patas con fronteras limpias (backend, frontend, infra)
más la documentación. Cada pata se levanta por separado y se comunican por HTTP/WebSocket.

```
Argos_MVP/
├── backend/      → El cerebro: Python + FastAPI (ingesta, BD, detectores, IA, notificaciones)
├── frontend/     → El panel: React + TypeScript + Vite (el dashboard que ves)
├── infra/        → Docker Compose: la base de datos TimescaleDB
├── docs/         → Documentación viva (este archivo, AGENTS, CHECKLIST, guías)
└── README.md     → Presentación del repo
```

El **flujo de datos** (cuando esté todo conectado): un exchange (Binance) → el **backend** ingiere
y guarda en **TimescaleDB** (infra) → los **detectores** miran esos datos y generan alertas → el
**frontend** consume la API/WebSocket y muestra todo → la **IA local** (Ollama) explica en palabras.
Hoy (Fase 0) las patas están montadas pero aún no conectadas entre sí.

---

## 🧠 backend/ — Python + FastAPI (gestionado con `uv`)

```
backend/
├── app/
│   ├── __init__.py
│   └── main.py          → la app FastAPI; hoy solo expone GET /health
├── pyproject.toml       → dependencias (fastapi, uvicorn)
├── uv.lock              → lockfile de uv
└── .python-version      → fija Python 3.13 (NO usar el 3.14 del sistema: faltan wheels)
```

- Framework **async** (FastAPI + uvicorn).
- Aquí vivirán, por fases: la **ingesta** (WebSocket de Binance), la **persistencia** en TimescaleDB,
  los **detectores** de alertas (como plugins: agregar = enchufar), las **notificaciones** (Telegram)
  y la **IA** on-demand (Ollama).
- Estado actual: esqueleto con `/health` que responde `{"status":"ok"}`.

## 🖥️ frontend/ — React 19 + Vite + Tailwind v4 (TypeScript)

El panel, con la piel de Argos (consola de inteligencia, paleta "pavo real" teal + oro, estilo Linear).

```
frontend/
├── index.html               → arranque; fija lang="es" y data-theme="dark"
├── vite.config.ts           → plugins React + Tailwind v4; alias "@" → src
├── tsconfig.*.json          → TypeScript (paths del alias "@")
└── src/
    ├── main.tsx             → monta <App/> en #root
    ├── App.tsx              → estado global: vista, chat abierto, activos fijados, tema
    ├── index.css            → SISTEMA DE DISEÑO: tokens (ambos temas), @font-face, estilos de componentes
    ├── data/
    │   └── coins.ts         → datos mock BTC/ETH + serie de velas (luego vienen del backend)
    ├── lib/
    │   └── useTheme.ts      → hook de tema claro/oscuro (escribe data-theme en <html>)
    ├── assets/fonts/        → Adwaita Sans + JetBrains Mono (subseteadas, .woff2)
    └── components/
        ├── Sidebar.tsx         → nav: secciones, "Fijados", cuenta, tema, "Vigilando"
        ├── MarketHeader.tsx    → cabecera del activo: logo + par + precio + timeframe + botón Chat
        ├── PanelView.tsx       → vista Panel (estado + gráfico + favoritos + "Lo que Argos vio")
        ├── MercadosView.tsx    → vista Mercados (KPIs + precio/volumen + tabla)
        ├── ChatIsland.tsx      → chat con Argos (isla a la derecha, estado vacío + demo)
        ├── Watchlist.tsx       → favoritos con logo, sparkline y pin
        ├── PulseCard.tsx       → StatusBar (banner + radar) y PulseCard ("Lo que Argos vio")
        ├── MarketTable.tsx     → tabla densa de activos vigilados
        ├── CandleChart.tsx     → gráfico de velas en canvas + crosshair
        ├── PriceVolChart.tsx   → precio (área) + histograma de volumen en canvas
        ├── Peacock.tsx         → logo pavo real (SVG generado; PLACEHOLDER)
        ├── CoinLogo.tsx        → logos oficiales BTC/ETH
        ├── Icon.tsx            → íconos de línea reutilizables
        ├── Pin.tsx             → botón de fijar (favorito)
        └── illustrations/
            ├── Radar.tsx       → ilustración isométrica "radar" (los cien ojos)
            └── IsoLayers.tsx   → ilustración isométrica "capas" (historia/hypertable)
```

**Sistema de diseño** (todo en `src/index.css`):
- **Tokens** como variables CSS (`--ground`, `--surface`, `--teal`, `--gold`, `--bull`, `--bear`…) con
  variantes para tema **oscuro** (por defecto) y **claro**. Los componentes usan `var(--…)`.
- **Fuentes** propias vía `@font-face` apuntando a los `.woff2` subseteados: **Adwaita Sans** (UI) y
  **JetBrains Mono** (números, tabulares).
- Tailwind v4 está instalado y disponible para utilidades; el look afinado vive como CSS de componentes.

**Convenciones del frontend:**
- Import con alias `@` → `src` (ej. `import { COINS } from '@/data/coins'`).
- Comentarios en español.
- Los datos son **mock** por ahora; el contrato con el backend se define en Fase 1–2.
- ⚠️ El **logo del pavo real** (`Peacock.tsx`) es un placeholder dibujado en SVG a mano →
  reemplazar por un vector pulido cuando esté.

## 🗄️ infra/ — Docker Compose (TimescaleDB)

```
infra/
├── docker-compose.yml   → servicio "timescaledb" (Postgres 16 + TimescaleDB), volumen persistente
├── .env.example         → plantilla de variables (copiar a .env)
└── .env                 → credenciales locales (NO sube a git)
```

- Imagen `timescale/timescaledb:latest-pg16`, contenedor `argos_timescaledb`, puerto **5432**.
- Datos persistentes en el volumen `argos_pgdata`.
- Docker se controla **manual** (alias `docker-on` / `docker-off`); no autoarranca con el sistema.

## 📚 docs/

| Archivo | Qué es |
|---|---|
| `AGENTS.md` | Contexto y guardarraíles (punto de entrada) |
| `CHECKLIST.md` | Pasos tildables del MVP + estado |
| `ARQUITECTURA.md` | Este archivo: distribución del repo |
| `COMO_CORRER.md` | Guía para levantar cada pata |

---

*El motor del MVP se reutiliza en cada fase, no se reescribe. La arquitectura deja espacio para
crecer (multiusuario, más activos, on-chain) sin romper lo hecho.*
