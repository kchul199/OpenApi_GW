import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi, ordersApi, strategiesApi, Order, Strategy } from '@/api/client'
import { TrendingUp, TrendingDown, Activity, Layers, ClipboardList, DollarSign } from 'lucide-react'
import { format } from 'date-fns'

function StatCard({
  label,
  value,
  sub,
  positive,
  icon: Icon,
}: {
  label: string
  value: string
  sub?: string
  positive?: boolean
  icon: React.ElementType
}) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400">{label}</span>
        <Icon className="w-4 h-4 text-gray-600" />
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && (
        <div
          className={`text-xs mt-1 ${
            positive === undefined
              ? 'text-gray-500'
              : positive
              ? 'text-emerald-400'
              : 'text-red-400'
          }`}
        >
          {sub}
        </div>
      )}
    </div>
  )
}

const STATUS_COLOR: Record<string, string> = {
  closed: 'text-emerald-400',
  open: 'text-blue-400',
  canceled: 'text-gray-500',
  rejected: 'text-red-400',
  partially_filled: 'text-yellow-400',
}

export default function DashboardPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [portfolioValue, setPortfolioValue] = useState<number>(0)
  const [totalPnl, setTotalPnl] = useState<number>(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [strats, ords, portfolio] = await Promise.allSettled([
          strategiesApi.list(),
          ordersApi.list({ limit: 5 } as Parameters<typeof ordersApi.list>[0]),
          portfolioApi.summary(),
        ])
        if (strats.status === 'fulfilled') setStrategies(strats.value.data as unknown as Strategy[])
        if (ords.status === 'fulfilled') {
          const data = ords.value.data
          setOrders(Array.isArray(data) ? data : (data as { items: Order[] }).items ?? [])
        }
        if (portfolio.status === 'fulfilled') {
          const data = portfolio.value.data as { total_usdt_value?: number; total_pnl?: number }
          setPortfolioValue(data.total_usdt_value ?? 0)
          setTotalPnl(data.total_pnl ?? 0)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const activeStrategies = strategies.filter((s) => (s as unknown as { is_active: boolean }).is_active)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">대시보드</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="포트폴리오 총액"
          value={`$${portfolioValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          icon={DollarSign}
        />
        <StatCard
          label="실현 손익"
          value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`}
          positive={totalPnl >= 0}
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          label="활성 전략"
          value={String(activeStrategies.length)}
          sub={`전체 ${strategies.length}개`}
          icon={Layers}
        />
        <StatCard
          label="오늘 주문"
          value={String(orders.length)}
          icon={Activity}
        />
      </div>

      {/* Recent Orders */}
      <div className="bg-gray-900 rounded-xl border border-gray-800">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-gray-400" />
            최근 주문
          </h2>
          <Link to="/orders" className="text-xs text-emerald-400 hover:text-emerald-300">
            전체보기 →
          </Link>
        </div>
        {orders.length === 0 ? (
          <div className="px-5 py-10 text-center text-gray-500 text-sm">주문 내역이 없습니다.</div>
        ) : (
          <div className="divide-y divide-gray-800">
            {orders.slice(0, 5).map((order) => (
              <div key={order.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      order.side === 'buy'
                        ? 'bg-emerald-900/40 text-emerald-400'
                        : 'bg-red-900/40 text-red-400'
                    }`}
                  >
                    {order.side.toUpperCase()}
                  </span>
                  <div>
                    <div className="text-sm font-medium text-white">{order.symbol}</div>
                    <div className="text-xs text-gray-500">
                      {format(new Date(order.created_at), 'MM/dd HH:mm')}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-white">
                    {Number(order.quantity).toFixed(6)}
                  </div>
                  <div className={`text-xs ${STATUS_COLOR[order.status] ?? 'text-gray-400'}`}>
                    {order.status}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Strategies */}
      <div className="bg-gray-900 rounded-xl border border-gray-800">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-gray-400" />
            활성 전략
          </h2>
          <Link to="/strategies" className="text-xs text-emerald-400 hover:text-emerald-300">
            관리 →
          </Link>
        </div>
        {activeStrategies.length === 0 ? (
          <div className="px-5 py-10 text-center text-gray-500 text-sm">
            활성화된 전략이 없습니다.
          </div>
        ) : (
          <div className="divide-y divide-gray-800">
            {activeStrategies.map((s) => (
              <div key={s.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <div className="text-sm font-medium text-white">{s.name}</div>
                  <div className="text-xs text-gray-500">
                    {s.symbol} · {(s as unknown as { timeframe: string }).timeframe}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs text-emerald-400">실행 중</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
