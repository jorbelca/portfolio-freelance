import assert from 'node:assert/strict';

export async function finishBrowserTask(engine,runId,step,options={}) {
 const task=await engine.claimBrowserTask(runId);
 assert.equal(task.step_id,step.step_id);assert.equal(task.kind,step.kind);
 if(task.kind==='discover') {
  const candidates=typeof options.candidates==='function'?options.candidates(task):options.candidates || [];
  return engine.submitBrowserDiscovery(runId,task.step_id,{page_urls:[task.url],truncated:false,candidates});
 }
 if(task.kind==='read') {
  const result=options.read?await options.read(task):{};
  const job=result.complete===false?null:{'@type':'JobPosting',title:task.candidate.title,hiringOrganization:{name:task.candidate.company},datePosted:result.datePosted || new Date().toISOString().slice(0,10),jobLocation:{address:{addressCountry:'ES'}},description:'Desarrollo de software. '.repeat(30),url:task.candidate.url};
  const html=job?`<script type="application/ld+json">${JSON.stringify(job)}</script>`:'<main>Ficha incompleta</main>';
  const applicationUrl=result.application_url===null?null:result.application_url || `https://1.1.1.1/apply/${encodeURIComponent(task.candidate.title.toLowerCase().replaceAll(' ','-'))}`;
  return engine.submitBrowserRead(runId,task.step_id,{page_url:result.page_url || task.url,html,visible_text:result.visible_text || (job?job.description:'Ficha incompleta'),application_url:applicationUrl});
 }
 const result=options.application?await options.application(task):{};
 const status=result.status || 'accessible';
 return engine.submitBrowserApplication(runId,task.step_id,{page_url:result.page_url || task.url,status,form_found:result.form_found ?? status==='accessible',required_fields:result.required_fields || (status==='accessible'?['Correo electrónico','CV']:[]),evidence:result.evidence || (status==='accessible'?'Formulario público visible; no se rellenó.':`Estado observado: ${status}.`),identity_evidence:result.identity_evidence,reason:result.reason});
}

export async function nextSearchTask(engine,runId,options={}) {
 let step=await engine.searchNext(runId);
 while(step.status==='awaiting_browser') {
  await finishBrowserTask(engine,runId,step,options);
  step=await engine.searchNext(runId);
 }
 return step;
}
