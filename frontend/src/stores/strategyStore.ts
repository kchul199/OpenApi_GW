import { create } from 'zustand'
import { strategiesApi, type Strategy, type CreateStrategyPayload } from '@/api/client'

interface StrategyState {
  strategies: Strategy[]
  isLoading: boolean
  error: string | null
  fetchStrategies: () => Promise<void>
  createStrategy: (data: CreateStrategyPayload) => Promise<Strategy>
  updateStrategy: (id: string, data: Partial<CreateStrategyPayload>) => Promise<void>
  deleteStrategy: (id: string) => Promise<void>
  toggleStrategy: (id: string, active: boolean) => Promise<void>
  emergencyStop: (id: string) => Promise<void>
  emergencyStopAll: () => Promise<void>
  clearError: () => void
}

export const useStrategyStore = create<StrategyState>((set, get) => ({
  strategies: [],
  isLoading: false,
  error: null,

  fetchStrategies: async () => {
    set({ isLoading: true, error: null })
    try {
      const res = await strategiesApi.list()
      set({ strategies: res.data, isLoading: false })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '전략을 불러오는데 실패했습니다.'
      set({ error: message, isLoading: false })
    }
  },

  createStrategy: async (data: CreateStrategyPayload) => {
    const res = await strategiesApi.create(data)
    set((state) => ({ strategies: [...state.strategies, res.data] }))
    return res.data
  },

  updateStrategy: async (id: string, data: Partial<CreateStrategyPayload>) => {
    const res = await strategiesApi.update(id, data)
    set((state) => ({
      strategies: state.strategies.map((s) => (s.id === id ? res.data : s)),
    }))
  },

  deleteStrategy: async (id: string) => {
    await strategiesApi.delete(id)
    set((state) => ({
      strategies: state.strategies.filter((s) => s.id !== id),
    }))
  },

  toggleStrategy: async (id: string, active: boolean) => {
    const res = await strategiesApi.toggle(id, active)
    set((state) => ({
      strategies: state.strategies.map((s) => (s.id === id ? res.data : s)),
    }))
  },

  emergencyStop: async (id: string) => {
    await strategiesApi.emergencyStop(id)
    set((state) => ({
      strategies: state.strategies.map((s) =>
        s.id === id ? { ...s, active: false } : s
      ),
    }))
  },

  emergencyStopAll: async () => {
    await strategiesApi.emergencyStopAll()
    set((state) => ({
      strategies: state.strategies.map((s) => ({ ...s, active: false })),
    }))
  },

  clearError: () => set({ error: null }),
}))

// Selector helpers
export const selectActiveStrategies = (state: StrategyState) =>
  state.strategies.filter((s) => s.active)

export const selectStrategyById = (id: string) => (state: StrategyState) =>
  state.strategies.find((s) => s.id === id)
