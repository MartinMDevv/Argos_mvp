import { useEffect, useState } from 'react'

import { simboloDe } from '@/lib/activos'
import { TONO_POR_SEVERIDAD, useAlertas } from '@/lib/alertas'
import type { AlertaJSON, DetectorJSON } from '@/lib/api'
import { obtenerDetectores } from '@/lib/api'
import { antiguedad, fechaHora } from '@/lib/formato'
import { Umbrales } from './Umbrales'

/**
 * Vista Alertas: todo lo que Argos vio, con la evidencia a la vista (paso 3.6).
 *
 * La diferencia con el recuadro del Panel no es el largo de la lista: es que acá se puede abrir
 * cada alerta y ver **con qué números** la emitió. Esa es la regla del proyecto puesta en
 * pantalla — Argos no pide que le crean, muestra la cuenta.
 */
export function AlertasView() {
  const { alertas, cargando, error, marcarVistas } = useAlertas()
  const [filtro, setFiltro] = useState<string>('')
  const [detectores, setDetectores] = useState<DetectorJSON[]>([])

  // Entrar a esta vista es haberlas visto: el contador del menú vuelve a cero.
  useEffect(() => {
    marcarVistas()
  }, [marcarVistas])

  useEffect(() => {
    const control = new AbortController()
    obtenerDetectores(control.signal)
      .then(setDetectores)
      .catch(() => {
        // Sin el catálogo, la lista sigue andando: solo se pierden los nombres bonitos del
        // filtro. No vale la pena molestar con un error por eso.
      })
    return () => control.abort()
  }, [])

  const visibles = filtro ? alertas.filter((a) => a.detector === filtro) : alertas
  const nombreDe = (detector: string) =>
    detectores.find((d) => d.nombre === detector)?.titulo ?? detector

  return (
    <>
      {/* Arriba lo que hay que configurar, abajo lo que pasó: el orden con el que uno llega a
          esta pantalla es "quiero que me avise de algo" y después "a ver qué vio". */}
      <Umbrales />

      <div className="panel">
        <div className="pulse-h">
          <h3>Lo que Argos vio</h3>
          <span className="mono-l stamp">{alertas.length} EN REGISTRO</span>
        </div>

        <div className="filtros">
          <button
            type="button"
            className={`chip ${filtro === '' ? 'on' : ''}`}
            onClick={() => setFiltro('')}
          >
            todo
          </button>
          {detectores.map((detector) => (
            <button
              key={detector.nombre}
              type="button"
              className={`chip ${filtro === detector.nombre ? 'on' : ''}`}
              onClick={() => setFiltro(detector.nombre)}
              title={detector.descripcion}
            >
              {detector.titulo}
            </button>
          ))}
        </div>

        {cargando && <p className="vacio">Trayendo lo que Argos vio…</p>}
        {!cargando && error && <p className="vacio">No se pudieron traer las alertas: {error}</p>}

        {!cargando && !error && visibles.length === 0 && (
          <p className="vacio">
            {filtro
              ? 'Este detector todavía no encontró nada.'
              : 'Todavía no vio nada que valga la pena contar. Es lo normal: los detectores callan casi siempre.'}
          </p>
        )}

        {visibles.map((alerta) => (
          <Fila key={alerta.id} alerta={alerta} nombreDe={nombreDe} />
        ))}
      </div>
    </>
  )
}

function Fila({
  alerta,
  nombreDe,
}: {
  alerta: AlertaJSON
  nombreDe: (detector: string) => string
}) {
  const [abierta, setAbierta] = useState(false)

  return (
    <div className={`pev ${TONO_POR_SEVERIDAD[alerta.severidad] ?? 'lo'}`}>
      <div className="st">
        <span className="pip" /> {alerta.titulo}
        <span className="meta">
          {simboloDe(alerta.simbolo)} · {antiguedad(alerta.momento)} · {nombreDe(alerta.detector)}
        </span>
      </div>
      <ul>
        <li>{alerta.detalle}</li>
      </ul>

      <button type="button" className="lnk" onClick={() => setAbierta((v) => !v)}>
        {abierta ? 'ocultar la cuenta' : 'ver la cuenta'}
      </button>

      {abierta && (
        <div className="evidencia">
          <div className="ev-fecha mono-l">{fechaHora(alerta.momento)}</div>
          {/* Las claves cambian según el detector, así que se muestran tal cual vienen en vez
              de suponer cuáles existen. Un detector nuevo aparece acá sin tocar nada. */}
          <table>
            <tbody>
              {Object.entries(alerta.evidencia).map(([nombre, valor]) => (
                <tr key={nombre}>
                  <td className="ev-k">{nombre.replaceAll('_', ' ')}</td>
                  <td className="ev-v mono-l">{valor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
