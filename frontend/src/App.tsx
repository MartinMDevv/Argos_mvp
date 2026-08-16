import { useState } from 'react'
import { ACTIVO_POR_DEFECTO, PARES } from '@/lib/activos'
import type { Intervalo } from '@/lib/api'
import { useTheme } from '@/lib/useTheme'
import { Sidebar } from '@/components/Sidebar'
import { MarketHeader } from '@/components/MarketHeader'
import { PanelView } from '@/components/PanelView'
import { MercadosView } from '@/components/MercadosView'
import { AlertasView } from '@/components/AlertasView'
import { AvisoDeAlerta } from '@/components/AvisoDeAlerta'
import { ConfiguracionView } from '@/components/ConfiguracionView'
import { ChatView } from '@/components/ChatView'
import { ChatIsland } from '@/components/ChatIsland'

export type View = 'panel' | 'mercados' | 'alertas' | 'chat' | 'configuracion'

export default function App() {
  const { theme, toggle } = useTheme()
  const [view, setView] = useState<View>('panel')
  // El chat arranca CERRADO siempre. Antes se abría solo en pantallas anchas y se comía 360px
  // del panel en cada arranque, cuando lo que uno viene a ver es el mercado: si quiere hablar
  // con Argos, lo abre. Su estado no se recuerda a propósito — abrirlo es una decisión del
  // momento, no una preferencia.
  const [chatOpen, setChatOpen] = useState(false)

  // El menú sí se recuerda: colapsarlo es una preferencia de cómo quieres trabajar, y que se
  // vuelva a abrir en cada recarga sería pelearse con la app todos los días.
  const [navRail, setNavRail] = useState(() => localStorage.getItem('argos:nav') === 'rail')

  const alternarNav = () => {
    setNavRail((colapsado) => {
      const siguiente = !colapsado
      localStorage.setItem('argos:nav', siguiente ? 'rail' : 'full')
      return siguiente
    })
  }

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
    <div
      className={`app ${chatOpen ? 'chat-open' : ''}`}
      data-view={view}
      data-nav={navRail ? 'rail' : 'full'}
    >
      <Sidebar
        view={view}
        setView={setView}
        irAlChat={() => {
          // Entrar a la sección cierra la isla: son dos ventanas a la misma conversación y
          // tenerlas abiertas a la vez es mostrar lo mismo dos veces, robándole ancho al chat.
          setChatOpen(false)
          setView('chat')
        }}
        order={order}
        pinned={pinned}
        par={par}
        seleccionar={seleccionar}
        theme={theme}
        toggleTheme={toggle}
        navRail={navRail}
        alternarNav={alternarNav}
      />

      <main>
        <MarketHeader
          par={par}
          intervalo={intervalo}
          setIntervalo={setIntervalo}
          /* El botón del encabezado abre la ISLA, no la sección: desde el gráfico uno quiere
             preguntar sin perder de vista lo que está mirando. Para leer con calma está el
             botón del menú, que sí lleva a la sección completa. */
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
        {view === 'chat' && (
          <div className="view v-chat">
            <ChatView />
          </div>
        )}
        {view === 'configuracion' && (
          <div className="view v-configuracion">
            <ConfiguracionView theme={theme} toggleTheme={toggle} />
          </div>
        )}
      </main>

      <ChatIsland
        close={() => setChatOpen(false)}
        verSeccion={() => {
          setChatOpen(false)
          setView('chat')
        }}
      />

      {/* Fuera de <main> a propósito: el aviso tiene que verse desde cualquier vista, y no
          debe empujar el contenido cuando aparece. */}
      <AvisoDeAlerta verAlertas={() => setView('alertas')} />
    </div>
  )
}
