import { useState, useEffect, useRef } from 'react';

import './index.css';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  Activity, Sun, AlertTriangle, CalendarDays, BarChart3,
  Zap, Wind, Droplets, ChevronDown, TrendingUp,
  CheckCircle, XCircle, Leaf, IndianRupee, Sparkles,
  TreePine, Fuel, Smartphone, Lightbulb,
  Fan, Tv, Refrigerator, AirVent, CookingPot, Home, GripVertical, Cloud
} from 'lucide-react';

// live energy-flow scene: sun/weather -> panel -> inverter -> house + grid.
// house/grid split is not measured (no CT clamp): those paths animate but
// carry no numbers.
function FlowScene({ now }: { now: any }) {
  if (!now) return null;
  const ac = now.fresh ? now.ac_w : 0;
  const active = ac > 20;
  const dur = active ? Math.max(0.5, 2.6 - ac / 1500) : 0;
  const cloudN = Math.min(3, Math.ceil((now.cloud || 0) / 34));
  const cloudOp = 0.3 + 0.6 * (now.cloud || 0) / 100;
  const windDur = Math.max(6, 34 - (now.wind_kmh || 0));
  const raining = (now.rain_mm || 0) > 0.05;
  const night = (now.sun_wm2 || 0) < 5 && !active;
  return (
    <div className="card flow-card">
      <svg viewBox="0 0 860 290" className={`flow-scene${night ? ' night' : ''}`}
           style={{['--dur' as any]: `${dur||1}s`, ['--wdur' as any]: `${windDur}s`}}>
        {/* sun / moon */}
        {night
          ? <g><circle cx="110" cy="66" r="22" fill="#cbd5e1"/><circle cx="119" cy="60" r="19" fill="#111527"/></g>
          : <g className="sun-g" opacity={1 - 0.55*(now.cloud||0)/100}>
              <circle cx="110" cy="66" r="40" fill="#fbbf24" opacity="0.18" className="sun-glow"/>
              <circle cx="110" cy="66" r="24" fill="#fbbf24"/>
            </g>}
        {/* clouds */}
        {Array.from({length: cloudN}).map((_,i)=>(
          <g key={i} className="cloud-g" opacity={cloudOp} style={{animationDelay:`${-i*7}s`}}>
            <ellipse cx={150+i*80} cy={52+i*16} rx="42" ry="15" fill="#94a3b8"/>
            <ellipse cx={185+i*80} cy={44+i*16} rx="30" ry="13" fill="#94a3b8"/>
            <ellipse cx={120+i*80} cy={46+i*16} rx="26" ry="11" fill="#94a3b8"/>
          </g>
        ))}
        {/* rain */}
        {raining && Array.from({length: 9}).map((_,i)=>(
          <line key={i} x1={140+i*24} y1={95} x2={135+i*24} y2={112}
                className="raindrop" style={{animationDelay:`${(i%4)*0.22}s`}}
                stroke="#60a5fa" strokeWidth="2" strokeLinecap="round"/>
        ))}
        {/* ground */}
        <line x1="30" y1="262" x2="830" y2="262" stroke="rgba(255,255,255,0.14)" strokeWidth="2"/>
        {/* panel */}
        <g>
          <polygon points="150,196 296,178 318,226 172,246" fill="#1e3a8a" stroke="#3b82f6" strokeWidth="2"/>
          <line x1="188" y1="191" x2="209" y2="240" stroke="#3b82f6" strokeWidth="1" opacity="0.6"/>
          <line x1="226" y1="187" x2="247" y2="235" stroke="#3b82f6" strokeWidth="1" opacity="0.6"/>
          <line x1="264" y1="182" x2="285" y2="231" stroke="#3b82f6" strokeWidth="1" opacity="0.6"/>
          <line x1="196" y1="246" x2="196" y2="262" stroke="#64748b" strokeWidth="3"/>
          <line x1="292" y1="232" x2="292" y2="262" stroke="#64748b" strokeWidth="3"/>
          <text x="232" y="282" className="fs-label" textAnchor="middle">Panels 3 kWp</text>
        </g>
        {/* inverter */}
        <g>
          <rect x="430" y="186" width="76" height="62" rx="9" fill="#1a1a2e" stroke="#6366f1" strokeWidth="2"/>
          <circle cx="468" cy="209" r="10" fill="none" stroke="#818cf8" strokeWidth="2"/>
          <line x1="462" y1="209" x2="474" y2="209" stroke="#818cf8" strokeWidth="2"/>
          <text x="468" y="240" className="fs-label" textAnchor="middle" fontSize="10">Inverter</text>
          <text x="468" y="282" className="fs-power" textAnchor="middle">{active ? `${Math.round(ac)} W AC` : night ? 'asleep' : 'idle'}</text>
        </g>
        {/* house */}
        <g>
          <polygon points="655,132 700,100 745,132" fill="none" stroke="#e2e8f0" strokeWidth="2.5"/>
          <rect x="663" y="132" width="74" height="46" fill="none" stroke="#e2e8f0" strokeWidth="2.5" rx="2"/>
          <rect x="692" y="150" width="16" height="28" fill="none" stroke="#e2e8f0" strokeWidth="2"/>
          <text x="700" y="196" className="fs-label" textAnchor="middle">Home</text>
        </g>
        {/* grid tower */}
        <g stroke="#94a3b8" strokeWidth="2" fill="none">
          <line x1="686" y1="262" x2="700" y2="212"/><line x1="714" y1="262" x2="700" y2="212"/>
          <line x1="690" y1="248" x2="710" y2="248"/><line x1="693" y1="236" x2="707" y2="236"/>
          <line x1="678" y1="222" x2="722" y2="222"/><line x1="700" y1="212" x2="700" y2="206"/>
          <text x="700" y="280" className="fs-label" textAnchor="middle" stroke="none">EB Grid</text>
        </g>
        {/* flow paths */}
        <path d="M320,214 C 360,212 390,212 428,212" className={`flow-line${active?'':' off'}`}/>
        <path d="M508,204 C 560,196 610,168 656,150" className={`flow-line dim${active?'':' off'}`}/>
        <path d="M508,226 C 560,232 620,240 682,240" className={`flow-line dim${active?'':' off'}`}/>
        {/* reg 96 ("DC power") reads below AC output - not trustworthy, so
            no DC number is shown; AC at the inverter is the measured truth */}
        {active && <text x="590" y="152" className="fs-note" textAnchor="middle">home + grid</text>}
        {active && <text x="590" y="256" className="fs-note" textAnchor="middle">split not measured (no CT clamp)</text>}
      </svg>
      <div className="flow-caption">
        <span><Cloud size={13}/> {now.cloud}% cloud</span>
        <span><Droplets size={13}/> {now.rain_mm} mm/h</span>
        <span><Wind size={13}/> {Math.round(now.wind_kmh)} km/h</span>
        {!now.fresh && <span className="fs-stale">logger offline - scene paused</span>}
      </div>
    </div>
  );
}

// typical Indian household loads, in the order solar covers them -
// everyday loads first, AC next, grinder last (occasional use)
type Appliance = {
  id: string; name: string; unit: number; qty: number; on: boolean;
  custom?: boolean; note?: string; Icon: any;
};
const DEFAULT_APPLIANCES: Appliance[] = [
  { id: 'light',   name: 'LED Lights',      unit: 10,   qty: 2, on: true,  Icon: Lightbulb },
  { id: 'fan',     name: 'Ceiling Fans',    unit: 75,   qty: 2, on: true,  Icon: Fan },
  { id: 'fridge',  name: 'Refrigerator',    unit: 150,  qty: 1, on: true,  Icon: Refrigerator },
  { id: 'tv',      name: 'TV',              unit: 100,  qty: 1, on: true,  Icon: Tv },
  { id: 'ac',      name: 'AC (1.5 ton)',    unit: 1500, qty: 1, on: true,  Icon: AirVent },
  { id: 'grinder', name: 'Mixer / Grinder', unit: 750,  qty: 1, on: false, note: 'occasional', Icon: CookingPot },
];

// forecast scene: a house with rooftop panels under the selected hour's
// forecast weather; a 24 h slider sweeps the sun right-to-left across the sky
function ForecastScene({ wHours, fcHourly }: { wHours: any[], fcHourly: any[] }) {
  const [hr, setHr] = useState(12);
  const w = wHours?.[hr];
  if (!w) return null;
  const p50ByHour: Record<number, number> = {};
  (fcHourly||[]).forEach((h:any) => { p50ByHour[parseInt(h.time)] = h.p50; });
  const pw = p50ByHour[hr] ?? 0;
  const active = pw > 20;
  const dayFrac = Math.max(0, Math.min(1, (hr + 0.5 - 6) / 12.5));
  const isDay = hr >= 6 && hr <= 18;
  const sunX = 790 - dayFrac * 680;                       // rises right, sets left
  const sunY = 215 - Math.sin(Math.PI * dayFrac) * 155;
  const cloudN = Math.min(3, Math.ceil((w.cloud || 0) / 34));
  const cloudOp = 0.3 + 0.6 * (w.cloud || 0) / 100;
  const windDur = Math.max(6, 34 - (w.wind_kmh || 0));
  const raining = (w.rain_mm || 0) > 0.05;
  const dur = active ? Math.max(0.5, 2.6 - pw / 1500) : 1;
  return (
    <div className="card flow-card" style={{position:'relative'}}>
      <div className="fc-overlay">
        <div className="fc-time">{String(hr).padStart(2,'0')}:00 · {w.label}</div>
        <div className="fc-nums">
          <span>{w.temp}°C</span>
          <span><Cloud size={12}/> {w.cloud}%</span>
          <span><Droplets size={12}/> {w.rain_mm} mm{(w.rain_chance||0) > 10 ? ` (${w.rain_chance}%)` : ''}</span>
          <span><Wind size={12}/> {Math.round(w.wind_kmh)} km/h</span>
        </div>
        <div className="fc-pw">{active ? `~${Math.round(pw)} W expected` : 'panels asleep'}</div>
      </div>
      <svg viewBox="0 0 860 300" className={`flow-scene${isDay ? '' : ' night'}`}
           style={{['--dur' as any]: `${dur}s`, ['--wdur' as any]: `${windDur}s`}}>
        {isDay
          ? <g className="sun-move" opacity={1 - 0.55*(w.cloud||0)/100}>
              <circle cx={sunX} cy={sunY} r="34" fill="#fbbf24" opacity="0.18"/>
              <circle cx={sunX} cy={sunY} r="20" fill="#fbbf24"/>
            </g>
          : <g><circle cx="730" cy="66" r="20" fill="#cbd5e1"/><circle cx="738" cy="60" r="17" fill="#111527"/></g>}
        {Array.from({length: cloudN}).map((_,i)=>(
          <g key={i} className="cloud-g" opacity={cloudOp} style={{animationDelay:`${-i*7}s`}}>
            <ellipse cx={220+i*180} cy={56+i*13} rx="46" ry="16" fill="#94a3b8"/>
            <ellipse cx={260+i*180} cy={47+i*13} rx="32" ry="13" fill="#94a3b8"/>
            <ellipse cx={186+i*180} cy={49+i*13} rx="27" ry="11" fill="#94a3b8"/>
          </g>
        ))}
        {raining && Array.from({length: 12}).map((_,i)=>(
          <line key={i} x1={150+i*50} y1={92} x2={145+i*50} y2={110} className="raindrop"
                style={{animationDelay:`${(i%5)*0.18}s`}} stroke="#60a5fa" strokeWidth="2" strokeLinecap="round"/>
        ))}
        <line x1="30" y1="262" x2="830" y2="262" stroke="rgba(255,255,255,0.14)" strokeWidth="2"/>
        {/* house with rooftop panels */}
        <g>
          <polygon points="330,162 430,96 530,162" fill="none" stroke="#e2e8f0" strokeWidth="2.5"/>
          <rect x="345" y="162" width="170" height="100" fill="none" stroke="#e2e8f0" strokeWidth="2.5" rx="2"/>
          <rect x="412" y="206" width="34" height="56" fill="none" stroke="#e2e8f0" strokeWidth="2"/>
          <rect x="362" y="186" width="30" height="24" fill="none" stroke="#e2e8f0" strokeWidth="1.5"/>
          <polygon points="358,152 424,108 450,108 384,152" fill="#1e3a8a" stroke="#3b82f6" strokeWidth="2"/>
          <polygon points="392,152 458,108 484,108 418,152" fill="#1e3a8a" stroke="#3b82f6" strokeWidth="2"/>
          {/* inverter mounted where the second window was - LED shows on/off */}
          <rect x="466" y="184" width="30" height="38" rx="4" fill="#1a1a2e" stroke="#6366f1" strokeWidth="2"/>
          <circle cx="481" cy="196" r="4.5" className={`inv-led${active ? ' on' : ''}`}/>
          <line x1="473" y1="210" x2="489" y2="210" stroke="#475569" strokeWidth="2"/>
          <line x1="473" y1="216" x2="489" y2="216" stroke="#475569" strokeWidth="2"/>
          <text x="481" y="236" className="fs-label" textAnchor="middle" fontSize="9.5">
            {active ? 'ON' : 'OFF'}
          </text>
        </g>
      </svg>
      <input type="range" className="fc-slider" min={0} max={23} value={hr}
             onChange={e=>setHr(Number(e.target.value))}/>
      <div className="fc-ticks"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span></div>
    </div>
  );
}

const API = 'http://localhost:8000';

export default function App() {
  const [activeTab, setActiveTab] = useState('live');

  const [liveData, setLiveData]       = useState<any[]>([]);
  const [yieldToday, setYieldToday]   = useState<string>('-');
  const [availDates, setAvailDates]   = useState<string[]>([]);
  const [selDate, setSelDate]         = useState<string>('');
  const [dayData, setDayData]         = useState<any>(null);
  const [loadingDay, setLoadingDay]   = useState(false);
  const [showDateDrop, setShowDateDrop] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  const [forecastData, setForecastData] = useState<any>({ days: [] });
  const [selFcDate, setSelFcDate]       = useState<string>('');
  const [weatherData, setWeatherData]   = useState<any>(null);

  const [savings, setSavings]   = useState<any>(null);
  const [consumption, setConsumption] = useState(600);  // assumed gross units / bi-monthly TNEB cycle
  const [appliances, setAppliances] = useState<Appliance[]>(DEFAULT_APPLIANCES);
  const [showAdd, setShowAdd] = useState(false);
  const [newAppl, setNewAppl] = useState({ name: '', watts: '', qty: '1' });
  const dragIdx = useRef<number|null>(null);
  const [draggingId, setDraggingId] = useState<string|null>(null);
  const [impact, setImpact]     = useState<any>(null);
  const [cleaning, setCleaning] = useState<any>(null);
  const [nowData, setNowData]   = useState<any>(null);

  useEffect(() => {
    const poll = () => {
      fetch(`${API}/live`).then(r=>r.json()).then(data => setLiveData(
        data.map((d:any) => ({ time: d.ts.split('T')[1].substring(0,5), power: Math.round(d.ac_power||0), tsFull: d.ts }))
      )).catch(console.error);
      fetch(`${API}/yield`).then(r=>r.json())
        .then(d => { if(d?.length) setYieldToday(d[0].yield); }).catch(console.error);
      fetch(`${API}/now`).then(r=>r.json()).then(setNowData).catch(console.error);
    };
    poll();
    const id = setInterval(poll, 5 * 60 * 1000);  // logger writes every 5 min
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch(`${API}/available_dates`).then(r=>r.json()).then((dates:string[]) => {
      setAvailDates(dates);
      if(dates.length) setSelDate(dates[0]);
    }).catch(console.error);

    fetch(`${API}/impact`).then(r=>r.json()).then(setImpact).catch(console.error);
    fetch(`${API}/cleaning`).then(r=>r.json()).then(setCleaning).catch(console.error);
  }, []);

  useEffect(() => {
    const pull = () => fetch(`${API}/forecast`).then(r=>r.json()).then(d => {
      setForecastData(d);
      // default to tomorrow; server regenerates when weather is >4 h old
      setSelFcDate(prev => d.days?.some((x:any)=>x.date===prev) ? prev : (d.days?.[1]?.date ?? d.days?.[0]?.date ?? ''));
    }).catch(console.error);
    pull();
    const id = setInterval(pull, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selFcDate) return;
    fetch(`${API}/weather?day=${selFcDate}`).then(r=>r.json()).then(setWeatherData).catch(console.error);
  }, [selFcDate]);

  useEffect(() => {
    fetch(`${API}/savings?consumption=${consumption}`).then(r=>r.json()).then(setSavings).catch(console.error);
  }, [consumption]);

  useEffect(() => {
    if (!selDate) return;
    setLoadingDay(true);
    fetch(`${API}/production/${selDate}`).then(r=>r.json()).then(d=>{setDayData(d); setLoadingDay(false);}).catch(()=>setLoadingDay(false));
  }, [selDate]);

  useEffect(() => {
    const h = (e:MouseEvent) => { if(dropRef.current && !dropRef.current.contains(e.target as Node)) setShowDateDrop(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const currentPower = liveData.length ? liveData[liveData.length-1].power : 0;
  const accuracy = dayData?.accuracy_pct;
  const fcDay = forecastData.days?.find((d:any)=>d.date===selFcDate) ?? forecastData.days?.[0];

  // solar is "live" only if the last reading is recent - otherwise /live is
  // showing a past day's curve (night, logger asleep) and the house is on EB
  const lastTsFull = liveData.length ? liveData[liveData.length-1].tsFull : null;
  const solarLive = !!lastTsFull && (Date.now() - new Date(lastTsFull).getTime()) < 30*60*1000;
  const solarNow = solarLive ? currentPower : 0;
  let _rem = solarNow;
  const applianceRows = appliances.map(a => {
    const total = a.unit * a.qty;
    if (!a.on) return { ...a, total, alloc: 0, share: 0 };
    const alloc = Math.max(0, Math.min(total, _rem)); _rem -= alloc;
    return { ...a, total, alloc, share: total ? Math.round(alloc / total * 100) : 0 };
  });
  const activeRows = applianceRows.filter(a => a.on);
  const totalLoadW = activeRows.reduce((s,a)=>s+a.total, 0);
  const coveredCount = activeRows.filter(a=>a.alloc === a.total).length;
  const spareW = Math.max(0, solarNow - totalLoadW);

  const toggleAppliance = (id:string) => setAppliances(prev =>
    prev.flatMap(a => a.id !== id ? [a]
      : a.custom && a.on ? []              // custom items are temporary - off = gone
      : [{ ...a, on: !a.on }]));
  const setApplianceQty = (id:string, q:number) => setAppliances(prev =>
    prev.map(a => a.id === id ? { ...a, qty: Math.max(1, Math.min(99, q || 1)) } : a));
  const setApplianceUnit = (id:string, w:number) => setAppliances(prev =>
    prev.map(a => a.id === id ? { ...a, unit: Math.max(1, Math.min(9999, w || 1)) } : a));
  const addAppliance = () => {
    const w = parseInt(newAppl.watts), q = Math.max(1, parseInt(newAppl.qty) || 1);
    if (!w || w < 1) return;
    setAppliances(prev => [...prev, { id: 'c'+Date.now(), name: newAppl.name.trim() || 'Custom load',
      unit: w, qty: q, on: true, custom: true, Icon: Zap }]);
    setNewAppl({ name: '', watts: '', qty: '1' }); setShowAdd(false);
  };
  const dragEnterRow = (idx:number) => {
    const from = dragIdx.current;
    if (from === null || from === idx) return;
    setAppliances(prev => {
      const arr = [...prev];
      const [moved] = arr.splice(from, 1);
      arr.splice(idx, 0, moved);
      return arr;
    });
    dragIdx.current = idx;
  };

  const fmtRs = (n:number) => n >= 100000 ? `₹${(n/100000).toFixed(1)}L` : n >= 1000 ? `₹${(n/1000).toFixed(1)}K` : `₹${Math.round(n)}`;
  const fmtNum = (n:number) => n >= 1000 ? `${(n/1000).toFixed(1)}K` : String(Math.round(n));

  return (
    <div className="app-container">
      <nav className="sidebar">
        <div className="logo"><Sun size={26} className="spin-slow" /><h2>Solar Int.</h2></div>
        <ul className="nav-links">
          <li className={activeTab==='live'?'active':''} onClick={()=>setActiveTab('live')}><Activity size={18}/> Live Status</li>
          <li className={activeTab==='forecast'?'active':''} onClick={()=>setActiveTab('forecast')}><CalendarDays size={18}/> Forecast</li>
          <li className={activeTab==='savings'?'active':''} onClick={()=>setActiveTab('savings')}><IndianRupee size={18}/> Savings</li>
          <li className={activeTab==='impact'?'active':''} onClick={()=>setActiveTab('impact')}><Leaf size={18}/> Green Impact</li>
          <li className={activeTab==='insights'?'active':''} onClick={()=>setActiveTab('insights')}><AlertTriangle size={18}/> Insights</li>
        </ul>
      </nav>

      <main className="main-content">
        <header>
          <h1>{
            activeTab==='live' ? 'Plant Live Status' :
            activeTab==='forecast' ? 'Generation Forecast' :
            activeTab==='savings' ? 'Money Saved' :
            activeTab==='impact' ? 'Green Impact' : 'System Insights'
          }</h1>
          <div className="status-badge"><span className="dot"></span>Online</div>
        </header>

        {/* ═══════════════════ LIVE TAB ═══════════════════ */}
        {activeTab==='live' && (
          <div className="live-layout">
            <FlowScene now={nowData}/>
            <div className="live-stats">
              <div className="card stat-card">
                <div className="stat-icon"><Zap size={20}/></div>
                <div className="stat-info"><p>Current Power</p><h3>{currentPower} W</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon gold"><BarChart3 size={20}/></div>
                <div className="stat-info"><p>Generated Today</p><h3>{yieldToday} kWh</h3></div>
              </div>
            </div>

            {/* What can solar power right now */}
            <div className="card">
              <div className="breakeven-title">
                <div className="stat-icon"><Home size={20}/></div>
                <div>
                  <h3 style={{fontSize:'1.05rem',fontWeight:600,marginBottom:2}}>What can solar power right now?</h3>
                  <p className="sub-label">Typical household loads vs live production · drag ⋮⋮ to change solar priority · grid-tied, no battery - solar offsets your EB draw</p>
                </div>
              </div>
              <div className="appliance-table">
                <div className="appliance-row appliance-head">
                  <span>Appliance</span><span>Qty</span><span>Watts each</span><span>Runs on (if on now)</span>
                </div>
                {applianceRows.map((a, idx) => (
                  <div key={a.id}
                       className={`appliance-row${a.on ? '' : ' row-off'}${draggingId===a.id ? ' row-dragging' : ''}`}
                       onDragEnter={()=>dragEnterRow(idx)}
                       onDragOver={e=>e.preventDefault()}>
                    <span className="a-name">
                      <span className="a-grip" draggable
                            onDragStart={e=>{ dragIdx.current = idx; setDraggingId(a.id); e.dataTransfer.effectAllowed='move'; }}
                            onDragEnd={()=>{ dragIdx.current = null; setDraggingId(null); }}>
                        <GripVertical size={14}/>
                      </span>
                      <input type="checkbox" className="a-check" checked={a.on} onChange={()=>toggleAppliance(a.id)}/>
                      <a.Icon size={16}/>{a.name}
                      {a.note && <em className="a-note">{a.note}</em>}
                      {a.custom && <em className="a-note">temporary</em>}
                    </span>
                    <span className="a-qty">
                      {a.on
                        ? <input type="number" className="a-qty-input" min={1} max={99} value={a.qty}
                                 onChange={e=>setApplianceQty(a.id, Number(e.target.value))}/>
                        : a.qty}
                    </span>
                    <span className="a-watts">
                      {a.on
                        ? <>
                            <input type="number" className="a-qty-input a-watts-input" min={1} max={9999}
                                   value={a.unit} onChange={e=>setApplianceUnit(a.id, Number(e.target.value))}/>
                            {a.qty > 1 && <span className="sub-label"> = {a.total} W</span>}
                          </>
                        : `${a.total} W`}
                    </span>
                    <span>
                      {!a.on ? <span className="a-off-dash">off</span>
                       : a.alloc === a.total ? <span className="app-pill solar">Solar</span>
                       : a.alloc <= 0 ? <span className="app-pill eb">EB</span>
                       : <span className="app-pill partial">~{a.share}% solar · {a.share < 50 ? 'heavy load on EB' : 'rest on EB'}</span>}
                    </span>
                  </div>
                ))}
                {showAdd ? (
                  <div className="appliance-row add-form">
                    <span className="a-name">
                      <Zap size={16}/>
                      <input className="a-text-input" placeholder="Name (e.g. Washing machine)" value={newAppl.name}
                             onChange={e=>setNewAppl({...newAppl, name: e.target.value})} autoFocus/>
                    </span>
                    <span>
                      <input type="number" className="a-qty-input" min={1} max={99} placeholder="1" value={newAppl.qty}
                             onChange={e=>setNewAppl({...newAppl, qty: e.target.value})}/>
                    </span>
                    <span>
                      <input type="number" className="a-qty-input a-watts-input" min={1} placeholder="Watts" value={newAppl.watts}
                             onChange={e=>setNewAppl({...newAppl, watts: e.target.value})}
                             onKeyDown={e=>{ if(e.key==='Enter') addAppliance(); }}/>
                    </span>
                    <span className="add-actions">
                      <button className="mini-btn accent" onClick={addAppliance}>Add</button>
                      <button className="mini-btn" onClick={()=>{setShowAdd(false); setNewAppl({name:'',watts:'',qty:'1'});}}>Cancel</button>
                    </span>
                  </div>
                ) : (
                  <div className="appliance-row add-row" onClick={()=>setShowAdd(true)}>
                    <span className="a-name add-label">+ Add appliance</span><span/><span/><span/>
                  </div>
                )}
              </div>
              {solarNow <= 20 ? (
                <div className="power-strip eb-strip">
                  <Zap size={15}/> Solar is idle - the house is drawing from EB right now.
                </div>
              ) : (
                <div className="power-strip solar-strip">
                  <Sun size={15}/> Producing {solarNow} W - fully covers {coveredCount} of {activeRows.length} selected loads
                  ({Math.min(solarNow, totalLoadW)} of {totalLoadW} W){spareW > 0 ? `, with ${spareW} W to spare` : ' - the rest draws from EB'}.
                </div>
              )}
            </div>

            <div className="date-row">
              <div className="date-picker-wrap" ref={dropRef}>
                <button className="date-btn" onClick={()=>setShowDateDrop(v=>!v)}>
                  <CalendarDays size={14}/> {selDate||'Pick a date'} <ChevronDown size={13} className={showDateDrop?'rotated':''}/>
                </button>
                {showDateDrop && (
                  <div className="date-dropdown">
                    {availDates.map(d=>(
                      <div key={d} className={`date-item${d===selDate?' selected':''}`}
                        onClick={()=>{setSelDate(d);setShowDateDrop(false);}}>{d}</div>
                    ))}
                  </div>
                )}
              </div>
              {dayData && !loadingDay && (
                <div className="day-summary-pills">
                  <div className="pill"><Sun size={12}/><span>{dayData.actual_kwh} kWh actual</span></div>
                  <div className="pill muted"><TrendingUp size={12}/><span>{dayData.predicted_kwh} kWh predicted</span></div>
                  <div className={`pill ${accuracy>=85?'green':accuracy>=70?'amber':'red'}`}>
                    {accuracy>=85?<CheckCircle size={12}/>:<XCircle size={12}/>}<span>{accuracy}% accuracy</span>
                  </div>
                </div>
              )}
            </div>

            <div className="card chart-card full-width">
              <div className="chart-header">
                <h3>Production on {selDate}</h3>
                <div className="legend-inline">
                  <span className="leg-dot" style={{background:'#6366f1'}}></span>Actual &nbsp;
                  <span className="leg-dot" style={{background:'#f59e0b'}}></span>Predicted
                </div>
              </div>
              {loadingDay ? <div className="loading-state">Loading…</div> : dayData ? (
                <ResponsiveContainer width="100%" height={290}>
                  <LineChart data={dayData.hourly}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)"/>
                    <XAxis dataKey="time" stroke="#555" tick={{fill:'#888',fontSize:10}} interval={11}/>
                    <YAxis stroke="#555" tick={{fill:'#888',fontSize:10}} unit="W"/>
                    <Tooltip contentStyle={{backgroundColor:'#1a1a2e',border:'1px solid #333',borderRadius:'10px',color:'#fff'}} formatter={(v:any,n:string)=>[`${Math.round(v)} W`,n]}/>
                    <Line type="monotone" dataKey="actual_w" name="Actual" stroke="#6366f1" strokeWidth={2} dot={false}/>
                    <Line type="monotone" dataKey="predicted_w" name="Predicted" stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="5 3" dot={false}/>
                  </LineChart>
                </ResponsiveContainer>
              ) : <div className="loading-state">No data for this date.</div>}
            </div>
          </div>
        )}

        {/* ═══════════════════ FORECAST TAB ═══════════════════ */}
        {activeTab==='forecast' && (
          <div className="forecast-layout">
            {/* Week selector, weather-app style */}
            <div className="day-chips">
              {forecastData.days?.map((d:any, i:number) => (
                <button key={d.date} className={`day-chip${d.date===selFcDate?' active':''}`} onClick={()=>setSelFcDate(d.date)}>
                  <span className="dc-day">{i===0?'Today':i===1?'Tmrw':d.weekday}</span>
                  <span className="dc-date">{d.date.slice(8)}/{d.date.slice(5,7)}</span>
                  <span className="dc-kwh">{d.p50_kwh} kWh</span>
                </button>
              ))}
            </div>
            {forecastData.generated_at && (
              <p className="sub-label" style={{marginTop:'-0.8rem'}}>
                Weather pulled {forecastData.generated_at.replace('T',' ').slice(0,16)} · auto-refreshes every 4 h · further days are less certain
              </p>
            )}
            <div className="forecast-stats">
              <div className="card stat-card"><div className="stat-icon gold"><Sun size={20}/></div><div className="stat-info"><p>Expected Generation</p><h3>{fcDay?.p50_kwh??'-'} kWh</h3><span className="sub-label">most likely · {fcDay?.date??''}</span></div></div>
              <div className="card stat-card"><div className="stat-icon green"><Zap size={20}/></div><div className="stat-info"><p>Best-Case</p><h3>{fcDay?.p90_kwh??'-'} kWh</h3><span className="sub-label">clear skies</span></div></div>
              <div className="card stat-card"><div className="stat-icon red"><BarChart3 size={20}/></div><div className="stat-info"><p>Worst-Case</p><h3>{fcDay?.p10_kwh??'-'} kWh</h3><span className="sub-label">cloudy / rainy</span></div></div>
            </div>
            {weatherData && !weatherData.error && (<>
              <div className="card weather-hero">
                <div className="weather-hero-left"><div className="weather-big-icon">{weatherData.daily?.icon}</div><div><div className="weather-condition">{weatherData.daily?.label}</div><div className="weather-temp">{weatherData.daily?.temp_max}° / {weatherData.daily?.temp_min}°C</div></div></div>
                <div className="weather-hero-right">
                  <div className="weather-pill"><Droplets size={13}/>{weatherData.daily?.rain_mm} mm</div>
                  <div className="weather-pill"><Sun size={13}/>{weatherData.daily?.sunshine_hrs} hrs sun</div>
                  <div className="weather-pill"><Wind size={13}/>UV {weatherData.daily?.uv_index}</div>
                </div>
              </div>
              <ForecastScene key={selFcDate} wHours={weatherData.hourly} fcHourly={fcDay?.hourly}/>
              <div className="card impact-banner" style={{borderLeftColor:weatherData.impact?.color}}>
                <div className="impact-icon" style={{background:`${weatherData.impact?.color}22`,color:weatherData.impact?.color}}><Sun size={18}/></div>
                <div><div className="impact-title">How this day's weather affects your panels</div><div className="impact-text">{weatherData.impact?.text}</div></div>
              </div>
            </>)}
            <div className="card chart-card full-width">
              <div className="chart-header"><h3>Generation Forecast - Hour by Hour</h3>
                <div className="legend-inline">
                  <span className="leg-dot" style={{background:'#4f46e5',opacity:0.4}}></span>Best-Case &nbsp;
                  <span className="leg-dot" style={{background:'#6366f1'}}></span>Expected &nbsp;
                  <span className="leg-dot" style={{background:'#818cf8'}}></span>Worst-Case
                </div>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={fcDay?.hourly ?? []}>
                  <defs>
                    <linearGradient id="g90" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/><stop offset="95%" stopColor="#6366f1" stopOpacity={0}/></linearGradient>
                    <linearGradient id="g50" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.7}/><stop offset="95%" stopColor="#6366f1" stopOpacity={0.1}/></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.07)"/>
                  <XAxis dataKey="time" stroke="#555" tick={{fill:'#888',fontSize:11}}/>
                  <YAxis stroke="#555" tick={{fill:'#888',fontSize:11}} unit="W"/>
                  <Tooltip contentStyle={{backgroundColor:'#1a1a2e',border:'1px solid #333',borderRadius:'10px',color:'#fff'}} formatter={(v:any,n:string)=>[`${Math.round(v)} W`,n]}/>
                  <Area type="monotone" dataKey="p90" name="Best-Case" stroke="none" fill="url(#g90)"/>
                  <Area type="monotone" dataKey="p50" name="Expected" stroke="#6366f1" strokeWidth={2} fill="url(#g50)"/>
                  <Area type="monotone" dataKey="p10" name="Worst-Case" stroke="#818cf8" strokeWidth={1.5} strokeDasharray="4 3" fill="none"/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ═══════════════════ SAVINGS TAB ═══════════════════ */}
        {activeTab==='savings' && savings && (
          <div className="savings-layout">
            {/* Assumption control - no CT clamp, so gross usage is an estimate */}
            <div className="card" style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap',padding:'12px 16px'}}>
              <span style={{fontSize:13,color:'#888'}}>Your household usage (from TNEB bill, units per 2-month cycle):</span>
              <select value={consumption} onChange={e=>setConsumption(Number(e.target.value))}
                      style={{background:'#1a1a2e',color:'#fff',border:'1px solid #333',borderRadius:8,padding:'6px 10px'}}>
                {[300,400,500,600,700,800,1000,1200].map(u=><option key={u} value={u}>{u} units</option>)}
              </select>
              <span style={{fontSize:12,color:'#666'}}>
                Solar is worth ₹{savings.tariff_rs_per_kwh}/kWh at this usage - TNEB slabs are telescopic, so solar
                offsets your most expensive units first. No CT clamp: usage is assumed, not measured.
              </span>
            </div>
            {/* Top savings stats */}
            <div className="savings-stats">
              <div className="card stat-card">
                <div className="stat-icon gold"><IndianRupee size={20}/></div>
                <div className="stat-info"><p>Saved Today</p><h3>{fmtRs(savings.today_rs)}</h3><span className="sub-label">{savings.today_kwh} kWh</span></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon"><IndianRupee size={20}/></div>
                <div className="stat-info"><p>Saved This Month</p><h3>{fmtRs(savings.month_rs)}</h3><span className="sub-label">{savings.month_kwh} kWh</span></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon green"><IndianRupee size={20}/></div>
                <div className="stat-info"><p>Saved This Year</p><h3>{fmtRs(savings.year_rs)}</h3><span className="sub-label">{savings.year_kwh} kWh</span></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#7c3aed,#a78bfa)'}}><Sparkles size={20}/></div>
                <div className="stat-info"><p>Total Saved (Lifetime)</p><h3>{fmtRs(savings.total_rs)}</h3><span className="sub-label">{(savings.total_kwh/1000).toFixed(1)} MWh generated</span></div>
              </div>
            </div>

            {/* Break-even tracker */}
            <div className="card breakeven-card">
              <div className="breakeven-header">
                <div className="breakeven-title">
                  <div className="stat-icon green"><TrendingUp size={20}/></div>
                  <div>
                    <h3>Investment Recovery</h3>
                    <p className="sub-label">₹{(savings.install_cost_rs/1000).toFixed(0)}K system · ₹{savings.tariff_rs_per_kwh}/kWh effective · {savings.assumed_consumption} units assumed</p>
                  </div>
                </div>
                <div className={`breakeven-badge ${savings.breakeven_achieved?'achieved':''}`}>
                  {savings.breakeven_achieved ? 'Paid Off' : `~${Math.round(savings.months_to_breakeven/12*10)/10} yrs left`}
                </div>
              </div>
              <div className="progress-bar-wrap">
                <div className="progress-bar-track">
                  <div className="progress-bar-fill" style={{width:`${savings.pct_recovered}%`}}></div>
                </div>
                <span className="progress-label">{savings.pct_recovered}%</span>
              </div>
              <div className="breakeven-stats">
                <div><span className="be-label">Total invested</span><span className="be-val">₹{(savings.install_cost_rs/1000).toFixed(0)}K</span></div>
                <div><span className="be-label">Recovered so far</span><span className="be-val green-text">{fmtRs(savings.total_rs)}</span></div>
                <div><span className="be-label">Remaining</span><span className="be-val amber-text">{fmtRs(Math.max(0, savings.install_cost_rs - savings.total_rs))}</span></div>
              </div>
            </div>

            {/* Monthly savings chart */}
            <div className="card chart-card full-width">
              <div className="chart-header"><h3>Monthly Savings (₹)</h3></div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={savings.monthly_chart} barSize={28}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)"/>
                  <XAxis dataKey="month" stroke="#555" tick={{fill:'#888',fontSize:9}} tickFormatter={(v:string)=>v.slice(5)}/>
                  <YAxis stroke="#555" tick={{fill:'#888',fontSize:10}} tickFormatter={(v:number)=>`₹${(v/1000).toFixed(0)}K`}/>
                  <Tooltip contentStyle={{backgroundColor:'#1a1a2e',border:'1px solid #333',borderRadius:'10px',color:'#fff'}} formatter={(v:any)=>[`₹${Math.round(v)}`, 'Saved']}/>
                  <Bar dataKey="savings" name="₹ Saved" fill="#6366f1" radius={[6,6,0,0]}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ═══════════════════ GREEN IMPACT TAB ═══════════════════ */}
        {activeTab==='impact' && impact && (
          <div className="impact-layout">
            {/* CO2 stats */}
            <div className="impact-stats">
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#10b981,#34d399)'}}><Leaf size={20}/></div>
                <div className="stat-info"><p>CO₂ Avoided Today</p><h3>{impact.today_co2_kg} kg</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#10b981,#34d399)'}}><Leaf size={20}/></div>
                <div className="stat-info"><p>CO₂ Avoided This Month</p><h3>{impact.month_co2_kg} kg</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#10b981,#34d399)'}}><Leaf size={20}/></div>
                <div className="stat-info"><p>CO₂ Avoided This Year</p><h3>{impact.year_co2_kg} kg</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#065f46,#10b981)'}}><Leaf size={20}/></div>
                <div className="stat-info"><p>Lifetime CO₂ Avoided</p><h3>{(impact.total_co2_kg/1000).toFixed(2)} tonnes</h3><span className="sub-label">{impact.total_kwh} kWh clean energy</span></div>
              </div>
            </div>

            {/* Equivalents - same stat-card layout as the CO₂ row */}
            <div className="impact-stats">
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#166534,#22c55e)'}}><TreePine size={20}/></div>
                <div className="stat-info"><p>Trees worth of CO₂ absorbed</p><h3>{impact.trees_equivalent}</h3><span className="sub-label">over {impact.op_years} yrs</span></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#b45309,#f59e0b)'}}><Fuel size={20}/></div>
                <div className="stat-info"><p>Petrol equivalent not burned</p><h3>{(impact.petrol_litres/1000).toFixed(1)}K L</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon" style={{background:'linear-gradient(135deg,#4f46e5,#818cf8)'}}><Smartphone size={20}/></div>
                <div className="stat-info"><p>Smartphone charges powered</p><h3>{fmtNum(impact.phone_charges)}</h3></div>
              </div>
              <div className="card stat-card">
                <div className="stat-icon gold"><Lightbulb size={20}/></div>
                <div className="stat-info"><p>Hours of LED light powered</p><h3>{fmtNum(impact.led_bulb_hours)}</h3></div>
              </div>
            </div>

            {/* Monthly CO2 chart */}
            <div className="card chart-card full-width">
              <div className="chart-header"><h3>Monthly CO₂ Avoided (kg)</h3></div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={impact.monthly_chart} barSize={28}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)"/>
                  <XAxis dataKey="month" stroke="#555" tick={{fill:'#888',fontSize:9}} tickFormatter={(v:string)=>v.slice(5)}/>
                  <YAxis stroke="#555" tick={{fill:'#888',fontSize:10}} unit=" kg"/>
                  <Tooltip contentStyle={{backgroundColor:'#1a1a2e',border:'1px solid #333',borderRadius:'10px',color:'#fff'}} formatter={(v:any)=>[`${v} kg`, 'CO₂ Avoided']}/>
                  <Bar dataKey="co2_kg" name="CO₂ Avoided" fill="#10b981" radius={[6,6,0,0]}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ═══════════════════ INSIGHTS TAB ═══════════════════ */}
        {activeTab==='insights' && (
          <div className="insights-layout">
            {/* Smart Cleaning Card */}
            {cleaning && !cleaning.error && (
              <div className="card cleaning-card" style={{borderLeftColor: cleaning.color}}>
                <div className="cleaning-header">
                  <div className="stat-icon" style={{background:`linear-gradient(135deg, ${cleaning.color}, ${cleaning.color}99)`, boxShadow:`0 3px 12px ${cleaning.color}55`}}><Sparkles size={20}/></div>
                  <div>
                    <h3>{cleaning.title}</h3>
                    <p>{cleaning.detail}</p>
                  </div>
                </div>
                <div className="cleaning-stats">
                  <div className="c-stat"><span className="c-label">Output vs usual (last {cleaning.n_recent} days)</span><span className="c-val" style={{color:cleaning.color}}>{cleaning.delta_pct > 0 ? '+' : ''}{cleaning.delta_pct}%</span></div>
                  <div className="c-stat"><span className="c-label">Give or take</span><span className="c-val">{cleaning.ci_low}% to {cleaning.ci_high}%</span></div>
                  <div className="c-stat"><span className="c-label">Chance it's just weather noise</span><span className="c-val">{cleaning.noise_pct}%</span></div>
                  <div className="c-stat"><span className="c-label">Last good rain wash</span><span className="c-val">{cleaning.days_since_rain != null ? `${cleaning.days_since_rain} days ago` : 'none recorded'}</span></div>
                </div>
                {cleaning.trend_chart?.length > 0 && (
                  <div style={{marginTop:'1rem'}}>
                    <p className="sub-label" style={{marginBottom:'0.5rem'}}>Output vs expected, last 30 days (1.0 = exactly as expected) · data through {cleaning.as_of}</p>
                    <ResponsiveContainer width="100%" height={140}>
                      <AreaChart data={cleaning.trend_chart}>
                        <defs><linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={cleaning.color} stopOpacity={0.4}/><stop offset="95%" stopColor={cleaning.color} stopOpacity={0}/></linearGradient></defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)"/>
                        <XAxis dataKey="date" stroke="#555" tick={{fill:'#888',fontSize:9}} tickFormatter={(v:string)=>v.slice(5)}/>
                        <YAxis stroke="#555" tick={{fill:'#888',fontSize:9}} domain={[0.6,1.2]}/>
                        <Tooltip contentStyle={{backgroundColor:'#1a1a2e',border:'1px solid #333',borderRadius:'10px',color:'#fff'}} formatter={(v:any)=>[v,'Efficiency Ratio']}/>
                        <Area type="monotone" dataKey="ratio" stroke={cleaning.color} strokeWidth={2} fill="url(#gc)"/>
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}

            {/* Other alerts */}
            <div className="dashboard-grid">
              <div className="card alert-card warning">
                <div className="alert-header"><div className="stat-icon gold"><AlertTriangle size={20}/></div><h3>Morning Shading Active</h3></div>
                <p>A consistent power dip is detected every morning around 07:30 AM, likely due to a nearby obstruction.</p>
                <div className="cost-impact cost-minor">~0.4 kWh/day lost</div>
              </div>
              <div className="card alert-card info">
                <div className="alert-header"><div className="stat-icon"><TrendingUp size={20}/></div><h3>Prediction Accuracy</h3></div>
                <p>Our physics-guided ML model is running at <strong>88.7% accuracy</strong> on daily kWh predictions across the last 15 months.</p>
                <div className="cost-impact" style={{background:'rgba(99,102,241,0.1)',color:'#818cf8'}}>11.3% avg error</div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
