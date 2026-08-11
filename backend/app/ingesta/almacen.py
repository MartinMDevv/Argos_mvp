"""Guarda los ticks en TimescaleDB, de a lotes (paso 1.2).

## Por qué de a lotes y no uno por uno
Cada escritura a Postgres es una ida y vuelta por la red más el trabajo del motor. Escribir
tick por tick significa pagar ese peaje cientos de veces por minuto para guardar unos pocos
bytes cada vez. Juntamos los ticks en memoria y los mandamos en tandas: un viaje en vez de
doscientos.

El lote se vuelca cuando pasa lo primero de estas dos cosas:
  - se juntaron `tamano_lote` ticks (mercado agitado → volcados frecuentes), o
  - pasaron `segundos_entre_volcados` (mercado dormido → igual no perdemos el dato).

## Por qué `executemany` y no `copy_records_to_table`
En el paso 0.5 habíamos anotado que la ingesta usaría `copy_records_to_table`, que es la vía
más rápida que ofrece asyncpg. Al implementarlo aparece un problema: **COPY no admite
`ON CONFLICT DO NOTHING`**. Y el anti-duplicados no es opcional acá: cada vez que el WebSocket
se reconecta podemos recibir operaciones ya guardadas, y un tick contado dos veces le miente a
los detectores de volumen justo cuando más importa.

Con el volumen del MVP (BTC + ETH, unas decenas de operaciones por segundo), `executemany` va
holgado y nos deja la deduplicación gratis, hecha por la base. Si algún día el volumen crece
—memecoins, muchos pares— la salida conocida es COPY a una tabla temporal y después
`INSERT ... SELECT ... ON CONFLICT DO NOTHING`. Se anota y se hace cuando duela, no antes.

## Si la base de datos no está
No se pierde el dato ni se cae Argos: los ticks quedan esperando en memoria y se reintentan en
el siguiente volcado (la reconexión perezosa del pool hace el resto en cuanto vuelve Docker).
Eso sí, la espera tiene tope: si la base no vuelve nunca, preferimos descartar los ticks más
viejos antes que comernos toda la RAM del equipo.
"""

import asyncio
import logging
from collections import deque

from app.db import asegurar_pool
from app.modelos import Tick

logger = logging.getLogger(__name__)

SQL_INSERTAR_TICK = """
    INSERT INTO ticks (momento, simbolo, precio, cantidad, id_operacion, comprador_pasivo)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT DO NOTHING
"""


class EscritorDeTicks:
    """Junta ticks en memoria y los va escribiendo en la base de datos por tandas."""

    def __init__(
        self,
        tamano_lote: int = 200,
        segundos_entre_volcados: float = 2.0,
        maximo_en_espera: int = 20_000,
    ) -> None:
        self.tamano_lote = tamano_lote
        self.segundos_entre_volcados = segundos_entre_volcados
        self.maximo_en_espera = maximo_en_espera

        self._pendientes: deque[Tick] = deque()
        self._hay_lote = asyncio.Event()

        # Contadores para poder mirar por dentro sin abrir la base (se exponen en la API).
        self.guardados = 0
        self.descartados = 0
        self.fallos_de_volcado = 0

    # -- Entrada -------------------------------------------------------------

    def encolar(self, tick: Tick) -> None:
        """Mete un tick en la cola de espera.

        Es una función normal, sin `await`, a propósito: la llama el que está leyendo el
        WebSocket, y ese no puede quedarse esperando a que termine una escritura en disco.
        Encolar tiene que ser instantáneo o la ingesta se atrasa.
        """
        if len(self._pendientes) >= self.maximo_en_espera:
            # Cola llena (la base lleva rato caída). Tiramos el más viejo: si tenemos que
            # perder algo, que sea lo más lejano, no lo que está pasando ahora.
            self._pendientes.popleft()
            self.descartados += 1
            if self.descartados % 1000 == 1:
                logger.warning(
                    "Cola de escritura llena (%d ticks). Descartados hasta ahora: %d",
                    self.maximo_en_espera,
                    self.descartados,
                )

        self._pendientes.append(tick)

        if len(self._pendientes) >= self.tamano_lote:
            self._hay_lote.set()  # despierta al bucle sin esperar al reloj

    # -- Salida --------------------------------------------------------------

    async def volcar(self) -> int:
        """Escribe en la base todo lo que haya pendiente. Devuelve cuántos ticks guardó."""
        if not self._pendientes:
            return 0

        # Sacamos el lote de la cola de una sola vez. Entre estas dos líneas no hay `await`,
        # así que nadie puede meter mano en el medio: o está entero en la cola, o está entero
        # en el lote. Sin estados a medio camino.
        lote = list(self._pendientes)
        self._pendientes.clear()

        filas = [
            (
                tick.momento,
                tick.simbolo,
                tick.precio,
                tick.cantidad,
                tick.id_operacion,
                tick.comprador_pasivo,
            )
            for tick in lote
        ]

        try:
            pool = await asegurar_pool()
            async with pool.acquire() as conexion:
                await conexion.executemany(SQL_INSERTAR_TICK, filas)
        except Exception as error:
            # No se pudo escribir: devolvemos el lote al FRENTE de la cola (era lo más viejo)
            # y lo reintentamos en el próximo volcado.
            self.fallos_de_volcado += 1
            self._pendientes.extendleft(reversed(lote))
            self._recortar_cola()
            logger.warning(
                "No se pudo volcar %d ticks (%s). Quedan %d esperando.",
                len(lote),
                error,
                len(self._pendientes),
            )
            return 0

        self.guardados += len(lote)
        logger.debug("Volcados %d ticks (total: %d)", len(lote), self.guardados)
        return len(lote)

    async def correr(self) -> None:
        """Bucle que vuelca la cola cada tanto. No termina: se corta cancelando la tarea.

        Antes de morir, quien la cancela debería llamar a `volcar()` una última vez para no
        dejarse ticks sin guardar (lo hace el `lifespan` en main.py).
        """
        logger.info(
            "Escritor de ticks activo (lotes de %d o cada %.1fs)",
            self.tamano_lote,
            self.segundos_entre_volcados,
        )

        while True:
            try:
                # Esperamos a que se junte un lote… o a que se acabe el tiempo, lo que pase
                # primero. Así el mercado agitado no espera y el mercado dormido no se queda
                # con ticks colgados en memoria.
                await asyncio.wait_for(
                    self._hay_lote.wait(),
                    timeout=self.segundos_entre_volcados,
                )
            except TimeoutError:
                pass

            self._hay_lote.clear()
            await self.volcar()

    # -- Auxiliares ----------------------------------------------------------

    def _recortar_cola(self) -> None:
        """Deja la cola dentro del tope, tirando los ticks más viejos."""
        while len(self._pendientes) > self.maximo_en_espera:
            self._pendientes.popleft()
            self.descartados += 1

    @property
    def en_espera(self) -> int:
        """Cuántos ticks hay ahora mismo esperando a ser escritos."""
        return len(self._pendientes)

    def resumen(self) -> dict[str, int]:
        """Estado del escritor, para exponerlo en la API y ver si está sano."""
        return {
            "guardados": self.guardados,
            "en_espera": self.en_espera,
            "descartados": self.descartados,
            "fallos_de_volcado": self.fallos_de_volcado,
        }
