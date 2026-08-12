"""El antirruido: la pieza que decide que Argos se calle aunque tenga razón.

Es la más fácil de romper sin darse cuenta, porque cuando falla no se rompe nada
visible: simplemente empiezan a llegar mensajes de más, y para cuando te diste cuenta ya
silenciaste las notificaciones. Por eso está probada al detalle, incluidos los bordes
(la ventana exacta, la ventana en cero, la precarga tras un reinicio).

Todas las pruebas manejan el tiempo a mano, con instantes fijos. Nada de `sleep`: una
prueba que depende del reloj real es lenta y algún día falla sola.
"""

from datetime import timedelta

from app.detectores.silencio import VENTANA_DE_OLVIDO, Silencio

from .conftest import MOMENTO

UN_MINUTO = timedelta(minutes=1)


# -- El comportamiento básico --------------------------------------------------


def test_la_primera_vez_siempre_pasa():
    assert Silencio().permite("k", MOMENTO, UN_MINUTO) is True


def test_lo_mismo_al_rato_se_corta():
    s = Silencio()
    s.permite("k", MOMENTO, UN_MINUTO)
    s.anotar("k", MOMENTO)

    assert s.permite("k", MOMENTO + timedelta(seconds=30), UN_MINUTO) is False


def test_pasada_la_ventana_vuelve_a_pasar():
    s = Silencio()
    s.anotar("k", MOMENTO)

    assert s.permite("k", MOMENTO + timedelta(seconds=61), UN_MINUTO) is True


def test_en_la_ventana_exacta_pasa():
    """El borde. Con `>` en vez de `>=`, un detector con silencio de 60 s emitiría
    recién a los 61, y una ventana de cero no emitiría nunca."""
    s = Silencio()
    s.anotar("k", MOMENTO)

    assert s.permite("k", MOMENTO + UN_MINUTO, UN_MINUTO) is True


def test_una_ventana_de_cero_nunca_bloquea():
    """La usan los detectores cuya cadencia ya garantiza una evaluación por evento."""
    s = Silencio()
    s.anotar("k", MOMENTO)

    assert s.permite("k", MOMENTO, timedelta(0)) is True


# -- Que no se mezclen las noticias --------------------------------------------


def test_callar_una_clave_no_calla_a_las_demas():
    s = Silencio()
    s.anotar("volumen:BTCUSDT", MOMENTO)

    assert s.permite("volumen:ETHUSDT", MOMENTO, UN_MINUTO) is True
    assert s.permite("volumen:BTCUSDT", MOMENTO, UN_MINUTO) is False


def test_anotar_corre_la_ventana_hacia_adelante():
    s = Silencio()
    s.anotar("k", MOMENTO)
    s.anotar("k", MOMENTO + timedelta(seconds=50))

    # Al segundo 61 desde la PRIMERA, pero solo 11 desde la última.
    assert s.permite("k", MOMENTO + timedelta(seconds=61), UN_MINUTO) is False


# -- El contador ---------------------------------------------------------------


def test_cuenta_las_silenciadas():
    """El número no es decorativo: si crece muy rápido, hay un detector gritón."""
    s = Silencio()
    s.anotar("k", MOMENTO)

    for segundo in range(1, 6):
        s.permite("k", MOMENTO + timedelta(seconds=segundo), UN_MINUTO)

    assert s.silenciadas == 5
    assert s.resumen()["silenciadas"] == 5


def test_las_permitidas_no_se_cuentan_como_silenciadas():
    s = Silencio()
    s.permite("k", MOMENTO, UN_MINUTO)

    assert s.silenciadas == 0


# -- La precarga: que un reinicio no sea una forma de saltarse el silencio ------


def test_la_precarga_evita_repetir_tras_un_reinicio():
    """Sin esto, con `--reload` puesto cada cambio de código repetiría las alertas."""
    s = Silencio()
    s.precargar({"k": MOMENTO})

    assert s.permite("k", MOMENTO + timedelta(seconds=5), UN_MINUTO) is False


def test_la_precarga_no_pisa_algo_mas_nuevo_que_ya_esta_en_memoria():
    s = Silencio()
    s.anotar("k", MOMENTO + timedelta(minutes=10))
    s.precargar({"k": MOMENTO})

    # Si la precarga hubiera pisado, a los 5 s del MOMENTO viejo ya dejaría emitir.
    assert s.permite("k", MOMENTO + timedelta(seconds=5), UN_MINUTO) is False


def test_la_precarga_informa_cuantas_cargo():
    assert Silencio().precargar({"a": MOMENTO, "b": MOMENTO}) == 2


# -- Que la memoria no crezca para siempre -------------------------------------


def test_olvida_las_claves_viejas():
    s = Silencio()
    s.anotar("vieja", MOMENTO - VENTANA_DE_OLVIDO - timedelta(minutes=1))
    s.anotar("nueva", MOMENTO)

    assert s.olvidar_viejas(MOMENTO) == 1
    assert s.resumen()["claves_recordadas"] == 1


def test_no_olvida_lo_que_todavia_podria_estar_silenciado():
    """La ventana de olvido tiene que ser más larga que cualquier silencio razonable:
    olvidar antes de tiempo es permitir el repetido que estamos evitando."""
    s = Silencio()
    s.anotar("reciente", MOMENTO - VENTANA_DE_OLVIDO + timedelta(minutes=1))

    assert s.olvidar_viejas(MOMENTO) == 0
