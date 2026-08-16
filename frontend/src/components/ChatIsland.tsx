import { useEffect, useRef, useState } from 'react'

import { ACTIVOS, simboloDe } from '@/lib/activos'
import { useAlertas } from '@/lib/alertas'
import {
  SIN_DATO,
  antiguedad,
  medida,
  porcentaje,
  precio as formatearPrecio,
} from '@/lib/formato'
import { useFichas } from '@/lib/resumen'
import { useVolatilidad } from '@/lib/volatilidad'
import { Peacock } from './Peacock'
import { Icon } from './Icon'
import { Radar } from './illustrations/Radar'

interface Mensaje {
  quien: 'tu' | 'argos'
  /** Texto plano. Lo que Argos dice se arma acá con datos reales, nunca con HTML del usuario. */
  texto: string
  hora: string
}

const hora = () => new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })

/**
 * Chat con Argos: la isla de la derecha.
 *
 * ## Qué es y qué no es todavía
 * **Conversar de verdad llega en la Fase 5**, cuando Ollama corra el modelo local. Hasta
 * entonces esto no finge ser una IA: el botón arma una ficha con lo que Argos **sabe ahora
 * mismo** —precios, cambios, volatilidad, últimas alertas— y lo dice tal cual, aclarando que
 * lo escribió la app y no un modelo.
 *
 * La versión anterior mostraba una "conversación de ejemplo" con `$64.284` y `3,4σ` inventados.
 * Ese texto contradecía en la propia pantalla la regla que el chat decía respetar dos líneas más
 * abajo ("nunca invento números"). Ahora los números son los de verdad, o dice que no los tiene.
 */
export function ChatIsland({ close }: { close: () => void }) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [texto, setTexto] = useState('')
  const listaRef = useRef<HTMLDivElement>(null)

  const pares = ACTIVOS.map((activo) => activo.par)
  const fichas = useFichas(pares)
  const volatilidades = useVolatilidad(pares)
  const { alertas } = useAlertas()

  useEffect(() => {
    if (listaRef.current) listaRef.current.scrollTop = listaRef.current.scrollHeight
  }, [mensajes])

  /** Arma el estado del mercado con los datos que la app ya tiene cargados. */
  function resumenDeAhora(): string {
    // `useFichas` devuelve `null` para un activo del que Argos todavía no sabe nada: ausencia
    // de dato, no cero. Se dice y se sigue.
    const lineas = fichas.map((ficha, i) => {
      const simbolo = ACTIVOS[i].simbolo
      if (!ficha || ficha.precio === null) return `${simbolo}: sin datos todavía.`

      const cambio = ficha.cambios['24h']
      const vol = volatilidades[ficha.activo.par]

      return (
        `${simbolo}: ${formatearPrecio(ficha.precio)} ` +
        `(${cambio === null ? SIN_DATO : porcentaje(cambio)} en 24 h)` +
        (vol ? `, con un rango típico de ${medida(vol.tipico_pct)} cada 5 min.` : '.')
      )
    })

    const recientes = alertas.filter(
      (alerta) => Date.now() - new Date(alerta.momento).getTime() < 3600_000,
    )

    if (recientes.length === 0) {
      lineas.push('No vi nada fuera de lo normal en la última hora.')
    } else {
      lineas.push(`Vi ${recientes.length} ${recientes.length === 1 ? 'cosa' : 'cosas'} en la última hora:`)
      for (const alerta of recientes.slice(0, 3)) {
        lineas.push(
          `· ${alerta.titulo} en ${simboloDe(alerta.simbolo)} (${antiguedad(alerta.momento)}): ${alerta.detalle}`,
        )
      }
    }

    return lineas.join('\n')
  }

  function mostrarEstado() {
    setMensajes([
      { quien: 'tu', texto: '¿Cómo viene el mercado ahora?', hora: hora() },
      { quien: 'argos', texto: resumenDeAhora(), hora: hora() },
    ])
  }

  function enviar() {
    const pregunta = texto.trim()
    if (!pregunta) return

    setMensajes((previos) => [
      ...previos,
      { quien: 'tu', texto: pregunta, hora: hora() },
      {
        quien: 'argos',
        // Se responde lo único cierto: todavía no sé conversar. Fingir una respuesta con
        // plantillas sería peor que decirlo — el usuario creería que hay alguien pensando.
        texto:
          'Todavía no sé conversar: el modelo que va a leer los datos y responderte en ' +
          'palabras llega en la Fase 5. Mientras tanto puedo mostrarte el estado del mercado ' +
          'con los números que tengo — el botón "Ver lo que sé ahora" hace exactamente eso.',
        hora: hora(),
      },
    ])
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
          {/* Antes había acá un botón "Sacar como ventana (pronto)" que no hacía nada. */}
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
            <button className="listen" type="button" onClick={mostrarEstado}>
              Ver lo que sé ahora
            </button>
          </div>
        ) : (
          mensajes.map((mensaje, i) => (
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
                  {mensaje.quien === 'tu' ? 'Tú' : 'Argos'} <span>{mensaje.hora}</span>
                </div>
                {/* Texto plano y `white-space: pre-line`: sin `dangerouslySetInnerHTML`, que
                    era una puerta abierta a que lo que uno escriba se interprete como HTML. */}
                <div className="body cuerpo-texto">{mensaje.texto}</div>
              </div>
            </div>
          ))
        )}

        {mensajes.length > 0 && (
          <p className="guard-nota">
            ✦ Esto lo escribió la app con los datos que tiene, no un modelo de lenguaje. Sin
            dato, dice “no hay dato”.
          </p>
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
            {/* Los íconos de adjuntar, formato y micrófono no hacían nada: se fueron. */}
            <button type="button" className="send" onClick={enviar} aria-label="Enviar">
              <Icon name="send" />
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
