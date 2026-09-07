import { Activity, AlertTriangle, Battery, Bot, Building2, Clock3, Radio, ShieldCheck } from 'lucide-react';
import MapView from './components/MapView';
import { alerts, racks, robots } from './data/mock';

function RobotCard({ robot }: { robot: (typeof robots)[number] }) {
  return (
    <article className="robot-card">
      <div className="robot-card-head">
        <div className={`robot-icon ${robot.id}`}><Bot size={18} /></div>
        <div><strong>{robot.label}</strong><small>/{robot.id}</small></div>
        <span className="online-dot" />
      </div>
      <div className="robot-state"><span className={`state-pill ${robot.state.toLowerCase()}`}>{robot.state}</span><span>{robot.zone}</span></div>
      <div className="battery-row"><Battery size={15} /><div className="battery-track"><i style={{ width: `${robot.battery}%` }} /></div><b>{robot.battery}%</b></div>
      <div className="coords">x {robot.x.toFixed(2)} <span>y {robot.y.toFixed(2)}</span></div>
    </article>
  );
}

function AlertCard({ alert }: { alert: (typeof alerts)[number] }) {
  const isL3 = alert.severity === 3;
  return (
    <article className={`alert-card ${isL3 ? 'l3' : 'l2'}`}>
      <div className="alert-top"><span className="severity">L{alert.severity}</span><time>{alert.updatedAt}</time></div>
      <div className="alert-title"><AlertTriangle size={17} /><strong>{alert.id}</strong><span>· {alert.zone}</span></div>
      <p>{alert.state === 'DOOR_OPEN' ? 'Rack door opened' : 'LED status anomaly'}</p>
      <button>OPEN EVENT</button>
    </article>
  );
}

export default function App() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Building2 size={20} /></div><div><strong>IDC AUTONOMOUS PATROL</strong><small>ROBOT SECURITY CONTROL CENTER</small></div></div>
        <div className="system-online"><Radio size={15} /><span>SYSTEM ONLINE</span><b>LIVE</b></div>
      </header>

      <section className="dashboard-grid">
        <aside className="left-rail panel">
          <div className="section-heading"><div><span className="eyebrow">FLEET</span><h2>Robots</h2></div><span className="count-chip">2 / 2</span></div>
          <div className="robot-list">{robots.map((robot) => <RobotCard key={robot.id} robot={robot} />)}</div>
          <div className="mission-card"><span className="eyebrow">CURRENT MISSION</span><strong>Night Patrol · Route A</strong><div><Activity size={15} /><span>18 / 26 waypoints</span></div><div className="mission-progress"><i /></div></div>
        </aside>

        <MapView robots={robots} racks={racks} />

        <aside className="right-rail panel">
          <div className="section-heading"><div><span className="eyebrow">SECURITY</span><h2>Rack Alerts</h2></div><span className="alert-count">{alerts.length}</span></div>
          <div className="alert-stack">{alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)}</div>
          <div className="security-score"><ShieldCheck size={23} /><div><span>Facility Status</span><strong>ATTENTION</strong></div><b>{racks.length - alerts.length}/{racks.length}</b></div>
        </aside>
      </section>

      <footer className="statusbar">
        <div><Bot size={15} /><strong>2</strong><span>Robots Online</span></div>
        <div><Building2 size={15} /><strong>{racks.length}</strong><span>Racks Monitored</span></div>
        <div className="footer-alert"><AlertTriangle size={15} /><strong>{alerts.length}</strong><span>Active Alerts</span></div>
        <div className="push-right"><Clock3 size={15} /><span>UI Mock · 2 Hz target</span></div>
      </footer>
    </main>
  );
}
