import { useEffect, useState } from 'react'
import { strategiesApi, Strategy, CreateStrategyPayload } from '@/api/client'
import { Play, Pause, AlertTriangle, RefreshCw, Plus, Trash2, Edit2, RotateCcw, X } from 'lucide-react'

const AI_MODE_LABELS: Record<string, string> = {
  off: '비활성',
  advisory: '자문',
  auto: '자동',
}

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
const AI_MODES = ['off', 'advisory', 'auto'] as const

// ── Modal ────────────────────────────────────────────────────────────────────

type ModalMode = 'create' | 'edit'

interface StrategyModalProps {
  mode: ModalMode
  initial?: Strategy
  onClose: () => void
  onSave: () => void
}

const BLANK: CreateStrategyPayload = {
  name: '',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  condition_tree: {},
  order_config: { type: 'market', quantity: 0.001 },
  ai_mode: 'off',
  priority: 5,
  hold_retry_interval: 30,
  hold_max_retry: 3,
}

function StrategyModal({ mode, initial, onClose, onSave }: StrategyModalProps) {
  const [form, setForm] = useState<CreateStrategyPayload>(
    initial
      ? {
          name: initial.name,
          symbol: initial.symbol,
          timeframe: initial.timeframe,
          condition_tree: initial.condition_tree,
          order_config: initial.order_config,
          ai_mode: initial.ai_mode,
          priority: initial.priority,
        }
      : BLANK
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // condition_tree and order_config are stored as JSON strings in the textarea
  const [conditionJson, setConditionJson] = useState(
    JSON.stringify(form.condition_tree, null, 2)
  )
  const [orderJson, setOrderJson] = useState(
    JSON.stringify(form.order_config, null, 2)
  )

  function set<K extends keyof CreateStrategyPayload>(key: K, val: CreateStrategyPayload[K]) {
    setForm((f) => ({ ...f, [key]: val }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    let cTree: Record<string, unknown>
    let oConfig: Record<string, unknown>
    try {
      cTree = JSON.parse(conditionJson)
      oConfig = JSON.parse(orderJson)
    } catch {
      setError('조건 트리 또는 주문 설정의 JSON 형식이 올바르지 않습니다.')
      return
    }

    const payload: CreateStrategyPayload = { ...form, condition_tree: cTree, order_config: oConfig }
    setSaving(true)
    try {
      if (mode === 'create') {
        await strategiesApi.create(payload)
      } else if (initial) {
        await strategiesApi.update(initial.id, payload)
      }
      onSave()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? '저장 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-base font-semibold text-white">
            {mode === 'create' ? '전략 추가' : '전략 편집'}
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">전략명 *</label>
            <input
              required
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              placeholder="My Strategy"
            />
          </div>

          {/* Symbol + Timeframe */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">심볼 *</label>
              <input
                required
                value={form.symbol}
                onChange={(e) => set('symbol', e.target.value.toUpperCase())}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500"
                placeholder="BTC/USDT"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">타임프레임 *</label>
              <select
                value={form.timeframe}
                onChange={(e) => set('timeframe', e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
          </div>

          {/* AI Mode + Priority */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">AI 모드</label>
              <select
                value={form.ai_mode}
                onChange={(e) => set('ai_mode', e.target.value as 'off' | 'advisory' | 'auto')}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              >
                {AI_MODES.map((m) => (
                  <option key={m} value={m}>{AI_MODE_LABELS[m]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">우선순위 (1–10)</label>
              <input
                type="number"
                min={1}
                max={10}
                value={form.priority}
                onChange={(e) => set('priority', Number(e.target.value))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Hold retry */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">보류 재시도 간격(초)</label>
              <input
                type="number"
                min={1}
                value={form.hold_retry_interval ?? 30}
                onChange={(e) => set('hold_retry_interval', Number(e.target.value))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">최대 재시도 횟수</label>
              <input
                type="number"
                min={1}
                value={form.hold_max_retry ?? 3}
                onChange={(e) => set('hold_max_retry', Number(e.target.value))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Condition Tree */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">조건 트리 (JSON)</label>
            <textarea
              rows={4}
              value={conditionJson}
              onChange={(e) => setConditionJson(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-emerald-500 resize-none"
            />
          </div>

          {/* Order Config */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">주문 설정 (JSON)</label>
            <textarea
              rows={3}
              value={orderJson}
              onChange={(e) => setOrderJson(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-emerald-500 resize-none"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {saving ? '저장 중...' : '저장'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ s }: { s: Strategy }) {
  if (s.emergency_stopped)
    return <span className="text-xs px-2 py-0.5 rounded bg-red-900/40 text-red-400">긴급정지</span>
  if (!s.is_active)
    return <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-500">비활성</span>
  if (s.is_paused)
    return <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/40 text-yellow-400">일시정지</span>
  return <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-400">실행 중</span>
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [modal, setModal] = useState<{ mode: ModalMode; strategy?: Strategy } | null>(null)

  async function load() {
    setLoading(true)
    try {
      const res = await strategiesApi.list()
      setStrategies((res.data as unknown as Strategy[]) ?? [])
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

  async function handleToggle(s: Strategy) {
    if (s.is_active && !s.is_paused) {
      await withAction(s.id, () => strategiesApi.pause(s.id))
    } else {
      await withAction(s.id, () => strategiesApi.activate(s.id))
    }
  }

  async function handleEmergencyStop(id: string) {
    if (!confirm('긴급정지를 실행하시겠습니까?')) return
    await withAction(id, () => strategiesApi.emergencyStop(id))
  }

  async function handleResume(id: string) {
    await withAction(id, () => strategiesApi.resume(id))
  }

  async function handleDelete(id: string) {
    if (!confirm('전략을 삭제하시겠습니까?')) return
    await withAction(id, () => strategiesApi.delete(id))
  }

  function handleModalSave() {
    setModal(null)
    load()
  }

  return (
    <div className="space-y-5">
      {modal && (
        <StrategyModal
          mode={modal.mode}
          initial={modal.strategy}
          onClose={() => setModal(null)}
          onSave={handleModalSave}
        />
      )}

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
          <button
            onClick={() => setModal({ mode: 'create' })}
            className="flex items-center gap-1.5 text-sm bg-emerald-500 hover:bg-emerald-400 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
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
                      {AI_MODE_LABELS[s.ai_mode] ?? s.ai_mode}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge s={s} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {/* Edit */}
                        <button
                          disabled={busy}
                          onClick={() => setModal({ mode: 'edit', strategy: s })}
                          title="편집"
                          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>

                        {/* Activate / Pause */}
                        {!s.emergency_stopped && (
                          <button
                            disabled={busy}
                            onClick={() => handleToggle(s)}
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

                        {/* Emergency stop / Resume */}
                        {s.emergency_stopped ? (
                          <button
                            disabled={busy}
                            onClick={() => handleResume(s.id)}
                            title="재개"
                            className="p-1.5 rounded hover:bg-emerald-900/40 text-gray-400 hover:text-emerald-400 transition-colors disabled:opacity-50"
                          >
                            <RotateCcw className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            disabled={busy}
                            onClick={() => handleEmergencyStop(s.id)}
                            title="긴급정지"
                            className="p-1.5 rounded hover:bg-red-900/40 text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50"
                          >
                            <AlertTriangle className="w-4 h-4" />
                          </button>
                        )}

                        {/* Delete */}
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
