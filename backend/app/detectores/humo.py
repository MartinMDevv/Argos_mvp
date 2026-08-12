"""Detectores de humo: no detectan nada útil, prueban que la cañería anda (paso 3.1).

## ⚠️ Este archivo se borra en el paso 3.2
Son andamios. Existen porque el framework del 3.1 no tiene todavía ningún detector real
que lo recorra, y un framework que nunca se ejecutó es un framework que no sabemos si
funciona. Apenas el umbral de precio (3.2) ocupe su lugar, este archivo se elimina.

Hay dos, uno por cadencia, porque las dos rutas del motor son código distinto y hay que
ver andar a las dos:

- `humo_tick` prueba la ruta rápida: que la ingesta llame al motor con cada operación y
  que el antirruido corte la catarata (entran unas 40 operaciones por segundo y sale
  **una alerta por minuto**; ese cociente es la demostración de que el silencio sirve).
- `humo_vela` prueba la ruta lenta: que se detecte el cierre de vela, que la historia
  llegue cargada al contexto y que `velas_necesarias` se respete.

Su severidad es siempre `info` y su detalle dice lo que son, para que nadie confunda un
andamio con una señal de mercado.
"""

from datetime import timedelta

from app.detectores.base import Cadencia, ContextoDeEvaluacion, Detector
from app.detectores.registro import registrar
from app.modelos import Alerta


@registrar
class HumoDelTick(Detector):
    """Emite con el precio vivo, como mucho una vez por minuto y por símbolo."""

    nombre = "humo_tick"
    titulo = "Humo · ruta rápida"
    descripcion = (
        "Andamio del paso 3.1: confirma que la ingesta alimenta al motor tick a tick. "
        "Se borra en 3.2."
    )
    cadencia = Cadencia.POR_TICK
    velas_necesarias = 0
    silencio = timedelta(minutes=1)

    def evaluar(self, contexto: ContextoDeEvaluacion) -> Alerta | None:
        if contexto.tick is None:
            return None  # sin precio no se opina, ni siquiera de mentira

        tick = contexto.tick

        return self.alerta(
            contexto,
            severidad="info",
            detalle=(
                f"La ruta rápida está viva: {contexto.simbolo} cotiza {tick.precio} "
                f"(operación {tick.id_operacion})."
            ),
            evidencia={
                "precio": str(tick.precio),
                "cantidad": str(tick.cantidad),
                "id_operacion": str(tick.id_operacion),
                "momento_del_tick": tick.momento.isoformat(),
                "lado_agresor": tick.lado_agresor,
            },
        )


@registrar
class HumoDeLaVela(Detector):
    """Emite una vez por cada vela de 1m que cierra, con lo que vio en el tramo."""

    nombre = "humo_vela"
    titulo = "Humo · ruta lenta"
    descripcion = (
        "Andamio del paso 3.1: confirma que se detecta el cierre de vela y que la "
        "historia llega cargada al contexto. Se borra en 3.2."
    )
    cadencia = Cadencia.POR_VELA_CERRADA
    intervalo = "1m"
    velas_necesarias = 3

    # Cero: el motor ya garantiza una evaluación por vela cerrada, así que no hay nada
    # que silenciar. Sirve además para probar que una ventana de cero no bloquea.
    silencio = timedelta(0)

    def evaluar(self, contexto: ContextoDeEvaluacion) -> Alerta | None:
        vela = contexto.ultima_cerrada
        if vela is None:
            return None

        cerradas = contexto.velas_cerradas

        return self.alerta(
            contexto,
            severidad="info",
            detalle=(
                f"Cerró la vela de {contexto.intervalo} de {contexto.simbolo} en "
                f"{vela.cierre} ({vela.variacion:+.2f}% en el tramo), con "
                f"{len(cerradas)} velas cerradas de contexto."
            ),
            evidencia={
                "inicio_vela": vela.inicio.isoformat(),
                "apertura": str(vela.apertura),
                "cierre": str(vela.cierre),
                "maximo": str(vela.maximo),
                "minimo": str(vela.minimo),
                "volumen": str(vela.volumen),
                "operaciones": str(vela.operaciones),
                "fuente": vela.fuente,
                "velas_cerradas_en_contexto": str(len(cerradas)),
                "precio_vivo": str(contexto.precio) if contexto.precio is not None else "—",
                "origen_precio": contexto.origen_precio or "—",
            },
        )
