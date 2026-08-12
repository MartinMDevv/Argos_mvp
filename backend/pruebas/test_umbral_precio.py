"""Alerta #1: que avise al CRUZAR, y que no avise cuando no cruzó (paso 3.2).

Casi todas estas pruebas son sobre lo segundo. Un detector de umbrales es fácil de
escribir mal de una forma que parece que funciona: avisa cuando el precio pasa la línea
—correcto— y también cada vez que lo evalúan mientras siga del otro lado, que es la
diferencia entre un aviso y un goteo.

Las pruebas alimentan al detector con una secuencia de precios, como haría la ingesta, y
miran qué sale de cada paso.
"""

from decimal import Decimal

from app.detectores.umbral_precio import UmbralDePrecio
from app.detectores.umbrales import Umbrales, texto_de_precio
from app.modelos import Umbral

from .conftest import hacer_contexto, hacer_tick


def con_umbrales(*umbrales: Umbral) -> UmbralDePrecio:
    """Un detector cargado con los umbrales que se le pasen, sin tocar la base."""
    catalogo = Umbrales()
    catalogo.reemplazar(umbrales)
    return UmbralDePrecio(umbrales=catalogo)


def umbral(valor: str, direccion: str = "arriba", simbolo: str = "BTCUSDT", **extra) -> Umbral:
    return Umbral(simbolo=simbolo, valor=Decimal(valor), direccion=direccion, **extra)


def alimentar(detector: UmbralDePrecio, *precios: str, simbolo: str = "BTCUSDT") -> list[list]:
    """Le pasa una secuencia de precios y devuelve lo que emitió en cada uno."""
    return [
        detector.evaluar(hacer_contexto(tick=hacer_tick(precio, simbolo=simbolo), simbolo=simbolo))
        for precio in precios
    ]


# -- Lo que tiene que avisar ---------------------------------------------------


def test_avisa_al_cruzar_hacia_arriba():
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "69900", "70100")

    assert pasos[0] == []  # primera observación: solo anota el lado
    assert len(pasos[1]) == 1
    assert "cruzó 70000 hacia arriba" in pasos[1][0].detalle


def test_avisa_al_cruzar_hacia_abajo():
    detector = con_umbrales(umbral("3400", "abajo", simbolo="ETHUSDT"))

    pasos = alimentar(detector, "3450", "3390", simbolo="ETHUSDT")

    assert len(pasos[1]) == 1
    assert "cruzó 3400 hacia abajo" in pasos[1][0].detalle


def test_avisa_de_nuevo_si_vuelve_a_cruzar():
    """Baja, sube: son dos cruces distintos y los dos son noticia.

    (El silencio del motor puede callar el segundo si pasa muy pronto, pero esa
    decisión es del motor. El detector tiene que reportar los dos.)
    """
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "69900", "70100", "69800", "70200")

    assert len(pasos[1]) == 1
    assert pasos[2] == []  # bajó: a este umbral no le interesa
    assert len(pasos[3]) == 1


def test_un_tick_puede_cruzar_varios_umbrales_a_la_vez():
    """El caso que obligó a que `evaluar` devuelva una lista.

    Un salto de 69.900 a 71.200 cruza el de 70.000 y el de 71.000. Si solo se reportara
    uno, el otro quedaría marcado como visto sin haber avisado nunca.
    """
    detector = con_umbrales(umbral("70000", "arriba"), umbral("71000", "arriba"))

    pasos = alimentar(detector, "69900", "71200")

    assert len(pasos[1]) == 2
    cruzados = {a.evidencia["umbral"] for a in pasos[1]}
    assert cruzados == {"70000", "71000"}


def test_cada_umbral_tiene_su_propia_clave():
    """Para que callar uno no calle al otro cuando el motor aplique el silencio."""
    detector = con_umbrales(umbral("70000", "arriba"), umbral("71000", "arriba"))

    alertas = alimentar(detector, "69900", "71200")[1]

    assert len({a.clave for a in alertas}) == 2


# -- Lo que NO tiene que avisar ------------------------------------------------


def test_no_avisa_si_al_despertar_el_precio_ya_estaba_del_otro_lado():
    """El caso más importante del detector.

    Argos arranca, el primer precio de BTC es 71.000 y hay un umbral en 70.000. No vio
    ningún cruce: se despertó y el precio ya estaba ahí. Avisar sería fechar hoy algo
    que pasó mientras estaba apagado.
    """
    detector = con_umbrales(umbral("70000", "arriba"))

    assert alimentar(detector, "71000") == [[]]


def test_no_repite_mientras_se_queda_del_mismo_lado():
    """La diferencia entre avisar de un cruce y gotear mientras dure la condición."""
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "69900", "70100", "70200", "70300", "70400")

    assert len(pasos[1]) == 1
    assert pasos[2:] == [[], [], []]


def test_no_avisa_si_cruza_hacia_el_lado_que_no_le_importa():
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "70100", "69900")  # cruza, pero bajando

    assert pasos[1] == []


def test_no_avisa_si_se_acerca_sin_cruzar():
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "69000", "69500", "69900", "69999.99")

    assert all(paso == [] for paso in pasos)


def test_un_umbral_de_otro_simbolo_no_se_dispara():
    detector = con_umbrales(umbral("70000", "arriba", simbolo="BTCUSDT"))

    pasos = alimentar(detector, "69900", "70100", simbolo="ETHUSDT")

    assert all(paso == [] for paso in pasos)


def test_sin_umbrales_configurados_no_opina():
    detector = UmbralDePrecio(umbrales=Umbrales())
    contexto = hacer_contexto(tick=hacer_tick("70100"))

    assert detector.puede_opinar(contexto) is False


def test_sin_precio_no_opina():
    detector = con_umbrales(umbral("70000", "arriba"))

    assert detector.evaluar(hacer_contexto()) == []


# -- El borde exacto -----------------------------------------------------------


def test_la_linea_pertenece_al_lado_de_abajo_subiendo():
    """"Avísame si sube de 70.000" no avisa AL llegar a 70.000, sino al pasarlo."""
    detector = con_umbrales(umbral("70000", "arriba"))

    pasos = alimentar(detector, "69900", "70000", "70000.01")

    assert pasos[1] == []       # tocar la línea no es superarla
    assert len(pasos[2]) == 1   # un centavo más arriba, sí


def test_la_linea_pertenece_al_lado_de_abajo_bajando():
    """"Avísame si baja de 3.400" avisa al tocar 3.400 justo."""
    detector = con_umbrales(umbral("3400", "abajo", simbolo="ETHUSDT"))

    pasos = alimentar(detector, "3450", "3400", simbolo="ETHUSDT")

    assert len(pasos[1]) == 1


def test_dos_umbrales_en_el_mismo_valor_comparten_el_lado_visto():
    """Uno hacia arriba y otro hacia abajo sobre el mismo número.

    De qué lado está el precio es una sola cosa, no una por umbral. Cada cruce dispara
    solo el que mira hacia ese lado.
    """
    detector = con_umbrales(umbral("70000", "arriba"), umbral("70000", "abajo"))

    pasos = alimentar(detector, "69900", "70100", "69800")

    assert [a.evidencia["direccion"] for a in pasos[1]] == ["arriba"]
    assert [a.evidencia["direccion"] for a in pasos[2]] == ["abajo"]


# -- La evidencia y el mensaje -------------------------------------------------


def test_la_alerta_trae_los_numeros_para_rehacer_la_cuenta():
    detector = con_umbrales(umbral("70000", "arriba"))

    alerta = alimentar(detector, "69900", "70100.50")[1][0]

    assert alerta.evidencia["umbral"] == "70000"
    assert alerta.evidencia["precio"] == "70100.50"
    assert alerta.evidencia["precio_anterior"] == "69900"
    assert alerta.evidencia["distancia"] == "100.50"
    assert alerta.evidencia["direccion"] == "arriba"


def test_el_mensaje_dice_de_donde_venia():
    detector = con_umbrales(umbral("70000", "arriba"))

    alerta = alimentar(detector, "69900", "70100")[1][0]

    assert "venía de 69900" in alerta.detalle


def test_no_dice_que_venia_de_la_linea_misma():
    """Salió de mirar una alerta real: "cruzó 63834 hacia arriba (venía de 63834)".

    Es cierto —la línea cuenta como abajo— pero se lee como un error, y pasa seguido
    porque los umbrales se ponen en números redondos y el precio se queda pegado ahí.
    El dato exacto sigue en la evidencia.
    """
    detector = con_umbrales(umbral("70000", "arriba"))

    alerta = alimentar(detector, "70000", "70000.06")[1][0]

    assert "venía de" not in alerta.detalle
    assert alerta.detalle == "BTCUSDT cruzó 70000 hacia arriba. Precio: 70000.06."
    assert alerta.evidencia["precio_anterior"] == "70000"


def test_la_nota_del_umbral_viaja_en_el_aviso():
    detector = con_umbrales(umbral("70000", "arriba", nota="objetivo de venta"))

    alerta = alimentar(detector, "69900", "70100")[1][0]

    assert "objetivo de venta" in alerta.detalle


def test_la_severidad_es_aviso():
    """No es `info` (lo pediste tú, no es color) ni `fuerte` (eso queda para lo que
    Argos encuentre solo y sea anómalo de verdad)."""
    detector = con_umbrales(umbral("70000", "arriba"))

    assert alimentar(detector, "69900", "70100")[1][0].severidad == "aviso"


# -- El formato de los números en el texto -------------------------------------


def test_texto_de_precio_saca_los_ceros_de_relleno():
    """La base devuelve NUMERIC(20,8): "70000.00000000" no se puede meter en una frase."""
    assert texto_de_precio(Decimal("70000.00000000")) == "70000"
    assert texto_de_precio(Decimal("3400.50000000")) == "3400.5"
    assert texto_de_precio(Decimal("0.00001000")) == "0.00001"


def test_texto_de_precio_no_usa_notacion_cientifica():
    """`Decimal.normalize()` sobre un entero grande da "7E+4"; eso no puede llegar a un
    mensaje."""
    assert texto_de_precio(Decimal("70000")) == "70000"
    assert texto_de_precio(Decimal("100000000")) == "100000000"


def test_texto_de_precio_no_redondea():
    """Saca ceros, no cifras: el número que se muestra sigue siendo el exacto."""
    assert texto_de_precio(Decimal("63745.92000001")) == "63745.92000001"
