import {handleTurn,updateInvestigationReply,type ChatState} from '@/lib/truestate/conversation';
import { load, save } from '@/lib/truestate/store';
import { SCENARIOS, AGENTS, consumeEvent, step, seedState, uid, record, releasePayment, overview, report, evaluate, type Scenario } from '@/lib/truestate/engine';
export const dynamic='force-dynamic';
const json=(value:unknown,status=200)=>Response.json(value,{status,headers:{'Cache-Control':'no-store'}});
function identity(req:Request){const id=req.headers.get('oai-authenticated-user-id');if(!id)throw new Error('Authentication required');return id;}
function pathOf(req:Request){return new URL(req.url).pathname.replace(/^\/api\//,'').split('/');}
export async function GET(req:Request){try{
 const userId=identity(req),x=await load(userId),s=x.state,parts=pathOf(req),[root,id,sub]=parts;
 if(root==='state')return json(s);
 if(root==='health')return json({mode:'demo',database:'Connected',gemini:'Not configured',documentAI:'Not configured',bigQuery:'Not configured',pubSub:'Not configured',agentSearch:'Not configured',paymentProcessor:'Synthetic local adapter'});
 if(root==='dashboard')return json(overview(s));
 if(root==='transactions'){const p=id?s.payments.find(p=>p.id===id):s.payments;return p?json(p):json({error:'Payment not found'},404);}
 if(root==='investigations'){if(!id)return json(s.cases);const c=[...s.cases,...(s.archivedCases||[])].find(c=>c.id===id);if(!c)return json({error:'Case not found'},404);return json(sub==='evidence'?c.claims:sub==='graph'?{nodes:c.claims,edges:c.claims.flatMap(cl=>cl.derivedFrom.map(parent=>({source:parent,target:cl.id,type:'DERIVED_FROM'})))}:sub==='report'?report(s,c):c);}
 if(root==='agents')return json(id==='runs'?s.cases.find(c=>c.id===sub):AGENTS.map(a=>({...a,run:s.cases.find(c=>!c.finishedAt&&c.activeAgent===a.id)??null})));
 if(root==='audit')return json(s.audit);
 if(root==='evaluation')return json(s.evaluation);
 return json({error:'Endpoint not found'},404);
 }catch(e){const error=(e as Error).message;return json({error},error==='Authentication required'?401:500);}}
export async function POST(req:Request){try{
 const userId=identity(req);const origin=req.headers.get('origin');if(origin&&origin!==new URL(req.url).origin)return json({error:'Cross-origin action denied'},403);
 const body=await req.json() as Record<string,any>;const [root,id,action]=pathOf(req);const x=await load(userId),s=x.state;
 if(root==='chat'){
  const result=handleTurn(s as ChatState,{conversationId:body.conversationId||undefined,requestId:body.requestId,prompt:body.prompt||'',attachmentIds:body.attachmentIds},userId,s.role);
  await save(x);const encoder=new TextEncoder();
  const stream=new ReadableStream({async start(controller){
   const emit=(event:string,data:unknown)=>{try{controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));}catch{}};
   const textReply=()=>{const m=(s as ChatState).conversations?.find(c=>c.id===result.conversationId)?.messages.find(m=>m.id===result.messageId);if(m){emit('response',{messageId:m.id});for(const text of m.text.match(/[\s\S]{1,120}/g)||[])emit('delta',{messageId:m.id,text});}};
   emit('status',{phase:result.scopeRejected?'rejected':'accepted',message:result.scopeRejected?'Outside TRUESTATE scope':'Financial scope checked'});textReply();emit('state',{state:s,...result});
   try{if(result.runCaseId){const c=s.cases.find(c=>c.id===result.runCaseId);if(!c)throw new Error('Investigation not found');while(!c.finishedAt){step(s,c);updateInvestigationReply(s as ChatState,result.conversationId,result.messageId,c.id);await save(x);emit('status',{phase:'investigation',message:c.receipts.at(-1)?.summary||'Checking evidence',step:c.stage,total:13});if(c.finishedAt)textReply();emit('state',{state:s,...result});if(!c.finishedAt)await new Promise(r=>setTimeout(r,550));}}emit('done',result);}catch(e){emit('error',{error:(e as Error).message});}finally{try{controller.close();}catch{}}
  }});return new Response(stream,{headers:{'Content-Type':'text/event-stream','Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'}});
 }
 if((root==='simulations'&&id==='start')||root==='events'){
  const scenario=body.scenario as Scenario;if(!SCENARIOS.some(v=>v.id===scenario))return json({error:'Unknown scenario'},400);
  const eventId=body.eventId||req.headers.get('idempotency-key')||uid();if(eventId.length>128)return json({error:'Invalid event ID'},400);
  const c=consumeEvent(s,scenario,eventId);await save(x);
  const encoder=new TextEncoder();const stream=new ReadableStream({async start(controller){
   const emit=(event:string,data:unknown)=>{try{controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));}catch{/* Client disconnected; still finish the bounded workflow. */}};
   emit('state',s);
   try{while(!c.finishedAt){step(s,c);await save(x);emit('state',s);if(!c.finishedAt)await new Promise(r=>setTimeout(r,550));}emit('done',{caseId:c.id});}catch(e){emit('error',{error:(e as Error).message});}finally{try{controller.close();}catch{}}
  }});return new Response(stream,{headers:{'Content-Type':'text/event-stream','Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'}});
 }
 if(root==='simulations'&&id==='recover'){const c=s.cases.find(c=>!c.finishedAt);if(!c)return json({error:'No interrupted run'},400);if(Date.now()-Date.parse(c.startedAt)<65000)return json({error:'The run is still within its 60-second deadline'},409);c.status='Escalated';c.error='Run interrupted or deadline exceeded; human review required.';c.finishedAt=new Date().toISOString();record(s,'RUN_RECOVERED',c.error,c.id,'reviewer');await save(x);return json(s);}
 if(s.cases.some(c=>!c.finishedAt))return json({error:'An investigation is running. Wait for it to finish.'},409);
 if(root==='simulations'&&id==='reset'){const fresh=seedState() as ChatState;fresh.conversations=(s as ChatState).conversations;fresh.attachments=(s as ChatState).attachments;fresh.audit=s.audit;fresh.archivedCases=[...(s.archivedCases||[]),...s.cases];fresh.archivedPayments=[...(s.archivedPayments||[]),...s.payments.filter(p=>p.caseId)];record(fresh,'DEMO_RESET','Synthetic working records reset. Historical audit events retained.',null,userId);x.state=fresh;await save(x);return json(fresh);}
 if(root==='evaluation'&&id==='run'){s.evaluation=evaluate();record(s,'EVALUATION_COMPLETED',`${s.evaluation.count} frozen synthetic cases executed.`,null,userId);await save(x);return json(s);}
 if(root==='payments'&&action==='approve-release'){try{releasePayment(s,id,userId,s.role,body.reason||'');}catch(e){return json({error:(e as Error).message},403);}await save(x);return json(s);}
 if(root==='payments'&&action==='request-hold'){const p=s.payments.find(p=>p.id===id);if(!p)return json({error:'Payment not found'},404);if(s.role!=='reviewer')return json({error:'Reviewer required'},403);if((body.reason||'').trim().length<15)return json({error:'Provide a justification of at least 15 characters'},400);if(p.state==='Released')return json({error:'A released payment cannot be held'},409);if(p.state!=='Held'){p.state='Held';record(s,'REVIEWER_PRECAUTIONARY_HOLD',`${p.ref}: ${body.reason}`,p.caseId,userId);}await save(x);return json(s);}
 if(root==='investigations'&&(action==='verify'||action==='escalate')){const c=s.cases.find(c=>c.id===id);if(!c)return json({error:'Case not found'},404);c.status='Escalated';record(s,action==='verify'?'VERIFICATION_REQUESTED':'HUMAN_ESCALATION',action==='verify'?'Human verification requested through the pre-established supplier contact. No message sent.':body.reason||'Reviewer escalation requested.',c.id,userId);await save(x);return json(s);}
 return json({error:'Endpoint not found'},404);
 }catch(e){const error=(e as Error).message;return json({error},error==='Authentication required'?401:409);}}
