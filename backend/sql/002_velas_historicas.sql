-- 002_velas_historicas.sql — La historia que Argos NO vivió (paso 2.1b)
--
-- Idempotente como el 001: todo es "IF NOT EXISTS", se aplica en cada arranque.

-- ---------------------------------------------------------------------------
-- Por qué esta tabla existe y no metemos esto en `ticks`
-- ---------------------------------------------------------------------------
-- Argos solo tiene lo que vio: antes de su primer arranque no hay nada, y cada
-- vez que se apaga queda un hueco. En el gráfico eso se ve como un salto en el
-- eje de tiempo, y para los detectores de la Fase 3 es peor: sin historia no hay
-- forma de saber qué es "raro".
--
-- La solución es traer las velas oficiales de Binance (`/api/v3/klines`), que son
-- exactamente los minutos que nos perdimos, del mismo exchange que ya escuchamos.
--
-- Pero **una vela NO es un tick**. La tabla `ticks` guarda operaciones individuales
-- reales; una kline ya viene resumida por Binance. Meterlas ahí obligaría a
-- inventar operaciones que nunca vimos —precios, cantidades e ids falsos— y eso
-- envenenaría a los detectores de volumen, que cuentan operaciones. Por eso van
-- acá, separadas y sin disfraz: son otra cosa y se guardan como otra cosa.

-- ---------------------------------------------------------------------------
-- Siempre a resolución de UN MINUTO
-- ---------------------------------------------------------------------------
-- No se guarda 5m, 15m, 1h ni 1d: se descarga solo el minuto y el resto se calcula
-- agregando con `time_bucket`, igual que hacemos con los ticks. Guardar cada
-- intervalo por separado sería seis veces más disco y seis veces más para
-- desincronizarse.
CREATE TABLE IF NOT EXISTS velas_historicas (
    inicio           TIMESTAMPTZ     NOT NULL,  -- comienzo del minuto, en UTC
    simbolo          TEXT            NOT NULL,
    -- Mismos tipos que en `ticks`: NUMERIC y no float. Binance manda los precios
    -- como texto justamente para que no se degraden, y así llegan al disco.
    apertura         NUMERIC(20, 8)  NOT NULL,
    maximo           NUMERIC(20, 8)  NOT NULL,
    minimo           NUMERIC(20, 8)  NOT NULL,
    cierre           NUMERIC(20, 8)  NOT NULL,
    volumen          NUMERIC(30, 12) NOT NULL,  -- en la moneda base (ej. BTC)
    volumen_cotizado NUMERIC(30, 12) NOT NULL,  -- en la moneda de cotización (ej. USDT)
    -- OJO: acá `operaciones` son las operaciones REALES que contó Binance. En las
    -- velas que armamos nosotros son `aggTrade` (operaciones agrupadas), que
    -- siempre son menos. Los dos números son correctos pero NO son comparables
    -- entre sí; está documentado en velas.py y en ARQUITECTURA.md.
    operaciones      INT             NOT NULL
);

-- Hypertable por el mismo motivo que `ticks`: las consultas son siempre por rango
-- de tiempo, y así Timescale toca solo los trozos que hacen falta.
SELECT create_hypertable(
    'velas_historicas',
    by_range('inicio'),
    if_not_exists => TRUE
);

-- Anti-duplicados + la consulta de siempre ("las velas de tal símbolo, tal rango"),
-- en un solo índice. Permite además reejecutar la descarga sin miedo: lo que ya
-- está se descarta con ON CONFLICT DO NOTHING.
-- Incluye `inicio` porque Timescale exige que todo índice único contenga la
-- columna por la que particiona.
CREATE UNIQUE INDEX IF NOT EXISTS velas_historicas_sin_duplicados
    ON velas_historicas (simbolo, inicio);
