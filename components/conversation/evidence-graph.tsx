'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {ReactFlow,Background,Controls,Handle,Position,MarkerType,type NodeProps} from '@xyflow/react';
import {FileText,GitBranch,Move,ShieldCheck,Check} from 'lucide-react';
import '@xyflow/react/dist/style.css';
import type {Investigation,Claim} from '@/lib/truestate/engine';
function EvidenceNode({data}:NodeProps){const d=data as {label:string;account:string;trusted:boolean;origin:boolean};return <div className={`chat-graph-node ${d.trusted?'trusted':d.origin?'origin':''}`}><Handle type="target" position={Position.Top}/>{d.trusted?<ShieldCheck size={17}/>:d.origin?<GitBranch size={17}/>:<FileText size={17}/>}<div><b>{d.label}</b><span>{d.account}</span></div><Handle type="source" position={Position.Bottom}/></div>}
const nodeTypes={evidence:EvidenceNode};
export default function EvidenceGraph({c,onSelect}:{c:Investigation;onSelect:(claim:Claim)=>void}){
 const frame=useRef<HTMLDivElement>(null),fitGraph=useRef<(()=>void)|null>(null);
 const [width,setWidth]=useState(700),[exploring,setExploring]=useState(false);
 const compact=width<560,interactive=!compact||exploring;
 useEffect(()=>{const el=frame.current;if(!el)return;const measure=()=>setWidth(Math.round(el.getBoundingClientRect().width));measure();const observer=new ResizeObserver(measure);observer.observe(el);return()=>observer.disconnect();},[]);
 useEffect(()=>{setExploring(false);},[compact]);
 const nodes=useMemo(()=>c.claims.map((cl,i)=>({id:cl.id,type:'evidence',ariaLabel:`${cl.label}: ${cl.value}. ${cl.independence} evidence.`,position:compact?(i===0?{x:122,y:0}:{x:((i-1)%2)*245,y:130+Math.floor((i-1)/2)*130}):(i===0?{x:245,y:0}:i<4?{x:(i-1)*245,y:145}:{x:(i-4)*300+90,y:295}),data:{label:cl.label,account:cl.value,trusted:cl.independence==='independent',origin:i===0}})),[c.claims,compact]);
 const edges=useMemo(()=>c.claims.flatMap(cl=>cl.derivedFrom.map(parent=>({id:`${parent}-${cl.id}`,source:parent,target:cl.id,animated:!c.finishedAt,style:{stroke:'#c8a17d'},markerEnd:{type:MarkerType.ArrowClosed,color:'#c8a17d'}}))).concat(c.claims.filter(cl=>cl.independence==='independent'&&c.claims[2]).map(cl=>({id:`ind-${cl.id}`,source:cl.id,target:c.claims[2].id,animated:false,style:{stroke:cl.value===c.claims[2].value?'#79cbb0':'#d88d91',strokeDasharray:'5 5'} as any,markerEnd:{type:MarkerType.ArrowClosed,color:'#86c6af'}}))),[c]);
 useEffect(()=>{const id=requestAnimationFrame(()=>{fitGraph.current?.();});return()=>cancelAnimationFrame(id);},[width,compact,c.claims.length]);
 return <div ref={frame} className="graph-frame" data-compact={compact} data-interactive={interactive}>
  {compact&&<div className="graph-explore-toolbar"><span>{exploring?'Drag to pan. Pinch or use + / − to zoom.':'Scroll normally, or explore the graph. Sources are also listed below.'}</span><button type="button" aria-pressed={exploring} onClick={()=>setExploring(v=>!v)}>{exploring?<Check size={15}/>:<Move size={15}/>} {exploring?'Finish exploring':'Explore graph'}</button></div>}
  <div className="conversation-graph"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={instance=>{fitGraph.current=()=>{void instance.fitView({padding:.18,minZoom:.15,maxZoom:1,duration:0});};}} fitView fitViewOptions={{padding:.18,minZoom:.15,maxZoom:1}} minZoom={.15} maxZoom={2} nodesConnectable={false} nodesDraggable={false} panOnDrag={interactive} zoomOnPinch={interactive} zoomOnScroll={false} zoomOnDoubleClick={interactive} preventScrolling={false} onNodeClick={(_,n)=>{const cl=c.claims.find(cl=>cl.id===n.id);if(cl)onSelect(cl);}} colorMode="system"><Background color="var(--line)" gap={24}/><Controls showInteractive={false}/></ReactFlow></div>
 </div>;
}
