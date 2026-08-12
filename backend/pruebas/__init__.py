"""Pruebas del backend de Argos.

Es un paquete (y no una carpeta suelta) para que los módulos de prueba puedan importar
las fábricas compartidas con `from .conftest import ...`.

Correr todo:      `uv run pytest`
Un solo archivo:  `uv run pytest pruebas/test_silencio.py`
Con detalle:      `uv run pytest -v`

Ninguna prueba necesita Docker ni internet. Ver el encabezado de `conftest.py`: eso no
es una comodidad, es la comprobación de que los detectores siguen siendo funciones puras
de su contexto — que es lo que va a permitir, más adelante, correrlos sobre la historia.
"""
