import { Radar } from './illustrations/Radar'

// Banner de estado del panel (integra la ilustración radar).
export function StatusBar() {
  return (
    <div className="statusbar">
      <div className="st-txt">
        <div className="k"><span className="pip" /> Mercado tranquilo · Argos vigilando</div>
        <p>Sin movimientos bruscos. 1 anomalía de volumen en la mira (BTC).</p>
      </div>
      <Radar />
    </div>
  )
}

// "Lo que Argos vio": eventos que los detectores marcaron (estilo Pulse de Linear).
export function PulseCard() {
  return (
    <div className="panel">
      <div className="pulse-h"><h3>Lo que Argos vio</h3></div>
      <div className="pev hi">
        <div className="st"><span className="pip" /> Volumen anómalo <span className="meta">BTC · hace 2 min</span></div>
        <ul><li>Pico de <b>3,4σ</b> sobre la media de 24 h.</li><li>Sin cambio brusco de precio aún.</li></ul>
      </div>
      <div className="pev mid">
        <div className="st"><span className="pip" /> Umbral tocado <span className="meta">ETH · hace 11 min</span></div>
        <ul><li>ETH cruzó <b>$3.400</b> a la baja (tu umbral).</li></ul>
      </div>
      <div className="pev lo">
        <div className="st"><span className="pip" /> Volatilidad calma <span className="meta">mercado · hace 40 min</span></div>
        <ul><li>Rango estrecho las últimas 3 h.</li></ul>
      </div>
    </div>
  )
}
