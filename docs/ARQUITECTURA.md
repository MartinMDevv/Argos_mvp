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
│   ├── velas.py         → arma velas OHLCV; fusiona ticks propios + historia (pasos 1.3 y 2.1b)
│   ├── resumen.py       → precio + cambio % (1h/24h/7d) + máx/mín/volumen del día (paso 2.2)
│   ├── difusion.py      → empuja el estado a los paneles conectados por WS (paso 1.4)
│   ├── modelos.py       → modelos de dominio (Tick, Vela, Alerta, Cambio, ResumenSimbolo). No
│   │                      sabe de exchanges ni de BD
│   ├── ingesta/
│   │   ├── binance.py   → escucha el WebSocket de Binance y emite Ticks (paso 1.1)
│   │   ├── almacen.py   → EscritorDeTicks: junta ticks y los guarda por lotes (paso 1.2)
│   │   └── backfill.py  → baja de la REST de Binance la historia que Argos no vivió (paso 2.1b)
│   ├── detectores/      → cada alerta es un plugin: agregar = enchufar (paso 3.1)
│   │   ├── base.py      → clase Detector + ContextoDeEvaluacion + las dos cadencias
│   │   ├── registro.py  → decorador @registrar + descubrimiento automático de la carpeta
│   │   ├── silencio.py  → el antirruido: cuándo callarse aunque haya algo que decir
│   │   ├── motor.py     → quién pregunta, cuándo, y qué hace con la respuesta
│   │   ├── almacen.py   → guarda y lee alertas en la tabla `alertas`
│   │   └── humo.py      → ⚠️ andamios de verificación del 3.1; SE BORRAN en el paso 3.2
│   └── main.py          → la app FastAPI; endpoints + arranque de las tareas de fondo
├── sql/
│   ├── 001_ticks.sql            → tabla `ticks` como hypertable + índices
│   ├── 002_velas_historicas.sql → velas de 1m traídas de Binance (la historia que nos perdimos)
│   └── 003_alertas.sql          → tabla `alertas` (tabla normal, NO hypertable: son pocas por diseño)
├── pruebas/             → pytest. Ninguna necesita Docker ni internet (paso 3.1)
│   ├── conftest.py      → fábricas de datos + detectores de mentira + aislamiento del registro
│   ├── test_registro.py → que un detector mal definido reviente AL ARRANCAR
│   ├── test_contexto.py → qué ve un detector, y qué pasa cuando no hay nada que ver
│   ├── test_alertas.py  → la clave (antirruido), la evidencia (regla de oro), la severidad
│   └── test_silencio.py → el antirruido al detalle, incluidos los bordes
├── pyproject.toml       → dependencias (fastapi, uvicorn, asyncpg, pydantic-settings, websockets, httpx)
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
**La historia que Argos no vivió: el backfill** (decidido en el paso 2.1b)

Argos solo puede armar velas de los minutos que escuchó. Antes de su primer arranque no hay nada, y cada
apagón deja un hueco — se medía **12,6 % de cobertura** cuando se detectó. Eso se ve feo en el gráfico
(el eje de tiempo pega saltos) pero el problema serio es otro: los detectores de la Fase 3 comparan lo de
ahora contra lo que es *normal*, y sin historia no hay normal.

- **Se traen las velas oficiales de Binance** (`GET /api/v3/klines`, sin API key). No es inventar datos:
  son exactamente los minutos que nos perdimos, contados por el mismo exchange que ya escuchamos. Es la
  misma fuente con la que verificamos nuestras velas en el paso 1.3.
- **Tabla aparte, no dentro de `ticks`**. Una kline **no es un tick**: ya viene resumida. Meterla en
  `ticks` obligaría a fabricar operaciones con precios, cantidades e ids falsos, y eso envenenaría a los
  detectores de volumen, que cuentan operaciones. Van en `velas_historicas`, separadas y sin disfraz.
- **Solo se descarga 1 minuto.** El resto (5m, 15m, 1h, 4h, 1d) se agrega, igual que con los ticks. Bajar
  seis intervalos sería seis veces más disco y seis oportunidades de desincronizarse.
- **La vela en curso nunca se guarda.** Si el rango llega hasta ahora, la última kline que manda Binance
  se está formando: congelarla sería dar por firme algo a medio hacer, y encima le ganaría a nuestros
  ticks en vivo, que de ese minuto saben más.
- **Regla de desempate al fusionar**: para un **minuto cerrado manda la vela de Binance** (incluye todas
  las operaciones; la nuestra puede estar mocha si Argos arrancó a mitad de minuto), y el **minuto en
  curso siempre es nuestro**. Medido: de 119 minutos comparables, 112 daban OHLC idéntico; los 7 que no,
  eran justamente minutos de borde —arranque o apagado— que es lo que esta regla repara.
- **Cada vela dice de dónde salió** (`fuente`: `propia` / `historia` / `mixta`). No se disimula la mezcla,
  porque `operaciones` no se cuenta igual: en las nuestras son `aggTrade` (agrupadas) y en las históricas
  son las operaciones reales, siempre más. Los dos números son correctos pero no son comparables.
- **Se va despacio a propósito**: se mira la cabecera `x-mbx-used-weight-1m` y se frena antes del techo;
  si igual llega un 429/418 se respeta el `Retry-After`. Misma lección del paso 1.1. Los símbolos se bajan
  **en serie**, no en paralelo: el límite es por IP, así que hacerlo a la vez no acelera nada, solo gasta
  el presupuesto al doble.
- **Es incremental**: solo pide lo que falta en los bordes (más atrás o más adelante de lo que ya hay).
  Reejecutarlo no duplica nada — el índice único + `ON CONFLICT DO NOTHING` se encargan.
- **El piso de las consultas no usa `now()`** sino el dato más nuevo que exista del símbolo. Si Argos
  estuvo apagado dos días, un piso calculado desde "ahora" dejaría fuera todo lo que sí tenemos.

**Cómo se calcula "cómo viene" un activo** (decidido en el paso 2.2):

`GET /mercado/resumen` junta las dos mitades que hasta acá vivían separadas: el precio del instante
(memoria) y la historia que le da sentido (TimescaleDB). Un precio suelto no informa nada; "63.831 y
viene −0,36% en el día" ya es información. Es lo que alimenta la watchlist.

- **El ancla no es `now()`, y tampoco alcanza con "el dato más nuevo de la base".** Es el momento del
  dato más nuevo mirando las **tres** fuentes: ticks, historia y el tick vivo en memoria. El caso que
  obliga a esto es silencioso: Argos lleva treinta segundos encendido después de dos días apagado. La
  memoria tiene un precio de este segundo y la base llega hasta hace dos días; comparar uno contra otro
  mostraría un cambio de **tres** días con la etiqueta "24h", y nadie se daría cuenta.
- **Tolerancia por plazo, y `null` cuando no alcanza.** El minuto exacto de hace 24 horas puede no
  existir, así que se toma el último cierre anterior al blanco. Si ese cierre quedó más lejos que la
  tolerancia (5 min para 1h, 30 min para 24h, 3 h para 7d — alrededor del 2% del plazo), el cambio se
  devuelve **`null`**: ya no representa el plazo pedido. Un cero diría "no se movió" y un aproximado
  diría "se movió esto" con más confianza de la que hay. Regla de oro: Argos no rellena.
- **Los ticks se escanean solo donde la historia oficial no llega.** 24 horas de ticks de BTC son medio
  millón de filas, pero esos mismos minutos ya están calculados en `velas_historicas`. El piso del
  escaneo de ticks es el último minuto que trajo el backfill, así que con el backfill al día se leen
  minutos, no un día. **Medido con `EXPLAIN ANALYZE`: 1.766 filas de ticks en vez de ~500.000**, y entra
  como condición del índice (*Index Only Scan*). No cambia ningún resultado: es la misma regla de
  desempate de `velas.py` (para minuto cerrado manda Binance), solo cambia el trabajo que hace la base.
- **`minutos_24h` viaja con el volumen.** Dice cuántos de los 1.440 minutos del día tienen datos. Sin
  ese número, un volumen armado con 300 minutos se leería como el volumen del día. Se informa en vez de
  disimularse — igual que `fuente` en las velas.
- **Una consulta para todos los símbolos**, no una por símbolo: entran como arreglo (`unnest`). Con dos
  da igual; con veinte en la watchlist, es una consulta contra veinte.
- **Verificado contra Binance** (mismo método que en 1.3 y 2.1b): con cobertura completa, el máximo y el
  mínimo de 24 h salen **idénticos al octavo decimal** a los de `/api/v3/ticker/24hr`, el volumen difiere
  0,006% (nuestra ventana no arranca en el mismo segundo que la suya) y el cambio % a 0,01 pp.

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

### Los detectores: por qué son plugins y no una lista (paso 3.1)

El corazón de la Fase 3, y el lugar donde el spec pone la escalabilidad del proyecto. La forma obvia
de sumar detectores sería una lista en el arranque; se descartó porque con esa lista agregar una
alerta son dos cambios en dos archivos y el motor termina conociendo a todos los detectores
concretos. Acá es un decorador (`@registrar`) más un descubrimiento automático de la carpeta:
**crear el archivo es darlo de alta**, y no hay ninguna lista que mantener.

- **Un detector es una función pura de su contexto.** `evaluar()` no es `async` y no toca la base:
  recibe un `ContextoDeEvaluacion` ya cargado y devuelve `Alerta | None`. No es comodidad, es lo que
  hace posibles tres cosas: probarlo sin Docker, **correrlo sobre la historia** (la v2.0 pide
  backtesting de las propias alertas, y un detector que sale a buscar datos no se puede rebobinar) y
  no multiplicar consultas — el motor trae los datos una vez y los reparte entre todos.
- **Dos cadencias, que son las dos capas del spec.** `POR_TICK` cuelga de la ingesta y corre en la
  ruta caliente: sin `await`, sin base, para que un umbral de precio salte al cruzar. `POR_VELA_CERRADA`
  es una tarea de fondo que despierta cada 5 s y pregunta si cerró una vela nueva: un z-score sobre
  1.440 minutos de historia no da otra respuesta si se lo consulta 40 veces por segundo. El registro
  **rechaza al arrancar** un detector `POR_TICK` que pida historia, porque se callaría para siempre
  sin que nadie se entere.
- **El antirruido vive en el motor, no en cada detector.** Si el volumen de BTC está a 3,4σ ahora, va a
  seguir estándolo el minuto que viene: son detecciones correctas y son la misma noticia. El
  `Silencio` agrupa por la `clave` de la alerta (la identidad de la *situación*) y cada detector
  elige cuánto dura su espera. Medido en vivo: **230 ticks evaluados → 4 alertas y 226 silenciadas**.
  Al arrancar, el silencio se **precarga desde la tabla `alertas`**: sin eso, reiniciar sería una
  forma de saltarse el antirruido, y con `--reload` puesto pasaría en cada cambio de código.
- **Toda alerta viaja con su `evidencia`**: los números crudos con los que el detector concluyó, como
  texto. Es la regla de oro hecha estructura — quien la reciba puede rehacer la cuenta. Es también lo
  que va a permitir que la v1.2 vuelva sobre una alerta vieja y anote qué pasó después.
- **Emitir y guardar están separados.** La detección ocurre en la ruta caliente, donde un `INSERT`
  frenaría la ingesta; las alertas van a una cola y una tercera tarea las escribe, con reintento si la
  base no está. Verificado tirando TimescaleDB 25 s: 2 alertas quedaron esperando, `/alertas` devolvió
  503 con mensaje (no un stacktrace) y al volver la base entraron solas — 14 emitidas, 14 guardadas,
  0 descartadas.
- **`sql/003_alertas.sql` NO es una hypertable**, a diferencia de `ticks` y `velas_historicas`. Las
  alertas son pocas por diseño; si algún día hicieran falta particiones por tiempo, el problema no
  sería la tabla sino que Argos se volvió el ruido del que quería protegerte.

**Las pruebas** (`backend/pruebas/`, `uv run pytest`) — 57 y corren en 0,06 s. Que ninguna necesite
Docker ni internet **es** la comprobación del diseño: si mañana una prueba de detectores empieza a
pedir la base, la pregunta no es cómo levantarla, es qué se rompió. Dos decisiones que conviene no
deshacer:

- **Las pruebas definen sus propios detectores** en vez de usar los de `humo.py`. Los de humo son
  andamios que se borran en el 3.2, y una prueba que dependiera de ellos se rompería ese día por un
  motivo que no tiene nada que ver con lo que prueba.
- **`test_todos_los_detectores_de_verdad_cumplen_las_reglas`** recorre lo que haya en la carpeta y
  verifica los invariantes sin nombrar a nadie. Es la red que cubre gratis a cada detector que se
  escriba de acá en adelante — incluidos los cuatro del MVP, que todavía no existen.

## 🖥️ frontend/ — React 19 + Vite + Tailwind v4 (TypeScript)

El panel, con la piel de Argos (consola de inteligencia, paleta "pavo real" teal + oro, estilo Linear).

```
frontend/
├── index.html               → arranque; fija lang="es" y data-theme="dark"
├── vite.config.ts           → plugins React + Tailwind v4; alias "@" → src
├── tsconfig.*.json          → TypeScript (paths del alias "@")
└── src/
    ├── main.tsx             → monta <App/> en #root
    ├── App.tsx              → estado global: vista, activo y tramo elegidos, chat, fijados, tema
    ├── index.css            → SISTEMA DE DISEÑO: tokens (ambos temas), @font-face, estilos de componentes
    ├── lib/
    │   ├── api.ts           → puente REST: URL del backend, tipos, obtenerVelas() + obtenerResumen()
    │   ├── activos.ts       → catálogo: par (BTCUSDT) ↔ símbolo corto (BTC) ↔ nombre (2.2b)
    │   ├── formato.ts       → cómo se escriben los números (es-CL, signos, "—" cuando no hay) (2.2b)
    │   ├── mercado.tsx      → ProveedorMercado: LA conexión WebSocket + hooks para leerla (2.1)
    │   ├── resumen.tsx      → ProveedorResumen: EL pedido de resumen + Ficha por activo (2.2b)
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
        ├── Sparkline.tsx       → la curvita de precio de watchlist y tabla, con velas reales (2.2b)
        ├── PriceVolChart.tsx   → precio (área) + volumen en canvas — ⚠️ ÚLTIMO MOCK que queda
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
- Import con alias `@` → `src` (ej. `import { useFicha } from '@/lib/resumen'`).
- Comentarios en español.
- **Un activo se identifica siempre por su PAR** (`BTCUSDT`), que es como lo llama el backend. El
  símbolo corto (`BTC`) y el nombre salen del catálogo (`lib/activos.ts`) y son **solo para mostrar**.
  Antes del 2.2b convivían las dos formas sin traductor y cada componente resolvía la diferencia como
  podía; un solo idioma adentro evita el clásico "acá era BTC y allá BTCUSDT".
- **Los números se formatean en `lib/formato.ts`, nunca a mano.** Formato chileno vía `Intl` (punto de
  miles, coma decimal) y signo menos de verdad (`−`, U+2212). Cuando no hay dato va `SIN_DATO` (`—`),
  **nunca un cero**: un cero afirma "no se movió" y eso es decir algo que no sabemos.
- **Datos reales en todo el panel** desde el 2.2b. El único mock que queda es `PriceVolChart.tsx`,
  y la tarjeta que lo contiene lo dice en su encabezado.
- **Nunca escribir `dangerouslySetInnerHTML={{ __html: … }}` dentro del render.** El objeto va
  fuera del componente. React compara esa prop **por identidad del objeto**, no por el string:
  uno nuevo en cada pasada hace que reescriba el `innerHTML` del SVG entero, y con nodos nuevos
  las animaciones CSS arrancan de cero. Es el bug de "el logo se anima todo el rato" — aparecía
  en `Peacock`, `Radar`, `IsoLayers` y `CoinLogo`, y solo se hizo visible cuando el paso 2.2b
  puso datos en vivo en el menú y en la tabla, que pasaron a renderizarse dos veces por segundo.
- ⚠️ El **logo del pavo real** (`Peacock.tsx`) es un placeholder dibujado en SVG a mano →
  reemplazar por un vector pulido cuando esté.

**La escala de tintas, medida** (auditoría del 12-ago con `ui-ux-pro-max`):

Los contrastes se calculan contra `--surface`, el fondo de las tarjetas donde vive casi todo el
texto. El problema de fondo era `--faint`: **2,69:1 en oscuro y 2,79:1 en claro**, contra el
mínimo de 4,5:1 de WCAG — y con ese color estaban escritos los nombres de las monedas, los
encabezados de la tabla, las etiquetas de los KPI y los rótulos del menú. Era el color del que
más cosas dependían y el único ilegible.

Subirlo a secas habría aplastado la jerarquía (`--faint` habría quedado igual de fuerte que
`--muted`), así que la escala pasó de tres escalones a cuatro y el más tenue se reservó para lo
que **no** es información:

| Token | Oscuro | Claro | Para qué |
|---|---|---|---|
| `--text` | 16,3:1 | 18,9:1 | el dato |
| `--muted` | 7,0:1 | 7,1:1 | texto secundario |
| `--faint` | 4,5:1 | 5,1:1 | etiquetas y encabezados — el mínimo legal |
| `--ghost` | 2,4:1 | 2,4:1 | **solo adorno** (los sellos `FIG_02`). Nunca información. |

Además: `--line` pasó de 1,20:1 (las tarjetas no se despegaban del fondo) a ~1,45:1; se agregó
`--line-strong` (3:1) para el borde de los **controles**, que es donde WCAG 1.4.11 sí lo exige;
y en tema claro los tres acentos estaban entre 3,4 y 3,6:1 — bien para un ícono, corto para un
`+0,38%` de 12 px — así que se oscurecieron a ~5:1 sin moverles el tono.

**Lo que la auditoría confirmó que ya estaba bien**: el anillo de foco global (`:focus-visible`),
`prefers-reduced-motion` respetado en las cinco animaciones, la tabla con `overflow-x:auto`, y
—la regla de "no comunicar solo con color"— los porcentajes que ya viajan con su signo `+`/`−`,
así que se entienden en escala de grises.

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

**Cómo se llena el resto del panel** (decidido en el paso 2.2b):

Watchlist, cabecera, tabla y KPIs dejaron de leer `data/coins.ts` —precios y porcentajes inventados del
boceto— y pasaron a `GET /mercado/resumen`. **Ese archivo ya no existe.**

- **Un solo proveedor**, `lib/resumen.tsx`, con la misma lógica que el del WebSocket: cinco componentes
  necesitan estos datos y cinco `fetch` en bucle serían cinco pollings pidiendo lo mismo, reiniciándose
  en cada cambio de vista. Un pedido cada 10 s arriba del todo, y todos leen de ahí. Se repregunta
  además al volver a la pestaña: el navegador congela los temporizadores en segundo plano, así que al
  volver de un rato largo lo que hay en pantalla puede tener horas.
- **El porcentaje se recalcula en el navegador, y para eso está `referencia`.** El REST refresca cada
  10 s y el WebSocket cada 0,5 s: si nos quedáramos con el porcentaje que calculó el backend, el precio
  de la watchlist se movería y el `+1,84%` de al lado quedaría clavado — dos números contradiciéndose en
  la misma fila. Por eso al backend no se le pide el resultado sino **el punto de partida**: cada cambio
  viene con el precio de hace 24 h, y la división se rehace acá contra el precio vivo.
  **Verificado**: el porcentaje recalculado sale idéntico al del backend (`+0,13%` vs `0.13`).
  Lo que *no* se hace es inventar la referencia: si el backend dijo `null`, acá sigue siendo `null`.
- **Una identidad por activo: el par.** Todo el estado (seleccionado, fijados, claves de diccionario,
  argumentos de llamada) usa `BTCUSDT`. `lib/activos.ts` traduce al `BTC` que se muestra.
- **Los sparklines pasaron a ser reales.** Un número inventado ya es malo; un **gráfico** inventado es
  peor, porque no se lee como un dato sino como una forma — nadie verifica una curva, se la cree. Salen
  de `/mercado/velas` con pocas velas anchas (24 de 1 h, 42 de 4 h): una curva de 70 píxeles no
  distingue más detalle, y pedir 1.440 velas de 1 minuto sería mover mil veces más datos de los que se
  ven. Sin datos no se dibuja nada — una línea plana diría "no se movió".
- **Lo que no se sabe se muestra como `—`, nunca como cero.** Aplica a los plazos que el backend manda
  en `null` (falta historia) y a la volatilidad σ, que la va a calcular el detector de z-score en la
  Fase 3. Un `3,4σ` de relleno se leería como una medición.
- **`minutos_24h` se muestra.** Si la cobertura del día es parcial, el KPI de volumen lo dice en oro
  (`parcial · 1.435/1.440 min`) en vez de presentar el volumen de 1.435 minutos como el del día.
- **Bug que encontró la verificación**: el rango de 24 h se abreviaba con un decimal y en ETH salía
  `1,9K – 1,9K` —dos números distintos con el mismo texto—, que sugiere que el precio no se movió. Se
  cambió a cifras significativas: la precisión se adapta a la magnitud en vez de a la unidad.

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
