import { activoDe } from '@/lib/activos'
import {
  SIN_DATO,
  dineroCorto,
  diferencia,
  direccion,
  entero,
  porcentaje,
  rango,
  medida,
  precio as formatearPrecio,
} from '@/lib/formato'
import { MINUTOS_DEL_DIA, useFicha } from '@/lib/resumen'
import { useVolatilidad } from '@/lib/volatilidad'
import { PriceVolChart } from './PriceVolChart'
import { MarketTable } from './MarketTable'

interface Props {
  par: string
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (par: string) => void
  seleccionar: (par: string) => void
}

/**
 * Vista Mercados: los KPIs del activo seleccionado + precio/volumen + tabla de activos.
 *
 * Cinco KPIs salen de `GET /mercado/resumen` y el de volatilidad de `GET /mercado/volatilidad`
 * (paso 3.7): el rango verdadero mediano de un tramo de 5 minutos en las últimas 24 h, que es la
 * misma medida con la que la alerta #3 decide qué es raro. Hasta que ese detector existió, el
 * KPI mostraba `—`; ponerle mientras tanto un "3,4σ" de adorno habría sido exactamente lo que la
 * regla de oro prohíbe, un número que parece medido y no lo es.
 */
export function MercadosView({ par, order, pinned, togglePin, seleccionar }: Props) {
  const activo = activoDe(par)
  const ficha = useFicha(par)
  const volatilidad = useVolatilidad([par])[par] ?? null

  const cambio24h = ficha?.cambios['24h'] ?? null
  const cambio7d = ficha?.cambios['7d'] ?? null

  const enPlata =
    ficha?.precio != null && ficha.referencia24h != null ? ficha.precio - ficha.referencia24h : null

  // Cuando falta cobertura, el volumen es el de los minutos que hay y no el del día. Se dice.
  const parcial = ficha != null && ficha.minutos24h > 0 && ficha.minutos24h < MINUTOS_DEL_DIA

  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <div className="l">Precio</div>
          <div className="v">{ficha?.precio == null ? SIN_DATO : formatearPrecio(ficha.precio)}</div>
          <div className={`s num ${direccion(cambio24h)}`}>{porcentaje(cambio24h)}</div>
        </div>

        <div className="kpi">
          <div className="l">Cambio 24h</div>
          <div className={`v ${direccion(cambio24h)}`}>{diferencia(enPlata)}</div>
          <div className="s num" style={{ color: 'var(--muted)' }}>vs hace 24 h</div>
        </div>

        <div className="kpi">
          <div className="l">Volumen 24h</div>
          <div className="v">{dineroCorto(ficha?.volumenCotizado24h ?? null)}</div>
          <div className="s num" style={{ color: parcial ? 'var(--gold)' : 'var(--muted)' }}>
            {ficha == null
              ? SIN_DATO
              : parcial
                ? `parcial · ${entero(ficha.minutos24h)}/${entero(MINUTOS_DEL_DIA)} min`
                : 'día completo'}
          </div>
        </div>

        <div className="kpi" title="Rango verdadero mediano de un tramo de 5 minutos en las últimas 24 h. Es la medida que usa la alerta de volatilidad anómala.">
          <div className="l">Volatilidad</div>
          <div className="v">{medida(volatilidad?.tipico_pct ?? null)}</div>
          <div className="s num" style={{ color: 'var(--muted)' }}>
            {volatilidad
              ? `típico 5m · máx ${medida(volatilidad.maximo_pct)}`
              : 'sin historia suficiente'}
          </div>
        </div>

        <div className="kpi">
          <div className="l">Rango 24h</div>
          <div className="v" style={{ fontSize: 13 }}>
            {rango(ficha?.minimo24h ?? null, ficha?.maximo24h ?? null)}
          </div>
          <div className="s num" style={{ color: 'var(--muted)' }}>bajo–alto</div>
        </div>

        <div className="kpi">
          <div className="l">Cambio 7d</div>
          <div className={`v ${direccion(cambio7d)}`}>{porcentaje(cambio7d)}</div>
          <div className="s num" style={{ color: 'var(--muted)' }}>vs hace 7 días</div>
        </div>
      </div>

      <div className="panel">
        <div className="pulse-h">
          <h3>
            {activo ? `${activo.simbolo}/${activo.cotizacion}` : par} · precio &amp; volumen · 24h
          </h3>
          <span className="mono-l stamp">FIG_03</span>
        </div>
        <PriceVolChart par={par} />
      </div>

      <MarketTable
        order={order}
        pinned={pinned}
        togglePin={togglePin}
        par={par}
        seleccionar={seleccionar}
      />
    </>
  )
}
