"""Alerta #4: que el reloj no se le pase por anomalía (paso 3.5).

La prueba que da sentido a todo el detector es `test_el_mismo_volumen_es_normal_de_dia_y
_raro_de_madrugada`: el mismo número de dólares operados tiene que ser rutina a las 14:00
UTC y noticia a las 03:00. Un detector que compare contra el promedio del día entero no
puede distinguir esas dos situaciones, y por eso existe el perfil intradía.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.detectores.volumen import CLAVE_PERFIL, VolumenAnomalo
from app.modelos import Vela
from app.perfiles import franja_de

from .conftest import hacer_contexto

DIA = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)

TARDE = DIA + timedelta(hours=14)  # 14:00 UTC: la franja más cargada del día
MADRUGADA = DIA + timedelta(hours=3)  # 03:00 UTC: una de las más flojas

TIPICO_TARDE = Decimal("6000000")
TIPICO_MADRUGADA = Decimal("2000000")


def perfil(**franjas: Decimal) -> dict[int, Decimal]:
    """Un perfil de mentira con solo las franjas que la prueba necesita."""
    return {
        franja_de(TARDE): TIPICO_TARDE,
        franja_de(MADRUGADA): TIPICO_MADRUGADA,
        **{int(clave[1:]): valor for clave, valor in franjas.items()},
    }


def vela(volumen: str, momento: datetime = TARDE, cierre: str = "100") -> Vela:
    """Un tramo de 5 minutos con el volumen (en USDT) y el cierre que se pidan."""
    return Vela(
        inicio=momento,
        apertura=Decimal(100),
        maximo=Decimal(101),
        minimo=Decimal(99),
        cierre=Decimal(cierre),
        volumen=Decimal(10),
        volumen_cotizado=Decimal(volumen),
        operaciones=500,
        fuente="propia",
        completa=True,
    )


def detector(**extra) -> VolumenAnomalo:
    """Un detector con umbrales cómodos de leer, no los de producción.

    Los de verdad (RVOL 30) obligarían a escribir volúmenes enormes en cada prueba y las
    volverían ilegibles; peor todavía, atarían las pruebas a un número que se recalibra
    con los datos. Lo que se prueba acá es el comportamiento, no la calibración.
    """
    opciones = {"rvol_para_avisar": Decimal(5), "rvol_para_fuerte": Decimal(10)} | extra
    return VolumenAnomalo(**opciones)


def mirar(det: VolumenAnomalo, velas, extras=None, simbolo: str = "BTCUSDT"):
    return det.evaluar(
        hacer_contexto(
            velas=velas if isinstance(velas, tuple) else (velas,),
            simbolo=simbolo,
            intervalo="5m",
            extras={CLAVE_PERFIL: perfil()} if extras is None else extras,
        )
    )


# -- El motivo de existir del perfil intradía ----------------------------------


def test_el_mismo_volumen_es_normal_de_dia_y_raro_de_madrugada():
    """Doce millones a las 14:00 es un día activo; a las 03:00, seis veces lo habitual.

    Es exactamente lo que un detector contra "la mediana de las últimas 24 h" no puede
    ver, y el motivo por el que se mide RVOL contra la misma franja horaria.
    """
    monto = "12000000"

    de_dia = mirar(detector(), vela(monto, TARDE))
    de_madrugada = mirar(detector(), vela(monto, MADRUGADA))

    assert de_dia == []  # 2× lo habitual de esa franja: un martes movido
    assert len(de_madrugada) == 1  # 6× lo habitual de esa franja: eso sí es raro
    assert de_madrugada[0].evidencia["rvol"] == "6.00"


# -- Lo que tiene que avisar ---------------------------------------------------


def test_avisa_cuando_se_opera_muchas_veces_lo_habitual():
    alertas = mirar(detector(), vela("30000000", TARDE))

    assert len(alertas) == 1
    assert "5.00× lo habitual para las 14:00 UTC" in alertas[0].detalle
    assert alertas[0].evidencia["volumen_tipico_franja"] == str(TIPICO_TARDE)


def test_un_volumen_normal_no_dice_nada():
    assert mirar(detector(), vela("7000000", TARDE)) == []


def test_lo_muy_raro_sube_a_fuerte():
    alertas = mirar(detector(), vela("70000000", TARDE))

    assert alertas[0].severidad == "fuerte"


# -- Volumen con y sin movimiento de precio ------------------------------------


def test_avisa_distinto_cuando_el_precio_no_acompana():
    """La versión interesante de esta señal: mucha actividad y el precio quieto."""
    quieto = mirar(detector(), vela("30000000", TARDE, cierre="100.1"))

    assert "el precio casi no se movió" in quieto[0].detalle
    assert quieto[0].evidencia["variacion_precio_pct"] == "0.10"


def test_cuando_el_precio_si_se_mueve_lo_dice():
    con_caida = mirar(detector(), vela("30000000", TARDE, cierre="98"))

    assert "bajando 2.00%" in con_caida[0].detalle


# -- Sin material no se opina ---------------------------------------------------


def test_sin_perfil_no_opina():
    """Sin la costumbre de la franja no hay con qué comparar, y no se improvisa."""
    det = detector()
    contexto = hacer_contexto(velas=(vela("99000000", MADRUGADA),), intervalo="5m", extras={})

    assert det.puede_opinar(contexto) is False
    assert det.evaluar(contexto) == []


def test_una_franja_sin_costumbre_conocida_se_calla():
    """El perfil no cubre todas las franjas si faltan días con datos."""
    otra_hora = DIA + timedelta(hours=9)

    assert mirar(detector(), vela("99000000", otra_hora)) == []


def test_el_piso_absoluto_tapa_las_franjas_muertas():
    """Cinco veces la nada sigue siendo poca cosa.

    El RVOL da 6 y pasaría el umbral: lo que la calla es el piso. Con el detector de
    producción esta prueba pasaría igual sin piso —RVOL 30 ya la descarta— y no estaría
    probando nada.
    """
    perfil_muerto = {franja_de(MADRUGADA): Decimal("20000")}
    velas = (vela("120000", MADRUGADA),)  # 6× lo habitual, pero son 120 mil dólares
    extras = {CLAVE_PERFIL: perfil_muerto}

    assert mirar(detector(), velas, extras=extras) == []
    # Sin piso, el mismo caso sí habla: la diferencia la hace el piso y nada más.
    assert len(mirar(detector(volumen_minimo=Decimal(0)), velas, extras=extras)) == 1


# -- Un episodio, un aviso ------------------------------------------------------


def test_no_repite_mientras_el_episodio_sigue_abierto():
    det = detector()

    primera = mirar(det, vela("30000000", TARDE))
    segunda = mirar(det, vela("35000000", TARDE))

    assert len(primera) == 1
    assert segunda == []


def test_vuelve_a_avisar_cuando_el_volumen_ya_habia_bajado():
    det = detector()

    assert len(mirar(det, vela("30000000", TARDE))) == 1
    assert mirar(det, vela("6000000", TARDE)) == []  # RVOL 1: se rearma
    assert len(mirar(det, vela("30000000", TARDE))) == 1


def test_cada_simbolo_lleva_su_propio_episodio():
    det = detector()

    assert len(mirar(det, vela("30000000", TARDE), simbolo="BTCUSDT")) == 1
    assert len(mirar(det, vela("30000000", TARDE), simbolo="ETHUSDT")) == 1


# -- La evidencia ---------------------------------------------------------------


def test_la_evidencia_permite_rehacer_la_cuenta():
    alerta = mirar(detector(), vela("30000000", TARDE))[0]
    evidencia = alerta.evidencia

    volumen = Decimal(evidencia["volumen_cotizado"])
    tipico = Decimal(evidencia["volumen_tipico_franja"])

    assert volumen / tipico == Decimal(5)
    assert evidencia["hora_utc"] == "14:00"
    assert evidencia["franja"] == str(franja_de(TARDE))
    assert evidencia["fuente"] == "propia"


# -- La franja --------------------------------------------------------------------


def test_la_franja_parte_el_dia_en_tramos_de_cinco_minutos():
    assert franja_de(DIA) == 0
    assert franja_de(DIA + timedelta(minutes=5)) == 1
    assert franja_de(DIA + timedelta(hours=12)) == 144
    assert franja_de(DIA + timedelta(hours=23, minutes=55)) == 287
    # Los minutos dentro de la franja no la mueven: 14:00 y 14:04 son la misma.
    assert franja_de(TARDE) == franja_de(TARDE + timedelta(minutes=4))
