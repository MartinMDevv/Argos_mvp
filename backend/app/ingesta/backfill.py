"""Trae desde Binance la historia que Argos no vivió (paso 2.1b).

## El problema que resuelve
Argos solo tiene lo que vio con sus propios ojos. Antes de su primer arranque no hay nada, y
cada apagón deja un hueco. Eso se nota en dos lugares:

- **En el gráfico**: el eje de tiempo pega saltos y la vista no se parece a la de un gráfico
  de verdad, que es continuo.
- **En los detectores** (Fase 3), que es lo grave: una alerta de volatilidad por z-score
  compara el movimiento de ahora contra lo que es *normal*. Sin historia no hay normal, y sin
  normal no hay anomalía. Con un mes, "lo normal" es el humor del último mes.

## De dónde sale la historia
De `GET /api/v3/klines` de Binance: las velas oficiales del mismo exchange que ya escuchamos
en vivo. No hace falta API key. **No estamos inventando nada** — son exactamente los minutos
que nos perdimos, contados por quien los vio.

Es la misma fuente que usamos en el paso 1.3 para verificar que nuestras velas estaban bien
(salían idénticas al octavo decimal), así que ya sabemos que encajan con las nuestras.

## Solo el minuto
Se descarga únicamente el intervalo de 1 minuto. El resto (5m, 15m, 1h, 4h, 1d) se calcula
agregando, igual que con los ticks. Bajar seis intervalos sería seis veces más disco y seis
oportunidades de que queden desincronizados entre sí.

## Ir despacio a propósito
Misma lección que en el paso 1.1: a Binance no se le entra a lo bruto. Cada respuesta trae en
la cabecera `x-mbx-used-weight-1m` cuánto peso llevamos gastado en el minuto en curso; si se
acerca al techo, frenamos solos. Y si igual nos pasamos, Binance responde 429 (o 418 si ya se
enojó) con un `Retry-After` que respetamos al pie de la letra. Bajar un año tarda un par de
minutos; que te bloqueen la IP tarda mucho más.

## Lo que NO se guarda: el minuto en curso
Si el rango pedido llega hasta ahora, la última vela que manda Binance es la que se está
formando y sus números van a seguir cambiando. Guardarla sería congelar un dato a medio hacer
y, peor, dejar que le gane a nuestros ticks en vivo, que de ese minuto saben más. Se descarta.
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.db import asegurar_pool

logger = logging.getLogger(__name__)

URL_KLINES = "https://api.binance.com/api/v3/klines"

INTERVALO = "1m"
"""Único intervalo que se descarga. El resto se calcula agregando (ver `velas.py`)."""

MINUTO = timedelta(minutes=1)

VELAS_POR_PEDIDO = 1_000
"""Máximo que admite Binance por pedido. Son ~16,6 horas de velas de un minuto."""

PESO_MAXIMO = 4_000
"""Cuánto peso nos permitimos gastar por minuto. Binance corta en 6.000; el margen es a
propósito, para dejarle aire a la ingesta en vivo, que también consume."""

SEGUNDOS_ENFRIAR = 20.0
"""Cuánto paramos si nos acercamos al techo de peso."""

PAUSA_ENTRE_PEDIDOS = 0.12
"""Freno de mano entre pedidos. No hace falta para el límite, pero evita salir a mil por hora
contra un servicio ajeno que nos está dando datos gratis."""

REINTENTOS = 4

DIAS_POR_DEFECTO = 365


def _a_milisegundos(momento: datetime) -> int:
    return int(momento.timestamp() * 1000)


def _a_momento(milisegundos: int) -> datetime:
    return datetime.fromtimestamp(milisegundos / 1000, UTC)


async def _pedir(cliente: httpx.AsyncClient, parametros: dict[str, object]) -> list[list]:
    """Un pedido a Binance, con respeto por sus límites.

    Devuelve la lista cruda de klines. Cada kline es una lista donde nos interesan:
    `[0]` inicio (ms), `[1..4]` apertura/máximo/mínimo/cierre, `[5]` volumen base,
    `[6]` fin (ms), `[7]` volumen cotizado, `[8]` cantidad de operaciones.
    """
    for intento in range(1, REINTENTOS + 1):
        respuesta = await cliente.get(URL_KLINES, params=parametros)

        # 429 = te pasaste de la raya. 418 = te pasaste y ya te bloqueó un rato.
        if respuesta.status_code in (418, 429):
            espera = float(respuesta.headers.get("retry-after", 60))
            logger.warning(
                "Binance pide frenar (HTTP %d). Esperando %.0f s antes de reintentar (%d/%d).",
                respuesta.status_code,
                espera,
                intento,
                REINTENTOS,
            )
            await asyncio.sleep(espera)
            continue

        respuesta.raise_for_status()

        # Freno preventivo: si el peso gastado en este minuto se acerca al techo, paramos
        # antes de que Binance tenga que pedírnoslo.
        peso = int(respuesta.headers.get("x-mbx-used-weight-1m", 0))
        if peso >= PESO_MAXIMO:
            logger.info("Peso usado %d/6000 — enfriando %.0f s", peso, SEGUNDOS_ENFRIAR)
            await asyncio.sleep(SEGUNDOS_ENFRIAR)

        return respuesta.json()

    raise RuntimeError(f"Binance no respondió bien después de {REINTENTOS} intentos")


def _a_filas(simbolo: str, klines: list[list], corte: datetime) -> list[tuple]:
    """Pasa las klines crudas a filas listas para la base, tirando la vela en curso.

    `corte` es el instante a partir del cual una vela ya no se considera cerrada: cualquier
    kline cuyo fin caiga después no se guarda, porque todavía se está formando.
    """
    filas = []

    for k in klines:
        fin = _a_momento(int(k[6]))
        if fin >= corte:
            continue

        filas.append(
            (
                _a_momento(int(k[0])),  # inicio
                simbolo,
                Decimal(k[1]),  # apertura
                Decimal(k[2]),  # máximo
                Decimal(k[3]),  # mínimo
                Decimal(k[4]),  # cierre
                Decimal(k[5]),  # volumen (moneda base)
                Decimal(k[7]),  # volumen cotizado
                int(k[8]),  # operaciones (las REALES de Binance, no aggTrades)
            )
        )

    return filas


SQL_INSERTAR = """
    INSERT INTO velas_historicas (
        inicio, simbolo, apertura, maximo, minimo, cierre,
        volumen, volumen_cotizado, operaciones
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    -- Reejecutar la descarga no duplica nada: lo que ya estaba se descarta en silencio.
    ON CONFLICT DO NOTHING
"""

SQL_COBERTURA = """
    SELECT min(inicio) AS primera, max(inicio) AS ultima, count(*) AS cuantas
    FROM velas_historicas
    WHERE simbolo = $1
"""


async def _tramos_faltantes(
    conexion, simbolo: str, desde: datetime, hasta: datetime
) -> list[tuple[datetime, datetime]]:
    """Qué pedazos del rango pedido todavía no tenemos.

    La descarga es **incremental**: si ya bajaste un año y mañana vuelves a correrla, solo pide
    lo nuevo. Y si un día quieres más historia hacia atrás, pide solo lo que falta por delante
    del comienzo actual. Como Binance devuelve rangos continuos, alcanza con mirar los bordes:
    lo que hay en el medio está completo.
    """
    fila = await conexion.fetchrow(SQL_COBERTURA, simbolo)
    primera, ultima = fila["primera"], fila["ultima"]

    if primera is None:
        return [(desde, hasta)]

    tramos = []
    if desde < primera:
        tramos.append((desde, primera))
    if ultima + MINUTO < hasta:
        tramos.append((ultima + MINUTO, hasta))

    return tramos


async def rellenar_simbolo(
    simbolo: str,
    dias: int = DIAS_POR_DEFECTO,
    cliente: httpx.AsyncClient | None = None,
) -> int:
    """Baja la historia que falte de un símbolo. Devuelve cuántas velas nuevas se guardaron."""
    ahora = datetime.now(UTC)
    desde = ahora - timedelta(days=dias)

    pool = await asegurar_pool()
    propio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=30.0)

    guardadas = 0

    try:
        async with pool.acquire() as conexion:
            tramos = await _tramos_faltantes(conexion, simbolo, desde, ahora)

            if not tramos:
                logger.info("%s: la historia ya está completa, no hay nada que bajar", simbolo)
                return 0

            for inicio_tramo, fin_tramo in tramos:
                logger.info(
                    "%s: bajando de %s a %s",
                    simbolo,
                    inicio_tramo.date(),
                    fin_tramo.date(),
                )

                cursor = inicio_tramo
                pedidos = 0

                while cursor < fin_tramo:
                    klines = await _pedir(
                        cliente,
                        {
                            "symbol": simbolo,
                            "interval": INTERVALO,
                            "startTime": _a_milisegundos(cursor),
                            "endTime": _a_milisegundos(fin_tramo),
                            "limit": VELAS_POR_PEDIDO,
                        },
                    )

                    # Binance no tiene nada más para este rango: se terminó el tramo.
                    if not klines:
                        break

                    filas = _a_filas(simbolo, klines, corte=datetime.now(UTC))
                    if filas:
                        await conexion.executemany(SQL_INSERTAR, filas)
                        guardadas += len(filas)

                    pedidos += 1
                    if pedidos % 25 == 0:
                        logger.info(
                            "%s: %d velas guardadas (voy por %s)",
                            simbolo,
                            guardadas,
                            _a_momento(int(klines[-1][0])).date(),
                        )

                    # El próximo pedido arranca justo después de la última vela recibida.
                    siguiente = _a_momento(int(klines[-1][0])) + MINUTO
                    if siguiente <= cursor:
                        break  # guarda contra un bucle infinito si Binance repitiera datos
                    cursor = siguiente

                    await asyncio.sleep(PAUSA_ENTRE_PEDIDOS)

        logger.info("%s: listo, %d velas nuevas", simbolo, guardadas)
        return guardadas

    finally:
        if propio:
            await cliente.aclose()


async def rellenar(simbolos: list[str], dias: int = DIAS_POR_DEFECTO) -> dict[str, int]:
    """Baja la historia de varios símbolos, uno tras otro.

    A propósito **en serie y no en paralelo**: el límite de peso de Binance es por IP, así que
    bajar dos símbolos a la vez no va el doble de rápido, solo gasta el presupuesto el doble
    de rápido y nos acerca al freno.
    """
    resultado: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=30.0) as cliente:
        for simbolo in simbolos:
            resultado[simbolo] = await rellenar_simbolo(simbolo, dias=dias, cliente=cliente)

    return resultado


async def _principal() -> None:
    parser = argparse.ArgumentParser(
        description="Baja a la base la historia de velas de 1 minuto desde Binance."
    )
    parser.add_argument(
        "--simbolo",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT"],
        help="Símbolos a rellenar (por defecto BTCUSDT y ETHUSDT)",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=DIAS_POR_DEFECTO,
        help=f"Cuánta historia traer hacia atrás (por defecto {DIAS_POR_DEFECTO})",
    )
    argumentos = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # El esquema puede no estar aplicado si nunca se arrancó la API contra esta base.
    from app.esquema import aplicar_esquema

    await aplicar_esquema()

    resultado = await rellenar(argumentos.simbolo, dias=argumentos.dias)

    print()
    for simbolo, cuantas in resultado.items():
        print(f"  {simbolo}: {cuantas:,} velas nuevas")


if __name__ == "__main__":
    asyncio.run(_principal())
