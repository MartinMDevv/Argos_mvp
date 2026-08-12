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
- [ ] **2.2b** Watchlist BTC/ETH + cabecera del panel con datos reales *(jubila `src/data/coins.ts`,
  que hoy tiene precios inventados) + selector de moneda/intervalo: el gráfico está fijo en
  BTCUSDT · 1m y los botones `15m/1H/4H/1D` son decorativos*

## FASE 3 — Detectores de alertas (el corazón)
- [ ] **3.1** Framework de detectores (clase base + registro de plugins)
- [ ] **3.2** Alerta #1 Umbral de precio
- [ ] **3.3** Alerta #2 Movimiento % en ventana
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

**👉 Estamos aquí:** **Fases 0 y 1 cerradas + 2.1 y 2.1b hechos.** El backend ve el mercado, lo guarda,
lo resume en velas y lo empuja en vivo; el gráfico del Panel lo dibuja con datos reales moviéndose solo;
y con el backfill ya no tiene huecos: hay un año de historia real detrás. Siguiente: **2.2 — watchlist y
panel de estado con datos reales** (precio y cambio %), más el selector de moneda e intervalo, que jubila
lo que queda de `src/data/coins.ts`.

### Cómo levantar el frontend
```bash
cd frontend
npm install     # (solo la 1ª vez)
npm run dev     # http://localhost:5173
```
Diseño de referencia (boceto vivo): la piel salió de una maqueta iterada; el sistema (paleta pavo real teal+oro, Adwaita Sans + JetBrains Mono, estilo Linear) vive en `src/index.css`. **Pendiente:** el logo del pavo real es un placeholder dibujado en SVG → reemplazar por un vector pulido cuando esté.
