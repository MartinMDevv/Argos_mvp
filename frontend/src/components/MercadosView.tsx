import { activoDe } from '@/lib/activos'
import {
  SIN_DATO,
  dineroCorto,
  diferencia,
  direccion,
  entero,
  porcentaje,
  rango,
  precio as formatearPrecio,
} from '@/lib/formato'
import { MINUTOS_DEL_DIA, useFicha } from '@/lib/resumen'
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
 * Los cinco KPIs que se pueden calcular con lo que Argos tiene hoy salen de
 * `GET /mercado/resumen`. El de volatilidad queda en `—` a propósito: esa cifra la va a producir
 * el detector de z-score en la Fase 3, y ponerle mientras tanto un "3,4σ" de adorno sería
 * exactamente lo que la regla de oro prohíbe — un número que parece medido y no lo es.
 */
export function MercadosView({ par, order, pinned, togglePin, seleccionar }: Props) {
  const activo = activoDe(par)
  const ficha = useFicha(par)

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

        <div className="kpi">
          <div className="l">Volatilidad</div>
          <div className="v" style={{ color: 'var(--muted)' }}>{SIN_DATO}</div>
          <div className="s num" style={{ color: 'var(--faint)' }}>llega en Fase 3</div>
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
          <span className="mono-l stamp" title="Este gráfico todavía dibuja datos de ejemplo">FIG_03 · mock</span>
        </div>
        <PriceVolChart />
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
