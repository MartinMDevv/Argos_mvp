"""Alerta #3: el mercado está más agitado de lo que suele estar (paso 3.4).

La que el spec llama **la clave anti-ruido**, y la primera que tiene criterio propio.

Las dos anteriores comparan contra un número que pusimos nosotros: "70.000", "2% en
cinco minutos". Y en el paso 3.3 quedó medido a qué lleva eso — con el mismo umbral, ETH
alerta tres o cuatro veces más que BTC, no porque pase más, sino porque un porcentaje
fijo no sabe contra qué activo lo están midiendo. Peor todavía: tampoco sabe contra qué
*época*. Un 2% en cinco minutos era rutina en marzo de 2020 y es un notición en una
semana plana.

Esta alerta cambia la pregunta. En vez de *"¿se movió más de X?"* pregunta **"¿esto es
raro para lo que este activo viene haciendo?"**. El umbral deja de ser un número escrito
a mano y pasa a salir de los datos del propio activo, que es lo que la regla de oro pide
en todos lados.

## Qué se mide: la amplitud de la vela
`(máximo − mínimo) / apertura`, en porcentaje. Cuánto terreno recorrió el precio dentro
del tramo, sin importar dónde terminó.

Es a propósito distinta de la #2, que mide cierre contra cierre. Un tramo que sube 3% y
vuelve al mismo lugar tiene movimiento neto **cero** y una amplitud enorme: para la #2 no
pasó nada, y sin embargo ahí hubo pánico. Las dos preguntas son distintas y por eso hay
dos detectores:

- **#2:** ¿se fue a alguna parte? (dirección)
- **#3 (esta):** ¿se está agitando? (dispersión)

La otra opción era la desviación estándar de los retornos, que es la definición de manual
de "volatilidad". Se eligió la amplitud porque es lo que una persona llama agitación, se
lee directo en la evidencia (`el tramo recorrió 1,8% cuando lo normal es 0,3%`) y la IA
de la Fase 5 la puede explicar sin traducir estadística. La de manual queda anotada por
si algún día la evidencia pide más finura.

## Por qué NO es un z-score clásico
El z-score de toda la vida —`(valor − media) / desviación`— asume que los datos se
reparten más o menos como una campana. Las amplitudes no: no pueden bajar de cero, se
amontonan cerca de la calma y tienen una cola derecha larguísima. Sobre esa forma, la
media y la desviación las mueven justamente los picos, y eso rompe la alerta en los dos
momentos que más importan:

- **Después de un desplome**, los picos que acaban de pasar inflan la desviación durante
  las 24 h siguientes. El z de las réplicas queda chico y Argos se queda **ciego justo
  después del evento**, que es cuando más se lo necesita.
- **En calma total**, la desviación se acerca a cero y cualquier respiro da un z enorme:
  ruido puro en el peor momento para gastar la atención de quien lee.

Por eso acá el centro es la **mediana** y la dispersión es el **MAD** (la mediana de las
distancias a la mediana). Los dos se calculan con el orden de los datos, no con su suma,
así que un puñado de picos no los arrastra: eso es lo que quiere decir "robusto". El MAD
se multiplica por 1,4826, que es lo que lo pone en la misma escala que una desviación
estándar de toda la vida — así un z de 3 sigue queriendo decir más o menos lo que
esperarías que quiera decir.

Y aun así se le pone un **piso absoluto** de amplitud: en una noche muerta, "diez veces
más agitado que lo normal" pueden ser dos décimas de porcentaje. Estadísticamente cierto,
humanamente irrelevante. Sin ese piso, esta alerta hablaría toda la madrugada.

## Se rearma cuando vuelve la calma
Es el pariente del "moverse no es haberse movido" de la #2. Un episodio de volatilidad no
dura un tramo: dura mientras dura. Si el detector avisara en cada evaluación mientras el
z siga alto, contaría el mismo episodio una y otra vez.

Entonces avisa **al entrar** en zona rara y después se queda callado hasta que el z vuelve
a valores normales; recién ahí se rearma. Un episodio = un aviso, y el siguiente aviso
significa de verdad "esto empezó de nuevo". Es la misma memoria mínima y derivada de los
datos que ya usan las otras dos: reproducible, y por lo tanto rebobinable sobre el pasado.
"""

import statistics
from datetime import timedelta
from decimal import Decimal

from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.registro import registrar
from app.modelos import Alerta, Vela
from app.velas import INTERVALOS

INTERVALO = "5m"
"""Tramo que se mira. Cinco minutos y no uno por dos razones que empujan igual: un minuto
suelto de cripto es casi todo ruido, y 24 h de referencia en velas de 1m son 1.441, por
encima del tope de 1.000 de `obtener_velas`. En tramos de 5m son 288 y entran holgadas
(medido: 22 ms la consulta, contra 31 ms la misma cantidad en 1m)."""

VELAS_DE_REFERENCIA = 288
"""Cuánto pasado define "lo normal": 288 tramos de 5 minutos = **24 horas**.

Es un compromiso deliberado. Con mucho menos, un rato movido se vuelve "lo normal" y la
alerta se apaga sola justo cuando hay acción. Con mucho más, "lo normal" es el humor de
la semana pasada y deja de reconocer el régimen de hoy — que es media gracia de esta
alerta, porque el mercado cambia de humor por temporadas."""

Z_PARA_AVISAR = Decimal("25")
"""Cuán raro tiene que ser para avisar, medido en desviaciones robustas.

**Muy por encima del 3 de manual, y no es un error.** El 3 clásico viene de suponer una
campana, donde pasar de 3σ es raro de verdad. Estos datos no son una campana: medidos
sobre los 369 días de la base, los z de los tramos de 5 minutos dan p50≈0, p90≈2,3,
p99≈7, p99,9≈15 y p99,99≈34. Con el umbral en 3 —o en 5, que fue la primera propuesta—
esta alerta hablaba entre 90 y 130 veces al mes: ruido puro.

En 25 quedan 2,4 alertas al mes en BTC y 3,7 en ETH, contadas sobre historia real. El
número sale de la distribución, no de la costumbre estadística."""

Z_PARA_REARMAR = Decimal("8")
"""Por debajo de esto se considera que el episodio terminó y se puede volver a avisar.

Es aproximadamente el p99: mientras el z siga por encima, lo que pasa sigue siendo
anormal y el episodio no terminó. Va bastante más abajo que `Z_PARA_AVISAR` a propósito;
si los dos números estuvieran pegados, un z bailando alrededor del umbral daría un aviso
nuevo cada vez que lo cruza, que es exactamente el goteo que se quiere evitar."""

Z_PARA_FUERTE = Decimal("50")
"""A partir de acá la alerta sube de `aviso` a `fuerte`: media alerta al mes, o sea los
episodios de verdad grandes."""

AMPLITUD_MINIMA = Decimal("0.5")
"""Piso absoluto: por debajo de este recorrido (en % del precio) no se avisa, por más
raro que sea el número. Ver "Por qué NO es un z-score clásico".

Medio punto porcentual está cerca del p97 de los tramos de BTC y del p95 de los de ETH:
lo bastante arriba como para tapar las madrugadas muertas, lo bastante abajo como para
no censurar un movimiento real de un día tranquilo."""

FACTOR_MAD = Decimal("1.4826")
"""Lo que pone al MAD en la escala de una desviación estándar (para datos normales).
Sin esto, los z de este detector no serían comparables con los de ningún otro lado."""


@registrar
class VolatilidadAnomala(Detector):
    """Avisa cuando el mercado se agita mucho más de lo que viene siendo su costumbre."""

    nombre = "volatilidad_anomala"
    titulo = "Volatilidad anómala"
    descripcion = (
        "Avisa cuando el precio se agita mucho más de lo normal para este activo, "
        "comparando el recorrido del tramo contra sus últimas 24 horas."
    )
    cadencia = Cadencia.POR_VELA_CERRADA
    intervalo = INTERVALO
    velas_necesarias = VELAS_DE_REFERENCIA + 1
    """La referencia más el tramo que se está juzgando."""

    silencio = timedelta(minutes=30)
    """Red de seguridad nada más: el antirruido real es el rearme por calma. Más largo
    que el de la #2 porque un episodio de volatilidad dura más que un salto de precio."""

    def __init__(
        self,
        z_para_avisar: Decimal = Z_PARA_AVISAR,
        z_para_rearmar: Decimal = Z_PARA_REARMAR,
        amplitud_minima: Decimal = AMPLITUD_MINIMA,
        velas_de_referencia: int = VELAS_DE_REFERENCIA,
    ) -> None:
        self.z_para_avisar = z_para_avisar
        self.z_para_rearmar = z_para_rearmar
        self.amplitud_minima = amplitud_minima
        self.velas_de_referencia = velas_de_referencia
        self.velas_necesarias = velas_de_referencia + 1

        # Símbolo → ¿ya avisamos de este episodio y estamos esperando que se calme?
        self._en_episodio: dict[str, bool] = {}

    def puede_opinar(self, contexto: ContextoDeEvaluacion) -> bool:
        """Sin la referencia completa no se opina, y no es una formalidad.

        Un MAD sacado de veinte tramos no es "lo normal de este activo": es lo normal del
        último rato, que suele ser justo el rato que se quiere juzgar. Publicar un z
        calculado así sería inventar precisión, que es lo que la regla de oro prohíbe.
        """
        return len(contexto.velas_cerradas) >= self.velas_necesarias

    def evaluar(self, contexto: ContextoDeEvaluacion) -> list[Alerta]:
        cerradas = contexto.velas_cerradas
        if len(cerradas) < self.velas_necesarias:
            return []

        actual = cerradas[-1]
        # La referencia excluye el tramo que se está juzgando: si entrara, el valor se
        # estaría comparando en parte contra sí mismo.
        referencia = cerradas[-(self.velas_de_referencia + 1) : -1]

        amplitud = amplitud_de(actual)
        if amplitud is None:
            return []

        medidas = [medida for vela in referencia if (medida := amplitud_de(vela)) is not None]
        if len(medidas) < self.velas_de_referencia:
            # Alguna vela de la referencia no se pudo medir (apertura en cero). No se
            # rellena el hueco con nada: se espera al próximo tramo.
            return []

        centro = Decimal(statistics.median(medidas))
        dispersion = Decimal(statistics.median([abs(m - centro) for m in medidas])) * FACTOR_MAD

        if dispersion <= 0:
            # Más de la mitad de las 24 h tuvieron exactamente la misma amplitud: no hay
            # variación con la cual comparar. Pasa con datos raros o mercados congelados,
            # y dividir acá sería fabricar un infinito.
            return []

        z = (amplitud - centro) / dispersion

        # ¿Se calmó? Entonces se rearma y el próximo pico vuelve a ser noticia.
        if z < self.z_para_rearmar:
            self._en_episodio[contexto.simbolo] = False

        if z < self.z_para_avisar or amplitud < self.amplitud_minima:
            return []

        if self._en_episodio.get(contexto.simbolo):
            return []  # el episodio ya se contó; sigue abierto

        self._en_episodio[contexto.simbolo] = True

        return [self._armar_alerta(contexto, actual, amplitud, centro, dispersion, z)]

    def _armar_alerta(
        self,
        contexto: ContextoDeEvaluacion,
        vela: Vela,
        amplitud: Decimal,
        centro: Decimal,
        dispersion: Decimal,
        z: Decimal,
    ) -> Alerta:
        """Escribe el aviso con los números que permiten rehacer la cuenta."""
        veces = amplitud / centro if centro > 0 else None

        detalle = (
            f"{contexto.simbolo} se agitó {texto(amplitud)}% en {self.minutos()} min, "
            f"cuando lo normal de las últimas 24 h es {texto(centro)}%"
        )
        if veces is not None:
            detalle += f" ({texto(veces)}× lo habitual)"
        detalle += f". Rareza: {texto(z)} desviaciones."

        evidencia = {
            "amplitud_pct": texto(amplitud),
            "mediana_24h_pct": texto(centro),
            "dispersion_robusta_pct": texto(dispersion),
            "z": texto(z),
            "z_exigido": str(self.z_para_avisar),
            "amplitud_minima_pct": str(self.amplitud_minima),
            # Los crudos del tramo: con estos tres se rehace la amplitud a mano.
            "maximo": str(vela.maximo),
            "minimo": str(vela.minimo),
            "apertura": str(vela.apertura),
            "cierre": str(vela.cierre),
            "inicio_vela": vela.inicio.isoformat(),
            "muestras": str(self.velas_de_referencia),
            "intervalo": contexto.intervalo,
            "fuente": vela.fuente,
        }

        return self.alerta(
            contexto,
            severidad="fuerte" if z >= Z_PARA_FUERTE else "aviso",
            detalle=detalle,
            evidencia=evidencia,
            # Sin variante: para un símbolo hay una sola situación posible (está agitado
            # o no lo está). A diferencia de la #2, acá no hay dirección que distinguir.
            variante="",
        )

    def minutos(self) -> int:
        """Cuántos minutos abarca el tramo que mira. Solo para redactar el mensaje.

        Sale de la tabla de intervalos de `velas.py` en vez de estar escrito a mano: si
        algún día este detector pasa a mirar tramos de 15 minutos, el mensaje no puede
        seguir diciendo cinco.
        """
        return int(INTERVALOS[self.intervalo].total_seconds() // 60)


def amplitud_de(vela: Vela) -> Decimal | None:
    """Cuánto terreno recorrió el precio dentro de la vela, en % de su apertura.

    `None` si no se puede calcular. Con apertura en cero no hay porcentaje posible, y
    devolver un cero disfrazaría un dato que falta como si fuera un dato tranquilo.
    """
    if vela.apertura <= 0:
        return None
    return (vela.maximo - vela.minimo) / vela.apertura * 100


def texto(valor: Decimal) -> str:
    """Dos decimales, que es la precisión que se puede leer en una frase.

    Los números crudos con los que se hizo la cuenta viajan enteros en la evidencia; esto
    es solo para que el mensaje se entienda de un vistazo.
    """
    return str(valor.quantize(Decimal("0.01")))
