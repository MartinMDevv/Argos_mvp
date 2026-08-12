"""Los umbrales configurados: en memoria para leerlos, en la base para conservarlos (paso 3.2).

## Por qué hay una copia en memoria
El detector de umbrales corre en la ruta caliente, con cada operación que entra —unas
cuarenta por segundo. Preguntarle a la base "¿qué umbrales hay?" cuarenta veces por
segundo para leer tres filas que casi nunca cambian sería absurdo, y encima metería E/S
donde el diseño dice que no puede haber (ver `base.py`).

Es el mismo reparto de siempre en Argos: **memoria para el ahora, disco para conservar**.
La diferencia con `estado.py` es la dirección — ahí la memoria se llena del mercado, acá
se llena de la base.

## Cómo se mantienen sincronizadas
Por dos caminos, a propósito redundantes:

1. **Al crear o borrar por la API**, se escribe en la base y se actualiza la memoria en
   el mismo paso. Así el cambio se nota en el tick siguiente, no en el minuto siguiente.
2. **Una tarea de fondo recarga desde la base cada minuto.** Cubre lo que el camino 1 no
   puede: que la base estuviera caída al arrancar (y la memoria arrancara vacía, con
   Argos "vigilando" nada sin decirlo), o que alguien toque la tabla por fuera.

El segundo camino es el importante. Un umbral que no se cargó no falla: simplemente no
avisa nunca, y no avisar no se nota hasta el día que esperabas el aviso.
"""

import asyncio
import logging
from collections.abc import Iterable, Sequence
from decimal import Decimal

from app.db import asegurar_pool
from app.modelos import DIRECCIONES, Umbral

logger = logging.getLogger(__name__)

SEGUNDOS_ENTRE_RECARGAS = 60.0
"""Cada cuánto se relee la tabla. Es la red de seguridad, no el camino principal: los
cambios hechos por la API ya se aplican al instante."""

SQL_LISTAR = """
    SELECT id, simbolo, valor, direccion, nota, creado
    FROM umbrales
    ORDER BY simbolo, valor
"""

SQL_CREAR = """
    INSERT INTO umbrales (simbolo, valor, direccion, nota)
    VALUES ($1, $2, $3, $4)
    RETURNING id, simbolo, valor, direccion, nota, creado
"""

SQL_BORRAR = "DELETE FROM umbrales WHERE id = $1 RETURNING id"


class Umbrales:
    """Los umbrales vigentes, agrupados por símbolo para que el detector los busque rápido."""

    def __init__(self) -> None:
        self._por_simbolo: dict[str, tuple[Umbral, ...]] = {}
        self.cargado_alguna_vez = False
        """False mientras nunca se haya podido leer la tabla. Sirve para distinguir
        "no hay umbrales configurados" de "no pudimos enterarnos de si los hay" — que
        se ven igual desde afuera y no son lo mismo en absoluto."""

    def reemplazar(self, umbrales: Iterable[Umbral]) -> None:
        """Deja en memoria exactamente lo que diga la base. Es un reemplazo, no una fusión:
        si un umbral se borró en la tabla, tiene que desaparecer de acá."""
        agrupados: dict[str, list[Umbral]] = {}
        for umbral in umbrales:
            agrupados.setdefault(umbral.simbolo, []).append(umbral)

        self._por_simbolo = {
            simbolo: tuple(lista) for simbolo, lista in agrupados.items()
        }
        self.cargado_alguna_vez = True

    def de(self, simbolo: str) -> tuple[Umbral, ...]:
        """Los umbrales de un símbolo. Tupla vacía si no hay ninguno."""
        return self._por_simbolo.get(simbolo, ())

    def todos(self) -> list[Umbral]:
        """Todos, ordenados por símbolo y valor."""
        return sorted(
            (u for lista in self._por_simbolo.values() for u in lista),
            key=lambda u: (u.simbolo, u.valor),
        )

    def agregar(self, umbral: Umbral) -> None:
        """Suma uno recién creado, sin esperar a la próxima recarga."""
        actuales = self._por_simbolo.get(umbral.simbolo, ())
        self._por_simbolo[umbral.simbolo] = (*actuales, umbral)

    def quitar(self, id_umbral: int) -> bool:
        """Saca uno por id. Devuelve si lo encontró."""
        for simbolo, lista in self._por_simbolo.items():
            quedan = tuple(u for u in lista if u.id != id_umbral)
            if len(quedan) != len(lista):
                self._por_simbolo[simbolo] = quedan
                return True
        return False

    def resumen(self) -> dict[str, object]:
        """Pulso, para exponerlo junto al del motor."""
        return {
            "configurados": sum(len(lista) for lista in self._por_simbolo.values()),
            "cargado_alguna_vez": self.cargado_alguna_vez,
        }


CATALOGO = Umbrales()
"""El catálogo compartido: lo llena la tarea de recarga, lo actualizan los endpoints y
lo lee el detector. Es un único objeto para todo el proceso, igual que `EstadoMercado`."""


# -- Base de datos -------------------------------------------------------------


def _fila_a_umbral(fila) -> Umbral:
    return Umbral(
        id=fila["id"],
        simbolo=fila["simbolo"],
        valor=fila["valor"],
        direccion=fila["direccion"],
        nota=fila["nota"],
        creado=fila["creado"],
    )


async def listar() -> list[Umbral]:
    """Lee la tabla entera. Son pocas filas: no hace falta paginar."""
    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        filas = await conexion.fetch(SQL_LISTAR)

    return [_fila_a_umbral(fila) for fila in filas]


async def crear(
    simbolo: str,
    valor: Decimal,
    direccion: str,
    nota: str | None = None,
    catalogo: Umbrales | None = None,
) -> Umbral:
    """Guarda un umbral nuevo y lo deja disponible para el tick siguiente.

    Valida acá además del `CHECK` de la tabla: el error de la base es correcto pero
    ilegible, y quien se equivoca escribiendo un umbral merece que se le diga qué
    opciones hay.
    """
    if direccion not in DIRECCIONES:
        raise ValueError(
            f"Dirección '{direccion}' desconocida. Opciones: {', '.join(DIRECCIONES)}"
        )
    if valor <= 0:
        raise ValueError("El umbral tiene que ser un precio positivo.")

    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        fila = await conexion.fetchrow(SQL_CREAR, simbolo, valor, direccion, nota)

    umbral = _fila_a_umbral(fila)
    (catalogo or CATALOGO).agregar(umbral)
    logger.info("Umbral nuevo: %s %s %s", umbral.simbolo, umbral.direccion, umbral.valor)
    return umbral


async def borrar(id_umbral: int, catalogo: Umbrales | None = None) -> bool:
    """Borra un umbral. Devuelve si existía."""
    pool = await asegurar_pool()
    async with pool.acquire() as conexion:
        fila = await conexion.fetchrow(SQL_BORRAR, id_umbral)

    if fila is None:
        return False

    (catalogo or CATALOGO).quitar(id_umbral)
    logger.info("Umbral borrado: id %d", id_umbral)
    return True


async def recargar(catalogo: Umbrales | None = None) -> int:
    """Trae la tabla a memoria. Devuelve cuántos umbrales quedaron cargados."""
    umbrales = await listar()
    (catalogo or CATALOGO).reemplazar(umbrales)
    return len(umbrales)


async def mantener_al_dia(catalogo: Umbrales | None = None) -> None:
    """Tarea de fondo: recarga la tabla cada minuto. No termina.

    Existe sobre todo por el arranque con la base caída. Sin esto, Argos levantaría con
    el catálogo vacío, el detector no encontraría nada que vigilar y todo se vería
    perfectamente normal — hasta el día que esperabas el aviso.
    """
    destino = catalogo or CATALOGO

    while True:
        try:
            cuantos = await recargar(destino)
            logger.debug("Umbrales al día: %d configurados", cuantos)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Se avisa fuerte solo mientras nunca se haya logrado cargar: ahí Argos no
            # está vigilando nada y hay que saberlo. Después, un fallo suelto es un
            # bache y la copia en memoria sigue siendo válida.
            if destino.cargado_alguna_vez:
                logger.warning("No se pudieron recargar los umbrales: %s", error)
            else:
                logger.error(
                    "AÚN NO se pudieron leer los umbrales (%s). "
                    "Hasta que se pueda, la alerta de umbral NO está vigilando nada.",
                    error,
                )

        await asyncio.sleep(SEGUNDOS_ENTRE_RECARGAS)


def umbral_a_json(umbral: Umbral) -> dict[str, object]:
    """Pasa un umbral a un diccionario listo para responder por HTTP.

    El valor va como texto por lo mismo que los precios en el resto de Argos.
    """
    return {
        "id": umbral.id,
        "simbolo": umbral.simbolo,
        "valor": str(umbral.valor),
        "direccion": umbral.direccion,
        "nota": umbral.nota,
        "creado": umbral.creado.isoformat() if umbral.creado else None,
    }


def texto_de_precio(valor: Decimal) -> str:
    """Escribe un precio sin ceros de relleno, para que quepa en una frase.

    `Decimal("70000.00000000")` sale de la base así, y "cruzó los 70000.00000000" se
    lee mal. **No se redondea**: solo se sacan los ceros que no aportan, así que el
    número sigue siendo exactamente el mismo. Las comas y los puntos de miles los pone
    el frontend (`lib/formato.ts`), que es el que sabe en qué idioma se está mostrando.
    """
    entero = valor.to_integral_value()
    if valor == entero:
        return str(entero)
    # `normalize` saca los ceros de la derecha; sobre un no entero nunca da notación
    # científica, que es el único caso que habría que evitar.
    return str(valor.normalize())


def sin_duplicado(umbrales: Sequence[Umbral], simbolo: str, valor: Decimal, direccion: str) -> bool:
    """¿Se puede crear este umbral, o ya existe uno igual?

    La base también lo impide (índice único), pero preguntarlo antes permite responder
    un 409 con un mensaje claro en vez de dejar escapar un error de asyncpg.
    """
    return not any(
        u.simbolo == simbolo and u.valor == valor and u.direccion == direccion
        for u in umbrales
    )
