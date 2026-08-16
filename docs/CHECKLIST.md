# CHECKLIST — MVP de Argos ✅

> Documento vivo. Se tilda a medida que avanzamos. Contexto y reglas: [`./AGENTS.md`](./AGENTS.md).

## 🔄 La dinámica (ritmo de cada paso)
1. **Explico** qué vamos a hacer y por qué (didáctico) 📖
2. **Construyo** el código 🔨
3. **Verificamos** que funciona (un check concreto) ✅
4. **Commiteas** con tu visto bueno al cerrar cada bloque 💾

---

## FASE 0 — Cimientos (las 3 patas respirando)
- [x] **0.1** Esqueleto de carpetas + `.gitignore` + `README` *(hecho + commiteado)*
- [x] **0.2** `infra/docker-compose.yml` con **TimescaleDB** → contenedor `healthy`, PG 16.14 + TimescaleDB 2.28.3 ✅
- [x] **0.3** Esqueleto **FastAPI** con endpoint `/health` → responde `{"status":"ok"}` + `/docs` OK ✅
- [x] **0.4** Esqueleto **React + Vite + Tailwind** (v8.1 + React 19 + Tailwind v4) → `localhost:5173` muestra la página de Argos con la piel del boceto (nav, panel/mercados, chat isla, tema claro/oscuro) ✅
- [x] **0.5** Conexión backend ↔ base de datos verificada → `GET /health/db` responde
  `{"postgres":"16.14","timescaledb":"2.28.3"}` ✅ *(pool asyncpg + config desde `infra/.env`;
  con la BD caída devuelve 503 con mensaje claro y se reconecta sola cuando vuelve)*

**🎉 FASE 0 COMPLETA** — las tres patas montadas y el backend hablando con la base de datos.

## FASE 1 — Motor de datos en tiempo real
- [x] **1.1** WebSocket de Binance para BTC/ETH → ticks por consola ✅
  *(`app/ingesta/binance.py` + modelo `Tick` en `app/modelos.py`; stream `aggTrade` combinado,
  precios en `Decimal`, reconexión con espera creciente. Probar:
  `cd backend && uv run python -m app.ingesta.binance --limite 20`)*
- [x] **1.2** Persistir ticks en TimescaleDB (hypertable) + "último estado" en memoria ✅
  *(tabla `ticks` en `sql/001_ticks.sql`; escritura por lotes en `app/ingesta/almacen.py`;
  memoria en `app/estado.py`; la ingesta arranca con la API. Ver: `GET /mercado/estado`.
  Aguanta que se caiga la base: los ticks esperan y entran solos cuando vuelve)*
- [x] **1.3** Armar velas (candles) por agregación + endpoint REST para consultarlas ✅
  *(`app/velas.py` con `time_bucket` + `first`/`last` de Timescale; intervalos 1m/5m/15m/1h/4h/1d.
  `GET /mercado/velas?simbolo=BTCUSDT&intervalo=1m&limite=200`. Verificado contra las velas
  oficiales de Binance: idénticas hasta el octavo decimal)*
- [x] **1.4** WebSocket del backend que empuja precios en vivo al frontend ✅
  *(`app/difusion.py`; `WS /ws/mercado` manda `bienvenida` al conectarse, `estado` cuando cambia algo
  —cada 0,5 s como mucho— y `latido` cada 15 s de silencio. Soporta varios paneles a la vez. CORS
  habilitado para localhost:5173)*

**🎉 FASE 1 COMPLETA** — el motor de datos en tiempo real anda de punta a punta: Binance → ticks →
TimescaleDB → velas → empujado al panel.

## FASE 2 — Dashboard base
- [x] **2.1** Gráfico de velas (lightweight-charts) actualizándose en vivo ✅
  *(`src/lib/api.ts` = puente REST; `src/lib/mercado.tsx` = LA conexión WebSocket de toda la app;
  `CandleChart.tsx` reescrito con lightweight-charts v5. La historia sale de `/mercado/velas` y el
  WebSocket mueve la vela en curso; cada 10 s se le vuelve a preguntar a la base para corregir el
  máximo/mínimo, porque entre dos fotos del WebSocket puede haberse escapado un pico)*
- [x] **2.1b** Backfill: traer desde Binance la historia que Argos no vivió ✅
  *(No estaba en el plan original: salió de mirar el gráfico y ver que el eje de tiempo pegaba
  saltos. Argos tenía 100 minutos repartidos en 13 horas — 12,6% de cobertura. `sql/002_velas_historicas.sql`
  (tabla aparte: una kline NO es un tick) + `app/ingesta/backfill.py` (pagina la REST de Binance,
  1.000 velas por pedido, respetando el peso) + fusión en `velas.py`. Se descarga solo el intervalo
  de 1m; el resto se agrega. Verificado: en los minutos con cobertura continua nuestras velas y las
  de Binance son idénticas (112 de 119); las 7 que diferían eran minutos de borde —arranque o
  apagado— donde la nuestra estaba mocha, que es justo lo que la fusión repara.)*
- [x] **2.2a** Backend del resumen: precio + cambio % (1h/24h/7d) + máx/mín/volumen del día ✅
  *(`app/resumen.py` + `GET /mercado/resumen`. Junta las dos mitades que estaban separadas: el precio
  de memoria y la historia de la base. **El ancla mira las TRES fuentes** —ticks, historia y el tick
  vivo— porque con solo la base pasa esto: Argos lleva 30 s encendido tras dos días apagado, la
  memoria tiene el precio de ahora y la base llega hasta hace dos días, y el "24h" mostraría un cambio
  de tres días sin que se note. Cada plazo tiene **tolerancia**; si el cierre más cercano queda más
  lejos, el cambio va `null` en vez de un aproximado. Los ticks se escanean solo desde donde termina el
  backfill: medido con `EXPLAIN ANALYZE`, 1.766 filas en vez de ~500.000. Verificado contra
  `/api/v3/ticker/24hr` de Binance: máx y mín idénticos al octavo decimal, volumen a 0,006%.)*
- [x] **2.2b** Watchlist, cabecera, tabla y KPIs con datos reales + selector de moneda e intervalo ✅
  *(`src/data/coins.ts` **eliminado**. Nuevos: `lib/activos.ts` (catálogo par ↔ símbolo corto),
  `lib/formato.ts` (números es-CL, y `—` cuando no hay dato — nunca cero), `lib/resumen.tsx`
  (UN pedido cada 10 s para toda la app) y `Sparkline.tsx` (curvas con velas reales; las de antes
  eran polilíneas escritas a mano). **El % se recalcula en el navegador** contra el precio vivo del
  WebSocket, usando la `referencia` que manda el backend: si no, el precio se movería y el
  porcentaje de al lado quedaría clavado 10 s. Verificado: el recalculado sale idéntico al del
  backend. El gráfico ya no está clavado en BTCUSDT · 1m y los botones de tramo salen de
  `INTERVALOS` (antes eran 4 decorativos de los 6 reales). **Bug que apareció al verificar**: el
  rango de 24 h de ETH salía `1,9K – 1,9K` por redondear a un decimal → ahora usa cifras
  significativas. Queda en mock solo `PriceVolChart` (la tarjeta lo declara) y la volatilidad σ,
  que llega con los detectores de la Fase 3.)*

- [x] **2.2c** Arreglos de la primera pasada por el navegador + auditoría de diseño ✅
  *(**Tres bugs**: (a) al cambiar de tramo la app se ponía en negro — `CandleChart` mandaba el
  precio en vivo, ya ubicado en el tramo NUEVO, a una serie que todavía tenía dibujado el viejo,
  y lightweight-charts no acepta actualizar hacia atrás; se resolvió con la marca `datosDe`.
  (b) El pin salía aplastado: lo había envuelto en un `span` sin `flex:none` para cortar el clic
  — ahora el corte lo hace el propio `Pin`. (c) Las animaciones se repetían sin parar:
  `dangerouslySetInnerHTML={{…}}` creaba un objeto nuevo por render y React reescribía el SVG
  entero; el objeto se sacó fuera del componente en `Peacock`, `Radar`, `IsoLayers` y `CoinLogo`.
  Además, seleccionar un activo ya no te expulsa de la vista Mercados.
  **Auditoría con `ui-ux-pro-max`** (instalado como plugin): `--faint` fallaba contraste en los
  dos temas y era el color de casi todas las etiquetas → escala de tintas rehecha en 4 escalones
  con `--ghost` para lo decorativo, `--line-strong` para bordes de control, acentos del tema
  claro de ~3,5:1 a ~5:1, piso tipográfico de 9 a 10,5 px, y los botones de tramo de ~26×19 a
  32×28 px con el activo en teal. Ver ARQUITECTURA.md → "La escala de tintas, medida".)*

## FASE 3 — Detectores de alertas (el corazón)
- [x] **3.1** Framework de detectores (clase base + registro de plugins) ✅
  *(Paquete `app/detectores/`: `base.py` (clase `Detector` + `ContextoDeEvaluacion` + las dos
  cadencias), `registro.py` (decorador `@registrar` + descubrimiento automático de la carpeta —
  **crear el archivo es darlo de alta**), `silencio.py` (antirruido), `motor.py` y `almacen.py`.
  Modelo `Alerta` en `modelos.py` y tabla en `sql/003_alertas.sql`. Endpoints `GET /detectores`
  y `GET /alertas`. **Decisión de fondo: un detector es una función pura de su contexto** —
  `evaluar()` no es async y no toca la base, porque así se puede probar sin Docker y, sobre todo,
  correr sobre la historia (la v2.0 pide backtesting, y un detector que sale a buscar datos no se
  puede rebobinar). **Verificado**: en vivo, 230 ticks evaluados → 4 alertas y 226 silenciadas; y
  tirando TimescaleDB 25 s las alertas quedaron en cola y entraron solas al volver (14 emitidas =
  14 guardadas, 0 descartadas). ⚠️ `humo.py` son dos andamios de verificación y **se borran en el
  3.2**.)*
- [x] **3.1b** Primeras pruebas automatizadas del proyecto ✅
  *(No estaba en el plan: salió de que el 3.1 se verificó con un script suelto que se iba a perder.
  `backend/pruebas/` con pytest (grupo `dev` del `pyproject`, no toca las dependencias de
  producción): **57 pruebas en 0,06 s, sin Docker ni internet** — comprobado apuntando la config a
  un host inexistente. Cubren el registro (que un detector mal definido reviente **al arrancar**),
  el contexto y sus huecos, la clave y la evidencia de las alertas, y el silencio con sus bordes
  (ventana exacta, ventana en cero, precarga tras reinicio). **Las pruebas de la maquinaria definen
  sus propios detectores** en vez de usar los reales — y se comprobó enseguida que valía la pena:
  los andamios `humo.py` se borraron en el 3.2 y ninguna prueba se rompió. Y
  `test_todos_los_detectores_de_verdad_cumplen_las_reglas` recorre la carpeta sin nombrar a nadie:
  cubre gratis a cada detector que se escriba después.)*
- [x] **3.2** Alerta #1 Umbral de precio ✅
  *(`app/detectores/umbral_precio.py` + `umbrales.py` (configuración: memoria + tabla) +
  `sql/004_umbrales.sql` + `GET/POST/DELETE /umbrales`. **`humo.py` borrado**: los andamios
  cumplieron. **La idea central: cruzar no es estar.** La versión ingenua (`if precio > umbral`)
  sigue siendo verdadera mientras el precio se quede arriba, así que avisaría una y otra vez de lo
  mismo; lo que se detecta es la **transición**, y para eso el detector recuerda de qué lado vio el
  precio la última vez (la única memoria que se permite, y sigue siendo reproducible: misma
  secuencia → mismas alertas). **Recién despierto no inventa un cruce**: si Argos arranca y el
  precio ya está del otro lado, anota el lado y se calla — encontrarlo cruzado no es haberlo visto
  cruzar. La línea pertenece al lado de abajo, para que "sube de 70.000" y "baja de 3.400" digan
  las dos la verdad. **Dos bugs encontrados y arreglados**: (a) el lado visto se actualizaba dentro
  del bucle, así que con dos umbrales sobre el mismo número el segundo nunca veía el cruce — lo
  cazó una prueba; (b) el mensaje decía "cruzó 63834 (venía de 63834)", cierto pero ilegible, y
  pasa seguido porque los umbrales se ponen en números redondos. **Verificado en vivo**: cruces
  reales en las dos direcciones, uno a valor exacto, 11 cruces silenciados por el antirruido
  mientras el precio bailaba sobre la línea, y ninguna alerta falsa al reiniciar con el precio ya
  cruzado.)*
- [x] **3.2b** Corrección al framework del 3.1 (salió al escribir el primer detector real) ✅
  *(`evaluar()` pasó de devolver `Alerta | None` a `list[Alerta]`. El caso que lo rompía: con
  umbrales en 70.000 y 71.000, un tick que salta de 69.900 a 71.200 cruza los dos, y devolviendo
  una sola el segundo quedaba marcado como visto **sin haber avisado nunca** — alerta perdida en
  silencio, el peor modo de falla de Argos. Se cambió con dos detectores en el repo en vez de con
  cinco; para eso servían los andamios.)*
- [x] **3.3** Alerta #2 Movimiento % en ventana ✅
  *(`app/detectores/movimiento_porcentual.py`. El primer detector `POR_VELA_CERRADA` y el primero
  que Argos encuentra **solo**, sin que tú tengas que saber qué número mirar. Mide **cierre contra
  cierre** de hace N minutos: el rango máx-mín mediría agitación y eso es la #3, tener dos
  detectores contando la misma noticia es no tener dos detectores. Tres ventanas (5/15/60 min) y se
  emite **solo la más corta que saltó**, con la clave llevando la dirección y **no** la ventana,
  para que las tres compartan el silencio. **La idea central, hermana del "cruzar no es estar" de
  la #1: moverse no es haberse movido.** Un pump de 4% sigue dentro de la ventana de una hora
  durante la hora siguiente, así que el detector ingenuo lo grita sesenta veces mientras el precio
  ya no hace nada; por eso al emitir se anota **desde qué precio se avisó** y hacia ese mismo lado
  no se vuelve a hablar salvo que el movimiento continúe otro tanto. La referencia se busca **por
  marca de tiempo y no por posición** (un minuto sin operaciones correría la ventana sin avisar), y
  si esa vela no está, no se opina: no se aproxima con la más cercana.
  **Verificado rebobinando el detector sobre los 369 días de historia real de la base** — que es
  el argumento de diseño del 3.1 cobrado: un detector puro se puede correr sobre el pasado. Ahí se
  midió que la memoria del último aviso evita entre **3,4× (BTC) y 5× (ETH)** las alertas, y se
  eligieron los umbrales con datos: con 3/5/8 —lo primero que propusimos— BTC habría hablado **un
  solo día en todo el año** (el desplome del 10-oct-2025), así que quedó en **2 / 3,5 / 6%** →
  BTC 1,5 alertas al mes en 11 días distintos, ETH 5,8 en 40. Dos hallazgos anotados en el módulo:
  con la ventana larga en 8% las cortas la tapaban **siempre** y no disparaba nunca; y con el mismo
  número ETH alerta 3-4× más que BTC, que es la evidencia empírica de por qué hace falta la #3.
  103 pruebas en total, sin Docker ni internet.)*
- [x] **3.3b** La historia se completa sola al arrancar *(pedido sobre la marcha, no estaba en el plan)* ✅
  *(`ponerse_al_dia()` en `app/ingesta/backfill.py` + `BACKFILL_AL_ARRANCAR`/`BACKFILL_DIAS` en la
  config. El backfill existía desde el 2.1b pero había que **acordarse de correrlo a mano**, así que
  cada apagón dejaba un hueco visible en el gráfico y, peor, sin historia fresca los detectores de
  la Fase 3 comparan contra un "normal" viejo. Ahora al encender Argos pide los minutos que se
  perdió. Va en **tarea de fondo**: en una base vacía esto baja un año y nadie va a esperar mirando
  una pantalla en blanco. **Reintenta con espera creciente** (30 s → 5 min) en vez de rendirse,
  porque acá Docker se levanta a mano y arrancar el backend antes que la base es lo normal — es la
  misma razón por la que `db.py` reconecta perezosamente. Verificado borrando a propósito 3 horas de
  historia: al reiniciar bajó 180 velas por símbolo —las 174 borradas más los minutos que habían
  pasado— sin tocar nada más.)*
- [ ] **3.4** Alerta #3 Volatilidad anómala (z-score) *(ya con algo de historia)*
- [ ] **3.5** Alerta #4 Volumen anómalo
- [ ] **3.6** Panel de alertas en el dashboard + configuración de umbrales

## FASE 4 — Notificaciones
- [ ] **4.1** Crear el bot de Telegram y conectar el envío de alertas
- [ ] **4.2** Notificaciones dentro del panel

## FASE 5 — IA mínima on-demand
- [ ] **5.1** Instalar Ollama + modelo cuantizado → verificar que usa la GPU (RTX 3060)
- [ ] **5.2** Botón *"resumime el mercado ahora"* → la IA explica el estado actual (sin probabilidades)

---

## 🎯 → Fin del MVP (v1.0)
Luego seguimos el **roadmap de versiones** (v1.1 → v5.0) del [spec](../../spec-crypto-monitor.md).

---

## 📌 Anotado para más adelante (NO se implementa ahora)

Ideas que salieron trabajando y quedaron parqueadas a propósito, para no desviar el MVP. El detalle
de cada una está en el [spec, §2.F](../../spec-crypto-monitor.md).

- [ ] **Revisión completa del frontend** — pantalla completa / expandir el gráfico, selector de rango
  temporal (1D/1W/1M/3M/6M/YTD/1Y/All, que **no es lo mismo** que el intervalo de vela), enchufar los
  botones `15m/1H/4H/1D` que hoy son decorativos, volumen real bajo el gráfico, leyenda O/H/L/C bajo
  el cursor, logo del pavo real de verdad, estados de carga/error unificados, responsive y
  accesibilidad. *Después del MVP funcional: pulir la vitrina de una tienda vacía es el orden
  equivocado.*
- [ ] **Medidor de veredicto técnico** (venta fuerte → compra fuerte) + rejilla de rendimiento por
  plazo + key stats + estacionalidad. Va en **v1.1**, que es cuando existirán los indicadores de los
  que tiene que salir. Ojo con la regla de oro: el medidor informa qué dicen los indicadores, **no
  aconseja**.

---

**👉 Estamos aquí:** **Fases 0, 1 y 2 cerradas + 3.1, 3.2 y 3.3 hechos.** Argos ya no solo vigila lo
que tú le pides: encuentra cosas por su cuenta. Si BTC se mueve fuerte en cinco minutos, lo dice —una
vez, con los números, y sin repetirlo mientras la ventana arrastra el mismo salto. Y desde el 3.3b se
pone al día solo al encender, así que el gráfico y la historia contra la que comparan los detectores
están completos desde el primer minuto.

Lo que todavía le falta es **criterio propio**: el "2% en 5 minutos" lo elegimos nosotros, y quedó
medido que con el mismo número ETH alerta 3-4 veces más que BTC. Siguiente: **3.4 — Volatilidad
anómala (z-score)**, que en vez de preguntar "¿se movió más de X?" pregunta *"¿esto es raro para lo
que este activo suele hacer?"*. Es la alerta que el spec señala como la clave anti-ruido y la que
después alimenta las base rates de las probabilidades.

### Cómo levantar el frontend
```bash
cd frontend
npm install     # (solo la 1ª vez)
npm run dev     # http://localhost:5173
```
Diseño de referencia (boceto vivo): la piel salió de una maqueta iterada; el sistema (paleta pavo real teal+oro, Adwaita Sans + JetBrains Mono, estilo Linear) vive en `src/index.css`. **Pendiente:** el logo del pavo real es un placeholder dibujado en SVG → reemplazar por un vector pulido cuando esté.
