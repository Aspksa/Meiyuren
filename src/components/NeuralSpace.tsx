import { useMemo, useState } from 'react';

export type NeuralGraph = {
  nodes: { id: string; brain: string; createdAt: number }[];
  edges: { source: string; target: string; relation: string; weight: number; updatedAt?: number }[];
  events: { kind: string; nodeId: string; action: string; timestamp: number }[];
  truncated: boolean;
};
const DOMAINS = ['identity','episodes','goals','habits','knowledge','relationships','projects','decisions'];
const COLORS = ['#64bbff','#c49cff','#68eed9','#ffce7a','#ed8bfa','#93daff','#ffc08e','#f5a8d2'];
const hash = (value:string) => [...value].reduce((h,c) => (Math.imul(31,h)+c.charCodeAt(0))|0,7)>>>0;
type Point = {id:string; x:number;y:number;z:number; brain:string;depth:number;radius:number};
export function NeuralSpace({graph, at}:{graph:NeuralGraph|null;at:number}) {
  const [angle,setAngle]=useState(0.32);
  const [tilt,setTilt]=useState(0.22);
  const [zoom,setZoom]=useState(1);
  const [focus,setFocus]=useState('');
  const [drag,setDrag]=useState<{x:number;y:number}|null>(null);
  const visible=useMemo(()=>{
    const nodes=(graph?.nodes??[]).filter(n=>n.createdAt<=at);
    return nodes.map(n=>{
      const brainIndex=Math.max(0,DOMAINS.indexOf(n.brain));
      const t=brainIndex*Math.PI/4-Math.PI/2;
      const h=hash(n.id);
      const orbit=95+(h%65),local=(h%628)/100;
      const x=Math.cos(t)*orbit+Math.cos(local)*35;
      const y=Math.sin(t)*orbit+Math.sin(local)*35;
      const z=((h>>>12)%170)-85;
      const rx=x*Math.cos(angle)-z*Math.sin(angle);
      const rz=x*Math.sin(angle)+z*Math.cos(angle);
      const ry=y*Math.cos(tilt)-rz*Math.sin(tilt);
      const depth=y*Math.sin(tilt)+rz*Math.cos(tilt);
      const scale=zoom*(400/(400+depth));
      return {id:n.id,brain:n.brain,x:300+rx*scale,y:225+ry*scale,z:depth,depth,radius:Math.max(2,3.7*scale)} as Point;
    });
  },[graph,at,angle,tilt,zoom]);
  const lookup=new Map(visible.map(p=>[p.id,p]));
  const edges=(graph?.edges??[]).filter(e=>(e.updatedAt??0)<=at && lookup.has(e.source)&&lookup.has(e.target)).slice(0,800);
  return <div className="neural-space">
    <div className="neural-space__controls">
      <strong>Пространственная карта памяти</strong>
      <div><button type="button" onClick={()=>setZoom(z=>Math.min(2.5,z+.2))} aria-label="Приблизить">＋</button>
      <button type="button" onClick={()=>setZoom(z=>Math.max(.55,z-.2))} aria-label="Отдалить">－</button>
      <button type="button" onClick={()=>{setAngle(.32);setTilt(.22);setZoom(1);setFocus('');}}>Сброс</button></div>
    </div>
    <svg viewBox="0 0 600 450" role="img" aria-label="Интерактивная пространственная проекция фактов и подтверждённых связей" onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);setDrag({x:e.clientX,y:e.clientY});}} onPointerUp={()=>setDrag(null)} onPointerCancel={()=>setDrag(null)} onPointerMove={e=>{if(!drag)return;setAngle(a=>a+(e.clientX-drag.x)*.007);setTilt(t=>Math.max(-1.2,Math.min(1.2,t+(e.clientY-drag.y)*.007)));setDrag({x:e.clientX,y:e.clientY});}} style={{touchAction:'none',cursor:drag?'grabbing':'grab'}}>
      <defs><radialGradient id="neuralSpaceBackground"><stop stopColor="#2b3b8d"/><stop offset="1" stopColor="#070c22"/></radialGradient></defs>
      <rect width="600" height="450" fill="url(#neuralSpaceBackground)" rx="16"/>
      {[80,150,220].map(r=><ellipse key={r} cx="300" cy="225" rx={r*zoom} ry={r*.5*zoom} fill="none" stroke="#76aeff" strokeOpacity=".17" strokeDasharray="3 8"/>)}
      {edges.map((e,i)=>{const a=lookup.get(e.source)!,b=lookup.get(e.target)!;return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#a6c7ff" strokeWidth={Math.max(.6,Math.min(3,e.weight*1.5))} strokeOpacity={focus && e.source!==focus && e.target!==focus?.09:.55}/>;})}
      {visible.sort((a,b)=>b.depth-a.depth).map(p=><circle key={p.id} cx={p.x} cy={p.y} r={focus===p.id?p.radius+3:p.radius} fill={COLORS[Math.max(0,DOMAINS.indexOf(p.brain))]} stroke={focus===p.id?'white':'none'} strokeWidth="2" opacity={focus && focus!==p.id?.35:.95} onClick={e=>{e.stopPropagation();if(!drag)setFocus(p.id);}}/>)}
      {visible.length===0 && <text x="300" y="225" fill="#c5d9ff" textAnchor="middle" fontSize="15">Подтверждённых воспоминаний пока нет</text>}
    </svg>
    <p>Перетаскивай для вращения, используй +/− для масштаба. Узлов: {visible.length}; реальных связей: {edges.length}. {focus ? `Выбран узел ${focus.slice(0,8)}.` : ''}</p>
    <small>3D-проекция на SVG без WebGL. Положение узлов — визуальная раскладка, не координаты модели; связи только из SQLite.</small>
  </div>;
}
