# CÓMO CORRER Argos

> Guía para levantar el proyecto de cero. Para entender qué es cada carpeta, ver
> [`./ARQUITECTURA.md`](./ARQUITECTURA.md).

Argos tiene **tres patas** que se levantan por separado. El orden recomendado es
**infra → backend → frontend**, y importa: sin backend el panel avisa que no hay conexión en vez de
dibujar. Desde el paso 4.3 **no queda nada en mock** — todo lo que se ve en pantalla sale de datos
reales o dice que no los hay.

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
cp .env.example .env            # solo la 1ª vez; pon una contraseña real
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
- http://localhost:8000/mercado/resumen → precio + cambio % (1h/24h/7d) + máx/mín/volumen del día
  de cada símbolo. Filtrable: `?simbolos=BTCUSDT&simbolos=ETHUSDT`.
  **Si un plazo sale `null` es que falta historia de ese tramo** — no es un error: espera a que termine
  la puesta al día del arranque (o corre el backfill a mano). Mira también `minutos_24h`: cuántos de los
  1.440 minutos del día tienen datos. Con menos de 1.440, el volumen es el de esos minutos y nada más.
- http://localhost:8000/mercado/volatilidad → cuánto se agita normalmente cada activo: el rango
  verdadero mediano de un tramo de 5 min en las últimas 24 h. **Es la misma medida que usa la alerta
  #3**, a propósito: si el panel midiera distinto que el detector, las dos pantallas dirían cosas
  distintas del mismo mercado. Un símbolo con menos de 5 h de datos no aparece (es un "no sé").
- `ws://localhost:8000/ws/mercado` → canal en vivo. Empuja precios (`estado`), señal de vida
  (`latido`) y, desde el paso 4.2, cada **alerta** en cuanto se emite. Para probarlo sin frontend:
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
- http://localhost:8000/detectores → qué vigila Argos y con qué cadencia, más el pulso del motor.
  Si escribiste un detector en `app/detectores/` y **no aparece acá**, no se registró: lo más
  probable es que le falte el decorador `@registrar`. Mira también `silenciadas`: son alertas
  correctas que repetían algo ya dicho, así que un número alto es el antirruido funcionando.
  Lo mismo se ve **sin terminal** en la vista Configuración del panel (paso 4.3).
- http://localhost:8000/alertas → lo que Argos vio, de lo más nuevo a lo más viejo.
  Filtrable: `?simbolo=BTCUSDT`, `?detector=umbral_precio`, `?limite=100`.
  Cada alerta trae su `evidencia`: los números crudos con los que el detector concluyó, para que
  puedas rehacer la cuenta. En el panel es la vista **Alertas**, donde cada una se abre y muestra
  esa cuenta sin pasar por la API (paso 3.6).
- http://localhost:8000/umbrales → los precios que pediste vigilar (alerta #1, paso 3.2).
  Para agregar uno:
  ```bash
  curl -X POST localhost:8000/umbrales -H 'Content-Type: application/json' \
    -d '{"simbolo":"BTCUSDT","valor":"70000","direccion":"arriba","nota":"objetivo"}'
  curl -X DELETE localhost:8000/umbrales/1      # dejar de vigilarlo
  ```
  **Ojo con dos cosas.** (a) Si al crearlo el precio ya está del otro lado, no vas a recibir un aviso
  inmediato: el detector avisa cuando ve **cruzar**, y encontrarlo ya cruzado no es haberlo visto
  cruzar. (b) Si `cargado_alguna_vez` sale `false`, Argos todavía no pudo leer la tabla y la lista
  vacía **no significa que no haya umbrales**: significa que no sabemos. Se reintenta cada minuto.
- http://localhost:8000/docs → documentación interactiva (Swagger)

> **Desde el paso 1.2 la API se conecta sola a Binance al arrancar** y empieza a guardar ticks.
> Si quieres trabajar sin abrir esa conexión (por ejemplo con `--reload`, que reinicia en cada cambio):
> ```bash
> INGESTA_ACTIVA=false uv run uvicorn app.main:app --reload --port 8000
> ```
>
> Desde el 3.1 hay un interruptor equivalente para la detección, si quieres que la ingesta y el panel
> sigan andando pero nadie evalúe ni escriba alertas:
> ```bash
> DETECCION_ACTIVA=false uv run uvicorn app.main:app --reload --port 8000
> ```

### Correr las pruebas

```bash
cd backend
uv run pytest              # todo (139 pruebas, ~0,2 s)
uv run pytest -v           # con el nombre de cada una
uv run pytest pruebas/test_silencio.py    # un solo archivo
```

**No hace falta Docker ni internet**, y eso no es un detalle de comodidad: los detectores están
diseñados como funciones puras de su contexto justamente para que se puedan probar así (y, más
adelante, correr sobre la historia para medir si aciertan). Si algún día una prueba de detectores
empieza a necesitar la base, hay que mirar qué se rompió en el diseño antes de levantarla.

### Traer la historia que Argos no vivió (paso 2.1b)

Argos solo tiene lo que escuchó desde que lo encendiste. Para que el gráfico se vea continuo —y sobre
todo para que los detectores de la Fase 3 tengan con qué comparar— se baja la historia real de Binance.

**Desde el paso 3.3b esto pasa solo**: al arrancar la API, Argos le pide a Binance los minutos que se
perdió mientras estuvo apagado. Corre en segundo plano (no retrasa el arranque) y reintenta si la base
o la red todavía no están, así que **no hay que acordarse de nada**. Se apaga con
`BACKFILL_AL_ARRANCAR=false` y se le cambia el alcance con `BACKFILL_DIAS` (365 por defecto).

Sigue estando el comando a mano, útil para pedir más historia hacia atrás de la que baja el arranque
o para poblar la base sin levantar la API:

```bash
cd backend
uv run python -m app.ingesta.backfill                             # BTC y ETH, 365 días
uv run python -m app.ingesta.backfill --simbolo BTCUSDT --dias 30 # solo BTC, 30 días
```

- Tarda **unos minutos** la primera vez (un año son ~526 pedidos por símbolo, y va despacio a propósito
  para no chocar con los límites de Binance). Después es **incremental**: solo pide lo que falta.
- **Se puede reejecutar sin miedo**: lo que ya está se descarta solo.
- Necesita la base de datos arriba. No necesita que el backend esté corriendo.
- Ocupa ~78 MB por símbolo al año (medido). Para comparar: la ingesta en vivo escribe ~75 MB **por día**.

Comprobar qué historia hay:
```bash
docker exec argos_timescaledb psql -U argos -d argos \
  -c "SELECT simbolo, count(*), min(inicio), max(inicio) FROM velas_historicas GROUP BY simbolo;"
```

Para mirar los ticks guardados directo en la base:
```bash
cd infra && set -a && . ./.env && set +a
docker exec argos_timescaledb psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*), min(momento), max(momento) FROM ticks;"
```

> Si `/health/db` devuelve **503** con `"status":"sin_conexion"`, no es un bug: es el aviso de que
> la base de datos no está arriba. Vuelve al paso 1 (`docker-on` + `docker compose up -d --wait`).
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
la compra (▲) o la venta (▼). Si no sale nada, revisa la conexión a internet.

## 3. Frontend (React + Vite)

```bash
cd frontend
npm install     # instala dependencias (1ª vez)
npm run dev     # arranca el servidor de desarrollo
```

Abrir **http://localhost:5173** → deberías ver el panel de Argos (nav, gráfico, favoritos, chat).

**Con el backend arriba**, el gráfico del Panel muestra velas reales de BTCUSDT y se mueve solo. Para
comprobar que está vivo de verdad y no es una imagen: déjalo un minuto y mira cómo la última vela cambia
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
> CORS los orígenes de desarrollo, así que si mueves el frontend hay que agregarlo en `app/main.py`.

---

## Cositas a tener en cuenta (gotchas)

- **Docker no autoarranca**: si algo de la BD falla, revisa que Docker esté encendido (`docker-on`).
- **Python 3.13**: el backend está fijado a 3.13 con `uv` (el 3.14 del sistema no tiene todos los
  wheels). `uv` lo maneja solo; no uses el Python global.
- **Si mueves o renombras la carpeta del proyecto, el `.venv` se rompe.** Los entornos virtuales
  guardan **rutas absolutas** dentro de sus scripts, así que `uvicorn` falla con
  `Failed to spawn: uvicorn — No such file or directory` aunque el paquete esté instalado.
  Solución: regenerarlo (es desechable, está en `.gitignore`):
  ```bash
  cd backend && rm -rf .venv && uv sync
  ```
- **`.env` de infra**: no se sube a git. Si clonas el repo en otra máquina, copia `.env.example` a
  `.env` y pon la contraseña.
- **Todavía queda mock en el frontend**: el **gráfico** ya usa datos reales (2.1), pero la watchlist, la
  tabla de mercados y el sidebar siguen con los números de ejemplo de `src/data/coins.ts`. Se enchufan
  en el paso 2.2.
- **El gráfico arranca casi vacío si Argos se encendió recién**: solo puede dibujar lo que vio. Dale unos
  minutos, o mira un intervalo corto (`1m`).
- **`en_espera` que no baja** en `/mercado/estado` significa que la ingesta anda pero la base no está
  recibiendo. Revisa `/health/db`. Los ticks no se pierden mientras tanto (hay 20.000 de colchón).
- **Pocas velas al principio, y con huecos**: Argos solo arma velas de lo que escuchó, y cada apagón deja
  un hueco. Desde el 3.3b **el arranque lo tapa solo** (busca `Historia al día` en el log). Si igual ves
  huecos: o la descarga todavía va en curso —un año tarda unos minutos—, o falló y está reintentando
  (aparece `No se pudo completar la historia … reintento en N s`), o alguien puso `BACKFILL_AL_ARRANCAR=false`.
- **La vela dice de dónde salió** (campo `fuente`): `propia` si la armamos con nuestros ticks, `historia`
  si vino del backfill, `mixta` si el tramo abarca las dos. Ojo con `operaciones`: en las propias son
  operaciones **agrupadas** y en las históricas son las **reales** (siempre más). No los compares entre sí.
- **La última vela siempre viene con `completa: false`**: su tramo todavía no terminó y sus números van
  a seguir cambiando. No la uses como cerrada.
- **node_modules** y **dist/** están ignorados en git (los regeneran `npm install` / `npm run build`).
