"""FastAPI transport for the shared TRUESTATE engine. Run from repository root."""
import asyncio, base64, hashlib, json, os, secrets, subprocess
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field
from . import repository
ROOT=Path(__file__).resolve().parents[1]
def bridge(op,**kwargs):
    result=subprocess.run(['node',str(ROOT/'backend/bridge.mjs')],input=json.dumps({'op':op,**kwargs}),capture_output=True,text=True,timeout=20,cwd=ROOT)
    data=json.loads(result.stdout)
    if not data['ok']:raise ValueError(data['error'])
    return data['value']
def add_audit(state,action,detail,case_id=None,actor='reviewer'):
    state['audit'].append(dict(id=str(uuid4()),at=datetime.now(timezone.utc).isoformat(),caseId=case_id,actor=actor,action=action,detail=detail,evidenceIds=[]))
@asynccontextmanager
async def lifespan(app):
    if os.getenv('TRUESTATE_MODE','demo')=='cloud' and not os.getenv('DATABASE_URL','').startswith('postgresql'):
        raise RuntimeError('Cloud mode requires durable PostgreSQL DATABASE_URL. SQLite is local only.')
    if os.getenv('TRUESTATE_MIGRATE_ON_START','1')=='1':repository.migrate()
    yield
app=FastAPI(title='TRUESTATE API',version='1.0.0',lifespan=lifespan)
class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario:Literal['coordinated','legitimate','simple','insufficient','failed']
    eventId:str=Field(default_factory=lambda:str(uuid4()),max_length=128)
class ChatPrompt(BaseModel):
    model_config=ConfigDict(extra='forbid')
    prompt:str=Field(min_length=1,max_length=4000)
    requestId:str=Field(min_length=1,max_length=128)
    conversationId:str|None=None
    attachmentIds:list[str]=Field(default_factory=list,max_length=3)
class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(default='',max_length=2000)
class Principal(BaseModel):
    user_id:str
    role:Literal['analyst','reviewer']
def principal(req:Request):
    """Server config maps bearer tokens to roles; request JSON never selects a role."""
    token=req.headers.get('authorization','').removeprefix('Bearer ')
    if req.url.path=='/api/pubsub' and os.getenv('PUBSUB_AUDIENCE'):
        try:
            from google.oauth2 import id_token
            from google.auth.transport.requests import Request as GoogleRequest
            claims=id_token.verify_oauth2_token(token,GoogleRequest(),os.environ['PUBSUB_AUDIENCE'])
            if claims.get('email')!=os.environ['PUBSUB_SERVICE_ACCOUNT'] or not claims.get('email_verified'):raise ValueError('Unexpected service identity')
            return Principal(user_id=os.environ['PUBSUB_TENANT_ID'],role='analyst')
        except Exception:raise HTTPException(401,'Invalid Pub/Sub OIDC identity')
    configured=os.getenv('TRUESTATE_API_TOKENS','')
    if configured:
        mapping=json.loads(configured)
        for key,entry in mapping.items():
            if secrets.compare_digest(key,token):return Principal(**entry)
        raise HTTPException(401,'Valid API bearer token required')
    # Explicit opt-in demo auth only. Never enabled implicitly on Cloud Run.
    if os.getenv('TRUESTATE_LOCAL_DEMO_AUTH')=='1' and not os.getenv('K_SERVICE') and os.getenv('TRUESTATE_MODE','demo')=='demo':return Principal(user_id='local-demo',role='reviewer')
    raise HTTPException(401,'Configure TRUESTATE_API_TOKENS or explicitly enable local demo auth')
def loaded(p):return repository.load(p.user_id,lambda:bridge('seed'))
def case_of(s,case_id):
    c=next((c for c in s['cases']+s.get('archivedCases',[]) if c['id']==case_id),None)
    if not c:raise HTTPException(404,'Case not found in this workspace')
    return c
def idle(s):
    if any(not c['finishedAt'] for c in s['cases']):raise HTTPException(409,'An investigation is running')
@app.get('/api/state')
def state(p:Principal=Depends(principal)):return loaded(p)[0]
@app.get('/api/health')
def health(p:Principal=Depends(principal)):
    from .cloud import integration_health
    return integration_health()
@app.get('/api/dashboard/overview')
def overview(p:Principal=Depends(principal)):return bridge('overview',state=loaded(p)[0])
@app.get('/api/transactions')
def payments(p:Principal=Depends(principal)):return loaded(p)[0]['payments']
@app.get('/api/transactions/{payment_id}')
def payment(payment_id:str,p:Principal=Depends(principal)):
    result=next((v for v in loaded(p)[0]['payments'] if v['id']==payment_id),None)
    if not result:raise HTTPException(404,'Payment not found')
    return result
@app.get('/api/investigations')
def investigations(p:Principal=Depends(principal)):return loaded(p)[0]['cases']
@app.get('/api/investigations/{case_id}')
def investigation(case_id:str,p:Principal=Depends(principal)):return case_of(loaded(p)[0],case_id)
@app.get('/api/investigations/{case_id}/evidence')
def evidence(case_id:str,p:Principal=Depends(principal)):return case_of(loaded(p)[0],case_id)['claims']
@app.get('/api/investigations/{case_id}/graph')
def graph(case_id:str,p:Principal=Depends(principal)):
    c=case_of(loaded(p)[0],case_id)
    return {'nodes':c['claims'],'edges':[{'source':parent,'target':cl['id'],'type':'DERIVED_FROM'} for cl in c['claims'] for parent in cl['derivedFrom']]}
@app.get('/api/investigations/{case_id}/report')
def report(case_id:str,p:Principal=Depends(principal)):return bridge('report',state=loaded(p)[0],caseId=case_id)
@app.get('/api/agents/status')
def agents(p:Principal=Depends(principal)):
    s,_=loaded(p);c=next((c for c in s['cases'] if not c['finishedAt']),None)
    return {'mode':os.getenv('TRUESTATE_MODE','demo'),'activeAgent':c['activeAgent'] if c else None}
@app.get('/api/agents/runs/{case_id}')
def run(case_id:str,p:Principal=Depends(principal)):return case_of(loaded(p)[0],case_id)['receipts']
@app.get('/api/audit/events')
def audit(p:Principal=Depends(principal)):return loaded(p)[0]['audit']
@app.get('/api/evaluation/results')
def evaluation(p:Principal=Depends(principal)):return loaded(p)[0]['evaluation']
async def drive(s,revision,case_id,p,delay=0.2):
    while not case_of(s,case_id)['finishedAt']:
        c=case_of(s,case_id)
        # Optional live ADK reasoning is advisory; the independent gateway still owns authorization.
        if c['stage']==7 and os.getenv('TRUESTATE_MODE','demo')=='cloud' and not c.get('cloudReasoning'):
            from .adk_agents import investigate
            try:c['cloudReasoning']=await investigate(c,p.user_id)
            except Exception as exc:
                c['cloudReasoning']={'status':'error','error':type(exc).__name__,'liveVerified':False}
                c['status']='Escalated';c['error']='Cloud reasoning unavailable; no automated containment executed.';c['finishedAt']=datetime.now(timezone.utc).isoformat();add_audit(s,'CLOUD_ERROR',c['error'],c['id'])
                revision=repository.save(p.user_id,s,revision);yield s;return
        s=await asyncio.to_thread(bridge,'step',state=s,caseId=case_id)
        revision=repository.save(p.user_id,s,revision)
        yield s
        if delay:await asyncio.sleep(delay)
@app.post('/api/chat')
async def chat(body:ChatPrompt,p:Principal=Depends(principal)):
    s,revision=loaded(p)
    try:result=bridge('chat',state=s,input=body.model_dump(),actor=p.user_id,role=p.role)
    except ValueError as exc:raise HTTPException(409,str(exc))
    s=result['state'];revision=repository.save(p.user_id,s,revision)
    async def stream():
        nonlocal s,revision
        meta={k:v for k,v in result.items() if k!='state'}
        yield 'event: status\ndata: '+json.dumps({'phase':'rejected' if result.get('scopeRejected') else 'accepted','message':'Outside TRUESTATE scope' if result.get('scopeRejected') else 'Financial scope checked'})+'\n\n'
        message=next(m for c in s['conversations'] if c['id']==result['conversationId'] for m in c['messages'] if m['id']==result['messageId'])
        yield 'event: response\ndata: '+json.dumps({'messageId':message['id']})+'\n\n'
        for offset in range(0,len(message['text']),120):yield 'event: delta\ndata: '+json.dumps({'messageId':message['id'],'text':message['text'][offset:offset+120]})+'\n\n'
        yield 'event: state\ndata: '+json.dumps({'state':s,**meta})+'\n\n'
        try:
            case_id=result.get('runCaseId')
            if case_id:
                async for value in drive(s,revision,case_id,p):
                    s=value
                    # drive committed this stage; reload its current revision before saving chat.
                    _,revision=loaded(p)
                    s=bridge('chat_update',state=s,conversationId=result['conversationId'],messageId=result['messageId'],caseId=case_id)
                    # Persist only the final conversational summary; intermediate frames are live views.
                    if case_of(s,case_id)['finishedAt']:revision=repository.save(p.user_id,s,revision)
                    current=case_of(s,case_id)
                    yield 'event: status\ndata: '+json.dumps({'phase':'investigation','message':current['receipts'][-1]['summary'] if current['receipts'] else 'Checking evidence','step':current['stage'],'total':13})+'\n\n'
                    yield 'event: state\ndata: '+json.dumps({'state':s,**meta})+'\n\n'
            yield 'event: done\ndata: '+json.dumps(meta)+'\n\n'
        except Exception as exc:
            yield 'event: error\ndata: '+json.dumps({'error':str(exc)})+'\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream')
@app.post('/api/simulations/start')
async def start(body:Start,p:Principal=Depends(principal)):
    s,revision=loaded(p)
    try:result=bridge('start',state=s,scenario=body.scenario,eventId=body.eventId)
    except ValueError as exc:raise HTTPException(409,str(exc))
    s=result['state'];revision=repository.save(p.user_id,s,revision)
    async def stream():
        yield 'event: state\ndata: '+json.dumps(s)+'\n\n'
        async for value in drive(s,revision,result['caseId'],p):yield 'event: state\ndata: '+json.dumps(value)+'\n\n'
        yield 'event: done\ndata: '+json.dumps({'caseId':result['caseId']})+'\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream')
@app.post('/api/events')
async def event(body:Start,p:Principal=Depends(principal)):
    """Non-chat event ingestion. Acknowledge only after bounded execution is persisted."""
    s,revision=loaded(p)
    try:result=bridge('start',state=s,scenario=body.scenario,eventId=body.eventId)
    except ValueError as exc:raise HTTPException(409,str(exc))
    s=result['state'];revision=repository.save(p.user_id,s,revision)
    async for value in drive(s,revision,result['caseId'],p,delay=0):s=value
    return case_of(s,result['caseId'])
@app.post('/api/pubsub')
async def pubsub(req:Request,p:Principal=Depends(principal)):
    envelope=await req.json()
    try:
        data=json.loads(base64.b64decode(envelope['message']['data'],validate=True));data['eventId']=envelope['message']['messageId'];body=Start.model_validate(data)
    except Exception:raise HTTPException(400,'Invalid synthetic Pub/Sub envelope')
    return await event(body,p)
@app.post('/api/simulations/reset')
def reset(p:Principal=Depends(principal)):
    if p.role!='reviewer':raise HTTPException(403,'Reviewer required')
    s,revision=loaded(p);idle(s);fresh=bridge('seed');fresh['attachments']=s.get('attachments',[]);fresh['conversations']=s.get('conversations',[]);fresh['audit']=s['audit'];fresh['archivedCases']=s.get('archivedCases',[])+s['cases'];fresh['archivedPayments']=s.get('archivedPayments',[])+[p for p in s['payments'] if p['caseId']];add_audit(fresh,'DEMO_RESET','Working data reset; audit retained',actor=p.user_id);repository.save(p.user_id,fresh,revision);return fresh
@app.post('/api/simulations/recover')
def recover(p:Principal=Depends(principal)):
    s,revision=loaded(p);c=next((c for c in s['cases'] if not c['finishedAt']),None)
    if not c:raise HTTPException(400,'No interrupted case')
    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(c['startedAt'].replace('Z','+00:00'))).total_seconds()
    if elapsed<65:raise HTTPException(409,'Execution deadline has not elapsed')
    c['status']='Escalated';c['finishedAt']=datetime.now(timezone.utc).isoformat();c['error']='Interrupted run: human review required';add_audit(s,'RUN_RECOVERED',c['error'],c['id']);repository.save(p.user_id,s,revision);return s
@app.post('/api/evaluation/run')
def evaluate(p:Principal=Depends(principal)):
    s,revision=loaded(p);idle(s);s['evaluation']=bridge('evaluate');add_audit(s,'EVALUATION_COMPLETED','120 frozen synthetic cases executed',actor=p.user_id);repository.save(p.user_id,s,revision);return s
@app.post('/api/payments/{payment_id}/approve-release')
def release(payment_id:str,body:Action,p:Principal=Depends(principal)):
    s,revision=loaded(p)
    try:s=bridge('release',state=s,paymentId=payment_id,actor=p.user_id,role=p.role,reason=body.reason)
    except ValueError as exc:raise HTTPException(403,str(exc))
    repository.save(p.user_id,s,revision);return s
@app.post('/api/payments/{payment_id}/request-hold')
def hold(payment_id:str,body:Action,p:Principal=Depends(principal)):
    if p.role!='reviewer':raise HTTPException(403,'Reviewer required')
    if len(body.reason.strip())<15:raise HTTPException(400,'Reviewer justification required (15 characters)')
    s,revision=loaded(p);idle(s);payment=next((v for v in s['payments'] if v['id']==payment_id),None)
    if not payment:raise HTTPException(404,'Payment not found')
    if payment['state']=='Released':raise HTTPException(409,'Released payment cannot be held')
    if payment['state']!='Held':payment['state']='Held';add_audit(s,'REVIEWER_PRECAUTIONARY_HOLD',body.reason,payment['caseId'],p.user_id)
    repository.save(p.user_id,s,revision);return s
@app.post('/api/investigations/{case_id}/verify')
@app.post('/api/investigations/{case_id}/escalate')
def verification(case_id:str,req:Request,p:Principal=Depends(principal)):
    s,revision=loaded(p);idle(s);c=case_of(s,case_id);c['status']='Escalated';add_audit(s,'HUMAN_VERIFICATION_REQUESTED','Human review requested. No external message sent.',case_id,p.user_id);repository.save(p.user_id,s,revision);return s


MAX_UPLOAD=8*1024*1024
UPLOAD_ROOT=Path(os.getenv('TRUESTATE_UPLOAD_DIR',str(ROOT/'.private-evidence')))
def evidence_path(user_id,file_id):
    return UPLOAD_ROOT/hashlib.sha256(user_id.encode()).hexdigest()/file_id
@app.post('/api/uploads')
async def upload_evidence(request:Request,p:Principal=Depends(principal)):
    if int(request.headers.get('content-length','0'))>MAX_UPLOAD+100000:raise HTTPException(413,'File is too large')
    s,revision=loaded(p);idle(s);files=s.setdefault('attachments',[])
    if len(files)>=30:raise HTTPException(422,'Workspace evidence limit reached')
    form=await request.form(max_files=1,max_fields=1,max_part_size=100000);file=form.get('file')
    if not file or not hasattr(file,'read'):raise HTTPException(422,'Choose a financial source file')
    data=await file.read(MAX_UPLOAD+1);await file.close()
    if not data or len(data)>MAX_UPLOAD:raise HTTPException(413,'Each file must be between 1 byte and 8 MB')
    if sum(a['size'] for a in files)+len(data)>64*1024*1024:raise HTTPException(422,'Workspace evidence limit reached')
    try:attachment=bridge('prepare_upload',name=file.filename,mime=file.content_type,bytes=base64.b64encode(data).decode(),extraction=json.loads(form.get('extraction','{}')))
    except Exception as exc:raise HTTPException(422,str(exc))
    attachment.update(id=str(uuid4()),sha256=hashlib.sha256(data).hexdigest(),createdAt=datetime.now(timezone.utc).isoformat())
    path=evidence_path(p.user_id,attachment['id']);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);files.append(attachment)
    try:repository.save(p.user_id,s,revision)
    except Exception:path.unlink(missing_ok=True);raise
    return {'attachment':attachment}
@app.get('/api/uploads/{file_id}')
def download_evidence(file_id:str,p:Principal=Depends(principal)):
    s,_=loaded(p);file=next((a for a in s.get('attachments',[]) if a['id']==file_id),None)
    if not file:raise HTTPException(404,'File not found in this workspace')
    path=evidence_path(p.user_id,file['id'])
    if not path.is_file():raise HTTPException(404,'Source file unavailable')
    return FileResponse(path,media_type=file['mime'],filename=file['name'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@app.delete('/api/uploads/{file_id}')
def remove_draft_evidence(file_id:str,p:Principal=Depends(principal)):
    s,revision=loaded(p);file=next((a for a in s.get('attachments',[]) if a['id']==file_id),None)
    if not file:raise HTTPException(404,'File not found in this workspace')
    if any(file_id in m.get('attachmentIds',[]) for c in s.get('conversations',[]) for m in c['messages']):raise HTTPException(409,'Evidence referenced by a saved conversation must be retained')
    s['attachments']=[a for a in s['attachments'] if a['id']!=file_id];repository.save(p.user_id,s,revision);evidence_path(p.user_id,file['id']).unlink(missing_ok=True);return {'removed':True}
