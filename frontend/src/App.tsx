import { useState } from 'react'
import { ORDER } from '@/data/coins'
import { useTheme } from '@/lib/useTheme'
import { Sidebar } from '@/components/Sidebar'
import { MarketHeader } from '@/components/MarketHeader'
import { PanelView } from '@/components/PanelView'
import { MercadosView } from '@/components/MercadosView'
import { ChatIsland } from '@/components/ChatIsland'

export type View = 'panel' | 'mercados'

export default function App() {
  const { theme, toggle } = useTheme()
  const [view, setView] = useState<View>('panel')
  // El chat arranca abierto en pantallas anchas; cerrado en angostas.
  const [chatOpen, setChatOpen] = useState(() => !matchMedia('(max-width:1040px)').matches)
  const [pinned, setPinned] = useState<Record<string, boolean>>({ BTC: true, ETH: true })

  const togglePin = (sym: string) => setPinned(p => ({ ...p, [sym]: !p[sym] }))
  // Fijados primero (mantiene el orden base dentro de cada grupo).
  const order = [...ORDER].sort((a, b) => (pinned[b] ? 1 : 0) - (pinned[a] ? 1 : 0))

  return (
    <div className={`app ${chatOpen ? 'chat-open' : ''}`} data-view={view}>
      <Sidebar
        view={view}
        setView={setView}
        openChat={() => setChatOpen(true)}
        order={order}
        pinned={pinned}
        theme={theme}
        toggleTheme={toggle}
      />

      <main>
        <MarketHeader openChat={() => setChatOpen(true)} />
        {view === 'panel' && (
          <div className="view v-panel">
            <PanelView order={order} pinned={pinned} togglePin={togglePin} />
          </div>
        )}
        {view === 'mercados' && (
          <div className="view v-mercados">
            <MercadosView order={order} pinned={pinned} togglePin={togglePin} />
          </div>
        )}
      </main>

      <ChatIsland close={() => setChatOpen(false)} />
    </div>
  )
}
