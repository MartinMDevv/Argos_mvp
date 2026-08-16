import { activoDe } from '@/lib/activos'
import { SIN_DATO, direccion, porcentaje } from '@/lib/formato'
import { useFichas } from '@/lib/resumen'
import { useAlertas } from '@/lib/alertas'
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
  par: string
  seleccionar: (par: string) => void
  theme: 'dark' | 'light'
  toggleTheme: () => void
}

export function Sidebar({
  view,
  setView,
  openChat,
  order,
  pinned,
  par,
  seleccionar,
  theme,
  toggleTheme,
}: Props) {
  const pins = order.filter((p) => pinned[p])
  const fichas = useFichas(pins)
  const { sinLeer } = useAlertas()

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
      <button
        type="button"
        className={`nav-i ${view === 'alertas' ? 'on' : ''}`}
        onClick={() => setView('alertas')}
      >
        <Icon name="alertas" /> <span className="lbl">Alertas</span>
        {/* El contador sale de lo que Argos vio y todavía no miraste. Sin alertas nuevas no
            hay globo: un "0" permanente es ruido, y un número inventado sería peor. */}
        {sinLeer > 0 && <span className="badge">{sinLeer}</span>}
      </button>

      <div className="navsec">Asistente</div>
      <button type="button" className="nav-i" onClick={openChat}>
        <Icon name="chat" /> <span className="lbl">Chat con Argos</span>
      </button>

      {/* Los fijados son también el selector de moneda: hacer clic cambia lo que mira el gráfico.
          El cambio de 24 h va al lado, real y moviéndose, para poder elegir mirando. */}
      <div className="navsec">Fijados</div>
      <div className="pinnav">
        {pins.length === 0 ? (
          <div className="empty">Sin activos fijados</div>
        ) : (
          pins.map((parFijado, i) => {
            const activo = activoDe(parFijado)
            const cambio = fichas[i]?.cambios['24h'] ?? null
            if (!activo) return null

            return (
              <button
                type="button"
                className={`pinnav-i ${parFijado === par ? 'on' : ''}`}
                key={parFijado}
                title={activo.nombre}
                onClick={() => seleccionar(parFijado)}
              >
                <CoinLogo sym={activo.simbolo} />
                <span className="tk">{activo.simbolo}</span>
                <span className={`ch ${direccion(cambio)}`}>
                  {cambio === null ? SIN_DATO : porcentaje(cambio)}
                </span>
              </button>
            )
          })
        )}
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
