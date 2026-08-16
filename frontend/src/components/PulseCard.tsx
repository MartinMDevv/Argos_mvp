import { TONO_POR_SEVERIDAD, useAlertas } from '@/lib/alertas'
import type { AlertaJSON } from '@/lib/api'
import { simboloDe } from '@/lib/activos'
import { antiguedad } from '@/lib/formato'
import { Radar } from './illustrations/Radar'

/** Cuántas alertas entran en el recuadro del panel antes de mandar a la vista completa. */
const EN_EL_PANEL = 4

// Banner de estado del panel (integra la ilustración radar).
//
// Desde el paso 3.6 dice la verdad: lo que hay arriba sale de las alertas reales de la última
// hora, no de un texto fijo. "Mercado tranquilo" cuando Argos no vio nada es una afirmación, y
// las afirmaciones de Argos tienen que estar respaldadas por datos como cualquier otra.
export function StatusBar() {
  const { alertas, cargando, error } = useAlertas()

  const recientes = alertas.filter(
    (alerta) => Date.now() - new Date(alerta.momento).getTime() < 3600_000,
  )
  const fuertes = recientes.filter((alerta) => alerta.severidad === 'fuerte').length

  let titulo = 'Mercado tranquilo · Argos vigilando'
  let detalle = 'Sin movimientos que valga la pena contar en la última hora.'

  if (cargando) {
    titulo = 'Argos despertando'
    detalle = 'Trayendo lo que vio.'
  } else if (error) {
    // Un feed vacío por un error no puede parecer calma: sería exactamente la mentira que
    // Argos existe para no decir.
    titulo = 'Argos no puede leer sus alertas'
    detalle = 'El backend no respondió. Lo que se ve abajo puede estar viejo.'
  } else if (recientes.length > 0) {
    titulo = `Argos vio ${recientes.length} ${recientes.length === 1 ? 'cosa' : 'cosas'} en la última hora`
    const simbolos = [...new Set(recientes.map((alerta) => simboloDe(alerta.simbolo)))]
    detalle = fuertes
      ? `${fuertes} de nivel fuerte · ${simbolos.join(', ')}.`
      : `Nada de nivel fuerte · ${simbolos.join(', ')}.`
  }

  return (
    <div className="statusbar">
      <div className="st-txt">
        <div className="k">
          <span className="pip" /> {titulo}
        </div>
        <p>{detalle}</p>
      </div>
      <Radar />
    </div>
  )
}

/**
 * Una alerta en el feed. El detalle ya viene escrito por el detector que la emitió.
 *
 * A propósito NO se reescribe el texto acá: el que sabe qué pasó es el detector, que además lo
 * redactó con los números exactos delante. Traducirlo en el frontend sería una segunda versión
 * de la verdad, y tarde o temprano las dos dejan de coincidir.
 */
function Evento({ alerta, ahora }: { alerta: AlertaJSON; ahora: number }) {
  return (
    <div className={`pev ${TONO_POR_SEVERIDAD[alerta.severidad] ?? 'lo'}`}>
      <div className="st">
        <span className="pip" /> {alerta.titulo}
        <span className="meta">
          {simboloDe(alerta.simbolo)} · {antiguedad(alerta.momento, ahora)}
        </span>
      </div>
      <ul>
        <li>{alerta.detalle}</li>
      </ul>
    </div>
  )
}

// "Lo que Argos vio": las últimas alertas reales de los cuatro detectores (paso 3.6).
export function PulseCard({ verTodas }: { verTodas?: () => void }) {
  const { alertas, cargando, error } = useAlertas()
  const ahora = Date.now()

  return (
    <div className="panel">
      <div className="pulse-h">
        <h3>Lo que Argos vio</h3>
        {alertas.length > EN_EL_PANEL && verTodas && (
          <button type="button" className="lnk" onClick={verTodas}>
            ver todas ({alertas.length})
          </button>
        )}
      </div>

      {cargando && <p className="vacio">Trayendo lo que Argos vio…</p>}

      {!cargando && error && <p className="vacio">No se pudieron traer las alertas: {error}</p>}

      {/* Que no haya nada es una respuesta válida y frecuente: los detectores callan casi
          siempre, y eso es lo que se busca. Se dice, en vez de dejar un hueco. */}
      {!cargando && !error && alertas.length === 0 && (
        <p className="vacio">Todavía no vio nada que valga la pena contar.</p>
      )}

      {alertas.slice(0, EN_EL_PANEL).map((alerta) => (
        <Evento key={alerta.id} alerta={alerta} ahora={ahora} />
      ))}
    </div>
  )
}
