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
