import { create } from 'zustand'
import { authApi } from '@/api/client'

interface User {
  id: string
  email: string
}

interface AuthState {
  token: string | null
  user: User | null
  isLoading: boolean
  error: string | null
  login: (email: string, password: string, totpCode?: string) => Promise<void>
  logout: () => void
  isAuthenticated: () => boolean
  clearError: () => void
}

const getInitialToken = (): string | null => {
  try {
    return localStorage.getItem('token')
  } catch {
    return null
  }
}

const getInitialUser = (): User | null => {
  try {
    const raw = localStorage.getItem('user')
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getInitialToken(),
  user: getInitialUser(),
  isLoading: false,
  error: null,

  login: async (email: string, password: string, totpCode?: string) => {
    set({ isLoading: true, error: null })
    try {
      const res = await authApi.login(email, password, totpCode)
      const { access_token, user } = res.data
      localStorage.setItem('token', access_token)
      localStorage.setItem('user', JSON.stringify(user))
      set({ token: access_token, user, isLoading: false })
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : '로그인에 실패했습니다.'
      set({ error: message, isLoading: false })
      throw err
    }
  },

  logout: () => {
    authApi.logout().catch(() => {
      // ignore logout errors
    })
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    set({ token: null, user: null })
    window.location.href = '/login'
  },

  isAuthenticated: () => {
    const { token } = get()
    return token !== null
  },

  clearError: () => set({ error: null }),
}))
