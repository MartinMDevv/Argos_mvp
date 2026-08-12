-- 003_alertas.sql — Lo que Argos vio y decidió contar (paso 3.1)
--
-- Idempotente como los anteriores: todo es "IF NOT EXISTS", se aplica en cada arranque.

-- ---------------------------------------------------------------------------
-- Por qué las alertas se guardan y no solo se avisan
-- ---------------------------------------------------------------------------
-- Una alerta que se manda por Telegram y se olvida sirve una sola vez. Guardarla
-- compra tres cosas que el proyecto ya tiene anotadas en el norte:
--
--   1. El panel (paso 3.6) necesita mostrar "lo que Argos vio" también después de
--      un reinicio; hoy ese bloque del panel está escrito a mano en el frontend.
--   2. El silencio antirruido se puede reconstruir al arrancar: sin esto, un
--      reinicio repetiría una alerta que ya se mandó hace treinta segundos.
--   3. La v1.2 ("memoria de predicciones") tiene que poder volver sobre cada
--      alerta y anotar qué pasó después. Sin registro no hay base rates, y sin
--      base rates la v2.0 no existe.
--
-- ---------------------------------------------------------------------------
-- A propósito NO es una hypertable
-- ---------------------------------------------------------------------------
-- `ticks` y `velas_historicas` sí lo son porque son millones de filas y siempre
-- se consultan por rango de tiempo. Las alertas son lo contrario por diseño: la
-- regla del proyecto es "bajo ruido sobre volumen de alertas", así que si algún
-- día esta tabla necesita particionarse por tiempo, el problema no es la tabla —
-- es que Argos se volvió el ruido del que quería protegerte.
CREATE TABLE IF NOT EXISTS alertas (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    momento   TIMESTAMPTZ NOT NULL,  -- cuándo la emitió el detector, en UTC
    detector  TEXT        NOT NULL,  -- qué plugin la disparó (`Detector.nombre`)
    simbolo   TEXT        NOT NULL,
    severidad TEXT        NOT NULL,  -- 'info' | 'aviso' | 'fuerte'
    titulo    TEXT        NOT NULL,  -- el encabezado corto: "Volumen anómalo"
    detalle   TEXT        NOT NULL,  -- una frase con los números adentro

    -- La evidencia: los números crudos que justifican la alerta (valor medido,
    -- media, desviación, umbral cruzado…). Es la regla de oro hecha columna —
    -- quien lea la alerta puede rehacer la cuenta y verificarla. Va como JSONB
    -- y no como columnas fijas porque cada detector justifica lo suyo con
    -- números distintos, y el día que se enchufe uno nuevo no se toca el esquema.
    --
    -- Los valores van como TEXTO adentro del JSON, igual que en el resto de
    -- Argos: JSON no tiene decimales exactos y un precio guardado como número
    -- volvería a ser un float.
    evidencia JSONB       NOT NULL,

    -- La identidad de la SITUACIÓN, no de la alerta. Dos alertas con la misma
    -- clave cuentan lo mismo ("z-score alto de volumen en BTC"), aunque se
    -- emitan con un minuto de diferencia. Es sobre esto que trabaja el silencio.
    clave     TEXT        NOT NULL
);

-- El feed del panel: "las últimas N alertas", con o sin filtro por símbolo.
CREATE INDEX IF NOT EXISTS alertas_por_momento
    ON alertas (momento DESC);

-- La precarga del silencio al arrancar: "¿cuándo fue la última vez que se dijo
-- esto?". Sin este índice sería un escaneo completo en cada arranque.
CREATE INDEX IF NOT EXISTS alertas_por_clave
    ON alertas (clave, momento DESC);
