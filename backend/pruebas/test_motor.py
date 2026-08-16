"""El aviso en vivo del motor: a quién le cuenta una alerta, y cuándo (paso 4.2).

`revisar_tick` es una función normal que no toca la base, así que el motor se puede probar
igual que un detector: se le da un tick y se mira qué hizo. Eso no es casualidad — es la
misma decisión del paso 3.1 que permite rebobinar los detectores sobre el pasado.
"""

from datetime import timedelta

from app.detectores.motor import MotorDeDetectores
from app.estado import EstadoMercado
from app.modelos import Alerta

from .conftest import DetectorQueNuncaEmite, DetectorQueSiempreEmite, hacer_tick

SIMBOLOS = ("BTCUSDT",)


def armar(detector, al_emitir=None) -> MotorDeDetectores:
    return MotorDeDetectores(
        estado=EstadoMercado(),
        detectores=[detector],
        simbolos=SIMBOLOS,
        al_emitir=al_emitir,
    )


def test_avisa_en_el_momento_en_que_la_alerta_pasa_el_antirruido():
    avisadas: list[Alerta] = []
    motor = armar(DetectorQueSiempreEmite(), al_emitir=avisadas.append)

    motor.revisar_tick(hacer_tick())

    assert len(avisadas) == 1
    assert avisadas[0].detector == "prueba_siempre"


def test_lo_que_el_detector_no_emite_no_se_avisa():
    avisadas: list[Alerta] = []
    motor = armar(DetectorQueNuncaEmite(), al_emitir=avisadas.append)

    motor.revisar_tick(hacer_tick())

    assert avisadas == []


def test_una_alerta_silenciada_no_vuelve_a_avisar():
    """El aviso cuelga del antirruido, no de la evaluación: si no se emite, no se notifica.

    Es lo que evita que el panel reciba cien carteles del mismo hecho mientras el detector
    lo sigue viendo tick tras tick.
    """
    avisadas: list[Alerta] = []
    detector = DetectorQueSiempreEmite()
    detector.silencio = timedelta(minutes=5)
    motor = armar(detector, al_emitir=avisadas.append)

    for _ in range(5):
        motor.revisar_tick(hacer_tick())

    assert len(avisadas) == 1
    assert motor.emitidas == 1
    assert motor.resumen()["silenciadas"] == 4


def test_si_el_que_escucha_revienta_la_alerta_igual_se_guarda():
    """Perder una detección por un fallo al notificar sería el peor intercambio posible."""

    def oyente_roto(alerta: Alerta) -> None:
        raise RuntimeError("el panel explotó")

    motor = armar(DetectorQueSiempreEmite(), al_emitir=oyente_roto)

    motor.revisar_tick(hacer_tick())

    assert motor.emitidas == 1  # quedó encolada para escribirse igual
    assert motor.resumen()["en_espera"] == 1


def test_sin_nadie_escuchando_el_motor_funciona_igual():
    """`al_emitir` es opcional: el motor no depende de que haya un panel abierto."""
    motor = armar(DetectorQueSiempreEmite())

    motor.revisar_tick(hacer_tick())

    assert motor.emitidas == 1
