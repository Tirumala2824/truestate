"""Normalized domain schema. Operational snapshots are projected into these tables.
The hosted Worker uses a compact D1 snapshot plus immutable audit; this SQLAlchemy
schema is the portable Cloud SQL/SQLite read model and full domain extension point.
"""
import json
from datetime import datetime, timezone
from uuid import uuid5,NAMESPACE_URL
from sqlalchemy import Table,Column,String,Text,Integer,ForeignKey,select,insert,update

def define(metadata):
    def table(name,*columns):return Table(name,metadata,Column('id',String(36),primary_key=True),*columns,Column('payload',Text,nullable=False,default='{}'),Column('created_at',String,nullable=False),Column('updated_at',String,nullable=False))
    org=table('organizations',Column('tenant_id',String,nullable=False,unique=True))
    def scoped(name,*cols):return table(name,Column('organization_id',String(36),ForeignKey('organizations.id'),nullable=False),*cols)
    def fk(name,target,nullable=True):return Column(name,String(36),ForeignKey(target+'.id'),nullable=nullable)
    t={'organizations':org}
    t['suppliers']=scoped('suppliers',Column('name',String,nullable=False))
    t['trusted_supplier_contacts']=scoped('trusted_supplier_contacts',fk('supplier_id','suppliers',False),Column('channel',String))
    t['bank_accounts']=scoped('bank_accounts',fk('supplier_id','suppliers'),Column('account_identifier',String))
    t['purchase_orders']=scoped('purchase_orders',fk('supplier_id','suppliers'))
    t['invoices']=scoped('invoices',fk('supplier_id','suppliers'),fk('purchase_order_id','purchase_orders'))
    t['invoice_line_items']=scoped('invoice_line_items',fk('invoice_id','invoices',False),Column('amount_minor',Integer))
    t['payment_batches']=scoped('payment_batches')
    t['payments']=scoped('payments',fk('supplier_id','suppliers',False),fk('bank_account_id','bank_accounts'),fk('batch_id','payment_batches'),Column('amount_minor',Integer,nullable=False),Column('state',String,nullable=False))
    t['users_and_roles']=scoped('users_and_roles',Column('subject',String,nullable=False),Column('role',String,nullable=False))
    t['approval_events']=scoped('approval_events',fk('payment_id','payments'),fk('approver_id','users_and_roles'))
    t['account_change_events']=scoped('account_change_events',fk('supplier_id','suppliers'),Column('external_event_id',String))
    t['source_documents']=scoped('source_documents',Column('source_system',String),Column('integrity_status',String))
    t['evidence_claims']=scoped('evidence_claims',Column('subject',String),Column('predicate',String),Column('value',String),Column('source_system',String),fk('source_document_id','source_documents'),Column('originating_event_id',String),Column('derived_from_claim_ids',Text),Column('observed_at',String),Column('asserted_at',String),Column('integrity_verification_status',String),Column('independent_verification_status',String),Column('confidentiality_classification',String))
    t['evidence_dependencies']=scoped('evidence_dependencies',fk('parent_claim_id','evidence_claims',False),fk('child_claim_id','evidence_claims',False),Column('relation',String))
    t['investigation_cases']=scoped('investigation_cases',fk('payment_id','payments',False),Column('status',String))
    t['agent_runs']=scoped('agent_runs',fk('case_id','investigation_cases',False),Column('agent',String))
    t['agent_tool_calls']=scoped('agent_tool_calls',fk('run_id','agent_runs',False),Column('tool',String),Column('status',String))
    t['hypotheses']=scoped('hypotheses',fk('case_id','investigation_cases',False),Column('status',String))
    t['verification_requests']=scoped('verification_requests',fk('case_id','investigation_cases',False),Column('status',String))
    t['policy_decisions']=scoped('policy_decisions',fk('case_id','investigation_cases',False),Column('allowed',Integer),Column('policy_id',String))
    t['containment_actions']=scoped('containment_actions',fk('payment_id','payments',False),fk('case_id','investigation_cases',False),Column('idempotency_key',String,nullable=False,unique=True),Column('state',String))
    return t

def project(conn,t,tenant,state):
    stamp=datetime.now(timezone.utc).isoformat();org_id=str(uuid5(NAMESPACE_URL,'truestate:'+tenant))
    def key(v):return str(uuid5(NAMESPACE_URL,org_id+':'+v))
    def up(table_name,id,payload,**values):
        tab=t[table_name];data={'id':id,'payload':json.dumps(payload,sort_keys=True),'updated_at':stamp,**values}
        if table_name!='organizations':data['organization_id']=org_id
        existing=conn.execute(select(tab.c.id,tab.c.payload).where(tab.c.id==id)).first()
        if existing:
            if existing.payload!=data['payload']:conn.execute(update(tab).where(tab.c.id==id).values(**data))
        else:conn.execute(insert(tab).values(**data,created_at=stamp))
    up('organizations',org_id,{'name':'Meridian Finance Operations'},tenant_id=tenant)
    up('users_and_roles',key('user:'+tenant),{'role':state['role']},subject=tenant,role=state['role'])
    for p in state['payments']:
        supplier=key('supplier:'+p['supplier']);account=key('account:'+p['supplier']+':'+p['account'])
        up('suppliers',supplier,{'name':p['supplier']},name=p['supplier'])
        up('bank_accounts',account,{'identifier':p['account']},supplier_id=supplier,account_identifier=p['account'])
        up('payments',p['id'],p,supplier_id=supplier,bank_account_id=account,amount_minor=p['amount']*100,state=p['state'])
    for c in state['cases']:
        up('investigation_cases',c['id'],{k:v for k,v in c.items() if k not in ('claims','receipts','hypotheses')},payment_id=c['paymentId'],status=c['status'])
        up('account_change_events',key('event:'+c['eventId']),{'eventId':c['eventId']},supplier_id=key('supplier:'+c['supplier']),external_event_id=c['eventId'])
        for cl in c['claims']:
            up('source_documents',cl['documentId'],{'text':cl['content']},source_system=cl['sourceSystem'],integrity_status=cl['integrity'])
            up('evidence_claims',cl['id'],cl,subject=cl['subject'],predicate=cl['predicate'],value=cl['value'],source_system=cl['sourceSystem'],source_document_id=cl['documentId'],originating_event_id=cl['origin'],derived_from_claim_ids=json.dumps(cl['derivedFrom']),observed_at=cl['observedAt'],asserted_at=cl['assertedAt'],integrity_verification_status=cl['integrity'],independent_verification_status=cl['independence'],confidentiality_classification=cl['classification'])
        for cl in c['claims']:
            for parent in cl['derivedFrom']:up('evidence_dependencies',key(parent+':'+cl['id']),{'parent':parent,'child':cl['id']},parent_claim_id=parent,child_claim_id=cl['id'],relation='DERIVED_FROM')
        for h in c['hypotheses']:up('hypotheses',key(c['id']+':'+h['name']),h,case_id=c['id'],status=h['status'])
        for r in c['receipts']:
            run_id=key(c['id']+':'+r['agent']);up('agent_runs',run_id,{'agent':r['agent']},case_id=c['id'],agent=r['agent'])
            up('agent_tool_calls',r['id'],r,run_id=run_id,tool=r['tool'],status=r['status'])
            if r['tool']=='policy_gateway':up('policy_decisions',r['id'],r['output'],case_id=c['id'],allowed=int(r['output']['allowed']),policy_id=c['policyId'])
        if c['attempts']:up('containment_actions',key(c['id']+':hold'),{'attempts':c['attempts'],'verified':c['verified']},payment_id=c['paymentId'],case_id=c['id'],idempotency_key=c['idempotencyKey'],state=next(p['state'] for p in state['payments'] if p['id']==c['paymentId']))
