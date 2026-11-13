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

test('usa el criterio configurado sin relajar citas y conserva reglas de snapshots antiguos',async()=>{
 const criteria=decisionRules.map(rule=>rule.id==='contract'?{...rule,instruction:'Admite contrato temporal explícito.',pending:'Confirmar duración acordada'}:rule);
 await evaluateRule('contract','Contrato temporal',{...profile,criteria},'',async prompt=>{
  assert.ok(prompt.startsWith('Admite contrato temporal explícito.'));
  assert.match(prompt,/cita literal continua/);
  return {state:'acreditado',value:'cumple',evidence:'Contrato temporal'};
 });
 const result=classifyCandidate({...base,profile:{...profile,criteria},decisions:{...decisions,contract:{state:'desconocido',value:'desconocido',evidence:''}}});
 assert.equal(result.pending.find(item=>item.rule==='contract').resolution,'Confirmar duración acordada');
 assert.equal(classifyCandidate(base).classification,'A');
});

test('encaje independiente: B débil computable, desconocido pendiente y C prevalece',()=>{
 const input={...base,profile:{...profile,fit_instruction:'Instrucción configurada'},decisions:{...decisions,contract:{state:'desconocido',value:'desconocido',evidence:''}},fitResult:{state:'acreditado',value:'débil',evidence:'Autonomía avanzada'}};
 const weak=classifyCandidate(input);assert.equal(weak.classification,'B');assert.equal(weak.computable,true);assert.equal(weak.fit,'débil');assert.equal(weak.fit_evidence,'Autonomía avanzada');assert.match(weak.fit_explanation,/no acredita/);
 const unknown=classifyCandidate({...input,fitResult:{state:'desconocido',value:'desconocido',evidence:''}});
 assert.equal(unknown.classification,'B');assert.equal(unknown.computable,false);assert.ok(unknown.pending.some(item=>item.rule==='fit'));
 assert.equal(classifyCandidate({...input,history:{excluded:true}}).classification,'C');
 const legacyCorrection=classifyCandidate({...input,profile});assert.equal(legacyCorrection.fit,'débil');
 assert.equal(classifyCandidate(base).fit,'favorable');
});
test('valoración de encaje singular con cita literal y sin decisiones A/B/C',async()=>{
 const {evaluateFit}=await import('../src/evaluation.js');
 const profile={fit_instruction:'Evalúa esta brecha concreta.',professional_years:null,internship_details:'Prácticas de duración desconocida',skills:[],qualifications:[],sources:['no incluir']};
 const text='Experiencia profesional de dos años.';
 const result=await evaluateFit(text,profile,'',async prompt=>{assert.ok(prompt.startsWith(profile.fit_instruction));assert.match(prompt,/value exactamente favorable/);assert.doesNotMatch(prompt,/no incluir/);return {state:'acreditado',value:'condicionado',evidence:text};});
 assert.equal(result.value,'condicionado');
 for(const invalid of [{state:'acreditado',value:'cumple',evidence:text},{state:'acreditado',value:'débil',evidence:'Inventado'},{state:'desconocido',value:'favorable',evidence:''}]) await assert.rejects(()=>evaluateFit(text,profile,'',async()=>invalid),error=>error.retryable===true);
 assert.equal((await evaluateFit(text,profile,'',async()=>({state:'desconocido',value:'desconocido',evidence:''}))).state,'desconocido');
});
