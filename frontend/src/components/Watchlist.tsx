import { COINS } from '@/data/coins'
import { CoinLogo } from './CoinLogo'
import { Pin } from './Pin'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (sym: string) => void
}

// "Vigilancia · favoritos": los activos fijados, primero los pineados.
export function Watchlist({ order, pinned, togglePin }: Props) {
  return (
    <div className="panel">
      <div className="pulse-h"><h3>Vigilancia · favoritos</h3></div>
      {order.map(sym => {
        const c = COINS[sym]
        return (
          <div className="asset" key={sym} data-sym={sym}>
            <Pin on={pinned[sym]} onClick={() => togglePin(sym)} />
            <CoinLogo sym={sym} />
            <div className="id">
              <div className="tk">{sym}</div>
              <div className="nm">{c.name}</div>
            </div>
            <svg className="spark2" viewBox="0 0 200 22" preserveAspectRatio="none">
              <polyline fill="none" stroke={`var(${c.dir === 'up' ? '--bull' : '--bear'})`} strokeWidth="1.6" points={c.spark} />
            </svg>
            <div className="rt">
              <div className="px">{c.px}</div>
              <div className={`ch ${c.dir}`}>{c.dir === 'up' ? '▲' : '▼'} {c.ch.replace(/[+−-]/, '')}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
