"""Cómo Argos decide que algo es "raro" (paso 3.4, compartido desde el 3.5).

Dos detectores hacen la misma pregunta sobre cosas distintas —la #3 sobre cuánto se agitó
el precio, la #4 sobre cuánto se operó— y la respuesta se calcula igual. Vive acá para
que se calcule una sola vez y, sobre todo, para que el motivo esté escrito una sola vez.

## Por qué no se usan la media y la desviación estándar
El z-score de manual, `(valor − media) / desviación`, da por sentado que los datos se
reparten como una campana. Ni la agitación del precio ni el volumen lo hacen: no pueden
ser negativos, se amontonan cerca de la calma y tienen una cola derecha larguísima. Sobre
esa forma, la media y la desviación las mueven justamente los picos, y eso rompe la
detección en los dos momentos que más importan:

- **Después de un evento grande**, los picos recién ocurridos inflan la desviación y las
  réplicas quedan con un z chico. Argos se queda ciego justo después del evento.
- **En calma total**, la desviación se acerca a cero y cualquier respiro da un z enorme.

## Qué se usa en su lugar
La **mediana** como centro y el **MAD** (mediana de las distancias a la mediana) como
dispersión. Los dos salen del orden de los datos, no de su suma, así que un puñado de
valores extremos no los arrastra: eso es lo que quiere decir "robusto". Hay una prueba
que hace las dos cuentas sobre los mismos números y el contraste queda a la vista.

El MAD se multiplica por 1,4826 para dejarlo en la escala de una desviación estándar
—es el factor que las hace coincidir cuando los datos SÍ son una campana—, así los z de
Argos son comparables con los de cualquier otro lado.

## Ojo con la escala de los umbrales
Que el z sea robusto no lo vuelve pequeño. Medido sobre la historia real de la base, los
tramos de 5 minutos dan p99≈7 y p99,99≈34: el clásico "3 sigma" acá es cosa de todos los
días. Los umbrales de cada detector se eligen mirando su propia distribución, no copiando
el número de un libro.
"""

from collections.abc import Sequence
from decimal import Decimal
from statistics import median

FACTOR_MAD = Decimal("1.4826")
"""Lo que pone al MAD en la escala de una desviación estándar (para datos normales)."""


def centro_y_dispersion(muestras: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    """La mediana de las muestras y su dispersión robusta. Ver el encabezado del módulo.

    La dispersión puede salir **cero**, y no es un error: pasa cuando más de la mitad de
    las muestras valen exactamente lo mismo. Quien llame tiene que decidir qué hacer con
    eso — nunca dividir sin mirar.
    """
    centro = Decimal(median(muestras))
    dispersion = Decimal(median([abs(muestra - centro) for muestra in muestras])) * FACTOR_MAD
    return centro, dispersion


def z_robusto(valor: Decimal, muestras: Sequence[Decimal]) -> tuple[Decimal, Decimal, Decimal] | None:
    """Cuán raro es `valor` frente a `muestras`: devuelve (z, centro, dispersión).

    `None` cuando no hay con qué comparar —sin muestras, o con todas iguales—. Se devuelve
    la nada y no un número grande: sin dispersión, "raro" no significa nada, y fabricar un
    infinito sería exactamente el tipo de número inventado que la regla de oro prohíbe.
    """
    if not muestras:
        return None

    centro, dispersion = centro_y_dispersion(muestras)
    if dispersion <= 0:
        return None

    return (valor - centro) / dispersion, centro, dispersion
