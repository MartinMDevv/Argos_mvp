/**
 * La curvita de precio que va en la watchlist y en la tabla (paso 2.2b).
 *
 * ## Por qué no podía quedarse en mock
 * Hasta este paso los puntos venían escritos a mano en `data/coins.ts`. Un número inventado ya
 * es malo; un **gráfico** inventado es peor, porque no se lee como un dato sino como una forma:
 * nadie verifica una curva, se la cree. Mostrar una subida dibujada a mano al lado de un precio
 * real es justo lo que Argos no debe hacer.
 *
 * ## De dónde salen los puntos
 * De `GET /mercado/velas`, el mismo endpoint del gráfico grande. Se piden pocas velas anchas
 * (24 de 1 h para el día, 42 de 4 h para la semana): una curva de 70 píxeles no distingue más
 * detalle que eso, y pedir 1.440 velas de 1 minuto para dibujar 70 píxeles sería mover mil veces
 * más datos de los que se ven.
 *
 * ## Si no hay datos no se dibuja nada
 * Sin velas —o con una sola, que no hace línea— el componente no pinta. No hay línea plana de
 * relleno: una recta horizontal diría "el precio no se movió", que es una afirmación, y acá lo
 * que pasa es que no sabemos.
 */

import { useEffect, useState } from 'react'

import { obtenerVelas } from '@/lib/api'
import type { Intervalo } from '@/lib/api'

interface Props {
  par: string
  intervalo: Intervalo
  limite: number
  /** Dimensiones del `viewBox`. La curva se estira al ancho real con `preserveAspectRatio`. */
  ancho: number
  alto: number
  className?: string
}

export function Sparkline({ par, intervalo, limite, ancho, alto, className = '' }: Props) {
  const [cierres, setCierres] = useState<number[]>([])

  useEffect(() => {
    const control = new AbortController()

    obtenerVelas(par, intervalo, limite, control.signal)
      .then((velas) => setCierres(velas.map((v) => Number(v.cierre))))
      // Un sparkline que no carga no es motivo para romper nada: se queda sin dibujar y ya.
      // El precio y el cambio %, que son los datos que importan de la fila, siguen ahí.
      .catch(() => {
        if (!control.signal.aborted) setCierres([])
      })

    return () => control.abort()
  }, [par, intervalo, limite])

  if (cierres.length < 2) return <svg className={className} viewBox={`0 0 ${ancho} ${alto}`} />

  const minimo = Math.min(...cierres)
  const maximo = Math.max(...cierres)
  // El recorrido puede ser cero si todas las velas cerraron al mismo precio. Sin esta guarda la
  // división daría NaN y el SVG no dibujaría nada; con ella sale una línea recta al medio, que
  // acá sí es la verdad: el precio efectivamente no se movió en ese tramo.
  const recorrido = maximo - minimo || 1

  const margen = 1.5
  const util = alto - margen * 2

  const puntos = cierres
    .map((cierre, i) => {
      const x = (i / (cierres.length - 1)) * ancho
      // El eje Y del SVG crece hacia abajo, así que el precio más alto va arriba (y menor).
      const y = margen + (1 - (cierre - minimo) / recorrido) * util
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  // El color lo decide el tramo completo: dónde terminó contra dónde empezó. Es la misma
  // pregunta que responde el porcentaje de al lado, así que los dos tienen que coincidir.
  const subio = cierres[cierres.length - 1] >= cierres[0]

  return (
    <svg className={className} viewBox={`0 0 ${ancho} ${alto}`} preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke={`var(${subio ? '--bull' : '--bear'})`}
        strokeWidth="1.6"
        vectorEffect="non-scaling-stroke"
        points={puntos}
      />
    </svg>
  )
}
