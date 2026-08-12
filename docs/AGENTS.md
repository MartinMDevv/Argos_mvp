# AGENTS.md — Contexto del agente · Argos

Punto de entrada de contexto: léelo primero y siempre. Solo lo esencial + el índice (§9); salta a
un doc enlazado solo cuando necesites su detalle. Mantener corto.

## 1. Qué es
Argos: asistente personal de inteligencia de mercado cripto. Vigila en tiempo real, detecta lo
anómalo (precio/volatilidad/volumen), lo explica y avisa. Lema: "Argos lo ve primero".

## 2. Regla de oro (inviolable)
La IA nunca inventa números. Probabilidades/porcentajes salen de estadística sobre datos históricos
reales; la IA solo los traduce a lenguaje natural. Sin dato, decir "no hay dato"; no suponer.

## 3. Guardarraíles
- Foco MVP = solo BTC/ETH. Memecoins/Solana/on-chain/social/portafolio = "fase futura": se anotan, no se implementan.
- Ideas de panel anotadas para v1.1 (medidor de veredicto técnico estilo TradingView, rejilla de rendimiento
  por plazo, key stats, estacionalidad): están en el spec §2.F. El medidor NO puede aconsejar: muestra qué
  dicen los indicadores calculados sobre datos reales, y de qué está hecho. No implementar todavía.
- No inventar APIs, endpoints, columnas de BD, librerías ni datos; verificar contra código/docs reales. Ante duda, decirlo.
- Bajo ruido > volumen de alertas.
- Cambios pequeños y verificables, cada paso con un check concreto.
- No es consejo financiero: contexto y números; decide el usuario.

## 4. Estilo de trabajo
Español, didáctico paso a paso, comentarios de código en español. Explicar antes de ejecutar;
confirmar antes de commitear. Sin firma de Claude / Co-Authored-By. Docker manual (docker-on/off;
no systemctl enable). Ritmo por paso: explico -> construyo -> verificamos -> commiteas.

## 5. Stack
Python + FastAPI (async) · TimescaleDB (Docker) · detectores como plugins (numpy/scipy) ·
Ollama (7-8B cuantizado, RTX 3060) · aiogram (Telegram) · React + TS + Vite + Tailwind ·
lightweight-charts · Docker Compose.

## 6. Arquitectura
Monolito modular, fronteras limpias. Detectores como plugins (agregar = enchufar, no reescribir).
Núcleo agnóstico de usuario (multiusuario/suscripción se añade encima, después).

## 7. Estado y norte
**Fase 0 (cimientos) COMPLETA** (0.1-0.5): esqueleto + git; TimescaleDB viva; frontend
React+Vite+Tailwind con la piel de Argos; backend FastAPI conectado a la BD (pool **asyncpg**, sin
ORM; config desde `infra/.env`; `/health` = API viva, `/health/db` = llega a la BD).
**1.1 HECHO**: ingesta en vivo de Binance (`app/ingesta/binance.py`), stream `aggTrade` de BTC/ETH ->
modelo `Tick` (`app/modelos.py`, precios en `Decimal`, UTC). El módulo solo escucha y traduce: entrega
cada tick a un consumidor que recibe por parámetro.
**1.2 HECHO**: cada tick va a dos destinos: memoria (`app/estado.py` = el ahora, responde al instante) y
TimescaleDB (`sql/001_ticks.sql`, hypertable `ticks` = la historia). Escritura por lotes en
`app/ingesta/almacen.py` con `executemany` + `ON CONFLICT DO NOTHING` (COPY se descartó: no admite
ON CONFLICT y la dedup al reconectar no es negociable). La ingesta arranca con la API (`INGESTA_ACTIVA=false`
para apagarla); si la BD se cae los ticks esperan en memoria (tope 20.000) y entran solos al volver.
Endpoint `GET /mercado/estado`.
**1.3 HECHO**: velas OHLCV en `app/velas.py` con `time_bucket` + `first`/`last` de Timescale (la agregación
la hace la BD, no Python); intervalos 1m/5m/15m/1h/4h/1d; `GET /mercado/velas`. **Ojo con dos cosas que
costaron encontrar:** (a) apertura y cierre se ordenan por `id_operacion` y NO por `momento`, porque Binance
manda operaciones con el mismo milisegundo y el desempate por tiempo hacía el cierre no determinista (~6% de
las velas); (b) una vela se marca `completa` recién 5 s después de cerrar el tramo (`MARGEN_ASENTADO`), porque
el escritor vuelca de a lotes cada 2 s y si no la bandera mentiría en el borde. Verificado contra las velas
oficiales de Binance: idénticas al octavo decimal. Argos NO tiene historia anterior a su primer arranque
(backfill = fase futura).
**1.4 HECHO → FASE 1 COMPLETA**: `app/difusion.py` + `WS /ws/mercado`. El panel se conecta y el backend le
empuja: `bienvenida` (foto al conectarse), `estado` (cuando cambia algo, máximo cada 0,5 s) y `latido`
(cada 15 s de silencio, para distinguir conexión viva de conexión muerta). NO se manda cada tick: bajo
ruido, ~1,6 msg/s en vez de ~40. Envíos en paralelo para que un panel lento no frene a los demás. CORS
solo para los orígenes de desarrollo (nunca `*`).
**2.1 HECHO**: el gráfico del Panel usa datos reales. `src/lib/api.ts` (puente REST + tipos de la API),
`src/lib/mercado.tsx` (`ProveedorMercado`: UNA conexión WebSocket para toda la app, montada en `main.tsx`;
reconexión con espera creciente igual que con Binance) y `CandleChart.tsx` reescrito con
**lightweight-charts v5** (ojo: la API v5 es `chart.addSeries(CandlestickSeries, …)`, no
`addCandlestickSeries()`). **Decisión clave:** la historia sale de `/mercado/velas` (verdad) y el WebSocket
mueve la vela en curso (inmediatez), pero cada 10 s se le vuelve a preguntar a la base y se corrige —
entre dos fotos del WebSocket puede escaparse un pico, y el máximo de una vela no se aproxima. Máx/mín se
combinan con `Math.max`/`Math.min` para que ninguna fuente achique a la otra. Si no hay datos se dice, no
se inventa. Gráfico fijo en BTCUSDT · 1m. Siguen en mock watchlist/tabla/sidebar.
**2.1b HECHO (backfill, no estaba en el plan)**: Argos ya NO empieza sin memoria. `sql/002_velas_historicas.sql`
(tabla aparte, **una kline NO es un tick**: meterlas en `ticks` obligaría a inventar operaciones y envenenaría
los detectores de volumen) + `app/ingesta/backfill.py` (pagina `api/v3/klines`, 1.000 por pedido, mira
`x-mbx-used-weight-1m` y respeta `Retry-After`; **nunca guarda la vela en curso**) + fusión en `velas.py`.
Se descarga **solo 1m**; el resto se agrega. Regla de desempate: **minuto cerrado → manda la vela de Binance**
(la nuestra puede estar mocha si Argos arrancó a mitad); **minuto en curso → siempre nuestro**. Cada vela dice
su `fuente` (`propia`/`historia`/`mixta`) porque `operaciones` NO se cuenta igual en ambas (aggTrades vs reales).
Correr: `uv run python -m app.ingesta.backfill --simbolo BTCUSDT ETHUSDT --dias 365` (incremental).
**2.2a HECHO (backend del resumen)**: `app/resumen.py` + `GET /mercado/resumen` → precio, cambio %
(1h/24h/7d), máx/mín y volumen del día. Junta memoria (el ahora) con la base (la historia). **El ancla
mira las TRES fuentes** —ticks, historia y el tick vivo en memoria—: con Argos recién encendido tras dos
días apagado, la memoria tiene el precio de ahora y la base llega a hace dos días, y un "24h" anclado en
la base mostraría un cambio de tres días sin que se note. Cada plazo lleva **tolerancia** (5 min / 30 min
/ 3 h ≈ 2% del plazo); si el cierre más cercano queda más lejos, el cambio va **`null`**, nunca cero ni
aproximado. Los ticks se escanean **solo desde donde termina el backfill** (misma regla de desempate que
`velas.py`): medido con `EXPLAIN ANALYZE`, 1.766 filas en vez de ~500.000, y entra como condición del
índice. `minutos_24h` viaja con el volumen para que no se lea como el volumen del día cuando falta
cobertura. Verificado contra `/api/v3/ticker/24hr`: máx/mín idénticos al octavo decimal, volumen a
0,006%, cambio % a 0,01 pp. ⚠️ Los plazos están escritos a mano en dos lados (`PLAZOS` y `SQL_RESUMEN`).
**2.2b HECHO → FASE 2 COMPLETA**: todo el panel usa datos reales. `src/data/coins.ts` **eliminado**.
Nuevos: `lib/activos.ts` (catálogo par ↔ símbolo corto: **un activo se identifica SIEMPRE por su par**
`BTCUSDT`; `BTC` es solo para mostrar), `lib/formato.ts` (números es-CL vía `Intl`, signo `−` U+2212, y
`SIN_DATO` = `—` cuando no hay dato — **nunca un cero**, que afirmaría "no se movió"), `lib/resumen.tsx`
(UN pedido cada 10 s para toda la app, misma lógica que el proveedor del WebSocket) y `Sparkline.tsx`
(curvas con velas reales; las de antes eran polilíneas escritas a mano — un gráfico inventado es peor
que un número inventado, porque no se verifica, se cree). **El % se recalcula en el navegador** contra
el precio vivo usando la `referencia` que manda el backend: si no, el precio se movería y el porcentaje
de al lado quedaría clavado 10 s. Verificado: el recalculado sale idéntico al del backend. El gráfico ya
no está fijo en BTCUSDT · 1m y los botones de tramo salen de `INTERVALOS`. **Bug que apareció al
verificar**: el rango de 24 h de ETH salía `1,9K – 1,9K` (dos números distintos, mismo texto) → cifras
significativas. Sigue en mock solo `PriceVolChart` (la tarjeta lo dice) y la volatilidad σ → Fase 3.
**2.2c HECHO (primera pasada real por el navegador + auditoría de diseño)**: tres bugs y una escala de
color. Los dos gotchas de React están abajo porque se repiten. Además: seleccionar un activo **ya no
salta al Panel** —desde Mercados se elige otra moneda para comparar KPIs y el salto expulsaba de la
tabla—; elegir cambia de QUÉ se habla, no DÓNDE se mira. El pin se aplastaba porque estaba envuelto en
un `span` sin `flex:none` para cortar el clic → ahora el corte lo hace el propio `Pin`. Y la auditoría
con **`ui-ux-pro-max`** (instalada como plugin) encontró que `--faint` daba **2,69:1** contra el mínimo
de 4,5:1 de WCAG y era el color de casi todas las etiquetas: la escala de tintas se rehizo en cuatro
escalones con **`--ghost` reservado para lo que NO es información**. Detalle y tabla de contrastes en
`ARQUITECTURA.md` → "La escala de tintas, medida". ⚠️ Ojo con esa skill: su `--design-system` devuelve
patrones de *landing page* y no sirve para Argos — lo útil son sus dominios `ux`, `react` y `chart`.
**3.1 HECHO (framework de detectores)**: paquete `app/detectores/` — `base.py` (clase `Detector`,
`ContextoDeEvaluacion`, las dos cadencias), `registro.py` (`@registrar` + descubrimiento automático de
la carpeta: **crear el archivo ES darlo de alta**, no hay lista que mantener), `silencio.py`, `motor.py`,
`almacen.py`. Modelo `Alerta` en `modelos.py`, tabla en `sql/003_alertas.sql` (**tabla normal, no
hypertable**: las alertas son pocas por diseño), endpoints `GET /detectores` y `GET /alertas`, ajuste
`DETECCION_ACTIVA`. **Decisión de fondo: un detector es una función pura de su contexto** — `evaluar()`
no es `async` y no toca la BD; recibe todo cargado y devuelve `Alerta | None`. Motivo fuerte: la v2.0
pide backtesting de las propias alertas, y un detector que sale a buscar datos mira el "ahora" y no se
puede rebobinar. Si mañana hace falta una fuente nueva, la carga el MOTOR y la agrega al contexto.
**Dos cadencias = las dos capas del spec**: `POR_TICK` cuelga del consumidor de la ingesta (sin `await`,
sin BD) y `POR_VELA_CERRADA` es tarea de fondo que despierta cada 5 s a preguntar si cerró vela. El
registro **rechaza al arrancar** un `POR_TICK` que pida historia (se callaría para siempre sin que se
note). **El antirruido vive en el motor, no en cada detector**: agrupa por la `clave` de la alerta (la
identidad de la SITUACIÓN) y se precarga desde la tabla al arrancar — sin eso, reiniciar sería saltarse
el silencio, y con `--reload` pasaría en cada cambio de código. Toda alerta viaja con `evidencia` (los
números crudos, como texto): la regla de oro hecha estructura. Emitir y guardar están separados por una
cola con reintento. **Verificado**: 35 comprobaciones sin BD ni red; en vivo 230 ticks → 4 alertas +
226 silenciadas; con TimescaleDB caída 25 s, 2 alertas en cola, `/alertas` 503 con mensaje, y al volver
entraron solas (14 emitidas = 14 guardadas, 0 descartadas). ⚠️ `detectores/humo.py` son dos andamios de
verificación y **se borran en el 3.2**.
**3.1b HECHO (primeras pruebas del proyecto, no estaba en el plan)**: `backend/pruebas/` con pytest en
el grupo `dev` del pyproject (no toca las dependencias de producción). **57 pruebas en 0,06 s, sin
Docker ni internet** — verificado apuntando `POSTGRES_HOST` a un host inexistente. Que no necesiten la
base ES la comprobación del diseño: si una prueba de detectores empieza a pedirla, mirar qué se rompió
antes de levantarla. Dos decisiones a no deshacer: (a) **las pruebas definen sus propios detectores**
(en `conftest.py`) y no usan los de `humo.py`, que se borra en el 3.2; (b)
`test_todos_los_detectores_de_verdad_cumplen_las_reglas` recorre la carpeta **sin nombrar a nadie** y
verifica los invariantes, así que cubre gratis a cada detector futuro. Correr: `cd backend && uv run pytest`.
**3.2 HECHO (alerta #1, umbral de precio — el primer detector real)**: `detectores/umbral_precio.py`
+ `detectores/umbrales.py` (la configuración: copia en memoria + tabla `sql/004_umbrales.sql`) +
`GET/POST/DELETE /umbrales`. **`detectores/humo.py` BORRADO**. **La idea central: cruzar no es estar.**
`if precio > umbral` sigue siendo verdad mientras el precio se quede arriba → avisaría en bucle; lo que
se detecta es la TRANSICIÓN. Para eso el detector recuerda **de qué lado vio el precio la última vez**
— la única memoria que se permite, y no rompe la reproducibilidad (misma secuencia de ticks → mismas
alertas). **Recién despierto NO inventa un cruce**: si Argos arranca con el precio ya del otro lado,
anota el lado y se calla; encontrarlo cruzado no es haberlo visto cruzar (verificado en vivo). **La
línea pertenece al lado de abajo**, para que "sube de 70.000" (avisa a 70.000,01) y "baja de 3.400"
(avisa al tocar 3.400) digan las dos la verdad. Contra el precio que baila sobre la línea actúa el
silencio del motor, no una histéresis: medido en vivo, **11 cruces reales silenciados**. Los umbrales
se recargan de la tabla **cada 60 s** además de al crearlos por la API, porque si la base está caída al
arrancar el detector vigilaría nada y eso no se nota solo (`cargado_alguna_vez` lo distingue de "no hay
umbrales"). **Dos bugs cazados**: (a) el lado visto se actualizaba DENTRO del bucle → con dos umbrales
sobre el mismo número el segundo nunca veía el cruce (lo encontró una prueba; ahora son 3 fases:
calcular lados → emitir → recordar); (b) "cruzó 63834 (venía de 63834)" — cierto pero ilegible, y
frecuente porque los umbrales van en números redondos.
**3.2b HECHO (corrección al 3.1)**: `Detector.evaluar()` devuelve **`list[Alerta]`**, ya no
`Alerta | None`. Con umbrales en 70.000 y 71.000, un tick de 69.900 a 71.200 cruza los dos y el segundo
quedaba marcado como visto sin haber avisado nunca. Se cambió con 2 detectores en el repo y no con 5.
**Siguiente: 3.3 (alerta #2, movimiento % en ventana — el primero `POR_VELA_CERRADA`).**
Estado tildable en CHECKLIST.md. Norte: MVP (v1.0) primero; el mercado se expande por versiones (v1.1 -> v5.0)
hasta un posible producto con suscripción. El motor del MVP se reutiliza en cada fase, no se reescribe.
Pendiente de diseño: el logo del pavo real es un placeholder SVG → reemplazar por un vector pulido.

## Gotchas que ya nos mordieron (leer antes de tocar el frontend)

- **`dangerouslySetInnerHTML`: el objeto va FUERA del componente.** React compara esa prop por
  **identidad del objeto**, no por el string que lleva adentro. Escrito como
  `dangerouslySetInnerHTML={{ __html: … }}` dentro del render, es un objeto nuevo en cada pasada →
  React reescribe el `innerHTML` del SVG entero → nodos nuevos → **las animaciones CSS arrancan de
  cero**. Síntoma: "el logo se anima todo el rato". Estaba en `Peacock`, `Radar`, `IsoLayers` y
  `CoinLogo` desde el paso 0.4 y no se veía porque esos árboles se renderizaban una vez; lo destapó
  el 2.2b, al poner datos en vivo en el menú y en la tabla (render cada 0,5 s).
- **lightweight-charts no acepta actualizar hacia atrás.** Al cambiar de intervalo, el efecto que
  trae la historia sale a la red (asíncrono) y el que mueve la vela en curso corre enseguida, en el
  mismo commit: mandaba el precio vivo ya ubicado en el tramo NUEVO a una serie que todavía tenía
  dibujado el viejo. Excepción → sin error boundary React desmonta la app → **pantalla negra**. Se
  resuelve con la marca `datosDe` en `CandleChart.tsx`: de qué símbolo e intervalo son las velas que
  la serie muestra ahora mismo.
- **La regla `data/` del `.gitignore` no estaba anclada** y se comía `frontend/src/data/`. Resultado:
  el frontend **no compilaba desde un clon limpio** desde el paso 0.4, y nadie se enteró porque en la
  máquina de trabajo el archivo estaba. Ya está anclada a `/data/`. Moraleja: al agregar una carpeta
  con nombre genérico al `.gitignore`, anclarla a la raíz.
- **`pkill -f "uvicorn"` se mata a sí mismo**: el patrón coincide con la propia línea de comando del
  shell que lo ejecuta. Usar `pgrep -f "app.main:app"` y matar por PID.

## 8. Índice de documentos
Salta a un doc solo si necesitas su detalle. Conforme avance el proyecto se agregan aquí los MD de avance.

| Documento | Qué contiene | Cuándo saltar |
|---|---|---|
| [`../../spec-crypto-monitor.md`](../../spec-crypto-monitor.md) | Spec completo: idea, metas, MVP, taxonomía de alertas, stack, roadmap v1→v5 | Dudas de alcance, diseño o el "por qué" de una decisión |
| [`./CHECKLIST.md`](./CHECKLIST.md) | Dinámica de trabajo + pasos tildables del MVP | Saber qué toca ahora o el estado de avance |
| [`./ARQUITECTURA.md`](./ARQUITECTURA.md) | Distribución del repo (backend/frontend/infra) + mapa de componentes del frontend | Ubicar dónde vive algo o cómo se conectan las patas |
| [`./COMO_CORRER.md`](./COMO_CORRER.md) | Requisitos + comandos para levantar cada pata + gotchas | Arrancar el proyecto o recordar un comando |
| [`../README.md`](../README.md) | Presentación del repo, estructura y cómo levantarlo | Onboarding rápido o comandos de arranque |
| *(avance-fase-N.md)* | *(Notas de avance por fase — se enlazan aquí al crearlas)* | Detalle de lo hecho en una fase concreta |
