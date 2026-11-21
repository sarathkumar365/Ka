import { Navigate, type RouteObject, createBrowserRouter } from 'react-router-dom'
import { ActivityPage } from '../features/activity/ActivityPage'
import { LoginPage } from '../features/auth/LoginPage'
import { SignedOut } from '../features/auth/SignedOut'
import { SignupPage } from '../features/auth/SignupPage'
import { WelcomePage } from '../features/auth/WelcomePage'
import { ChatPage } from '../features/chat/ChatPage'
import { LoopsPage } from '../features/loops/LoopsPage'
import { OnboardingPage } from '../features/onboarding/OnboardingPage'
import { PendingPage } from '../features/pending/PendingPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { Shell } from './Shell'

export const routes: RouteObject[] = [
  { path: '/welcome', element: <SignedOut><WelcomePage /></SignedOut> },
  { path: '/signup', element: <SignedOut><SignupPage /></SignedOut> },
  { path: '/login', element: <SignedOut><LoginPage /></SignedOut> },
  {
    element: <Shell />,
    children: [
      { path: '/', element: <Navigate to="/chat" replace /> },
      { path: '/chat', element: <ChatPage /> },
      { path: '/chat/:id', element: <ChatPage /> },
      { path: '/pending', element: <PendingPage /> },
      { path: '/activity', element: <ActivityPage /> },
      { path: '/onboarding', element: <OnboardingPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '/loops', element: <LoopsPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
