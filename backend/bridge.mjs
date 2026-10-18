/** Shared policy/fixture engine: one implementation for Worker and FastAPI. */
import {prepareAttachment} from '../lib/truestate/evidence-input.ts';
import * as e from '../lib/truestate/engine.ts';
import {handleTurn,updateInvestigationReply} from '../lib/truestate/conversation.ts';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
try{const {op,state,...args}=JSON.parse(raw);let value;
 if(op==='chat'){const result=handleTurn(state,args.input,args.actor,args.role);value={state,...result};}
 else if(op==='chat_update'){updateInvestigationReply(state,args.conversationId,args.messageId,args.caseId);value=state;}
 else if(op==='prepare_upload'){value=prepareAttachment(args.name,args.mime,new Uint8Array(Buffer.from(args.bytes,'base64')),args.extraction);}
 else if(op==='seed')value=e.seedState();
 else if(op==='start'){const c=e.consumeEvent(state,args.scenario,args.eventId);value={state,caseId:c.id};}
 else if(op==='step'){const c=state.cases.find(c=>c.id===args.caseId);if(!c)throw new Error('Case not found');e.step(state,c);value=state;}
 else if(op==='release'){e.releasePayment(state,args.paymentId,args.actor,args.role,args.reason);value=state;}
 else if(op==='evaluate')value=e.evaluate();
 else if(op==='overview')value=e.overview(state);
 else if(op==='report')value=e.report(state,[...state.cases,...(state.archivedCases||[])].find(c=>c.id===args.caseId));
 else if(op==='fixtures')value=Array.from({length:120},(_,i)=>{const kind=['legitimate','simple','coordinated','insufficient','failed'][i%5];return {id:`synthetic-v1-${i}`,scenario:kind,amount:25000+i*4900,fixture:e.fixtureFor(kind,i)};});
 else throw new Error('Unknown operation');
 process.stdout.write(JSON.stringify({ok:true,value}));
}catch(error){process.stdout.write(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;}
