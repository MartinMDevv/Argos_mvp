import { COINS } from '@/data/coins'
import { Peacock } from './Peacock'
import { CoinLogo } from './CoinLogo'
import { Icon } from './Icon'
import type { View } from '@/App'

interface Props {
  view: View
  setView: (v: View) => void
  openChat: () => void
  order: string[]
  pinned: Record<string, boolean>
  theme: 'dark' | 'light'
  toggleTheme: () => void
}

export function Sidebar({ view, setView, openChat, order, pinned, theme, toggleTheme }: Props) {
  const pins = order.filter(s => pinned[s])
  return (
    <nav>
      <div className="brand">
        <Peacock size={30} anim />
        <h1 className="wordmark">Argos</h1>
      </div>

      <div className="navsec">Vigilancia</div>
      <button type="button" className={`nav-i ${view === 'panel' ? 'on' : ''}`} onClick={() => setView('panel')}>
        <Icon name="panel" /> <span className="lbl">Panel</span>
      </button>
      <button type="button" className={`nav-i ${view === 'mercados' ? 'on' : ''}`} onClick={() => setView('mercados')}>
        <Icon name="mercados" /> <span className="lbl">Mercados</span>
      </button>
      <button type="button" className="nav-i">
        <Icon name="alertas" /> <span className="lbl">Alertas</span> <span className="badge">2</span>
      </button>

      <div className="navsec">Asistente</div>
      <button type="button" className="nav-i" onClick={openChat}>
        <Icon name="chat" /> <span className="lbl">Chat con Argos</span>
      </button>

      <div className="navsec">Fijados</div>
      <div className="pinnav">
        {pins.length === 0
          ? <div className="empty">Sin activos fijados</div>
          : pins.map(s => (
            <button type="button" className="pinnav-i" key={s} title={COINS[s].name}>
              <CoinLogo sym={s} />
              <span className="tk">{s}</span>
              <span className={`ch ${COINS[s].dir}`}>{COINS[s].ch}</span>
            </button>
          ))}
      </div>

      <div className="navsec">Cuenta</div>
      <button type="button" className="nav-i soon">
        <Icon name="cartera" /> <span className="lbl">Cartera</span> <span className="badge">pronto</span>
      </button>
      <button type="button" className="nav-i soon">
        <Icon name="cuenta" /> <span className="lbl">Cuenta</span> <span className="badge">pronto</span>
      </button>
      <button type="button" className="nav-i">
        <Icon name="config" /> <span className="lbl">Configuración</span>
      </button>

      <div className="navfoot">
        <div className="live alert" title="1 anomalía activa: el sonar late más rápido">
          <span className="sonar"><i /></span>
          <span className="livetxt"><b>Vigilando</b> · en vivo</span>
        </div>
        <button type="button" className="themebtn" onClick={toggleTheme}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          <span className="lbl">{theme === 'dark' ? 'Tema claro' : 'Tema oscuro'}</span>
        </button>
      </div>
    </nav>
  )
}
