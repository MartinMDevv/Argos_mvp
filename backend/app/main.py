"""Punto de entrada de la API de Argos (FastAPI).

Signos vitales:
    GET /health           → ¿está viva la API?           (no toca la base de datos)
    GET /health/db        → ¿la API llega a la BD?       (hace una consulta real)

Mercado:
    GET /mercado/estado   → último precio de cada símbolo + salud de la ingesta   (paso 1.2)
    GET /mercado/velas    → velas OHLCV para dibujar el gráfico                   (paso 1.3)

Desde el paso 1.2, al arrancar la API se encienden además dos tareas de fondo que corren
para siempre: una escucha Binance y otra va guardando lo que llega en TimescaleDB.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import obtener_settings
from app.db import abrir_pool, cerrar_pool, revisar_conexion
from app.esquema import aplicar_esquema
from app.estado import EstadoMercado
from app.ingesta.almacen import EscritorDeTicks
from app.ingesta.binance import SIMBOLOS_MVP, escuchar_ticks
from app.modelos import Tick
from app.velas import LIMITE_MAXIMO, obtener_velas, vela_a_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado vivo del proceso. Se arma en el `lifespan` y lo leen los endpoints.
estado_mercado = EstadoMercado()
escritor_de_ticks = EscritorDeTicks()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida: qué pasa al encender y al apagar la app.

    Todo lo que está ANTES del `yield` corre al arrancar; lo de DESPUÉS, al parar.
    """
    settings = obtener_settings()

    # --- Arranque ---
    try:
        await abrir_pool()
        await aplicar_esquema()
    except Exception as error:
        # A propósito NO reventamos: si Docker está apagado queremos que la API igual
        # levante y lo diga en /health/db, en vez de negarse a arrancar. La ingesta
        # tampoco se detiene: los ticks esperan en memoria hasta que vuelva la base.
        logger.warning("Base de datos no disponible al arrancar: %s", error)

    tareas: list[asyncio.Task[None]] = []

    if settings.ingesta_activa:

        async def consumir(tick: Tick) -> None:
            """Qué hacemos con cada operación que llega del mercado.

            Dos destinos, a propósito separados: la memoria guarda el AHORA (para responder
            al instante) y la base guarda la HISTORIA (para tener con qué comparar).
            """
            estado_mercado.actualizar(tick)
            escritor_de_ticks.encolar(tick)

        tareas.append(asyncio.create_task(escuchar_ticks(consumir), name="ingesta-binance"))
        tareas.append(asyncio.create_task(escritor_de_ticks.correr(), name="escritor-ticks"))
    else:
        logger.info("Ingesta desactivada (INGESTA_ACTIVA=false)")

    yield

    # --- Apagado ---
    for tarea in tareas:
        tarea.cancel()
    await asyncio.gather(*tareas, return_exceptions=True)

    # Último volcado: lo que quedó en la cola se guarda antes de cerrar el pool.
    # Va después de cancelar las tareas para que nadie siga encolando mientras escribimos.
    if tareas:
        try:
            guardados = await escritor_de_ticks.volcar()
            if guardados:
                logger.info("Volcado final: %d ticks guardados antes de cerrar", guardados)
        except Exception as error:
            logger.warning("No se pudo hacer el volcado final: %s", error)

    await cerrar_pool()


app = FastAPI(title="Argos API", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Confirma que la API está viva y respondiendo."""
    return {"status": "ok", "service": "argos-backend"}


@app.get("/health/db")
async def health_db() -> JSONResponse:
    """Confirma que la API le llega de verdad a TimescaleDB.

    Devuelve 200 con las versiones si la conexión anda, o 503 con un mensaje claro
    (no un stacktrace) si la base de datos no está disponible.
    """
    try:
        versiones = await revisar_conexion()
    except Exception as error:
        logger.warning("Falló la revisión de la base de datos: %s", error)
        return JSONResponse(
            status_code=503,
            content={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "Encendé Docker (docker-on) y levantá infra: docker compose up -d --wait",
            },
        )

    return JSONResponse(
        content={
            "status": "ok",
            "base_de_datos": "timescaledb",
            "versiones": versiones,
        }
    )


@app.get("/mercado/estado")
def mercado_estado() -> dict[str, object]:
    """Foto del mercado ahora mismo, respondida desde memoria (no toca la base de datos).

    `simbolos` está vacío hasta que entre el primer tick: si todavía no sabemos el precio,
    lo decimos, no lo inventamos.

    `persistencia` es el pulso del escritor: `guardados` tiene que subir, `en_espera` tiene
    que mantenerse bajo. Si `en_espera` crece sin parar, la base de datos no está recibiendo.
    """
    return {
        "desde": estado_mercado.desde.isoformat(),
        "simbolos": estado_mercado.instantanea(),
        "persistencia": escritor_de_ticks.resumen(),
    }


@app.get("/mercado/velas")
async def mercado_velas(
    simbolo: str = Query(
        description=f"Par a consultar. El MVP vigila solo: {', '.join(SIMBOLOS_MVP)}.",
    ),
    intervalo: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Query(
        default="1m",
        description="Duración de cada vela.",
    ),
    limite: int = Query(
        default=200,
        ge=1,
        le=LIMITE_MAXIMO,
        description="Cuántas velas devolver, contando desde la más reciente hacia atrás.",
    ),
    desde: datetime | None = Query(
        default=None,
        description="Opcional: ignorar los ticks anteriores a este momento (ISO 8601).",
    ),
) -> JSONResponse:
    """Velas OHLCV armadas sobre los ticks guardados, en orden cronológico.

    **Ojo con la última vela**: viene con `completa: false` porque su tramo todavía no
    terminó. Sus valores van a seguir cambiando hasta que cierre el minuto (o la hora).

    **Ojo con la historia**: Argos solo tiene lo que vio desde que lo encendiste por primera
    vez. No hay velas de antes de eso, y no las inventamos. Traer historia vieja de Binance
    es un paso posterior.
    """
    # Lo validamos a mano contra la lista del MVP para poder responder con un mensaje útil
    # en vez de devolver una lista vacía que parezca "no hubo operaciones".
    if simbolo not in SIMBOLOS_MVP:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "simbolo_no_vigilado",
                "detalle": f"Argos todavía no vigila '{simbolo}'.",
                "disponibles": list(SIMBOLOS_MVP),
            },
        )

    try:
        velas = await obtener_velas(simbolo, intervalo, limite, desde)
    except Exception as error:
        logger.warning("No se pudieron armar las velas: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Probá GET /health/db",
            },
        ) from error

    return JSONResponse(
        content={
            "simbolo": simbolo,
            "intervalo": intervalo,
            "cantidad": len(velas),
            "velas": [vela_a_json(vela) for vela in velas],
        }
    )
