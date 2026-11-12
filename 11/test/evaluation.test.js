import test from 'node:test';
import assert from 'node:assert/strict';
import {decisionRules,evaluateRule,publicationAge,postingCountry,classifyCandidate} from '../src/evaluation.js';
const cutoff='2026-11-12T12:00:00Z';
const settings={max_age_days:45,timezone:'Europe/Madrid',history_ready:true};
const profile={excluded_employers:['CNAC','Hubmud']};
const job={datePosted:'2026-11-01',jobLocation:{address:{addressCountry:'ES'}}};
const decisions=Object.fromEntries(decisionRules.map(rule=>[rule.id,{state:'acreditado',value:'cumple',evidence:'Texto comprobado'}]));
const base={company:'Fixture aislada',job,complete:true,decisions,history:{excluded:false,needs_review:false},settings,profile,cutoff};
test('45 días inclusive y fechas imposibles, futuras y sin publicación',()=>{
 assert.equal(publicationAge('2026-09-28',cutoff,45).state,'valid');
 assert.equal(publicationAge('2026-09-27',cutoff,45).state,'expired');
 for (const date of ['2026-02-30','2026-11-13','ayer',undefined]) assert.equal(publicationAge(date,cutoff,45).state,'unknown');
 assert.equal(publicationAge('2026-11-11T00:00:00Z','2026-11-11T23:30:00Z',45).days,1);
});
test('país de puesto separado de elegibilidad, sin reparto conveniente',()=>{
 assert.equal(postingCountry(job).zone,'spain');
 assert.equal(postingCountry({jobLocation:{address:{addressCountry:'GB'}}}).zone,'europe');
 assert.equal(postingCountry({applicantLocationRequirements:{name:'Spain'}}),null);
 assert.equal(postingCountry({jobLocation:[job.jobLocation,{address:{addressCountry:'DE'}}]}),null);
});
test('A verificada; B con contrato pendiente computa; fecha o identidad pendiente no computan',()=>{
 assert.equal(classifyCandidate(base).classification,'A');
 assert.equal(classifyCandidate(base).computable,true);
 const pending=classifyCandidate({...base,decisions:{...decisions,contract:{state:'desconocido',value:'desconocido',evidence:''}}});
 assert.equal(pending.classification,'B');assert.equal(pending.computable,true);
 assert.equal(classifyCandidate({...base,job:{...job,datePosted:undefined}}).computable,false);
 assert.equal(classifyCandidate({...base,history:{needs_review:true}}).computable,false);
 assert.equal(classifyCandidate({...base,settings:{...settings,history_ready:false}}).computable,false);
 assert.equal(classifyCandidate({...base,complete:false}).classification,'pista');
});
test('rechazo anterior, cierre y requisito incumplido prevalecen sobre pendientes',()=>{
 for (const change of [{history:{excluded:true}},{company:'CNAC'},{job:{...job,datePosted:'2026-01-01'}},{job:{...job,validThrough:'2026-11-01'}},{decisions:{contract:{state:'acreditado',value:'incumple',evidence:'Temporal'}}}]) {
  const result=classifyCandidate({...base,...change});assert.equal(result.classification,'C');assert.equal(result.computable,false);
 }
});
test('una regla recibe solo su responsabilidad y rechaza decisiones inventadas',async()=>{
 assert.equal((await evaluateRule('video','Vídeo obligatorio',profile,'',async prompt=>{assert.match(prompt,/exclusivamente vídeo/);return {state:'acreditado',value:'incumple',evidence:'Vídeo obligatorio'};})).value,'incumple');
 await assert.rejects(()=>evaluateRule('contract','Texto',profile,'',async()=>({state:'acreditado',value:'cumple',evidence:'Indefinido'})));
 await assert.rejects(()=>evaluateRule('contract','Texto',profile,'',async()=>({state:'desconocido',value:'cumple',evidence:''})));
});
test('ordena por encaje, preferencia tecnológica y ubicación sin confundir subcadenas',async()=>{
 const {rankCandidate,compareCandidates}=await import('../src/evaluation.js');
 const profile={skills:[{name:'RAG',priority:1},{name:'React',priority:2},{name:'Java',priority:3}]};
 const evaluation={fit:'favorable',pending:[],zone:'spain',classification:'B'};
 assert.deepEqual(rankCandidate(evaluation,{technology:{state:'acreditado',value:'Storage y React'}},profile),[0,2,2]);
 assert.deepEqual(rankCandidate(evaluation,{technology:{state:'acreditado',value:'RAG'},work_mode:{state:'acreditado',value:'Remoto'}},profile),[0,1,0]);
 const a={id:'a',evaluation:{classification:'B',sort_key:[0,3,2]}},b={id:'b',evaluation:{classification:'B',sort_key:[1,1,0]}};
 assert.equal([b,a].sort(compareCandidates)[0].id,'a');
});
