"""El antirruido: cuándo Argos se calla aunque tenga algo que decir (paso 3.1).

## Por qué esto existe
Imagina el detector de volumen anómalo. A las 14:03 el volumen de BTC está a 3,4σ de
su media y salta la alerta. A las 14:04 sigue a 3,2σ. A las 14:05, a 3,1σ. Todas son
detecciones correctas — y las tres son **la misma noticia**. Sin nada que lo frene,
Argos te manda sesenta mensajes por hora contando lo mismo.

Eso tiene nombre: fatiga de alertas. Y el final es conocido: silencias las
notificaciones y el día que salte la que importaba no te enteras. Un vigilante que grita
todo el tiempo es igual de inútil que uno dormido, con el agravante de que parece que
funciona.

Por eso el spec pone "bajo ruido sobre volumen de alertas" como guardarraíl, y por eso
esto vive en el motor y no en cada detector: es una propiedad del sistema. Un detector
nuevo, escrito dentro de un año, nace con el antirruido puesto sin tener que acordarse.

## Cómo decide
Con la `clave` de la alerta, que identifica la *situación* y no el mensaje. Mientras la
situación siga siendo la misma, se dice una vez y se espera. Cuánto se espera lo elige
cada detector en su atributo `silencio`, porque no todas las situaciones duran igual:
un umbral de precio cruzado es un instante, una anomalía de volumen se estira minutos.

## Lo que NO hace
No borra la alerta: el detector la emitió y tenía razón. Solo decide no repetirla.
Las silenciadas se cuentan (`silenciadas` en el motor) para poder mirar el número: si
es enorme, el problema no es el silencio, es un detector demasiado gritón.
"""

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

VENTANA_DE_OLVIDO = timedelta(hours=6)
"""Cuánto se recuerda una clave que no volvió a aparecer.

Sin esto el diccionario crece para siempre. Es holgado a propósito: tiene que ser mucho
mayor que cualquier `silencio` razonable de un detector, porque olvidar una clave antes
de tiempo equivale a permitir el repetido que justamente estamos evitando."""


class Silencio:
    """Recuerda cuándo se dijo cada cosa por última vez.

    Vive en memoria y se reconstruye al arrancar desde la tabla `alertas` (ver
    `precargar`). Es la misma división de siempre en Argos: la memoria responde al
    instante, el disco recuerda entre reinicios.
    """

    def __init__(self) -> None:
        self._ultima_vez: dict[str, datetime] = {}
        self.silenciadas = 0
        """Cuántas alertas correctas se dejaron pasar por repetidas. Es un dato de
        salud: si sube muy rápido, hay un detector emitiendo de más."""

    def permite(self, clave: str, momento: datetime, ventana: timedelta) -> bool:
        """¿Se puede decir esto ahora, o se dijo hace muy poco?"""
        ultima = self._ultima_vez.get(clave)

        if ultima is None:
            return True

        # `>=` y no `>`: con una ventana de cero (un detector que quiere emitir en cada
        # evaluación) tiene que dar siempre permiso.
        if momento - ultima >= ventana:
            return True

        self.silenciadas += 1
        logger.debug(
            "Silenciada '%s': se dijo hace %s (espera %s)", clave, momento - ultima, ventana
        )
        return False

    def anotar(self, clave: str, momento: datetime) -> None:
        """Registra que se acaba de decir. El motor la llama solo cuando emite de verdad."""
        self._ultima_vez[clave] = momento

    def precargar(self, ultimas: Mapping[str, datetime]) -> int:
        """Rellena la memoria con lo último que se dijo de cada clave, leído de la base.

        Sin esto, reiniciar el backend sería una forma de saltarse el antirruido: la
        memoria arranca vacía y la primera vuelta repetiría alertas que se mandaron
        treinta segundos antes. Con `--reload` puesto durante el desarrollo, eso pasaría
        con cada cambio de código.

        No pisa lo que ya esté en memoria y sea más nuevo.
        """
        cargadas = 0
        for clave, momento in ultimas.items():
            actual = self._ultima_vez.get(clave)
            if actual is None or momento > actual:
                self._ultima_vez[clave] = momento
                cargadas += 1

        if cargadas:
            logger.info("Silencio precargado con %d claves ya emitidas", cargadas)
        return cargadas

    def olvidar_viejas(self, momento: datetime) -> int:
        """Saca las claves que no aparecen hace rato. Devuelve cuántas sacó."""
        limite = momento - VENTANA_DE_OLVIDO
        viejas = [clave for clave, cuando in self._ultima_vez.items() if cuando < limite]

        for clave in viejas:
            del self._ultima_vez[clave]

        return len(viejas)

    def resumen(self) -> dict[str, int]:
        """Pulso del antirruido, para exponerlo junto al resto del estado."""
        return {
            "claves_recordadas": len(self._ultima_vez),
            "silenciadas": self.silenciadas,
        }
