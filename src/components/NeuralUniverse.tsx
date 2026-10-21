import { useEffect, useState } from 'react';
import './NeuralUniverse.css';
import { NeuralSpace } from './NeuralSpace';

type Graph = { nodes: {id:string;brain:string;createdAt:number}[]; edges:{source:string;target:string;relation:string;weight:number;updatedAt?:number}[]; events:{kind:string;nodeId:string;action:string;timestamp:number}[]; truncated:boolean };
const BRAINS = [
  ['identity', 'Личность'], ['episodes', 'События'], ['goals', 'Цели'],
  ['habits', 'Привычки'], ['knowledge', 'Знания'], ['relationships', 'Отношения'],
  ['projects', 'Проекты'], ['decisions', 'Решения'],
] as const;
type BrainId = typeof BRAINS[number][0];
type Status = {
  facts: number; autonomousBranches: number; pending: number; jobs: number;
  network: { brains: Record<string, number>; links: number; neuralVectors: number };
  cortex?: { edges?: number; connectedBrains?: number };
  evolution?: { evaluations?: number; generation?: number };
};
const initial = BRAINS.reduce((acc, [key]) => ({ ...acc, [key]: 0 }), {} as Record<BrainId, number>);
export function NeuralUniverse({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [lab,setLab]=useState<{evolution:{generation:number;strategy:string;benchmark:string;feedbackCases:number;microbrains:number;adaptiveSynapses:number};trials:{generation:number;strategy:string;cases:number;score:number;selected:boolean}[];branchesByBrain:Record<string,number>;scoreMeaning:string}|null>(null);
  const [health, setHealth] = useState<{healthy:boolean;orphanLinks:number;orphanVectors:number}|null>(null);
  const [snapshots,setSnapshots] = useState<{timestamp:number;brains:Record<string,number>}[]>([]);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [mode, setMode] = useState<'universe'|'synapses'|'evolution'|'activity'>('universe');
  const [selected, setSelected] = useState<BrainId>('projects');
  const [showSpatial, setShowSpatial] = useState(true);
  const [timePercent, setTimePercent] = useState(100);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch('/api/memory/status', { signal: controller.signal });
        if (!response.ok) throw new Error(`Backend: HTTP ${response.status}`);
        const result = await response.json() as Status;
        const graphResponse = await fetch('/api/memory/universe/graph?limit=180', { signal: controller.signal });
        if (!graphResponse.ok) throw new Error(`Graph API: HTTP ${graphResponse.status}`);
        const graphData = await graphResponse.json() as Graph;
        if (!controller.signal.aborted) { setStatus(result); setGraph(graphData); setError(''); }
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Нет связи с backend');
      }
    }
    void refresh();
    void fetch('/api/memory/universe/evolution-lab',{signal:controller.signal}).then(r=>r.ok?r.json():null).then(d=>{if(!controller.signal.aborted&&d)setLab(d);}).catch(()=>{});
    void fetch('/api/memory/universe/snapshots',{signal:controller.signal}).then(r=>r.ok?r.json():null).then(data=>{if(!controller.signal.aborted&&data)setSnapshots(data.snapshots??[]);}).catch(()=>{});
    const stream = new EventSource('/api/memory/universe/events');
    stream.addEventListener('health',(message)=>{if(controller.signal.aborted)return;try{setHealth(JSON.parse((message as MessageEvent).data));void refresh();}catch{/* malformed event ignored */}});
    const interval = window.setInterval(() => void refresh(), 8000);
    return () => { controller.abort(); stream.close(); window.clearInterval(interval); };
  }, [open]);
  if (!open) return null;
  const counts = status?.network?.brains ?? initial;
  const earliest = graph?.nodes.reduce((v,n)=>Math.min(v,n.createdAt),Date.now()) ?? Date.now();
  const latest = Date.now();
  const selectedTime = earliest+(latest-earliest)*timePercent/100;
  const total = BRAINS.reduce((sum, [id]) => sum + (counts[id] || 0), 0);
  const max = Math.max(1, ...BRAINS.map(([id]) => counts[id] || 0));
  const points = BRAINS.map(([id, label], index) => ({
    id, label, count: counts[id] || 0, x: 300 + Math.cos(index * Math.PI / 4 - Math.PI / 2) * 210,
    y: 242 + Math.sin(index * Math.PI / 4 - Math.PI / 2) * 174,
  }));
  return <section className="neural-universe" role="dialog" aria-label="Нейросеть Meiyuren">
    <header className="neural-universe__head">
      <div><small>MEIYUREN • NEURAL UNIVERSE</small><h2>Нейросеть <span>8 мозгов</span></h2><p>Живая карта подтверждённой памяти — обновление каждые 8 секунд</p></div>
      <button type="button" onClick={onClose} aria-label="Закрыть нейросеть">×</button>
    </header>
    <div className="neural-universe__stats" aria-label="Показатели памяти">
      {[
        ['Подтверждённые факты', total], ['Связи памяти', status?.network?.links ?? '—'],
        ['Нейронные векторы', status?.network?.neuralVectors ?? '—'],
        ['Тематические ветви', status?.autonomousBranches ?? '—'],
        ['Оценки эволюции', status?.evolution?.evaluations ?? '—'],
      ].map(([label, value]) => <div className="neural-universe__metric" key={label}><span>{label}</span><strong>{status ? value : '—'}</strong></div>)}
    </div>
    {error && <p className="neural-universe__error" role="alert">{error}. Показаны последние полученные данные.</p>}
    <div className="neural-universe__tabs" role="tablist" aria-label="Режим нейросети">
      {([['universe','Вселенная'],['synapses','Синапсы'],['evolution','Эволюция'],['activity','Активность']] as const).map(([id,label])=><button key={id} role="tab" aria-selected={mode===id} className={mode===id?'is-active':''} onClick={()=>setMode(id)}>{label}</button>)}
    </div>
    <div className="neural-universe__health" role="status">Проверка связности: {health ? (health.healthy ? 'нет обнаруженных повреждений' : `проблемы: ${health.orphanLinks} связей, ${health.orphanVectors} векторов`) : 'ожидание данных'} · Сохранённых снимков: {snapshots.length} <button type="button" onClick={()=>void fetch('/api/memory/universe/snapshots').then(r=>r.json()).then(d=>setSnapshots(d.snapshots??[]))}>Сохранить текущий снимок</button></div>
    {mode==='synapses' && <div className="neural-universe__ledger"><h3>Подтверждённые связи ({graph?.edges.length ?? 0})</h3>{graph?.edges.length ? graph.edges.slice(0,35).map((edge,index)=><p key={index}>{edge.source.slice(0,8)} ↔ {edge.target.slice(0,8)} · {edge.relation} · вес {edge.weight.toFixed(2)}</p>):<p>Подтверждённых связей пока нет.</p>}</div>}
    {mode==='evolution' && <div className="neural-universe__ledger"><h3>История изменения памяти</h3>{graph?.events.filter(e=>e.kind==='revision').length ? graph.events.filter(e=>e.kind==='revision').slice(0,30).map((e,i)=><p key={i}>{new Date(e.timestamp).toLocaleString('ru-RU')} · {e.action} · узел {e.nodeId.slice(0,8)}</p>):<p>История изменений пока отсутствует.</p>}</div>}
    {mode==='evolution' && <div className="neural-universe__ledger"><h3>Лаборатория эволюции</h3><p>Поколение: {lab?.evolution.generation ?? '—'} · активная стратегия: {lab?.evolution.strategy ?? '—'} · тип оценки: {lab?.evolution.benchmark ?? '—'}</p><p>Оценок пользователя: {lab?.evolution.feedbackCases ?? '—'} · подмозгов: {lab?.evolution.microbrains ?? '—'} · адаптивных синапсов: {lab?.evolution.adaptiveSynapses ?? '—'}</p><h3>Распределение ветвей по мозгам</h3>{BRAINS.map(([id,label])=><p key={id}>{label}: {lab?.branchesByBrain[id] ?? '—'}</p>)}<h3>Последние испытания</h3>{lab?.trials.length?lab.trials.slice(0,30).map((trial,i)=><p key={i}>Поколение {trial.generation} · {trial.strategy} · {trial.cases} случаев · оценка {trial.score.toFixed(3)}{trial.selected?' · выбрана':''}</p>):<p>Проверенных испытаний пока нет.</p>}<p>Метрики основаны на локальном тесте извлечения или обратной связи, это не процент интеллекта.</p></div>}
    {mode==='activity' && <div className="neural-universe__ledger"><h3>Подтверждённые обращения к памяти</h3>{graph?.events.filter(e=>e.kind==='recall').length ? graph.events.filter(e=>e.kind==='recall').slice(0,30).map((e,i)=><p key={i}>{new Date(e.timestamp).toLocaleString('ru-RU')} · извлечён узел {e.nodeId.slice(0,8)}</p>):<p>Журнал обращений пока пуст. Внутренние мысли модели не регистрируются.</p>}</div>}
    {mode==='universe' && <div className="neural-universe__spatial-actions"><label>Исторический срез создания активных узлов: {timePercent===100?'Сейчас':new Date(selectedTime).toLocaleString('ru-RU')}<input type="range" min="0" max="100" value={timePercent} onChange={e=>setTimePercent(Number(e.target.value))}/></label><button type="button" onClick={()=>setShowSpatial(x=>!x)}>{showSpatial?'Показать восемь мозгов':'Пространственный граф'}</button></div>}
    {mode==='universe' && showSpatial && <NeuralSpace graph={graph} at={selectedTime}/>}
    {mode==='universe' && !showSpatial && <div className="neural-universe__body">
      <div className="neural-universe__map">
        <svg viewBox="0 0 600 490" role="img" aria-label="Восемь мозгов и количество подтверждённых фактов в каждом">
          <defs>
            <radialGradient id="nuCore"><stop stopColor="#f8d7a1"/><stop offset=".36" stopColor="#a67cfb"/><stop offset="1" stopColor="#242e64" stopOpacity=".05"/></radialGradient>
            <filter id="nuGlow"><feGaussianBlur stdDeviation="4"/></filter>
          </defs>
          {[90,160,231].map(r=><circle key={r} cx="300" cy="242" r={r} fill="none" stroke="#77aafa" strokeOpacity=".14" strokeDasharray="3 9"/>)}
          {points.map(p=><line key={p.id} x1="300" y1="242" x2={p.x} y2={p.y} stroke="#6b9deb" strokeOpacity=".22" strokeDasharray="3 7"/>)}
          <circle cx="300" cy="242" r="66" fill="url(#nuCore)" opacity=".65"/>
          <circle cx="300" cy="242" r="27" fill="#18265b" stroke="#ccadff" strokeWidth="1.5"/>
          <text x="300" y="239" fill="#fff" fontSize="12" textAnchor="middle">MEMORY</text>
          <text x="300" y="254" fill="#96bafb" fontSize="12" textAnchor="middle">{total}</text>
          {points.map((p, index)=>{
            const radius=21+Math.min(15,p.count/max*15);
            const active=p.id===selected;
            return <g key={p.id} onClick={()=>setSelected(p.id)} tabIndex={0} role="button" aria-label={`${p.label}: ${p.count} записей`} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setSelected(p.id);}}} style={{cursor:'pointer'}}>
              <circle cx={p.x} cy={p.y} r={radius+13} fill={['#558dff','#bf6cff','#31d2f6','#ffa95b','#b879ff','#52dec2','#ffd080','#f875bb'][index]} opacity={active?.22:.12} filter="url(#nuGlow)"/>
              <circle cx={p.x} cy={p.y} r={radius+5} fill="none" stroke={active?'#fff':'#5a8bc8'} strokeOpacity={active?'.85':'.3'} strokeWidth={active?2:1}/>
              <circle cx={p.x} cy={p.y} r={radius} fill="#111b43" stroke={['#558dff','#bf6cff','#31d2f6','#ffa95b','#b879ff','#52dec2','#ffd080','#f875bb'][index]} strokeWidth="2.3"/>
              <text x={p.x} y={p.y+5} textAnchor="middle" fill="#fff" fontSize="18" fontWeight="700">{p.count}</text>
              <text x={p.x} y={p.y+radius+20} textAnchor="middle" fill="#d6e8ff" fontSize="12">{p.label}</text>
              {Array.from({length:Math.min(p.count,12)},(_,i)=><circle key={i} cx={p.x+Math.cos(i*2.4)*(radius+8)} cy={p.y+Math.sin(i*2.4)*(radius+8)} r="2" fill="#a9eeff"/>)}
            </g>;
          })}
        </svg>
        {graph && <p>В графе отображено {graph.nodes.length} фактических узлов и {graph.edges.length} связей.{graph.truncated ? ' Показана ограниченная выборка.' : ''}</p>}
        <p>Пунктирные линии — схема расположения, <strong>не подтверждённые синапсы</strong>. Размер узла отражает количество фактов.</p>
      </div>
      <aside className="neural-universe__detail">
        <small>ВЫБРАННЫЙ МОЗГ</small>
        <h3>{BRAINS.find(([id])=>id===selected)?.[1]}</h3>
        <strong>{counts[selected] || 0}</strong><span>подтверждённых фактов</span>
        <div className="neural-universe__bar"><i style={{width:`${((counts[selected] || 0)/max)*100}%`}}/></div>
        <p>Ключ: <code>{selected}</code></p>
        <p>Система Cortex: {status?.cortex?.edges ?? '—'} рёбер. Активных связанных мозгов: {status?.cortex?.connectedBrains ?? '—'}.</p>
        <p>Ожидают обработки: {status?.jobs ?? '—'} задач. Ожидают подтверждения: {status?.pending ?? '—'}.</p>
        <p className="neural-universe__note">Визуализация использует фактические счётчики SQLite. Проценты интеллекта, имитация синапсов и фиктивный рост не отображаются.</p>
      </aside>
    </div>}
  </section>;
}
