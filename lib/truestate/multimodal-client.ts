import {MAX_FILE_BYTES,MAX_TEXT_CHARS,validateFile,type ExtractionInput} from './evidence-input';
export type InputProgress={phase:string;progress:number};
const supported:Record<string,string>={pdf:'application/pdf',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',txt:'text/plain',csv:'text/csv'};
export function fileMime(file:File){return supported[file.name.split('.').at(-1)?.toLowerCase()||'']||file.type;}
export async function extractFile(file:File,onProgress:(p:InputProgress)=>void,signal?:AbortSignal):Promise<ExtractionInput>{
 const check=()=>{if(signal?.aborted)throw new DOMException('Cancelled','AbortError');};
 check();if(file.size>MAX_FILE_BYTES)throw new Error('Use files of 8 MB or smaller.');const bytes=new Uint8Array(await file.arrayBuffer()),mime=fileMime(file);validateFile(file.name,mime,bytes);
 if(mime==='text/plain'||mime==='text/csv'){onProgress({phase:'Reading financial text',progress:60});const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);if(text.length>MAX_TEXT_CHARS)throw new Error('Use a shorter document (up to 18,000 text characters).');check();return {text,method:'text',pages:1};}
 let worker:Awaited<ReturnType<typeof import('tesseract.js').createWorker>>|undefined;
 const abort=()=>{void worker?.terminate();};signal?.addEventListener('abort',abort);
 async function recognize(image:HTMLCanvasElement|Blob){check();if(!worker){const {createWorker}=await import('tesseract.js');worker=await createWorker('eng',1,{workerPath:'/vendor/ocr/worker.min.js',corePath:'/vendor/ocr',langPath:'/vendor/ocr',workerBlobURL:false,logger:m=>onProgress({phase:m.status==='recognizing text'?'Reading financial text with OCR':m.status,progress:Math.round((m.progress||0)*75)})});check();}const result=await worker.recognize(image);check();return result.data;}
 try{
 if(mime.startsWith('image/')){onProgress({phase:'Opening evidence image',progress:5});const bitmap=await createImageBitmap(file);const pixels=bitmap.width*bitmap.height;bitmap.close();if(pixels>16000000)throw new Error('Use an image smaller than 16 megapixels.');const result=await recognize(file);if(result.text.length>MAX_TEXT_CHARS)throw new Error('Too much text in this image.');return {text:result.text,method:'ocr',pages:1,confidence:result.confidence};}
 onProgress({phase:'Opening PDF',progress:5});const pdfjs=await import('pdfjs-dist');pdfjs.GlobalWorkerOptions.workerSrc='/vendor/pdf/pdf.worker.min.mjs';
 const task=pdfjs.getDocument({data:bytes,stopAtErrors:true,cMapUrl:'/vendor/pdf/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/pdf/standard_fonts/',wasmUrl:'/vendor/pdf/wasm/'});
 const cancelPdf=()=>{void task.destroy();};signal?.addEventListener('abort',cancelPdf);let doc;
 try{doc=await task.promise;check();if(doc.numPages>10)throw new Error('Use a PDF with no more than 10 pages.');let text='',ocrCount=0,confidence=0;
 for(let pageNumber=1;pageNumber<=doc.numPages;pageNumber++){check();onProgress({phase:`Reading PDF page ${pageNumber} of ${doc.numPages}`,progress:Math.round(pageNumber/doc.numPages*70)});const page=await doc.getPage(pageNumber),content=await page.getTextContent();let pageText=content.items.map(item=>'str' in item?item.str+(item.hasEOL?'\n':' '):'').join('');
 if(pageText.trim().length<30){const viewport=page.getViewport({scale:1.6});if(viewport.width*viewport.height>12000000)throw new Error('This PDF page is too large to scan.');const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Canvas is unavailable in this browser.');await page.render({canvas,canvasContext:ctx,viewport}).promise;const result=await recognize(canvas);pageText=result.text;confidence+=result.confidence;ocrCount++;canvas.width=canvas.height=0;}
 text+=pageText+'\n';page.cleanup();if(text.length>MAX_TEXT_CHARS)throw new Error('Use a shorter PDF (up to 18,000 extracted characters).');}
 return {text,method:ocrCount?'ocr':'pdf-text',pages:doc.numPages,confidence:ocrCount?confidence/ocrCount:null};
 }finally{signal?.removeEventListener('abort',cancelPdf);await task.destroy();}
 }finally{signal?.removeEventListener('abort',abort);await worker?.terminate();}
}
export function uploadEvidence(file:File,extraction:ExtractionInput,onProgress:(p:InputProgress)=>void,signal?:AbortSignal){return new Promise<import('./evidence-input').Attachment>((resolve,reject)=>{
 const request=new XMLHttpRequest();request.open('POST','/api/uploads');request.responseType='json';const abort=()=>request.abort();signal?.addEventListener('abort',abort);const finish=()=>signal?.removeEventListener('abort',abort);
 request.upload.onprogress=e=>{if(e.lengthComputable)onProgress({phase:'Saving evidence securely',progress:Math.round(e.loaded/e.total*100)});};
 request.onload=()=>{finish();const data=request.response;if(request.status>=200&&request.status<300&&data?.attachment)resolve(data.attachment);else reject(new Error(data?.error||data?.detail||'Evidence upload failed.'));};request.onerror=()=>{finish();reject(new Error('Upload connection failed. Please try again.'));};request.onabort=()=>{finish();reject(new DOMException('Cancelled','AbortError'));};
 const form=new FormData();form.append('file',new File([file],file.name,{type:fileMime(file)}));form.append('extraction',JSON.stringify(extraction));if(signal?.aborted){reject(new DOMException('Cancelled','AbortError'));return;}request.send(form);
 });}
