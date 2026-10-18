import { env } from 'cloudflare:workers';
import { seedState, uid, type State } from './engine';
export type Loaded={state:State;revision:number;userId:string;seen:Set<string>};
function database(){if(!env.DB)throw new Error('Database unavailable');return env.DB;}
export async function load(userId:string):Promise<Loaded>{
 const db=database();let row=await db.prepare('SELECT data, revision FROM demo_workspaces WHERE user_id=?').bind(userId).first<{data:string;revision:number}>();
 if(!row){const state=seedState();await db.prepare('INSERT OR IGNORE INTO demo_workspaces (user_id,data,revision,mutation,updated_at) VALUES (?,?,0,?,?)').bind(userId,JSON.stringify(state),uid(),new Date().toISOString()).run();row=await db.prepare('SELECT data, revision FROM demo_workspaces WHERE user_id=?').bind(userId).first<{data:string;revision:number}>();}
 if(!row)throw new Error('Could not initialize demo workspace');const state=JSON.parse(row.data) as State;return {state,revision:row.revision,userId,seen:new Set(state.audit.map(a=>a.id))};
}
export async function save(x:Loaded){const db=database(),mutation=uid(),fresh=x.state.audit.filter(a=>!x.seen.has(a.id));
 const statements=[db.prepare('UPDATE demo_workspaces SET data=?, revision=revision+1, mutation=?, updated_at=? WHERE user_id=? AND revision=?').bind(JSON.stringify(x.state),mutation,new Date().toISOString(),x.userId,x.revision),...fresh.map(a=>db.prepare('INSERT INTO audit_events (id,user_id,case_id,at,actor,action,detail,evidence_ids) SELECT ?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM demo_workspaces WHERE user_id=? AND mutation=?)').bind(a.id,x.userId,a.caseId,a.at,a.actor,a.action,a.detail,JSON.stringify(a.evidenceIds),x.userId,mutation))];
 const result=await db.batch(statements);if(!result[0].meta.changes)throw new Error('Workspace changed concurrently. Refresh and retry.');x.revision++;fresh.forEach(a=>x.seen.add(a.id));
}
