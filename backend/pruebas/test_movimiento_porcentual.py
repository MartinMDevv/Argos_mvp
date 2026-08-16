"""Alerta #2: que avise el movimiento, y que lo avise UNA vez (paso 3.3).

La mitad de estas pruebas son sobre lo segundo. Un detector de movimiento porcentual es
fácil de escribir mal de una forma que parece correcta: mide bien el porcentaje, avisa
cuando corresponde… y lo vuelve a avisar en cada vela mientras el movimiento siga dentro
de la ventana, que en la de una hora son sesenta avisos del mismo salto.

Las pruebas le pasan series de cierres de 1 minuto, como haría el motor cuando cierra
una vela, y miran qué emite en cada paso.
"""

from datetime import timedelta
from decimal import Decimal

from app.detectores.movimiento_porcentual import (
    BAJADA,
    SUBIDA,
    MovimientoPorcentual,
    Ventana,
    texto_de_porcentaje,
    variacion,
)
from app.modelos import Vela

from .conftest import MOMENTO, hacer_contexto, hacer_vela

CINCO_MINUTOS = (Ventana(minutos=5, porcentaje=Decimal("3")),)
"""Una sola ventana, para las pruebas donde la elección entre ventanas no es el tema."""


def serie(*cierres: str) -> tuple[Vela, ...]:
    """Velas de 1 minuto consecutivas, con los cierres que se le pasen."""
    return tuple(
        hacer_vela(cierre=cierre, inicio=MOMENTO + timedelta(minutes=minuto))
        for minuto, cierre in enumerate(cierres)
    )


def mirar(detector: MovimientoPorcentual, velas: tuple[Vela, ...], simbolo: str = "BTCUSDT"):
    """Una evaluación, como la haría el motor al cerrar la última vela de la serie."""
    return detector.evaluar(hacer_contexto(velas=velas, simbolo=simbolo))


# -- Lo que tiene que avisar ---------------------------------------------------


def test_avisa_cuando_el_precio_sube_lo_suficiente():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    alertas = mirar(detector, serie("100", "100", "100", "100", "100", "104"))

    assert len(alertas) == 1
    assert "subió 4.00% en 5 min" in alertas[0].detalle
    assert "(100 → 104)" in alertas[0].detalle
    assert alertas[0].evidencia["direccion"] == SUBIDA


def test_avisa_cuando_el_precio_cae():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    alertas = mirar(detector, serie("100", "100", "100", "100", "100", "95"))

    assert len(alertas) == 1
    assert "cayó" in alertas[0].detalle
    assert alertas[0].evidencia["direccion"] == BAJADA


def test_no_avisa_si_el_movimiento_se_queda_corto():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    assert mirar(detector, serie("100", "100", "100", "100", "100", "102.9")) == []


def test_el_borde_exacto_cuenta_como_movimiento():
    """Un 3% clavado con la ventana en 3% avisa: el criterio es "al menos", no "más de"."""
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    assert len(mirar(detector, serie("100", "100", "100", "100", "100", "103"))) == 1


def test_dobla_lo_exigido_y_la_alerta_sube_a_fuerte():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    suave = mirar(detector, serie("100", "100", "100", "100", "100", "104"))
    assert suave[0].severidad == "aviso"

    otro = MovimientoPorcentual(CINCO_MINUTOS)
    violento = mirar(otro, serie("100", "100", "100", "100", "100", "106"))
    assert violento[0].severidad == "fuerte"


# -- Una noticia, una alerta ---------------------------------------------------


def test_gana_la_ventana_mas_corta_de_las_que_saltaron():
    """Un salto de 9% supera las tres ventanas; se cuenta una sola vez, la más corta."""
    detector = MovimientoPorcentual()

    velas = serie(*(["100"] * 60 + ["109"]))
    alertas = mirar(detector, velas)

    assert len(alertas) == 1
    assert alertas[0].evidencia["ventana_minutos"] == "5"


def test_una_ventana_larga_avisa_de_lo_que_la_corta_no_ve():
    """Movimiento lento: 9% en una hora sin que ningún tramo corto llegue a lo suyo.

    Subiendo parejo, cada 5 minutos son 0,75% (la ventana corta pide 2%) y cada 15 son
    2,25% (pide 3,5%). Ninguna de las dos ve nada; la de una hora sí. Ese es justamente
    el caso que justifica tener más de una ventana.
    """
    detector = MovimientoPorcentual()

    cierres = [str(100 + Decimal(9) * minuto / 60) for minuto in range(61)]
    alertas = mirar(detector, serie(*cierres))

    assert len(alertas) == 1
    assert alertas[0].evidencia["ventana_minutos"] == "60"


def test_las_ventanas_comparten_la_clave_para_compartir_el_silencio():
    """Lo que agrupa el antirruido es la dirección, no la ventana que saltó.

    Si la clave llevara la ventana, el mismo salto tendría tres claves distintas y el
    silencio del motor dejaría pasar tres avisos de la misma noticia.
    """
    corta = MovimientoPorcentual(CINCO_MINUTOS)
    larga = MovimientoPorcentual((Ventana(minutos=60, porcentaje=Decimal("3")),))

    por_la_corta = mirar(corta, serie(*(["100"] * 5 + ["104"])))
    por_la_larga = mirar(larga, serie(*(["100"] * 60 + ["104"])))

    assert por_la_corta[0].clave == por_la_larga[0].clave


def test_subida_y_bajada_no_se_callan_entre_si():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    subida = mirar(detector, serie("100", "100", "100", "100", "100", "104"))
    bajada = mirar(detector, serie("104", "104", "104", "104", "104", "100"))

    assert subida[0].clave != bajada[0].clave


# -- Moverse no es haberse movido ----------------------------------------------


def test_no_repite_el_mismo_movimiento_mientras_la_ventana_lo_arrastra():
    """El caso que hace inútil al detector ingenuo, y el motivo de que haya memoria."""
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    primera = mirar(detector, serie("100", "100", "100", "100", "100", "104"))
    assert len(primera) == 1

    # Minuto siguiente: el precio no hizo nada, pero el salto sigue dentro de la ventana
    # (la referencia ahora es la segunda vela, que también vale 100).
    quieto = mirar(detector, serie("100", "100", "100", "100", "100", "104", "104"))
    assert quieto == []


def test_si_el_movimiento_continua_vuelve_a_avisar():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    mirar(detector, serie("100", "100", "100", "100", "100", "104"))
    sigue = mirar(detector, serie("100", "100", "100", "100", "100", "104", "108.2"))

    assert len(sigue) == 1
    assert "y sigue" in sigue[0].detalle
    # Desde el aviso anterior (104), no desde el inicio del movimiento.
    assert sigue[0].evidencia["avance_desde_aviso_pct"].startswith("4.038")


def test_una_reversion_avisa_aunque_recien_hayamos_avisado_la_subida():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    mirar(detector, serie("100", "100", "100", "100", "100", "104"))
    vuelta = mirar(detector, serie("104", "104", "104", "104", "104", "100"))

    assert len(vuelta) == 1
    assert vuelta[0].evidencia["direccion"] == BAJADA


def test_callarse_no_mueve_el_ancla_del_ultimo_aviso():
    """Si cada evaluación corriera el ancla, un movimiento lento se avisaría de a poco.

    Sube 4% (avisa desde 104), después va sumando de a 1,5%: ninguno de esos pasos es
    continuación por sí solo, pero acumulados sí. El ancla tiene que quedarse en 104
    hasta que se emita la próxima alerta.
    """
    detector = MovimientoPorcentual(CINCO_MINUTOS)
    base = ["100"] * 5 + ["104"]

    assert len(mirar(detector, serie(*base))) == 1
    assert mirar(detector, serie(*base, "105.5")) == []  # +1,44% desde el aviso
    tercera = mirar(detector, serie(*base, "105.5", "107.2"))  # +3,08% desde el aviso

    assert len(tercera) == 1


def test_cada_simbolo_lleva_su_propia_memoria():
    detector = MovimientoPorcentual(CINCO_MINUTOS)
    velas = serie("100", "100", "100", "100", "100", "104")

    assert len(mirar(detector, velas, simbolo="BTCUSDT")) == 1
    assert len(mirar(detector, velas, simbolo="ETHUSDT")) == 1


# -- Huecos en la historia -----------------------------------------------------


def test_sin_la_vela_de_referencia_no_se_opina():
    """No se busca la más cercana: un movimiento de 5 min medido contra hace 6 es falso."""
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    completa = serie("100", "100", "100", "100", "100", "104")
    con_hueco = completa[1:]  # falta justo la referencia de la ventana
    anterior = (hacer_vela(cierre="100", inicio=MOMENTO - timedelta(minutes=1)),)

    assert len(mirar(detector, completa)) == 1
    assert mirar(MovimientoPorcentual(CINCO_MINUTOS), anterior + con_hueco) == []


def test_un_hueco_en_el_medio_no_estorba():
    """Lo que importa son los dos extremos: el movimiento neto se mide entre ellos."""
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    extremos = (
        hacer_vela(cierre="100", inicio=MOMENTO),
        hacer_vela(cierre="104", inicio=MOMENTO + timedelta(minutes=5)),
    )

    assert len(mirar(detector, extremos)) == 1


def test_con_menos_historia_que_la_ventana_corta_no_opina():
    detector = MovimientoPorcentual()

    assert detector.puede_opinar(hacer_contexto(velas=serie("100", "101", "102"))) is False


def test_alcanza_con_la_ventana_corta_aunque_falte_para_la_larga():
    """Pide historia para la de 60 min, pero empieza a vigilar con la de 5."""
    detector = MovimientoPorcentual()
    velas = serie(*(["100"] * 20))

    assert detector.velas_necesarias == 61
    assert detector.puede_opinar(hacer_contexto(velas=velas)) is True


def test_la_vela_en_curso_no_cuenta():
    """La última vela está a medio formar: su cierre todavía puede cambiar."""
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    velas = serie(*(["100"] * 6)) + (
        hacer_vela(cierre="104", inicio=MOMENTO + timedelta(minutes=6), completa=False),
    )

    assert mirar(detector, velas) == []


# -- La evidencia --------------------------------------------------------------


def test_la_evidencia_permite_rehacer_la_cuenta():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    alerta = mirar(detector, serie("100", "100", "100", "100", "100", "104"))[0]
    evidencia = alerta.evidencia

    desde = Decimal(evidencia["cierre_referencia"])
    hasta = Decimal(evidencia["cierre_actual"])

    assert variacion(desde, hasta) == Decimal(4)
    assert evidencia["porcentaje_exigido"] == "3"
    assert evidencia["fuente"] == "propia"


def test_la_evidencia_avisa_cuando_los_extremos_son_de_distinta_fuente():
    """Los precios son igual de reales, pero quien lea la alerta merece saberlo.

    Pasa de verdad en el borde entre lo que trajo el backfill y lo que Argos vio con sus
    propios ojos: la referencia de hace una hora puede ser de Binance y la última, nuestra.
    """
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    referencia = hacer_vela(cierre="100", inicio=MOMENTO)
    del_backfill = Vela(
        **{campo: getattr(referencia, campo) for campo in Vela.__slots__ if campo != "fuente"},
        fuente="historia",
    )
    ultima = hacer_vela(cierre="104", inicio=MOMENTO + timedelta(minutes=5))

    alerta = mirar(detector, (del_backfill, ultima))[0]

    assert alerta.evidencia["fuente"] == "historia→propia"


# -- Cuentas de borde ----------------------------------------------------------


def test_un_precio_de_referencia_en_cero_no_revienta():
    detector = MovimientoPorcentual(CINCO_MINUTOS)

    assert mirar(detector, serie("0", "1", "1", "1", "1", "1")) == []
    assert variacion(Decimal(0), Decimal(1)) is None


def test_el_porcentaje_se_escribe_con_dos_decimales_y_sin_signo():
    assert texto_de_porcentaje(Decimal("-4.0384615384")) == "4.04%"
    assert texto_de_porcentaje(Decimal("3")) == "3.00%"
