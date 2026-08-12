"""Lo que un detector puede mirar, y cómo se comporta cuando NO hay nada que mirar.

La mitad de estas pruebas son sobre huecos: sin tick, sin velas, sin historia
suficiente. Es donde vive la regla de oro. Un contexto vacío tiene que producir un
`None` limpio, nunca un cero ni un precio heredado: un cero afirma "no se movió" y un
precio viejo afirma "así está ahora", y las dos cosas son mentira dicha con seguridad.
"""

from decimal import Decimal

from app.detectores.base import ContextoDeEvaluacion

from .conftest import (
    MOMENTO,
    DetectorConHistoria,
    hacer_contexto,
    hacer_tick,
    hacer_vela,
)

# -- Qué velas cuentan ---------------------------------------------------------


def test_velas_cerradas_descarta_la_que_esta_a_medio_formar():
    """La última vela siempre está en curso: sacar conclusiones de ella es opinar
    sobre un minuto que todavía no terminó."""
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103", completa=False))
    )

    assert len(contexto.velas) == 3
    assert len(contexto.velas_cerradas) == 2


def test_ultima_cerrada_es_la_ultima_COMPLETA():
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103", completa=False))
    )

    assert contexto.ultima_cerrada.cierre == Decimal("102")


def test_sin_velas_cerradas_no_hay_ultima():
    contexto = hacer_contexto(velas=(hacer_vela("103", completa=False),))

    assert contexto.ultima_cerrada is None


# -- De dónde sale el precio ---------------------------------------------------


def test_prefiere_el_tick_vivo():
    contexto = hacer_contexto(tick=hacer_tick("64000"), velas=(hacer_vela("100"),))

    assert contexto.precio == Decimal("64000")
    assert contexto.origen_precio == "vivo"


def test_sin_tick_cae_al_ultimo_cierre_guardado():
    contexto = hacer_contexto(velas=(hacer_vela("102"),))

    assert contexto.precio == Decimal("102")
    assert contexto.origen_precio == "guardado"


def test_sin_nada_el_precio_es_none_y_se_dice():
    """No se inventa un precio, y además se declara que no hay."""
    contexto = hacer_contexto()

    assert contexto.precio is None
    assert contexto.origen_precio is None


def test_el_precio_no_pierde_decimales():
    """Va y vuelve como Decimal: si en algún lado se convirtiera a float, esto falla."""
    contexto = hacer_contexto(tick=hacer_tick("63745.92000001"))

    assert contexto.precio == Decimal("63745.92000001")
    assert str(contexto.precio) == "63745.92000001"


# -- Sin material, no se opina -------------------------------------------------


def test_con_menos_velas_de_las_necesarias_no_puede_opinar():
    """Un cálculo estadístico con cuatro muestras no es estadística: es un número con
    cara de estadística. Preferimos no decir nada."""
    detector = DetectorConHistoria()  # pide 3
    contexto = hacer_contexto(velas=(hacer_vela("101"), hacer_vela("102")))

    assert detector.puede_opinar(contexto) is False


def test_con_las_velas_justas_ya_puede_opinar():
    detector = DetectorConHistoria()
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103"))
    )

    assert detector.puede_opinar(contexto) is True


def test_las_velas_en_curso_no_cuentan_para_el_minimo():
    """Tres velas, pero una sin cerrar: siguen siendo dos utilizables."""
    detector = DetectorConHistoria()
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103", completa=False))
    )

    assert detector.puede_opinar(contexto) is False


# -- El momento de la evaluación -----------------------------------------------


def test_el_contexto_lleva_su_propio_momento():
    """Los detectores usan `contexto.momento` y no `datetime.now()`.

    Es lo que va a permitir correrlos sobre la historia (backtesting, v2.0): con
    `now()` adentro, un detector siempre miraría el presente aunque se lo alimente
    con datos de marzo.
    """
    contexto = ContextoDeEvaluacion(simbolo="BTCUSDT", momento=MOMENTO)

    assert contexto.momento == MOMENTO


def test_la_alerta_hereda_el_momento_del_contexto():
    detector = DetectorConHistoria()
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103"))
    )

    assert detector.evaluar(contexto)[0].momento == MOMENTO
