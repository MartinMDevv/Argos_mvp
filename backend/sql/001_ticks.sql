-- 001_ticks.sql — Donde viven las operaciones del mercado (paso 1.2)
--
-- Este archivo se aplica solo al arrancar el backend y es IDEMPOTENTE: todo es
-- "IF NOT EXISTS", así que correrlo mil veces da el mismo resultado que correrlo una.

-- ---------------------------------------------------------------------------
-- Tabla de ticks
-- ---------------------------------------------------------------------------
-- Ojo con lo que NO tiene: no hay una columna "id SERIAL PRIMARY KEY".
-- En una tabla de series temporales eso sería un lastre: un índice gigante que
-- crece con cada fila y que nunca vamos a consultar. Acá el eje es el TIEMPO;
-- no nos interesa "el tick número 8.472.913", nos interesa "los ticks de BTC
-- de los últimos 5 minutos".
CREATE TABLE IF NOT EXISTS ticks (
    momento          TIMESTAMPTZ     NOT NULL,  -- cuándo pasó, EN EL EXCHANGE, en UTC
    simbolo          TEXT            NOT NULL,  -- "BTCUSDT"
    -- NUMERIC y no DOUBLE PRECISION: los decimales binarios (float) no pueden
    -- representar exacto 0.1, y con dinero eso no se negocia. asyncpg convierte
    -- NUMERIC <-> Decimal de Python solo, así que la precisión viaja intacta
    -- desde Binance hasta el disco.
    precio           NUMERIC(20, 8)  NOT NULL,
    cantidad         NUMERIC(30, 12) NOT NULL,
    id_operacion     BIGINT          NOT NULL,  -- id del exchange; sirve para no duplicar
    comprador_pasivo BOOLEAN         NOT NULL   -- true = la operación la empujó el vendedor
);

-- ---------------------------------------------------------------------------
-- Convertirla en hypertable (esto es lo que hace TimescaleDB)
-- ---------------------------------------------------------------------------
-- Por fuera se sigue usando como una tabla normal (SELECT, INSERT, todo igual).
-- Por dentro, Timescale la parte en trozos ("chunks") por rango de tiempo. Cuando
-- preguntes por la última hora, el motor toca un solo trozo en vez de escanear
-- millones de filas viejas. Es la diferencia entre que Argos responda al instante
-- o se arrastre cuando tenga meses de historia encima.
SELECT create_hypertable(
    'ticks',
    by_range('momento'),
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- Índices
-- ---------------------------------------------------------------------------
-- 1) Anti-duplicados. Hace falta de verdad: cuando el WebSocket se reconecta
--    podemos recibir de nuevo operaciones que ya guardamos, y un tick contado
--    dos veces le mentiría a los detectores de volumen. Con este índice único,
--    el "ON CONFLICT DO NOTHING" del INSERT los descarta sin hacer ruido.
--    Incluye `momento` porque Timescale exige que todo índice único contenga la
--    columna por la que particiona.
CREATE UNIQUE INDEX IF NOT EXISTS ticks_sin_duplicados
    ON ticks (simbolo, id_operacion, momento);

-- 2) La consulta que Argos va a hacer todo el tiempo: "dame los últimos ticks de
--    tal símbolo". DESC porque siempre se pide lo más reciente primero.
CREATE INDEX IF NOT EXISTS ticks_por_simbolo_y_momento
    ON ticks (simbolo, momento DESC);

-- Fase futura (no ahora): compresión automática de trozos viejos y política de
-- retención. Timescale las trae de fábrica; se activan cuando haya historia real
-- que comprimir y sepamos cuánta queremos guardar.
