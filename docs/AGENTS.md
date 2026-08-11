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
solo para los orígenes de desarrollo (nunca `*`). Siguiente: **2.1 = gráfico de velas en vivo en el
frontend** (reemplazar el mock de `src/data/coins.ts`).
Estado tildable en CHECKLIST.md. Norte: MVP (v1.0) primero; el mercado se expande por versiones (v1.1 -> v5.0)
hasta un posible producto con suscripción. El motor del MVP se reutiliza en cada fase, no se reescribe.
Pendiente de diseño: el logo del pavo real es un placeholder SVG → reemplazar por un vector pulido.

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
