"""Guardar y leer alertas en TimescaleDB (paso 3.1).

Es la contraparte de `ingesta/almacen.py`, pero con un problema mucho más chico: los
ticks entran a cuarenta por segundo y necesitan escritura por lotes con cola y volcado
periódico; las alertas, si el proyecto hace bien su trabajo, son unas pocas por hora.
Por eso acá alcanza con un `INSERT` directo.

La tabla y el porqué de cada columna están en `sql/003_alertas.sql`.
"""

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.db import asegurar_pool
from app.modelos import Alerta

logger = logging.getLogger(__name__)

SQL_GUARDAR = """
    INSERT INTO alertas (momento, detector, simbolo, severidad, titulo, detalle, evidencia, clave)
    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
"""

SQL_ULTIMAS = """
    SELECT id, momento, detector, simbolo, severidad, titulo, detalle, evidencia, clave
    FROM alertas
    WHERE ($1::text IS NULL OR simbolo  = $1)
      AND ($2::text IS NULL OR detector = $2)
    ORDER BY momento DESC, id DESC
    LIMIT $3
"""

SQL_ULTIMA_POR_CLAVE = """
    SELECT clave, max(momento) AS ultima
    FROM alertas
    WHERE momento >= $1
    GROUP BY clave
"""


async def guardar(alertas: Sequence[Alerta]) -> int:
    """Escribe las alertas y devuelve cuántas guardó.

    Deja subir cualquier error de base: quien llama decide qué hacer. El motor las
    devuelve a la cola y reintenta, igual que hace el escritor de ticks.
    """
    if not alertas:
        return 0

    filas = [
        (
            alerta.momento,
            alerta.detector,
            alerta.simbolo,
            alerta.severidad,
            alerta.titulo,
            alerta.detalle,
            # asyncpg no convierte diccionarios a JSONB solo: va como texto y lo castea
            # la consulta. `ensure_ascii=False` para que un "σ" se guarde legible.
            json.dumps(alerta.evidencia, ensure_ascii=False),
            alerta.clave,
        )
        for alerta in alertas
    ]

    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        await conexion.executemany(SQL_GUARDAR, filas)

    return len(filas)


async def ultimas(
    limite: int = 50,
    simbolo: str | None = None,
    detector: str | None = None,
) -> list[Alerta]:
    """Las alertas más recientes primero. Es lo que va a leer el panel en el paso 3.6."""
    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(SQL_ULTIMAS, simbolo, detector, limite)

    return [
        Alerta(
            id=fila["id"],
            momento=fila["momento"],
            detector=fila["detector"],
            simbolo=fila["simbolo"],
            severidad=fila["severidad"],
            titulo=fila["titulo"],
            detalle=fila["detalle"],
            # asyncpg devuelve JSONB como texto si no se le registra un codec.
            evidencia=json.loads(fila["evidencia"]),
            clave=fila["clave"],
        )
        for fila in filas
    ]


async def ultima_por_clave(desde: datetime) -> dict[str, datetime]:
    """Cuándo se dijo por última vez cada cosa. Con esto se precarga el silencio.

    `desde` acota la consulta: no hace falta mirar el historial entero para saber si
    algo se dijo hace cinco minutos.
    """
    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(SQL_ULTIMA_POR_CLAVE, desde)

    return {fila["clave"]: fila["ultima"] for fila in filas}


def alerta_a_json(alerta: Alerta) -> dict[str, object]:
    """Pasa una alerta a un diccionario listo para responder por HTTP.

    La evidencia ya viene con los números como texto desde el detector, así que acá no
    hay nada que convertir: es la garantía de que el panel recibe exactamente los
    mismos dígitos con los que se tomó la decisión.
    """
    return {
        "id": alerta.id,
        "momento": alerta.momento.isoformat(),
        "detector": alerta.detector,
        "simbolo": alerta.simbolo,
        "severidad": alerta.severidad,
        "titulo": alerta.titulo,
        "detalle": alerta.detalle,
        "evidencia": alerta.evidencia,
        "clave": alerta.clave,
    }


VENTANA_PRECARGA = timedelta(hours=6)
"""Cuánto para atrás mira la precarga del silencio. Igual que `VENTANA_DE_OLVIDO`:
más allá de eso, ninguna clave sigue silenciada."""
