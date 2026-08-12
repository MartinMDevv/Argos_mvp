"""Escucha en vivo el mercado de Binance por WebSocket (paso 1.1).

## Qué hace
Abre UNA conexión permanente a Binance y se queda escuchando las operaciones de BTC y ETH
a medida que ocurren. Cada operación se traduce a un `Tick` (ver `app.modelos`) y se le
entrega a quien la haya pedido.

## Por qué WebSocket y no preguntar cada X segundos
Preguntar en bucle ("¿y ahora cuánto vale?") llega tarde y gasta cuota de la API. Con un
WebSocket la conexión queda abierta y es Binance quien nos empuja el dato en el momento en
que pasa. Argos tiene que ver primero: esto es lo que lo hace posible.

## Por qué el stream `aggTrade` y no `trade`
Cuando alguien lanza una orden grande, el exchange la ejecuta contra muchas órdenes chicas
del libro y genera decenas de `trade` idénticos en el mismo milisegundo y al mismo precio.
`aggTrade` los junta en un solo evento. Es el mismo hecho económico, con mucho menos ruido
y menos filas que guardar después. Sirve igual para precio, volumen y velas.

## Frontera de responsabilidad
Este módulo SOLO escucha y traduce. No guarda en la base de datos ni decide alertas: le pasa
cada tick a una función que recibe por parámetro (`al_recibir`). Hoy, en el paso 1.1, esa
función solo imprime por consola; en el 1.2 va a ser la que escribe en TimescaleDB, y este
archivo no va a cambiar. Esa es la idea.

## Cómo probarlo a mano
    cd backend
    uv run python -m app.ingesta.binance --limite 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.modelos import Tick

logger = logging.getLogger(__name__)

# Endpoint público de datos de mercado. No necesita cuenta ni API key: son datos abiertos.
URL_STREAM_BINANCE = "wss://stream.binance.com:9443/stream"

# El MVP mira solo estos dos (guardarraíl del proyecto: memecoins y compañía son fase futura).
SIMBOLOS_MVP: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")

# --- Freno para no hacernos banear al reconectar ---
# Binance corta la IP que intenta conectarse más de 300 veces en 5 minutos. Si la conexión
# se cae y reintentamos al toque, entramos en un bucle que se come esa cuota en segundos y
# nos deja fuera del mercado justo cuando más lo necesitamos. Por eso: si una conexión se
# cortó enseguida, esperamos cada vez más antes de reintentar.
SEGUNDOS_ESPERA_BASE = 1.0
SEGUNDOS_ESPERA_MAXIMA = 60.0
# Una conexión que aguantó más que esto se considera sana: el corte fue un hecho aislado
# (Binance recicla conexiones cada 24h) y no un problema de fondo, así que reseteamos la espera.
SEGUNDOS_CONEXION_SANA = 60.0

# Firma de la función que recibe cada tick. Es async porque el consumidor real (paso 1.2)
# va a escribir en la base de datos, y eso se espera.
Consumidor = Callable[[Tick], Awaitable[None]]


def armar_url(simbolos: Sequence[str]) -> str:
    """Arma la URL del stream combinado: los dos símbolos por UNA sola conexión.

    Binance permite pedir varios streams a la vez separándolos con `/`. Conviene: una
    conexión sola es menos que mantener, menos que reconectar y menos límite que gastar.
    """
    streams = "/".join(f"{simbolo.lower()}@aggTrade" for simbolo in simbolos)
    return f"{URL_STREAM_BINANCE}?streams={streams}"


def parsear_mensaje(mensaje: str | bytes) -> Tick | None:
    """Traduce un mensaje crudo de Binance a un `Tick` nuestro.

    Devuelve None (en vez de reventar) si el mensaje no es una operación: Binance también
    manda respuestas de control y, si algún día agregamos otro stream, llegarán eventos de
    otro tipo por el mismo cable.

    Así se ve un evento aggTrade dentro del sobre del stream combinado:
        {"stream": "btcusdt@aggTrade",
         "data": {"e": "aggTrade", "s": "BTCUSDT", "a": 1234, "p": "118432.15",
                  "q": "0.00412", "T": 1786422603543, "m": false, ...}}
    """
    sobre = json.loads(mensaje)

    # Con stream combinado el evento viene envuelto en "data"; con stream simple viene pelado.
    # Aceptamos las dos formas para que la función sirva en ambos casos.
    dato = sobre.get("data", sobre)

    if dato.get("e") != "aggTrade":
        return None

    return Tick(
        simbolo=dato["s"],
        # OJO: Decimal(str) y no Decimal(float). Binance manda "118432.15" como texto
        # justamente para que no se pierda precisión; pasar por float la destruiría.
        precio=Decimal(dato["p"]),
        cantidad=Decimal(dato["q"]),
        # "T" son milisegundos desde 1970 en UTC. Guardamos siempre en UTC y con zona
        # explícita: un dato de mercado sin zona horaria es una bomba de tiempo.
        momento=datetime.fromtimestamp(dato["T"] / 1000, tz=UTC),
        id_operacion=dato["a"],
        comprador_pasivo=dato["m"],
    )


async def escuchar_ticks(
    al_recibir: Consumidor,
    simbolos: Sequence[str] = SIMBOLOS_MVP,
) -> None:
    """Se conecta a Binance y le entrega cada operación a `al_recibir`. No termina nunca.

    Reconexión: `async for ws in connect(...)` es la forma que trae la librería `websockets`
    para reconectar sola. Hace falta de verdad, no es paranoia: Binance corta las conexiones
    cada 24 horas por diseño, y el wifi se cae. Argos tiene que aguantar la noche sin que
    nadie lo mire.

    Ahora bien, esa reconexión automática NO espera nada cuando el servidor cierra bien: si
    Binance nos rechazara en el saludo, reintentaríamos decenas de veces por segundo y nos
    ganaríamos un baneo de IP. Por eso medimos cuánto duró cada conexión y, si fue corta,
    frenamos cada vez más antes de volver a intentar.

    Para detenerlo, cancelá la tarea que lo ejecuta (`tarea.cancel()`).
    """
    url = armar_url(simbolos)
    espera = SEGUNDOS_ESPERA_BASE
    logger.info("Conectando a Binance → %s", ", ".join(simbolos))

    async for websocket in connect(
        url,
        # Latido: si Binance deja de contestar, cortamos y reconectamos en vez de quedarnos
        # esperando para siempre frente a una conexión muerta que parece viva.
        ping_interval=20,
        ping_timeout=20,
    ):
        inicio = time.monotonic()

        try:
            logger.info("Conectado. Escuchando operaciones…")

            async for mensaje in websocket:
                tick = parsear_mensaje(mensaje)
                if tick is not None:
                    await al_recibir(tick)

        except ConnectionClosed:
            # No es un error: es lo esperado cada tanto. Abajo decidimos cuánto esperar.
            logger.warning("Binance cerró la conexión.")

        # Solo se llega acá si la conexión terminó por su cuenta. Si nos cancelaron, el
        # CancelledError pasa de largo por este bloque y la tarea muere al instante.
        duracion = time.monotonic() - inicio

        if duracion >= SEGUNDOS_CONEXION_SANA:
            # Venía funcionando bien: el corte fue puntual, reintentamos sin castigo.
            espera = SEGUNDOS_ESPERA_BASE
            logger.info("Reconectando…")
        else:
            logger.warning(
                "La conexión duró solo %.1fs. Esperando %.0fs antes de reintentar.",
                duracion,
                espera,
            )
            await asyncio.sleep(espera)
            espera = min(espera * 2, SEGUNDOS_ESPERA_MAXIMA)


# ---------------------------------------------------------------------------
# Modo de prueba por consola (paso 1.1): `uv run python -m app.ingesta.binance`
# ---------------------------------------------------------------------------


class _ImpresorDeTicks:
    """Consumidor de prueba: muestra cada tick por consola y lleva la cuenta.

    Es el "cliente" descartable del paso 1.1, solo para ver con los ojos que el dato real
    está entrando. En el paso 1.2 lo reemplaza el que escribe en TimescaleDB.
    """

    def __init__(self, limite: int | None) -> None:
        self.limite = limite
        self.total = 0
        self.por_simbolo: dict[str, int] = {}
        self.completado = asyncio.Event()
        self.inicio = asyncio.get_event_loop().time()

    async def __call__(self, tick: Tick) -> None:
        self.total += 1
        self.por_simbolo[tick.simbolo] = self.por_simbolo.get(tick.simbolo, 0) + 1

        # Hora local para leerlo cómodo, con milisegundos porque a esta velocidad importan.
        hora = tick.momento.astimezone().strftime("%H:%M:%S.%f")[:-3]
        flecha = "▲" if tick.lado_agresor == "compra" else "▼"

        print(
            f"{hora}  {tick.simbolo:<8} "
            f"{tick.precio:>12,.2f}  ×{tick.cantidad:>12,.5f}  "
            f"= {tick.volumen_cotizado:>11,.2f} USDT  {flecha} {tick.lado_agresor}"
        )

        if self.limite is not None and self.total >= self.limite:
            self.completado.set()

    def resumen(self) -> str:
        segundos = asyncio.get_event_loop().time() - self.inicio
        detalle = "  ".join(f"{s}={n}" for s, n in sorted(self.por_simbolo.items()))
        ritmo = self.total / segundos if segundos > 0 else 0
        return (
            f"\n{self.total} operaciones en {segundos:.1f}s "
            f"({ritmo:.1f}/s)   {detalle}"
        )


async def _correr_prueba(simbolos: Sequence[str], limite: int | None) -> None:
    """Levanta la escucha y la corta cuando se llega al límite o cuando cortas con Ctrl+C."""
    impresor = _ImpresorDeTicks(limite)
    tarea = asyncio.create_task(escuchar_ticks(impresor, simbolos))

    try:
        if limite is None:
            await tarea  # sin límite: hasta que el usuario corte
        else:
            espera_limite = asyncio.create_task(impresor.completado.wait())
            await asyncio.wait(
                {tarea, espera_limite},
                return_when=asyncio.FIRST_COMPLETED,
            )
            espera_limite.cancel()
    finally:
        tarea.cancel()
        # Le damos a la tarea la chance de terminar de cancelarse sin ensuciar la salida.
        await asyncio.gather(tarea, return_exceptions=True)
        print(impresor.resumen())


def main() -> None:
    """Punto de entrada de la prueba por consola."""
    parser = argparse.ArgumentParser(
        description="Escucha las operaciones de Binance en vivo y las muestra por consola.",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=None,
        help="Cortar después de N operaciones (por defecto: no cortar nunca).",
    )
    parser.add_argument(
        "--simbolos",
        nargs="+",
        default=list(SIMBOLOS_MVP),
        metavar="PAR",
        help=f"Pares a escuchar (por defecto: {' '.join(SIMBOLOS_MVP)}).",
    )
    argumentos = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    try:
        asyncio.run(_correr_prueba(argumentos.simbolos, argumentos.limite))
    except KeyboardInterrupt:
        print("\nCortado por el usuario.")


if __name__ == "__main__":
    main()
