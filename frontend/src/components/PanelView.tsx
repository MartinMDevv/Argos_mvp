import { CandleChart } from './CandleChart'
import { StatusBar, PulseCard } from './PulseCard'
import { Watchlist } from './Watchlist'
import type { Intervalo } from '@/lib/api'

// Qué mira el gráfico del Panel. Por ahora fijo: el selector de moneda y de intervalo llega
// en el paso 2.2, cuando la watchlist también deje de ser mock.
const SIMBOLO = 'BTCUSDT'
const INTERVALO: Intervalo = '1m'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (sym: string) => void
}

// Vista Panel: estado + gráfico de velas + (favoritos | lo que Argos vio).
export function PanelView({ order, pinned, togglePin }: Props) {
  return (
    <>
      <StatusBar />
      <div className="panel">
        <div className="pulse-h">
          <h3>Gráfico · BTC/USDT · velas {INTERVALO}</h3>
          <span className="mono-l">FIG_02</span>
        </div>
        <CandleChart simbolo={SIMBOLO} intervalo={INTERVALO} />
      </div>
      <div className="row2">
        <Watchlist order={order} pinned={pinned} togglePin={togglePin} />
        <PulseCard />
      </div>
    </>
  )
}
