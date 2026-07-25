import { CoinLogo } from './CoinLogo'
import { Icon } from './Icon'

// Cabecera del activo activo: identidad (logo + nombre + par) + precio + timeframe + botón de chat.
export function MarketHeader({ openChat }: { openChat: () => void }) {
  return (
    <div className="mhead">
      <span className="mhlogo"><CoinLogo sym="BTC" /></span>
      <div className="mh-id">
        <div className="tk">BTC · Bitcoin</div>
        <div className="sub num">BTC/USD · spot</div>
      </div>
      <span className="price num">$64.284</span>
      <span className="delta num up">+$1.164 · +1,84%</span>
      <span className="spacer" />
      <div className="tf">
        <button type="button">15m</button>
        <button type="button">1H</button>
        <button type="button" className="on">4H</button>
        <button type="button">1D</button>
      </div>
      <button className="chatbtn" type="button" onClick={openChat}>
        <Icon name="chat" /> Chat
      </button>
    </div>
  )
}
