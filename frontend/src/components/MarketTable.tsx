import {
  SIN_DATO,
  dineroCorto,
  direccion,
  porcentaje,
  precio as formatearPrecio,
} from '@/lib/formato'
import { useFichas } from '@/lib/resumen'
import { CoinLogo } from './CoinLogo'
import { Pin } from './Pin'
import { Sparkline } from './Sparkline'
import { IsoLayers } from './illustrations/IsoLayers'

interface Props {
  order: string[]
  pinned: Record<string, boolean>
  togglePin: (par: string) => void
  par: string
  seleccionar: (par: string) => void
}

/**
 * Tabla densa de los activos vigilados: último precio, cambios por plazo, volumen y curva.
 *
 * La columna de volatilidad queda vacía a propósito hasta la Fase 3: el σ lo va a calcular el
 * detector de z-score sobre la historia, y hasta que exista se muestra el hueco. Un `3,4σ` de
 * relleno se leería como una medición.
 */
export function MarketTable({ order, pinned, togglePin, par, seleccionar }: Props) {
  const fichas = useFichas(order)

  return (
    <div className="panel">
      <div className="mkt-head">
        <h3>Mercado · activos vigilados</h3>
        <IsoLayers />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="mkt">
          <thead>
            <tr>
              <th></th><th>Activo</th><th>Último</th><th>1h</th><th>24h</th><th>7d</th>
              <th>Vol 24h</th><th>Volatilidad</th><th>7 días</th>
            </tr>
          </thead>
          <tbody>
            {order.map((parDeLaFila, i) => {
              const ficha = fichas[i]

              if (!ficha) {
                return (
                  <tr key={parDeLaFila}>
                    <td />
                    <td>{parDeLaFila}</td>
                    <td colSpan={7} style={{ color: 'var(--faint)' }}>sin datos todavía</td>
                  </tr>
                )
              }

              const { activo, cambios } = ficha

              return (
                <tr
                  key={activo.par}
                  data-sym={activo.simbolo}
                  className={activo.par === par ? 'sel' : ''}
                  onClick={() => seleccionar(activo.par)}
                >
                  <td className="pincell">
                    <Pin on={pinned[activo.par]} onClick={() => togglePin(activo.par)} />
                  </td>
                  <td>
                    <span className="sym">
                      <CoinLogo sym={activo.simbolo} />
                      <span>{activo.simbolo}<span className="nm2">{activo.nombre}</span></span>
                    </span>
                  </td>
                  <td>{ficha.precio === null ? SIN_DATO : formatearPrecio(ficha.precio)}</td>
                  <td className={direccion(cambios['1h'])}>{porcentaje(cambios['1h'])}</td>
                  <td className={direccion(cambios['24h'])}>{porcentaje(cambios['24h'])}</td>
                  <td className={direccion(cambios['7d'])}>{porcentaje(cambios['7d'])}</td>
                  <td>{dineroCorto(ficha.volumenCotizado24h)}</td>
                  <td style={{ color: 'var(--faint)' }} title="La calcula el detector de z-score (Fase 3)">
                    {SIN_DATO}
                  </td>
                  <td>
                    {/* 42 velas de 4 h = una semana, el mismo tramo que dice el encabezado. */}
                    <Sparkline
                      className="msvg"
                      par={activo.par}
                      intervalo="4h"
                      limite={42}
                      ancho={70}
                      alto={18}
                    />
                  </td>
                </tr>
              )
            })}
            <tr className="addrow">
              <td colSpan={9}>+ agregar activo a favoritos · <span style={{ color: 'var(--faint)' }}>más allá de BTC/ETH → fase futura</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
