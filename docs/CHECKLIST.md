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
- [ ] **1.4** WebSocket del backend que empuja precios en vivo al frontend

## FASE 2 — Dashboard base
- [ ] **2.1** Gráfico de velas (lightweight-charts) actualizándose en vivo
- [ ] **2.2** Watchlist BTC/ETH + panel de estado (precio, cambio %)

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

**👉 Estamos aquí:** **Fase 0 cerrada** (0.1 a 0.5) y **1.1, 1.2 y 1.3 hechos**: el dato real entra,
queda guardado, y ya se puede pedir en forma de velas listas para dibujar. Siguiente:
**1.4 — WebSocket propio del backend que empuja los precios al frontend**, para que el panel deje de
preguntar y pase a recibir.

### Cómo levantar el frontend
```bash
cd frontend
npm install     # (solo la 1ª vez)
npm run dev     # http://localhost:5173
```
Diseño de referencia (boceto vivo): la piel salió de una maqueta iterada; el sistema (paleta pavo real teal+oro, Adwaita Sans + JetBrains Mono, estilo Linear) vive en `src/index.css`. **Pendiente:** el logo del pavo real es un placeholder dibujado en SVG → reemplazar por un vector pulido cuando esté.
