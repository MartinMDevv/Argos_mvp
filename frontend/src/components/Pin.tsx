import { Icon } from './Icon'

// Botón de fijar (favorito) en recuadro cuadrado con borde redondeado.
export function Pin({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      className={`pin ${on ? 'on' : ''}`}
      type="button"
      onClick={onClick}
      title={on ? 'Fijado' : 'Fijar'}
    >
      <Icon name="pin" />
    </button>
  )
}
