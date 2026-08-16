"""Alerta #3: que reconozca lo raro sin dejarse arrastrar por lo raro (paso 3.4).

Las pruebas que importan acá no son "¿avisa cuando hay un pico?" sino las de los bordes
donde un z-score mal hecho se rompe: después de un episodio grande, en calma total, y
cuando el episodio se estira varios tramos. Son exactamente los tres momentos que
justifican que este detector use mediana y MAD en vez de media y desviación.

La referencia real son 288 tramos (24 h). Acá se usan detectores con referencias cortas
para que las series se puedan leer, que es justamente para lo que el detector recibe sus
parámetros por constructor.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.detectores.volatilidad import VolatilidadAnomala, amplitud_de
from app.modelos import Vela

from .conftest import MOMENTO, hacer_contexto

CALMA = ("0.2", "0.3", "0.25", "0.35", "0.2", "0.3", "0.25", "0.35", "0.2", "0.3")
"""Diez tramos tranquilos con algo de variación: mediana 0,275% y un MAD que no es cero.
Sin variación el detector se calla a propósito (no hay con qué comparar)."""


def vela(amplitud: str, minuto: int = 0, completa: bool = True) -> Vela:
    """Una vela de apertura 100 cuyo recorrido máximo-mínimo es el % pedido."""
    recorrido = Decimal(amplitud)
    return Vela(
        inicio=MOMENTO + timedelta(minutes=5 * minuto),
        apertura=Decimal(100),
        maximo=Decimal(100) + recorrido,
        minimo=Decimal(100),
        cierre=Decimal(100) + recorrido,
        volumen=Decimal(5),
        volumen_cotizado=Decimal(500),
        operaciones=42,
        fuente="propia",
        completa=completa,
    )


def serie(*amplitudes: str) -> tuple[Vela, ...]:
    return tuple(vela(amplitud, minuto) for minuto, amplitud in enumerate(amplitudes))


def detector(**extra) -> VolatilidadAnomala:
    """Un detector con referencia de 10 tramos, para que las series se puedan leer."""
    opciones = {"velas_de_referencia": 10} | extra
    return VolatilidadAnomala(**opciones)


def mirar(det: VolatilidadAnomala, velas: tuple[Vela, ...], simbolo: str = "BTCUSDT"):
    # El intervalo va explícito porque este detector mira tramos de 5 minutos: es lo que
    # le pasaría el motor, y lo que sale escrito en el mensaje y en la evidencia.
    return det.evaluar(hacer_contexto(velas=velas, simbolo=simbolo, intervalo="5m"))


# -- Lo que tiene que reconocer ------------------------------------------------


def test_avisa_cuando_el_tramo_se_sale_de_lo_normal():
    alertas = mirar(detector(), serie(*CALMA, "3"))

    assert len(alertas) == 1
    assert "se agitó 3.00%" in alertas[0].detalle
    assert "0.28%" in alertas[0].detalle  # la mediana de la referencia
    assert Decimal(alertas[0].evidencia["z"]) >= 5


def test_un_tramo_normal_no_dice_nada():
    assert mirar(detector(), serie(*CALMA, "0.3")) == []


def test_lo_muy_raro_sube_a_fuerte():
    alertas = mirar(detector(), serie(*CALMA, "10"))

    assert alertas[0].severidad == "fuerte"


def test_la_referencia_excluye_al_tramo_que_se_esta_juzgando():
    """Si el pico entrara en su propia referencia, se estaría comparando contra sí mismo."""
    alerta = mirar(detector(), serie(*CALMA, "3"))[0]

    assert alerta.evidencia["muestras"] == "10"
    # La mediana es la de los diez tramos tranquilos: el 3% no la movió.
    assert alerta.evidencia["mediana_24h_pct"] == "0.28"


# -- Los bordes donde un z-score clásico se rompe -------------------------------


def test_un_pico_en_la_referencia_no_deja_ciego_al_siguiente():
    """El motivo de usar mediana y MAD, y no media y desviación estándar.

    Con media y σ, un 10% metido en la referencia infla tanto la dispersión que el
    siguiente pico parecido pasa desapercibido: Argos se quedaría ciego justo después de
    un evento grande, que es cuando más se lo necesita. La prueba hace las dos cuentas
    para que el contraste quede escrito y no haya que creerlo.
    """
    con_pico = ("0.2", "0.3", "10", "0.25", "0.35", "0.2", "0.3", "0.25", "0.35", "0.2")

    alertas = mirar(detector(), serie(*con_pico, "5"))
    assert len(alertas) == 1
    assert Decimal(alertas[0].evidencia["z"]) > 40  # robusto: clarísimamente raro

    # La misma medición con el z de manual sobre los mismos números.
    muestras = [Decimal(x) for x in con_pico]
    media = sum(muestras) / len(muestras)
    desviacion = (sum((x - media) ** 2 for x in muestras) / len(muestras)) ** Decimal("0.5")
    z_clasico = (Decimal(5) - media) / desviacion

    assert z_clasico < 3  # el mismo pico, invisible para el criterio clásico


def test_en_calma_absoluta_el_piso_impide_hablar():
    """Diez veces más agitado que nada sigue siendo nada.

    Sin el piso, una madrugada muerta produce z enormes con movimientos irrelevantes.
    """
    dormido = ("0.02", "0.03", "0.025", "0.035", "0.02", "0.03", "0.025", "0.035", "0.02", "0.03")

    alertas = mirar(detector(), serie(*dormido, "0.3"))

    assert alertas == []  # z altísimo, pero 0,3% de recorrido no es noticia


def test_sin_dispersion_no_se_inventa_un_infinito():
    """Si toda la referencia tiene la misma amplitud, no hay con qué comparar."""
    plano = ("1",) * 10

    assert mirar(detector(), serie(*plano, "5")) == []


def test_una_apertura_en_cero_no_revienta():
    assert amplitud_de(vela("1")) == Decimal(1)
    rota = Vela(
        inicio=MOMENTO,
        apertura=Decimal(0),
        maximo=Decimal(1),
        minimo=Decimal(0),
        cierre=Decimal(1),
        volumen=Decimal(1),
        volumen_cotizado=Decimal(1),
        operaciones=1,
        fuente="propia",
        completa=True,
    )
    assert amplitud_de(rota) is None
    assert mirar(detector(), serie(*CALMA) + (rota,)) == []


# -- Un episodio, un aviso ------------------------------------------------------


def test_no_repite_mientras_el_episodio_sigue_abierto():
    det = detector()

    primera = mirar(det, serie(*CALMA, "3"))
    segunda = mirar(det, serie(*CALMA, "3", "3.5"))

    assert len(primera) == 1
    assert segunda == []


def test_vuelve_a_avisar_despues_de_que_se_calma():
    det = detector()

    assert len(mirar(det, serie(*CALMA, "3"))) == 1
    # Un tramo tranquilo devuelve el z por debajo del umbral de rearme…
    assert mirar(det, serie(*CALMA, "3", "0.3")) == []
    # …y el episodio siguiente vuelve a ser noticia.
    assert len(mirar(det, serie(*CALMA, "3", "0.3", "3"))) == 1


def test_cada_simbolo_lleva_su_propio_episodio():
    det = detector()
    velas = serie(*CALMA, "3")

    assert len(mirar(det, velas, simbolo="BTCUSDT")) == 1
    assert len(mirar(det, velas, simbolo="ETHUSDT")) == 1


# -- Material insuficiente ------------------------------------------------------


def test_sin_la_referencia_completa_no_opina():
    """Un MAD de veinte tramos no es "lo normal del activo": es lo normal del último rato."""
    det = detector()
    contexto = hacer_contexto(velas=serie("0.2", "0.3", "5"))

    assert det.puede_opinar(contexto) is False
    assert det.evaluar(contexto) == []


def test_la_vela_en_curso_no_cuenta():
    det = detector()
    velas = serie(*CALMA) + (vela("8", minuto=10, completa=False),)

    assert mirar(det, velas) == []


# -- La evidencia ---------------------------------------------------------------


def test_la_evidencia_permite_rehacer_la_cuenta():
    alerta = mirar(detector(), serie(*CALMA, "3"))[0]
    evidencia = alerta.evidencia

    maximo = Decimal(evidencia["maximo"])
    minimo = Decimal(evidencia["minimo"])
    apertura = Decimal(evidencia["apertura"])

    assert (maximo - minimo) / apertura * 100 == Decimal(3)
    assert evidencia["intervalo"] == "5m"
    assert "en 5 min" in alerta.detalle


@pytest.mark.parametrize("amplitud,espera_alerta", [("0.5", False), ("3", True)])
def test_el_piso_manda_sobre_el_z(amplitud, espera_alerta):
    """Entre el piso y el z, el que calla gana: los dos tienen que dar el visto bueno."""
    det = detector(amplitud_minima=Decimal("1"))

    alertas = mirar(det, serie(*CALMA, amplitud))

    assert bool(alertas) is espera_alerta
