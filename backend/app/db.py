"""Conexión a TimescaleDB con asyncpg.

¿Por qué un POOL y no una conexión suelta? Abrir una conexión a Postgres es caro
(handshake, autenticación, memoria en el servidor). El pool abre unas pocas al arrancar
y las va prestando y recuperando. En la Fase 1, cuando entren miles de ticks por minuto,
esto es la diferencia entre volar y arrastrarse.

El pool es un recurso global del proceso: se abre al arrancar la app y se cierra al parar
(ver el `lifespan` en main.py).
"""

import logging

import asyncpg

from app.config import obtener_settings

logger = logging.getLogger(__name__)

# El pool vivo del proceso. Es None mientras no se haya abierto (o si la BD no estaba).
_pool: asyncpg.Pool | None = None


class SinConexionBD(RuntimeError):
    """No hay conexión con la base de datos (apagada, inalcanzable o credenciales malas)."""


async def abrir_pool() -> asyncpg.Pool:
    """Crea el pool de conexiones. Se llama una sola vez, al arrancar la app."""
    global _pool

    if _pool is not None:
        return _pool

    settings = obtener_settings()

    # Pasamos los datos por separado en vez de armar una URL: así una contraseña con
    # caracteres raros (@, /, #) no rompe nada, porque no hay que escaparla.
    _pool = await asyncpg.create_pool(
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
        host=settings.postgres_host,
        port=settings.postgres_port,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        timeout=settings.db_timeout_conexion,
        command_timeout=settings.db_timeout_conexion,
    )
    logger.info("Pool de BD abierto → %s", settings.dsn_visible)
    return _pool


async def cerrar_pool() -> None:
    """Cierra el pool y devuelve las conexiones. Se llama al apagar la app."""
    global _pool

    if _pool is None:
        return

    await _pool.close()
    _pool = None
    logger.info("Pool de BD cerrado")


def obtener_pool() -> asyncpg.Pool:
    """Devuelve el pool ya abierto, sin intentar abrirlo.

    Lanza SinConexionBD si no hay pool. Es la versión estricta, para el código caliente
    (la ingesta de ticks) que no debe pagar el costo de reintentar en cada llamada.
    """
    if _pool is None:
        raise SinConexionBD(
            "No hay conexión a la base de datos. ¿Está encendido Docker "
            "y levantado el contenedor argos_timescaledb?"
        )
    return _pool


async def asegurar_pool() -> asyncpg.Pool:
    """Devuelve el pool y, si todavía no existe, intenta abrirlo (reconexión perezosa).

    ¿Por qué hace falta? El pool se abre al arrancar la app, pero si en ese momento la BD
    estaba apagada, el pool quedó en None para siempre. Como Docker acá se enciende a mano,
    es normal levantar el backend antes que la base. Con esto, en cuanto la BD aparece el
    siguiente pedido se reconecta solo, sin reiniciar el backend.
    """
    if _pool is not None:
        return _pool

    try:
        return await abrir_pool()
    except Exception as error:
        raise SinConexionBD(
            f"No se pudo conectar a la base de datos ({error}). ¿Está encendido Docker "
            "y levantado el contenedor argos_timescaledb?"
        ) from error


async def revisar_conexion() -> dict[str, str | None]:
    """Le hace una pregunta real a la base de datos para probar que el cable funciona.

    Devuelve la versión de Postgres y la de la extensión TimescaleDB. Si TimescaleDB
    no estuviera instalada en esta BD, devuelve None en su campo (no inventamos datos).
    """
    pool = await asegurar_pool()

    async with pool.acquire() as conexion:
        # El clásico "¿me escuchas?": si esto vuelve con un 1, la conexión sirve.
        await conexion.fetchval("SELECT 1")

        version_postgres = await conexion.fetchval("SHOW server_version")
        version_timescale = await conexion.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
        )

    return {
        "postgres": version_postgres,
        "timescaledb": version_timescale,
    }
