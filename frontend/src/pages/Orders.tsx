import { useEffect, useState } from 'react'
import { ordersApi, Order } from '@/api/client'
import { RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'
import { format } from 'date-fns'

const STATUS_STYLE: Record<string, string> = {
  closed: 'bg-emerald-900/40 text-emerald-400',
  open: 'bg-blue-900/40 text-blue-400',
  canceled: 'bg-gray-800 text-gray-500',
  rejected: 'bg-red-900/40 text-red-400',
  partially_filled: 'bg-yellow-900/40 text-yellow-400',
}

const LIMIT = 20

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')

  async function load() {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { limit: LIMIT, offset: page * LIMIT }
      if (statusFilter) params.status = statusFilter
      const res = await ordersApi.list(params as Parameters<typeof ordersApi.list>[0])
      const data = res.data
      if (Array.isArray(data)) {
        setOrders(data)
        setTotal(data.length)
      } else {
        const d = data as { items: Order[]; total: number }
        setOrders(d.items ?? [])
        setTotal(d.total ?? 0)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [page, statusFilter])

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">주문 내역</h1>
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(0) }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
          >
            <option value="">전체 상태</option>
            <option value="open">open</option>
            <option value="closed">closed</option>
            <option value="canceled">canceled</option>
            <option value="rejected">rejected</option>
            <option value="partially_filled">partially_filled</option>
          </select>
          <button
            onClick={load}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : orders.length === 0 ? (
          <div className="py-20 text-center text-gray-500 text-sm">주문 내역이 없습니다.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500">
                <th className="px-5 py-3 text-left font-medium">심볼</th>
                <th className="px-4 py-3 text-left font-medium">방향</th>
                <th className="px-4 py-3 text-left font-medium">유형</th>
                <th className="px-4 py-3 text-right font-medium">수량</th>
                <th className="px-4 py-3 text-right font-medium">체결가</th>
                <th className="px-4 py-3 text-left font-medium">상태</th>
                <th className="px-5 py-3 text-left font-medium">시각</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-gray-800/50">
                  <td className="px-5 py-3 font-mono text-white">{o.symbol}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded ${
                        o.side === 'buy'
                          ? 'bg-emerald-900/40 text-emerald-400'
                          : 'bg-red-900/40 text-red-400'
                      }`}
                    >
                      {o.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{o.order_type}</td>
                  <td className="px-4 py-3 text-right text-gray-200 font-mono">
                    {Number(o.quantity).toFixed(6)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-200 font-mono">
                    {o.average_fill_price
                      ? `$${Number(o.average_fill_price).toLocaleString()}`
                      : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        STATUS_STYLE[o.status] ?? 'bg-gray-800 text-gray-400'
                      }`}
                    >
                      {o.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-500 text-xs">
                    {format(new Date(o.created_at), 'yy/MM/dd HH:mm')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-800">
            <span className="text-xs text-gray-500">
              {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, total)} / {total}건
            </span>
            <div className="flex gap-1">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="p-1.5 rounded hover:bg-gray-800 text-gray-400 hover:text-white disabled:opacity-40"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="p-1.5 rounded hover:bg-gray-800 text-gray-400 hover:text-white disabled:opacity-40"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
