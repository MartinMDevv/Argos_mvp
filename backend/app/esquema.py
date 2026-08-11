"""Aplica el esquema de la base de datos (las tablas) al arrancar.

## Por qué así y no con una herramienta de migraciones
Todos los `.sql` de `backend/sql/` están escritos para poder correrse muchas veces sin
romper nada (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`…). Siendo así,
la forma más simple y honesta es aplicarlos enteros en cada arranque: si ya estaban, no
pasa nada; si la base es nueva, quedan creados.

**Cuándo esto va a dejar de alcanzar:** el día que necesitemos *cambiar* algo ya creado
(renombrar una columna, cambiar un tipo, migrar datos existentes). Ahí sí hace falta llevar
registro de qué migración se aplicó y cuál no, y toca traer algo como Alembic o una tabla
`migraciones`. Hoy, con una sola tabla que solo se crea, sería ceremonia sin beneficio.
"""

import logging
from pathlib import Path

from app.db import asegurar_pool

logger = logging.getLogger(__name__)

# backend/app/esquema.py → app/ → backend/ → + sql/
CARPETA_SQL = Path(__file__).resolve().parent.parent / "sql"


async def aplicar_esquema() -> list[str]:
    """Corre todos los .sql en orden alfabético. Devuelve los nombres aplicados.

    El orden importa (por eso los archivos van numerados: 001_, 002_…): una tabla que
    referencia a otra tiene que crearse después.
    """
    archivos = sorted(CARPETA_SQL.glob("*.sql"))

    if not archivos:
        logger.warning("No hay archivos .sql en %s", CARPETA_SQL)
        return []

    pool = await asegurar_pool()
    aplicados: list[str] = []

    async with pool.acquire() as conexion:
        for archivo in archivos:
            # Sin parámetros, asyncpg manda el archivo tal cual y Postgres acepta
            # varias sentencias separadas por ';' en una sola ida y vuelta.
            await conexion.execute(archivo.read_text(encoding="utf-8"))
            aplicados.append(archivo.name)

    logger.info("Esquema aplicado: %s", ", ".join(aplicados))
    return aplicados
