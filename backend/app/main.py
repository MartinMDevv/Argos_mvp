"""Punto de entrada de la API de Argos (FastAPI).

Signos vitales:
    GET /health           → ¿está viva la API?           (no toca la base de datos)
    GET /health/db        → ¿la API llega a la BD?       (hace una consulta real)

Mercado:
    GET  /mercado/estado  → último precio de cada símbolo + salud de la ingesta   (paso 1.2)
    GET  /mercado/velas   → velas OHLCV para dibujar el gráfico                   (paso 1.3)
    GET  /mercado/resumen → precio + cambio % (1h/24h/7d) + máx/mín/volumen 24h   (paso 2.2)
    WS   /ws/mercado      → el backend EMPUJA los precios en vivo                 (paso 1.4)
                            …y las alertas en cuanto se emiten                    (paso 4.2)

Alertas:
    GET    /detectores    → qué vigila Argos y con qué cadencia                   (paso 3.1)
    GET    /alertas       → lo que Argos vio, de lo más nuevo a lo más viejo      (paso 3.1)
    GET    /umbrales      → los precios que pediste vigilar                       (paso 3.2)
    POST   /umbrales      → agregar uno                                           (paso 3.2)
    DELETE /umbrales/{id} → sacar uno                                             (paso 3.2)

Desde el paso 1.2, al arrancar la API se encienden tareas de fondo que corren para siempre:
escuchar Binance, guardar en TimescaleDB, difundir a los paneles conectados (1.4) y, desde
el 3.1, evaluar los detectores y guardar las alertas que emitan.

Y una que sí termina: al encender, Argos le pide a Binance los minutos que se perdió
mientras estuvo apagado, para que el gráfico se vea completo desde el primer momento sin
tener que acordarse de correr el backfill a mano (`BACKFILL_AL_ARRANCAR=false` lo apaga).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Path, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import obtener_settings
from app.db import abrir_pool, cerrar_pool, revisar_conexion
from app.detectores import almacen as almacen_de_alertas
from app.detectores import registro as registro_de_detectores
from app.detectores import umbrales as config_umbrales
from app.detectores.motor import MotorDeDetectores
from app.detectores.volumen import CLAVE_PERFIL
from app.difusion import ColaDeAlertas, GestorDeConexiones, emitir_alertas, emitir_estado
from app.esquema import aplicar_esquema
from app.estado import EstadoMercado
from app.ingesta.almacen import EscritorDeTicks
from app.ingesta.backfill import ponerse_al_dia
from app.ingesta.binance import SIMBOLOS_MVP, escuchar_ticks
from app.modelos import Tick
from app import perfiles
from app.resumen import PLAZOS, obtener_resumen, resumen_a_json
from app.velas import LIMITE_MAXIMO, obtener_velas, vela_a_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado vivo del proceso. Se arma en el `lifespan` y lo leen los endpoints.
estado_mercado = EstadoMercado()
escritor_de_ticks = EscritorDeTicks()
gestor_de_paneles = GestorDeConexiones()
cola_de_alertas = ColaDeAlertas()

# Los detectores se descubren al importar este módulo: cada archivo de `app/detectores/`
# se importa y sus clases decoradas con `@registrar` quedan en el catálogo. Si alguno
# está mal definido, revienta acá — al arrancar, con un mensaje claro — y no a las tres
# de la mañana dejando de emitir una alerta en silencio.
registro_de_detectores.descubrir()


def _extras_del_contexto(simbolo: str, intervalo: str) -> dict[str, object]:
    """Datos que un detector necesita y no salen de las velas (paso 3.5).

    Acá se junta lo que el motor le va a repartir a los detectores en `contexto.extras`.
    Es este archivo el que lo hace —y no el motor ni el detector— porque es el único que
    tiene por qué conocer a los dos: el motor sigue siendo genérico y el detector sigue
    siendo puro, que es lo que le permite rebobinarse sobre el pasado.

    Se lee en cada evaluación a propósito: el perfil se recalcula cada hora y guardarlo
    una sola vez lo dejaría clavado en el del arranque.
    """
    return {CLAVE_PERFIL: perfiles.CATALOGO.de(simbolo)}


motor_de_alertas = MotorDeDetectores(
    estado=estado_mercado,
    detectores=registro_de_detectores.crear(),
    simbolos=SIMBOLOS_MVP,
    extras=_extras_del_contexto,
    # Cada alerta que pasa el antirruido se deja en la cola de difusión para que el panel
    # se entere en el momento (paso 4.2). Guardar en la base sigue su propio camino: son
    # dos cosas distintas y ninguna debe esperar a la otra.
    al_emitir=lambda alerta: cola_de_alertas.encolar(almacen_de_alertas.alerta_a_json(alerta)),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida: qué pasa al encender y al apagar la app.

    Todo lo que está ANTES del `yield` corre al arrancar; lo de DESPUÉS, al parar.
    """
    settings = obtener_settings()

    # --- Arranque ---
    try:
        await abrir_pool()
        await aplicar_esquema()
    except Exception as error:
        # A propósito NO reventamos: si Docker está apagado queremos que la API igual
        # levante y lo diga en /health/db, en vez de negarse a arrancar. La ingesta
        # tampoco se detiene: los ticks esperan en memoria hasta que vuelva la base.
        logger.warning("Base de datos no disponible al arrancar: %s", error)

    tareas: list[asyncio.Task[None]] = []

    # Lo primero que se lanza: completar la historia que falte desde el último apagado.
    # Va en tarea de fondo y no bloqueando el arranque, porque en una base vacía esto
    # baja un año y nadie quiere esperar a que termine para ver el panel. Mientras baja,
    # la ingesta en vivo ya está guardando el presente.
    if settings.backfill_al_arrancar:
        tareas.append(
            asyncio.create_task(
                ponerse_al_dia(list(SIMBOLOS_MVP), dias=settings.backfill_dias),
                name="backfill-arranque",
            )
        )
    else:
        logger.info("Puesta al día de la historia desactivada (BACKFILL_AL_ARRANCAR=false)")

    if settings.ingesta_activa:

        async def consumir(tick: Tick) -> None:
            """Qué hacemos con cada operación que llega del mercado.

            Tres destinos, a propósito separados: la memoria guarda el AHORA (para responder
            al instante), la base guarda la HISTORIA (para tener con qué comparar) y los
            detectores miran el tick por si hay algo que contar (paso 3.1).

            Las tres son instantáneas: ninguna espera al disco ni a la red. Encolar y
            comparar en memoria es todo lo que se hace acá, porque este consumidor está
            en la ruta caliente del WebSocket y atrasarlo atrasa la ingesta entera.
            """
            estado_mercado.actualizar(tick)
            escritor_de_ticks.encolar(tick)

            if settings.deteccion_activa:
                motor_de_alertas.revisar_tick(tick)

        tareas.append(asyncio.create_task(escuchar_ticks(consumir), name="ingesta-binance"))
        tareas.append(asyncio.create_task(escritor_de_ticks.correr(), name="escritor-ticks"))
    else:
        logger.info("Ingesta desactivada (INGESTA_ACTIVA=false)")

    # Las dos tareas de fondo de la detección: la que mira los cierres de vela y la que
    # va guardando las alertas emitidas. La ruta rápida no necesita tarea propia porque
    # cuelga del consumidor de la ingesta, ahí arriba.
    if settings.deteccion_activa:
        tareas.append(
            asyncio.create_task(motor_de_alertas.vigilar_velas(), name="detectores-velas")
        )
        tareas.append(
            asyncio.create_task(motor_de_alertas.despachar(), name="detectores-despacho")
        )
        # Trae los umbrales configurados a memoria y los mantiene al día. Es una tarea
        # aparte porque tiene que sobrevivir a que la base esté caída al arrancar: si
        # no se cargan, la alerta de umbral no vigila nada y eso no se nota solo.
        tareas.append(
            asyncio.create_task(config_umbrales.mantener_al_dia(), name="umbrales-recarga")
        )
        # El perfil intradía de volumen que necesita la alerta #4: cuánto se opera
        # normalmente a cada hora del día. Tarea aparte por lo mismo que los umbrales —
        # si la base está caída al arrancar, un cálculo único dejaría a esa alerta sin
        # poder opinar el resto de la sesión, y eso no se nota desde afuera.
        tareas.append(
            asyncio.create_task(
                perfiles.mantener_al_dia(list(SIMBOLOS_MVP)), name="perfil-volumen"
            )
        )
    else:
        logger.info("Detección desactivada (DETECCION_ACTIVA=false)")

    # La difusión se enciende igual, haya ingesta o no: si no hay novedades simplemente no
    # manda nada, y así un panel conectado no se queda esperando un socket que nunca abrió.
    tareas.append(
        asyncio.create_task(
            emitir_estado(gestor_de_paneles, estado_mercado), name="difusion-paneles"
        )
    )
    # Las alertas van por el mismo socket pero en su propia tarea: el estado es una foto que
    # se puede saltear y una alerta es un hecho que no.
    tareas.append(
        asyncio.create_task(
            emitir_alertas(gestor_de_paneles, cola_de_alertas), name="difusion-alertas"
        )
    )

    yield

    # --- Apagado ---
    for tarea in tareas:
        tarea.cancel()
    await asyncio.gather(*tareas, return_exceptions=True)

    # Último volcado: lo que quedó en la cola se guarda antes de cerrar el pool.
    # Va después de cancelar las tareas para que nadie siga encolando mientras escribimos.
    if settings.ingesta_activa:
        try:
            guardados = await escritor_de_ticks.volcar()
            if guardados:
                logger.info("Volcado final: %d ticks guardados antes de cerrar", guardados)
        except Exception as error:
            logger.warning("No se pudo hacer el volcado final: %s", error)

    if settings.deteccion_activa:
        try:
            alertas_guardadas = await motor_de_alertas.volcar()
            if alertas_guardadas:
                logger.info(
                    "Volcado final: %d alertas guardadas antes de cerrar", alertas_guardadas
                )
        except Exception as error:
            logger.warning("No se pudo guardar las alertas pendientes: %s", error)

    await cerrar_pool()


app = FastAPI(title="Argos API", version="0.3.0", lifespan=lifespan)

# El navegador bloquea los pedidos entre orígenes distintos salvo que el servidor los autorice,
# y el frontend vive en otro puerto (5173) que la API (8000). Sin esto, el panel recibiría un
# error de CORS al pedir /mercado/velas. Se listan solo los orígenes de desarrollo: cuando haya
# un dominio real, se agrega acá (nunca "*", que abriría la API a cualquier página).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    # POST y DELETE desde el paso 3.2: el panel tiene que poder crear y borrar umbrales.
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Confirma que la API está viva y respondiendo."""
    return {"status": "ok", "service": "argos-backend"}


@app.get("/health/db")
async def health_db() -> JSONResponse:
    """Confirma que la API le llega de verdad a TimescaleDB.

    Devuelve 200 con las versiones si la conexión anda, o 503 con un mensaje claro
    (no un stacktrace) si la base de datos no está disponible.
    """
    try:
        versiones = await revisar_conexion()
    except Exception as error:
        logger.warning("Falló la revisión de la base de datos: %s", error)
        return JSONResponse(
            status_code=503,
            content={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "Enciende Docker (docker-on) y levanta infra: docker compose up -d --wait",
            },
        )

    return JSONResponse(
        content={
            "status": "ok",
            "base_de_datos": "timescaledb",
            "versiones": versiones,
        }
    )


@app.get("/mercado/estado")
def mercado_estado() -> dict[str, object]:
    """Foto del mercado ahora mismo, respondida desde memoria (no toca la base de datos).

    `simbolos` está vacío hasta que entre el primer tick: si todavía no sabemos el precio,
    lo decimos, no lo inventamos.

    `persistencia` es el pulso del escritor: `guardados` tiene que subir, `en_espera` tiene
    que mantenerse bajo. Si `en_espera` crece sin parar, la base de datos no está recibiendo.
    """
    return {
        "desde": estado_mercado.desde.isoformat(),
        "simbolos": estado_mercado.instantanea(),
        "persistencia": escritor_de_ticks.resumen(),
    }


@app.get("/mercado/velas")
async def mercado_velas(
    simbolo: str = Query(
        description=f"Par a consultar. El MVP vigila solo: {', '.join(SIMBOLOS_MVP)}.",
    ),
    intervalo: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Query(
        default="1m",
        description="Duración de cada vela.",
    ),
    limite: int = Query(
        default=200,
        ge=1,
        le=LIMITE_MAXIMO,
        description="Cuántas velas devolver, contando desde la más reciente hacia atrás.",
    ),
    desde: datetime | None = Query(
        default=None,
        description="Opcional: ignorar los ticks anteriores a este momento (ISO 8601).",
    ),
) -> JSONResponse:
    """Velas OHLCV armadas sobre los ticks guardados, en orden cronológico.

    **Ojo con la última vela**: viene con `completa: false` porque su tramo todavía no
    terminó. Sus valores van a seguir cambiando hasta que cierre el minuto (o la hora).

    **Ojo con la historia**: Argos solo tiene lo que vio desde que lo encendiste por primera
    vez. No hay velas de antes de eso, y no las inventamos. Traer historia vieja de Binance
    es un paso posterior.
    """
    # Lo validamos a mano contra la lista del MVP para poder responder con un mensaje útil
    # en vez de devolver una lista vacía que parezca "no hubo operaciones".
    if simbolo not in SIMBOLOS_MVP:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "simbolo_no_vigilado",
                "detalle": f"Argos todavía no vigila '{simbolo}'.",
                "disponibles": list(SIMBOLOS_MVP),
            },
        )

    try:
        velas = await obtener_velas(simbolo, intervalo, limite, desde)
    except Exception as error:
        logger.warning("No se pudieron armar las velas: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Prueba GET /health/db",
            },
        ) from error

    return JSONResponse(
        content={
            "simbolo": simbolo,
            "intervalo": intervalo,
            "cantidad": len(velas),
            "velas": [vela_a_json(vela) for vela in velas],
        }
    )


@app.get("/mercado/resumen")
async def mercado_resumen(
    simbolos: list[str] | None = Query(
        default=None,
        description=(
            "Pares a resumir, repetible (?simbolos=BTCUSDT&simbolos=ETHUSDT). "
            f"Si se omite, se devuelven todos los vigilados: {', '.join(SIMBOLOS_MVP)}."
        ),
    ),
) -> JSONResponse:
    """Ficha de cada activo: a cuánto está y cómo viene. Es lo que llena la watchlist.

    Para cada símbolo: el precio de ahora, la variación contra hace 1 h / 24 h / 7 d, y
    el techo, el piso y el volumen del día.

    **Tres campos que conviene mirar antes de creerle a los números:**

    - `momento` — de cuándo es el precio. Si Argos estuvo apagado, es viejo, y el
      resumen lo dice en vez de disimularlo.
    - `cambios.<plazo>` en `null` — no había con qué comparar (falta historia de ese
      tramo, o la que hay quedó demasiado lejos del plazo pedido). Es un "no sé", no un
      cero: rellenarlo sería inventar. Si pasa en `7d` recién estrenado, corre el
      backfill: `uv run python -m app.ingesta.backfill --dias 365`.
    - `minutos_24h` — cuántos de los 1.440 minutos del día tienen datos. Con 1.440 el
      volumen es el real; con 300, es el volumen de 300 minutos y nada más.

    Un símbolo del que no hay ningún dato **no aparece** en la respuesta.
    """
    pedidos = list(SIMBOLOS_MVP) if not simbolos else simbolos

    desconocidos = [simbolo for simbolo in pedidos if simbolo not in SIMBOLOS_MVP]
    if desconocidos:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "simbolo_no_vigilado",
                "detalle": f"Argos todavía no vigila: {', '.join(desconocidos)}.",
                "disponibles": list(SIMBOLOS_MVP),
            },
        )

    # El precio del instante sale de memoria; la historia con qué compararlo, de la base.
    # Se los pasamos juntos para que el ancla de los plazos sea el dato más nuevo de las
    # dos fuentes (ver el docstring de resumen.py: es el detalle que evita mostrar un
    # cambio de tres días con la etiqueta "24h").
    ticks_vivos = {
        simbolo: tick
        for simbolo in pedidos
        if (tick := estado_mercado.ultimo(simbolo)) is not None
    }

    try:
        resumenes = await obtener_resumen(pedidos, ticks_vivos)
    except Exception as error:
        logger.warning("No se pudo armar el resumen de mercado: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Prueba GET /health/db",
            },
        ) from error

    return JSONResponse(
        content={
            "plazos": list(PLAZOS),
            "simbolos": {
                simbolo: resumen_a_json(resumen) for simbolo, resumen in resumenes.items()
            },
        }
    )


@app.get("/detectores")
def listar_detectores() -> dict[str, object]:
    """Qué vigila Argos ahora mismo, y con qué cadencia (paso 3.1).

    Es el catálogo de plugins registrados: si escribiste un detector nuevo en
    `app/detectores/` y no aparece acá, es que no se registró (¿le falta el decorador
    `@registrar`?). `motor` es el pulso del sistema de detección:

    - `emitidas` — cuántas alertas se dispararon desde que arrancó el proceso.
    - `silenciadas` — cuántas eran correctas pero repetían algo ya dicho. Es el
      antirruido trabajando; que sea alto no es un problema, es el punto.
    - `en_espera` — alertas emitidas que todavía no llegaron al disco. Debería ser 0
      casi siempre; si crece, la base no está recibiendo.
    - `fallos_de_detector` — un detector que reventó al evaluar. Cualquier número
      distinto de 0 acá merece una mirada al log.
    """
    return {
        "activa": obtener_settings().deteccion_activa,
        "detectores": [
            registro_de_detectores.ficha(clase)
            for clase in registro_de_detectores.catalogo().values()
        ],
        "motor": motor_de_alertas.resumen(),
    }


@app.get("/alertas")
async def listar_alertas(
    limite: int = Query(default=50, ge=1, le=500, description="Cuántas devolver."),
    simbolo: str | None = Query(default=None, description="Filtrar por par."),
    detector: str | None = Query(default=None, description="Filtrar por detector."),
) -> JSONResponse:
    """Lo que Argos vio, de lo más nuevo a lo más viejo (paso 3.1).

    Cada alerta viaja con su `evidencia`: los números crudos con los que el detector
    llegó a esa conclusión. Está para que puedas rehacer la cuenta — la regla de oro
    del proyecto es que Argos no afirma nada que no se pueda verificar.

    Ojo con `severidad`: mide qué tan notable es el hallazgo para el detector que lo
    emitió, no si conviene comprar o vender. Argos informa; decides tú.
    """
    if simbolo is not None and simbolo not in SIMBOLOS_MVP:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "simbolo_no_vigilado",
                "detalle": f"Argos todavía no vigila '{simbolo}'.",
                "disponibles": list(SIMBOLOS_MVP),
            },
        )

    if detector is not None and detector not in registro_de_detectores.catalogo():
        raise HTTPException(
            status_code=400,
            detail={
                "status": "detector_desconocido",
                "detalle": f"No hay ningún detector llamado '{detector}'.",
                "disponibles": sorted(registro_de_detectores.catalogo()),
            },
        )

    try:
        alertas = await almacen_de_alertas.ultimas(limite, simbolo, detector)
    except Exception as error:
        logger.warning("No se pudieron leer las alertas: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Prueba GET /health/db",
            },
        ) from error

    return JSONResponse(
        content={
            "cantidad": len(alertas),
            "alertas": [almacen_de_alertas.alerta_a_json(alerta) for alerta in alertas],
        }
    )


class UmbralNuevo(BaseModel):
    """El cuerpo de `POST /umbrales`."""

    simbolo: str = Field(description="Par a vigilar. Ej: BTCUSDT.")
    valor: Decimal = Field(gt=0, description="El precio que marca la línea.")
    direccion: Literal["arriba", "abajo"] = Field(
        description="`arriba` = avisar al cruzar subiendo; `abajo`, bajando."
    )
    nota: str | None = Field(
        default=None, max_length=200, description="Para qué lo pusiste, en tus palabras."
    )


@app.get("/umbrales")
def listar_umbrales() -> dict[str, object]:
    """Los precios que pediste vigilar (paso 3.2).

    Se responde **desde memoria**, que es la misma copia que mira el detector con cada
    operación: si algo aparece acá, está siendo vigilado de verdad.

    Mira `cargado_alguna_vez`: si es `false`, Argos todavía no pudo leer la tabla (la
    base estaba caída al arrancar) y la lista vacía **no significa que no haya
    umbrales**, significa que no sabemos. Se reintenta cada minuto.
    """
    catalogo = config_umbrales.CATALOGO

    return {
        "umbrales": [config_umbrales.umbral_a_json(u) for u in catalogo.todos()],
        **catalogo.resumen(),
    }


@app.post("/umbrales", status_code=201)
async def crear_umbral(nuevo: UmbralNuevo = Body()) -> dict[str, object]:
    """Agrega un umbral. Empieza a vigilarse en la operación siguiente (paso 3.2).

    **Ojo con lo que NO hace:** si el precio ya está del otro lado de la línea cuando lo
    creas, no vas a recibir un aviso inmediato. El detector avisa cuando ve **cruzar**, y
    encontrar el precio ya cruzado no es haberlo visto cruzar. Vas a recibir el aviso la
    próxima vez que la cruce de verdad.
    """
    if nuevo.simbolo not in SIMBOLOS_MVP:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "simbolo_no_vigilado",
                "detalle": f"Argos todavía no vigila '{nuevo.simbolo}'.",
                "disponibles": list(SIMBOLOS_MVP),
            },
        )

    catalogo = config_umbrales.CATALOGO
    if not config_umbrales.sin_duplicado(
        catalogo.todos(), nuevo.simbolo, nuevo.valor, nuevo.direccion
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "status": "umbral_repetido",
                "detalle": (
                    f"Ya hay un umbral de {nuevo.simbolo} en {nuevo.valor} "
                    f"hacia {nuevo.direccion}."
                ),
            },
        )

    try:
        umbral = await config_umbrales.crear(
            nuevo.simbolo, nuevo.valor, nuevo.direccion, nuevo.nota
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"detalle": str(error)}) from error
    except Exception as error:
        logger.warning("No se pudo crear el umbral: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Prueba GET /health/db",
            },
        ) from error

    return config_umbrales.umbral_a_json(umbral)


@app.delete("/umbrales/{id_umbral}", status_code=204)
async def borrar_umbral(id_umbral: int = Path(ge=1)) -> None:
    """Deja de vigilar un precio (paso 3.2)."""
    try:
        existia = await config_umbrales.borrar(id_umbral)
    except Exception as error:
        logger.warning("No se pudo borrar el umbral %d: %s", id_umbral, error)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "sin_conexion",
                "detalle": str(error),
                "pista": "¿Está levantada la base? Prueba GET /health/db",
            },
        ) from error

    if not existia:
        raise HTTPException(
            status_code=404,
            detail={"status": "no_existe", "detalle": f"No hay ningún umbral con id {id_umbral}."},
        )


@app.websocket("/ws/mercado")
async def ws_mercado(websocket: WebSocket) -> None:
    """Canal en vivo: el panel se conecta una vez y Argos le va empujando los precios.

    Mensajes que manda el servidor (mirar siempre el campo `tipo`):

        {"tipo": "bienvenida", "momento": ..., "simbolos": {...}}  ← al conectarse
        {"tipo": "estado",     "momento": ..., "simbolos": {...}}  ← cuando algo cambió
        {"tipo": "latido",     "momento": ...}                     ← "sigo acá", sin novedades

    El cliente no necesita mandar nada. Si manda, se ignora.
    """
    await gestor_de_paneles.conectar(websocket, estado_mercado)

    try:
        # No esperamos mensajes del panel, pero hay que quedarse leyendo igual: es la forma de
        # enterarse de que cerró la conexión. Sin este `receive`, un panel que se va quedaría
        # en la lista para siempre y le seguiríamos escribiendo al vacío.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as error:
        logger.debug("Conexión de panel terminada con error: %s", error)
    finally:
        gestor_de_paneles.desconectar(websocket)
