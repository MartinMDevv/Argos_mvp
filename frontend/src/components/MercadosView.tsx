import { PriceVolChart } from './PriceVolChart'
import { MarketTable } from './MarketTable'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (sym: string) => void
}

// Vista Mercados: KPIs densos + precio/volumen + tabla de activos.
export function MercadosView({ order, pinned, togglePin }: Props) {
  return (
    <>
      <div className="kpis">
        <div className="kpi"><div className="l">Precio</div><div className="v">$64.284</div><div className="s up num">+1,84%</div></div>
        <div className="kpi"><div className="l">Cambio 24h</div><div className="v up">+$1.164</div><div className="s num" style={{ color: 'var(--muted)' }}>vs ayer</div></div>
        <div className="kpi"><div className="l">Volumen 24h</div><div className="v">$28,4B</div><div className="s up num">+12%</div></div>
        <div className="kpi"><div className="l">Volatilidad</div><div className="v" style={{ color: 'var(--gold)' }}>3,4σ</div><div className="s num" style={{ color: 'var(--muted)' }}>anómala</div></div>
        <div className="kpi"><div className="l">Rango 24h</div><div className="v" style={{ fontSize: 13 }}>62,1k–64,9k</div><div className="s num" style={{ color: 'var(--muted)' }}>bajo–alto</div></div>
        <div className="kpi"><div className="l">Máx 7d</div><div className="v">$66.020</div><div className="s down num">−2,6%</div></div>
      </div>

      <div className="panel">
        <div className="pulse-h">
          <h3>BTC/USD · precio &amp; volumen · 24h</h3>
          <span className="mono-l">FIG_03</span>
        </div>
        <PriceVolChart />
      </div>

      <MarketTable order={order} pinned={pinned} togglePin={togglePin} />
    </>
  )
}
