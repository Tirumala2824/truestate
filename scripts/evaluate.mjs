import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fixtureFor,evaluate} from '../lib/truestate/engine.ts';
const frozen=readFileSync(new URL('../datasets/synthetic-v1.json',import.meta.url));
const dataset=JSON.parse(frozen);
for(let i=0;i<dataset.length;i++)if(JSON.stringify(dataset[i].fixture)!==JSON.stringify(fixtureFor(dataset[i].scenario,i)))throw new Error('Fixture generator differs from frozen v1 dataset');
const results={...evaluate(),datasetSHA256:createHash('sha256').update(frozen).digest('hex')};
writeFileSync(new URL('../docs/evaluation-latest.json',import.meta.url),JSON.stringify(results,null,2));
console.log(JSON.stringify(results,null,2));
