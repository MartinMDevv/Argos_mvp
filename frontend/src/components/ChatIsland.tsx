import { useEffect, useRef, useState } from 'react'

import { horaDe, useChat } from '@/lib/chat'
import { Peacock } from './Peacock'
import { Icon } from './Icon'
import { Radar } from './illustrations/Radar'

/**
 * Chat con Argos: la isla acoplada a la derecha.
 *
 * Es la ventana **rápida** a la conversación: preguntar sin dejar de mirar el gráfico. Para leer
 * con calma está la sección Chat a pantalla completa (`ChatView`), y las dos comparten los
 * mensajes (`lib/chat.tsx`) — cambiar de una a otra no empieza de cero.
 *
 * Qué responde Argos hoy y por qué no finge más que eso: ver el encabezado de `lib/chat.tsx`.
 */
export function ChatIsland({ close, verSeccion }: { close: () => void; verSeccion: () => void }) {
  const { mensajes, preguntar, contarEstado } = useChat()
  const [texto, setTexto] = useState('')
  const listaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listaRef.current) listaRef.current.scrollTop = listaRef.current.scrollHeight
  }, [mensajes])

  const enviar = () => {
    preguntar(texto)
    setTexto('')
  }

  return (
    <aside className="chat-island">
      <div className="chat-h">
        <Peacock size={22} />
        <div>
          <div className="ttl">Chat con Argos</div>
          <div className="sub">te explica el mercado</div>
        </div>
        <div className="acts">
          {/* Antes acá había un "Sacar como ventana (pronto)" que no hacía nada. Ahora lleva a
              la sección completa, que es lo que ese botón prometía. */}
          <button type="button" title="Abrir en la sección Chat" onClick={verSeccion}>
            <Icon name="external" />
          </button>
          <button type="button" title="Cerrar" onClick={close}>
            <Icon name="arrowRight" />
          </button>
        </div>
      </div>

      <div className="msgs" ref={listaRef}>
        {mensajes.length === 0 ? (
          <div className="chat-empty">
            <Radar className="ce-iso" />
            <div className="t">Pregúntale a Argos sobre el mercado</div>
            <div className="s">
              Conversar llega con la IA local (Fase 5).
              <br />
              Por ahora te muestro los números que tengo.
            </div>
            <button className="listen" type="button" onClick={contarEstado}>
              Ver lo que sé ahora
            </button>
          </div>
        ) : (
          <>
            {mensajes.map((mensaje, i) => (
              <div className="m" key={i}>
                {mensaje.quien === 'tu' ? (
                  <div className="av you">Tú</div>
                ) : (
                  <div className="av">
                    <Peacock size={16} />
                  </div>
                )}
                <div>
                  <div className="who">
                    {mensaje.quien === 'tu' ? 'Tú' : 'Argos'} <span>{horaDe(mensaje.momento)}</span>
                  </div>
                  <div className="body cuerpo-texto">{mensaje.texto}</div>
                </div>
              </div>
            ))}
            <p className="guard-nota">
              ✦ Lo escribió la app con los datos que tiene, no un modelo de lenguaje.
            </p>
          </>
        )}
      </div>

      <div className="chat-in">
        <div className="chat-box">
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') enviar()
            }}
            placeholder="Pregúntale a Argos…"
            aria-label="Mensaje para Argos"
          />
          <div className="chat-tools">
            <button type="button" className="send" onClick={enviar} aria-label="Enviar">
              <Icon name="send" />
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
