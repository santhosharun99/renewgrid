import { useState, useEffect, useRef } from 'react';
import './index.css';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  Activity, Sun, AlertTriangle, CalendarDays, BarChart3,
  Zap, Wind, Droplets, ChevronDown, TrendingUp,
  CheckCircle, XCircle, Leaf, IndianRupee, Sparkles
} from 'lucide-react';

const API = 'http://localhost:8000';

export default function App() {
  const [activeTab, setActiveTab] = useState('live');

  const [liveData, setLiveData]       = useState<any[]>([]);
  const [yieldToday, setYieldToday]   = useState<string>('—');
  const [availDates, setAvailDates]   = useState<string[]>([]);
  const [selDate, setSelDate]         = useState<string>('');
  const [dayData, setDayData]         = useState<any>(null);
  const [loadingDay, setLoadingDay]   = useState(false);
  const [showDateDrop, setShowDateDrop] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  const [forecastData, setForecastData] = useState<any>({ hourly: [], summary: {} });
  const [weatherData, setWeatherData]   = useState<any>(null);

  const [savings, setSavings]   = useState<any>(null);
  const [impact, setImpact]     = useState<any>(null);
  const [cleaning, setCleaning] = useState<any>(null);

  useEffect(() => {
    fetch(`${API}/live`).then(r=>r.json()).then(data => setLiveData(
      data.map((d:any) => ({ time: d.ts.split('T')[1].substring(0,5), power: Math.round(d.ac_power||0) }))
    )).catch(console.error);

    fetch(`${API}/yield`).then(r=>r.json())
      .then(d => { if(d?.length) setYieldToday(d[0].yield); }).catch(console.error);

    fetch(`${API}/available_dates`).then(r=>r.json()).then((dates:string[]) => {
      setAvailDates(dates);
      if(dates.length) setSelDate(dates[0]);
    }).catch(console.error);

    fetch(`${API}/forecast`).then(r=>r.json()).then(setForecastData).catch(console.error);
    fetch(`${API}/weather`).then(r=>r.json()).then(setWeatherData).catch(console.error);
    fetch(`${API}/savings`).then(r=>r.json()).then(setSavings).catch(console.error);
    fetch(`${API}/impact`).then(r=>r.json()).then(setImpact).catch(console.error);
    fetch(`${API}/cleaning`).then(r=>r.json()).then(setCleaning).catch(console.error);
  }, []);

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
            activeTab==='forecast' ? "Tomorrow's Forecast" :
            activeTab==='savings' ? 'Money Saved' :
            activeTab==='impact' ? 'Green Impact' : 'System Insights'
          }</h1>
          <div className="status-badge"><span className="dot"></span>Online</div>
        </header>

        {/* ═══════════════════ LIVE TAB ═══════════════════ */}
        {activeTab==='live' && (
          <div className="live-layout">
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
            <div className="forecast-stats">
              <div className="card stat-card"><div className="stat-icon gold"><Sun size={20}/></div><div className="stat-info"><p>Expected Generation</p><h3>{forecastData.summary?.expected_kwh??'—'} kWh</h3><span className="sub-label">most likely</span></div></div>
              <div className="card stat-card"><div className="stat-icon green"><Zap size={20}/></div><div className="stat-info"><p>Best-Case</p><h3>{forecastData.summary?.best_kwh??'—'} kWh</h3><span className="sub-label">clear skies</span></div></div>
              <div className="card stat-card"><div className="stat-icon red"><BarChart3 size={20}/></div><div className="stat-info"><p>Worst-Case</p><h3>{forecastData.summary?.worst_kwh??'—'} kWh</h3><span className="sub-label">cloudy / rainy</span></div></div>
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
              <div className="card hourly-strip-card">
                <h3>Hour-by-Hour</h3>
                <div className="hourly-strip">
                  {weatherData.hourly?.map((h:any,i:number)=>(
                    <div key={i} className="hourly-slot">
                      <span className="h-time">{h.time}</span>
                      <span className="h-icon">{h.icon}</span>
                      <span className="h-temp">{h.temp}°</span>
                      {h.rain_chance>10&&<span className="h-rain">{h.rain_chance}%</span>}
                    </div>
                  ))}
                </div>
              </div>
              <div className="card impact-banner" style={{borderLeftColor:weatherData.impact?.color}}>
                <div className="impact-icon" style={{background:`${weatherData.impact?.color}22`,color:weatherData.impact?.color}}><Sun size={18}/></div>
                <div><div className="impact-title">How tomorrow's weather affects your panels</div><div className="impact-text">{weatherData.impact?.text}</div></div>
              </div>
            </>)}
            <div className="card chart-card full-width">
              <div className="chart-header"><h3>Generation Forecast — Hour by Hour</h3>
                <div className="legend-inline">
                  <span className="leg-dot" style={{background:'#4f46e5',opacity:0.4}}></span>Best-Case &nbsp;
                  <span className="leg-dot" style={{background:'#6366f1'}}></span>Expected &nbsp;
                  <span className="leg-dot" style={{background:'#818cf8'}}></span>Worst-Case
                </div>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={forecastData.hourly}>
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
                <div>
                  <h3>Investment Recovery</h3>
                  <p className="sub-label">System cost: ₹{(savings.install_cost_rs/1000).toFixed(0)}K at ₹{savings.tariff_rs_per_kwh}/kWh</p>
                </div>
                <div className={`breakeven-badge ${savings.breakeven_achieved?'achieved':''}`}>
                  {savings.breakeven_achieved ? '🎉 Paid Off!' : `~${savings.months_to_breakeven} months left`}
                </div>
              </div>
              <div className="progress-bar-wrap">
                <div className="progress-bar-track">
                  <div className="progress-bar-fill" style={{width:`${savings.pct_recovered}%`}}></div>
                </div>
                <span className="progress-label">{savings.pct_recovered}% recovered</span>
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

            {/* Trees & fun facts */}
            <div className="fun-facts-row">
              <div className="card fun-fact-card">
                <div className="fun-fact-icon">🌳</div>
                <div className="fun-fact-val">{impact.trees_equivalent}</div>
                <div className="fun-fact-label">Trees worth of CO₂ absorbed over {impact.op_years} yrs</div>
              </div>
              <div className="card fun-fact-card">
                <div className="fun-fact-icon">⛽</div>
                <div className="fun-fact-val">{(impact.petrol_litres/1000).toFixed(1)}K L</div>
                <div className="fun-fact-label">Petrol equivalent not burned</div>
              </div>
              <div className="card fun-fact-card">
                <div className="fun-fact-icon">📱</div>
                <div className="fun-fact-val">{fmtNum(impact.phone_charges)}</div>
                <div className="fun-fact-label">Smartphone charges powered</div>
              </div>
              <div className="card fun-fact-card">
                <div className="fun-fact-icon">💡</div>
                <div className="fun-fact-val">{fmtNum(impact.led_bulb_hours)}</div>
                <div className="fun-fact-label">Hours of LED light powered</div>
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
                  <div className="cleaning-icon" style={{background:`${cleaning.color}22`, color: cleaning.color}}><Sparkles size={20}/></div>
                  <div>
                    <h3>{cleaning.title}</h3>
                    <p>{cleaning.detail}</p>
                  </div>
                </div>
                <div className="cleaning-stats">
                  <div className="c-stat"><span className="c-label">Current efficiency vs baseline</span><span className="c-val" style={{color:cleaning.color}}>{cleaning.recent_ratio} / {cleaning.baseline_ratio}</span></div>
                  <div className="c-stat"><span className="c-label">Performance drop</span><span className="c-val">{cleaning.soiling_pct}%</span></div>
                  {cleaning.daily_loss_rs > 0 && <div className="c-stat"><span className="c-label">Daily loss from soiling</span><span className="c-val red-text">₹{cleaning.daily_loss_rs} ({cleaning.daily_loss_kwh} kWh)</span></div>}
                </div>
                {cleaning.trend_chart?.length > 0 && (
                  <div style={{marginTop:'1rem'}}>
                    <p className="sub-label" style={{marginBottom:'0.5rem'}}>30-day efficiency trend</p>
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
                <div className="alert-header"><AlertTriangle/><h3>Morning Shading Active</h3></div>
                <p>A consistent power dip is detected every morning around 07:30 AM, likely due to a nearby obstruction.</p>
                <div className="cost-impact cost-minor">~0.4 kWh/day lost</div>
              </div>
              <div className="card alert-card info">
                <div className="alert-header"><TrendingUp/><h3>Prediction Accuracy</h3></div>
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
