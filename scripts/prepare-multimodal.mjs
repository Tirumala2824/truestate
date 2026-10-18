import {createRequire} from 'node:module';
import {cpSync,mkdirSync,readdirSync,existsSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
const require=createRequire(import.meta.url);
const tesseract=dirname(require.resolve('tesseract.js/package.json'));
const core=dirname(createRequire(resolve(tesseract,'package.json')).resolve('tesseract.js-core/package.json'));
const pdf=dirname(require.resolve('pdfjs-dist/package.json'));
const eng=dirname(require.resolve('@tesseract.js-data/eng/package.json'));
const dest=resolve('public/vendor');mkdirSync(dest+'/ocr',{recursive:true});mkdirSync(dest+'/pdf',{recursive:true});
cpSync(tesseract+'/dist/worker.min.js',dest+'/ocr/worker.min.js');
for(const name of readdirSync(core))if(/(?:^tesseract-core-lstm|^tesseract-core-(?:simd|relaxedsimd)-lstm)\.wasm(?:\.js)?$/.test(name))cpSync(core+'/'+name,dest+'/ocr/'+name);
cpSync(eng+'/4.0.0/eng.traineddata.gz',dest+'/ocr/eng.traineddata.gz');
cpSync(pdf+'/build/pdf.worker.min.mjs',dest+'/pdf/pdf.worker.min.mjs');
cpSync(pdf+'/standard_fonts',dest+'/pdf/standard_fonts',{recursive:true});
cpSync(pdf+'/wasm',dest+'/pdf/wasm',{recursive:true});
cpSync(pdf+'/cmaps',dest+'/pdf/cmaps',{recursive:true});
for(const [from,to] of [[tesseract+'/LICENSE.md',dest+'/ocr/LICENSE-tesseract.txt'],[pdf+'/LICENSE',dest+'/pdf/LICENSE.txt']])cpSync(from,to);
console.log('Prepared self-hosted OCR and PDF assets.');

mkdirSync('frontend/public',{recursive:true});
cpSync('public/vendor','frontend/public/vendor',{recursive:true});
cpSync('public/samples','frontend/public/samples',{recursive:true});

if(existsSync('public/downloads'))cpSync('public/downloads','frontend/public/downloads',{recursive:true});
