import { create } from 'zustand'
import { persist } from 'zustand/middleware'

function isTokenExpired(token: string | null): boolean {
  if (!token) return true
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return Date.now() / 1000 > (payload.exp ?? 0)
  } catch {
    return true
  }
}

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
    {
      name: 'rc-auth',
      partialize: (s) => ({ token: s.token, sessionId: s.sessionId }),
      onRehydrateStorage: () => (state) => {
        if (state && isTokenExpired(state.token)) {
          state.token = null
          state.sessionId = null
          localStorage.removeItem('rc_token')
          localStorage.removeItem('rc_session')
        }
      },
    },
  ),
)
