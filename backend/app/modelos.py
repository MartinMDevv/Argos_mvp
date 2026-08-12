"""Modelos de dominio de Argos: las "cosas" con las que trabaja el sistema.

Este archivo NO sabe de Binance, ni de Postgres, ni de FastAPI. Es a propósito:
mañana podemos sumar otro exchange y el resto de Argos (detectores, velas, panel)
no se entera, porque todos hablan el mismo idioma definido acá.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Tick:
    """Una operación real ocurrida en el mercado: alguien compró algo, a un precio, en un instante.

    Es la unidad mínima de información de Argos. Todo lo demás —velas, volatilidad,
    volumen anómalo, alertas— se calcula a partir de estos.

    ¿Por qué `Decimal` y no `float` para precio y cantidad?
    Porque `float` es binario y no puede representar exacto un decimal: `0.1 + 0.2` da
    `0.30000000000000004`. Con dinero eso es veneno, y en Argos los números tienen que ser
    exactos (regla de oro: no inventamos ni deformamos cifras). Binance manda precios como
    TEXTO justamente por eso, y nosotros los pasamos a Decimal sin tocar el float.

    `frozen=True` = inmutable: un tick es un hecho histórico, no se edita.
    `slots=True`  = más liviano en memoria; van a ser millones.
    """

    simbolo: str
    """Par negociado, en mayúsculas. Ej: "BTCUSDT"."""

    precio: Decimal
    """Precio al que se ejecutó la operación."""

    cantidad: Decimal
    """Cuánto se operó, en la moneda base. Ej: 0.0041 (BTC)."""

    momento: datetime
    """Cuándo ocurrió la operación EN EL EXCHANGE (no cuándo nos llegó), en UTC."""

    id_operacion: int
    """Identificador del exchange. Sirve para no guardar dos veces el mismo tick."""

    comprador_pasivo: bool
    """True si el comprador estaba esperando en el libro de órdenes.

    Traducido: si el comprador era el pasivo, entonces quien empujó la operación fue el
    VENDEDOR (presión vendedora). Si es False, fue el comprador el que salió a barrer el
    libro (presión compradora). Este dato es la base del "quién manda" que vamos a usar
    más adelante en los detectores de volumen.
    """

    @property
    def volumen_cotizado(self) -> Decimal:
        """Cuánto dinero movió la operación (precio × cantidad). Ej: 487.93 USDT.

        Es lo que de verdad importa para medir si un movimiento es grande: 100 unidades
        de una moneda barata no es lo mismo que 100 de una cara.
        """
        return self.precio * self.cantidad

    @property
    def lado_agresor(self) -> str:
        """Quién tomó la iniciativa en esta operación: "compra" o "venta"."""
        return "venta" if self.comprador_pasivo else "compra"


@dataclass(frozen=True, slots=True)
class Vela:
    """El resumen de todo lo que pasó en un tramo de tiempo. La barrita del gráfico.

    Un tick suelto no dice nada: en un minuto de BTC hay cientos y son ruido puro. La vela
    comprime ese minuto en cinco números que sí cuentan una historia:

        apertura → a cuánto empezó el tramo
        máximo   → lo más alto que llegó
        mínimo   → lo más bajo que tocó
        cierre   → a cuánto terminó
        volumen  → cuánto se movió

    Es también la unidad con la que van a trabajar los detectores: "el precio se movió 3% en
    5 minutos" se responde mirando velas, no ticks.
    """

    inicio: datetime
    """Comienzo del tramo, en UTC. Una vela de 1m que empieza 10:03:00 cubre hasta 10:03:59."""

    apertura: Decimal
    maximo: Decimal
    minimo: Decimal
    cierre: Decimal

    volumen: Decimal
    """Cuánto se operó en la moneda base. Ej: 12.4 BTC."""

    volumen_cotizado: Decimal
    """Cuánto dinero cambió de manos. Ej: 794.000 USDT. Para comparar entre activos, este."""

    operaciones: int
    """Cuántas operaciones hubo en el tramo. Muchas operaciones chicas y pocas grandes son
    situaciones distintas aunque el volumen sea el mismo.

    ⚠️ **Cuidado al comparar entre velas de distinta `fuente`.** En las velas que armamos
    nosotros esto cuenta `aggTrade` (operaciones agrupadas por Binance); en las históricas
    cuenta las operaciones reales. Las históricas siempre dan un número mayor. Los dos son
    correctos, pero miden cosas distintas: no los restes ni los promedies entre sí.
    """

    fuente: str
    """De dónde salieron estos números: `propia`, `historia` o `mixta`.

    - `propia`   → lo armamos con los ticks que Argos vio con sus propios ojos.
    - `historia` → vela oficial de Binance, traída por el backfill (los minutos que nos perdimos).
    - `mixta`    → el tramo abarca minutos de las dos clases (pasa en el borde entre ambas).

    Existe porque Argos no debe hacer pasar una cosa por otra. Los precios son igual de reales
    en los dos casos, pero `operaciones` no se cuenta igual, y quien lea estos datos —un
    detector, el panel, la IA— tiene derecho a saber con qué está tratando.
    """

    completa: bool
    """False si el tramo TODAVÍA no terminó (es la vela que se está formando ahora mismo).

    Importa: la última vela siempre está a medio hacer, y mostrarla como cerrada haría creer
    que el mínimo del minuto ya está definido cuando puede caer más en los próximos segundos.
    Preferimos decir que está incompleta antes que dar por firme algo que no lo está.
    """

    @property
    def variacion(self) -> Decimal:
        """Cuánto se movió el precio dentro del tramo, en porcentaje (cierre contra apertura)."""
        if self.apertura == 0:
            return Decimal(0)
        return (self.cierre - self.apertura) / self.apertura * 100


@dataclass(frozen=True, slots=True)
class Cambio:
    """Cuánto se movió el precio respecto de un momento anterior. El "+1,84%" del panel.

    Es una comparación entre dos precios reales y concretos, no una tendencia ni una
    estimación. Por eso viaja con el precio contra el que se comparó y con el momento
    exacto de ese precio: quien lo lea puede rehacer la cuenta y verificarla.

    Cuando no hay con qué comparar —falta historia de ese plazo— **no existe un `Cambio`**:
    el plazo vale `None`. Un cero sería mentira (diría "no se movió") y un aproximado
    también (diría "se movió esto" con más confianza de la que tenemos).
    """

    plazo: str
    """Nombre del plazo comparado: `1h`, `24h` o `7d`."""

    porcentaje: Decimal
    """Variación porcentual entre `referencia` y el precio actual. Positivo = subió."""

    referencia: Decimal
    """El precio de entonces: el cierre del minuto usado como punto de partida."""

    momento_referencia: datetime
    """Cuándo cerró ese minuto, en UTC. Casi nunca cae exacto en el plazo pedido (el
    minuto de hace 24 horas puede no tener operaciones), pero siempre cae dentro de la
    tolerancia; si no, no habría `Cambio`."""


@dataclass(frozen=True, slots=True)
class ResumenSimbolo:
    """La ficha de un activo: a cuánto está y cómo viene. Lo que alimenta la watchlist.

    Junta las dos mitades de Argos que hasta ahora estaban separadas: el precio del
    instante (memoria) y la historia con la que ese precio cobra sentido (TimescaleDB).
    Un precio solo no dice nada; "64.284 y viene +1,8% en el día" ya es información.
    """

    simbolo: str

    precio: Decimal
    """El precio de referencia del resumen: contra este se calcularon los cambios."""

    momento: datetime
    """Cuándo es ese precio, en UTC. **Mirarlo siempre**: si Argos lleva rato apagado,
    el precio es viejo y decirlo es la diferencia entre informar y engañar."""

    origen_precio: str
    """`vivo` si salió del último tick en memoria (segundos de antigüedad), `guardado`
    si salió del último cierre de minuto en la base (la ingesta está apagada o caída)."""

    cambios: dict[str, "Cambio | None"]
    """Variación por plazo (`1h`, `24h`, `7d`). `None` = no había con qué comparar."""

    maximo_24h: Decimal | None
    minimo_24h: Decimal | None
    """Techo y piso del día. `None` si no hay ni un minuto de datos en la ventana."""

    volumen_24h: Decimal | None
    """Cuánto se operó en 24h, en la moneda base (ej. BTC)."""

    volumen_cotizado_24h: Decimal | None
    """Cuánto dinero movió en 24h (ej. USDT). Este es el comparable entre activos."""

    minutos_24h: int
    """Cuántos de los 1.440 minutos del día tienen datos. Es el **medidor de confianza**
    del bloque de 24h: con 1.440 el volumen es el real; con 300, es el de 300 minutos y
    nada más. Se informa en vez de disimularse."""

    fuente_24h: str | None
    """De qué está hecha la ventana de 24h: `propia`, `historia` o `mixta`.
    Mismo significado que en `Vela.fuente`, y la misma advertencia."""
