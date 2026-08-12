"""La clase base de los detectores y lo que un detector puede mirar (paso 3.1).

## Qué es un detector
Una pregunta que Argos le hace al mercado una y otra vez. "¿BTC cruzó los 70.000?".
"¿Este volumen es raro comparado con lo normal?". La respuesta es una `Alerta` o
nada — y **nada es la respuesta más frecuente y más deseable**.

## La decisión de fondo: un detector es una función pura
`evaluar()` no es `async` y no toca la base de datos. Recibe todo lo que necesita ya
cargado en el `ContextoDeEvaluacion` y devuelve una alerta o `None`. No es un descuido:

- **Se puede probar.** Le armás un contexto a mano y sabés qué tiene que salir. Un
  detector que se conecta a la base solo se prueba con la base encendida.
- **Se puede repetir sobre el pasado.** La v2.0 del norte pide *backtesting de las
  propias alertas*: correr los detectores sobre la historia para medir cuáles sirven.
  Un detector que sale a buscar datos por su cuenta mira el "ahora" y no se puede
  rebobinar. Uno que solo lee su contexto se corre sobre cualquier momento de 2025.
- **No se multiplican las consultas.** Cuatro detectores por dos símbolos que
  consultaran por su cuenta serían ocho viajes a la base por vela. El motor trae los
  datos una vez y los reparte.

Si algún día un detector necesita algo que hoy no está en el contexto (datos on-chain,
por ejemplo), lo correcto es que el **motor** lo cargue y lo agregue al contexto — no
que el detector salga a buscarlo.

## Las dos cadencias
Los detectores no corren todos al mismo ritmo, y esto viene del spec: hay una capa
rápida (detección cruda, en tiempo real) y una lenta (estadística sobre historia).

- **`por_tick`** — reacciona al precio vivo, sin consultar nada. Un umbral de precio
  tiene que saltar cuando cruza, no un minuto después. Corre en la ruta caliente de la
  ingesta, así que tiene prohibido hacer trabajo pesado.
- **`por_vela_cerrada`** — se evalúa una vez por vela terminada. Un z-score sobre 1.440
  minutos de historia no cambia de respuesta cuarenta veces por segundo: recalcularlo
  a cada tick sería quemar CPU para llegar al mismo número.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from app.modelos import Alerta, Tick, Vela

SEVERIDADES = ("info", "aviso", "fuerte")
"""Cuánto pide tu atención una alerta. Lista cerrada para que dos detectores no
inventen dos escalas distintas y el panel no sepa cuál pintar más fuerte."""


class Cadencia(StrEnum):
    """Cada cuánto se le pregunta a un detector. Ver "Las dos cadencias" arriba."""

    POR_TICK = "por_tick"
    POR_VELA_CERRADA = "por_vela_cerrada"


@dataclass(frozen=True, slots=True)
class ContextoDeEvaluacion:
    """Todo lo que un detector puede mirar para decidir. Se lo arma el motor.

    Es deliberadamente una foto cerrada: lo que no está acá, el detector no lo tiene.
    Esa restricción es lo que hace que un detector sea repetible sobre el pasado.
    """

    simbolo: str

    momento: datetime
    """Cuándo se está evaluando, en UTC. Los detectores usan **esto** y no
    `datetime.now()`: si algún día se los corre sobre la historia, `now()` los sacaría
    del momento que se está reproduciendo."""

    tick: Tick | None = None
    """El último precio vivo, si lo hay. `None` con la ingesta apagada o antes del
    primer tick — y ahí el detector se calla, no supone."""

    velas: tuple[Vela, ...] = ()
    """Historia reciente en orden cronológico (la más vieja primero).

    **La última puede estar a medio formar** (`completa=False`). Casi siempre querés
    `velas_cerradas`: sacar conclusiones de una vela que todavía se está armando es
    opinar sobre un minuto que no terminó."""

    intervalo: str = "1m"
    """De qué tramo son esas velas. El que pidió el detector en `Detector.intervalo`."""

    extras: dict[str, object] = field(default_factory=dict)
    """Puerta para datos que hoy no existen (on-chain, social, otro exchange). Vacío en
    el MVP; está para que sumar una fuente sea agregar una clave acá y no rediseñar
    la firma de `evaluar()` en todos los detectores a la vez."""

    @property
    def velas_cerradas(self) -> tuple[Vela, ...]:
        """Solo los tramos que ya terminaron. Sobre estos se hace estadística."""
        return tuple(vela for vela in self.velas if vela.completa)

    @property
    def ultima_cerrada(self) -> Vela | None:
        """La vela terminada más reciente, o `None` si todavía no hay ninguna."""
        cerradas = self.velas_cerradas
        return cerradas[-1] if cerradas else None

    @property
    def precio(self) -> Decimal | None:
        """El precio más confiable que hay a mano, o `None` si no hay ninguno.

        Prefiere el tick vivo (segundos de antigüedad) y si no hay cae al último cierre
        guardado. Mirá `origen_precio` para saber cuál de los dos tocó: no es lo mismo
        decidir con un precio de hace dos segundos que con uno de hace dos días.
        """
        if self.tick is not None:
            return self.tick.precio
        ultima = self.ultima_cerrada
        return ultima.cierre if ultima is not None else None

    @property
    def origen_precio(self) -> str | None:
        """`vivo`, `guardado` o `None`. Mismos nombres que en `ResumenSimbolo`."""
        if self.tick is not None:
            return "vivo"
        return "guardado" if self.ultima_cerrada is not None else None


class Detector(ABC):
    """La clase de la que hereda cada alerta enchufable.

    Para escribir uno nuevo: heredá de acá, completá los atributos de clase, poné el
    decorador `@registrar` encima y guardá el archivo en esta carpeta. Eso es todo —
    el motor lo encuentra solo. No hay ningún lugar donde haya que "darlo de alta".
    """

    nombre: ClassVar[str]
    """Identificador corto y estable, en minúsculas. Ej: `umbral_precio`.

    Se guarda en cada alerta y va a quedar escrito en la base: cambiarlo más adelante
    parte la historia en dos. Elegilo pensando en eso."""

    titulo: ClassVar[str]
    """El encabezado que ve una persona. Ej: "Volumen anómalo"."""

    descripcion: ClassVar[str]
    """Una línea explicando qué busca. Sale en `GET /detectores`."""

    cadencia: ClassVar[Cadencia]
    """`POR_TICK` o `POR_VELA_CERRADA`. Ver "Las dos cadencias" arriba."""

    intervalo: ClassVar[str] = "1m"
    """Qué tramo de vela quiere mirar. Solo aplica a `POR_VELA_CERRADA`."""

    velas_necesarias: ClassVar[int] = 0
    """Cuánta historia necesita para poder opinar.

    **Si no la hay, el detector no se evalúa.** Un z-score con cuatro muestras no es un
    z-score, es un número con cara de z-score, y publicarlo sería inventar precisión.
    Preferimos no decir nada."""

    silencio: ClassVar[timedelta] = timedelta(minutes=15)
    """Cuánto se calla después de emitir, para la misma `clave`.

    Es el antirruido, y cada detector elige el suyo porque no todos duran igual: un
    umbral de precio cruzado es un instante, una anomalía de volumen se estira varios
    minutos. Lo aplica el motor, no el detector (ver `silencio.py`)."""

    @abstractmethod
    def evaluar(self, contexto: ContextoDeEvaluacion) -> Alerta | None:
        """Mira el contexto y devuelve una alerta, o `None` si no hay nada que contar.

        `None` es la respuesta normal. Un detector que casi siempre encuentra algo no
        está detectando: está describiendo.

        No hagas E/S acá dentro (ni base de datos, ni red): ver el encabezado del
        módulo. Y usá `contexto.momento`, nunca `datetime.now()`.
        """

    def puede_opinar(self, contexto: ContextoDeEvaluacion) -> bool:
        """¿Hay material suficiente para que este detector diga algo?

        El motor lo consulta antes de llamar a `evaluar()`. Sobreescribilo si tu
        detector necesita algo más que un mínimo de velas.
        """
        return len(contexto.velas_cerradas) >= self.velas_necesarias

    def alerta(
        self,
        contexto: ContextoDeEvaluacion,
        *,
        severidad: str,
        detalle: str,
        evidencia: dict[str, str],
        variante: str = "",
    ) -> Alerta:
        """Arma la alerta rellenando lo que es igual para todos los detectores.

        Existe para que nadie se olvide del `momento` ni arme la `clave` a su manera:
        si cada detector la construyera por su cuenta, el silencio dejaría de agrupar
        bien y volverían los mensajes repetidos.

        `variante` afina la clave cuando un mismo detector vigila varias situaciones a
        la vez sobre el mismo símbolo. Ejemplo: el umbral de precio puede tener
        configurados 70.000 y 60.000 para BTC, y que salte uno no debe silenciar al
        otro — ahí `variante` sería `"70000:arriba"`.
        """
        if severidad not in SEVERIDADES:
            raise ValueError(
                f"Severidad '{severidad}' desconocida en el detector '{self.nombre}'. "
                f"Opciones: {', '.join(SEVERIDADES)}"
            )

        clave = f"{self.nombre}:{contexto.simbolo}"
        if variante:
            clave = f"{clave}:{variante}"

        return Alerta(
            detector=self.nombre,
            simbolo=contexto.simbolo,
            momento=contexto.momento,
            severidad=severidad,
            titulo=self.titulo,
            detalle=detalle,
            evidencia=evidencia,
            clave=clave,
        )
