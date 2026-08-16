import { activoDe } from '@/lib/activos'
import type { Intervalo } from '@/lib/api'
import { CandleChart } from './CandleChart'
import { StatusBar, PulseCard } from './PulseCard'
import { Watchlist } from './Watchlist'

interface Props {
  par: string
  intervalo: Intervalo
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (par: string) => void
  seleccionar: (par: string) => void
  /** Saltar a la vista Alertas, desde el "ver todas" del recuadro. */
  verAlertas: () => void
}

// Vista Panel: estado + gráfico de velas + (favoritos | lo que Argos vio).
// Desde el paso 2.2b el gráfico ya no está clavado en BTCUSDT · 1m: sigue lo que eligió el
// usuario en la watchlist, en el menú y en los botones de tramo de la cabecera.
export function PanelView({
  par,
  intervalo,
  order,
  pinned,
  togglePin,
  seleccionar,
  verAlertas,
}: Props) {
  const activo = activoDe(par)

  return (
    <>
      <StatusBar />
      <div className="panel">
        <div className="pulse-h">
          <h3>
            Gráfico · {activo ? `${activo.simbolo}/${activo.cotizacion}` : par} · velas {intervalo}
          </h3>
          <span className="mono-l stamp">FIG_02</span>
        </div>
        <CandleChart simbolo={par} intervalo={intervalo} />
      </div>
      <div className="row2">
        <Watchlist
          order={order}
          pinned={pinned}
          togglePin={togglePin}
          par={par}
          seleccionar={seleccionar}
        />
        <PulseCard verTodas={verAlertas} />
      </div>
    </>
  )
}
