import { usePriceFeed } from '@/hooks/usePriceFeed'

const TRACKED_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT']

/** Mounts one WebSocket price feed per tracked symbol. Render inside authenticated layout. */
function SingleFeed({ symbol }: { symbol: string }) {
  usePriceFeed(symbol)
  return null
}

export default function PriceFeedConnector() {
  return (
    <>
      {TRACKED_SYMBOLS.map((s) => (
        <SingleFeed key={s} symbol={s} />
      ))}
    </>
  )
}
