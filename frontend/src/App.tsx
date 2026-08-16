import { useState } from 'react'
import { ACTIVO_POR_DEFECTO, PARES } from '@/lib/activos'
import type { Intervalo } from '@/lib/api'
import { useTheme } from '@/lib/useTheme'
import { Sidebar } from '@/components/Sidebar'
import { MarketHeader } from '@/components/MarketHeader'
import { PanelView } from '@/components/PanelView'
import { MercadosView } from '@/components/MercadosView'
import { AlertasView } from '@/components/AlertasView'
import { ChatIsland } from '@/components/ChatIsland'

export type View = 'panel' | 'mercados' | 'alertas'

export default function App() {
  const { theme, toggle } = useTheme()
  const [view, setView] = useState<View>('panel')
  // El chat arranca abierto en pantallas anchas; cerrado en angostas.
  const [chatOpen, setChatOpen] = useState(() => !matchMedia('(max-width:1040px)').matches)

  // Qué activo y qué tramo está mirando el usuario. Vive acá arriba porque lo tocan tres
  // lugares distintos —el menú, la watchlist y la cabecera— y todos tienen que mostrar lo
  // mismo. Se guarda el PAR (`BTCUSDT`), que es la identidad que entiende el backend; el
  // símbolo corto sale del catálogo solo para escribirlo en pantalla.
  const [par, setPar] = useState(ACTIVO_POR_DEFECTO.par)
  const [intervalo, setIntervalo] = useState<Intervalo>('1m')

  const [pinned, setPinned] = useState<Record<string, boolean>>({ BTCUSDT: true, ETHUSDT: true })
  const togglePin = (par: string) => setPinned((p) => ({ ...p, [par]: !p[par] }))

  // Fijados primero (mantiene el orden base del catálogo dentro de cada grupo).
  const order = [...PARES].sort((a, b) => (pinned[b] ? 1 : 0) - (pinned[a] ? 1 : 0))

  // Seleccionar un activo cambia de QUÉ se está hablando, no DÓNDE se está mirando: la vista se
  // queda donde estaba. La primera versión saltaba al Panel y estaba mal — desde Mercados, elegir
  // otra moneda para comparar sus KPIs te expulsaba de la tabla que estabas leyendo.
  const seleccionar = setPar

  return (
    <div className={`app ${chatOpen ? 'chat-open' : ''}`} data-view={view}>
      <Sidebar
        view={view}
        setView={setView}
        openChat={() => setChatOpen(true)}
        order={order}
        pinned={pinned}
        par={par}
        seleccionar={seleccionar}
        theme={theme}
        toggleTheme={toggle}
      />

      <main>
        <MarketHeader
          par={par}
          intervalo={intervalo}
          setIntervalo={setIntervalo}
          openChat={() => setChatOpen(true)}
        />
        {view === 'panel' && (
          <div className="view v-panel">
            <PanelView
              par={par}
              intervalo={intervalo}
              order={order}
              pinned={pinned}
              togglePin={togglePin}
              seleccionar={seleccionar}
              verAlertas={() => setView('alertas')}
            />
          </div>
        )}
        {view === 'mercados' && (
          <div className="view v-mercados">
            <MercadosView
              par={par}
              order={order}
              pinned={pinned}
              togglePin={togglePin}
              seleccionar={seleccionar}
            />
          </div>
        )}
        {view === 'alertas' && (
          <div className="view v-alertas">
            <AlertasView />
          </div>
        )}
      </main>

      <ChatIsland close={() => setChatOpen(false)} />
    </div>
  )
}
