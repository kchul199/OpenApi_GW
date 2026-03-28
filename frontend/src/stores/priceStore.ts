import { create } from 'zustand'

interface PriceState {
  prices: Record<string, number>
  changes: Record<string, number> // 24h change %
  updatePrice: (symbol: string, price: number, change?: number) => void
  getPrice: (symbol: string) => number | undefined
}

export const usePriceStore = create<PriceState>((set, get) => ({
  prices: {},
  changes: {},

  updatePrice: (symbol: string, price: number, change?: number) => {
    set((state) => ({
      prices: { ...state.prices, [symbol]: price },
      changes:
        change !== undefined
          ? { ...state.changes, [symbol]: change }
          : state.changes,
    }))
  },

  getPrice: (symbol: string) => {
    return get().prices[symbol]
  },
}))
