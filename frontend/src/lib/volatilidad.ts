/**
 * Cuánto se agita cada activo, para mostrarlo en el panel (paso 3.7).
 *
 * Del otro lado está `GET /mercado/volatilidad`, que devuelve el rango verdadero mediano de un
 * tramo de 5 minutos en las últimas 24 horas — la misma medida que usa la alerta #3.
 *
 * ## Se refresca despacio, y con razón
 * Es una mediana de 24 horas: no se mueve de un minuto al otro. Pedirla cada 10 segundos como el
 * resumen sería gastar pedidos para recibir el mismo número. Un minuto alcanza de sobra.
 */

import { useEffect, useState } from 'react'

import { obtenerVolatilidad } from './api'
import type { VolatilidadJSON } from './api'

const REFRESCO = 60_000

/**
 * La volatilidad de los pares pedidos. Un par que no esté en el resultado es un "no sé".
 *
 * `pares` se serializa para la dependencia del efecto: pasar el array directo relanzaría el
 * pedido en cada render, porque un array nuevo nunca es igual al anterior aunque diga lo mismo.
 */
export function useVolatilidad(pares: string[]): Record<string, VolatilidadJSON> {
  const [medidas, setMedidas] = useState<Record<string, VolatilidadJSON>>({})
  const clave = pares.join(',')

  useEffect(() => {
    if (!clave) return

    const control = new AbortController()
    let vivo = true

    const pedir = async () => {
      try {
        const nuevas = await obtenerVolatilidad(clave.split(','), control.signal)
        if (vivo) setMedidas(nuevas)
      } catch {
        // Sin volatilidad el panel muestra "—", que es exactamente lo que corresponde: no
        // sabemos. No hace falta un cartel de error para un dato secundario.
      }
    }

    pedir()
    const reloj = setInterval(pedir, REFRESCO)
    return () => {
      vivo = false
      clearInterval(reloj)
      control.abort()
    }
  }, [clave])

  return medidas
}
