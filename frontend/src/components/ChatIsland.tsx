import { useEffect, useRef, useState } from 'react'
import { Peacock } from './Peacock'
import { Icon } from './Icon'
import { Radar } from './illustrations/Radar'

interface Msg { who: 'you' | 'argos'; html: string; time: string; typing?: boolean }

const hora = () => new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })

// Chat con Argos: isla acoplada a la derecha. Estado vacío ilustrado + demo + envío.
export function ChatIsland({ close }: { close: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [msgs])

  function loadDemo() {
    setMsgs([
      { who: 'you', html: '¿Cómo viene el mercado ahora?', time: hora() },
      { who: 'argos', time: hora(), html: 'Ahora: BTC en <b class="n">$64.284</b> (<span class="n">+1,84%</span> hoy) y ETH en <b>$3.412</b> (<span class="d">−0,62%</span>). Lo llamativo: pico de volumen en BTC de <b>3,4σ</b> sobre su media de 24 h, hace 2 min.' },
      { who: 'you', html: '¿Cuál va a subir mañana?', time: hora() },
      { who: 'argos', time: hora(), html: 'No hay dato para eso: no proyecto precios ni invento probabilidades. Te muestro lo que pasa ahora y te aviso si algo se sale de lo normal.<span class="guard">✦ Regla de oro: sin dato, digo “no hay dato”.</span>' },
    ])
  }

  function send() {
    const t = text.trim()
    if (!t) return
    const esc = t.replace(/</g, '&lt;')
    setMsgs(m => [...m,
      { who: 'you', html: esc, time: hora() },
      { who: 'argos', html: 'escribiendo…', time: hora(), typing: true },
    ])
    setText('')
    setTimeout(() => {
      setMsgs(m => {
        const c = [...m]
        const last = c[c.length - 1]
        if (last?.typing) {
          c[c.length - 1] = { ...last, typing: false, html: '(Maqueta) En la app real leo los datos en vivo y respondo con números reales. Sin dato, digo “no hay dato”.' }
        }
        return c
      })
    }, 700)
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
          <button type="button" title="Sacar como ventana (pronto)"><Icon name="external" /></button>
          <button type="button" title="Cerrar" onClick={close}><Icon name="arrowRight" /></button>
        </div>
      </div>

      <div className="msgs" ref={listRef}>
        {msgs.length === 0 ? (
          <div className="chat-empty">
            <Radar className="ce-iso" />
            <div className="t">Pregúntale a Argos sobre el mercado</div>
            <div className="s">Te explica en palabras lo que dicen los datos.<br />Nunca inventa números.</div>
            <button className="listen" type="button" onClick={loadDemo}>Ver conversación de ejemplo</button>
          </div>
        ) : (
          msgs.map((m, i) => (
            <div className={`m ${m.typing ? 'typing' : ''}`} key={i}>
              {m.who === 'you'
                ? <div className="av you">Tú</div>
                : <div className="av"><Peacock size={16} /></div>}
              <div>
                <div className="who">{m.who === 'you' ? 'Tú' : 'Argos'} <span>{m.time}</span></div>
                <div className="body" dangerouslySetInnerHTML={{ __html: m.html }} />
              </div>
            </div>
          ))
        )}
      </div>

      <div className="chat-in">
        <div className="chat-box">
          <input
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') send() }}
            placeholder="Pregúntale a Argos…"
            aria-label="Mensaje para Argos"
          />
          <div className="chat-tools">
            <Icon name="plus" />
            <Icon name="format" />
            <Icon name="mic" />
            <span className="send" onClick={send}><Icon name="send" /></span>
          </div>
        </div>
      </div>
    </aside>
  )
}
