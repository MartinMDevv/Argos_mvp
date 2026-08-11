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
Hoy (Fase 1 completa) el tramo Binance → backend → TimescaleDB → velas → WebSocket funciona de punta a
punta, y el **gráfico de velas del panel ya lo consume en vivo** (paso 2.1). Siguen en mock la
watchlist, la tabla de mercados y el sidebar → paso 2.2.

---

## 🧠 backend/ — Python + FastAPI (gestionado con `uv`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py        → ajustes y credenciales (leídos de ../infra/.env con pydantic-settings)
│   ├── db.py            → pool de conexiones a TimescaleDB (asyncpg) + chequeo de conexión
│   ├── esquema.py       → aplica los .sql de sql/ al arrancar (idempotente)
│   ├── estado.py        → EstadoMercado: último tick de cada símbolo, en memoria
│   ├── velas.py         → arma velas OHLCV con time_bucket de TimescaleDB (paso 1.3)
│   ├── difusion.py      → empuja el estado a los paneles conectados por WS (paso 1.4)
│   ├── modelos.py       → modelos de dominio (hoy: Tick). No sabe de exchanges ni de BD
│   ├── ingesta/
│   │   ├── binance.py   → escucha el WebSocket de Binance y emite Ticks (paso 1.1)
│   │   └── almacen.py   → EscritorDeTicks: junta ticks y los guarda por lotes (paso 1.2)
│   └── main.py          → la app FastAPI; endpoints + arranque de las tareas de fondo
├── sql/
│   └── 001_ticks.sql    → tabla `ticks` como hypertable + índices
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

**Dónde queda ese dato** (decidido en el paso 1.2):

Cada tick que entra va a **dos lugares distintos, con propósitos distintos**:

| Destino | Qué guarda | Para qué |
|---|---|---|
| `estado.py` (memoria) | El **ahora**: último tick de cada símbolo | Responder al instante "¿a cuánto está BTC?" |
| `ticks` en TimescaleDB (disco) | La **historia**: todas las operaciones | Tener con qué comparar y decidir si el ahora es raro |

- **Tabla `ticks` como hypertable**: por fuera es una tabla normal; por dentro Timescale la parte en
  trozos por rango de tiempo, así una consulta de "la última hora" toca un trozo y no millones de filas.
  **Sin `id SERIAL`**: en series temporales el eje es el tiempo, y una clave autonumérica sería un índice
  enorme que nunca se consulta.
- **`NUMERIC`, no `DOUBLE PRECISION`**: misma razón que el `Decimal` de la ingesta. asyncpg convierte
  `NUMERIC ↔ Decimal` solo, así que la precisión viaja intacta de Binance al disco.
- **Escritura por lotes** (`almacen.py`): se juntan ticks en memoria y se vuelcan cuando hay 200 o cuando
  pasan 2 segundos, lo que ocurra primero. Un viaje a la base en vez de doscientos.
- **`executemany` y no `copy_records_to_table`** — *esto corrige lo anotado en el paso 0.5*. COPY es más
  rápido pero **no admite `ON CONFLICT DO NOTHING`**, y la deduplicación no es negociable: al reconectar
  el WebSocket podemos recibir operaciones ya guardadas, y un tick contado dos veces le miente a los
  detectores de volumen. Con el volumen del MVP `executemany` sobra. Si crece (memecoins, muchos pares),
  la salida es COPY a tabla temporal + `INSERT ... SELECT ... ON CONFLICT DO NOTHING`.
- **Anti-duplicados en la base, no en el código**: índice único `(simbolo, id_operacion, momento)` +
  `ON CONFLICT DO NOTHING`. Incluye `momento` porque Timescale exige que todo índice único contenga la
  columna de particionado.
- **Si la base se cae, Argos no**: los ticks se acumulan en memoria y se reintentan solos cuando vuelve
  (reconexión perezosa del pool). La cola tiene tope (20.000): si la base no vuelve nunca, se descartan
  los ticks **más viejos** antes que agotar la RAM. El endpoint `/mercado/estado` muestra ese pulso
  (`guardados`, `en_espera`, `descartados`).
- **Esquema idempotente**: los `.sql` de `backend/sql/` se aplican enteros en cada arranque (`IF NOT
  EXISTS`). Alcanza mientras solo *creemos* cosas; el día que haya que *cambiar* algo ya creado, hará
  falta control de migraciones de verdad.

**Cómo se arman las velas** (decidido en el paso 1.3):

- **La agrupación la hace la base, no Python**: traerse 50.000 ticks por la red para tirar el 99% no
  tiene sentido. `velas.py` manda una consulta y recibe las velas ya calculadas.
- **`time_bucket()`** es el `GROUP BY` por tramos de tiempo de Timescale: tira cada tick al cajón que le
  toca. Postgres pelado obligaría a malabares con `date_trunc`, que además no sirve para tramos como 5m o 4h.
- **`first(precio, momento)` / `last(precio, momento)`**: dan el primer y último valor de un grupo *según
  otra columna* — exactamente la apertura y el cierre de una vela. En SQL estándar esto pide funciones de
  ventana; acá es una línea.
- **Intervalo parametrizado, no interpolado**: los tramos válidos son una lista cerrada (`INTERVALOS`) y el
  ancho viaja como parámetro `$1::interval`. El usuario nunca escribe algo que termine dentro de la consulta.
- **No se rellenan huecos**: si en un tramo no hubo operaciones, no hay vela. No se interpola ni se repite el
  precio anterior — si no hay dato, no hay dato. (Timescale tiene `time_bucket_gapfill` si algún día se
  quiere rellenar *para dibujar*, pero es una decisión de presentación, no del dato.)
- **Bandera `completa`**: la última vela siempre está formándose, y darla por cerrada haría creer que su
  mínimo ya está definido. Además se espera un `MARGEN_ASENTADO` de 5 s antes de declararla completa,
  porque el escritor vuelca de a lotes cada 2 s: justo al cerrar el minuto, sus últimos ticks pueden estar
  todavía en memoria. Sin ese margen la bandera mentiría en el borde.
- **Se calcula en cada consulta**. Simple y siempre al día. Cuando haya mucha historia y se pidan rangos
  largos, el reemplazo natural son las *continuous aggregates* de Timescale (velas pre-calculadas que se
  refrescan solas).
- **Argos solo tiene lo que vio**: no hay historia anterior al primer arranque y no se inventa. Traer
  historia vieja desde la API REST de Binance (backfill) es un paso posterior.

**Cómo llega el dato al panel** (decidido en el paso 1.4):

Hasta acá el panel tenía que *preguntar*. Con `WS /ws/mercado` se da vuelta: se conecta una vez y el
backend le **avisa**. Es el mismo trato que tenemos con Binance, un escalón más arriba.

- **No se manda cada tick.** Por lo mismo que elegimos `aggTrade`: bajo ruido. BTC y ETH generan decenas
  de operaciones por segundo y ni el ojo humano ni React sacan provecho de redibujar 40 veces por segundo.
  Se manda una foto cada 0,5 s **y solo si cambió algo** (medido: ~1,6 mensajes/s en vez de ~40).
- **Foto completa al conectarse** (`bienvenida`): sin eso el panel arrancaría en blanco hasta la primera
  novedad, y parecería que Argos no sabe nada cuando en realidad sí sabe.
- **Latido cada 15 s sin novedades**: una conexión muda es indistinguible de una muerta. El `latido` le
  dice al panel que Argos sigue mirando.
- **Envíos en paralelo** (`asyncio.gather`): si fueran secuenciales, un panel lento —una pestaña en
  segundo plano, una conexión mala— haría esperar a todos. Al que falla se lo da de baja en el momento.
- **Hay que seguir leyendo del socket** aunque el panel no mande nada: es la única forma de enterarse de
  que cerró. Sin ese `receive`, un panel que se fue quedaría en la lista para siempre.
- **Tipos de mensaje explícitos** (`bienvenida` / `estado` / `latido`): el cliente decide mirando `tipo`,
  sin adivinar por la forma del contenido.
- **CORS**: el navegador bloquea pedidos entre orígenes distintos, y el frontend vive en el 5173 mientras
  la API está en el 8000. Se autorizan solo los orígenes de desarrollo — nunca `"*"`, que abriría la API
  a cualquier página.

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
    │   └── coins.ts         → datos mock BTC/ETH (los usan aún watchlist/tabla/sidebar → paso 2.2)
    ├── lib/
    │   ├── api.ts           → puente REST: URL del backend, tipos de la API, obtenerVelas() (2.1)
    │   ├── mercado.tsx      → ProveedorMercado: LA conexión WebSocket + hooks para leerla (2.1)
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
        ├── CandleChart.tsx     → gráfico de velas con lightweight-charts y DATOS REALES (2.1)
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
- El **gráfico ya usa datos reales** (2.1). Siguen en mock la watchlist, la tabla y el sidebar → paso 2.2.
- ⚠️ El **logo del pavo real** (`Peacock.tsx`) es un placeholder dibujado en SVG a mano →
  reemplazar por un vector pulido cuando esté.

**Cómo llegan los datos al gráfico** (decidido en el paso 2.1):

- **Dos fuentes, cada una en lo que es buena.** REST (`/mercado/velas`) da la **historia y la verdad**:
  la base agrupa los ticks y devuelve máximo, mínimo y volumen exactos. El WebSocket (`/ws/mercado`) da
  el **ahora**: el último precio, cada 0,5 s. El WebSocket no manda velas, manda precios sueltos, así
  que la vela en curso se arma en el navegador.
- **Y aun así se le sigue preguntando a la base.** La foto del WebSocket viaja cada 0,5 s y solo si
  cambió algo: entre dos fotos puede haber habido un pico que no vimos. Quedarnos solo con eso daría
  "el máximo de lo que alcanzamos a mirar", que no es el máximo real. Cada `RECONCILIACION_MS` (10 s) se
  vuelven a pedir las últimas velas y se corrige. La vela en curso es la **unión** de las dos fuentes:
  de la base lo que ya aterrizó en disco, del WebSocket los últimos segundos que aún no llegaron —
  el máximo y el mínimo se toman con `Math.max`/`Math.min`, así ninguna fuente puede achicar a la otra.
- **UNA sola conexión para toda la app.** `ProveedorMercado` va en `main.tsx`, arriba de `<App/>`. Si cada
  componente abriera su socket habría uno por gráfico, otro por tabla, y todos se caerían al cambiar de
  vista (React desmonta lo que deja de mostrar).
- **Reconexión con espera creciente, igual que con Binance** (paso 1.1): 1 s → 2 s → … → 30 s, y la espera
  se resetea si la conexión duró más de un minuto. La lección se repite un escalón más abajo.
- **Los precios viajan como texto y se convierten a número lo más tarde posible**, solo al dibujar. El
  `Number()` vive en una función (`aVela`) y en ningún otro lado: el string sigue siendo la fuente de verdad.
- **El bucket se calcula igual que en la base**: `Math.floor(momento / ancho) * ancho`. Es lo mismo que hace
  `time_bucket()` (ambos alinean contra el epoch), y por eso las velas de las dos fuentes caen siempre en
  el mismo casillero.
- **Se guarda y se devuelve el encuadre** al reconciliar (`getVisibleLogicalRange` / `setVisibleLogicalRange`):
  sin eso, cada corrección le arrebataría el zoom al usuario cada 10 segundos.
- **Si no hay datos, se dice.** Cargando, sin conexión, o "Argos todavía no vio operaciones de X" — nunca un
  precio en cero, que en un gráfico se vería como un desplome que no ocurrió.
- **Las velas viven en un `ref`, no en estado**: cambian varias veces por segundo y no queremos un render de
  React por cada una — el gráfico se actualiza solo, por su propia API. Lo único que va a estado es *si hay
  o no hay* velas, porque eso sí decide qué se muestra.

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
