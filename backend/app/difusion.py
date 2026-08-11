"""Empuja el estado del mercado a los paneles conectados, por WebSocket (paso 1.4).

## El cambio de sentido
Hasta ahora el panel tenía que *preguntar* ("dame el precio", "dame las velas"). Eso llega
tarde y hace trabajo al pedo: la mayoría de las veces la respuesta es "lo mismo que hace un
segundo". Acá se da vuelta: el panel se conecta una vez y **el backend le avisa** cuando hay
algo nuevo. Es el mismo trato que tenemos nosotros con Binance, un escalón más arriba.

## Por qué NO mandamos cada tick
Por el mismo motivo que elegimos `aggTrade` en vez de `trade`: bajo ruido. BTC y ETH pueden
generar decenas de operaciones por segundo, y ningún ojo humano —ni React— saca provecho de
redibujar 40 veces por segundo. Mandaríamos muchísimo tráfico para que el navegador tire casi
todo. En vez de eso mandamos una **foto cada `INTERVALO_DIFUSION`**, y solo si cambió algo.

## El latido
Si el mercado se queda quieto no hay nada que mandar, y una conexión muda es indistinguible de
una conexión muerta. Cada `SEGUNDOS_LATIDO` sin novedades mandamos un `latido` para que el panel
sepa que Argos sigue ahí, mirando.
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import WebSocket

from app.estado import EstadoMercado

logger = logging.getLogger(__name__)

INTERVALO_DIFUSION = 0.5
"""Cada cuánto miramos si hay novedades para mandar. Dos veces por segundo alcanza de sobra
para que un panel se sienta "en vivo" sin inundarlo."""

SEGUNDOS_LATIDO = 15.0
"""Cuánto silencio toleramos antes de mandar señal de vida."""


class GestorDeConexiones:
    """Lleva la lista de paneles conectados y les manda los mensajes.

    Es deliberadamente tonto: no sabe qué se manda ni por qué, solo a quién. Quien decide el
    contenido es `emitir_estado`.
    """

    def __init__(self) -> None:
        self._conexiones: set[WebSocket] = set()

    @property
    def cantidad(self) -> int:
        """Cuántos paneles hay mirando ahora mismo."""
        return len(self._conexiones)

    async def conectar(self, websocket: WebSocket, estado: EstadoMercado) -> None:
        """Acepta un panel nuevo y le manda el estado actual de entrada.

        Lo de mandar la foto al toque importa: sin eso, el panel arrancaría en blanco hasta la
        primera novedad. Se vería como si Argos no supiera nada, cuando en realidad sí sabe.
        """
        await websocket.accept()
        self._conexiones.add(websocket)
        logger.info("Panel conectado (%d en total)", self.cantidad)

        await websocket.send_json(
            {
                "tipo": "bienvenida",
                "momento": datetime.now(UTC).isoformat(),
                "simbolos": estado.instantanea(),
            }
        )

    def desconectar(self, websocket: WebSocket) -> None:
        """Saca un panel de la lista. Tolera que ya no esté (puede llegar por dos caminos)."""
        self._conexiones.discard(websocket)
        logger.info("Panel desconectado (%d en total)", self.cantidad)

    async def difundir(self, mensaje: dict[str, object]) -> None:
        """Manda el mismo mensaje a todos los paneles conectados.

        Los envíos van **en paralelo** (`gather`), no uno tras otro: si fueran secuenciales, un
        panel lento —una pestaña en segundo plano, una conexión mala— haría esperar a todos los
        demás. Al que falle lo damos de baja en el momento; ya se reconectará.
        """
        if not self._conexiones:
            return

        destinatarios = list(self._conexiones)
        resultados = await asyncio.gather(
            *(ws.send_json(mensaje) for ws in destinatarios),
            return_exceptions=True,
        )

        for websocket, resultado in zip(destinatarios, resultados, strict=True):
            if isinstance(resultado, BaseException):
                # Se cayó mientras le escribíamos. No es un error digno de alarma: pasa cada
                # vez que alguien cierra la pestaña justo en el momento equivocado.
                logger.debug("Panel caído durante el envío: %s", resultado)
                self.desconectar(websocket)


async def emitir_estado(
    gestor: GestorDeConexiones,
    estado: EstadoMercado,
    intervalo: float = INTERVALO_DIFUSION,
    segundos_latido: float = SEGUNDOS_LATIDO,
) -> None:
    """Bucle que va empujando el estado del mercado. No termina: se corta cancelando la tarea.

    Solo manda cuando la foto cambió respecto de la anterior. Si no cambió nada en
    `segundos_latido`, manda un latido para demostrar que la conexión sigue viva.
    """
    logger.info("Difusión de estado activa (cada %.1fs)", intervalo)

    ultima_foto: dict[str, dict[str, object]] | None = None
    ultimo_envio = asyncio.get_running_loop().time()

    while True:
        await asyncio.sleep(intervalo)

        # Si no hay nadie escuchando, no gastamos ni en armar la foto.
        if gestor.cantidad == 0:
            continue

        foto = estado.instantanea()
        ahora = asyncio.get_running_loop().time()

        if foto != ultima_foto:
            await gestor.difundir(
                {
                    "tipo": "estado",
                    "momento": datetime.now(UTC).isoformat(),
                    "simbolos": foto,
                }
            )
            ultima_foto = foto
            ultimo_envio = ahora

        elif ahora - ultimo_envio >= segundos_latido:
            await gestor.difundir(
                {"tipo": "latido", "momento": datetime.now(UTC).isoformat()}
            )
            ultimo_envio = ahora
