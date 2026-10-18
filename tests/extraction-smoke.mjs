import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createRequire} from 'node:module';
import {createWorker} from 'tesseract.js';
import {extractFinancialFields} from '../lib/truestate/evidence-input.ts';
const require=createRequire(import.meta.url);
const pdfRequire=createRequire(require.resolve('pdfjs-dist/package.json'));
const canvas=pdfRequire('@napi-rs/canvas');Object.assign(globalThis,{DOMMatrix:canvas.DOMMatrix,ImageData:canvas.ImageData,Path2D:canvas.Path2D});
const {getDocument}=await import('pdfjs-dist/legacy/build/pdf.mjs');
const task=getDocument({data:new Uint8Array(readFileSync('public/samples/supplier-invoice.pdf')),useSystemFonts:true});
const doc=await task.promise;const page=await doc.getPage(1);const content=await page.getTextContent();const text=content.items.map(x=>x.str+(x.hasEOL?'\n':' ')).join('');assert.equal(extractFinancialFields(text).fields.account,'ACCOUNT_B');await task.destroy();
const worker=await createWorker('eng',1,{langPath:resolve('public/vendor/ocr'),cacheMethod:'none'});
try{const result=await worker.recognize('public/samples/supplier-invoice.png');const fields=extractFinancialFields(result.data.text).fields;assert.equal(fields.supplier,'Aster Components');assert.equal(fields.amount,'INR 840000');assert.equal(fields.account,'ACCOUNT_B');console.log('Actual PDF text extraction and image OCR passed; supplier, account, and amount recovered.');}finally{await worker.terminate();}
