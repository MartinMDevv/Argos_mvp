"""El registro tiene que rechazar un detector mal definido AL ARRANCAR.

## Por qué esto importa más de lo que parece
Un detector roto no se nota. Si una alerta salta de más, molesta y la arreglás; si un
detector deja de emitir en silencio, todo se ve perfectamente normal — hasta el día que
esperabas el aviso y no llegó. Ese es el modo de falla peligroso de Argos, y contra eso
la defensa es que el error aparezca lo más temprano y lo más ruidoso posible: al
importar el archivo, no al evaluarlo.

Por eso estas pruebas verifican **que reviente**, y que el mensaje diga qué arreglar.
"""

from datetime import timedelta

import pytest

from app.detectores import registro
from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.modelos import Alerta
from app.velas import INTERVALOS

from .conftest import (
    DetectorConHistoria,
    DetectorQueNuncaEmite,
    DetectorQueSiempreEmite,
    hacer_contexto,
    hacer_tick,
)


def detector_de_mentira(**atributos) -> type[Detector]:
    """Arma una clase de detector con los atributos que se le pasen.

    Se hace así, y no con clases escritas a mano, porque cada prueba de acá necesita
    exactamente UNA cosa mal y todo lo demás bien.
    """
    base = {
        "nombre": "prueba_x",
        "titulo": "Prueba",
        "descripcion": "Detector de mentira.",
        "cadencia": Cadencia.POR_TICK,
        "evaluar": lambda self, contexto: None,
    }
    return type("DetectorDeMentira", (Detector,), base | atributos)


# -- Lo que tiene que aceptar --------------------------------------------------


def test_registra_un_detector_valido():
    registro.registrar(DetectorQueSiempreEmite)
    assert "prueba_siempre" in registro.catalogo()


def test_registrar_devuelve_la_clase_para_poder_usarlo_de_decorador():
    # `@registrar` solo funciona como decorador si devuelve lo que recibió.
    assert registro.registrar(DetectorQueSiempreEmite) is DetectorQueSiempreEmite


def test_registrar_dos_veces_la_misma_clase_no_molesta():
    # Puede pasar si un módulo se importa por dos caminos distintos.
    registro.registrar(DetectorQueSiempreEmite)
    registro.registrar(DetectorQueSiempreEmite)
    assert len(registro.catalogo()) >= 1


# -- Lo que tiene que rechazar -------------------------------------------------


@pytest.mark.parametrize("atributo", ["nombre", "titulo", "descripcion"])
def test_rechaza_un_detector_al_que_le_falta_un_atributo(atributo):
    with pytest.raises(ValueError, match=f"no define '{atributo}'"):
        registro.registrar(detector_de_mentira(**{atributo: ""}))


def test_rechaza_un_nombre_ya_usado():
    registro.registrar(DetectorQueSiempreEmite)

    with pytest.raises(ValueError, match="Ya hay un detector llamado"):
        registro.registrar(detector_de_mentira(nombre="prueba_siempre"))


def test_rechaza_una_cadencia_que_no_es_una_cadencia():
    with pytest.raises(ValueError, match="cadencia inválida"):
        registro.registrar(detector_de_mentira(cadencia="cuando_pueda"))


def test_rechaza_un_intervalo_que_no_existe():
    with pytest.raises(ValueError, match="que no existe"):
        registro.registrar(
            detector_de_mentira(cadencia=Cadencia.POR_VELA_CERRADA, intervalo="7m")
        )


def test_rechaza_un_detector_por_tick_que_pide_historia():
    """La combinación imposible: la ruta del tick no carga velas.

    Si esto pasara, el detector nunca podría opinar y se callaría para siempre —
    exactamente el modo de falla silencioso que queremos que sea imposible.
    """
    with pytest.raises(ValueError, match="La ruta del tick no carga historia"):
        registro.registrar(
            detector_de_mentira(cadencia=Cadencia.POR_TICK, velas_necesarias=20)
        )


def test_rechaza_un_silencio_negativo():
    with pytest.raises(ValueError, match="silencio negativo"):
        registro.registrar(detector_de_mentira(silencio=timedelta(seconds=-1)))


def test_un_rechazo_no_ensucia_el_catalogo():
    antes = registro.catalogo()

    with pytest.raises(ValueError):
        registro.registrar(detector_de_mentira(nombre=""))

    assert registro.catalogo() == antes


# -- Crear instancias ----------------------------------------------------------


def test_crear_sin_argumentos_instancia_todo_lo_registrado():
    registro.registrar(DetectorQueSiempreEmite)
    registro.registrar(DetectorConHistoria)

    nombres = {d.nombre for d in registro.crear()}

    assert {"prueba_siempre", "prueba_historia"} <= nombres


def test_crear_con_un_nombre_inventado_avisa():
    """Un nombre mal escrito tiene que gritar, no dejar a Argos vigilando de menos."""
    with pytest.raises(KeyError, match="No existen los detectores"):
        registro.crear(["umbral_de_precio_typo"])


# -- La red de seguridad para los detectores que todavía no existen -------------


def test_todos_los_detectores_de_verdad_cumplen_las_reglas():
    """Recorre lo que haya en `app/detectores/` y verifica los invariantes.

    Esta prueba no nombra ningún detector concreto a propósito: los de hoy son andamios
    que se borran en el 3.2, y los reales llegan en los pasos siguientes. Escrita así,
    cubre gratis a cada detector que se escriba de acá en adelante.
    """
    registro.descubrir()
    catalogo = registro.catalogo()

    assert catalogo, "no se descubrió ningún detector: ¿se rompió `descubrir()`?"

    for nombre, clase in catalogo.items():
        assert nombre == nombre.lower(), f"'{nombre}' debería ir en minúsculas"
        assert isinstance(clase.cadencia, Cadencia), f"'{nombre}' tiene mala cadencia"
        assert clase.velas_necesarias >= 0, f"'{nombre}' pide velas negativas"
        assert clase.silencio >= timedelta(0), f"'{nombre}' tiene silencio negativo"

        if clase.cadencia is Cadencia.POR_TICK:
            assert clase.velas_necesarias == 0, (
                f"'{nombre}' es POR_TICK y pide historia: nunca podría opinar"
            )
        else:
            assert clase.intervalo in INTERVALOS, f"'{nombre}' pide un intervalo inexistente"


def test_la_ficha_describe_al_detector_para_la_api():
    ficha = registro.ficha(DetectorConHistoria)

    assert ficha["nombre"] == "prueba_historia"
    assert ficha["cadencia"] == "por_vela_cerrada"
    assert ficha["intervalo"] == "1m"
    assert ficha["velas_necesarias"] == 3


def test_la_ficha_de_un_por_tick_no_miente_con_el_intervalo():
    """Un detector de tick no mira velas, así que su intervalo es `None`, no "1m"."""
    assert registro.ficha(DetectorQueSiempreEmite)["intervalo"] is None


# -- Que la clase base siga siendo abstracta -----------------------------------


def test_no_se_puede_instanciar_un_detector_sin_evaluar():
    class DetectorIncompleto(Detector):
        nombre = "incompleto"
        titulo = "Incompleto"
        descripcion = "No implementa evaluar()."
        cadencia = Cadencia.POR_TICK

    with pytest.raises(TypeError):
        DetectorIncompleto()  # type: ignore[abstract]


def test_evaluar_devuelve_alerta_o_none_y_nada_mas():
    """El contrato de `evaluar`, escrito como prueba."""
    contexto = hacer_contexto(tick=hacer_tick())

    assert isinstance(DetectorQueSiempreEmite().evaluar(contexto), Alerta)
    assert DetectorQueNuncaEmite().evaluar(contexto) is None
