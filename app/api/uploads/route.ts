import {env} from 'cloudflare:workers';
import {load,save} from '@/lib/truestate/store';
import {prepareAttachment,MAX_FILE_BYTES,type ExtractionInput,type Attachment} from '@/lib/truestate/evidence-input';
import type {ChatState} from '@/lib/truestate/conversation';
export const dynamic='force-dynamic';
export async function POST(req:Request){try{
 const userId=req.headers.get('oai-authenticated-user-id');if(!userId)return Response.json({error:'Authentication required'},{status:401});
 const origin=req.headers.get('origin');if(origin&&origin!==new URL(req.url).origin)return Response.json({error:'Cross-origin upload denied'},{status:403});
 if(!env.BUCKET)throw new Error('Evidence storage is unavailable.');
 if(Number(req.headers.get('content-length')||0)>MAX_FILE_BYTES+100000)return Response.json({error:'File is too large'},{status:413});
 const x=await load(userId),s=x.state as ChatState;if(s.cases.some(c=>!c.finishedAt))throw new Error('Wait for the active investigation before uploading.');
 const uploads=s.attachments??=[];if(uploads.length>=30||uploads.reduce((v,a)=>v+a.size,0)>=64*1024*1024)throw new Error('This workspace has reached its evidence upload limit.');
 const reader=req.body?.getReader();if(!reader)throw new Error('Choose a financial source file.');const chunks:Uint8Array[]=[];let total=0;while(true){const part=await reader.read();if(part.done)break;total+=part.value.length;if(total>MAX_FILE_BYTES+100000){await reader.cancel();return Response.json({error:'Upload is too large'},{status:413});}chunks.push(part.value);}const body=new Uint8Array(total);let offset=0;for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.length;}const form=await new Response(body,{headers:{'Content-Type':req.headers.get('content-type')||''}}).formData(),file=form.get('file');if(!file||typeof file==='string')throw new Error('Choose a financial source file.');
 if(file.size>MAX_FILE_BYTES)throw new Error('Each file must be 8 MB or smaller.');
 const extraction=JSON.parse(String(form.get('extraction')||'{}')) as ExtractionInput;
 const bytes=new Uint8Array(await file.arrayBuffer());const data=prepareAttachment(file.name,file.type,bytes,extraction);
 if(uploads.reduce((v,a)=>v+a.size,0)+bytes.length>64*1024*1024)throw new Error('This workspace has reached its 64 MB evidence limit.');
 const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(v=>v.toString(16).padStart(2,'0')).join('');
 const attachment:Attachment={...data,id:crypto.randomUUID(),sha256,createdAt:new Date().toISOString()};
 const key=`evidence/${encodeURIComponent(userId)}/${attachment.id}`;
 await env.BUCKET.put(key,bytes,{httpMetadata:{contentType:attachment.mime}});uploads.push(attachment);
 try{await save(x);}catch(error){await env.BUCKET.delete(key);throw error;}
 return Response.json({attachment},{headers:{'Cache-Control':'no-store'}});
 }catch(error){return Response.json({error:(error as Error).message},{status:422});}}
