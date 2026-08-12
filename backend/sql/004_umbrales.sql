-- 004_umbrales.sql — Los precios que elegiste vigilar (paso 3.2)
--
-- Idempotente como los anteriores: todo es "IF NOT EXISTS", se aplica en cada arranque.

-- ---------------------------------------------------------------------------
-- Por qué una tabla y no un archivo de configuración
-- ---------------------------------------------------------------------------
-- Todo lo demás que Argos guarda viene del mercado. Esto no: viene de una decisión
-- tuya ("avísame si BTC pasa de 70.000"), y es la única parte del sistema que se
-- crea y se borra mientras está corriendo. Un `.env` o un YAML habría que releerlo,
-- no tiene identificadores para poder borrar uno solo, y el panel del paso 3.6 no
-- podría editarlo. Una tabla resuelve las tres cosas.
--
-- No es hypertable, por lo mismo que `alertas`: son unas pocas filas, y particionar
-- por tiempo una tabla que no se consulta por tiempo sería ceremonia.

CREATE TABLE IF NOT EXISTS umbrales (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    simbolo   TEXT           NOT NULL,
    -- Mismo tipo que los precios en `ticks`: NUMERIC, nunca float. Un umbral es un
    -- número con el que se comparan precios exactos; si se degradara a binario, la
    -- comparación del borde ("¿cruzó o no cruzó?") dejaría de ser confiable justo
    -- en el único momento que importa.
    valor     NUMERIC(20, 8) NOT NULL CHECK (valor > 0),
    -- 'arriba' = avisar al cruzar subiendo; 'abajo', bajando. Un umbral vigila UNA
    -- dirección: si quieres las dos, son dos filas, y así cada aviso dice qué pasó
    -- sin que haya que deducirlo. El CHECK está para que un error de tipeo no entre
    -- a la base y deje un umbral que no se dispara nunca.
    direccion TEXT           NOT NULL CHECK (direccion IN ('arriba', 'abajo')),
    nota      TEXT,                    -- para qué lo pusiste, en tus palabras
    creado    TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Sin duplicados: el mismo precio, en el mismo par, en la misma dirección, es el
-- mismo aviso. Dos filas iguales solo servirían para avisarte dos veces de lo mismo,
-- que es justo lo que el proyecto trata de no hacer.
CREATE UNIQUE INDEX IF NOT EXISTS umbrales_sin_duplicados
    ON umbrales (simbolo, valor, direccion);
