"""Alerta #4: se está operando mucho más de lo que se acostumbra a esta hora (paso 3.5).

La última de las cuatro del MVP, y la única que puede avisar **antes** de que el precio
se mueva. Las otras tres reaccionan al precio —cruzó, saltó, se agitó—; el volumen es lo
que se mueve primero cuando alguien grande empieza a entrar o a salir. De ahí lo que dice
el spec: suele *preceder* al movimiento en vez de acompañarlo.

Por eso la alerta cuenta también qué hizo el precio en ese tramo. Volumen alto **con**
movimiento es la confirmación de lo que ya se ve; volumen alto **sin** movimiento es la
señal interesante: alguien está operando fuerte y el precio todavía no lo refleja.

## RVOL: comparar contra la misma hora, no contra el día entero
El volumen de cripto tiene horario, y no un poco: medido sobre los 369 días de la base,
la franja de las 14:00 UTC —cuando abre Estados Unidos— mueve **2,8 veces** lo de las
21:00 UTC, todos los días. Comparar el volumen de ahora contra la mediana de las últimas
24 horas no detecta anomalías: detecta el amanecer de Nueva York. Se probó, y una cuarta
parte de las alertas caía en tres horas del día.

Lo que usa cualquier operador para esto es el **RVOL** (*relative volume*): el volumen de
ahora dividido por el volumen típico de **esta misma franja horaria** en los días
anteriores. RVOL 1 = un martes cualquiera a esta hora. RVOL 5 = se está operando cinco
veces lo acostumbrado *para esta hora*, y eso ya no lo explica el reloj.

La tabla de "lo típico de cada franja" la arma `app/perfiles.py` y se la pasa el motor en
`contexto.extras`: el detector no sale a buscarla, porque tiene que seguir siendo puro
para poder rebobinarse sobre el pasado (ver `detectores/base.py`).

## Lo que este detector NO puede saber solo
Que el volumen sea raro no dice **hacia dónde**. Un pico puede ser alguien acumulando o
alguien liquidando, y desde el volumen agregado las dos cosas se ven igual. Argos lo dice
así, sin adornar: informa que hay actividad inusual y muestra qué hizo el precio mientras
tanto. Deducir la intención sería inventar, que es justo lo que la regla de oro prohíbe.
(El dato que sí distingue —quién fue el agresor de cada operación— existe en `Tick`
(`lado_agresor`) y está anotado para más adelante: acá se mira la vela, que ya viene
agregada y perdió esa información.)

## Un episodio, un aviso
Igual que la #3: se avisa **al entrar** en zona rara y no se repite mientras el episodio
siga abierto; el detector se rearma cuando el RVOL vuelve a valores normales. Un pico de
volumen dura varios tramos y no son varias noticias.
"""

from datetime import timedelta
from decimal import Decimal

from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.registro import registrar
from app.modelos import Alerta, Vela
from app.perfiles import franja_de

CLAVE_PERFIL = "perfil_volumen"
"""Con qué nombre viaja el perfil intradía dentro de `contexto.extras`."""

INTERVALO = "5m"
"""Mismo tramo que la #3, y el mismo que usa el perfil de `perfiles.py`."""

RVOL_PARA_AVISAR = Decimal("30")
"""Cuántas veces lo habitual de esta franja hay que operar para que sea noticia.

**Mucho más alto que el RVOL de 2 o 3 del que se habla en el ambiente, y con motivo.**
Ese número es para el RVOL *acumulado del día* —cuánto lleva operado una acción a media
rueda contra lo que suele llevar—, que es una medida lenta y estable. Acá se mira un
tramo de cinco minutos, donde el volumen pega saltos todo el tiempo: medido sobre los 369
días de la base, un umbral de 5 daba **165 alertas al mes** y hasta el de 12 daba 27.

En 30 quedan 3,9 al mes en BTC y 5,3 en ETH, en línea con las otras tres alertas. El
número sale de la historia, no de la costumbre."""

RVOL_PARA_REARMAR = Decimal("2")
"""Por debajo de esto el episodio se considera terminado y se puede volver a avisar.

Dos es el "está activo" de manual, y acá cumple bien ese papel: mientras el volumen siga
al doble de lo normal, lo que empezó no terminó."""

RVOL_PARA_FUERTE = Decimal("60")
"""A partir de acá la alerta sube de `aviso` a `fuerte`. Sobre la historia real, los
picos de esta magnitud aparecen unas pocas veces al año."""

VOLUMEN_MINIMO = Decimal("500000")
"""Piso absoluto en USDT por tramo de 5 minutos.

Mismo argumento que el piso de la #3: "treinta veces lo habitual" en una franja muerta
puede seguir siendo calderilla. **Con BTC y ETH hoy no cambia nada** —se midió: con piso
de 500 mil o de 5 millones salen exactamente las mismas alertas, porque un tramo raro de
estos dos siempre mueve decenas de millones—, así que está para cuando Argos mire activos
más chicos, que es adonde va el proyecto. Es un seguro barato, no el filtro principal."""

MOVIMIENTO_NOTORIO = Decimal("0.3")
"""A partir de este cambio de precio (en %) se considera que el volumen "vino con
movimiento". Por debajo, la alerta dice que el precio todavía no lo refleja — que es la
versión interesante de esta señal."""


@registrar
class VolumenAnomalo(Detector):
    """Avisa cuando se opera mucho más de lo que se acostumbra a esta hora del día."""

    nombre = "volumen_anomalo"
    titulo = "Volumen anómalo"
    descripcion = (
        "Avisa cuando el volumen operado supera varias veces lo típico de esta misma "
        "franja horaria (RVOL), comparando contra los últimos 14 días."
    )
    cadencia = Cadencia.POR_VELA_CERRADA
    intervalo = INTERVALO
    velas_necesarias = 1
    """Solo el tramo que se juzga: la referencia no sale de las velas sino del perfil."""

    silencio = timedelta(minutes=30)
    """Red de seguridad; el antirruido real es el rearme, igual que en la #3."""

    def __init__(
        self,
        rvol_para_avisar: Decimal = RVOL_PARA_AVISAR,
        rvol_para_rearmar: Decimal = RVOL_PARA_REARMAR,
        rvol_para_fuerte: Decimal = RVOL_PARA_FUERTE,
        volumen_minimo: Decimal = VOLUMEN_MINIMO,
    ) -> None:
        self.rvol_para_avisar = rvol_para_avisar
        self.rvol_para_rearmar = rvol_para_rearmar
        self.rvol_para_fuerte = rvol_para_fuerte
        self.volumen_minimo = volumen_minimo

        # Símbolo → ¿ya avisamos de este episodio y esperamos que vuelva a lo normal?
        self._en_episodio: dict[str, bool] = {}

    def puede_opinar(self, contexto: ContextoDeEvaluacion) -> bool:
        """Hace falta un tramo cerrado y un perfil con el que compararlo.

        Sin perfil no se opina y no se improvisa una referencia con lo que haya a mano:
        el volumen de las tres de la mañana comparado contra el promedio del día es
        exactamente el error que este detector existe para no cometer.
        """
        return bool(contexto.velas_cerradas) and bool(contexto.extras.get(CLAVE_PERFIL))

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        perfil = contexto.extras.get(CLAVE_PERFIL)
        if not isinstance(perfil, dict) or not perfil:
            return []

        actual = contexto.ultima_cerrada
        if actual is None:
            return []

        franja = franja_de(actual.inicio)
        tipico = perfil.get(franja)
        if tipico is None or tipico <= 0:
            # De esta franja no hay costumbre conocida (pocos días con datos). Se calla.
            return []

        volumen = actual.volumen_cotizado
        rvol = volumen / tipico

        if rvol < self.rvol_para_rearmar:
            self._en_episodio[contexto.simbolo] = False

        if rvol < self.rvol_para_avisar or volumen < self.volumen_minimo:
            return []

        if self._en_episodio.get(contexto.simbolo):
            return []

        self._en_episodio[contexto.simbolo] = True

        return [self._armar_alerta(contexto, actual, volumen, tipico, rvol, franja)]

    def _armar_alerta(
        self,
        contexto: ContextoDeEvaluacion,
        vela: Vela,
        volumen: Decimal,
        tipico: Decimal,
        rvol: Decimal,
        franja: int,
    ) -> Alerta:
        """Escribe el aviso, incluyendo qué hizo el precio mientras tanto."""
        variacion = vela.variacion
        hora = f"{vela.inicio:%H:%M}"

        detalle = (
            f"{contexto.simbolo} operó {texto(rvol)}× lo habitual para las {hora} UTC "
            f"({dinero(volumen)} contra {dinero(tipico)} de costumbre)"
        )

        if abs(variacion) >= MOVIMIENTO_NOTORIO:
            direccion = "subiendo" if variacion > 0 else "bajando"
            detalle += f", con el precio {direccion} {texto(abs(variacion))}%."
        else:
            # La versión que vale la pena mirar: mucha actividad y el precio quieto.
            detalle += f", y el precio casi no se movió ({texto(variacion)}%)."

        evidencia = {
            "rvol": texto(rvol),
            "rvol_exigido": str(self.rvol_para_avisar),
            "volumen_cotizado": str(volumen),
            "volumen_tipico_franja": str(tipico),
            "franja": str(franja),
            "hora_utc": hora,
            "variacion_precio_pct": texto(variacion),
            "apertura": str(vela.apertura),
            "cierre": str(vela.cierre),
            "inicio_vela": vela.inicio.isoformat(),
            "intervalo": contexto.intervalo,
            # `operaciones` NO se compara entre fuentes distintas (ver `modelos.Vela`),
            # así que viaja junto con la fuente o no significa nada.
            "operaciones": str(vela.operaciones),
            "fuente": vela.fuente,
        }

        return self.alerta(
            contexto,
            severidad="fuerte" if rvol >= self.rvol_para_fuerte else "aviso",
            detalle=detalle,
            evidencia=evidencia,
            # Sin variante: hay una sola situación posible por símbolo. Y a propósito no
            # se separa "con movimiento" de "sin movimiento": es el mismo episodio, y el
            # precio puede empezar a moverse en el tramo siguiente.
            variante="",
        )


def texto(valor: Decimal) -> str:
    """Dos decimales, para leerlo en una frase. El crudo va en la evidencia."""
    return str(valor.quantize(Decimal("0.01")))


def dinero(valor: Decimal) -> str:
    """Cifras grandes en formato corto: 12,4 M en vez de 12.431.887,42.

    Se redondea a propósito, y solo para el mensaje: nadie lee catorce dígitos de volumen
    en una notificación. El número exacto viaja entero en la evidencia.
    """
    if valor >= 1_000_000:
        return f"{valor / 1_000_000:.1f} M"
    if valor >= 1_000:
        return f"{valor / 1_000:.0f} K"
    return str(valor.quantize(Decimal("1")))
