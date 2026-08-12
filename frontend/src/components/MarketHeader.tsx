import { activoDe } from '@/lib/activos'
import { INTERVALOS } from '@/lib/api'
import type { Intervalo } from '@/lib/api'
import {
  SIN_DATO,
  antiguedad,
  diferencia,
  direccion,
  porcentaje,
  precio as formatearPrecio,
} from '@/lib/formato'
import { useFicha } from '@/lib/resumen'
import { CoinLogo } from './CoinLogo'
import { Icon } from './Icon'

interface Props {
  par: string
  intervalo: Intervalo
  setIntervalo: (i: Intervalo) => void
  openChat: () => void
}

/**
 * Cabecera del activo que se está mirando: identidad, precio, cambio del día y selector de tramo.
 *
 * ## El cambio se muestra en las dos unidades
 * `+$1.164,20 · +1,84%` — el porcentaje sirve para comparar entre activos y la plata para
 * entender cuánto es. La diferencia en plata sale de restarle al precio de ahora la `referencia`
 * de 24 h que manda el backend, así que es la misma cuenta que el porcentaje y no puede
 * contradecirlo.
 *
 * ## Los botones de tramo ahora mandan (paso 2.2b)
 * Hasta acá eran decorativos y decían `15m/1H/4H/1D`. Ahora salen de `INTERVALOS`, que es la
 * lista cerrada que el backend sabe armar (`app/velas.py`): si algún día se agrega un tramo, se
 * agrega en un lugar y aparece acá solo. Antes, además, faltaban dos de los seis.
 */
export function MarketHeader({ par, intervalo, setIntervalo, openChat }: Props) {
  const activo = activoDe(par)
  const ficha = useFicha(par)

  const cambio24h = ficha?.cambios['24h'] ?? null
  const dir = direccion(cambio24h)

  // En plata: cuánto se movió desde el precio de hace 24 h. Solo se puede si hay las dos puntas.
  const enPlata =
    ficha?.precio != null && ficha.referencia24h != null ? ficha.precio - ficha.referencia24h : null

  return (
    <div className="mhead">
      <span className="mhlogo">
        <CoinLogo sym={activo?.simbolo ?? ''} />
      </span>

      <div className="mh-id">
        <div className="tk">
          {activo ? `${activo.simbolo} · ${activo.nombre}` : par}
        </div>
        <div className="sub num">
          {activo ? `${activo.simbolo}/${activo.cotizacion} · spot` : 'sin catálogo'}
        </div>
      </div>

      <span className="price num">
        {ficha?.precio == null ? SIN_DATO : formatearPrecio(ficha.precio)}
      </span>

      <span className={`delta num ${dir}`}>
        {cambio24h === null ? SIN_DATO : `${diferencia(enPlata)} · ${porcentaje(cambio24h)}`}
      </span>

      {/* Cuándo es ese precio. Con la ingesta corriendo dice "hace 0 s" y pasa desapercibido, que
          es justo lo que tiene que hacer; el día que Argos esté apagado, delata que el número de
          al lado es viejo en vez de dejar que se lea como el de ahora. */}
      {ficha?.momento && (
        <span className="mono-l" title={`Último dato: ${new Date(ficha.momento).toLocaleString('es-CL')}`}>
          {ficha.vivo ? 'en vivo' : antiguedad(ficha.momento)}
        </span>
      )}

      <span className="spacer" />

      <div className="tf">
        {INTERVALOS.map((i) => (
          <button
            type="button"
            key={i}
            className={i === intervalo ? 'on' : ''}
            onClick={() => setIntervalo(i)}
          >
            {i}
          </button>
        ))}
      </div>

      <button className="chatbtn" type="button" onClick={openChat}>
        <Icon name="chat" /> Chat
      </button>
    </div>
  )
}
