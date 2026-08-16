/**
 * Conexión del panel con el WebSocket de Argos (paso 2.1).
 *
 * Del otro lado está `WS /ws/mercado` (paso 1.4): el panel se conecta una vez y el backend le
 * avisa cuando cambia algo. Esto es la contraparte en el navegador.
 *
 * ## Por qué un contexto y no un hook suelto
 * Si cada componente que necesita precios abriera su propio socket, tendríamos una conexión por
 * gráfico, otra por watchlist, otra por tabla — y todas se caerían y reconectarían cada vez que
 * el usuario cambia de vista, porque React desmonta lo que deja de mostrar. **Una sola conexión
 * arriba del todo**, y todos leen de ahí.
 *
 * ## La misma lección que nos dio Binance, ahora de este lado
 * En el paso 1.1 casi nos ganamos un baneo por reconectar sin esperar. Acá pasa lo mismo un
 * escalón más abajo: si el backend está apagado y el panel reintenta en bucle, el navegador
 * gasta CPU y llena la consola de errores. Misma receta —esperar cada vez más— y el mismo
 * detalle que allá: **si la conexión duró bien, la espera se resetea**, porque una caída aislada
 * después de una hora sana no merece castigo.
 *
 * ## Por qué no guardamos un historial de mensajes
 * Solo interesa el ÚLTIMO estado de cada símbolo. Acumular mensajes sería una fuga de memoria
 * lenta y no serviría de nada: la historia ya está en TimescaleDB, que es su lugar.
 */

import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { URL_WS } from './api'
import type { AlertaJSON, EstadoSimbolo, MensajeMercado } from './api'

/** Primera espera antes de reintentar. Se va duplicando si el backend sigue sin responder. */
const ESPERA_INICIAL = 1_000

/** Techo de la espera. Más que esto es hacer esperar al usuario cuando el backend ya volvió. */
const ESPERA_MAXIMA = 30_000

/** A partir de acá consideramos que la conexión fue sana y la espera vuelve a cero. */
const CONEXION_SANA = 60_000

export interface Mercado {
  /** Último estado conocido de cada símbolo. Vacío hasta que llegue la `bienvenida`. */
  simbolos: Record<string, EstadoSimbolo>
  /** `true` mientras el socket está abierto. Sirve para no mostrar datos viejos como si fueran vivos. */
  conectado: boolean
}

const ContextoMercado = createContext<Mercado>({ simbolos: {}, conectado: false })

/**
 * Quién quiere enterarse de una alerta apenas llega (paso 4.2).
 *
 * El socket es uno solo y lo maneja este archivo, así que las alertas entran por acá aunque
 * de ellas se ocupe `alertas.tsx`. En vez de meter las alertas en el estado del mercado —que
 * es la foto de precios y no tiene nada que ver—, se reparten a quien se anote. Así el
 * proveedor de mercado no sabe qué se hace con ellas y el de alertas no sabe de sockets.
 */
type OyenteDeAlerta = (alerta: AlertaJSON) => void

const oyentes = new Set<OyenteDeAlerta>()

/** Se anota para recibir cada alerta que llegue. Devuelve la función para darse de baja. */
export function alLlegarAlerta(oyente: OyenteDeAlerta): () => void {
  oyentes.add(oyente)
  return () => {
    oyentes.delete(oyente)
  }
}

export function ProveedorMercado({ children }: { children: ReactNode }) {
  const [simbolos, setSimbolos] = useState<Record<string, EstadoSimbolo>>({})
  const [conectado, setConectado] = useState(false)

  useEffect(() => {
    let socket: WebSocket | null = null
    let temporizador: number | undefined
    let espera = ESPERA_INICIAL

    // React en modo estricto monta, desmonta y vuelve a montar en desarrollo. Sin esta bandera,
    // el socket del primer montaje reprogramaría reconexiones para siempre.
    let desmontado = false

    const conectar = () => {
      if (desmontado) return

      const abierto = Date.now()
      socket = new WebSocket(`${URL_WS}/ws/mercado`)

      socket.onopen = () => setConectado(true)

      socket.onmessage = (evento) => {
        let mensaje: MensajeMercado
        try {
          mensaje = JSON.parse(evento.data)
        } catch {
          // Un mensaje ilegible no debe tumbar el panel: se ignora y seguimos escuchando.
          return
        }

        // El latido no trae datos, solo demuestra que Argos sigue mirando.
        if (mensaje.tipo === 'latido') return

        // Una alerta no es una foto del mercado: no toca `simbolos` y se reparte aparte.
        if (mensaje.tipo === 'alerta') {
          for (const oyente of oyentes) oyente(mensaje.alerta)
          return
        }

        setSimbolos(mensaje.simbolos)
      }

      // No hace falta manejar `onerror` aparte: el navegador siempre dispara `onclose`
      // después, así que toda la reconexión vive en un solo lugar.
      socket.onclose = () => {
        setConectado(false)
        if (desmontado) return

        if (Date.now() - abierto > CONEXION_SANA) espera = ESPERA_INICIAL

        temporizador = setTimeout(conectar, espera)
        espera = Math.min(espera * 2, ESPERA_MAXIMA)
      }
    }

    conectar()

    return () => {
      desmontado = true
      clearTimeout(temporizador)
      socket?.close()
    }
  }, [])

  return (
    <ContextoMercado.Provider value={{ simbolos, conectado }}>{children}</ContextoMercado.Provider>
  )
}

/** El mercado completo: todos los símbolos + si la conexión está viva. */
export function useMercado(): Mercado {
  return useContext(ContextoMercado)
}

/**
 * El estado de un símbolo puntual, o `null` si Argos todavía no vio ninguna operación suya.
 *
 * Devolver `null` es deliberado: es la forma de decir "no hay dato" sin inventar un precio en
 * cero, que en un gráfico se vería como un desplome.
 */
export function useSimbolo(simbolo: string): EstadoSimbolo | null {
  const { simbolos } = useMercado()
  return simbolos[simbolo] ?? null
}
