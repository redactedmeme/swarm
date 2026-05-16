import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  sessionId: string | null
  setAuth: (token: string, sessionId: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      sessionId: null,
      setAuth: (token, sessionId) => {
        localStorage.setItem('rc_token', token)
        localStorage.setItem('rc_session', sessionId)
        set({ token, sessionId })
      },
      logout: () => {
        localStorage.removeItem('rc_token')
        localStorage.removeItem('rc_session')
        set({ token: null, sessionId: null })
      },
    }),
    { name: 'rc-auth', partialize: (s) => ({ token: s.token, sessionId: s.sessionId }) },
  ),
)
