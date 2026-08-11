"""Arma velas (OHLCV) a partir de los ticks guardados (paso 1.3).

## Quién hace el trabajo pesado: la base de datos
Podríamos traernos 50.000 ticks a Python y agruparlos acá. Sería lento y absurdo: mover todos
esos datos por la red para después tirar el 99%. La agrupación la hace TimescaleDB, que para
eso está, y nos devuelve solo las velas ya calculadas.

Las dos herramientas que usamos son propias de TimescaleDB y valen la pena:

- **`time_bucket(intervalo, momento)`** — es como un `GROUP BY` por tramos de tiempo. Agarra
  cada tick y lo tira al cajón que le toca ("los del minuto 10:03"). En Postgres pelado habría
  que hacer malabares con `date_trunc` y no sirve para tramos raros (5m, 4h).

- **`first(valor, orden)` y `last(valor, orden)`** — dan el primer y el último valor de un grupo
  *según otra columna*. Justo lo que necesita una vela: la apertura y el cierre del tramo. Con SQL
  estándar esto pide funciones de ventana o subconsultas; acá es una línea.

  **Ordenamos por `id_operacion` y no por `momento`, y esto no es un detalle.** Binance manda
  varias operaciones marcadas con el mismo milisegundo exacto (en las pruebas: 264 de 1.500 ticks
  de BTC compartían milisegundo). Ordenando por tiempo, el desempate entre esas queda librado al
  azar y el cierre de la vela cambiaba entre dos consultas de los mismos datos — pasaba en ~6% de
  las velas. El `id_operacion` del exchange es un contador que solo sube, así que refleja el orden
  real de los hechos y da siempre el mismo resultado. Es también el criterio que usa Binance para
  el cierre de sus propias velas, por eso ahora coinciden.

## Lo que este módulo NO hace: inventar velas
Si en un tramo no hubo ninguna operación, no hay vela. No se rellena con el precio anterior ni
se interpola: si no hay dato, no hay dato. (Timescale tiene `time_bucket_gapfill` para rellenar
huecos, pero eso es una decisión de presentación y hoy no hace falta: BTC y ETH operan sin parar.)

## Fase futura
Hoy la agregación se calcula **en cada consulta**. Es simple y siempre está al día. Cuando haya
mucha historia y se pidan rangos largos, el reemplazo natural son las *continuous aggregates* de
Timescale: velas pre-calculadas que se refrescan solas. Se hace cuando duela, no antes.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db import asegurar_pool
from app.modelos import Vela

logger = logging.getLogger(__name__)

# Tramos que Argos sabe armar. Es una lista cerrada a propósito: el usuario elige de acá,
# nunca escribe un intervalo libre que termine metido en la consulta.
INTERVALOS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

LIMITE_MAXIMO = 1_000
"""Techo de velas por consulta. Sin tope, un pedido distraído puede pedir años de historia."""

MARGEN_ASENTADO = timedelta(seconds=5)
"""Cuánto esperamos, después de que cierra un tramo, antes de declarar su vela terminada.

Hace falta por cómo escribimos: el `EscritorDeTicks` guarda de a lotes cada 2 segundos, así que
en el instante en que termina el minuto 10:03, los últimos ticks de ese minuto todavía pueden
estar en memoria esperando su turno para ir al disco. Si en ese momento marcáramos la vela como
completa, estaríamos firmando un volumen al que aún le falta un pedazo.

El margen es mayor que el intervalo de volcado a propósito, para cubrir también un volcado que
se haya demorado. Cuesta 5 segundos de latencia y compra que "completa" signifique de verdad
completa — que es lo único que hace útil a esa bandera."""

SQL_VELAS = """
    WITH agrupadas AS (
        SELECT
            time_bucket($1::interval, momento) AS inicio,
            -- Apertura y cierre se ordenan por `id_operacion`, NO por `momento`.
            -- Motivo (medido, no teórico): Binance manda varias operaciones con el mismo
            -- milisegundo exacto, y ordenando por tiempo el desempate queda al azar — el
            -- cierre salía distinto entre consultas. El id del exchange es un contador que
            -- solo sube, así que da el orden real en que ocurrieron y es determinista.
            first(precio, id_operacion)        AS apertura,
            max(precio)                        AS maximo,
            min(precio)                        AS minimo,
            last(precio, id_operacion)         AS cierre,
            sum(cantidad)                      AS volumen,
            sum(precio * cantidad)             AS volumen_cotizado,
            count(*)                           AS operaciones
        FROM ticks
        WHERE simbolo = $2
          -- Si no mandan "desde", este filtro se anula y se mira toda la historia.
          AND ($4::timestamptz IS NULL OR momento >= $4)
        GROUP BY inicio
        -- Ordenamos al revés para quedarnos con las MÁS RECIENTES…
        ORDER BY inicio DESC
        LIMIT $3
    )
    -- …y las devolvemos en orden cronológico, que es como las dibuja un gráfico.
    SELECT * FROM agrupadas ORDER BY inicio
"""


async def obtener_velas(
    simbolo: str,
    intervalo: str,
    limite: int = 200,
    desde: datetime | None = None,
) -> list[Vela]:
    """Devuelve las últimas `limite` velas del símbolo, de la más vieja a la más nueva.

    Lanza `ValueError` si el intervalo no está en `INTERVALOS`.
    """
    if intervalo not in INTERVALOS:
        raise ValueError(
            f"Intervalo '{intervalo}' no soportado. Opciones: {', '.join(INTERVALOS)}"
        )

    ancho = INTERVALOS[intervalo]
    limite = max(1, min(limite, LIMITE_MAXIMO))

    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(SQL_VELAS, ancho, simbolo, limite, desde)

    # Una vela está completa cuando su tramo terminó Y sus ticks ya aterrizaron en disco
    # (ver MARGEN_ASENTADO). La última siempre está a medio formar, y decirlo es parte de no
    # dar por firme lo que todavía se está moviendo.
    limite_completas = datetime.now(UTC) - MARGEN_ASENTADO

    return [
        Vela(
            inicio=fila["inicio"],
            apertura=fila["apertura"],
            maximo=fila["maximo"],
            minimo=fila["minimo"],
            cierre=fila["cierre"],
            volumen=fila["volumen"],
            volumen_cotizado=fila["volumen_cotizado"],
            operaciones=fila["operaciones"],
            completa=(fila["inicio"] + ancho) <= limite_completas,
        )
        for fila in filas
    ]


def vela_a_json(vela: Vela) -> dict[str, object]:
    """Pasa una vela a un diccionario listo para responder por HTTP.

    Los números van como TEXTO por la misma razón que en `estado.py`: JSON no tiene decimales
    exactos y mandarlos como número los degradaría a float justo antes de llegar al panel.
    """
    return {
        "inicio": vela.inicio.isoformat(),
        "apertura": str(vela.apertura),
        "maximo": str(vela.maximo),
        "minimo": str(vela.minimo),
        "cierre": str(vela.cierre),
        "volumen": str(vela.volumen),
        "volumen_cotizado": str(vela.volumen_cotizado),
        "operaciones": vela.operaciones,
        "variacion": str(vela.variacion.quantize(Decimal("0.01"))),
        "completa": vela.completa,
    }
