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

## Dos fuentes en la misma serie (paso 2.1b)
Argos solo puede armar velas de los minutos que escuchó. Todo lo anterior a su primer arranque
—y cada apagón— sería un agujero. Por eso existe `velas_historicas`: las velas oficiales de
Binance, bajadas por `ingesta/backfill.py`, que son exactamente los minutos que nos perdimos.

La consulta pone las dos fuentes en la misma mesa **a resolución de un minuto** y recién después
arma el intervalo pedido. La regla de desempate es simple: **para un minuto cerrado manda la
vela oficial de Binance**, porque incluye todas las operaciones del minuto (la nuestra puede
estar mocha si Argos arrancó a mitad de camino); **el minuto en curso siempre es nuestro**,
porque el backfill nunca guarda una vela a medio formar y nuestros ticks son de hace segundos.

Cada vela devuelta dice de dónde salió en su campo `fuente` (`propia`, `historia` o `mixta`).
No se disimula la mezcla: los precios son igual de reales en ambos casos, pero `operaciones` no
se cuenta igual (ver `Vela.operaciones` en `modelos.py`).

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
    WITH limites AS (
        -- El dato más nuevo que tenemos del símbolo, mirando las DOS fuentes.
        -- Sirve para acotar el escaneo sin usar now(): si Argos estuvo apagado dos días,
        -- un piso calculado desde "ahora" dejaría fuera todo lo que sí tenemos.
        SELECT greatest(
            COALESCE((SELECT max(inicio)  FROM velas_historicas WHERE simbolo = $2),
                     '-infinity'::timestamptz),
            COALESCE((SELECT max(momento) FROM ticks            WHERE simbolo = $2),
                     '-infinity'::timestamptz)
        ) AS ultimo
    ),
    piso AS (
        -- Desde dónde miramos. Si no mandan "desde", se calcula uno: el ancho del intervalo
        -- por el doble de velas pedidas. Sin este piso, cada consulta escanearía el año
        -- entero de historia para devolver 200 velas.
        SELECT COALESCE(
            $4::timestamptz,
            (SELECT ultimo FROM limites) - $1::interval * ($3 * 2)
        ) AS desde
    ),
    minutos_propios AS (
        -- Los minutos que Argos vio con sus propios ojos, armados desde los ticks.
        SELECT
            time_bucket('1 minute'::interval, momento) AS minuto,
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
            count(*)::int                      AS operaciones,
            false                              AS es_historia
        FROM ticks
        WHERE simbolo = $2
          AND momento >= (SELECT desde FROM piso)
        GROUP BY minuto
    ),
    minutos AS (
        -- Las dos fuentes puestas en la misma mesa, a resolución de un minuto.
        -- Para un minuto CERRADO manda la vela oficial de Binance: incluye todas las
        -- operaciones del minuto, mientras que la nuestra solo tiene lo que alcanzamos a
        -- escuchar (si Argos arrancó a mitad del minuto, la nuestra está mocha).
        SELECT inicio AS minuto, apertura, maximo, minimo, cierre,
               volumen, volumen_cotizado, operaciones, true AS es_historia
        FROM velas_historicas
        WHERE simbolo = $2
          AND inicio >= (SELECT desde FROM piso)

        UNION ALL

        -- …y los nuestros solo donde no hay vela oficial. Ahí entra siempre el minuto en
        -- curso, que el backfill nunca guarda porque todavía se está formando.
        SELECT p.* FROM minutos_propios p
        WHERE NOT EXISTS (
            SELECT 1 FROM velas_historicas h
            WHERE h.simbolo = $2 AND h.inicio = p.minuto
        )
    ),
    agrupadas AS (
        -- Recién acá se arma el intervalo pedido. Agregar minutos da lo mismo que agregar
        -- los ticks directamente: la apertura es la del primer minuto, el cierre la del
        -- último, el máximo el mayor de los máximos y el volumen la suma.
        SELECT
            time_bucket($1::interval, minuto) AS inicio,
            first(apertura, minuto)           AS apertura,
            max(maximo)                       AS maximo,
            min(minimo)                       AS minimo,
            last(cierre, minuto)              AS cierre,
            sum(volumen)                      AS volumen,
            sum(volumen_cotizado)             AS volumen_cotizado,
            sum(operaciones)::int             AS operaciones,
            -- De qué está hecha la vela. No se oculta la mezcla: se informa.
            bool_and(es_historia)             AS toda_historia,
            bool_or(es_historia)              AS algo_historia
        FROM minutos
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
            fuente=nombre_de_fuente(fila["toda_historia"], fila["algo_historia"]),
            completa=(fila["inicio"] + ancho) <= limite_completas,
        )
        for fila in filas
    ]


def nombre_de_fuente(toda_historia: bool, algo_historia: bool) -> str:
    """Traduce las dos banderas de la consulta al nombre de la fuente.

    Ver `Vela.fuente` en `modelos.py` para qué significa cada una y por qué importa.
    Es pública porque `resumen.py` usa las mismas dos banderas sobre la misma mezcla de
    fuentes: si el nombre se decidiera dos veces, tarde o temprano se decidiría distinto.
    """
    if toda_historia:
        return "historia"
    if not algo_historia:
        return "propia"
    return "mixta"


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
        "fuente": vela.fuente,
        "variacion": str(vela.variacion.quantize(Decimal("0.01"))),
        "completa": vela.completa,
    }
