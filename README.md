# Argos 🦚

> **Tu asistente de inteligencia de mercado cripto** — *"Argos lo ve primero."*
> El guardián de cien ojos que vigila el mercado por ti: detecta lo anómalo, lo explica y te avisa.

Este repositorio contiene el **MVP** de Argos. Especificación completa (idea, metas, roadmap de
versiones y stack): [`../spec-crypto-monitor.md`](../spec-crypto-monitor.md).

## ¿Qué hace el MVP?

Vigila **BTC y ETH** en tiempo real, detecta movimientos anómalos (precio, volatilidad y volumen),
los guarda con historia, los muestra en un panel moderno y te avisa por Telegram — de bajo ruido y
a costo cero. Una IA local puede **explicarte** el estado del mercado on-demand (sin inventar números).

## Estructura del proyecto

```
Argos_MVP/
├── backend/     → El cerebro: Python + FastAPI (ingesta, base de datos, detectores, IA, notificaciones)
├── frontend/    → El panel: React + TypeScript + Vite + Tailwind (dashboard en tiempo real)
├── infra/       → Docker Compose (TimescaleDB)
├── docs/        → Documentación viva (arquitectura, guía de arranque, checklist, contexto)
└── README.md
```

Detalle de cada carpeta y del mapa de componentes del frontend:
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python + FastAPI (async) |
| Base de datos | TimescaleDB (Postgres) en Docker |
| IA local | Ollama (modelo 7-8B cuantizado, GPU) |
| Notificaciones | Telegram (aiogram) + panel |
| Frontend | React + TypeScript + Vite + Tailwind |
| Gráficos | TradingView lightweight-charts |

## Estado

🚧 **En construcción — Fases 0, 1, 2 y 3 cerradas; Fase 4 (avisos) en marcha.**

La cadena anda de punta a punta: Argos escucha el WebSocket de Binance, guarda cada operación en
TimescaleDB, la resume en velas y se las empuja al panel, que las dibuja moviéndose en vivo. Tiene un
año de historia real traída de Binance, así que el gráfico no arranca vacío ni con huecos, y todo el
panel usa datos reales.

**Las cuatro alertas del MVP funcionan**, y las tres últimas no dependen de que uno sepa qué número
mirar: umbral de precio (el que pones tú), movimiento fuerte, volatilidad anómala y volumen anómalo.
Los detectores son plugins —agregar uno es crear un archivo—, cada alerta se guarda con los números
que la justifican y un antirruido evita contar veinte veces la misma noticia.

Los umbrales de cada detector **no se eligieron a ojo**: salieron de correrlos sobre un año de
historia real hasta dejarlos en unas diez alertas al mes por activo. El panel muestra cada hallazgo
con su evidencia, avisa en el momento por WebSocket, y no queda ni un dato inventado en la app.

Falta que Argos te encuentre **fuera de la pantalla** (Telegram) y que la IA local ponga en palabras
lo que ve. Después, el panel de
alertas, Telegram y la IA que explica.

Estado tildable en [`docs/CHECKLIST.md`](docs/CHECKLIST.md).

## Cómo levantarlo

Guía completa (requisitos, orden, gotchas): [`docs/COMO_CORRER.md`](docs/COMO_CORRER.md). En corto:

```bash
# 1. Base de datos (requiere Docker encendido: docker-on)
cd infra
cp .env.example .env          # (solo la 1ª vez) y pon una contraseña
docker compose up -d --wait   # levanta TimescaleDB
docker compose ps             # debe verse "healthy"

# 2. Backend (Python + FastAPI, gestionado con uv)
cd backend
uv sync                                              # instala dependencias
uv run uvicorn app.main:app --reload --port 8000     # arranca la API
# Verificar: http://localhost:8000/health  y  http://localhost:8000/docs

# 3. Frontend (React + Vite)
cd frontend
npm install                   # (solo la 1ª vez)
npm run dev                   # http://localhost:5173  → el panel de Argos
```

---

*Argos es una herramienta personal de contexto e información. No es consejo financiero: da números y
contexto, la decisión siempre es tuya.*
