import { useEffect, useState } from 'react'
import { exchangeApi, ExchangeAccount, CreateExchangePayload } from '@/api/client'
import { Plus, RefreshCw, Trash2, X } from 'lucide-react'

// ── Add Modal ─────────────────────────────────────────────────────────────────

interface AddModalProps {
  supported: string[]
  onClose: () => void
  onSave: () => void
}

function AddModal({ supported, onClose, onSave }: AddModalProps) {
  const [form, setForm] = useState<CreateExchangePayload>({
    exchange_id: supported[0] ?? 'binance',
    label: '',
    api_key: '',
    api_secret: '',
    is_testnet: false,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof CreateExchangePayload>(k: K, v: CreateExchangePayload[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await exchangeApi.create(form)
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
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-base font-semibold text-white">거래소 계정 추가</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">거래소 *</label>
            <select
              value={form.exchange_id}
              onChange={(e) => set('exchange_id', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            >
              {supported.map((ex) => (
                <option key={ex} value={ex}>{ex}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">레이블 *</label>
            <input
              required
              value={form.label}
              onChange={(e) => set('label', e.target.value)}
              placeholder="My Binance Account"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">API Key *</label>
            <input
              required
              value={form.api_key}
              onChange={(e) => set('api_key', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500"
              autoComplete="off"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">API Secret *</label>
            <input
              required
              type="password"
              value={form.api_secret}
              onChange={(e) => set('api_secret', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500"
              autoComplete="new-password"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="testnet"
              type="checkbox"
              checked={form.is_testnet}
              onChange={(e) => set('is_testnet', e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-emerald-500 focus:ring-emerald-500"
            />
            <label htmlFor="testnet" className="text-sm text-gray-300">테스트넷 사용</label>
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

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ExchangesPage() {
  const [accounts, setAccounts] = useState<ExchangeAccount[]>([])
  const [supported, setSupported] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const [aRes, sRes] = await Promise.all([exchangeApi.list(), exchangeApi.supported()])
      setAccounts((aRes.data as unknown as ExchangeAccount[]) ?? [])
      setSupported((sRes.data as unknown as { exchanges: string[] }).exchanges ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleDelete(id: string) {
    if (!confirm('계정을 삭제하시겠습니까?')) return
    setDeleting(id)
    try {
      await exchangeApi.delete(id)
      await load()
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-5">
      {showModal && (
        <AddModal
          supported={supported}
          onClose={() => setShowModal(false)}
          onSave={() => { setShowModal(false); load() }}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">거래소 계정</h1>
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
            <Plus className="w-3.5 h-3.5" />계정 추가
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : accounts.length === 0 ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 py-20 text-center text-gray-500">
          등록된 거래소 계정이 없습니다.
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500">
                <th className="px-5 py-3 text-left font-medium">레이블</th>
                <th className="px-4 py-3 text-left font-medium">거래소</th>
                <th className="px-4 py-3 text-left font-medium">네트워크</th>
                <th className="px-4 py-3 text-left font-medium">상태</th>
                <th className="px-4 py-3 text-left font-medium">마지막 동기화</th>
                <th className="px-4 py-3 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {accounts.map((a) => (
                <tr key={a.id} className="hover:bg-gray-800/50">
                  <td className="px-5 py-3 font-medium text-white">{a.label}</td>
                  <td className="px-4 py-3 text-gray-300 font-mono">{a.exchange_id}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${a.is_testnet ? 'bg-yellow-900/40 text-yellow-400' : 'bg-emerald-900/40 text-emerald-400'}`}>
                      {a.is_testnet ? '테스트넷' : '메인넷'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${a.is_active ? 'bg-emerald-900/40 text-emerald-400' : 'bg-gray-800 text-gray-500'}`}>
                      {a.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {a.last_synced_at ? new Date(a.last_synced_at).toLocaleString('ko-KR') : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <button
                        disabled={deleting === a.id}
                        onClick={() => handleDelete(a.id)}
                        className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
