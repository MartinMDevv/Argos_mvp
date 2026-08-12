// Logos oficiales de las monedas (Bitcoin / Ethereum) como SVG inline.
// Se usan en watchlist, tabla, menú, cabecera y chat.

const LOGOS: Record<string, string> = {
  BTC: '<circle cx="16" cy="16" r="16" fill="#F7931A"/><path fill="#fff" d="M21.6 14.1c.25-1.7-1.04-2.6-2.8-3.2l.57-2.3-1.4-.35-.56 2.24c-.37-.09-.75-.18-1.13-.26l.56-2.26-1.4-.35-.57 2.3c-.3-.07-.6-.14-.9-.21v-.01l-1.93-.48-.37 1.5s1.04.24 1.02.25c.57.14.67.52.65.82l-1.57 6.3c-.07.17-.24.43-.63.33.01.02-1.02-.26-1.02-.26l-.7 1.6 1.82.46c.34.08.67.17 1 .26l-.58 2.32 1.4.35.57-2.3c.38.1.75.2 1.11.29l-.57 2.29 1.4.35.58-2.32c2.39.45 4.19.27 4.94-1.9.61-1.74-.03-2.75-1.29-3.4.92-.22 1.61-.82 1.8-2.07zm-3.22 4.5c-.43 1.74-3.36.8-4.31.56l.76-3.06c.95.24 4.01.71 3.55 2.5zm.43-4.53c-.4 1.58-2.83.78-3.62.58l.69-2.78c.79.2 3.34.57 2.93 2.2z"/>',
  ETH: '<circle cx="16" cy="16" r="16" fill="#627EEA"/><g fill="#fff"><polygon fill-opacity=".6" points="16,4 16,12.87 23.5,16.22"/><polygon points="16,4 8.5,16.22 16,12.87"/><polygon fill-opacity=".6" points="16,21.97 16,27.99 23.5,17.62"/><polygon points="16,27.99 16,21.97 8.5,17.62"/><polygon fill-opacity=".2" points="16,20.57 23.5,16.22 16,12.88"/><polygon fill-opacity=".6" points="8.5,16.22 16,20.57 16,12.88"/></g>',
}

// Un objeto por símbolo, creado una sola vez. React compara `dangerouslySetInnerHTML` por
// identidad del objeto, así que armarlo dentro del render haría que reescribiera el SVG en cada
// pasada — acá no se nota (los logos no se animan), pero son dos SVG reconstruidos por fila cada
// medio segundo. La explicación larga de por qué esto importa está en `Peacock.tsx`.
const HTML: Record<string, { __html: string }> = Object.fromEntries(
  Object.entries(LOGOS).map(([sym, svg]) => [sym, { __html: svg }]),
)

const VACIO = { __html: '' }

export function CoinLogo({ sym, className = '' }: { sym: string; className?: string }) {
  return (
    <svg
      className={`coin ${className}`}
      viewBox="0 0 32 32"
      aria-hidden="true"
      dangerouslySetInnerHTML={HTML[sym] ?? VACIO}
    />
  )
}
