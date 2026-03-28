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
  activate: (id: string) => apiClient.post<Strategy>(`/strategies/${id}/activate`),
  pause: (id: string) => apiClient.post<Strategy>(`/strategies/${id}/pause`),
  emergencyStop: (id: string, reason?: string) =>
    apiClient.post(`/strategies/${id}/emergency-stop`, { reason: reason ?? 'manual' }),
  resume: (id: string) => apiClient.post<Strategy>(`/strategies/${id}/resume`),
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
  list: () => apiClient.get<ExchangeAccount[]>('/exchange/accounts'),
  create: (data: CreateExchangePayload) => apiClient.post<ExchangeAccount>('/exchange/accounts', data),
  delete: (id: string) => apiClient.delete(`/exchange/accounts/${id}`),
  supported: () => apiClient.get<{ exchanges: string[] }>('/exchange/supported'),
}

export const backtestApi = {
  list: (strategyId?: string) =>
    apiClient.get<{ items: BacktestResult[]; total: number }>('/backtest', {
      params: strategyId ? { strategy_id: strategyId } : undefined,
    }),
  create: (data: CreateBacktestPayload) => apiClient.post<BacktestResult>('/backtest', data),
  get: (id: string) => apiClient.get<BacktestResult>(`/backtest/${id}`),
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
  disable: (code: string) => apiClient.delete('/auth/2fa/disable', { data: { totp_code: code } }),
}

// Shared types
export interface Strategy {
  id: string
  user_id: string
  name: string
  symbol: string
  timeframe: string
  condition_tree: Record<string, unknown>
  order_config: Record<string, unknown>
  ai_mode: 'off' | 'advisory' | 'auto'
  priority: number
  is_active: boolean
  is_paused: boolean
  emergency_stopped: boolean
  total_trades: number
  total_pnl: number
  created_at: string
  updated_at: string
}

export interface CreateStrategyPayload {
  name: string
  symbol: string
  timeframe: string
  condition_tree: Record<string, unknown>
  order_config: Record<string, unknown>
  ai_mode: 'off' | 'advisory' | 'auto'
  priority: number
  hold_retry_interval?: number
  hold_max_retry?: number
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
  strategy_id: string
  recommendation: 'execute' | 'hold' | 'cancel'
  confidence: number
  reasoning: string
  is_error: boolean
  created_at: string
}

export interface AiStats {
  total_advice: number
  execute_count: number
  hold_count: number
  cancel_count: number
  error_count: number
  avg_confidence: number
}

export interface ExchangeAccount {
  id: string
  exchange_id: string
  label: string
  is_testnet: boolean
  is_active: boolean
  last_synced_at: string | null
  created_at: string
}

export interface CreateExchangePayload {
  exchange_id: string
  label: string
  api_key: string
  api_secret: string
  is_testnet: boolean
}

export interface BacktestResult {
  id: string
  strategy_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  from_date: string
  to_date: string
  total_return: number
  annualized_return: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  created_at: string
  completed_at?: string
  error_message?: string
}

export interface CreateBacktestPayload {
  strategy_id: string
  from_date: string
  to_date: string
  initial_capital: number
}

export interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}
