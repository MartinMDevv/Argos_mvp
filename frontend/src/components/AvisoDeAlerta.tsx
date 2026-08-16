import { useEffect, useState } from 'react'

import { simboloDe } from '@/lib/activos'
import { TONO_POR_SEVERIDAD, useAlertas } from '@/lib/alertas'

/** Cuánto se queda el cartel antes de irse solo. */
const SEGUNDOS_VISIBLE = 12_000

/**
 * El cartel que aparece cuando Argos ve algo, estés donde estés en la app (paso 4.2).
 *
 * Hasta ahora había que estar mirando el recuadro del Panel, y encima esperar al refresco: la
 * alerta llegaba hasta diez segundos tarde y solo si estabas en la vista correcta. Esto es lo
 * mínimo para que Argos te encuentre a ti dentro de la app; salir de la pantalla —Telegram— es
 * el paso 4.1.
 *
 * ## Se va solo, y se puede cerrar
 * Doce segundos alcanzan para leerlo sin que quede tapando el panel. **No hay cola de carteles**:
 * si llegan tres alertas seguidas se muestra la última, porque apilar avisos en pantalla es
 * justo el tipo de ruido que el resto del proyecto se esfuerza en evitar. Las otras no se
 * pierden: están en el feed y en la vista Alertas, que es donde se miran las cosas con calma.
 */
export function AvisoDeAlerta({ verAlertas }: { verAlertas: () => void }) {
  const { ultimaLlegada, descartarAviso } = useAlertas()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!ultimaLlegada) return

    setVisible(true)
    const reloj = setTimeout(() => setVisible(false), SEGUNDOS_VISIBLE)
    return () => clearTimeout(reloj)
  }, [ultimaLlegada])

  if (!ultimaLlegada || !visible) return null

  const tono = TONO_POR_SEVERIDAD[ultimaLlegada.severidad] ?? 'lo'

  return (
    <div className={`aviso ${tono}`} role="status" aria-live="polite">
      <div className="aviso-cab">
        <span className="pip" />
        <b>{ultimaLlegada.titulo}</b>
        <span className="meta">{simboloDe(ultimaLlegada.simbolo)} · recién</span>
        <button
          type="button"
          className="aviso-x"
          onClick={() => {
            setVisible(false)
            descartarAviso()
          }}
          aria-label="Cerrar el aviso"
        >
          ×
        </button>
      </div>
      <p>{ultimaLlegada.detalle}</p>
      <button
        type="button"
        className="lnk"
        onClick={() => {
          setVisible(false)
          verAlertas()
        }}
      >
        ver la cuenta
      </button>
    </div>
  )
}
