import { useEffect, useState } from 'react'
import { strategiesApi, Strategy } from '@/api/client'
import { Play, Pause, AlertTriangle, RefreshCw, Plus, Trash2 } from 'lucide-react'

const AI_MODE_LABELS: Record<string, string> = {
  '0': '비활성',
  '1': '자문',
  '2': '자동',
  off: '비활성',
  advisory: '자문',
  auto: '자동',
}

type StrategyExt = Strategy & {
  is_active: boolean
  is_paused: boolean
  emergency_stopped: boolean
  timeframe: string
  condition_tree: object
  order_config: object
  ai_mode: string | number
  priority: number
}

function StatusBadge({ s }: { s: StrategyExt }) {
  if (s.emergency_stopped)
    return <span className="text-xs px-2 py-0.5 rounded bg-red-900/40 text-red-400">긴급정지</span>
  if (!s.is_active)
    return <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-500">비활성</span>
  if (s.is_paused)
    return <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/40 text-yellow-400">일시정지</span>
  return <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-400">실행 중</span>
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyExt[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const res = await strategiesApi.list()
      setStrategies((res.data as unknown as StrategyExt[]) ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function withAction(id: string, fn: () => Promise<unknown>) {
    setActionLoading(id)
    try {
      await fn()
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setActionLoading(null)
    }
  }

  async function handleActivate(s: StrategyExt) {
    if (s.is_active && !s.is_paused) {
      await withAction(s.id, () => fetch(`/api/v1/strategies/${s.id}/pause`, { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }))
    } else {
      await withAction(s.id, () => fetch(`/api/v1/strategies/${s.id}/activate`, { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }))
    }
  }

  async function handleEmergencyStop(id: string) {
    await withAction(id, () => strategiesApi.emergencyStop(id))
  }

  async function handleDelete(id: string) {
    if (!confirm('전략을 삭제하시겠습니까?')) return
    await withAction(id, () => strategiesApi.delete(id))
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">전략 관리</h1>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            새로고침
          </button>
          <button className="flex items-center gap-1.5 text-sm bg-emerald-500 hover:bg-emerald-400 text-white px-3 py-1.5 rounded-lg transition-colors">
            <Plus className="w-3.5 h-3.5" />
            전략 추가
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : strategies.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 py-20 text-center text-gray-500">
          등록된 전략이 없습니다.
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500">
                <th className="px-5 py-3 text-left font-medium">전략명</th>
                <th className="px-4 py-3 text-left font-medium">심볼</th>
                <th className="px-4 py-3 text-left font-medium">타임프레임</th>
                <th className="px-4 py-3 text-left font-medium">AI 모드</th>
                <th className="px-4 py-3 text-left font-medium">상태</th>
                <th className="px-4 py-3 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {strategies.map((s) => {
                const busy = actionLoading === s.id
                return (
                  <tr key={s.id} className="hover:bg-gray-800/50">
                    <td className="px-5 py-3">
                      <div className="font-medium text-white">{s.name}</div>
                      <div className="text-xs text-gray-500">우선순위 {s.priority}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-300 font-mono">{s.symbol}</td>
                    <td className="px-4 py-3 text-gray-400">{s.timeframe}</td>
                    <td className="px-4 py-3 text-gray-400">
                      {AI_MODE_LABELS[String(s.ai_mode)] ?? String(s.ai_mode)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge s={s} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {!s.emergency_stopped && (
                          <button
                            disabled={busy}
                            onClick={() => handleActivate(s)}
                            title={s.is_active && !s.is_paused ? '일시정지' : '활성화'}
                            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                          >
                            {s.is_active && !s.is_paused ? (
                              <Pause className="w-4 h-4" />
                            ) : (
                              <Play className="w-4 h-4" />
                            )}
                          </button>
                        )}
                        {!s.emergency_stopped && (
                          <button
                            disabled={busy}
                            onClick={() => handleEmergencyStop(s.id)}
                            title="긴급정지"
                            className="p-1.5 rounded hover:bg-red-900/40 text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50"
                          >
                            <AlertTriangle className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          disabled={busy}
                          onClick={() => handleDelete(s.id)}
                          title="삭제"
                          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
