// Logo de Argos: pavo real (cuerpo/cuello de cisne + cola de abanico que se abre).
// El SVG se genera con las mismas fórmulas del boceto. La animación de apertura
// vive en el CSS (.peacock.anim ...) y corre al montar.

function buildPeacockInner(): string {
  // 12 plumas grandes + anillo interno corto de relleno
  const N = 12, spread = 150, mid = (N - 1) / 2
  let out = '', inn = ''
  for (let i = 0; i < N; i++) {
    const a = -spread + (i * (2 * spread)) / (N - 1), L = 41, tip = 56 - L, delay = Math.abs(i - mid) * 52
    out += `<g class="feather" style="transform:rotate(${a}deg);animation-delay:${delay}ms"><path class="stalk" style="stroke-width:1.7" d="M50 56 Q47 ${(56 + tip) / 2} 50 ${tip + 8}"/><ellipse class="plume" cx="50" cy="${tip + 5}" rx="8.6" ry="11"/><circle class="halo" cx="50" cy="${tip + 3.5}" r="4.3"/><circle class="iris" cx="50" cy="${tip + 3.5}" r="2.15"/></g>`
  }
  for (let i = 0; i < 8; i++) {
    const a = -138 + (i * (2 * 138)) / 7, L = 26, tip = 56 - L, delay = Math.abs(i - 3.5) * 52
    inn += `<g class="feather in" style="transform:rotate(${a}deg);animation-delay:${delay}ms"><ellipse class="plume" cx="50" cy="${tip + 5}" rx="6.6" ry="8.4"/></g>`
  }
  // cuerpo cisne + cuello en "?" (sube y se curva adelante) + pico negro
  const body = `<g class="bodyg">
    <path class="swan" d="M38.5 70 C 37.5 61.5 43 56.5 51 56 C 60.5 55.4 67 60.5 66.5 68 C 66 76.5 57.5 80.6 49.5 80.2 C 43.5 79.9 39.6 76.3 38.5 70 Z"/>
    <g class="headg">
      <path class="neck" d="M46.5 63 C 46.5 52 46 44.5 37.8 41.3"/>
      <circle class="head" cx="36.2" cy="40.6" r="4.9"/>
      <path class="beak" d="M31.6 40 l-6.2 1.9 l6.3 1.5z"/>
      <circle class="eyed" cx="37.3" cy="39.3" r="1.05"/>
      <path class="crest" d="M36.2 35.9 v-3.2 M34.1 36.2 l-1.4 -2.9 M38.3 36.2 l1.4 -2.9"/>
      <circle class="crest-d" cx="36.2" cy="31.6" r="1.1"/><circle class="crest-d" cx="32.5" cy="32.7" r="1"/><circle class="crest-d" cx="39.9" cy="32.7" r="1"/>
    </g></g>`
  return `<g class="tail">${inn}${out}</g>${body}`
}

// Se calcula una sola vez (el markup no depende de props).
const PEACOCK_INNER = buildPeacockInner()

export function Peacock({
  size = 100,
  anim = false,
  className = '',
}: { size?: number; anim?: boolean; className?: string }) {
  return (
    <svg
      className={`peacock ${anim ? 'anim' : ''} ${className}`}
      viewBox="0 0 100 100"
      style={{ width: size, height: size }}
      aria-label="Argos"
      dangerouslySetInnerHTML={{ __html: PEACOCK_INNER }}
    />
  )
}
