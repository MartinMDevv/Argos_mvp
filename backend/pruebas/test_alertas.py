"""Cómo se arma una alerta: la clave, la evidencia y la severidad.

La `clave` y la `evidencia` son las dos piezas de las que depende todo lo demás. La
clave es lo que permite que Argos no repita; la evidencia es lo que permite creerle.
Ninguna de las dos se ve a simple vista cuando funcionan bien, así que se prueban.
"""

import pytest

from .conftest import (
    DetectorConHistoria,
    DetectorQueSiempreEmite,
    hacer_contexto,
    hacer_tick,
    hacer_vela,
)

# -- La clave: la identidad de la SITUACIÓN ------------------------------------


def test_la_clave_junta_detector_y_simbolo():
    alerta = DetectorQueSiempreEmite().evaluar(hacer_contexto(tick=hacer_tick()))

    assert alerta.clave == "prueba_siempre:BTCUSDT"


def test_el_mismo_detector_en_otro_simbolo_es_otra_clave():
    """Que BTC esté raro no tiene por qué silenciar lo que pase con ETH."""
    detector = DetectorQueSiempreEmite()

    btc = detector.evaluar(hacer_contexto(tick=hacer_tick(), simbolo="BTCUSDT"))
    eth = detector.evaluar(hacer_contexto(tick=hacer_tick(), simbolo="ETHUSDT"))

    assert btc.clave != eth.clave


def test_la_variante_separa_dos_situaciones_del_mismo_detector():
    """El caso real: dos umbrales configurados para el mismo par.

    Si BTC cruza los 70.000, eso no debe silenciar el aviso de que cruzó los 60.000:
    son dos noticias distintas del mismo detector sobre el mismo símbolo.
    """
    detector = DetectorQueSiempreEmite()
    contexto = hacer_contexto(tick=hacer_tick())

    arriba = detector.alerta(
        contexto, severidad="info", detalle="x", evidencia={}, variante="70000:arriba"
    )
    abajo = detector.alerta(
        contexto, severidad="info", detalle="x", evidencia={}, variante="60000:abajo"
    )

    assert arriba.clave == "prueba_siempre:BTCUSDT:70000:arriba"
    assert arriba.clave != abajo.clave


# -- La evidencia: la regla de oro hecha estructura ----------------------------


def test_la_alerta_viaja_con_los_numeros_que_la_justifican():
    detector = DetectorConHistoria()
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103"))
    )

    alerta = detector.evaluar(contexto)

    assert alerta.evidencia["cierre"] == "103"
    assert alerta.evidencia["velas_cerradas"] == "3"


def test_la_evidencia_va_toda_como_texto():
    """Mismo motivo que en el resto de Argos: JSON no tiene decimales exactos, y un
    precio que pasa por float deja de ser el precio que mandó Binance."""
    detector = DetectorConHistoria()
    contexto = hacer_contexto(
        velas=(hacer_vela("101"), hacer_vela("102"), hacer_vela("103"))
    )

    alerta = detector.evaluar(contexto)

    assert all(isinstance(valor, str) for valor in alerta.evidencia.values())


def test_una_alerta_no_se_puede_editar_despues():
    """Una alerta es un hecho: se emitió en un momento, con unos números."""
    alerta = DetectorQueSiempreEmite().evaluar(hacer_contexto(tick=hacer_tick()))

    with pytest.raises(AttributeError):
        alerta.detalle = "otra cosa"  # type: ignore[misc]


def test_la_alerta_recien_emitida_todavia_no_tiene_id():
    """El id lo pone la base al guardarla; antes de eso, decir un número sería inventarlo."""
    alerta = DetectorQueSiempreEmite().evaluar(hacer_contexto(tick=hacer_tick()))

    assert alerta.id is None


# -- La severidad --------------------------------------------------------------


def test_una_severidad_inventada_es_un_error():
    """Lista cerrada: si cada detector inventa su escala, el panel no sabe cuál pintar
    más fuerte y la palabra deja de significar algo."""
    detector = DetectorQueSiempreEmite()

    with pytest.raises(ValueError, match="Severidad 'catastrofica' desconocida"):
        detector.alerta(
            hacer_contexto(tick=hacer_tick()),
            severidad="catastrofica",
            detalle="x",
            evidencia={},
        )


@pytest.mark.parametrize("severidad", ["info", "aviso", "fuerte"])
def test_las_tres_severidades_validas_pasan(severidad):
    alerta = DetectorQueSiempreEmite().alerta(
        hacer_contexto(tick=hacer_tick()), severidad=severidad, detalle="x", evidencia={}
    )

    assert alerta.severidad == severidad


# -- Lo que la alerta hereda del detector --------------------------------------


def test_la_alerta_sabe_de_que_detector_salio():
    alerta = DetectorQueSiempreEmite().evaluar(hacer_contexto(tick=hacer_tick()))

    assert alerta.detector == "prueba_siempre"
    assert alerta.titulo == "Prueba · siempre"
