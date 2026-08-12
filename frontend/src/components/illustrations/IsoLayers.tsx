// Ilustración isométrica "capas" (historia de datos / hypertable).

// Objeto creado UNA vez, fuera del componente: React compara `dangerouslySetInnerHTML` por
// identidad, y uno nuevo en cada render hace que reescriba el SVG y se reinicie el dibujado.
// La explicación completa está en `Peacock.tsx`.
const INNER = {
  __html: `<g class="iso">
  <polygon points="20,20 45,7 70,20 45,33"/><polygon points="20,31 45,18 70,31 45,44"/>
  <polygon class="fillt" points="20,42 45,29 70,42 45,55"/>
  <path d="M20,20 v11 M70,20 v11 M45,33 v11 M20,31 v11 M70,31 v11 M45,44 v11"/>
</g>`,
}

export function IsoLayers({ className = 'isomini' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 90 56" dangerouslySetInnerHTML={INNER} />
}
