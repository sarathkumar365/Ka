import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { routes } from '../../app/routes'

const signedOut = { user: null, username: null, min_password: 10, username_rule: '^[a-z][a-z0-9_-]{2,31}$' }

function renderAt(path: string) {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(signedOut), { headers: { 'content-type': 'application/json' } })),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

afterEach(() => vi.unstubAllGlobals())

test('signed-out visitors land on the home screen with both ways in', async () => {
  const router = renderAt('/chat')
  expect(await screen.findByRole('link', { name: 'Create account' })).toHaveProperty('pathname', '/signup')
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveProperty('pathname', '/login')
  expect(router.state.location.pathname).toBe('/welcome')
})

test('sign-up and sign-in link to each other', async () => {
  renderAt('/signup')
  expect(await screen.findByRole('link', { name: 'Sign in' })).toHaveProperty('pathname', '/login')
  renderAt('/login')
  expect(await screen.findByRole('link', { name: 'Create an account' })).toHaveProperty('pathname', '/signup')
})
