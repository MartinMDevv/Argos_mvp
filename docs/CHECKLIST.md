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
- [ ] **0.4** Esqueleto **React + Vite + Tailwind** → `localhost:5173` muestra la página de Argos
- [ ] **0.5** Conexión backend ↔ base de datos verificada (FastAPI le habla a TimescaleDB)

## FASE 1 — Motor de datos en tiempo real
- [ ] **1.1** WebSocket de Binance para BTC/ETH → ticks por consola
- [ ] **1.2** Persistir ticks en TimescaleDB (hypertable) + "último estado" en memoria
- [ ] **1.3** Armar velas (candles) por agregación + endpoint REST para consultarlas
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

**👉 Estamos aquí:** listos para el **paso 0.4 — esqueleto React + Vite + Tailwind**.
