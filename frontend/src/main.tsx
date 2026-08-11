import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ProveedorMercado } from '@/lib/mercado'

// El proveedor va acá arriba de todo a propósito: así hay UNA sola conexión con el backend
// para toda la app, y no se cae ni se reconecta cuando el usuario cambia de vista.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProveedorMercado>
      <App />
    </ProveedorMercado>
  </StrictMode>,
)
