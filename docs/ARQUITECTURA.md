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
│   ├── config.py        → ajustes y credenciales (leídos de ../infra/.env con pydantic-settings)
│   ├── db.py            → pool de conexiones a TimescaleDB (asyncpg) + chequeo de conexión
│   ├── modelos.py       → modelos de dominio (hoy: Tick). No sabe de exchanges ni de BD
│   ├── ingesta/
│   │   └── binance.py   → escucha el WebSocket de Binance y emite Ticks (paso 1.1)
│   └── main.py          → la app FastAPI; expone GET /health y GET /health/db
├── pyproject.toml       → dependencias (fastapi, uvicorn, asyncpg, pydantic-settings, websockets)
├── uv.lock              → lockfile de uv
└── .python-version      → fija Python 3.13 (NO usar el 3.14 del sistema: faltan wheels)
```

- Framework **async** (FastAPI + uvicorn).
- Aquí vivirán, por fases: la **ingesta** (WebSocket de Binance), la **persistencia** en TimescaleDB,
  los **detectores** de alertas (como plugins: agregar = enchufar), las **notificaciones** (Telegram)
  y la **IA** on-demand (Ollama).
- Estado actual: esqueleto conectado a la base de datos (paso 0.5).

**Cómo habla el backend con la base de datos** (decidido en el paso 0.5):

- **Driver: `asyncpg` puro**, sin ORM. Motivo: la ingesta de ticks de la Fase 1 es masiva
  (`copy_records_to_table` es lo más rápido que hay) y el SQL propio de TimescaleDB
  (hypertables, `time_bucket`) se escribe a mano igual, así que un ORM aportaba poco y agregaba
  una capa. Las tablas normales (alertas, config) llevan SQL a mano.
- **Pool de conexiones**: abrir una conexión a Postgres es caro, así que se mantienen varias
  abiertas y se van prestando. Vive en `db.py` como recurso global del proceso.
- **Ciclo de vida**: el pool se abre en el `lifespan` de FastAPI al arrancar y se cierra al parar.
  Si la BD no está disponible al arrancar, la API **igual levanta** y lo reporta en `/health/db`
  (no revienta el arranque).
- **Reconexión perezosa** (`asegurar_pool`): como Docker se enciende a mano, es normal levantar el
  backend antes que la base. Si no hay pool, el siguiente pedido intenta abrirlo — no hace falta
  reiniciar el backend. La variante estricta (`obtener_pool`, sin reintento) queda para el código
  caliente de la ingesta, que no debe pagar ese costo en cada tick.
- **Credenciales**: `config.py` lee el **mismo** `infra/.env` que usa docker-compose — una sola
  fuente de la contraseña, sin duplicarla. Las variables de entorno reales tienen prioridad sobre
  el archivo, así que cuando el backend corra dentro de Docker basta con pasarle `POSTGRES_HOST`.
- **Dos endpoints de salud, a propósito separados**: `/health` (¿vive la API?, no toca la BD) y
  `/health/db` (¿llega a la BD?, hace `SELECT 1` y devuelve 503 con mensaje claro si no).

**Cómo entra el dato del mercado** (decidido en el paso 1.1):

- **WebSocket, no sondeo**: la conexión queda abierta y es Binance quien empuja cada operación en el
  momento en que pasa. Preguntar cada X segundos llega tarde y gasta cuota.
- **Stream `aggTrade`, no `trade`**: una orden grande se ejecuta contra muchas órdenes chicas del libro
  y genera decenas de `trade` idénticos; `aggTrade` los junta en un evento. Mismo hecho económico, mucho
  menos ruido y menos filas que guardar. Los dos símbolos van por **una sola conexión** (stream combinado).
- **Precios en `Decimal`, nunca `float`**: Binance manda los precios como texto justamente para no perder
  precisión, y la regla de oro del proyecto es no deformar cifras. `0.1 + 0.2` en float da `0.30000000000000004`.
- **Tiempos en UTC con zona explícita**, tomados del reloj del exchange (campo `T`), no de cuándo llegó.
- **Frontera**: `ingesta/binance.py` solo escucha y traduce a `Tick`. No guarda ni decide alertas: le
  entrega cada tick a un consumidor que recibe por parámetro. Hoy ese consumidor imprime por consola;
  en 1.2 será el que escribe en TimescaleDB, y el módulo de ingesta no cambia.
- **Reconexión con espera creciente**: la reconexión automática de `websockets` no espera nada cuando el
  servidor cierra bien — reintentaría decenas de veces por segundo y Binance banea la IP a las 300
  conexiones en 5 minutos. Por eso se mide cuánto duró cada conexión: si fue corta, la espera se duplica
  (1→2→4…60 s); si aguantó más de un minuto, se considera sana y la espera se resetea.

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
