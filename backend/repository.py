"""Durable tenant-scoped snapshot storage plus append-only audit in SQLite/PostgreSQL."""
import json, os
from sqlalchemy import create_engine, MetaData, Table, Column, String, Text, Integer, select, insert, update
from sqlalchemy.exc import IntegrityError
engine=create_engine(os.getenv('DATABASE_URL','sqlite:///./truestate.db'),connect_args={'check_same_thread':False} if os.getenv('DATABASE_URL','sqlite:').startswith('sqlite') else {})
metadata=MetaData()
workspaces=Table('demo_workspaces',metadata,Column('user_id',String,primary_key=True),Column('data',Text,nullable=False),Column('revision',Integer,nullable=False,default=0))
audit=Table('audit_events',metadata,Column('id',String,primary_key=True),Column('user_id',String,nullable=False,index=True),Column('data',Text,nullable=False))
from .models import define, project
domain=define(metadata)
def migrate():
    metadata.create_all(engine)
    if engine.dialect.name=='sqlite':
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END")
            conn.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END")
    else:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE OR REPLACE FUNCTION truestate_deny_audit_change() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only audit'; END; $$ LANGUAGE plpgsql")
            conn.exec_driver_sql('DROP TRIGGER IF EXISTS audit_immutable ON audit_events')
            conn.exec_driver_sql('CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION truestate_deny_audit_change()')
def load(user_id,seed):
    with engine.begin() as conn:
        row=conn.execute(select(workspaces).where(workspaces.c.user_id==user_id)).mappings().first()
        if row:return json.loads(row['data']),row['revision']
    state=seed()
    try:
        with engine.begin() as conn:conn.execute(insert(workspaces).values(user_id=user_id,data=json.dumps(state),revision=0))
        return state,0
    except IntegrityError:return load(user_id,seed)
def save(user_id,state,revision):
    with engine.begin() as conn:
        result=conn.execute(update(workspaces).where(workspaces.c.user_id==user_id,workspaces.c.revision==revision).values(data=json.dumps(state),revision=revision+1))
        if result.rowcount!=1:raise RuntimeError('Concurrent workspace update; refresh and retry')
        seen=set(conn.execute(select(audit.c.id).where(audit.c.user_id==user_id)).scalars())
        new=[{'id':a['id'],'user_id':user_id,'data':json.dumps(a)} for a in state['audit'] if a['id'] not in seen]
        if new:conn.execute(insert(audit),new)
        project(conn,domain,user_id,state)
    return revision+1
if __name__=='__main__':migrate()
