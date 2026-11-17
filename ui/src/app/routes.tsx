import { Navigate, createBrowserRouter } from 'react-router-dom'
import { ActivityPage } from '../features/activity/ActivityPage'
import { ChatPage } from '../features/chat/ChatPage'
import { PendingPage } from '../features/pending/PendingPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { Shell } from './Shell'

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: '/', element: <Navigate to="/chat" replace /> },
      { path: '/chat', element: <ChatPage /> },
      { path: '/chat/:id', element: <ChatPage /> },
      { path: '/pending', element: <PendingPage /> },
      { path: '/activity', element: <ActivityPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])
