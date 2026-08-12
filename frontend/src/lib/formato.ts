/**
 * Cómo se escriben los números en Argos (paso 2.2b).
 *
 * ## Un solo lugar
 * Antes de este paso los números eran literales del boceto (`'$64.284'`, `'+1,84%'`) escritos a
 * mano en cada componente. Ahora vienen del backend y hay que darles forma, así que la decisión
 * de **cómo se ven** se toma acá y no en ocho archivos.
 *
 * ## Formato chileno
 * Punto para los miles y coma para los decimales (`63.825,87`), que es como se leen los números
 * en Chile. Lo hace `Intl.NumberFormat` con `es-CL`, no un `replace` a mano: el navegador ya
 * sabe hacerlo bien y gratis.
 *
 * ## El signo lo ponemos nosotros
 * `Intl` escribe el menos como guion (`-`). Acá se usa el **signo menos de verdad** (`−`, U+2212),
 * que es más ancho y se lee mejor al lado de un `+`. Por eso los porcentajes se formatean en
 * valor absoluto y el signo se antepone a mano.
 *
 * ## Y lo que no se sabe se dice
 * `SIN_DATO` es una raya, no un cero. Aparece cuando el backend mandó `null` —no había con qué
 * comparar— y es la traducción visual de la regla de oro: Argos no rellena huecos con números
 * que parecen ciertos.
 */

/** Lo que se muestra cuando no hay dato. Nunca un `0`, que se leería como "no se movió". */
export const SIN_DATO = '—'

const MILES = new Intl.NumberFormat('es-CL')

const decimales = (min: number, max: number) =>
  new Intl.NumberFormat('es-CL', { minimumFractionDigits: min, maximumFractionDigits: max })

const DOS = decimales(2, 2)
const UNO = decimales(1, 1)

/**
 * Un precio, con el detalle que ese precio merece.
 *
 * Los decimales se adaptan a la magnitud: a 63.825 dólares el octavo decimal es ruido, pero en
 * una moneda que vale 0,000004 los decimales **son** el precio. Hoy el MVP solo tiene BTC y ETH,
 * pero el norte del proyecto son las memecoins y ahí este detalle deja de ser cosmético.
 */
export function precio(valor: number): string {
  if (!Number.isFinite(valor)) return SIN_DATO
  const magnitud = Math.abs(valor)
  if (magnitud >= 1) return `$${DOS.format(valor)}`
  if (magnitud >= 0.01) return `$${decimales(4, 4).format(valor)}`
  return `$${decimales(2, 8).format(valor)}`
}

/** Una variación porcentual, con signo explícito: `+1,84%` / `−0,62%`. */
export function porcentaje(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return SIN_DATO
  return `${signoDe(valor)}${DOS.format(Math.abs(valor))}%`
}

/** Una diferencia de precio en plata, con signo: `+$1.164,20`. */
export function diferencia(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return SIN_DATO
  return `${signoDe(valor)}$${DOS.format(Math.abs(valor))}`
}

/**
 * Plata en forma corta: `$683,1 M`, `$1,2 B`.
 *
 * El volumen de un día son cientos de millones. Escrito entero no se lee ni se compara de un
 * vistazo, y en una tabla densa además no entra.
 */
export function dineroCorto(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return SIN_DATO
  const magnitud = Math.abs(valor)
  if (magnitud >= 1e9) return `$${UNO.format(valor / 1e9)} B`
  if (magnitud >= 1e6) return `$${UNO.format(valor / 1e6)} M`
  if (magnitud >= 1e3) return `$${UNO.format(valor / 1e3)} K`
  return `$${DOS.format(valor)}`
}

/** Una cantidad en su moneda base: `12.354,3 BTC`. */
export function cantidad(valor: number | null, unidad: string): string {
  if (valor === null || !Number.isFinite(valor)) return SIN_DATO
  return `${UNO.format(valor)} ${unidad}`
}

/**
 * Un rango, para el KPI de máximo y mínimo: `63,24K – 64,52K`.
 *
 * ## Por qué cifras significativas y no decimales fijos
 * La primera versión abreviaba con un decimal (`63,2K`). Con BTC se veía bien, pero el rango de
 * 24 h de ETH salía **`1,9K – 1,9K`**: dos números distintos redondeados al mismo texto. Un
 * rango cuyas dos puntas se ven iguales no informa nada — peor, sugiere que el precio no se movió.
 *
 * Con cifras significativas la precisión se adapta a la magnitud en vez de a la unidad, así que
 * el rango se sigue leyendo tanto en un activo de cinco dígitos como en uno de cuatro. Y por
 * debajo de mil se delega en `precio()`, que ya sabe cuántos decimales merece cada tamaño —
 * necesario para el día que Argos mire una moneda que vale 0,000004.
 */
export function rango(bajo: number | null, alto: number | null): string {
  if (bajo === null || alto === null) return SIN_DATO
  return `${corto(bajo)} – ${corto(alto)}`
}

const SIGNIFICATIVAS = new Intl.NumberFormat('es-CL', { maximumSignificantDigits: 4 })

/** Un precio abreviado, sin el `$`: `64,52K`, `912,30`, `0,0432`. */
function corto(valor: number): string {
  if (Math.abs(valor) >= 1000) return `${SIGNIFICATIVAS.format(valor / 1000)}K`
  return precio(valor).replace('$', '')
}

/** Un entero con separador de miles: `1.440`. */
export function entero(valor: number): string {
  return MILES.format(valor)
}

/**
 * Cuánto hace que pasó algo: `hace 3 s`, `hace 2 min`, `hace 4 h`, `hace 2 días`.
 *
 * Es la forma de que se note cuando un precio está viejo. Un número suelto no dice si es de hace
 * un segundo o de anteayer, y mostrar el precio de anteayer como si fuera el de ahora es
 * exactamente la clase de mentira que Argos no debe decir.
 */
export function antiguedad(iso: string, ahora = Date.now()): string {
  const segundos = Math.max(0, Math.round((ahora - new Date(iso).getTime()) / 1000))
  if (segundos < 60) return `hace ${segundos} s`
  const minutos = Math.round(segundos / 60)
  if (minutos < 60) return `hace ${minutos} min`
  const horas = Math.round(minutos / 60)
  if (horas < 24) return `hace ${horas} h`
  const dias = Math.round(horas / 24)
  return `hace ${dias} ${dias === 1 ? 'día' : 'días'}`
}

/** El signo que se antepone a un número: `+`, `−` (U+2212) o nada si es cero. */
function signoDe(valor: number): string {
  if (valor > 0) return '+'
  if (valor < 0) return '−'
  return ''
}

/**
 * La clase CSS que le corresponde a una variación: `up` (verde), `down` (rojo) o vacío.
 *
 * Verde y rojo se usan **solo para precio**, nunca para la marca ni para el estado de la app.
 * Es la regla de color de Argos: el campo es teal, la señal es oro, y el par verde/rojo queda
 * reservado para "subió/bajó" para que no pierda significado.
 */
export function direccion(valor: number | null): 'up' | 'down' | '' {
  if (valor === null || !Number.isFinite(valor) || valor === 0) return ''
  return valor > 0 ? 'up' : 'down'
}
