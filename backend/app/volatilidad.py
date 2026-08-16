"""Cuánto se está agitando cada activo, en un número que se pueda mostrar (paso 3.7).

La alerta #3 ya sabe medir esto: compara el **rango verdadero** del último tramo contra la
mediana de las últimas 24 horas y avisa cuando la relación se dispara. Pero esa cuenta vive
dentro del detector y solo sale de ahí cuando hay algo que contar, que es casi nunca.

El panel necesita la otra mitad: el número de todos los días. La columna "Volatilidad" de la
tabla de Mercados mostraba `—` con la nota "llega en Fase 3" desde el paso 2.2b — y la Fase 3
ya llegó.

## La misma definición que usa el detector, para que no haya dos verdades
Se mide el **rango verdadero** de cada tramo de 5 minutos (el mayor entre el recorrido interno
y los dos saltos contra el cierre anterior, o sea el *True Range* de Wilder), en porcentaje del
precio, y se toma la mediana de las últimas 24 horas. Es exactamente lo que la #3 llama "lo
normal de este activo".

Si acá se usara una definición más cómoda —el rango simple, o la desviación de los retornos—,
el número del panel y el de la alerta dirían cosas distintas del mismo mercado, y quien mirara
las dos pantallas tendría razón en no creerle a ninguna.

## Por qué es una consulta aparte y no un campo más del resumen
`resumen.py` responde con una consulta ya afinada (ver el paso 2.2a). Meterle una ventana móvil
para el cierre anterior la volvería más lenta para todos los que solo quieren el precio. Acá se
paga solo cuando se pide.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.db import asegurar_pool

logger = logging.getLogger(__name__)

MINUTOS_POR_TRAMO = 5
"""Ancho del tramo. El mismo que mira la alerta #3."""

HORAS_DE_REFERENCIA = 24

SQL_VOLATILIDAD = f"""
    WITH tramos AS (
        SELECT time_bucket('{MINUTOS_POR_TRAMO} minutes', inicio) AS tramo,
               first(apertura, inicio)                            AS apertura,
               max(maximo)                                        AS maximo,
               min(minimo)                                        AS minimo,
               last(cierre, inicio)                               AS cierre
        FROM velas_historicas
        WHERE simbolo = $1
          AND inicio >= now() - interval '{HORAS_DE_REFERENCIA} hours'
        GROUP BY tramo
    ),
    con_previo AS (
        -- El rango verdadero necesita el cierre del tramo anterior: de ahí la ventana.
        SELECT apertura, maximo, minimo,
               lag(cierre) OVER (ORDER BY tramo) AS cierre_previo
        FROM tramos
    ),
    rangos AS (
        SELECT GREATEST(
                   maximo - minimo,
                   abs(maximo - COALESCE(cierre_previo, maximo)),
                   abs(minimo - COALESCE(cierre_previo, minimo))
               ) / NULLIF(apertura, 0) * 100 AS rango
        FROM con_previo
    )
    SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY rango) AS mediana,
           max(rango)                                        AS maximo,
           count(*)                                          AS tramos
    FROM rangos
    WHERE rango IS NOT NULL
"""


@dataclass(frozen=True, slots=True)
class Volatilidad:
    """Lo agitado que estuvo un activo en las últimas 24 horas."""

    tipico: Decimal
    """Rango verdadero mediano de un tramo de 5 minutos, en % del precio."""

    maximo: Decimal
    """El tramo más movido de las 24 h. Sirve para saber si el día tuvo un susto."""

    tramos: int
    """Cuántos tramos se pudieron medir. Con pocos, el número dice poco."""


TRAMOS_MINIMOS = 60
"""Cinco horas de datos. Con menos, la mediana describe un rato y no un día, y se prefiere
no responder — el mismo criterio que usa el detector para no opinar sin referencia."""


async def obtener_volatilidad(simbolos: list[str]) -> dict[str, Volatilidad]:
    """La volatilidad típica de cada símbolo. Los que no alcanzan el mínimo **no aparecen**.

    Ausencia no es cero: si un símbolo falta, el panel muestra "—" y no un `0,00%` que se
    leería como "no se movió nada".
    """
    pool = await asegurar_pool()
    salida: dict[str, Volatilidad] = {}

    async with pool.acquire() as conexion:
        for simbolo in simbolos:
            fila = await conexion.fetchrow(SQL_VOLATILIDAD, simbolo)
            if fila is None or fila["mediana"] is None or fila["tramos"] < TRAMOS_MINIMOS:
                continue

            salida[simbolo] = Volatilidad(
                tipico=fila["mediana"],
                maximo=fila["maximo"],
                tramos=fila["tramos"],
            )

    return salida


def volatilidad_a_json(volatilidad: Volatilidad) -> dict[str, object]:
    """Recorta a dos decimales para mostrar; el porcentaje no se lee más fino que eso."""
    return {
        "tipico_pct": str(volatilidad.tipico.quantize(Decimal("0.01"))),
        "maximo_pct": str(volatilidad.maximo.quantize(Decimal("0.01"))),
        "tramos": volatilidad.tramos,
        "minutos_por_tramo": MINUTOS_POR_TRAMO,
    }
