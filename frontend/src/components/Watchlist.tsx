import { SIN_DATO, direccion, porcentaje, precio as formatearPrecio } from '@/lib/formato'
import { useEstadoResumen, useFichas } from '@/lib/resumen'
import { CoinLogo } from './CoinLogo'
import { Pin } from './Pin'
import { Sparkline } from './Sparkline'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (par: string) => void
  par: string
  seleccionar: (par: string) => void
}

/**
 * "Vigilancia · favoritos": los activos vigilados, con su precio y su cambio del día.
 *
 * Todo lo que se ve acá es real desde el paso 2.2b: el precio se mueve con el WebSocket, el
 * porcentaje se recalcula contra ese precio (ver `lib/resumen.tsx`) y la curvita sale de las
 * velas de verdad. Hacer clic en una fila cambia lo que mira el gráfico.
 *
 * El cambio que se muestra es el de **24 h**, que es el que la gente quiere decir cuando
 * pregunta "cómo viene". Si sale `—` no es un error: es que Argos no tiene con qué comparar
 * todavía, y prefiere decirlo antes que mostrar un cero que se leería como "no se movió".
 */
export function Watchlist({ order, pinned, togglePin, par, seleccionar }: Props) {
  const fichas = useFichas(order)
  const { cargando, error } = useEstadoResumen()

  return (
    <div className="panel">
      <div className="pulse-h">
        <h3>Vigilancia · favoritos</h3>
        {error && <span className="mono-l" title={error}>sin conexión</span>}
      </div>

      {order.map((parDeLaFila, i) => {
        const ficha = fichas[i]

        // Sin ficha no hay nada que mostrar todavía: ni el catálogo llegó a resolver el activo
        // ni Argos vio un precio. Es el estado de los primeros milisegundos.
        if (!ficha) {
          return (
            <div className="asset" key={parDeLaFila}>
              <span className="id">
                <div className="tk">{parDeLaFila}</div>
                <div className="nm">{cargando ? 'cargando…' : 'sin datos'}</div>
              </span>
            </div>
          )
        }

        const { activo, cambios } = ficha
        const dir = direccion(cambios['24h'])

        return (
          <div
            className={`asset ${activo.par === par ? 'sel' : ''}`}
            key={activo.par}
            data-sym={activo.simbolo}
            onClick={() => seleccionar(activo.par)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && seleccionar(activo.par)}
            title={`Ver ${activo.nombre} en el gráfico`}
          >
            {/* El pin corta el clic él mismo (ver Pin.tsx): fijar no debe arrastrar la selección. */}
            <Pin on={pinned[activo.par]} onClick={() => togglePin(activo.par)} />

            <CoinLogo sym={activo.simbolo} />
            <div className="id">
              <div className="tk">{activo.simbolo}</div>
              <div className="nm">{activo.nombre}</div>
            </div>

            {/* 24 velas de 1 h = el último día, el mismo tramo que el porcentaje de al lado. */}
            <Sparkline
              className="spark2"
              par={activo.par}
              intervalo="1h"
              limite={24}
              ancho={200}
              alto={22}
            />

            <div className="rt">
              <div className="px">
                {ficha.precio === null ? SIN_DATO : formatearPrecio(ficha.precio)}
              </div>
              <div className={`ch ${dir}`}>
                {cambios['24h'] === null
                  ? SIN_DATO
                  : `${dir === 'up' ? '▲' : '▼'} ${porcentaje(cambios['24h']).replace(/^[+−]/, '')}`}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
