import { useEffect, useRef, useState } from 'react'

import { SUGERENCIAS, horaDe, useChat } from '@/lib/chat'
import { Peacock } from './Peacock'
import { Icon } from './Icon'
import { Radar } from './illustrations/Radar'

/**
 * La sección Chat: conversar con Argos en toda la pantalla (paso 4.4).
 *
 * Convive con la isla de la derecha y no la reemplaza, porque resuelven cosas distintas: la isla
 * es para preguntar **sin dejar de mirar** el gráfico, y esta sección es para leer con calma una
 * respuesta larga —el estado del mercado son varias líneas de números— sin que entre en una
 * columna de 360 píxeles.
 *
 * Las dos leen la **misma conversación** (`lib/chat.tsx`): cambiar de una a otra no borra nada ni
 * empieza de cero, que es lo que pasaría si cada una guardara sus propios mensajes.
 */
export function ChatView() {
  const { mensajes, preguntar, contarEstado, limpiar } = useChat()
  const [texto, setTexto] = useState('')
  const finRef = useRef<HTMLDivElement>(null)

  // Cada mensaje nuevo baja la vista: en una conversación, lo último es lo que importa.
  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes])

  const enviar = () => {
    preguntar(texto)
    setTexto('')
  }

  return (
    <div className="chatv">
      <div className="chatv-h">
        <Peacock size={26} />
        <div className="chatv-t">
          <h3>Chat con Argos</h3>
          <span>te explica lo que ve, con los números delante</span>
        </div>
        {mensajes.length > 0 && (
          <button type="button" className="lnk" onClick={limpiar}>
            limpiar
          </button>
        )}
      </div>

      <div className="chatv-msgs">
        {mensajes.length === 0 ? (
          <div className="chatv-vacio">
            <Radar className="ce-iso" />
            <h4>Pregúntale a Argos sobre el mercado</h4>
            <p>
              Conversar de verdad llega con la IA local (Fase 5). Por ahora te cuento lo que tengo
              medido: precios, cuánto se está moviendo cada activo y qué vi en la última hora.
              <br />
              <b>Nunca invento números.</b>
            </p>
            <div className="chatv-sug">
              {SUGERENCIAS.map((sugerencia) => (
                <button
                  key={sugerencia}
                  type="button"
                  className="chip"
                  onClick={() => preguntar(sugerencia)}
                >
                  {sugerencia}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {mensajes.map((mensaje, i) => (
              <div className={`chatv-m ${mensaje.quien}`} key={i}>
                <div className="av">
                  {mensaje.quien === 'tu' ? 'Tú' : <Peacock size={18} />}
                </div>
                <div className="chatv-cuerpo">
                  <div className="who">
                    {mensaje.quien === 'tu' ? 'Tú' : 'Argos'} <span>{horaDe(mensaje.momento)}</span>
                  </div>
                  {/* Texto plano con saltos de línea respetados: sin `innerHTML`, que
                      convertiría en marcado lo que uno escriba. */}
                  <div className="texto cuerpo-texto">{mensaje.texto}</div>
                </div>
              </div>
            ))}
            <p className="guard-nota">
              ✦ Esto lo escribió la app con los datos que tiene, no un modelo de lenguaje. Sin
              dato, dice “no hay dato”.
            </p>
          </>
        )}
        <div ref={finRef} />
      </div>

      <div className="chatv-in">
        <button type="button" className="chip" onClick={contarEstado} title="Sin escribir nada">
          Contarme el estado ahora
        </button>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') enviar()
          }}
          placeholder="Pregúntale a Argos…"
          aria-label="Mensaje para Argos"
        />
        <button type="button" className="enviar" onClick={enviar} aria-label="Enviar">
          <Icon name="send" />
        </button>
      </div>
    </div>
  )
}
