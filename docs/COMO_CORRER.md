# CÓMO CORRER Argos

> Guía para levantar el proyecto de cero. Para entender qué es cada carpeta, ver
> [`./ARQUITECTURA.md`](./ARQUITECTURA.md).

Argos tiene **tres patas** que se levantan por separado. Hoy (Fase 0) cada una corre sola; todavía
no están conectadas entre sí. El orden recomendado es: **infra → backend → frontend**.

## Requisitos

| Herramienta | Para qué | Nota |
|---|---|---|
| **Docker** | La base de datos (TimescaleDB) | Control manual: `docker-on` / `docker-off` |
| **uv** | Gestionar el backend Python | Fija Python **3.13** (no usar 3.14 del sistema) |
| **Node + npm** | El frontend (Vite) | Probado con Node 26 / npm 11 |

Puertos que usa: **5432** (base de datos) · **8000** (API backend) · **5173** (frontend).

---

## 1. Base de datos (infra)

```bash
docker-on                       # encender Docker (alias personal)
cd infra
cp .env.example .env            # solo la 1ª vez; poné una contraseña real
docker compose up -d --wait     # levanta TimescaleDB
docker compose ps               # debe verse "healthy"
```

Para apagarla: `docker compose down` (los datos sobreviven en el volumen `argos_pgdata`).

## 2. Backend (FastAPI)

```bash
cd backend
uv sync                                              # instala dependencias (1ª vez)
uv run uvicorn app.main:app --reload --port 8000     # arranca la API
```

Verificar:
- http://localhost:8000/health → `{"status":"ok","service":"argos-backend"}`
- http://localhost:8000/docs → documentación interactiva (Swagger)

## 3. Frontend (React + Vite)

```bash
cd frontend
npm install     # instala dependencias (1ª vez)
npm run dev     # arranca el servidor de desarrollo
```

Abrir **http://localhost:5173** → deberías ver el panel de Argos (nav, gráfico, favoritos, chat).

Otros comandos útiles del frontend:
```bash
npm run build     # compila para producción (typecheck + bundle en dist/)
npm run preview   # sirve el build de producción para probarlo
```

---

## Cositas a tener en cuenta (gotchas)

- **Docker no autoarranca**: si algo de la BD falla, revisá que Docker esté encendido (`docker-on`).
- **Python 3.13**: el backend está fijado a 3.13 con `uv` (el 3.14 del sistema no tiene todos los
  wheels). `uv` lo maneja solo; no uses el Python global.
- **`.env` de infra**: no se sube a git. Si clonás el repo en otra máquina, copiá `.env.example` a
  `.env` y poné la contraseña.
- **Datos mock en el frontend**: por ahora BTC/ETH muestran números de ejemplo (en `src/data/coins.ts`).
  Se reemplazan por datos reales del backend en la Fase 1–2.
- **node_modules** y **dist/** están ignorados en git (los regeneran `npm install` / `npm run build`).
