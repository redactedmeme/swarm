import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { useAuthStore } from '@/app/store/authStore'
import AppLayout from '@/app/components/Layout/AppLayout'
import LoginPage from '@/app/pages/LoginPage'
import ChatPage from '@/app/pages/ChatPage'
import DashboardPage from '@/app/pages/DashboardPage'
import AgentsPage from '@/app/pages/AgentsPage'
import ToolsPage from '@/app/pages/ToolsPage'
import SettingsPage from '@/app/pages/SettingsPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="chat"      element={<ChatPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="agents"    element={<AgentsPage />} />
          <Route path="tools"     element={<ToolsPage />} />
          <Route path="settings"  element={<SettingsPage />} />
        </Route>
      </Routes>
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: 'hsl(240 8% 7%)',
            border: '1px solid hsl(240 6% 14%)',
            color: 'hsl(240 5% 90%)',
          },
        }}
      />
    </BrowserRouter>
  )
}
