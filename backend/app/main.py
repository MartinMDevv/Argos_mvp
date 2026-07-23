"""Punto de entrada de la API de Argos (FastAPI).

Por ahora solo expone /health (los "signos vitales" del backend).
La lógica real —ingesta, detectores, IA— se irá agregando en fases siguientes.
"""

from fastapi import FastAPI

app = FastAPI(title="Argos API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Confirma que la API está viva y respondiendo."""
    return {"status": "ok", "service": "argos-backend"}
