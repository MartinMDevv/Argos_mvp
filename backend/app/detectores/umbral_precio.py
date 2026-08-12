"""Alerta #1: el precio cruzó una línea que pusiste tú (paso 3.2).

La más simple de las cuatro del MVP y la de menos ruido, porque el criterio no lo pone
Argos: lo pusiste tú. "Avísame si BTC pasa de 70.000".

## Cruzar no es estar
La versión ingenua de esto es `if precio > umbral: avisar`, y está mal. Mientras BTC se
quede arriba de 70.000 —horas, días— esa condición sigue siendo verdadera, y Argos te
avisaría una y otra vez de algo que ya te contó. Lo que tú quieres saber es el
**momento en que cruza**: una transición, no un estado.

Y una transición no se puede ver en un instante. Hace falta saber de qué lado estaba el
precio la vez anterior.

## La única memoria que este detector se permite
Por eso guarda, para cada línea, **de qué lado vio el precio la última vez**. Es un dato
mínimo y derivado de los ticks que ya pasaron, así que el detector sigue siendo
reproducible: dale la misma secuencia de operaciones y emite las mismas alertas. Eso es
lo que importa para poder correrlo sobre la historia más adelante (v2.0, backtesting).

Lo que sigue estando prohibido, y acá se respeta, es salir a buscar datos: el detector
no toca la base ni la red. La configuración le llega ya cargada en memoria
(`umbrales.py`) y el precio le llega en el contexto.

## Recién despierto no se inventa un cruce
Argos arranca, el primer tick de BTC dice 71.000 y hay un umbral en 70.000. ¿Avisa?
**No.** No vio ningún cruce: se despertó y el precio ya estaba ahí. Decir "BTC cruzó los
70.000" sería fechar hoy algo que pasó mientras Argos estaba apagado.

La primera observación de cada línea solo anota el lado, en silencio. El costo es que un
reinicio puede perderse un cruce; el beneficio es que Argos nunca afirma haber visto algo
que no vio. Es el mismo criterio que en todo el resto del proyecto: mejor un hueco
honesto que un dato inventado.

## Cuando el precio queda bailando sobre la línea
Con BTC oscilando entre 69.999 y 70.001, hay un cruce de verdad cada pocos segundos.
Todos correctos, todos la misma noticia. De eso se encarga el silencio del motor, que
para este detector es lo que evita cien avisos idénticos en un minuto. Si con el uso se
viera que quince minutos no alcanzan, el próximo escalón conocido es la histéresis (no
volver a armar la línea hasta que el precio se aleje un margen). No se hace todavía:
suma un ajuste que hay que entender, y el silencio ya cubre el caso.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.registro import registrar
from app.detectores.umbrales import CATALOGO, Umbrales, texto_de_precio
from app.modelos import Alerta

logger = logging.getLogger(__name__)

ARRIBA = "arriba"
ABAJO = "abajo"


@registrar
class UmbralDePrecio(Detector):
    """Avisa cuando el precio cruza uno de los valores configurados."""

    nombre = "umbral_precio"
    titulo = "Umbral tocado"
    descripcion = (
        "Avisa cuando el precio cruza un valor que fijaste tú. "
        "Se configuran en GET/POST /umbrales."
    )
    cadencia = Cadencia.POR_TICK
    velas_necesarias = 0

    silencio = timedelta(minutes=15)
    """Contra el precio que queda bailando sobre la línea: ver el encabezado del módulo.
    Cada umbral tiene su propia clave, así que callar el de 70.000 no calla el de 60.000."""

    def __init__(self, umbrales: Umbrales | None = None) -> None:
        # Por defecto usa el catálogo compartido del proceso, que es lo que necesita
        # `registro.crear()` (instancia sin argumentos). Las pruebas le pasan el suyo:
        # es la forma de que un detector con configuración siga siendo probable sin
        # levantar nada.
        self.umbrales = umbrales if umbrales is not None else CATALOGO

        # Línea → de qué lado vimos el precio la última vez. La clave es
        # (símbolo, valor) y NO el id del umbral, a propósito: lo que se recuerda es
        # dónde está el precio respecto de esa línea, y eso no cambia porque el umbral
        # se borre y se vuelva a crear, ni porque haya dos umbrales (uno hacia arriba y
        # otro hacia abajo) sobre el mismo número.
        self._lado_visto: dict[tuple[str, Decimal], str] = {}

        # El precio de la evaluación anterior, por símbolo. Solo para poder contar de
        # dónde venía: sin esto la alerta diría "cruzó" sin decir desde dónde.
        self._precio_anterior: dict[str, Decimal] = {}

    def puede_opinar(self, contexto: ContextoDeEvaluacion) -> bool:
        """Sin umbrales configurados para este símbolo no hay nada que mirar."""
        return bool(self.umbrales.de(contexto.simbolo))

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        tick = contexto.tick
        if tick is None:
            return []  # sin precio no se opina

        precio = tick.precio
        anterior = self._precio_anterior.get(contexto.simbolo)
        self._precio_anterior[contexto.simbolo] = precio

        umbrales = self.umbrales.de(contexto.simbolo)

        # --- 1. De qué lado está el precio respecto de cada línea, y de qué lado estaba.
        #
        # Se calcula ANTES de mirar los umbrales, y no sobre la marcha, porque dos
        # umbrales pueden compartir la misma línea: uno hacia arriba y otro hacia abajo
        # sobre el mismo número. Actualizando el lado dentro del bucle, el segundo leía
        # el valor que el primero acababa de escribir, veía "no cambió" y **nunca
        # detectaba el cruce**. Lo encontró la prueba `test_dos_umbrales_en_el_mismo
        # _valor_comparten_el_lado_visto`.
        lineas: dict[tuple[str, Decimal], tuple[str | None, str]] = {}
        for umbral in umbrales:
            clave = (contexto.simbolo, umbral.valor)
            if clave in lineas:
                continue
            # La línea pertenece al lado de abajo (ver `Umbral.direccion`).
            lado_ahora = ARRIBA if precio > umbral.valor else ABAJO
            lineas[clave] = (self._lado_visto.get(clave), lado_ahora)

        # --- 2. Qué umbrales tienen algo que contar.
        alertas: list[Alerta] = []
        for umbral in umbrales:
            lado_antes, lado_ahora = lineas[(contexto.simbolo, umbral.valor)]

            if lado_antes is None:
                # Primera vez que vemos esta línea: solo anotamos de qué lado está el
                # precio. Encontrarlo ya cruzado no es haberlo visto cruzar.
                continue

            if lado_antes == lado_ahora:
                continue  # sigue del mismo lado: no pasó nada

            if lado_ahora != umbral.direccion:
                continue  # cruzó, pero hacia el lado que a este umbral no le importa

            alertas.append(self._armar_alerta(contexto, umbral, precio, anterior))

        # --- 3. Recién ahora se recuerda, con todos los umbrales ya consultados.
        for clave, (_, lado_ahora) in lineas.items():
            self._lado_visto[clave] = lado_ahora

        return alertas

    def _armar_alerta(
        self,
        contexto: ContextoDeEvaluacion,
        umbral,
        precio: Decimal,
        anterior: Decimal | None,
    ) -> Alerta:
        """Escribe el aviso, con los números que permiten verificarlo."""
        hacia = "hacia arriba" if umbral.direccion == ARRIBA else "hacia abajo"
        linea = texto_de_precio(umbral.valor)

        detalle = f"{contexto.simbolo} cruzó {linea} {hacia}"

        # El "venía de" se omite cuando el precio anterior era exactamente la línea:
        # "cruzó 70.000 hacia arriba (venía de 70.000)" es cierto —la línea cuenta como
        # abajo— pero se lee como un error. Y pasa seguido, porque los umbrales se ponen
        # en números redondos y el precio se queda pegado a ellos. El dato exacto sigue
        # estando en la evidencia; lo que se saca es una frase que confunde.
        if anterior is not None and anterior != umbral.valor:
            detalle += f" (venía de {texto_de_precio(anterior)})"

        detalle += f". Precio: {texto_de_precio(precio)}."
        if umbral.nota:
            detalle += f" — {umbral.nota}"

        evidencia = {
            "umbral": str(umbral.valor),
            "direccion": umbral.direccion,
            "precio": str(precio),
            "precio_anterior": str(anterior) if anterior is not None else "—",
            "distancia": str(precio - umbral.valor),
        }

        if contexto.tick is not None:
            evidencia["id_operacion"] = str(contexto.tick.id_operacion)
            evidencia["momento_del_tick"] = contexto.tick.momento.isoformat()

        return self.alerta(
            contexto,
            # `aviso` y no `info`: no es un dato de color, es exactamente lo que pediste
            # que te avisaran. Tampoco `fuerte`, que queda para lo que Argos encuentre
            # solo y sea de verdad anómalo.
            severidad="aviso",
            detalle=detalle,
            evidencia=evidencia,
            # Cada línea es una noticia distinta: que salte la de 70.000 no debe
            # silenciar la de 60.000.
            variante=f"{umbral.direccion}:{texto_de_precio(umbral.valor)}",
        )
