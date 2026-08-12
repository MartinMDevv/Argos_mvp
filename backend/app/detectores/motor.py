"""El motor: quién le pregunta a los detectores, cuándo, y qué hace con la respuesta (paso 3.1).

## Las dos rutas
El motor no corre un solo bucle, corre dos, porque las dos capas del spec tienen
necesidades opuestas:

**La ruta rápida (`revisar_tick`)** cuelga de la ingesta. Cada operación que llega de
Binance pasa por acá antes de seguir su camino. Es una función normal, sin `await`, por
el mismo motivo que `EscritorDeTicks.encolar`: quien la llama está leyendo un WebSocket y
no puede quedarse esperando. Acá no se consulta la base ni se escribe nada — solo
comparaciones en memoria y, si algo salta, la alerta va a una cola.

**La ruta lenta (`vigilar_velas`)** es una tarea de fondo que despierta cada pocos
segundos y se pregunta: ¿cerró alguna vela nueva? Si cerró, trae la historia una sola vez
por símbolo e intervalo y se la reparte a todos los detectores que la pidieron. Un
z-score no cambia de respuesta entre dos ticks; preguntarle cuarenta veces por segundo
sería trabajo puro para llegar al mismo número.

## Por qué las alertas van a una cola
Emitir y guardar son dos cosas distintas. La detección ocurre en la ruta caliente, donde
un `INSERT` bloquearía la ingesta; y si la base está caída, una alerta no se puede
perder solo porque Docker esté apagado. Entonces el que detecta encola, y `despachar()`
—tercera tarea, de fondo— escribe. Es la misma división que ya usa el escritor de ticks,
por las mismas razones.

## Lo que el motor garantiza y los detectores no tienen que repetir
- Que nadie evalúe sin material suficiente (`puede_opinar`).
- Que no se repita la misma noticia (el silencio).
- Que un detector que revienta no se lleve puesto al resto ni al bucle.
- Que la alerta quede guardada aunque la base esté caída en ese momento.
"""

import asyncio
import logging
from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import UTC, datetime

from app.detectores import almacen
from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.silencio import Silencio
from app.estado import EstadoMercado
from app.modelos import Alerta, Tick
from app.velas import LIMITE_MAXIMO, obtener_velas

logger = logging.getLogger(__name__)

SEGUNDOS_ENTRE_REVISIONES = 5.0
"""Cada cuánto la ruta lenta se pregunta si cerró una vela nueva.

Cinco segundos contra un minuto de vela es de sobra, y evita atarse a la hora del reloj:
una vela no se declara completa hasta que sus ticks aterrizaron en disco (`MARGEN_ASENTADO`
en velas.py), así que preguntar seguido y barato es mejor que calcular el instante exacto."""

MARGEN_DE_VELAS = 5
"""Velas de más que se piden por encima de lo que necesita el detector más exigente.
La última suele estar a medio formar y no cuenta; el margen evita quedarse justo."""

MINIMO_DE_VELAS = 10
"""Piso de velas a pedir, incluso si ningún detector pidió historia. Con esto un
detector nuevo tiene siempre algo de contexto alrededor sin cambiar nada."""

SEGUNDOS_ENTRE_DESPACHOS = 2.0
"""Cada cuánto se vacía la cola de alertas hacia la base."""

MAXIMO_EN_ESPERA = 5_000
"""Tope de alertas esperando a ser escritas. Si se llega a esto, o la base lleva
muchísimo tiempo caída o hay un detector desbocado; en cualquier caso, preferimos tirar
las más viejas antes que comernos la RAM."""


class MotorDeDetectores:
    """Corre los detectores registrados y despacha lo que encuentran."""

    def __init__(
        self,
        estado: EstadoMercado,
        detectores: Sequence[Detector],
        simbolos: Sequence[str],
    ) -> None:
        self.estado = estado
        self.simbolos = list(simbolos)
        self.detectores = list(detectores)

        # Los separamos una sola vez, acá, en vez de filtrar en cada vuelta del bucle.
        self._por_tick = [d for d in self.detectores if d.cadencia is Cadencia.POR_TICK]

        # Los de vela se agrupan por intervalo: todos los que miran 1m comparten la
        # misma consulta. Ahí está el ahorro de traer los datos una vez y repartirlos.
        self._por_intervalo: dict[str, list[Detector]] = defaultdict(list)
        for detector in self.detectores:
            if detector.cadencia is Cadencia.POR_VELA_CERRADA:
                self._por_intervalo[detector.intervalo].append(detector)

        self.silencio = Silencio()

        self._pendientes: deque[Alerta] = deque()
        self._hay_alertas = asyncio.Event()

        # De qué vela fue la última evaluación de cada (símbolo, intervalo). Es lo que
        # evita volver a opinar sobre el mismo minuto en cada vuelta del bucle.
        self._ultima_evaluada: dict[tuple[str, str], datetime] = {}

        self.emitidas = 0
        self.guardadas = 0
        self.descartadas = 0
        self.fallos_de_detector = 0
        self.fallos_de_guardado = 0

    # -- Ruta rápida: cuelga de la ingesta ------------------------------------

    def revisar_tick(self, tick: Tick) -> None:
        """Pasa el precio vivo por los detectores `por_tick`. Sin `await`, sin base de datos.

        La llama el consumidor de la ingesta con cada operación que entra, así que tiene
        que ser barata. Si no hay detectores de esta cadencia, sale en la primera línea.
        """
        if not self._por_tick:
            return

        contexto = ContextoDeEvaluacion(
            simbolo=tick.simbolo,
            momento=datetime.now(UTC),
            tick=tick,
        )

        for detector in self._por_tick:
            self._preguntar(detector, contexto)

    # -- Ruta lenta: tarea de fondo -------------------------------------------

    async def vigilar_velas(self) -> None:
        """Bucle que evalúa los detectores de vela cuando cierra una nueva.

        No termina nunca: se corta cancelando la tarea.
        """
        if not self._por_intervalo:
            logger.info("No hay detectores por vela cerrada; la ruta lenta no arranca")
            return

        logger.info(
            "Vigilancia por velas activa: %s",
            ", ".join(
                f"{intervalo} ({len(dets)})" for intervalo, dets in self._por_intervalo.items()
            ),
        )

        while True:
            await asyncio.sleep(SEGUNDOS_ENTRE_REVISIONES)

            for intervalo, detectores in self._por_intervalo.items():
                for simbolo in self.simbolos:
                    try:
                        await self._revisar_vela(simbolo, intervalo, detectores)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        # Base caída, casi siempre. No es motivo para matar la vigilancia:
                        # se reintenta en la próxima vuelta, dentro de cinco segundos.
                        logger.warning(
                            "No se pudo revisar %s · %s: %s", simbolo, intervalo, error
                        )

            self.silencio.olvidar_viejas(datetime.now(UTC))

    async def _revisar_vela(
        self, simbolo: str, intervalo: str, detectores: Sequence[Detector]
    ) -> None:
        """Si cerró una vela nueva para este símbolo e intervalo, evalúa sus detectores."""
        necesarias = max((d.velas_necesarias for d in detectores), default=0)
        limite = min(LIMITE_MAXIMO, max(MINIMO_DE_VELAS, necesarias + MARGEN_DE_VELAS))

        velas = await obtener_velas(simbolo, intervalo, limite)

        contexto = ContextoDeEvaluacion(
            simbolo=simbolo,
            momento=datetime.now(UTC),
            tick=self.estado.ultimo(simbolo),
            velas=tuple(velas),
            intervalo=intervalo,
        )

        ultima = contexto.ultima_cerrada
        if ultima is None:
            return

        # ¿Ya opinamos sobre esta vela? El bucle despierta cada cinco segundos y una vela
        # de 1m dura sesenta: sin esta guarda, la misma vela se evaluaría doce veces.
        clave_vela = (simbolo, intervalo)
        if self._ultima_evaluada.get(clave_vela) == ultima.inicio:
            return
        self._ultima_evaluada[clave_vela] = ultima.inicio

        for detector in detectores:
            self._preguntar(detector, contexto)

    # -- El paso común: preguntar y filtrar ------------------------------------

    def _preguntar(self, detector: Detector, contexto: ContextoDeEvaluacion) -> None:
        """Le pregunta a un detector y encola la respuesta si pasa el antirruido.

        Todo detector pasa por acá, venga de la ruta rápida o de la lenta, y es donde
        viven las garantías que los detectores no tienen que reimplementar.
        """
        if not detector.puede_opinar(contexto):
            return

        try:
            alertas = detector.evaluar(contexto)
        except Exception as error:
            # Un detector roto es un detector roto, no un Argos roto. Se anota y se sigue:
            # los otros tres tienen que poder seguir vigilando.
            self.fallos_de_detector += 1
            logger.exception(
                "El detector '%s' falló evaluando %s: %s", detector.nombre, contexto.simbolo, error
            )
            return

        # Un detector puede encontrar varias cosas a la vez (ver el docstring de
        # `Detector.evaluar`). Cada una pasa por el antirruido por separado, porque
        # cada una tiene su propia clave: que una se calle no debe callar a las otras.
        for alerta in alertas:
            if not self.silencio.permite(alerta.clave, alerta.momento, detector.silencio):
                continue

            self.silencio.anotar(alerta.clave, alerta.momento)
            self._encolar(alerta)

            logger.info(
                "ALERTA [%s] %s · %s — %s",
                alerta.severidad,
                alerta.titulo,
                alerta.simbolo,
                alerta.detalle,
            )

    def _encolar(self, alerta: Alerta) -> None:
        """Mete la alerta en la cola de escritura y despierta al despachador."""
        if len(self._pendientes) >= MAXIMO_EN_ESPERA:
            self._pendientes.popleft()
            self.descartadas += 1

        self._pendientes.append(alerta)
        self.emitidas += 1
        self._hay_alertas.set()

    # -- Salida: guardar lo emitido -------------------------------------------

    async def despachar(self) -> None:
        """Bucle que va escribiendo en la base las alertas emitidas. No termina."""
        await self._precargar_silencio()

        while True:
            try:
                await asyncio.wait_for(
                    self._hay_alertas.wait(), timeout=SEGUNDOS_ENTRE_DESPACHOS
                )
            except TimeoutError:
                pass

            self._hay_alertas.clear()
            await self.volcar()

    async def volcar(self) -> int:
        """Escribe las alertas pendientes. Devuelve cuántas guardó.

        Si la base no está, vuelven al frente de la cola y se reintentan: la misma
        política que con los ticks, porque una alerta perdida es peor que una tardía.
        """
        if not self._pendientes:
            return 0

        lote = list(self._pendientes)
        self._pendientes.clear()

        try:
            guardadas = await almacen.guardar(lote)
        except Exception as error:
            self.fallos_de_guardado += 1
            self._pendientes.extendleft(reversed(lote))
            while len(self._pendientes) > MAXIMO_EN_ESPERA:
                self._pendientes.popleft()
                self.descartadas += 1
            logger.warning(
                "No se pudieron guardar %d alertas (%s). Quedan %d esperando.",
                len(lote),
                error,
                len(self._pendientes),
            )
            return 0

        self.guardadas += guardadas
        return guardadas

    async def _precargar_silencio(self) -> None:
        """Le cuenta al silencio qué se dijo antes de este arranque.

        Sin esto, reiniciar sería una forma de saltarse el antirruido — y con `--reload`
        puesto, cada cambio de código repetiría las alertas de hace un minuto.
        """
        try:
            desde = datetime.now(UTC) - almacen.VENTANA_PRECARGA
            self.silencio.precargar(await almacen.ultima_por_clave(desde))
        except Exception as error:
            # Arrancar sin precarga es peor que con ella, pero mucho mejor que no arrancar.
            logger.warning("No se pudo precargar el silencio: %s", error)

    # -- Para mirarlo por dentro ----------------------------------------------

    def resumen(self) -> dict[str, object]:
        """Pulso del motor, para exponerlo en la API y ver si está sano."""
        return {
            "detectores": len(self.detectores),
            "por_tick": len(self._por_tick),
            "por_vela_cerrada": sum(len(d) for d in self._por_intervalo.values()),
            "emitidas": self.emitidas,
            "guardadas": self.guardadas,
            "en_espera": len(self._pendientes),
            "descartadas": self.descartadas,
            "fallos_de_detector": self.fallos_de_detector,
            "fallos_de_guardado": self.fallos_de_guardado,
            **self.silencio.resumen(),
        }
