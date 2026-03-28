import { useEffect, useState } from 'react'
import { backtestApi, strategiesApi, Strategy, BacktestResult, CreateBacktestPayload } from '@/api/client'
import { Plus, RefreshCw, X } from 'lucide-react'

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  pending:   { label: '대기',     cls: 'bg-gray-800 text-gray-400' },
  running:   { label: '실행 중',  cls: 'bg-blue-900/40 text-blue-400' },
  completed: { label: '완료',     cls: 'bg-emerald-900/40 text-emerald-400' },
  failed:    { label: '실패',     cls: 'bg-red-900/40 text-red-400' },
}

function pct(v: number | undefined) {
  if (v == null) return '-'
  return `${(v * 100).toFixed(2)}%`
}
function num(v: number | undefined, dp = 4) {
  if (v == null) return '-'
  return v.toFixed(dp)
}

// ── Submit Modal ──────────────────────────────────────────────────────────────

interface SubmitModalProps {
  strategies: Strategy[]
  onClose: () => void
  onSubmit: () => void
}

function SubmitModal({ strategies, onClose, onSubmit }: SubmitModalProps) {
  const today = new Date().toISOString().slice(0, 10)
  const monthAgo = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10)

  const [form, setForm] = useState<CreateBacktestPayload>({
    strategy_id: strategies[0]?.id ?? '',
    from_date: monthAgo,
    to_date: today,
    initial_capital: 10000,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof CreateBacktestPayload>(k: K, v: CreateBacktestPayload[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await backtestApi.create(form)
      onSubmit()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? '제출 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-base font-semibold text-white">백테스트 제출</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">전략 *</label>
            <select
              required
              value={form.strategy_id}
              onChange={(e) => set('strategy_id', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            >
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>{s.name} ({s.symbol})</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">시작일 *</label>
              <input
                type="date"
                required
                value={form.from_date}
                onChange={(e) => set('from_date', e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">종료일 *</label>
              <input
                type="date"
                required
                value={form.to_date}
                onChange={(e) => set('to_date', e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">초기 자본 (USDT) *</label>
            <input
              type="number"
              required
              min={100}
              value={form.initial_capital}
              onChange={(e) => set('initial_capital', Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            />
          </div>
          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white rounded-lg hover:bg-gray-800"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={saving || strategies.length === 0}
              className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {saving ? '제출 중...' : '제출'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Detail Panel ──────────────────────────────────────────────────────────────

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-800 rounded-lg px-4 py-3">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-sm font-semibold text-white">{value}</div>
    </div>
  )
}

function DetailPanel({ result }: { result: BacktestResult }) {
  return (
    <div className="mt-2 p-4 bg-gray-800/50 rounded-lg border border-gray-700 grid grid-cols-3 gap-3 sm:grid-cols-4">
      <MetricCard label="총 수익률" value={pct(result.total_return)} />
      <MetricCard label="연환산 수익률" value={pct(result.annualized_return)} />
      <MetricCard label="샤프 지수" value={num(result.sharpe_ratio, 2)} />
      <MetricCard label="소르티노 지수" value={num(result.sortino_ratio, 2)} />
      <MetricCard label="최대 낙폭" value={pct(result.max_drawdown)} />
      <MetricCard label="승률" value={pct(result.win_rate)} />
      <MetricCard label="수익 팩터" value={num(result.profit_factor, 2)} />
      <MetricCard label="총 거래 수" value={String(result.total_trades ?? '-')} />
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestResult[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const [bRes, sRes] = await Promise.all([backtestApi.list(), strategiesApi.list()])
      setResults((bRes.data as unknown as { items: BacktestResult[] }).items ?? [])
      setStrategies((sRes.data as unknown as Strategy[]) ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function handleSubmit() {
    setShowModal(false)
    load()
  }

  return (
    <div className="space-y-5">
      {showModal && (
        <SubmitModal
          strategies={strategies}
          onClose={() => setShowModal(false)}
          onSubmit={handleSubmit}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">백테스트</h1>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />새로고침
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 text-sm bg-emerald-500 hover:bg-emerald-400 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />새 백테스트
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : results.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 py-20 text-center text-gray-500">
          백테스트 결과가 없습니다.
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500">
                <th className="px-5 py-3 text-left font-medium">전략</th>
                <th className="px-4 py-3 text-left font-medium">기간</th>
                <th className="px-4 py-3 text-left font-medium">총수익률</th>
                <th className="px-4 py-3 text-left font-medium">샤프</th>
                <th className="px-4 py-3 text-left font-medium">MDD</th>
                <th className="px-4 py-3 text-left font-medium">상태</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {results.map((r) => {
                const st = STATUS_LABELS[r.status] ?? { label: r.status, cls: 'bg-gray-800 text-gray-400' }
                const isOpen = expanded === r.id
                return (
                  <>
                    <tr
                      key={r.id}
                      className="hover:bg-gray-800/50 cursor-pointer"
                      onClick={() => setExpanded(isOpen ? null : r.id)}
                    >
                      <td className="px-5 py-3">
                        <div className="text-white font-mono text-xs truncate max-w-[120px]">
                          {strategies.find((s) => s.id === r.strategy_id)?.name ?? r.strategy_id.slice(0, 8)}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {r.from_date?.slice(0, 10)} ~ {r.to_date?.slice(0, 10)}
                      </td>
                      <td className="px-4 py-3 text-gray-300">{pct(r.total_return)}</td>
                      <td className="px-4 py-3 text-gray-300">{num(r.sharpe_ratio, 2)}</td>
                      <td className="px-4 py-3 text-gray-300">{pct(r.max_drawdown)}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded ${st.cls}`}>{st.label}</span>
                      </td>
                    </tr>
                    {isOpen && r.status === 'completed' && (
                      <tr key={`${r.id}-detail`}>
                        <td colSpan={6} className="px-5 pb-4">
                          <DetailPanel result={r} />
                        </td>
                      </tr>
                    )}
                    {isOpen && r.status === 'failed' && (
                      <tr key={`${r.id}-err`}>
                        <td colSpan={6} className="px-5 pb-4">
                          <p className="text-xs text-red-400 bg-red-900/20 rounded px-3 py-2 mt-2">
                            {r.error_message ?? '알 수 없는 오류'}
                          </p>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
