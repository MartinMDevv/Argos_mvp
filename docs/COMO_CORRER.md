# CÓMO CORRER Argos

> Guía para levantar el proyecto de cero. Para entender qué es cada carpeta, ver
> [`./ARQUITECTURA.md`](./ARQUITECTURA.md).

Argos tiene **tres patas** que se levantan por separado. El backend usa la base de datos y sirve datos
reales, y desde el paso 2.1 el **gráfico del panel los consume en vivo** (el resto del panel sigue en
mock). El orden recomendado es: **infra → backend → frontend**, y ahora importa de verdad: sin backend,
el gráfico avisa que no hay conexión en vez de dibujar.

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
- http://localhost:8000/health → `{"status":"ok","service":"argos-backend"}` (la API está viva)
- http://localhost:8000/health/db → `{"status":"ok", ...}` con las versiones de Postgres y
  TimescaleDB (la API **llega a la base de datos**)
- http://localhost:8000/mercado/estado → el precio de BTC/ETH **ahora mismo** + el pulso de la
  ingesta (`guardados` tiene que subir; `en_espera` tiene que mantenerse bajo)
- http://localhost:8000/mercado/velas?simbolo=BTCUSDT&intervalo=1m&limite=20 → velas OHLCV
  (intervalos: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- `ws://localhost:8000/ws/mercado` → canal en vivo. Para probarlo sin frontend:
  ```bash
  uv run python -c "
  import asyncio, json
  from websockets.asyncio.client import connect
  async def main():
      async with connect('ws://localhost:8000/ws/mercado') as ws:
          for _ in range(10):
              m = json.loads(await ws.recv())
              print(m['tipo'], m.get('simbolos', ''))
  asyncio.run(main())"
  ```
- http://localhost:8000/docs → documentación interactiva (Swagger)

> **Desde el paso 1.2 la API se conecta sola a Binance al arrancar** y empieza a guardar ticks.
> Si querés trabajar sin abrir esa conexión (por ejemplo con `--reload`, que reinicia en cada cambio):
> ```bash
> INGESTA_ACTIVA=false uv run uvicorn app.main:app --reload --port 8000
> ```

Para mirar los ticks guardados directo en la base:
```bash
cd infra && set -a && . ./.env && set +a
docker exec argos_timescaledb psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*), min(momento), max(momento) FROM ticks;"
```

> Si `/health/db` devuelve **503** con `"status":"sin_conexion"`, no es un bug: es el aviso de que
> la base de datos no está arriba. Volvé al paso 1 (`docker-on` + `docker compose up -d --wait`).
> La API sigue respondiendo `/health` igual — se cae la BD, no Argos entero.

### Ver el mercado en vivo por consola (paso 1.1)

La ingesta todavía no está enchufada a la API: se prueba sola. **No necesita Docker ni base de datos**,
solo internet.

```bash
cd backend
uv run python -m app.ingesta.binance --limite 20     # muestra 20 operaciones reales y corta
uv run python -m app.ingesta.binance                 # sin límite; cortar con Ctrl+C
```

Deberías ver una línea por operación con hora, par, precio, cantidad, cuánto dinero movió y si mandó
la compra (▲) o la venta (▼). Si no sale nada, revisá la conexión a internet.

## 3. Frontend (React + Vite)

```bash
cd frontend
npm install     # instala dependencias (1ª vez)
npm run dev     # arranca el servidor de desarrollo
```

Abrir **http://localhost:5173** → deberías ver el panel de Argos (nav, gráfico, favoritos, chat).

**Con el backend arriba**, el gráfico del Panel muestra velas reales de BTCUSDT y se mueve solo. Para
comprobar que está vivo de verdad y no es una imagen: dejalo un minuto y mirá cómo la última vela cambia
de alto y de color, y cómo al cambiar de minuto nace una nueva.

Si el backend está apagado, el gráfico lo dice (`Sin conexión` / `Argos todavía no vio operaciones`)
en vez de inventar precios.

Otros comandos útiles del frontend:
```bash
npm run build     # compila para producción (typecheck + bundle en dist/)
npm run preview   # sirve el build de producción para probarlo
npx tsc -b        # solo el chequeo de tipos, sin compilar
```

> **¿El backend no está en `localhost:8000`?** Se cambia sin tocar código, con un `.env` en `frontend/`:
> ```
> VITE_API_URL=http://192.168.1.50:8000
> ```
> La dirección del WebSocket sale sola de ahí (`http://` → `ws://`). Ojo: el backend solo autoriza por
> CORS los orígenes de desarrollo, así que si movés el frontend hay que agregarlo en `app/main.py`.

---

## Cositas a tener en cuenta (gotchas)

- **Docker no autoarranca**: si algo de la BD falla, revisá que Docker esté encendido (`docker-on`).
- **Python 3.13**: el backend está fijado a 3.13 con `uv` (el 3.14 del sistema no tiene todos los
  wheels). `uv` lo maneja solo; no uses el Python global.
- **Si movés o renombrás la carpeta del proyecto, el `.venv` se rompe.** Los entornos virtuales
  guardan **rutas absolutas** dentro de sus scripts, así que `uvicorn` falla con
  `Failed to spawn: uvicorn — No such file or directory` aunque el paquete esté instalado.
  Solución: regenerarlo (es desechable, está en `.gitignore`):
  ```bash
  cd backend && rm -rf .venv && uv sync
  ```
- **`.env` de infra**: no se sube a git. Si clonás el repo en otra máquina, copiá `.env.example` a
  `.env` y poné la contraseña.
- **Todavía queda mock en el frontend**: el **gráfico** ya usa datos reales (2.1), pero la watchlist, la
  tabla de mercados y el sidebar siguen con los números de ejemplo de `src/data/coins.ts`. Se enchufan
  en el paso 2.2.
- **El gráfico arranca casi vacío si Argos se encendió recién**: solo puede dibujar lo que vio. Dale unos
  minutos, o mirá un intervalo corto (`1m`).
- **`en_espera` que no baja** en `/mercado/estado` significa que la ingesta anda pero la base no está
  recibiendo. Revisá `/health/db`. Los ticks no se pierden mientras tanto (hay 20.000 de colchón).
- **Pocas velas al principio, y con huecos**: Argos solo tiene lo que vio desde que lo encendiste, y
  cada vez que lo apagás queda un hueco en esos minutos. No se rellenan ni se inventan. Traer historia
  vieja desde Binance (backfill) es un paso posterior.
- **La última vela siempre viene con `completa: false`**: su tramo todavía no terminó y sus números van
  a seguir cambiando. No la uses como cerrada.
- **node_modules** y **dist/** están ignorados en git (los regeneran `npm install` / `npm run build`).
