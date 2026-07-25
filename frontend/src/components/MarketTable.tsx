import { COINS } from '@/data/coins'
import { CoinLogo } from './CoinLogo'
import { Pin } from './Pin'
import { IsoLayers } from './illustrations/IsoLayers'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (sym: string) => void
}

// Tabla densa de mercado (activos vigilados) con identidad + pin.
export function MarketTable({ order, pinned, togglePin }: Props) {
  return (
    <div className="panel">
      <div className="mkt-head">
        <h3>Mercado · activos vigilados</h3>
        <IsoLayers />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="mkt">
          <thead>
            <tr>
              <th></th><th>Activo</th><th>Último</th><th>1h</th><th>24h</th><th>7d</th><th>Vol 24h</th><th>Volatilidad</th><th>7 días</th>
            </tr>
          </thead>
          <tbody>
            {order.map(sym => {
              const c = COINS[sym], r = c.row
              return (
                <tr key={sym} data-sym={sym}>
                  <td className="pincell"><Pin on={pinned[sym]} onClick={() => togglePin(sym)} /></td>
                  <td>
                    <span className="sym">
                      <CoinLogo sym={sym} />
                      <span>{sym}<span className="nm2">{c.name}</span></span>
                    </span>
                  </td>
                  <td>{c.px}</td>
                  <td className={r.h1d}>{r.h1}</td>
                  <td className={r.d24d}>{r.d24}</td>
                  <td className={r.d7d}>{r.d7}</td>
                  <td>{r.vol}</td>
                  <td style={r.siggold ? { color: 'var(--gold)' } : undefined}>
                    {r.sig}{' '}
                    <span className="minibar"><i style={{ width: r.sigw, background: r.siggold ? 'var(--gold)' : undefined }} /></span>
                  </td>
                  <td>
                    <svg className="msvg" viewBox="0 0 70 18" preserveAspectRatio="none">
                      <polyline fill="none" stroke={`var(${r.sparkc})`} strokeWidth="1.5" points={r.spark} />
                    </svg>
                  </td>
                </tr>
              )
            })}
            <tr className="addrow">
              <td colSpan={9}>+ agregar activo a favoritos · <span style={{ color: 'var(--faint)' }}>más allá de BTC/ETH → fase futura</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
