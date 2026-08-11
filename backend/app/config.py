"""Configuración de Argos: de dónde salen las credenciales y los ajustes.

Regla: NUNCA escribir contraseñas en el código. Todo sale de variables de entorno.

La única fuente de la verdad es `infra/.env`, el MISMO archivo que usa docker-compose
para crear la base de datos. Así la contraseña vive en un solo lugar: si la cambiás ahí,
cambia para todos.

Orden de prioridad (gana el primero que exista):
    1. Variables de entorno reales del sistema  ← útil cuando el backend corra en Docker
    2. El archivo infra/.env
    3. Los valores por defecto de esta clase
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ruta al .env de infra, calculada desde este archivo para que funcione sin importar
# desde qué carpeta arranques el backend.
#   config.py → app/ → backend/ → Argos_MVP/  → + infra/.env
RUTA_ENV_INFRA = Path(__file__).resolve().parents[2] / "infra" / ".env"


class Settings(BaseSettings):
    """Ajustes del backend. Pydantic valida los tipos y avisa si falta algo."""

    model_config = SettingsConfigDict(
        env_file=RUTA_ENV_INFRA,
        env_file_encoding="utf-8",
        # El .env de infra puede tener variables que al backend no le importan
        # (y en Docker habrá muchas más): las ignoramos en vez de reventar.
        extra="ignore",
    )

    # --- Base de datos (los nombres coinciden con los de infra/.env) ---
    postgres_user: str
    postgres_password: str
    postgres_db: str
    # Estas dos NO están en infra/.env: desde el host siempre es localhost:5432.
    # Cuando el backend viva dentro de Docker, se pasará POSTGRES_HOST=timescaledb.
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Ingesta de mercado ---
    # Si está en false, la API arranca sin conectarse a Binance. Sirve para trabajar en
    # endpoints sin abrir una conexión al exchange cada vez que uvicorn recarga por un
    # cambio de código. Se apaga poniendo INGESTA_ACTIVA=false en el entorno.
    ingesta_activa: bool = True

    # --- Pool de conexiones ---
    # Cuántas conexiones mantiene abiertas y reciclando (abrir una cuesta caro).
    db_pool_min: int = 2
    db_pool_max: int = 10
    # Segundos que espera al arrancar antes de rendirse (si Docker está apagado,
    # no queremos que el backend se quede colgado esperando eternamente).
    db_timeout_conexion: float = 5.0

    @property
    def dsn_visible(self) -> str:
        """La dirección de la BD con la contraseña TAPADA, para poder loguearla sin filtrarla."""
        return (
            f"postgresql://{self.postgres_user}:***"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def obtener_settings() -> Settings:
    """Devuelve los ajustes leyendo el .env una sola vez (el resultado queda cacheado)."""
    return Settings()  # type: ignore[call-arg]  # los valores los llena pydantic desde el entorno
