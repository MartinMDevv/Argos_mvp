import type { MouseEvent } from 'react'

import { Icon } from './Icon'

/**
 * Botón de fijar (favorito), en recuadro cuadrado con borde redondeado.
 *
 * **Corta la propagación del clic él mismo.** Desde el paso 2.2b la fila entera es clickeable
 * —selecciona el activo—, y el pin vive adentro: sin esto, fijar algo también lo seleccionaría.
 *
 * Que lo haga el propio botón y no quien lo coloca no es un detalle: la primera versión lo
 * resolvía envolviéndolo en un `<span>` con `stopPropagation`, y ese `span` se metía como un ítem
 * más del contenedor flex de la fila — sin `flex:none`, así que se encogía y el botón salía
 * aplastado. Cortar el evento acá deja al pin como hijo directo de la fila, con su propio layout,
 * y hace que la regla valga en cualquier lugar donde se lo use.
 */
export function Pin({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      className={`pin ${on ? 'on' : ''}`}
      type="button"
      onClick={(evento: MouseEvent) => {
        evento.stopPropagation()
        onClick()
      }}
      title={on ? 'Fijado' : 'Fijar'}
      aria-pressed={on}
    >
      <Icon name="pin" />
    </button>
  )
}
