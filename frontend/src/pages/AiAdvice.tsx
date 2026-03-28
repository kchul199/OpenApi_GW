import { useEffect, useState } from 'react'
import { aiApi, AiAdvice, AiStats } from '@/api/client'
import { RefreshCw } from 'lucide-react'

const REC_STYLE: Record<string, string> = {
  execute: 'bg-emerald-900/40 text-emerald-400',
  hold:    'bg-yellow-900/40 text-yellow-400',
  cancel:  'bg-red-900/40 text-red-400',
}

const REC_LABELS: Record<string, string> = {
  execute: '실행',
  hold:    '보류',
  cancel:  '취소',
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function AiAdvicePage() {
  const [items, setItems] = useState<AiAdvice[]>([])
  const [stats, setStats] = useState<AiStats | null>(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const LIMIT = 20

  async function load(off = 0) {
    setLoading(true)
    try {
      const [advRes, statRes] = await Promise.all([
        aiApi.list({ limit: LIMIT, offset: off }),
        aiApi.stats(),
      ])
      const adv = advRes.data as unknown as { items: AiAdvice[]; total: number }
      setItems(adv.items ?? [])
      setTotal(adv.total ?? 0)
      setStats(statRes.data as unknown as AiStats)
      setOffset(off)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">AI 자문 이력</h1>
        <button
          onClick={() => load(offset)}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />새로고침
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard label="총 자문" value={stats.total_advice} />
          <StatCard label="실행" value={stats.execute_count} />
          <StatCard label="보류" value={stats.hold_count} />
          <StatCard label="취소" value={stats.cancel_count} />
          <StatCard label="오류" value={stats.error_count} />
          <StatCard
            label="평균 신뢰도"
            value={`${(stats.avg_confidence * 100).toFixed(1)}%`}
          />
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 py-20 text-center text-gray-500">
          AI 자문 이력이 없습니다.
        </div>
      ) : (
        <>
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500">
                  <th className="px-5 py-3 text-left font-medium">전략 ID</th>
                  <th className="px-4 py-3 text-left font-medium">추천</th>
                  <th className="px-4 py-3 text-left font-medium">신뢰도</th>
                  <th className="px-4 py-3 text-left font-medium">추론</th>
                  <th className="px-4 py-3 text-left font-medium">일시</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {items.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-800/50">
                    <td className="px-5 py-3 text-gray-400 font-mono text-xs">
                      {c.strategy_id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-3">
                      {c.is_error ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-red-900/40 text-red-400">오류</span>
                      ) : (
                        <span className={`text-xs px-2 py-0.5 rounded ${REC_STYLE[c.recommendation] ?? 'bg-gray-800 text-gray-400'}`}>
                          {REC_LABELS[c.recommendation] ?? c.recommendation}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-300">
                      {c.is_error ? '-' : `${(c.confidence * 100).toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">
                      {c.reasoning ?? '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                      {new Date(c.created_at).toLocaleString('ko-KR')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>총 {total}건</span>
            <div className="flex gap-2">
              <button
                disabled={offset === 0}
                onClick={() => load(Math.max(0, offset - LIMIT))}
                className="px-3 py-1.5 rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors"
              >
                이전
              </button>
              <button
                disabled={offset + LIMIT >= total}
                onClick={() => load(offset + LIMIT)}
                className="px-3 py-1.5 rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors"
              >
                다음
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
