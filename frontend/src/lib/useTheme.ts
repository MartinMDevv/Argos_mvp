import { useEffect, useState } from 'react'

// Tema claro/oscuro. Por defecto oscuro (dark-first: torre de vigilancia).
// Escribe data-theme en <html>, que es lo que leen los tokens del CSS.
export function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const toggle = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  return { theme, toggle }
}
