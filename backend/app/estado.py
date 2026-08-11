"""El "último estado" del mercado, vivo en memoria (paso 1.2).

## Por qué no consultar la base de datos
El panel pregunta "¿a cuánto está BTC?" muchas veces por segundo, y la respuesta es un dato
que acabamos de recibir hace milisegundos. Ir al disco a buscar algo que tenemos en la mano
es tirar tiempo. Esto es un diccionario en RAM: la respuesta es instantánea.

## Reparto de tareas
- **Esto (memoria)** → el AHORA. Qué precio tiene cada símbolo en este instante.
- **TimescaleDB (disco)** → la HISTORIA. Con qué comparar ese ahora para saber si es raro.

Los detectores de la Fase 3 van a necesitar las dos cosas: el tick que acaba de entrar y la
estadística de lo que venía pasando.

## Se pierde al reiniciar, y está bien
Es una foto del presente, no un archivo. Si Argos se reinicia, se rellena sola con el primer
tick que llegue (menos de un segundo). Lo que no se puede perder es la historia, y esa está
en disco.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modelos import Tick


@dataclass(slots=True)
class EstadoDeSimbolo:
    """Lo último que sabemos de un símbolo."""

    ultimo_tick: Tick
    ticks_vistos: int
    """Cuántas operaciones vimos desde que arrancó el proceso. Sirve para saber de un
    vistazo si el flujo está entrando o si la conexión se quedó muda."""


class EstadoMercado:
    """Último tick conocido de cada símbolo.

    No hace falta candado (lock) ni nada por el estilo: todo Argos corre en un solo hilo con
    asyncio, y estos métodos no tienen `await` adentro, así que nadie puede interrumpirlos a
    la mitad. Es un detalle que se agradece tener presente si algún día se mete threading.
    """

    def __init__(self) -> None:
        self._por_simbolo: dict[str, EstadoDeSimbolo] = {}
        self.desde = datetime.now(UTC)

    def actualizar(self, tick: Tick) -> None:
        """Registra el tick como lo más reciente de su símbolo."""
        actual = self._por_simbolo.get(tick.simbolo)

        if actual is None:
            self._por_simbolo[tick.simbolo] = EstadoDeSimbolo(ultimo_tick=tick, ticks_vistos=1)
            return

        actual.ticks_vistos += 1

        # Guarda contra el desorden: los mensajes pueden llegar cruzados tras una reconexión,
        # y no queremos que un tick viejo pise al último precio bueno.
        if tick.momento >= actual.ultimo_tick.momento:
            actual.ultimo_tick = tick

    def ultimo(self, simbolo: str) -> Tick | None:
        """Último tick del símbolo, o None si todavía no llegó ninguno (no inventamos precio)."""
        estado = self._por_simbolo.get(simbolo)
        return estado.ultimo_tick if estado else None

    def instantanea(self) -> dict[str, dict[str, object]]:
        """Foto del mercado lista para devolver como JSON.

        Los números van como TEXTO a propósito. JSON no tiene decimales exactos: si mandamos
        el precio como número, JavaScript lo recibe como float y vuelve el problema que
        evitamos usando Decimal. Como texto, el precio llega al panel tal cual salió de Binance.
        """
        return {
            simbolo: {
                "precio": str(estado.ultimo_tick.precio),
                "cantidad": str(estado.ultimo_tick.cantidad),
                "momento": estado.ultimo_tick.momento.isoformat(),
                "lado": estado.ultimo_tick.lado_agresor,
                "ticks_vistos": estado.ticks_vistos,
            }
            for simbolo, estado in sorted(self._por_simbolo.items())
        }
