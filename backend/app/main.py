"""Punto de entrada de la API de Argos (FastAPI).

Hoy expone dos "signos vitales":
    GET /health      → ¿está viva la API?           (no toca la base de datos)
    GET /health/db   → ¿la API llega a la BD?       (hace una consulta real)

Están separados a propósito: si la base de datos se cae, Argos sigue respondiendo
"estoy vivo pero sin BD" en vez de morirse entero.

La lógica real —ingesta, detectores, IA— se irá agregando en fases siguientes.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.db import abrir_pool, cerrar_pool, revisar_conexion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida: qué pasa al encender y al apagar la app.

    Todo lo que está ANTES del `yield` corre al arrancar; lo de DESPUÉS, al parar.
    """
    # --- Arranque ---
    try:
        await abrir_pool()
    except Exception as error:
        # A propósito NO reventamos: si Docker está apagado queremos que la API igual
        # levante y lo diga en /health/db, en vez de negarse a arrancar.
        logger.warning("No se pudo conectar a la base de datos al arrancar: %s", error)

    yield

    # --- Apagado ---
    await cerrar_pool()


app = FastAPI(title="Argos API", version="0.1.0", lifespan=lifespan)


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
