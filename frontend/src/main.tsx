import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ProveedorMercado } from '@/lib/mercado'
import { ProveedorResumen } from '@/lib/resumen'
import { ProveedorAlertas } from '@/lib/alertas'
import { ProveedorChat } from '@/lib/chat'

// Los proveedores van acá arriba de todo a propósito: así hay UNA sola conexión WebSocket, UN
// solo pedido periódico de resumen y UNO de alertas para toda la app, y ninguno se cae ni se
// reinicia cuando el usuario cambia de vista.
//
// El orden importa: el resumen combina sus datos con el precio vivo del WebSocket, así que tiene
// que quedar por dentro para poder leerlo. Las alertas no dependen de ninguno de los dos, pero
// van dentro igual para que el árbol tenga un solo lugar donde mirar.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProveedorMercado>
      <ProveedorResumen>
        <ProveedorAlertas>
          {/* El chat va por dentro de todos: arma sus respuestas con los precios, el resumen y
              las alertas, así que necesita poder leerlos. */}
          <ProveedorChat>
            <App />
          </ProveedorChat>
        </ProveedorAlertas>
      </ProveedorResumen>
    </ProveedorMercado>
  </StrictMode>,
)
