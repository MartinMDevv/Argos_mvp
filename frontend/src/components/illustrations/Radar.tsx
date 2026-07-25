// Ilustración isométrica "radar" (los cien ojos que vigilan).
// Las líneas se dibujan solas al aparecer (animación en el CSS .iso).

const INNER = `<g class="iso">
  <ellipse cx="75" cy="42" rx="58" ry="30"/><ellipse cx="75" cy="42" rx="38" ry="19.5"/><ellipse cx="75" cy="42" rx="18" ry="9.5"/>
  <path class="em" d="M75 42 L128 25"/><circle class="eye" cx="75" cy="42" r="3.4"/><path d="M75 12 v-4 M75 72 v4"/>
</g>`

export function Radar({ className = 'radar' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 150 78" dangerouslySetInnerHTML={{ __html: INNER }} />
}
