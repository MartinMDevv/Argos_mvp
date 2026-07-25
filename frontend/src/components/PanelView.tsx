import { CandleChart } from './CandleChart'
import { StatusBar, PulseCard } from './PulseCard'
import { Watchlist } from './Watchlist'

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
          <h3>Gráfico · BTC/USD · velas 4H</h3>
          <span className="mono-l">FIG_02</span>
        </div>
        <CandleChart />
      </div>
      <div className="row2">
        <Watchlist order={order} pinned={pinned} togglePin={togglePin} />
        <PulseCard />
      </div>
    </>
  )
}
