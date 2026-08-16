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
- [x] **3.4** Alerta #3 Volatilidad anómala (z-score) ✅
  *(`app/detectores/volatilidad.py`. **La primera alerta con criterio propio**: el umbral no lo
  ponemos nosotros, sale del propio activo. Mide la **amplitud** del tramo —`(máx − mín) / apertura`—
  contra lo que ese activo viene haciendo las últimas 24 h. Es a propósito otra pregunta que la #2:
  un tramo que sube 3% y vuelve tiene movimiento neto CERO y amplitud enorme, o sea que para la #2
  no pasó nada y ahí hubo pánico. #2 = ¿se fue a alguna parte? · #3 = ¿se está agitando?
  **No es el z-score de manual, y ese es el punto**: media y desviación las arrastran los propios
  picos, así que después de un desplome Argos quedaría ciego 24 h y en calma total alertaría de
  cualquier cosa. Se usa **mediana + MAD** (×1,4826), que se calculan con el orden de los datos y no
  con su suma. Hay una prueba que hace las dos cuentas sobre los mismos números: el pico que el
  criterio robusto ve con z>40, el clásico lo ve con z=1,3 — invisible.
  Tramos de **5 minutos** contra **288 de referencia (24 h)**: en velas de 1m serían 1.441, por
  encima del tope de 1.000 de `obtener_velas` (medido: la consulta de 5m cuesta 22 ms, la de 15m
  153 ms). Se avisa **al entrar** en zona rara y no se repite hasta que vuelve la calma: un episodio,
  un aviso. Más un **piso absoluto** de amplitud, porque "diez veces más agitado que nada" sigue
  siendo nada.
  **La primera calibración salió mal y quedó documentada**: con el umbral clásico (z 3-5) daba
  **90-130 alertas al mes**. Midiendo la distribución real sobre los 369 días de la base se vio por
  qué — p50≈0, p90≈2,3, p99≈7, p99,9≈15, p99,99≈34: el z estaba bien construido, la escala de
  umbrales era la equivocada. Quedó en **z 25** (rearme 8 ≈ p99, `fuerte` 50, piso 0,5%) →
  **BTC 1,9 alertas/mes, ETH 2,4/mes**, y el desplome del 10-oct-2025 produce **una** alerta, no una
  ráfaga. 119 pruebas, sin Docker ni internet.)*
- [x] **3.5** Alerta #4 Volumen anómalo ✅
  *(`app/detectores/volumen.py` + `app/perfiles.py`. La única de las cuatro que puede avisar **antes**
  de que el precio se mueva: las otras reaccionan al precio, y el volumen es lo que se mueve primero
  cuando alguien grande entra o sale. Por eso la alerta cuenta además qué hizo el precio — volumen
  alto **con** movimiento confirma lo que ya se ve; volumen alto **sin** movimiento es la señal
  interesante.
  **El problema propio de este detector es el reloj.** El volumen de cripto tiene horario: medido
  sobre la base, la franja de las 14:00 UTC (apertura de EEUU) mueve **2,8× la de las 21:00**, todos
  los días. Comparar contra "la mediana de las últimas 24 h" no detecta anomalías, detecta el
  amanecer de Nueva York — se comprobó: **una cuarta parte de las alertas caía en 3 horas del día**.
  La solución es la que usa cualquier operador: **RVOL**, el volumen de ahora dividido por el típico
  de **esta misma franja horaria** en los últimos 14 días. Con el perfil intradía la concentración
  bajó de 25% a **14-15%** (lo uniforme sería 12,5%), o sea que el efecto del reloj desapareció.
  El perfil lo arma `app/perfiles.py` (una consulta, 288 franjas, recalculado cada hora) y **se lo
  pasa el motor al detector en `contexto.extras`**, que es el camino que dejó previsto el 3.1: si
  hace falta una fuente nueva la carga el motor, nunca el detector, que tiene que seguir siendo puro
  para poder rebobinarse. Para eso el motor tomó un parámetro `extras` y `main.py` es quien conecta
  los dos — el motor sigue sin conocer ningún detector concreto.
  **Calibración con historia real, con el perfil móvil de los 14 días previos a cada día** (usar el
  año entero metería el futuro en la referencia y el backtest sería mentira): el RVOL de 2-3 del que
  se habla en el ambiente es para el acumulado del día, no para tramos de 5 minutos — con 5 daban
  **165 alertas al mes**. Quedó en **RVOL 30** (rearme 2, `fuerte` 60) → **BTC 3,9/mes, ETH 5,3/mes**.
  El piso en dólares no cambia nada con BTC/ETH (mismas alertas con 500 mil que con 5 millones):
  queda como seguro para cuando Argos mire activos más chicos. 134 pruebas.)*
- [x] **3.5b** La #3 pasa a medir como el resto del mundo *(salió de revisar el estándar)* ✅
  *(La alerta #3 medía `máximo − mínimo`; ahora usa el **rango verdadero** (*True Range*) de Wilder,
  que es lo que hay debajo del ATR de cualquier plataforma: el mayor entre el recorrido interno y
  los dos saltos contra el cierre anterior. Los huecos entre tramos son volatilidad real que la
  medida anterior no veía — hay una prueba donde un tramo "quieto" pasa de 0,1% a 3,1% al mirarlo
  bien. Recalibrado: los umbrales aguantan (BTC 2,0 alertas/mes, ETH 2,4) y el desplome del
  10-oct-2025 **sube a `fuerte`**, que antes se quedaba corto. Comparar contra la mediana en vez de
  un promedio hace de esto un ATR robusto. Además, el cálculo de mediana+MAD que comparten la #3 y
  la #4 se mudó a `detectores/estadistica.py`, para que el "por qué robusto" esté escrito una vez.)*
- [x] **3.6** Panel de alertas en el dashboard + configuración de umbrales ✅
  *(`lib/alertas.tsx` (proveedor), `components/AlertasView.tsx`, `components/Umbrales.tsx` y
  `PulseCard.tsx` reescrito. **Se acabó la maqueta**: el recuadro "Lo que Argos vio" mostraba tres
  eventos inventados desde el paso 0.4 y ahora muestra lo que emitieron los detectores de verdad.
  El banner de arriba también: decía "Mercado tranquilo" pasara lo que pasara, y ahora cuenta
  cuántas alertas hubo en la última hora — afirmar calma sin mirar es exactamente lo que la regla
  de oro prohíbe, y era la propia app la que lo hacía.
  **La vista Alertas muestra la evidencia**: cada alerta se abre y enseña los números crudos con
  los que el detector llegó a su conclusión. Esa es la regla del proyecto puesta en pantalla —
  Argos no pide que le crean, muestra la cuenta. Las claves se pintan tal cual vienen, así que un
  detector nuevo aparece ahí sin tocar el frontend. Hay filtros por detector, que salen de
  `GET /detectores` (nada escrito a mano).
  **Umbrales configurables desde la pantalla**: crear y quitar los precios que vigilas, con el
  precio actual como referencia en el campo. Después de crear o borrar **se vuelve a preguntar** en
  vez de creerle a la respuesta: la lista del backend es la copia en memoria que mira el detector,
  así que si algo aparece ahí está siendo vigilado de verdad. Y si `cargado_alguna_vez` es `false`
  se dice, porque ahí una lista vacía no significa "no tienes ninguno" sino "no sabemos".
  El contador del menú (que decía `2` fijo) ahora cuenta lo que no miraste, guardando en
  `localStorage` el id de la última vista — es una preferencia de la pantalla, no un hecho del
  mercado, así que no ensucia la tabla de alertas. Verificado de punta a punta en el navegador:
  crear → el detector lo toma (`Umbral nuevo: BTCUSDT arriba 63100` en el log) → listar → borrar.)*

## FASE 4 — Notificaciones
- [ ] **4.1** Crear el bot de Telegram y conectar el envío de alertas
- [x] **4.2** Notificaciones dentro del panel ✅
  *(`ColaDeAlertas` + `emitir_alertas()` en `app/difusion.py`, `al_emitir` en el motor,
  `components/AvisoDeAlerta.tsx` y el proveedor de alertas escuchando el socket. **Las alertas
  ahora viajan por el WebSocket que ya existía desde el 1.4**, con tipo `alerta`: antes había que
  esperar hasta diez segundos al refresco del feed **y** estar mirando la vista correcta. Una
  alerta que llega tarde ya no es una alerta.
  **Avisar y guardar quedaron separados**: el motor llama a `al_emitir` en el mismo instante en que
  la alerta pasa el antirruido, y el guardado en la base sigue su propio camino. Si escribir tarda
  o falla —la base puede estar caída— el aviso no espera a eso. Y si quien escucha revienta, se
  anota y la alerta sigue su curso: perder una detección por un fallo al notificar sería el peor
  intercambio posible. Ahí mismo se engancha Telegram en el 4.1.
  **Esta cola sí se puede tirar, al revés que la del guardado**: sin paneles abiertos el aviso en
  vivo no tiene a quién, y la alerta no se pierde igual porque está en la base. Lo que se descarta
  es el aviso, que fuera de su momento no sirve.
  El cartel se va solo a los 12 s, se puede cerrar y lleva a la vista Alertas. **No hay cola de
  carteles**: si llegan tres seguidas se muestra la última, porque apilar avisos es el ruido que
  todo el resto del proyecto evita. El pedido periódico se queda igual y ahora cumple otro papel:
  llenar la lista al abrir y repararla si el socket estuvo caído — inmediatez por un lado, verdad
  por el otro, el mismo trato que ya tienen el gráfico y el resumen. Verificado en vivo con un
  umbral puesto a un dólar del precio.)*

- [x] **4.3** Revisión del frontend: que lo que se ve haga algo *(pedido sobre la marcha)* ✅
  *(**No queda ningún dato inventado en la app.** Lo que se hizo, por orden de lo que se pidió:
  **el chat arranca cerrado** —antes se abría solo en pantallas anchas y se comía 360 px del panel
  en cada arranque, cuando lo que uno viene a ver es el mercado—; **el menú se colapsa** a una tira
  de íconos y lo recuerda (el chat NO se recuerda a propósito: abrirlo es una decisión del momento,
  colapsar el menú es una preferencia de trabajo); **Mercados quedó funcional**: el gráfico de
  precio y volumen dibujaba veinte velas del boceto y ahora sale de `GET /mercado/velas` (96 tramos
  de 15 min = 24 h exactas), y la **volatilidad dejó de decir "llega en Fase 3"** —ya llegó— con un
  endpoint nuevo, `GET /mercado/volatilidad` (`app/volatilidad.py`), que devuelve el rango
  verdadero mediano de 5 min de las últimas 24 h: **la misma medida que usa la alerta #3**, porque
  si el panel midiera la volatilidad de otra forma que el detector, las dos pantallas dirían cosas
  distintas del mismo mercado.
  **El chat dejó de mentir**: mostraba una "conversación de ejemplo" con `$64.284` y `3,4σ`
  inventados, contradiciendo dos líneas más abajo su propia promesa de no inventar números. Ahora
  el botón arma el estado real —precios, cambios, volatilidad, últimas alertas— y aclara que lo
  escribió la app y no un modelo; conversar de verdad sigue siendo Fase 5, y lo dice. De paso se
  fueron los botones que no hacían nada (adjuntar, formato, micrófono, "sacar como ventana") y el
  cuerpo del mensaje dejó de ser `dangerouslySetInnerHTML`, que era una puerta abierta a que lo
  que uno escriba se interprete como HTML.
  **El pie del menú también mentía**: decía "Vigilando · en vivo" con "1 anomalía activa" en el
  tooltip pasara lo que pasara, incluso con el backend apagado; ahora refleja el socket y las
  alertas de la última hora, y sin conexión el sonar se apaga. **Configuración dejó de ser un botón
  muerto**: muestra el estado de la API, la base, el WebSocket y la ingesta, más qué detectores
  corren y con qué cadencia — mirar a Argos por dentro sin abrir una terminal. La fila "+ agregar
  activo a favoritos" era un control muerto y pasó a ser una línea que dice la verdad.)*

- [x] **4.4** Sección Chat a pantalla completa *(pedida sobre la marcha)* ✅
  *(`lib/chat.tsx` (proveedor), `components/ChatView.tsx`, `ChatIsland.tsx` reescrito. El botón
  "Chat con Argos" del menú ya no abre la isla lateral: lleva a una **sección propia** que ocupa
  toda la pantalla, con sugerencias de lo que Argos sí sabe responder, historial y campo anclado
  abajo. La isla sigue existiendo y la abre el botón de la cabecera — resuelven cosas distintas:
  la isla es para preguntar **sin dejar de mirar** el gráfico, la sección para leer con calma una
  respuesta de ocho líneas que no entra en una columna de 360 px.
  **Las dos leen la misma conversación**, y eso obligó a sacar los mensajes de los componentes a
  un proveedor: si cada uno guardara los suyos, escribir en la isla y abrir la sección mostraría
  una pantalla en blanco, y peor, al cambiar de vista React desmonta el componente y el historial
  se perdería solo. Es el mismo argumento del WebSocket, el resumen y las alertas.
  Entrar a la sección cierra la isla: son dos ventanas a lo mismo y tenerlas abiertas a la vez es
  mostrar el contenido dos veces robándole ancho al chat. El botón "sacar como ventana (pronto)"
  de la isla —que no hacía nada— ahora lleva a la sección, que es lo que prometía.
  Argos responde con **datos medidos o con la verdad**: si la pregunta va de mercado arma el
  estado real y aclara que entender preguntas llega en la Fase 5; si no, dice que todavía no sabe
  conversar. A "¿cuál va a subir mañana?" **no inventa un pronóstico**, que es exactamente lo que
  el spec prohíbe.)*

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

- [~] **Revisión completa del frontend** — *parcialmente hecha en el 4.3*: los botones de intervalo
  ya funcionan (2.2b), el volumen real bajo el gráfico y la volatilidad ya están, y no queda ningún
  dato inventado. **Sigue pendiente**: pantalla completa / expandir el gráfico, selector de rango
  temporal (1D/1W/1M/3M/6M/YTD/1Y/All, que **no es lo mismo** que el intervalo de vela), leyenda
  O/H/L/C bajo el cursor, logo del pavo real de verdad, estados de carga/error unificados,
  responsive fino y accesibilidad.
- [ ] **Medidor de veredicto técnico** (venta fuerte → compra fuerte) + rejilla de rendimiento por
  plazo + key stats + estacionalidad. Va en **v1.1**, que es cuando existirán los indicadores de los
  que tiene que salir. Ojo con la regla de oro: el medidor informa qué dicen los indicadores, **no
  aconseja**.

---

**👉 Estamos aquí:** **Fases 0, 1, 2 y 3 CERRADAS. Fase 4 a medias.**

Argos ya no solo vigila lo que tú le pides: **encuentra cosas por su cuenta**. Las cuatro alertas del
MVP están hechas y calibradas contra un año de historia real — entre las cuatro hablan unas 10 veces
al mes por símbolo, que es exactamente el "bajo ruido" que pide el spec. Se pone al día solo al
encender, muestra cada hallazgo con la evidencia que lo justifica, avisa en el momento por WebSocket,
y **no queda ni un dato inventado en la aplicación**.

Detalle de la sesión que cerró la Fase 3: [`./avance-2026-08-16.md`](./avance-2026-08-16.md).

Siguiente: **4.1 — el bot de Telegram**, para enterarse **sin** tener la app abierta, que es el
sentido del proyecto. **Ese paso te necesita a ti**: hay que crear el bot con BotFather y
conseguir el token, y el asistente no maneja credenciales. Del lado del código el enganche ya está
puesto (`al_emitir` en el motor), así que es conectar y probar.

### Cómo levantar el frontend
```bash
cd frontend
npm install     # (solo la 1ª vez)
npm run dev     # http://localhost:5173
```
Diseño de referencia (boceto vivo): la piel salió de una maqueta iterada; el sistema (paleta pavo real teal+oro, Adwaita Sans + JetBrains Mono, estilo Linear) vive en `src/index.css`. **Pendiente:** el logo del pavo real es un placeholder dibujado en SVG → reemplazar por un vector pulido cuando esté.
