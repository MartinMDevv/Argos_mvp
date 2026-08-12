import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ProveedorMercado } from '@/lib/mercado'
import { ProveedorResumen } from '@/lib/resumen'

// Los dos proveedores van acá arriba de todo a propósito: así hay UNA sola conexión WebSocket y
// UN solo pedido periódico de resumen para toda la app, y ninguno se cae ni se reinicia cuando
// el usuario cambia de vista.
//
// El orden importa: el resumen combina sus datos con el precio vivo del WebSocket, así que tiene
// que quedar por dentro para poder leerlo.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProveedorMercado>
      <ProveedorResumen>
        <App />
      </ProveedorResumen>
    </ProveedorMercado>
  </StrictMode>,
)
