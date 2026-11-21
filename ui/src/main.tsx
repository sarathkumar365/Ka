import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import { router } from './app/routes'
import { getTheme, setTheme } from './lib/theme'
import './styles.css'
import { watchKeyboard } from './lib/viewport'

setTheme(getTheme())
// autoUpdate: when a new service worker takes over, reload so an old cached screen never lingers.
// Unsent onboarding input is protected by its beforeunload prompt.
registerSW({ immediate: true })
const client = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, retry: 1 } } })

watchKeyboard(window)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
