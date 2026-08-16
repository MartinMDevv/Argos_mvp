import { activoDe } from '@/lib/activos'
import { SIN_DATO, direccion, porcentaje } from '@/lib/formato'
import { useFichas } from '@/lib/resumen'
import { useAlertas } from '@/lib/alertas'
import { useMercado } from '@/lib/mercado'
import { Peacock } from './Peacock'
import { CoinLogo } from './CoinLogo'
import { Icon } from './Icon'
import type { View } from '@/App'

interface Props {
  view: View
  setView: (v: View) => void
  /** Lleva a la sección Chat a pantalla completa (no a la isla: eso lo hace la cabecera). */
  irAlChat: () => void
  order: string[]
  pinned: Record<string, boolean>
  par: string
  seleccionar: (par: string) => void
  theme: 'dark' | 'light'
  toggleTheme: () => void
  /** `true` cuando el menú está colapsado a la tira de íconos. */
  navRail: boolean
  alternarNav: () => void
}

export function Sidebar({
  view,
  setView,
  irAlChat,
  order,
  pinned,
  par,
  seleccionar,
  theme,
  toggleTheme,
  navRail,
  alternarNav,
}: Props) {
  const pins = order.filter((p) => pinned[p])
  const fichas = useFichas(pins)
  const { sinLeer, alertas } = useAlertas()
  const { conectado } = useMercado()

  // El pie del menú decía "Vigilando · en vivo" con una anomalía inventada en el `title`,
  // pasara lo que pasara — incluso con el backend apagado. Ahora dice lo que hay: si el
  // socket está abierto y si Argos vio algo en la última hora.
  const recientes = alertas.filter(
    (alerta) => Date.now() - new Date(alerta.momento).getTime() < 3600_000,
  ).length

  return (
    <nav>
      <div className="brand">
        <Peacock size={30} anim />
        <h1 className="wordmark">Argos</h1>
        {/* Colapsar el menú deja el panel más ancho, que es lo que uno quiere cuando está
            mirando un gráfico. Los íconos se quedan: colapsado sigue siendo navegable. */}
        <button
          type="button"
          className="navtoggle"
          onClick={alternarNav}
          title={navRail ? 'Expandir el menú' : 'Colapsar el menú'}
          aria-label={navRail ? 'Expandir el menú' : 'Colapsar el menú'}
          aria-pressed={navRail}
        >
          <Icon name="colapsar" />
        </button>
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
      <button
        type="button"
        className={`nav-i ${view === 'chat' ? 'on' : ''}`}
        onClick={irAlChat}
      >
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
      <button
        type="button"
        className={`nav-i ${view === 'configuracion' ? 'on' : ''}`}
        onClick={() => setView('configuracion')}
      >
        <Icon name="config" /> <span className="lbl">Configuración</span>
      </button>

      <div className="navfoot">
        <div
          className={`live ${conectado ? (recientes > 0 ? 'alert' : '') : 'off'}`}
          title={
            conectado
              ? recientes > 0
                ? `${recientes} ${recientes === 1 ? 'alerta' : 'alertas'} en la última hora`
                : 'Conectado al backend, sin novedades en la última hora'
              : 'Sin conexión con el backend: lo que se ve puede estar viejo'
          }
        >
          <span className="sonar"><i /></span>
          <span className="livetxt">
            {conectado ? (
              <>
                <b>Vigilando</b> · en vivo
              </>
            ) : (
              <>
                <b>Sin conexión</b> · reintentando
              </>
            )}
          </span>
        </div>
        <button type="button" className="themebtn" onClick={toggleTheme}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          <span className="lbl">{theme === 'dark' ? 'Tema claro' : 'Tema oscuro'}</span>
        </button>
      </div>
    </nav>
  )
}
