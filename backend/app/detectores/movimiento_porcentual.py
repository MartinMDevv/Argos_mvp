"""Alerta #2: el precio se movió mucho en poco tiempo (paso 3.3).

El clásico *spike*. La #1 avisaba de una línea que pusiste tú; esta es la primera que
Argos encuentra solo: no hace falta que sepas de antemano qué número mirar, solo que un
movimiento grande y rápido merece que levantes la vista.

Y es el primer detector `POR_VELA_CERRADA`. No mira el tick suelto sino la historia
reciente, que el motor le trae ya cargada; él solo hace cuentas.

## Qué se mide: cierre contra cierre
Se compara el cierre de la última vela terminada contra el cierre de hace N minutos. La
otra forma de medir un movimiento —máximo menos mínimo dentro de la ventana— mide otra
cosa: cuánto se agitó el precio. Eso es exactamente la alerta #3 (volatilidad por
z-score), y tener dos detectores midiendo lo mismo es tener dos que cuentan la misma
noticia. La división queda así:

- **#2 (esta):** se movió y se quedó allá. Tiene dirección.
- **#3:** esto está más agitado de lo que suele estar. No tiene dirección.

## La ventana se busca por hora, no por posición
La referencia no es "la vela de cinco lugares más atrás" sino "la vela que empieza cinco
minutos antes que esta". Parecen lo mismo y no lo son: `obtener_velas` no devuelve los
tramos sin operaciones, así que contar posiciones haría que un minuto vacío corriera la
ventana y "5 minutos" pasaran a ser seis sin que nada avise.

Buscándola por su marca de tiempo, además, **un hueco en el medio no importa**: el
movimiento neto se mide entre los dos extremos y lo que pasó adentro no cambia la
cuenta. Lo que sí importa es que el extremo exista. Si Argos estuvo apagado y esa vela
no está, la ventana no se evalúa esta vez — no se busca la más cercana. Decir "se movió
8% en 15 minutos" cuando la referencia es de hace tres días es justo lo que la regla de
oro prohíbe, y el costo de callarse es mínimo: al minuto siguiente hay otra referencia.

## Moverse no es haberse movido
Es el problema propio de este detector, y es hermano del "cruzar no es estar" de la #1.
Un pump de 4% sigue estando dentro de la ventana de una hora durante la hora siguiente:
el detector ingenuo lo grita vela tras vela, sesenta veces, mientras el precio ya no
hace nada. El silencio del motor no alcanza para eso — dura minutos, el arrastre dura lo
que dure la ventana más larga.

Por eso, al emitir, el detector **anota el precio desde el que avisó**. Hacia esa misma
dirección no vuelve a hablar salvo que el movimiento *continúe* otro tanto más allá de
ese punto. Un pump de 4% avisa una vez; si sigue hasta 8%, avisa de nuevo, porque eso ya
es otra noticia. Si se da vuelta, la dirección contraria vuelve a estar habilitada al
instante: una reversión sí es noticia nueva.

Es memoria, como en la #1, y de la misma clase: derivada de la secuencia que ya pasó.
Dale a este detector las mismas velas en el mismo orden y emite las mismas alertas, que
es lo que hace falta para poder correrlo sobre el pasado (v2.0, backtesting).

## Una noticia, una alerta
Un salto de 4% de golpe supera las tres ventanas a la vez. Se emite **solo la más corta
que superó su umbral**: es la que describe lo que está pasando ahora, y las más largas
son la misma noticia mirada con más contexto. Y la clave de la alerta lleva solo la
dirección, **no la ventana**, para que las tres compartan el mismo silencio en vez de
turnarse para repetir lo mismo.

## Lo que este detector NO resuelve
El "≥X%" lo elegimos a mano, y ahí hay una tensión con la regla de oro que conviene
tener escrita: un 3% en cinco minutos es notable para BTC y puede ser un martes
cualquiera para una moneda chica. Este detector no sabe distinguirlo, porque el número
no sale de los datos sino de nosotros.

Lo resuelve la **#3 (z-score)**: en vez de "avísame si se mueve 3%", pregunta "¿esto es
raro para lo que este activo suele hacer?". Esta alerta se queda igual porque es barata,
es directa de explicar y atrapa el spike clásico sin necesitar historia larga — pero no
es la que le da a Argos criterio propio.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.registro import registrar
from app.detectores.umbrales import texto_de_precio
from app.modelos import Alerta, Vela

SUBIDA = "subida"
BAJADA = "bajada"


@dataclass(frozen=True, slots=True)
class Ventana:
    """Un par (cuánto tiempo, cuánto movimiento) que dispara la alerta."""

    minutos: int
    """Largo de la ventana. Se mide en tiempo real, no en cantidad de velas."""

    porcentaje: Decimal
    """Movimiento mínimo, en valor absoluto: sirve igual para arriba que para abajo."""


VENTANAS: tuple[Ventana, ...] = (
    Ventana(minutos=5, porcentaje=Decimal("2")),
    Ventana(minutos=15, porcentaje=Decimal("3.5")),
    Ventana(minutos=60, porcentaje=Decimal("6")),
)
"""Las ventanas vigiladas, de la más corta a la más larga.

Van escritas acá y no en una tabla como los umbrales de la #1, y la diferencia es de
naturaleza: un umbral es una decisión tuya sobre un activo ("avísame si BTC pasa de
70.000"), esto es un parámetro del detector. Además la #3 los va a volver casi
innecesarios, así que montarles un CRUD sería trabajo con fecha de vencimiento.

## De dónde salen estos números
No de la intuición: se probaron cuatro configuraciones corriendo el detector sobre los
369 días de historia real que hay en la base (paso 3.3). Con 3 / 5 / 8 —lo primero que
propusimos— BTC habría hablado **un solo día en todo el año**, el del desplome del 10 de
octubre de 2025. Un detector que solo se despierta en el evento del año no reduce el
tiempo de reacción, que es para lo que existe Argos.

Con 2 / 3,5 / 6 sobre esa misma historia: BTC 1,5 alertas al mes repartidas en 11 días
distintos, ETH 5,8 al mes en 40 días. Raro, que es lo que queremos, pero no mudo. Bajar
a 1,5 / 2,5 / 4 llevaba a ETH a 17 al mes y ahí ya se rompe el "bajo ruido".

Ese ejercicio dejó dos cosas a la vista. Una: con la ventana larga en 8% las cortas la
tapaban siempre y no disparaba nunca; en 6% aporta lo suyo. Otra, más de fondo: con el
mismo número, ETH alerta entre tres y cuatro veces más que BTC. No es que ETH se mueva
"mal", es que un porcentaje fijo no se adapta al activo — la evidencia empírica de por
qué hace falta la #3.

Para moverlos no hace falta tocar el detector: recibe la lista por constructor."""


@dataclass(frozen=True, slots=True)
class Aviso:
    """Desde dónde avisamos la última vez. Es toda la memoria del detector."""

    direccion: str
    cierre: Decimal
    momento: datetime


@registrar
class MovimientoPorcentual(Detector):
    """Avisa cuando el precio se mueve un porcentaje grande en pocos minutos."""

    nombre = "movimiento_porcentual"
    titulo = "Movimiento fuerte"
    descripcion = (
        "Avisa cuando el precio se mueve un porcentaje grande en pocos minutos "
        "(2% en 5 min, 3,5% en 15 min o 6% en 1 h)."
    )
    cadencia = Cadencia.POR_VELA_CERRADA
    intervalo = "1m"

    velas_necesarias = max(v.minutos for v in VENTANAS) + 1
    """Cuánta historia quiere: la ventana más larga, más la vela de referencia.

    Ojo con la diferencia entre este atributo y `puede_opinar`. Este le dice al motor
    **cuántas velas traer**, y por eso pide para la ventana más larga. `puede_opinar`
    decide **cuándo alcanza para hablar**, y ahí basta con la ventana más corta: con
    veinte minutos de historia la de 5 min ya funciona, y esperar una hora para empezar
    a vigilar sería dejar a Argos ciego por nada."""

    silencio = timedelta(minutes=5)
    """Corto a propósito: el antirruido de verdad de este detector es la memoria del
    último aviso (ver "Moverse no es haberse movido"), que es más fina porque distingue
    "el mismo movimiento otra vez" de "el movimiento siguió". El silencio queda como red
    de seguridad, y de todos modos la evaluación es una por minuto."""

    def __init__(self, ventanas: tuple[Ventana, ...] = VENTANAS) -> None:
        # Ordenadas de la más corta a la más larga: `evaluar` recorre en ese orden y se
        # queda con la primera que supera, que es la regla de "una noticia, una alerta".
        self.ventanas = tuple(sorted(ventanas, key=lambda v: v.minutos))

        # Con otras ventanas, lo que el motor tiene que traer cambia. Se guarda en la
        # instancia (el motor lee `detector.velas_necesarias`, no la clase) para que un
        # detector configurado a mano pida la historia que de verdad usa.
        if self.ventanas:
            self.velas_necesarias = self.ventanas[-1].minutos + 1
            self._lapso_minimo = timedelta(minutes=self.ventanas[0].minutos)
        else:
            self.velas_necesarias = 0
            self._lapso_minimo = timedelta(0)

        # Símbolo → desde dónde avisamos la última vez.
        self._ultimo_aviso: dict[str, Aviso] = {}

    def puede_opinar(self, contexto: ContextoDeEvaluacion) -> bool:
        """¿La historia cubre al menos el tiempo de la ventana más corta?

        Se mide en **tiempo cubierto** y no en cantidad de velas, por lo mismo que la
        referencia se busca por hora: con un minuto sin operaciones en el medio, contar
        velas diría que falta historia cuando los dos extremos están ahí. Contar de
        menos es callarse de más, y eso acá no es prudencia sino una alerta perdida.

        Y alcanza con la ventana **más corta**, no con la más larga (que es lo que pide
        `velas_necesarias`): con veinte minutos de historia la de 5 min ya funciona, y
        esperar una hora para empezar a vigilar sería dejar a Argos ciego por nada.
        """
        cerradas = contexto.velas_cerradas
        if not self.ventanas or len(cerradas) < 2:
            return False
        return cerradas[-1].inicio - cerradas[0].inicio >= self._lapso_minimo

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        cerradas = contexto.velas_cerradas
        if len(cerradas) < 2 or not self.ventanas:
            return []

        ultima = cerradas[-1]
        por_inicio = {vela.inicio: vela for vela in cerradas}

        # --- 1. La ventana más corta que se pasó de la raya.
        hallazgo = self._buscar(ultima, por_inicio)
        if hallazgo is None:
            return []

        ventana, referencia, movimiento = hallazgo
        direccion = SUBIDA if movimiento > 0 else BAJADA

        # --- 2. ¿Es noticia nueva o el mismo movimiento arrastrado por la ventana?
        previo = self._ultimo_aviso.get(contexto.simbolo)
        avance = self._avance_desde(previo, direccion, ultima.cierre)
        if previo is not None and previo.direccion == direccion:
            if avance is None or abs(avance) < ventana.porcentaje:
                # Ya lo contamos, y desde entonces no se movió lo suficiente como para
                # que sea otra cosa. Se calla sin tocar la memoria: el ancla sigue
                # siendo el último aviso EMITIDO, no la última vez que se miró.
                return []

        # --- 3. Recién con la alerta decidida se recuerda desde dónde se avisó.
        self._ultimo_aviso[contexto.simbolo] = Aviso(
            direccion=direccion, cierre=ultima.cierre, momento=contexto.momento
        )

        return [
            self._armar_alerta(
                contexto,
                ventana=ventana,
                referencia=referencia,
                ultima=ultima,
                movimiento=movimiento,
                direccion=direccion,
                avance=avance if previo is not None and previo.direccion == direccion else None,
            )
        ]

    # -- Las cuentas ----------------------------------------------------------

    def _buscar(
        self, ultima: Vela, por_inicio: dict[datetime, Vela]
    ) -> tuple[Ventana, Vela, Decimal] | None:
        """Devuelve la ventana más corta que superó su porcentaje, o `None`.

        Recorre de la más corta a la más larga y corta en la primera que salta: si el
        precio se fue 4% en cinco minutos, agregar "y también 4% en una hora" no informa
        nada nuevo.
        """
        for ventana in self.ventanas:
            referencia = por_inicio.get(ultima.inicio - timedelta(minutes=ventana.minutos))
            if referencia is None:
                continue  # falta el extremo: no se aproxima con la vela más cercana
            movimiento = variacion(referencia.cierre, ultima.cierre)
            if movimiento is None or abs(movimiento) < ventana.porcentaje:
                continue
            return ventana, referencia, movimiento
        return None

    def _avance_desde(
        self, previo: Aviso | None, direccion: str, cierre: Decimal
    ) -> Decimal | None:
        """Cuánto se movió el precio desde el último aviso, si es hacia el mismo lado.

        Devuelve `None` cuando no hay con qué comparar o cuando el precio se fue para el
        otro lado: en ese caso no hay continuación posible y el movimiento actual se
        juzga solo por su ventana.
        """
        if previo is None or previo.direccion != direccion:
            return None
        avance = variacion(previo.cierre, cierre)
        if avance is None:
            return None
        # Un "avance" que apunta al lado contrario del movimiento no continúa nada.
        if (avance > 0) is not (direccion == SUBIDA):
            return None
        return avance

    # -- El mensaje -----------------------------------------------------------

    def _armar_alerta(
        self,
        contexto: ContextoDeEvaluacion,
        *,
        ventana: Ventana,
        referencia: Vela,
        ultima: Vela,
        movimiento: Decimal,
        direccion: str,
        avance: Decimal | None,
    ) -> Alerta:
        """Escribe el aviso con los números que permiten rehacer la cuenta."""
        verbo = "subió" if direccion == SUBIDA else "cayó"
        detalle = (
            f"{contexto.simbolo} {verbo} {texto_de_porcentaje(movimiento)} "
            f"en {ventana.minutos} min "
            f"({texto_de_precio(referencia.cierre)} → {texto_de_precio(ultima.cierre)})"
        )
        if avance is not None:
            detalle += f", y sigue: {texto_de_porcentaje(avance)} desde el aviso anterior"
        detalle += "."

        evidencia = {
            "direccion": direccion,
            "ventana_minutos": str(ventana.minutos),
            "porcentaje_exigido": str(ventana.porcentaje),
            # Los dos cierres son la fuente de verdad y van exactos: con ellos se rehace
            # el porcentaje. El movimiento va recortado a seis decimales porque una
            # división de Decimal arrastra veintiocho dígitos que no dicen nada.
            "cierre_referencia": str(referencia.cierre),
            "cierre_actual": str(ultima.cierre),
            "movimiento_pct": str(movimiento.quantize(Decimal("0.000001"))),
            "inicio_referencia": referencia.inicio.isoformat(),
            "inicio_vela": ultima.inicio.isoformat(),
            # De qué clase son las velas de los extremos: los precios son igual de
            # reales en las dos, pero quien lea la alerta tiene derecho a saberlo.
            "fuente": (
                referencia.fuente
                if referencia.fuente == ultima.fuente
                else f"{referencia.fuente}→{ultima.fuente}"
            ),
        }
        if avance is not None:
            evidencia["avance_desde_aviso_pct"] = str(avance.quantize(Decimal("0.000001")))

        return self.alerta(
            contexto,
            # `fuerte` cuando dobla lo exigido: 6% en cinco minutos no es "un poco más"
            # que 3%, es otra situación.
            severidad="fuerte" if abs(movimiento) >= ventana.porcentaje * 2 else "aviso",
            detalle=detalle,
            evidencia=evidencia,
            # Solo la dirección: las tres ventanas comparten silencio (misma noticia),
            # pero una subida no calla a una bajada (una reversión sí es noticia nueva).
            variante=direccion,
        )


def variacion(desde: Decimal, hasta: Decimal) -> Decimal | None:
    """Cambio porcentual entre dos precios. `None` si no se puede calcular.

    El precio cero no pasa en un par real de Binance, pero el detector no es quién para
    confiar en eso: una división por cero acá tumbaría la evaluación entera del símbolo.
    """
    if desde <= 0:
        return None
    return (hasta - desde) / desde * 100


def texto_de_porcentaje(valor: Decimal) -> str:
    """Escribe un porcentaje para leerlo en una frase: dos decimales y sin signo.

    El signo sobra porque la frase ya dice "subió" o "cayó", y el valor exacto viaja
    igual en la evidencia. Acá sí se redondea, a diferencia de los precios: dos
    decimales de porcentaje son la precisión que se puede leer.
    """
    return f"{abs(valor).quantize(Decimal('0.01'))}%"
