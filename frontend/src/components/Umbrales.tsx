import { useCallback, useEffect, useState } from 'react'

import { ACTIVOS, simboloDe } from '@/lib/activos'
import { borrarUmbral, crearUmbral, obtenerUmbrales } from '@/lib/api'
import type { UmbralJSON } from '@/lib/api'
import { precio } from '@/lib/formato'
import { useFichas } from '@/lib/resumen'

/**
 * Los precios que pediste vigilar, configurables desde la pantalla (paso 3.6).
 *
 * Es la única configuración del MVP que se toca acá, y tiene sentido que sea justo esta: las
 * otras tres alertas las calibramos con datos históricos, pero "avísame si BTC pasa de 70.000"
 * no sale de ningún dato — sale de que a ti te importa ese número.
 *
 * ## Después de crear o borrar se vuelve a preguntar
 * La respuesta del POST ya trae el umbral creado y sería tentador agregarlo a la lista y listo.
 * Se vuelve a pedir igual, porque la lista que responde el backend es **la copia en memoria que
 * mira el detector con cada operación**: si un umbral aparece acá, está siendo vigilado de
 * verdad. Armar la lista por nuestra cuenta mostraría lo que creemos que pasó en vez de lo que
 * está pasando, y son cosas distintas cuando algo falla.
 */
export function Umbrales() {
  const [umbrales, setUmbrales] = useState<UmbralJSON[]>([])
  const [cargadoAlgunaVez, setCargadoAlgunaVez] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const [simbolo, setSimbolo] = useState(ACTIVOS[0].par)
  const [valor, setValor] = useState('')
  const [direccion, setDireccion] = useState<'arriba' | 'abajo'>('arriba')
  const [nota, setNota] = useState('')

  const fichas = useFichas([simbolo])
  const precioActual = fichas[0]?.precio ?? null

  const refrescar = useCallback(async (senal?: AbortSignal) => {
    try {
      const respuesta = await obtenerUmbrales(senal)
      setUmbrales(respuesta.umbrales)
      setCargadoAlgunaVez(respuesta.cargado_alguna_vez)
      setError(null)
    } catch (fallo) {
      if (senal?.aborted) return
      setError(fallo instanceof Error ? fallo.message : 'No se pudieron traer los umbrales')
    }
  }, [])

  useEffect(() => {
    const control = new AbortController()
    refrescar(control.signal)
    return () => control.abort()
  }, [refrescar])

  const agregar = async (evento: React.FormEvent) => {
    evento.preventDefault()
    setGuardando(true)
    try {
      await crearUmbral({ simbolo, valor, direccion, nota: nota.trim() || undefined })
      setValor('')
      setNota('')
      setError(null)
      await refrescar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo crear el umbral')
    } finally {
      setGuardando(false)
    }
  }

  const quitar = async (id: number) => {
    try {
      await borrarUmbral(id)
      await refrescar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo borrar el umbral')
    }
  }

  return (
    <div className="panel">
      <div className="pulse-h">
        <h3>Precios que vigilas</h3>
        <span className="mono-l stamp">{umbrales.length} ACTIVOS</span>
      </div>

      <form className="umbral-form" onSubmit={agregar}>
        <select value={simbolo} onChange={(e) => setSimbolo(e.target.value)}>
          {ACTIVOS.map((activo) => (
            <option key={activo.par} value={activo.par}>
              {activo.simbolo}
            </option>
          ))}
        </select>

        <select
          value={direccion}
          onChange={(e) => setDireccion(e.target.value as 'arriba' | 'abajo')}
        >
          <option value="arriba">si sube de</option>
          <option value="abajo">si baja de</option>
        </select>

        <input
          type="number"
          step="any"
          min="0"
          required
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          /* El precio de ahora va en el marcador de posición para no tener que ir a buscarlo
             a otra parte: un umbral se pone en relación a dónde está el precio hoy. */
          placeholder={precioActual !== null ? String(Math.round(precioActual)) : 'precio'}
        />

        <input
          className="nota"
          type="text"
          maxLength={200}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="para qué lo pones (opcional)"
        />

        <button type="submit" disabled={guardando || !valor}>
          {guardando ? 'guardando…' : 'vigilar'}
        </button>
      </form>

      {error && <p className="vacio">{error}</p>}

      {/* Con la base caída al arrancar, una lista vacía no quiere decir "no tienes ninguno":
          quiere decir que Argos todavía no pudo leerlos. La diferencia importa, porque en un
          caso no te está vigilando nada y en el otro no lo sabemos. */}
      {!cargadoAlgunaVez && (
        <p className="vacio">
          Argos todavía no pudo leer tus umbrales de la base. Esta lista puede estar incompleta.
        </p>
      )}

      {cargadoAlgunaVez && umbrales.length === 0 && !error && (
        <p className="vacio">
          No vigilas ningún precio todavía. Las otras tres alertas funcionan igual: estas son las
          que pones tú.
        </p>
      )}

      {umbrales.map((umbral) => (
        <div className="umbral" key={umbral.id}>
          <span className="dir">
            {simboloDe(umbral.simbolo)} {umbral.direccion === 'arriba' ? '↑' : '↓'}
          </span>
          {/* El backend manda `63100.00000000` porque así sale de la base y ahí el número es
              exacto. Para leerlo se formatea como cualquier otro precio del panel; el valor sin
              tocar sigue estando en la respuesta de la API. */}
          <span className="val">{precio(Number(umbral.valor))}</span>
          <span className="nota">{umbral.nota ?? ''}</span>
          <button
            type="button"
            className="quitar"
            onClick={() => quitar(umbral.id)}
            title="Dejar de vigilar este precio"
          >
            quitar
          </button>
        </div>
      ))}
    </div>
  )
}
