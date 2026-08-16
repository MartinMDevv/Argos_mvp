"""Piezas compartidas por las pruebas: fábricas de datos y aislamiento del registro.

## Por qué las pruebas no necesitan Docker
Ninguna prueba de esta carpeta abre una conexión, ni a la base ni a Binance. No es una
casualidad ni una limitación: es la comprobación del argumento de diseño del paso 3.1.
Un detector recibe todo lo que necesita en su `ContextoDeEvaluacion` y devuelve las
alertas que encontró, así que probarlo es armarle un contexto a mano y mirar qué sale.

Si algún día una prueba de detectores empieza a pedir la base, la pregunta no es cómo
levantarla en el CI: es qué se rompió en el diseño.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.detectores import registro
from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.modelos import Alerta, Tick, Vela

MOMENTO = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
"""Un instante fijo. Las pruebas nunca usan `datetime.now()`: un resultado que depende
del reloj es un resultado que algún día falla solo, a una hora rara, sin haber tocado
nada."""


@pytest.fixture(autouse=True)
def registro_aislado():
    """Devuelve el catálogo de detectores a como estaba al terminar cada prueba.

    El registro es global a propósito (es lo que hace que un `@registrar` en cualquier
    archivo alcance). Eso significa que una prueba que registre un detector de mentira
    lo dejaría ahí para las siguientes, y el orden de ejecución pasaría a importar.
    """
    original = registro.catalogo()
    yield
    registro._CATALOGO.clear()
    registro._CATALOGO.update(original)


# -- Fábricas de datos --------------------------------------------------------


def hacer_tick(
    precio: str = "64000",
    simbolo: str = "BTCUSDT",
    momento: datetime | None = None,
) -> Tick:
    """Una operación de mercado inventada, pero con la forma exacta de una real."""
    return Tick(
        simbolo=simbolo,
        precio=Decimal(precio),
        cantidad=Decimal("0.5"),
        momento=momento or MOMENTO,
        id_operacion=777,
        comprador_pasivo=False,
    )


def hacer_vela(
    cierre: str = "100",
    inicio: datetime | None = None,
    completa: bool = True,
) -> Vela:
    """Una vela con valores redondos, para que las cuentas se lean de un vistazo."""
    return Vela(
        inicio=inicio or MOMENTO,
        apertura=Decimal("100"),
        maximo=Decimal("110"),
        minimo=Decimal("90"),
        cierre=Decimal(cierre),
        volumen=Decimal("5"),
        volumen_cotizado=Decimal("500"),
        operaciones=42,
        fuente="propia",
        completa=completa,
    )


def hacer_contexto(
    tick: Tick | None = None,
    velas: tuple[Vela, ...] = (),
    simbolo: str = "BTCUSDT",
    intervalo: str = "1m",
) -> ContextoDeEvaluacion:
    """Lo que vería un detector en un momento dado."""
    return ContextoDeEvaluacion(
        simbolo=simbolo, momento=MOMENTO, tick=tick, velas=velas, intervalo=intervalo
    )


# -- Detectores de mentira ----------------------------------------------------
#
# Las pruebas de la maquinaria usan estos y NO los detectores de verdad. Ya pasó una
# vez: los andamios `humo.py` del 3.1 se borraron en el 3.2, y cualquier prueba que
# hubiera dependido de ellos se habría roto ese día por un motivo que no tiene nada que
# ver con lo que probaba. Un detector real se prueba en su propio archivo
# (`test_umbral_precio.py`); la maquinaria se prueba con estos.


class DetectorQueSiempreEmite(Detector):
    """Emite en cada evaluación. Sirve para ver el camino completo de una alerta."""

    nombre = "prueba_siempre"
    titulo = "Prueba · siempre"
    descripcion = "Detector de mentira que siempre encuentra algo."
    cadencia = Cadencia.POR_TICK
    silencio = timedelta(minutes=5)

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        return [
            self.alerta(
                contexto,
                severidad="info",
                detalle="Siempre encuentro algo.",
                evidencia={"precio": str(contexto.precio)},
            )
        ]


class DetectorQueNuncaEmite(Detector):
    """Nunca encuentra nada — que es la respuesta normal de un detector sano."""

    nombre = "prueba_nunca"
    titulo = "Prueba · nunca"
    descripcion = "Detector de mentira que no encuentra nada."
    cadencia = Cadencia.POR_TICK
    silencio = timedelta(0)

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        return []


class DetectorConHistoria(Detector):
    """Pide tres velas cerradas antes de opinar."""

    nombre = "prueba_historia"
    titulo = "Prueba · historia"
    descripcion = "Detector de mentira que necesita historia."
    cadencia = Cadencia.POR_VELA_CERRADA
    intervalo = "1m"
    velas_necesarias = 3
    silencio = timedelta(0)

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        vela = contexto.ultima_cerrada
        if vela is None:
            return []
        return [
            self.alerta(
                contexto,
                severidad="aviso",
                detalle=f"Cerró en {vela.cierre}.",
                evidencia={
                    "cierre": str(vela.cierre),
                    "velas_cerradas": str(len(contexto.velas_cerradas)),
                },
            )
        ]
