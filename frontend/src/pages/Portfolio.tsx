import { useEffect, useState } from 'react'
import { portfolioApi } from '@/api/client'
import { RefreshCw, TrendingUp, TrendingDown, Wallet } from 'lucide-react'

interface BalanceItem {
  currency: string
  free: number
  locked: number
  total: number
  usd_value: number
}

interface AccountSummary {
  account_id: string
  exchange_id: string
  label: string
  is_testnet: boolean
  last_synced_at: string | null
  total_usdt_value: number
  balances: BalanceItem[]
}

interface PortfolioData {
  total_usdt_value: number
  accounts: AccountSummary[]
}

interface PnlData {
  total_realized_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
}

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null)
  const [pnl, setPnl] = useState<PnlData | null>(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [p, pnlRes] = await Promise.allSettled([
        portfolioApi.summary(),
        fetch('/api/v1/portfolio/pnl', {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        }).then((r) => r.json()),
      ])
      if (p.status === 'fulfilled') setPortfolio(p.value.data as unknown as PortfolioData)
      if (pnlRes.status === 'fulfilled') setPnl(pnlRes.value as PnlData)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-6 h-6 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">포트폴리오</h1>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          새로고침
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-2 text-gray-400 text-xs">
            <Wallet className="w-3.5 h-3.5" />
            총 평가금액
          </div>
          <div className="text-2xl font-bold text-white">
            ${(portfolio?.total_usdt_value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-2 text-gray-400 text-xs">
            {(pnl?.total_realized_pnl ?? 0) >= 0 ? (
              <TrendingUp className="w-3.5 h-3.5" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5" />
            )}
            실현 손익
          </div>
          <div
            className={`text-2xl font-bold ${
              (pnl?.total_realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
            }`}
          >
            {(pnl?.total_realized_pnl ?? 0) >= 0 ? '+' : ''}$
            {(pnl?.total_realized_pnl ?? 0).toFixed(2)}
          </div>
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <div className="text-xs text-gray-400 mb-2">총 거래 수</div>
          <div className="text-2xl font-bold text-white">{pnl?.total_trades ?? 0}</div>
          <div className="text-xs text-gray-500 mt-1">
            승 {pnl?.winning_trades ?? 0} / 패 {pnl?.losing_trades ?? 0}
          </div>
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <div className="text-xs text-gray-400 mb-2">승률</div>
          <div className="text-2xl font-bold text-white">
            {(pnl?.win_rate ?? 0).toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Accounts */}
      {portfolio?.accounts.map((account) => (
        <div key={account.account_id} className="bg-gray-900 rounded-xl border border-gray-800">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
            <div>
              <span className="font-semibold text-white capitalize">
                {account.exchange_id}
              </span>
              <span className="ml-2 text-sm text-gray-400">{account.label}</span>
              {account.is_testnet && (
                <span className="ml-2 text-xs px-1.5 py-0.5 bg-yellow-900/40 text-yellow-400 rounded">
                  테스트넷
                </span>
              )}
            </div>
            <div className="text-right">
              <div className="text-sm font-medium text-white">
                ${account.total_usdt_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              {account.last_synced_at && (
                <div className="text-xs text-gray-500">
                  {new Date(account.last_synced_at).toLocaleTimeString()} 동기화
                </div>
              )}
            </div>
          </div>

          {account.balances.length === 0 ? (
            <div className="px-5 py-8 text-center text-gray-500 text-sm">
              잔고 데이터가 없습니다. 잔고 동기화를 실행해주세요.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-800">
                  <th className="px-5 py-2 text-left font-medium">자산</th>
                  <th className="px-4 py-2 text-right font-medium">사용 가능</th>
                  <th className="px-4 py-2 text-right font-medium">잠금</th>
                  <th className="px-5 py-2 text-right font-medium">평가금액 (USDT)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {account.balances.map((b) => (
                  <tr key={b.currency} className="hover:bg-gray-800/50">
                    <td className="px-5 py-3 font-mono font-medium text-white">{b.currency}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {b.free.toFixed(8)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500 font-mono">
                      {b.locked.toFixed(8)}
                    </td>
                    <td className="px-5 py-3 text-right text-gray-200 font-mono">
                      ${b.usd_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {(!portfolio || portfolio.accounts.length === 0) && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 py-20 text-center text-gray-500">
          연결된 거래소 계정이 없습니다.
        </div>
      )}
    </div>
  )
}
