import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import Layout from '@/components/Layout'
import LoginPage from '@/pages/Login'
import DashboardPage from '@/pages/Dashboard'
import StrategiesPage from '@/pages/Strategies'
import OrdersPage from '@/pages/Orders'
import PortfolioPage from '@/pages/Portfolio'
import BacktestPage from '@/pages/Backtest'
import AiAdvicePage from '@/pages/AiAdvice'
import ExchangesPage from '@/pages/Exchanges'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated() ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="backtest" element={<BacktestPage />} />
        <Route path="ai-advice" element={<AiAdvicePage />} />
        <Route path="exchanges" element={<ExchangesPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
