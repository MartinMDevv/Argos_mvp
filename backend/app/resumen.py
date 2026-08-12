"""Resumen de mercado por símbolo: a cuánto está y cómo viene (paso 2.2).

Hasta acá Argos tenía las dos mitades separadas: `estado.py` sabe el precio de este
instante y `velas.py` sabe la historia. Un precio suelto no informa nada —"BTC vale
64.284" no le dice a nadie si eso es bueno, malo o normal—. Este módulo junta las dos:
toma el precio de ahora y lo compara contra el de hace 1 hora, 24 horas y 7 días.

Es lo que alimenta la watchlist y la cabecera del panel.

## El ancla: contra qué momento se mide "hace 24 horas"
Parece obvio (`now()`) y no lo es. Ya lo aprendimos en `velas.py`: si Argos estuvo
apagado dos días, un piso calculado desde "ahora" deja fuera todo lo que sí tenemos.

Acá aparece además el caso inverso, que es peor porque no se nota: Argos lleva treinta
segundos encendido después de dos días apagado. La memoria tiene un precio de *este
segundo* y la base llega hasta *hace dos días*. Si comparáramos el precio vivo contra
"el último cierre anterior a hace 24 horas según la base", estaríamos mostrando un
cambio de tres días con la etiqueta "24h". Nadie se daría cuenta.

Por eso el ancla es **el momento del dato más nuevo que tenemos**, mirando las tres
fuentes (ticks, historia y el tick vivo en memoria), y cada referencia trae una
**tolerancia**: si el cierre más cercano al blanco está más lejos que eso, el cambio se
devuelve `None`. No hay número aproximado ni cero de relleno — cuando no hay con qué
comparar, Argos lo dice.

## Cuántos datos se tocan (y por qué no son 500.000 ticks)
Veinticuatro horas de ticks de BTC son medio millón de filas. Agregarlas en cada
refresco del panel sería una tontería, porque esos mismos minutos ya están calculados y
guardados en `velas_historicas`: son las velas oficiales de Binance que trajo el
backfill, y para un minuto **cerrado** son mejor dato que el nuestro (están completas,
la nuestra puede estar mocha si Argos arrancó a mitad del minuto).

Así que los ticks se escanean **solo donde la historia oficial no llega**: desde el
último minuto que trajo el backfill hacia adelante. Con el backfill al día eso son
minutos, no un día entero. Es exactamente la misma regla de desempate que ya usa
`velas.py` —para minuto cerrado manda Binance, el minuto en curso siempre es nuestro—,
así que no cambia ningún resultado: solo cambia cuánto trabajo hace la base.

Corolario honesto: si el backfill nunca se corrió, los plazos largos no tienen con qué
compararse y salen en `None`. La respuesta trae `minutos_24h` (cuántos de los 1.440
minutos del día tienen datos) justamente para que eso se vea.

## Una consulta, no una por símbolo
Los símbolos entran como arreglo y salen todos en la misma consulta. Con dos da igual;
con veinte en la watchlist, la diferencia es entre una consulta y veinte.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.db import asegurar_pool
from app.modelos import Cambio, ResumenSimbolo, Tick
from app.velas import nombre_de_fuente

logger = logging.getLogger(__name__)

PLAZOS: dict[str, tuple[timedelta, timedelta]] = {
    "1h": (timedelta(hours=1), timedelta(minutes=5)),
    "24h": (timedelta(hours=24), timedelta(minutes=30)),
    "7d": (timedelta(days=7), timedelta(hours=3)),
}
"""Los plazos que se comparan: nombre → (cuánto atrás, cuánta tolerancia).

La **tolerancia** es cuánto se acepta que el dato encontrado se aleje del blanco. El
minuto exacto de hace 24 horas puede no existir (Argos estaba apagado, o ese minuto no
tuvo operaciones), así que se toma el último cierre anterior al blanco; si ese cierre
quedó más lejos que la tolerancia, ya no representa "hace 24 horas" y el cambio no se
informa.

Los números están calibrados a ojo sobre el mismo criterio: alrededor del 2% del plazo.
Un desfase de 5 minutos sobre 1 hora no cambia la lectura; uno de 3 horas sobre 1 hora,
sí.

⚠️ **Los plazos están también escritos a mano en `SQL_RESUMEN`** (los tres `LEFT JOIN
LATERAL`). Si se agrega o cambia uno acá, hay que tocar la consulta también. Es a
propósito: generar el SQL desde este diccionario haría la consulta ilegible para
ahorrar tres líneas."""

VENTANA_HISTORIA = timedelta(days=7, hours=4)
"""Cuánta historia se trae de `velas_historicas`: el plazo más largo (7 días) más su
tolerancia (3 h) más una hora de colchón. Son ~10.000 filas por símbolo, ya calculadas."""

VENTANA_TICKS = timedelta(hours=24, minutes=35)
"""Techo de cuánto se escanea de `ticks`, y solo si la historia oficial no cubre eso.
Alcanza para la ventana de 24 h y su tolerancia; los plazos más largos se apoyan en la
historia de Binance, que para minutos cerrados es la fuente correcta."""

SQL_RESUMEN = """
    WITH pedido AS (
        -- Los símbolos entran de a un arreglo, junto con el momento del tick que
        -- tenemos en memoria para cada uno (NULL si todavía no llegó ninguno).
        SELECT * FROM unnest($1::text[], $2::timestamptz[]) AS p(simbolo, momento_vivo)
    ),
    ancla AS (
        -- El punto de referencia temporal de todo el resumen: el dato MÁS NUEVO que
        -- tenemos del símbolo, mirando las tres fuentes. Nunca now(): ver el docstring.
        SELECT
            p.simbolo,
            -- Hasta dónde llegó el backfill. Marca la frontera a partir de la cual sí
            -- hace falta mirar los ticks (antes de eso ya está todo calculado).
            (SELECT max(inicio) FROM velas_historicas h WHERE h.simbolo = p.simbolo)
                AS tope_historia,
            greatest(
                COALESCE((SELECT max(inicio)  FROM velas_historicas h WHERE h.simbolo = p.simbolo),
                         '-infinity'::timestamptz),
                COALESCE((SELECT max(momento) FROM ticks            t WHERE t.simbolo = p.simbolo),
                         '-infinity'::timestamptz),
                COALESCE(p.momento_vivo, '-infinity'::timestamptz)
            ) AS momento
        FROM pedido p
    ),
    minutos_historia AS (
        -- Las velas oficiales de Binance. Ya vienen calculadas por minuto: traerlas
        -- es leer, no agregar.
        SELECT h.simbolo, h.inicio AS minuto, h.maximo, h.minimo, h.cierre,
               h.volumen, h.volumen_cotizado, true AS es_historia
        FROM velas_historicas h
        JOIN ancla a ON a.simbolo = h.simbolo
        WHERE h.inicio >= a.momento - $3::interval
          AND h.inicio <= a.momento
    ),
    minutos_propios AS (
        -- Nuestros ticks, agregados a minuto. El piso es lo MÁS NUEVO entre el tope de
        -- la historia y la ventana máxima: si el backfill está al día, esto escanea
        -- los últimos minutos y nada más.
        SELECT t.simbolo,
               time_bucket('1 minute'::interval, t.momento) AS minuto,
               max(t.precio)                  AS maximo,
               min(t.precio)                  AS minimo,
               -- Por `id_operacion` y no por `momento`: Binance repite milisegundo y
               -- el desempate por tiempo hace el cierre no determinista (ver velas.py).
               last(t.precio, t.id_operacion) AS cierre,
               sum(t.cantidad)                AS volumen,
               sum(t.precio * t.cantidad)     AS volumen_cotizado,
               false                          AS es_historia
        FROM ticks t
        JOIN ancla a ON a.simbolo = t.simbolo
        WHERE t.momento >= greatest(
                  a.momento - $4::interval,
                  COALESCE(a.tope_historia, '-infinity'::timestamptz)
              )
        GROUP BY t.simbolo, minuto
    ),
    minutos AS (
        -- Las dos fuentes en la misma mesa. Para un minuto cerrado manda Binance; los
        -- nuestros entran solo donde no hay vela oficial (ahí cae el minuto en curso,
        -- que el backfill nunca guarda porque todavía se está formando).
        SELECT * FROM minutos_historia
        UNION ALL
        SELECT p.* FROM minutos_propios p
        WHERE NOT EXISTS (
            SELECT 1 FROM velas_historicas h
            WHERE h.simbolo = p.simbolo AND h.inicio = p.minuto
        )
    ),
    ultimo AS (
        -- El cierre más reciente que hay en disco. Es el precio de respaldo para
        -- cuando la ingesta está apagada y la memoria está vacía.
        SELECT DISTINCT ON (simbolo) simbolo, minuto, cierre
        FROM minutos
        ORDER BY simbolo, minuto DESC
    ),
    dia AS (
        -- Techo, piso y volumen de las últimas 24 horas. `minutos_con_datos` va junto
        -- a propósito: sin él, un volumen armado con 300 de los 1.440 minutos del día
        -- se leería como el volumen del día.
        SELECT m.simbolo,
               max(m.maximo)            AS maximo,
               min(m.minimo)            AS minimo,
               sum(m.volumen)           AS volumen,
               sum(m.volumen_cotizado)  AS volumen_cotizado,
               count(*)::int            AS minutos_con_datos,
               bool_and(m.es_historia)  AS toda_historia,
               bool_or(m.es_historia)   AS algo_historia
        FROM minutos m
        JOIN ancla a ON a.simbolo = m.simbolo
        WHERE m.minuto > a.momento - interval '24 hours'
        GROUP BY m.simbolo
    )
    SELECT
        a.simbolo,
        a.momento                        AS ancla,
        u.minuto                         AS momento_ultimo,
        u.cierre                         AS precio_ultimo,
        d.maximo                         AS maximo_24h,
        d.minimo                         AS minimo_24h,
        d.volumen                        AS volumen_24h,
        d.volumen_cotizado               AS volumen_cotizado_24h,
        COALESCE(d.minutos_con_datos, 0) AS minutos_24h,
        d.toda_historia,
        d.algo_historia,
        r1.minuto  AS ref_1h_momento,  r1.cierre  AS ref_1h,
        r24.minuto AS ref_24h_momento, r24.cierre AS ref_24h,
        r7.minuto  AS ref_7d_momento,  r7.cierre  AS ref_7d
    FROM ancla a
    LEFT JOIN ultimo u ON u.simbolo = a.simbolo
    LEFT JOIN dia    d ON d.simbolo = a.simbolo
    -- Un LATERAL por plazo: "el último cierre anterior o igual al blanco". No se exige
    -- que caiga exacto —ese minuto puede no existir—, se exige que esté cerca, y de eso
    -- se encarga la tolerancia, ya en Python (ver PLAZOS).
    LEFT JOIN LATERAL (
        SELECT m.minuto, m.cierre FROM minutos m
        WHERE m.simbolo = a.simbolo AND m.minuto <= a.momento - interval '1 hour'
        ORDER BY m.minuto DESC LIMIT 1
    ) r1 ON true
    LEFT JOIN LATERAL (
        SELECT m.minuto, m.cierre FROM minutos m
        WHERE m.simbolo = a.simbolo AND m.minuto <= a.momento - interval '24 hours'
        ORDER BY m.minuto DESC LIMIT 1
    ) r24 ON true
    LEFT JOIN LATERAL (
        SELECT m.minuto, m.cierre FROM minutos m
        WHERE m.simbolo = a.simbolo AND m.minuto <= a.momento - interval '7 days'
        ORDER BY m.minuto DESC LIMIT 1
    ) r7 ON true
    -- Un símbolo del que no sabemos absolutamente nada no aparece en la respuesta.
    -- Es distinto de "vale cero": es "no tengo dato", y se nota por ausencia.
    WHERE a.momento > '-infinity'::timestamptz
    ORDER BY a.simbolo
"""


async def obtener_resumen(
    simbolos: Sequence[str],
    precios_vivos: Mapping[str, Tick] | None = None,
) -> dict[str, ResumenSimbolo]:
    """Arma el resumen de cada símbolo pedido.

    `precios_vivos` es el último tick en memoria de cada símbolo (`estado.py`). Es
    opcional: si no viene, o si falta un símbolo, el precio sale del último cierre
    guardado y el resumen lo declara en `origen_precio`.

    Los símbolos de los que no hay ningún dato quedan **fuera** del diccionario.
    """
    if not simbolos:
        return {}

    vivos = precios_vivos or {}
    momentos_vivos = [
        vivos[simbolo].momento if simbolo in vivos else None for simbolo in simbolos
    ]

    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(
            SQL_RESUMEN,
            list(simbolos),
            momentos_vivos,
            VENTANA_HISTORIA,
            VENTANA_TICKS,
        )

    resumenes: dict[str, ResumenSimbolo] = {}

    for fila in filas:
        simbolo = fila["simbolo"]
        precio, momento, origen = _elegir_precio(vivos.get(simbolo), fila)

        if precio is None or momento is None:
            # Hay ancla pero no hay precio: puede pasar si el único dato del símbolo
            # cae fuera de las ventanas escaneadas. No se inventa nada, se omite.
            continue

        resumenes[simbolo] = ResumenSimbolo(
            simbolo=simbolo,
            precio=precio,
            momento=momento,
            origen_precio=origen,
            cambios={
                plazo: _calcular_cambio(
                    plazo=plazo,
                    precio=precio,
                    ancla=fila["ancla"],
                    referencia=fila[f"ref_{plazo}"],
                    momento_referencia=fila[f"ref_{plazo}_momento"],
                )
                for plazo in PLAZOS
            },
            maximo_24h=fila["maximo_24h"],
            minimo_24h=fila["minimo_24h"],
            volumen_24h=fila["volumen_24h"],
            volumen_cotizado_24h=fila["volumen_cotizado_24h"],
            minutos_24h=fila["minutos_24h"],
            fuente_24h=(
                nombre_de_fuente(fila["toda_historia"], fila["algo_historia"])
                if fila["toda_historia"] is not None
                else None
            ),
        )

    return resumenes


def _elegir_precio(
    tick_vivo: Tick | None,
    fila: Mapping[str, object],
) -> tuple[Decimal | None, datetime | None, str]:
    """Decide qué precio muestra el resumen: el de memoria o el último guardado.

    Gana el más nuevo, y casi siempre es el vivo: el tick de memoria tiene segundos,
    mientras que el último cierre en disco tiene hasta un minuto (más los 2 segundos
    que el escritor tarda en volcar el lote).

    La comparación igual se hace, porque el caso raro existe: con la ingesta apagada
    (`INGESTA_ACTIVA=false`) la memoria queda vacía, y tras un backfill la base puede
    tener minutos más nuevos que el último tick que alcanzamos a escuchar.
    """
    precio_guardado = fila["precio_ultimo"]
    momento_guardado = fila["momento_ultimo"]

    if tick_vivo is not None and (
        momento_guardado is None or tick_vivo.momento >= momento_guardado
    ):
        return tick_vivo.precio, tick_vivo.momento, "vivo"

    if precio_guardado is None or momento_guardado is None:
        return None, None, "guardado"

    return precio_guardado, momento_guardado, "guardado"


def _calcular_cambio(
    plazo: str,
    precio: Decimal,
    ancla: datetime,
    referencia: Decimal | None,
    momento_referencia: datetime | None,
) -> Cambio | None:
    """Compara el precio actual contra el de hace `plazo`, o devuelve None si no se puede.

    Los tres motivos para no poder, todos igual de válidos y ninguno redondeado a cero:

    1. No hay ningún cierre anterior al blanco (Argos no tiene tanta historia).
    2. El cierre que hay quedó más lejos que la tolerancia: existe, pero ya no
       representa "hace 24 horas". Pasa cuando falta correr el backfill o hubo un
       apagón largo justo en ese tramo.
    3. La referencia es cero. No debería ocurrir con un precio real, pero dividir por
       cero revienta y una guarda vale más que la sorpresa.
    """
    if referencia is None or momento_referencia is None:
        return None

    atras, tolerancia = PLAZOS[plazo]
    blanco = ancla - atras

    if momento_referencia < blanco - tolerancia:
        return None

    if referencia == 0:
        return None

    return Cambio(
        plazo=plazo,
        porcentaje=(precio - referencia) / referencia * 100,
        referencia=referencia,
        momento_referencia=momento_referencia,
    )


def resumen_a_json(resumen: ResumenSimbolo) -> dict[str, object]:
    """Pasa un resumen a un diccionario listo para responder por HTTP.

    Los números van como TEXTO por lo mismo de siempre (ver `estado.py`): JSON no tiene
    decimales exactos y mandarlos como número los degradaría a float justo antes de
    llegar al panel.

    Los porcentajes se redondean a dos decimales acá y no antes: el cálculo se hace con
    toda la precisión y el recorte es cosa de la presentación.
    """
    return {
        "precio": str(resumen.precio),
        "momento": resumen.momento.isoformat(),
        "origen_precio": resumen.origen_precio,
        "cambios": {
            plazo: (
                None
                if cambio is None
                else {
                    "porcentaje": str(cambio.porcentaje.quantize(Decimal("0.01"))),
                    "referencia": str(cambio.referencia),
                    "momento": cambio.momento_referencia.isoformat(),
                }
            )
            for plazo, cambio in resumen.cambios.items()
        },
        "maximo_24h": _texto(resumen.maximo_24h),
        "minimo_24h": _texto(resumen.minimo_24h),
        "volumen_24h": _texto(resumen.volumen_24h),
        "volumen_cotizado_24h": _texto(resumen.volumen_cotizado_24h),
        "minutos_24h": resumen.minutos_24h,
        "fuente_24h": resumen.fuente_24h,
    }


def _texto(valor: Decimal | None) -> str | None:
    """Decimal a texto conservando el None: ausencia de dato no es un cero."""
    return None if valor is None else str(valor)
