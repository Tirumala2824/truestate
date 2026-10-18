/** Uploaded documents are untrusted evidence. Only bounded financial fields are extracted. */
export const MAX_FILE_BYTES=8*1024*1024;
export const MAX_TEXT_CHARS=18000;
export const FILE_TYPES=['application/pdf','image/png','image/jpeg','image/webp','text/plain','text/csv'] as const;
export type InputKind='pdf'|'image'|'text';
export type FinancialFields={supplier?:string;invoice?:string;account?:string;amount?:string;currency?:string;date?:string};
export type Attachment={id:string;name:string;mime:string;size:number;sha256:string;createdAt:string;kind:InputKind;method:'pdf-text'|'ocr'|'text';pages:number;confidence:number|null;fields:FinancialFields;warnings:string[];status:'unverified';};
export type ExtractionInput={text:string;method:string;pages:number;confidence?:number|null};
export function validateFile(name:string,mime:string,bytes:Uint8Array){
 if(!name||name.length>160||/[\x00-\x1f\x7f/\\]/.test(name))throw new Error('Use a filename under 160 characters without path characters.');
 if(!bytes.length||bytes.length>MAX_FILE_BYTES)throw new Error('Each file must be between 1 byte and 8 MB.');
 if(!FILE_TYPES.includes(mime as any))throw new Error('Supported files: PDF, PNG, JPG, WebP, TXT and CSV.');
 const head=Array.from(bytes.subarray(0,12));const ascii=new TextDecoder().decode(bytes.subarray(0,12));
 const valid=mime==='application/pdf'?ascii.startsWith('%PDF-'):mime==='image/png'?[137,80,78,71,13,10,26,10].every((v,i)=>head[i]===v):mime==='image/jpeg'?head[0]===255&&head[1]===216&&head[2]===255:mime==='image/webp'?ascii.startsWith('RIFF')&&ascii.slice(8,12)==='WEBP':!bytes.subarray(0,2048).includes(0);
 if(!valid)throw new Error('The file contents do not match its declared format.');
}
export function extractFinancialFields(raw:string):{fields:FinancialFields;warnings:string[]}{
 if(typeof raw!=='string'||raw.length>MAX_TEXT_CHARS)throw new Error('The extracted document is too long. Use a shorter file (up to 18,000 text characters).');
 const t=raw.normalize('NFKC').replace(/\r/g,'');
 if(/\b(?:ignore|override|bypass|disregard)\b.{0,70}\b(?:instructions?|rules?|policy|scope|system|previous)\b|\b(?:system prompt|developer message|jailbreak|roleplay|act as|pretend to|base64|execute code)\b/i.test(t))throw new Error('Document rejected: it contains instructions directed at the assistant. Upload financial source records only.');
 const fields:FinancialFields={};
 const read=(pattern:RegExp,max=120)=>{const m=t.match(pattern);return m?.[1]?.trim().slice(0,max);};
 fields.supplier=read(/^(?:supplier|vendor|beneficiary|seller)\s*[:=,]\s*([^\n]{2,120})$/im);
 fields.invoice=read(/^(?:invoice(?:\s*(?:number|no\.?|id|#))?)\s*[:=,]\s*([A-Z0-9][A-Z0-9 /_-]{1,48})$/im,50);
 fields.account=read(/^(?:(?:bank|receiving|beneficiary|new)\s+)?(?:account(?:\s*(?:number|no\.?|id))?|iban)\s*[:=,]\s*([A-Z0-9][A-Z0-9 _*-]{3,46})$/im,48);
 fields.amount=read(/^(?:total(?:\s+amount)?|amount(?:\s+due)?|invoice total)\s*[:=,]\s*((?:(?:INR|USD|EUR|GBP|RS\.?)\s*|[₹$€£]\s*)?[\d,]+(?:\.\d{1,2})?)$/im,40);
 fields.currency=read(/^currency\s*[:=,]\s*(INR|USD|EUR|GBP)$/im,3)?.toUpperCase();
 fields.date=read(/^(?:invoice\s+)?date\s*[:=,]\s*([\d]{2,4}[/-][\d]{1,2}[/-][\d]{2,4})$/im,16);
 if(!/\b(?:invoice|supplier|vendor|payment|bank account|beneficiary|purchase order|remittance)\b/i.test(t)||!fields.supplier||(!fields.account&&!fields.amount&&!fields.invoice))throw new Error('Out of scope: no readable supplier-payment record was found. Upload an invoice, supplier bank-change record, or payment evidence with labeled fields.');
 // These are displayed as quoted data, never interpreted as a prompt or as authoritative evidence.
 const warnings=['User-supplied evidence; not independently authenticated.','Extracted fields may contain OCR or formatting errors. Check the original before use.'];
 if(!fields.account)warnings.push('No labeled receiving account was found.');if(!fields.amount)warnings.push('No labeled total or amount was found.');
 return {fields,warnings};
}
export function prepareAttachment(name:string,mime:string,bytes:Uint8Array,input:ExtractionInput):Omit<Attachment,'id'|'sha256'|'createdAt'>{
 validateFile(name,mime,bytes);const kind:InputKind=mime==='application/pdf'?'pdf':mime.startsWith('image/')?'image':'text';
 if(!Number.isInteger(input.pages)||input.pages<1||input.pages>10)throw new Error('Use a document with 1–10 pages.');
 if(!['text','pdf-text','ocr'].includes(input.method)||kind==='image'&&input.method!=='ocr'||kind==='text'&&input.method!=='text'||kind==='pdf'&&input.method==='text')throw new Error('Invalid extraction method for this file.');
 if(input.confidence!=null&&(!Number.isFinite(input.confidence)||input.confidence<0||input.confidence>100))throw new Error('Invalid extraction confidence.');
 // Plain text is decoded from original bytes, not from the client-supplied extraction.
 const text=kind==='text'?new TextDecoder('utf-8',{fatal:true}).decode(bytes):input.text;
 const {fields,warnings}=extractFinancialFields(text);
 if(input.method==='ocr'&&(input.confidence??0)<70)warnings.push('Low OCR confidence. Do not act on these values without manual verification.');
 return {name,mime,size:bytes.length,kind,method:input.method as Attachment['method'],pages:input.pages,confidence:input.confidence??null,fields,warnings,status:'unverified'};
}
