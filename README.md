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
├── frontend/    → El panel: React + TypeScript (dashboard en tiempo real)
├── infra/       → Docker Compose (TimescaleDB)
├── .gitignore
└── README.md
```

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

🚧 **En construcción — Fase 0 (cimientos).** Aún no hace nada útil; se está montando la base.

## Cómo levantarlo (se irá completando)

```bash
# 1. Base de datos (requiere Docker encendido: docker-on)
cd infra
cp .env.example .env          # (solo la 1ª vez) y poné una contraseña
docker compose up -d --wait   # levanta TimescaleDB
docker compose ps             # debe verse "healthy"

# 2. Backend (Python + FastAPI, gestionado con uv)
cd backend
uv sync                                              # instala dependencias
uv run uvicorn app.main:app --reload --port 8000     # arranca la API
# Verificar: http://localhost:8000/health  y  http://localhost:8000/docs

# 3. Frontend (se agrega en el paso 0.4)
#    cd frontend && ...
```

---

*Argos es una herramienta personal de contexto e información. No es consejo financiero: da números y
contexto, la decisión siempre es tuya.*
