import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: inject Authorization header
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => Promise.reject(error)
)

// Response interceptor: handle 401
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient

// API helpers
export const authApi = {
  login: (email: string, password: string, totpCode?: string) =>
    apiClient.post<{ access_token: string; token_type: string; user: { id: string; email: string } }>(
      '/auth/login',
      { email, password, totp_code: totpCode }
    ),
  logout: () => apiClient.post('/auth/logout'),
  me: () => apiClient.get<{ id: string; email: string }>('/auth/me'),
}

export const strategiesApi = {
  list: () => apiClient.get<Strategy[]>('/strategies'),
  get: (id: string) => apiClient.get<Strategy>(`/strategies/${id}`),
  create: (data: CreateStrategyPayload) => apiClient.post<Strategy>('/strategies', data),
  update: (id: string, data: Partial<CreateStrategyPayload>) =>
    apiClient.put<Strategy>(`/strategies/${id}`, data),
  delete: (id: string) => apiClient.delete(`/strategies/${id}`),
  toggle: (id: string, active: boolean) =>
    apiClient.patch<Strategy>(`/strategies/${id}/toggle`, { active }),
  emergencyStop: (id: string) =>
    apiClient.post(`/strategies/${id}/emergency-stop`),
  emergencyStopAll: () => apiClient.post('/strategies/emergency-stop-all'),
}

export const ordersApi = {
  list: (params?: { page?: number; limit?: number; symbol?: string; status?: string }) =>
    apiClient.get<{ items: Order[]; total: number; page: number; limit: number }>('/orders', { params }),
}

export const portfolioApi = {
  get: () => apiClient.get<PortfolioItem[]>('/portfolio'),
  summary: () => apiClient.get<PortfolioSummary>('/portfolio/summary'),
}

export const aiApi = {
  list: (params?: { page?: number; limit?: number }) =>
    apiClient.get<{ items: AiAdvice[]; total: number }>('/ai/advice', { params }),
  stats: () => apiClient.get<AiStats>('/ai/stats'),
}

export const exchangeApi = {
  list: () => apiClient.get<ExchangeAccount[]>('/exchanges'),
  create: (data: CreateExchangePayload) => apiClient.post<ExchangeAccount>('/exchanges', data),
  delete: (id: string) => apiClient.delete(`/exchanges/${id}`),
}

export const chartApi = {
  candles: (symbol: string, interval: string, limit?: number) =>
    apiClient.get<CandleData[]>('/market/candles', {
      params: { symbol, interval, limit: limit ?? 200 },
    }),
  price: (symbol: string) =>
    apiClient.get<{ symbol: string; price: number; change_24h: number }>(`/market/price/${symbol}`),
}

export const dashboardApi = {
  summary: () =>
    apiClient.get<{
      active_strategies: number
      trades_today: number
      profit_today: number
      profit_today_pct: number
    }>('/dashboard/summary'),
  recentOrders: () => apiClient.get<Order[]>('/dashboard/recent-orders'),
  marketPrices: () =>
    apiClient.get<Array<{ symbol: string; price: number; change_24h: number }>>('/dashboard/market-prices'),
}

export const twoFactorApi = {
  setup: () => apiClient.post<{ secret: string; qr_code: string }>('/auth/2fa/setup'),
  verify: (code: string) => apiClient.post('/auth/2fa/verify', { code }),
  disable: (code: string) => apiClient.post('/auth/2fa/disable', { code }),
}

// Shared types
export interface Strategy {
  id: string
  name: string
  symbol: string
  active: boolean
  ai_mode: boolean
  priority: number
  created_at: string
  updated_at: string
  description?: string
  parameters?: Record<string, unknown>
}

export interface CreateStrategyPayload {
  name: string
  symbol: string
  ai_mode: boolean
  priority: number
  description?: string
  parameters?: Record<string, unknown>
}

export interface Order {
  id: string
  symbol: string
  side: 'buy' | 'sell'
  order_type: string
  status: string
  price?: number | null
  quantity: number
  filled_quantity?: number
  average_fill_price?: number | null
  fee?: number
  created_at: string
  updated_at?: string
  strategy_id?: string | null
}

export interface PortfolioItem {
  symbol: string
  quantity: number
  avg_buy_price: number
  current_price: number
  value: number
  pnl: number
  pnl_pct: number
}

export interface PortfolioSummary {
  total_value: number
  total_pnl: number
  total_pnl_pct: number
  cash_balance: number
}

export interface AiAdvice {
  id: string
  symbol: string
  decision: 'execute' | 'hold' | 'avoid'
  confidence: number
  risk_level: 'low' | 'medium' | 'high'
  reason: string
  created_at: string
  executed: boolean
  result_pnl?: number
}

export interface AiStats {
  total_advice: number
  execute_count: number
  hold_count: number
  avoid_count: number
  executed_pnl: number
  ai_win_rate: number
}

export interface ExchangeAccount {
  id: string
  exchange: string
  api_key: string
  testnet: boolean
  created_at: string
  active: boolean
}

export interface CreateExchangePayload {
  exchange: string
  api_key: string
  api_secret: string
  testnet: boolean
}

export interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}
