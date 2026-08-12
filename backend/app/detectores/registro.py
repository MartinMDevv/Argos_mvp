"""El registro de detectores: dónde "enchufar" es literal (paso 3.1).

## El problema que resuelve
La forma obvia de sumar detectores es una lista en algún lado:

    DETECTORES = [UmbralDePrecio(), MovimientoPorcentual(), Volatilidad(), ...]

Funciona, y es exactamente lo que el spec pide evitar. Con esa lista, agregar un
detector son dos cambios en dos archivos, y el motor —que no debería saber nada de
detectores concretos— termina importándolos a todos. La escalabilidad de la Fase 3 del
norte (memecoins, on-chain, social) depende de que sumar una alerta sea *agregar*, no
*editar*.

## Cómo funciona acá
Un decorador y un descubrimiento automático:

    @registrar
    class UmbralDePrecio(Detector):
        nombre = "umbral_precio"
        ...

Guardas el archivo en `app/detectores/` y listo. `descubrir()` importa todos los
módulos de la carpeta al arrancar, cada `@registrar` se ejecuta al importarse y el
detector queda en el catálogo. No hay ninguna lista que mantener.

## Las validaciones son a propósito ruidosas
`registrar` revisa el detector **al importarlo**, no al usarlo, y revienta con un
mensaje concreto si algo está mal. Un detector con el intervalo mal escrito tiene que
impedir que Argos arranque, no fallar en silencio a las tres de la mañana y dejarte sin
la alerta que esperabas. Que no salte una alerta no se nota; ese es justamente el
peligro.
"""

import importlib
import logging
import pkgutil
from collections.abc import Iterable, Sequence
from pathlib import Path

from app.detectores.base import Cadencia, Detector
from app.velas import INTERVALOS

logger = logging.getLogger(__name__)

_CATALOGO: dict[str, type[Detector]] = {}

INFRAESTRUCTURA = frozenset({"base", "registro", "motor", "silencio", "almacen"})
"""Módulos de esta carpeta que son la maquinaria, no detectores. `descubrir()` los
saltea: ya están importados y no tienen nada que registrar."""

ATRIBUTOS_OBLIGATORIOS = ("nombre", "titulo", "descripcion", "cadencia")


def registrar(clase: type[Detector]) -> type[Detector]:
    """Decorador que suma un detector al catálogo. Lo valida antes de aceptarlo."""
    for atributo in ATRIBUTOS_OBLIGATORIOS:
        if not getattr(clase, atributo, None):
            raise ValueError(
                f"El detector {clase.__name__} no define '{atributo}'. "
                "Todo detector tiene que decir cómo se llama, qué muestra y cuándo corre."
            )

    nombre = clase.nombre

    # Dos detectores con el mismo nombre serían indistinguibles en la base y el
    # segundo pisaría al primero sin que se note. Mejor no arrancar.
    ya_estaba = _CATALOGO.get(nombre)
    if ya_estaba is not None and ya_estaba is not clase:
        raise ValueError(
            f"Ya hay un detector llamado '{nombre}' ({ya_estaba.__module__}). "
            f"Elige otro nombre para {clase.__module__}.{clase.__name__}."
        )

    if not isinstance(clase.cadencia, Cadencia):
        raise ValueError(
            f"El detector '{nombre}' tiene una cadencia inválida ({clase.cadencia!r}). "
            f"Usa Cadencia.POR_TICK o Cadencia.POR_VELA_CERRADA."
        )

    if clase.cadencia is Cadencia.POR_VELA_CERRADA and clase.intervalo not in INTERVALOS:
        raise ValueError(
            f"El detector '{nombre}' pide el intervalo '{clase.intervalo}', que no existe. "
            f"Opciones: {', '.join(INTERVALOS)}"
        )

    # Un detector `por_tick` corre en la ruta caliente de la ingesta, donde no hay
    # velas cargadas (traerlas costaría una consulta por tick). Si pide historia,
    # nunca podría opinar: se callaría para siempre y parecería que no encuentra nada.
    if clase.cadencia is Cadencia.POR_TICK and clase.velas_necesarias > 0:
        raise ValueError(
            f"El detector '{nombre}' es POR_TICK pero pide {clase.velas_necesarias} velas. "
            "La ruta del tick no carga historia: usa Cadencia.POR_VELA_CERRADA."
        )

    if clase.silencio.total_seconds() < 0:
        raise ValueError(f"El detector '{nombre}' tiene un silencio negativo.")

    _CATALOGO[nombre] = clase
    return clase


def descubrir() -> list[str]:
    """Importa todos los módulos de `app/detectores/` para que se registren solos.

    Devuelve los nombres de los detectores encontrados. Se llama una vez al arrancar;
    volver a llamarla no duplica nada (Python cachea los módulos ya importados).
    """
    carpeta = Path(__file__).resolve().parent

    for modulo in pkgutil.iter_modules([str(carpeta)]):
        if modulo.name in INFRAESTRUCTURA or modulo.name.startswith("_"):
            continue
        importlib.import_module(f"{__package__}.{modulo.name}")

    encontrados = sorted(_CATALOGO)
    logger.info(
        "Detectores registrados (%d): %s",
        len(encontrados),
        ", ".join(encontrados) if encontrados else "ninguno",
    )
    return encontrados


def catalogo() -> dict[str, type[Detector]]:
    """Los detectores registrados, por nombre. Copia: nadie edita el original."""
    return dict(_CATALOGO)


def crear(nombres: Iterable[str] | None = None) -> list[Detector]:
    """Instancia los detectores pedidos (o todos, si no se pide ninguno en particular).

    Lanza `KeyError` si se pide uno que no existe: un nombre mal escrito en la
    configuración tiene que avisar, no dejar a Argos vigilando de menos en silencio.
    """
    if nombres is None:
        elegidos: Sequence[str] = sorted(_CATALOGO)
    else:
        elegidos = list(nombres)
        faltantes = [nombre for nombre in elegidos if nombre not in _CATALOGO]
        if faltantes:
            raise KeyError(
                f"No existen los detectores: {', '.join(faltantes)}. "
                f"Registrados: {', '.join(sorted(_CATALOGO)) or 'ninguno'}"
            )

    return [_CATALOGO[nombre]() for nombre in elegidos]


def ficha(clase: type[Detector]) -> dict[str, object]:
    """Describe un detector para `GET /detectores`."""
    return {
        "nombre": clase.nombre,
        "titulo": clase.titulo,
        "descripcion": clase.descripcion,
        "cadencia": str(clase.cadencia),
        "intervalo": clase.intervalo if clase.cadencia is Cadencia.POR_VELA_CERRADA else None,
        "velas_necesarias": clase.velas_necesarias,
        "silencio_segundos": int(clase.silencio.total_seconds()),
    }
