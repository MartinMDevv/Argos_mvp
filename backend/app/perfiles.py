"""El perfil intradía de volumen: cuánto se opera *a esta hora* normalmente (paso 3.5).

## El problema que resuelve
El volumen de cripto tiene horario. Medido sobre los 369 días de la base, la franja más
activa (14:00 UTC, cuando abre Estados Unidos) mueve **2,8 veces** lo de la más floja
(21:00 UTC), todos los días, sin que pase nada especial.

Entonces, si el volumen de las 14:05 se compara contra "la mediana de las últimas 24 h",
lo que se detecta no es una anomalía: es el amanecer de Nueva York. Se comprobó — con esa
referencia, una cuarta parte de las alertas caía en tres horas del día, el doble de lo que
tocaría si estuvieran repartidas.

## Cómo lo resuelve el resto del mundo
Con **RVOL** (*relative volume*), que es lo que mira cualquier operador: el volumen de
ahora dividido por el volumen **típico de esta misma franja horaria** en los días
anteriores. Un RVOL de 1 quiere decir "un martes cualquiera a esta hora"; uno de 5, que
se está operando cinco veces lo que se acostumbra **a esta hora**, que ya es otra cosa.

Este módulo arma justamente esa tabla: las 288 franjas de cinco minutos que tiene un día,
cada una con la mediana de lo que se operó en ella durante los últimos días.

## Por qué vive fuera de `detectores/`
Porque sale a la base, y un detector no puede hacerlo (ver `detectores/base.py`): tiene
que ser una función pura de su contexto para poder rebobinarse sobre el pasado. El
camino previsto para esto es que **el motor** cargue el dato y lo agregue al contexto,
que es exactamente lo que pasa acá — `main.py` conecta este perfil al motor y el motor lo
reparte en `contexto.extras`.

## Se recalcula solo, cada tanto
El perfil cambia despacio: es el hábito del mercado, no su estado. Se refresca cada hora
en una tarea de fondo, igual que los umbrales de la #1, y por el mismo motivo: si la base
está caída al arrancar, un cálculo único dejaría a la alerta #4 sin poder opinar el resto
de la sesión, y eso no se nota desde afuera.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from app.db import asegurar_pool

logger = logging.getLogger(__name__)

MINUTOS_POR_FRANJA = 5
"""Ancho de cada franja del día. Coincide con el tramo que mira la alerta #4."""

FRANJAS_POR_DIA = 24 * 60 // MINUTOS_POR_FRANJA  # 288

DIAS_DE_PERFIL = 14
"""Cuántos días hacia atrás definen "lo normal a esta hora".

Dos semanas es el rango habitual para el RVOL y acá también es un compromiso: con menos,
un par de días movidos deforman el perfil; con mucho más, se mezclan regímenes de mercado
distintos y "lo normal" deja de parecerse a estos días. Da 14 muestras por franja, que
alcanzan para una mediana honesta sin pedir una historia enorme."""

SEGUNDOS_ENTRE_REFRESCOS = 3600.0
"""Cada cuánto se recalcula. El hábito del mercado no cambia en minutos."""

MUESTRAS_MINIMAS = 5
"""Menos de esto en una franja y se prefiere no tener perfil para ella.

Una "mediana" de dos días no describe una costumbre. Sin perfil, la alerta #4 simplemente
no opina de esa franja — que es mejor que opinar con un número inventado."""

SQL_PERFIL = f"""
    WITH tramos AS (
        SELECT time_bucket('{MINUTOS_POR_FRANJA} minutes', inicio) AS tramo,
               sum(volumen_cotizado)                               AS volumen
        FROM velas_historicas
        WHERE simbolo = $1
          AND inicio >= now() - ($2::int * interval '1 day')
        GROUP BY tramo
    )
    SELECT (EXTRACT(HOUR FROM tramo)::int * 60 + EXTRACT(MINUTE FROM tramo)::int)
               / {MINUTOS_POR_FRANJA}                                  AS franja,
           -- percentile_disc y no percentile_cont: devuelve un valor REAL de la muestra
           -- y mantiene el tipo numeric, así el número no pasa por un float por el camino.
           percentile_disc(0.5) WITHIN GROUP (ORDER BY volumen)         AS mediana,
           count(*)                                                     AS muestras
    FROM tramos
    GROUP BY franja
    ORDER BY franja
"""


def franja_de(momento: datetime) -> int:
    """A qué franja del día pertenece un instante. De 0 a 287, en UTC."""
    return (momento.hour * 60 + momento.minute) // MINUTOS_POR_FRANJA


class PerfilesDeVolumen:
    """El volumen típico de cada franja, por símbolo. Vive en memoria."""

    def __init__(self) -> None:
        self._por_simbolo: dict[str, dict[int, Decimal]] = {}
        self._calculado: datetime | None = None

    def reemplazar(self, simbolo: str, perfil: dict[int, Decimal]) -> None:
        self._por_simbolo[simbolo] = perfil

    def de(self, simbolo: str) -> dict[int, Decimal]:
        """El perfil de un símbolo, o vacío si todavía no se calculó."""
        return self._por_simbolo.get(simbolo, {})

    def marcar_calculado(self, momento: datetime) -> None:
        self._calculado = momento

    def resumen(self) -> dict[str, object]:
        """Para mirarlo desde la API y saber si la alerta #4 tiene con qué trabajar."""
        return {
            "perfiles": {
                simbolo: len(perfil) for simbolo, perfil in sorted(self._por_simbolo.items())
            },
            "franjas_por_dia": FRANJAS_POR_DIA,
            "dias": DIAS_DE_PERFIL,
            "calculado": self._calculado.isoformat() if self._calculado else None,
        }


CATALOGO = PerfilesDeVolumen()
"""El perfil compartido del proceso. Igual que con los umbrales: uno solo, para que la
consulta se haga una vez y no una por detector."""


async def calcular(simbolo: str, dias: int = DIAS_DE_PERFIL) -> dict[int, Decimal]:
    """Arma el perfil de un símbolo consultando la base. Devuelve franja → volumen típico."""
    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(SQL_PERFIL, simbolo, dias)

    return {
        fila["franja"]: fila["mediana"]
        for fila in filas
        if fila["muestras"] >= MUESTRAS_MINIMAS and fila["mediana"] > 0
    }


async def recargar(simbolos: list[str], catalogo: PerfilesDeVolumen | None = None) -> int:
    """Recalcula el perfil de todos los símbolos. Devuelve cuántas franjas quedaron."""
    destino = catalogo if catalogo is not None else CATALOGO
    total = 0

    for simbolo in simbolos:
        perfil = await calcular(simbolo)
        destino.reemplazar(simbolo, perfil)
        total += len(perfil)

    from datetime import UTC

    destino.marcar_calculado(datetime.now(UTC))
    return total


async def mantener_al_dia(
    simbolos: list[str], catalogo: PerfilesDeVolumen | None = None
) -> None:
    """Tarea de fondo: recalcula el perfil cada hora. No termina nunca.

    El primer intento es inmediato para que la alerta #4 pueda opinar cuanto antes; si
    falla —la base tarda en levantar más veces de las que uno querría— se vuelve a
    intentar en el siguiente ciclo en vez de quedarse sin perfil para siempre.
    """
    while True:
        try:
            franjas = await recargar(simbolos, catalogo)
            logger.info("Perfil de volumen al día: %d franjas en total", franjas)
        except Exception as error:
            logger.warning("No se pudo calcular el perfil de volumen: %s", error)

        await asyncio.sleep(SEGUNDOS_ENTRE_REFRESCOS)
