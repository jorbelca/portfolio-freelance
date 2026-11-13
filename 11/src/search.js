import {writeSearchReport,candidateTotals} from './search-report.js';
import {randomUUID,createHash} from 'node:crypto';
import {pool,transaction} from './db.js';
import {validId,validateSettings,offerInput,cleanUrl,validDate} from './domain.js';
import {getSearchConfig,searchConfigSchema} from './search-config.js';
import {discoverSource,readSourceDocument,readingRoutes} from './sources.js';
import {publicGet} from './public-http.js';
import {checkHistory,saveOffer,appendPublication,addPublication} from './store.js';
import {insertCandidate,previousFinalists,inheritCorrections,reusableExtraction,publicationKey} from './continuity.js';
import {samePublication} from './identity.js';
import {extractionTasks} from './tasks.js';
import {extractField} from './codex.js';
import {decisionRules,evaluateRule,evaluateFit,fitValues,classifyCandidate,rankCandidate} from './evaluation.js';

const conflict=message=>Object.assign(new Error(message),{status:409});
export const searchTaskKinds=['recover','discover','precheck','read',...extractionTasks.map(task=>`extract_${task.id}`),...decisionRules.map(rule=>`decide_${rule.id}`),'assess_fit','evaluate','batch','audit'];
async function enqueue(client,runId,kind,key,{candidateId=null,input={},priority=10}={}) {
 return (await client.query('INSERT INTO search_steps(id,run_id,candidate_id,kind,task_key,input,priority) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(run_id,task_key) DO UPDATE SET task_key=excluded.task_key RETURNING id',[randomUUID(),runId,candidateId,kind,key,input,priority])).rows[0].id;
}
export async function startSearchRun(input,existingClient) {
 validId(input.id);
 const create=async client=>{
  const control=(await client.query('SELECT * FROM workflow_control WHERE id=1 FOR UPDATE')).rows[0];
  const previous=(await client.query('SELECT id,module,status FROM workflow_runs WHERE id=$1',[input.id])).rows[0];
  if (previous) {
   if (previous.module!=='search') throw conflict('El ID pertenece a otro módulo.');
   return {...previous,existing:true};
  }
  if (!control.enabled) throw conflict('Las nuevas ejecuciones están pausadas.');
  if ((await client.query("SELECT 1 FROM workflow_runs WHERE status IN ('queued','running','unknown')")).rowCount) throw conflict('Hay una ejecución activa o incierta.');
  await client.query('SELECT id FROM search_settings WHERE id=1 FOR SHARE');
  const settings=(await client.query('SELECT * FROM settings_summary WHERE id=1')).rows[0];
  validateSettings(settings.value);
  if (!settings.value.history_ready) throw conflict('Incorpora y confirma el historial antes de buscar.');
  await client.query('SELECT id FROM search_configuration WHERE id=1 FOR SHARE');
  const config=await getSearchConfig(client);searchConfigSchema.parse(config.value);
  const snapshot={...settings.value,search_config:config,analysis_contract:createHash('sha256').update(JSON.stringify(extractionTasks)).digest('hex')};
  await client.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text,started_at) VALUES($1,'search','running',$2,$3,'Búsqueda automática',now())",[input.id,settings.revision,snapshot]);
  await client.query('INSERT INTO search_run_state(run_id) VALUES($1)',[input.id]);
  if(config.value.recover_previous) await enqueue(client,input.id,'recover','recover',{priority:-10});
  for (const source of config.value.sources.filter(source=>source.enabled)) await enqueue(client,input.id,'discover',`discover:${source.source}`,{input:{source:source.source,max_pages:source.max_pages},priority:0});
  return {id:input.id,status:'running'};
 };
 return existingClient?create(existingClient):transaction(create);
}
export async function searchNext(id) {
 validId(id);
 return transaction(async client=>{
  const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[id])).rows[0];
  if (!run || run.module!=='search') throw Object.assign(new Error('Búsqueda no encontrada'),{status:404});
  const state=(await client.query('SELECT * FROM search_run_state WHERE run_id=$1',[id])).rows[0];
  if (run.status!=='running' || state.control!=='active') return {run_id:id,continue:false,status:state.control==='active'?run.status:state.control};
  if ((await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status IN ('running','unknown')",[id])).rowCount) throw conflict('Hay una tarea en curso o incierta.');
  const counts=await countQuotas(client,id,run.settings_snapshot);
  const openings=Number((await client.query('SELECT count(*) FROM search_documents WHERE run_id=$1',[id])).rows[0].count);
  const limited=counts.fulfilled || openings>=run.settings_snapshot.max_openings;
  const preferred=counts.deficit_spain>=counts.deficit_europe?'spain':'europe';
  let step=(await client.query(`SELECT s.id,s.kind FROM search_steps s LEFT JOIN search_candidates c ON c.id=s.candidate_id WHERE s.run_id=$1 AND s.status='pending' AND ($3::boolean=false OR s.kind NOT IN ('precheck','read') OR ($4::boolean=false AND s.kind='read' AND s.input->>'route'='1'))
   ORDER BY s.priority,CASE WHEN $2='spain' AND lower(coalesce(c.hint->>'location','')) ~ '(spain|españa|alicante|madrid|barcelona)' THEN 0 WHEN $2='europe' AND lower(coalesce(c.hint->>'location','')) !~ '(spain|españa)' THEN 0 ELSE 1 END,coalesce((c.hint->>'discovery_order')::integer,0),s.created_at,s.id LIMIT 1`,[id,preferred,limited,counts.fulfilled])).rows[0];
  if (!step) {
   const completed=Number((await client.query("SELECT count(*) FROM search_steps WHERE run_id=$1 AND status='succeeded'",[id])).rows[0].count);
   const taskId=await enqueue(client,id,'audit',`audit:${completed}`,{priority:1});
   step={id:taskId,kind:'audit'};
  }
  await client.query('UPDATE search_run_state SET selected_step=$2 WHERE run_id=$1',[id,step.id]);
  return {run_id:id,continue:true,step_id:step.id,kind:step.kind};
 });
}
export async function runSearchStep(runId,stepId,kind,executionId,deps={}) {
 validId(runId);validId(stepId);
 if (!searchTaskKinds.includes(kind) || typeof executionId!=='string' || !/^\d{1,30}$/.test(executionId)) throw new Error('Tarea o ejecución n8n inválida');
 const claim=await transaction(async client=>{
  const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[runId])).rows[0];
  if (!run || run.module!=='search') throw new Error('Búsqueda no encontrada');
  const step=(await client.query('SELECT * FROM search_steps WHERE id=$1 AND run_id=$2',[stepId,runId])).rows[0];
  if (!step || step.kind!==kind) throw new Error('La tarea no corresponde a este nodo');
  if (['succeeded','failed'].includes(step.status)) return {cached:step};
  const state=(await client.query('SELECT * FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
  if (run.status!=='running' || state.control!=='active') return {stopped:true};
  if (step.status!=='pending' || (await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status IN ('running','unknown')",[runId])).rowCount) throw conflict('Tarea en curso o incierta.');
  if (state.selected_step!==stepId) throw conflict('Tarea fuera de orden.');
  await client.query("UPDATE search_steps SET status='running',started_at=now() WHERE id=$1",[stepId]);
  await client.query('INSERT INTO search_step_attempts(step_id,execution_id) VALUES($1,$2)',[stepId,executionId]);
  await client.query('UPDATE workflow_runs SET n8n_execution_id=$2 WHERE id=$1',[runId,executionId]);
  return {run,step};
 });
 if (claim.cached || claim.stopped) return {run_id:runId,status:claim.cached?.status || 'paused'};
 const {run,step}=claim;
 try {
  const result=await executeStep(run,step,deps);
  await pool.query("UPDATE search_step_attempts SET status='succeeded',result=$2,finished_at=now() WHERE step_id=$1 AND status='running'",[stepId,result || {}]);
  await pool.query("UPDATE search_steps SET status='succeeded',result=$2,error=NULL,finished_at=now() WHERE id=$1 AND status='running'",[stepId,result || {}]);
  const state=(await pool.query('SELECT control FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
  if(state.control==='cancelled') await auditSearch(runId);
  return {run_id:runId,status:'succeeded'};
 } catch(error) {
  const message=String(error.message || 'Error de tarea').slice(0,2000);
  const retrying=await transaction(async client=>{
   await client.query('SELECT id FROM workflow_runs WHERE id=$1 FOR UPDATE',[runId]);
   const state=(await client.query('SELECT control FROM search_run_state WHERE run_id=$1 FOR UPDATE',[runId])).rows[0];
   await client.query("UPDATE search_step_attempts SET status='failed',error=$2,finished_at=now() WHERE step_id=$1 AND status='running'",[stepId,message]);
   const attempts=Number((await client.query('SELECT count(*) AS n FROM search_step_attempts WHERE step_id=$1',[stepId])).rows[0].n);
   if(error.retryable===true && /^(extract_|decide_|assess_fit$)/.test(kind) && state.control==='active' && attempts<=(run.settings_snapshot.model_retries || 0)) {
    await client.query("UPDATE search_steps SET status='pending',error=$2,started_at=NULL,finished_at=NULL WHERE id=$1 AND status='running'",[stepId,`Respuesta inválida, reintento ${attempts}: ${message}`]);
    return true;
   }
   await client.query("UPDATE search_steps SET status='failed',error=$2,finished_at=now() WHERE id=$1 AND status='running'",[stepId,message]);
   await client.query("UPDATE search_run_state SET control=CASE WHEN control='cancelled' THEN control ELSE 'paused' END,revision=revision+1,updated_at=now() WHERE run_id=$1",[runId]);
   await client.query('UPDATE workflow_runs SET error=$2 WHERE id=$1',[runId,`Tarea ${kind}: ${message}. Corrige la causa y reintenta solo esta tarea.`]);
  });
  if(retrying) return {run_id:runId,status:'pending',retrying:true,error:message};
  if((await pool.query('SELECT control FROM search_run_state WHERE run_id=$1',[runId])).rows[0].control==='cancelled') await auditSearch(runId);
  return {run_id:runId,status:'failed',error:message};
 }
}
function termsMatch(candidate,queries) {
 const text=candidate.title.toLocaleLowerCase();
 return queries.some(query=>text.includes(query.term.toLocaleLowerCase()));
}
async function scheduleAfterRead(client,runId,candidateId,index=0) {
 const task=extractionTasks[index];
 if (task) return enqueue(client,runId,`extract_${task.id}`,`${candidateId}:extract:${task.id}`,{candidateId,priority:10});
 return enqueue(client,runId,`decide_${decisionRules[0].id}`,`${candidateId}:decide:${decisionRules[0].id}`,{candidateId,priority:10});
}
async function scheduleBatch(client,run) {
 const count=Number((await client.query(`SELECT count(*) FROM search_documents d JOIN search_candidates c ON c.id=d.candidate_id
  WHERE d.run_id=$1 AND (c.stage='evaluated' OR (d.status IN ('incomplete','error') AND c.stage IN ('lead','excluded','blocked')
   AND NOT EXISTS (SELECT 1 FROM search_steps s WHERE s.candidate_id=c.id AND s.kind='read' AND s.status='pending')))`,[run.id])).rows[0].count);
 if(count && count%run.settings_snapshot.batch_size===0) await enqueue(client,run.id,'batch',`batch:${count}`,{input:{completed_readings:count},priority:5});
}
async function candidateHistory(client,candidate) {
 const history=await checkHistory(candidate,client);
 for(const {url} of (await client.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1',[candidate.id])).rows) {
  const linked=await checkHistory({url},client);
  history.excluded ||= linked.excluded;history.needs_review ||= linked.needs_review;history.already_known ||= linked.already_known;
  history.matches=[...new Map([...history.matches,...linked.matches].map(row=>[row.id,row])).values()];
 }
 return history;
}
async function executeStep(run,step,deps) {
 const settings=run.settings_snapshot,profile=settings.search_config.value;
 if(step.kind==='recover') {
  return transaction(async client=>{
   const prior=await previousFinalists(client,run);let accepted=0;
   for(const row of prior.rows) {
    const id=await insertCandidate(client,run,{source:row.source,external_id:row.external_id,url:row.url,company:row.company,title:row.title,recovered:true},{prior:row,rank:-1});
    if(id) {accepted++;await enqueue(client,run.id,'precheck',`${id}:precheck`,{candidateId:id,priority:90});}
   }
   return {accepted,truncated:prior.truncated,limit:settings.max_openings};
  });
 }
 if (step.kind==='discover') {
  const feed=await (deps.discoverSource || discoverSource)(step.input.source,undefined,{maxPages:step.input.max_pages || 3});
  let accepted=0;
  await transaction(async client=>{
   for (const [rank,lead] of feed.leads.filter(lead=>termsMatch(lead,profile.queries)).entries()) {
    const id=await insertCandidate(client,run,lead,{rank});
    if(id) {accepted++;await enqueue(client,run.id,'precheck',`${id}:precheck`,{candidateId:id,priority:100});}
   }
  });
  return {source:step.input.source,pages:feed.pages || 1,truncated:feed.truncated || false,received:feed.leads.length,accepted,checked_at:feed.checked_at};
 }
 if (step.kind==='audit' || step.kind==='batch') return auditSearch(run.id,{final:step.kind==='audit'});
 const candidate=(await pool.query('SELECT * FROM search_candidates WHERE id=$1',[step.candidate_id])).rows[0];
 if (!candidate) throw new Error('Pista no encontrada');
 if (step.kind==='precheck') {
  const history=await candidateHistory(pool,candidate);
  const others=(await pool.query('SELECT id,url FROM search_candidates WHERE run_id=$1 AND id<>$2 AND (created_at,id)<($3,$2) AND stage NOT IN (\'excluded\',\'blocked\')',[run.id,candidate.id,candidate.created_at])).rows;
  const duplicate=others.some(row=>samePublication(row.url,candidate.url));
  const excluded=history.excluded || profile.excluded_employers.some(name=>name.toLowerCase()===candidate.company.toLowerCase());
  const review=(history.needs_review && candidate.identity_resolution!=='distinct') || duplicate;
  if(history.already_known && !history.excluded && history.matches.length===1) {candidate.opportunity_id=history.matches[0].id;await pool.query('UPDATE search_candidates SET opportunity_id=$2 WHERE id=$1',[candidate.id,candidate.opportunity_id]);}
  await transaction(async client=>{
   await client.query('UPDATE search_candidates SET history=$2,stage=$3,reason=$4 WHERE id=$1',[candidate.id,history,excluded?'excluded':review?'blocked':'lead',excluded?'Historial o empleador excluido':review?'Identidad conocida o posible duplicidad; requiere revisión':null]);
   if (excluded) {
    const evaluation=classifyCandidate({company:candidate.company,job:null,complete:false,history,settings,profile,cutoff:run.created_at});
    await client.query('UPDATE search_candidates SET evaluation=$2 WHERE id=$1',[candidate.id,evaluation]);
   } else if (!review) await enqueue(client,run.id,'read',`${candidate.id}:read`,{candidateId:candidate.id,priority:50});
  });
  return {excluded,needs_review:review,history};
 }
 if (step.kind==='read') {
  // Revalida justo antes de reservar: una candidatura puede cambiar durante el lote.
  const history=await candidateHistory(pool,candidate);
  if (history.excluded || (history.already_known && !candidate.opportunity_id) || (history.needs_review && candidate.identity_resolution!=='distinct')) {
   const evaluation=classifyCandidate({company:candidate.company,job:null,complete:false,history,settings,profile,cutoff:run.created_at});
   await transaction(async client=>{
    await client.query("UPDATE search_candidates SET stage=$2,history=$3,evaluation=$4,reason='Historial actualizado antes de abrir' WHERE id=$1",[candidate.id,history.excluded?'excluded':'blocked',history,evaluation]);
    await scheduleBatch(client,run);
   });
   return {skipped:true,history};
  }
  const routes=readingRoutes(candidate,{alternatives:settings.public_alternatives===true}),routeIndex=step.input.route ?? 0,route=routes[routeIndex];
  if(!Number.isSafeInteger(routeIndex) || !route) throw new Error('Ruta de lectura no admitida');
  const reserved=await transaction(async client=>{
   await client.query('SELECT id FROM workflow_runs WHERE id=$1 FOR UPDATE',[run.id]);
   const prior=(await client.query('SELECT status FROM search_documents WHERE candidate_id=$1',[candidate.id])).rows[0];
   if(routeIndex===0 && prior) throw conflict('Lectura reservada previamente; comprobar documento antes de repetir.');
   if(routeIndex>0 && (!prior || !['incomplete','error'].includes(prior.status) || !(await client.query("SELECT 1 FROM search_document_reads WHERE candidate_id=$1 AND route=0 AND status IN ('incomplete','error')",[candidate.id])).rowCount)) throw conflict('La alternativa exige una primera lectura terminada e incompleta.');
   const openings=Number((await client.query('SELECT count(*) FROM search_documents WHERE run_id=$1',[run.id])).rows[0].count);
   const counts=await countQuotas(client,run.id,settings);
   if((!prior && openings>=settings.max_openings) || counts.fulfilled) {
    await client.query("UPDATE search_candidates SET stage='blocked',reason=$2 WHERE id=$1",[candidate.id,counts.fulfilled?'Cupos cubiertos':'Límite de aperturas alcanzado']);return false;
   }
   if(!prior) await client.query("INSERT INTO search_documents(candidate_id,run_id,url,status) VALUES($1,$2,$3,'reserved')",[candidate.id,run.id,route.url]);
   await client.query("INSERT INTO search_document_reads(candidate_id,route,request_url,format,status) VALUES($1,$2,$3,$4,'reserved')",[candidate.id,routeIndex,route.url,route.format]);
   await client.query("UPDATE search_candidates SET stage='reading' WHERE id=$1",[candidate.id]);return true;
  });
  if (!reserved) return {skipped:true};
  let response,document;
  try {
   response=await (deps.publicGet || publicGet)(route.url);
   document=response.status===200?readSourceDocument(candidate,response,route):{complete:false,reason:`HTTP ${response.status}: acceso no verificado`};
  } catch(error) {
   document={complete:false,reason:error.message};
  }
  if(document.complete && document.text.length>100000) document={complete:false,reason:'Ficha superior al límite de análisis; conservar como pista sin truncar evidencia.'};
  await transaction(async client=>{
   if (document.complete) {
    const company=String(document.job.hiringOrganization.name).slice(0,500),title=document.job.title.slice(0,500);
    await client.query('UPDATE search_candidates SET company=$2,title=$3 WHERE id=$1',[candidate.id,company,title]);
    for(const link of [response?.url,document.job.url].filter(value=>typeof value==='string')) {
     try {const clean=cleanUrl(link);await client.query('INSERT INTO search_candidate_links(candidate_id,url,publication_key) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',[candidate.id,clean,publicationKey(clean)]);} catch {}
    }
   }
   await client.query('UPDATE search_document_reads SET status=$3,http_status=$4,response_url=$5,reason=$6,checked_at=$7 WHERE candidate_id=$1 AND route=$2',[candidate.id,routeIndex,document.complete?'complete':response?'incomplete':'error',response?.status ?? null,response?.url || route.url,document.reason || null,response?.checked_at || new Date().toISOString()]);
   await client.query('UPDATE search_documents SET status=$2,http_status=$3,text=$4,job=$5,reason=$6,url=$7,checked_at=$8,source_payload=$9 WHERE candidate_id=$1',[candidate.id,document.complete?'complete':response?'incomplete':'error',response?.status ?? null,document.text?.slice(0,100000) || null,document.job || null,document.reason || null,response?.url || route.url,response?.checked_at || new Date().toISOString(),document.source_payload || null]);
   await client.query('UPDATE search_candidates SET stage=$2,reason=$3 WHERE id=$1',[candidate.id,document.complete?'extracting':'lead',document.reason || null]);
   if(!document.complete && routes[routeIndex+1]) await enqueue(client,run.id,'read',`${candidate.id}:read:${routeIndex+1}`,{candidateId:candidate.id,input:{route:routeIndex+1},priority:10});
   else if(!document.complete) await scheduleBatch(client,run);
   if (document.complete) {
    await inheritCorrections(client,run,candidate,document);
    const updated=(await client.query('SELECT * FROM search_candidates WHERE id=$1',[candidate.id])).rows[0];
    const initial=await candidateEvaluation(client,run,updated,{...document,status:'complete'});
    if(initial.evaluation.classification==='C') await enqueue(client,run.id,'evaluate',`${candidate.id}:evaluate`,{candidateId:candidate.id,priority:10});
    else await scheduleAfterRead(client,run.id,candidate.id);
   }
  });
  return {complete:document.complete,route:routeIndex,request_url:route.url,alternative_pending:!document.complete && Boolean(routes[routeIndex+1]),reason:document.reason || null,http_status:response?.status || null};
 }
 const document=(await pool.query('SELECT * FROM search_documents WHERE candidate_id=$1',[candidate.id])).rows[0];
 if (!document || document.status!=='complete') throw new Error('No hay ficha completa para evaluar');
 if (step.kind.startsWith('extract_')) {
  const taskId=step.kind.slice(8),index=extractionTasks.findIndex(task=>task.id===taskId);
  const reused=await reusableExtraction(pool,run,candidate,step.kind,document.text);
  const result=reused?.result || await (deps.extractField || extractField)(taskId,document.text,settings);
  await transaction(async client=>{
   if(reused) await client.query("UPDATE search_steps SET input=input||jsonb_build_object('reused_from_step',$2::text,'prior_candidate_id',$3::text) WHERE id=$1",[step.id,reused.id,candidate.prior_candidate_id]);
   await scheduleAfterRead(client,run.id,candidate.id,index+1);
  });
  return result;
 }
 if (step.kind.startsWith('decide_')) {
  const ruleId=step.kind.slice(7),index=decisionRules.findIndex(rule=>rule.id===ruleId);
  const result=await (deps.evaluateRule || evaluateRule)(ruleId,document.text,profile,settings);
  await transaction(async client=>{
   const next=decisionRules[index+1];
   if (result.value==='incumple' || !next) {
    const kind=result.value!=='incumple' && profile.fit_instruction?'assess_fit':'evaluate';
    await enqueue(client,run.id,kind,`${candidate.id}:${kind}`,{candidateId:candidate.id,priority:10});
   }
   else await enqueue(client,run.id,`decide_${next.id}`,`${candidate.id}:decide:${next.id}`,{candidateId:candidate.id,priority:10});
  });
  return result;
 }
 if(step.kind==='assess_fit') {
  const result=await (deps.evaluateFit || evaluateFit)(document.text,profile,settings);
  await transaction(client=>enqueue(client,run.id,'evaluate',`${candidate.id}:evaluate`,{candidateId:candidate.id,priority:10}));
  return result;
 }
 if (step.kind==='evaluate') return evaluateCandidate(run,candidate,document);
 throw new Error('Operación no implementada');
}
async function candidateEvaluation(client,run,candidate,document) {
 const rows=(await client.query("SELECT kind,result FROM search_steps WHERE candidate_id=$1 AND kind LIKE 'decide_%' AND status='succeeded'",[candidate.id])).rows;
 const decisions=Object.fromEntries(rows.map(row=>[row.kind.slice(7),row.result]));
 let fitResult=(await client.query("SELECT result FROM search_steps WHERE candidate_id=$1 AND kind='assess_fit' AND status='succeeded'",[candidate.id])).rows[0]?.result;
 const overrides=(await client.query('SELECT * FROM search_candidate_overrides WHERE candidate_id=$1',[candidate.id])).rows;
 const job=structuredClone(document?.job || {});
 let publicationSource=null;
 if(candidate.prior_candidate_id) {
  const prior=(await client.query('SELECT id,evaluation FROM search_candidates WHERE id=$1',[candidate.prior_candidate_id])).rows[0];
  const earlier=prior?.evaluation?.publication?.date;
  if(earlier && (typeof job.datePosted!=='string' || earlier<job.datePosted.slice(0,10))) {job.datePosted=earlier;publicationSource={prior_candidate_id:prior.id,date:earlier};}
 }
 for(const override of overrides) {
  if(override.field.startsWith('decision:')) decisions[override.field.slice(9)]=override.value;
  else if(override.field==='country') job.jobLocation={address:{addressCountry:override.value}};
  else if(override.field==='publication') job.datePosted=override.value;
  else if(override.field==='fit') fitResult=override.value;
 }
 const history=await candidateHistory(client,candidate);
 const possible=(await client.query("SELECT id FROM search_candidates WHERE run_id=$1 AND id<>$2 AND lower(company)=lower($3) AND lower(title)=lower($4) AND stage NOT IN ('excluded','blocked')",[run.id,candidate.id,candidate.company,candidate.title])).rows;
 history.needs_review ||= possible.length>0;
 if(candidate.identity_resolution==='distinct' && !history.already_known && !history.excluded) history.needs_review=false;
 if (candidate.opportunity_id) {history.matches=history.matches.filter(row=>row.id!==candidate.opportunity_id);history.needs_review=(candidate.identity_resolution!=='distinct' && possible.length>0) || (history.matches.length>0 && !history.excluded);}
 const evaluation=classifyCandidate({company:candidate.company,job,complete:document?.status==='complete',decisions,fitResult,history,identity_resolved:!history.needs_review,settings:run.settings_snapshot,profile:run.settings_snapshot.search_config.value,cutoff:run.created_at});
 if(candidate.identity_resolution==='duplicate') {evaluation.classification='C';evaluation.computable=false;evaluation.exclusions=[{rule:'duplicate',evidence:`Mismo proceso que ${candidate.duplicate_candidate_id}; identidad confirmada por el usuario.`}];evaluation.pending=[];}
 const extracted=(await client.query("SELECT kind,result FROM search_steps WHERE candidate_id=$1 AND kind LIKE 'extract_%' AND status='succeeded'",[candidate.id])).rows;
 evaluation.publication_source=publicationSource;
 evaluation.manual_corrections=overrides.map(({field,evidence,reason})=>({field,evidence,reason}));
 const countryCorrection=overrides.find(row=>row.field==='country');if(countryCorrection) evaluation.country_evidence=countryCorrection.evidence;
 evaluation.sort_key=rankCandidate(evaluation,Object.fromEntries(extracted.map(row=>[row.kind.slice(8),row.result])),run.settings_snapshot.search_config.value);
 return {history,evaluation};
}
async function evaluateCandidate(run,candidate,document) {
 const {history,evaluation}=await candidateEvaluation(pool,run,candidate,document);
 await transaction(async client=>{
  await client.query("UPDATE search_candidates SET history=$2,evaluation=$3,stage='evaluated' WHERE id=$1",[candidate.id,history,evaluation]);
  await scheduleBatch(client,run);
 });
 return evaluation;
}
async function countQuotas(client,runId,settings) {
 const counts={spain:0,europe:0};
 for (const row of (await client.query("SELECT evaluation->>'zone' AS zone,count(*)::integer AS count FROM search_candidates WHERE run_id=$1 AND (evaluation->>'computable')::boolean GROUP BY evaluation->>'zone'",[runId])).rows) if (row.zone in counts) counts[row.zone]=row.count;
 return {...counts,deficit_spain:Math.max(0,settings.quota_spain-counts.spain),deficit_europe:Math.max(0,settings.quota_europe-counts.europe),fulfilled:counts.spain>=settings.quota_spain && counts.europe>=settings.quota_europe};
}
export async function auditSearch(runId,{final=true,refresh=false}={}) {
 const result=await transaction(async client=>{
  const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[runId])).rows[0];
  // Bloquea correcciones concurrentes durante el cruce final y el cómputo.
  await client.query('LOCK TABLE opportunities,applications,publications IN SHARE MODE');
  const candidates=(await client.query("SELECT * FROM search_candidates WHERE run_id=$1 ORDER BY created_at,id",[runId])).rows;
  for (const candidate of candidates.filter(candidate=>candidate.evaluation || candidate.stage==='evaluated')) {
   const document=(await client.query('SELECT * FROM search_documents WHERE candidate_id=$1',[candidate.id])).rows[0];
   const {history,evaluation}=await candidateEvaluation(client,run,candidate,document);
   await client.query('UPDATE search_candidates SET history=$2,evaluation=$3 WHERE id=$1',[candidate.id,history,evaluation]);
  }
  const settings=run.settings_snapshot,counts=await countQuotas(client,runId,settings);
  const openings=Number((await client.query('SELECT count(*) FROM search_documents WHERE run_id=$1',[runId])).rows[0].count);
  const control=(await client.query('SELECT * FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
  const truncated=(await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND kind='discover' AND (result->>'truncated')::boolean LIMIT 1",[runId])).rowCount;
  const reason=control.control==='cancelled'?'cancelada':counts.fulfilled?'cupos completos':openings>=settings.max_openings?'límite de aperturas':truncated?'límite de páginas de fuentes':'fuentes agotadas';
  const classes=(await client.query("SELECT coalesce(evaluation->>'classification','pista') AS class,count(*)::integer AS count FROM search_candidates WHERE run_id=$1 GROUP BY 1",[runId])).rows;
  const summary=candidateTotals((await client.query('SELECT evaluation FROM search_candidates WHERE run_id=$1',[runId])).rows);
  const reportRevision=control.report_revision+1;
  const historyRevision=(await client.query('SELECT revision FROM history_state WHERE id=1')).rows[0].revision;
  await client.query('UPDATE search_run_state SET report_dirty=false,history_revision=$2,report_revision=$3 WHERE run_id=$1',[runId,historyRevision,reportRevision]);
  const report={report_revision:reportRevision,history_revision:historyRevision,final:refresh?run.status==='succeeded':final,files:{report:`/api/search/runs/${runId}/report`,register:`/api/search/runs/${runId}/register`},cutoff:run.created_at,timezone:settings.timezone,openings,max_openings:settings.max_openings,quota_spain:settings.quota_spain,quota_europe:settings.quota_europe,...counts,classes,summary,reason};
  if(refresh || !final) {
   if(refresh && run.status==='succeeded') {report.reason=control.close_reason || reason;report.updated_at=new Date().toISOString();}
   await client.query('UPDATE workflow_runs SET result=$2 WHERE id=$1',[runId,report]);
   return report;
  }
  const remaining=(await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status='pending' AND kind IN ('read','precheck') LIMIT 1",[runId])).rowCount;
  if(control.control!=='cancelled' && !counts.fulfilled && openings<settings.max_openings && remaining) return {...report,continuing:true};
  await client.query('UPDATE search_run_state SET close_reason=$2,updated_at=now() WHERE run_id=$1',[runId,reason]);
  await client.query("UPDATE workflow_runs SET status='succeeded',result=$2,finished_at=coalesce(finished_at,now()),error=NULL WHERE id=$1",[runId,report]);
  return report;
 });
 const files=await writeSearchReport(runId,result);
 return {...result,files};
}
export async function controlSearch(runId,raw) {
 validId(runId);
 if (!['pause','resume','cancel','retry','skip'].includes(raw.action) || !Number.isSafeInteger(raw.revision)) throw new Error('Control de búsqueda inválido');
 const result=await transaction(async client=>{
  const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[runId])).rows[0];
  const state=(await client.query('SELECT * FROM search_run_state WHERE run_id=$1 FOR UPDATE',[runId])).rows[0];
  if (!run || !state || state.revision!==raw.revision || !['running','unknown',...(raw.action==='resume'?['succeeded']:[])].includes(run.status)) throw conflict('Estado cambiado o búsqueda terminada.');
  if (['retry','skip'].includes(raw.action)) {
   validId(raw.step_id);
   if (typeof raw.reason!=='string' || !raw.reason.trim() || raw.reason.length>2000) throw new Error('Documenta qué has comprobado antes de reintentar.');
   const step=(await client.query('SELECT * FROM search_steps WHERE id=$1 AND run_id=$2',[raw.step_id,runId])).rows[0];
   if (!step || !['failed','unknown'].includes(step.status) || (raw.action==='retry' && step.kind==='read')) throw conflict('Solo se reintentan tareas fallidas/inciertas sin repetir una apertura reservada.');
   if(raw.action==='retry') await client.query("UPDATE search_steps SET status='pending',error=$2,started_at=NULL,finished_at=NULL WHERE id=$1",[raw.step_id,`Revisión antes de reintentar: ${raw.reason}`]);
   else {
    await client.query("UPDATE search_steps SET status='succeeded',result=$2,error=NULL,finished_at=now() WHERE id=$1",[step.id,{skipped:true,reason:raw.reason,state:'desconocido',value:'desconocido',evidence:''}]);
    if(step.kind==='read') {
     await client.query("UPDATE search_document_reads SET status='unknown',reason=$2,checked_at=now() WHERE candidate_id=$1 AND status='reserved'",[step.candidate_id,raw.reason]);
     await client.query("UPDATE search_documents SET status='error',reason=$2,checked_at=now() WHERE candidate_id=$1 AND status='reserved'",[step.candidate_id,raw.reason]);
     await client.query("UPDATE search_candidates SET stage='lead',reason=$2 WHERE id=$1",[step.candidate_id,raw.reason]);
     await scheduleBatch(client,run);
    } else if(step.kind.startsWith('extract_')) {
     await scheduleAfterRead(client,runId,step.candidate_id,extractionTasks.findIndex(task=>task.id===step.kind.slice(8))+1);
    } else if(step.kind.startsWith('decide_')) {
     const next=decisionRules[decisionRules.findIndex(rule=>rule.id===step.kind.slice(7))+1];
     const kind=next?`decide_${next.id}`:run.settings_snapshot.search_config.value.fit_instruction?'assess_fit':'evaluate';
     await enqueue(client,runId,kind,`${step.candidate_id}:${next?`decide:${next.id}`:kind}`,{candidateId:step.candidate_id,priority:10});
    } else if(step.kind==='assess_fit') {
     await enqueue(client,runId,'evaluate',`${step.candidate_id}:evaluate`,{candidateId:step.candidate_id,priority:10});
    }
   }
  }
  if(raw.action==='resume' && run.status==='succeeded') {
   if((await client.query("SELECT 1 FROM workflow_runs WHERE id<>$1 AND status IN ('running','queued','unknown')",[runId])).rowCount) throw conflict('Ya hay otra ejecución activa.');
   if(!(await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status='pending'",[runId])).rowCount) throw conflict('No quedan tareas pendientes para continuar.');
   const openings=Number((await client.query('SELECT count(*) FROM search_documents WHERE run_id=$1',[runId])).rows[0].count);
   if(openings>=run.settings_snapshot.max_openings) throw conflict('Se alcanzó el máximo de aperturas del snapshot. Inicia otra búsqueda con nuevos parámetros.');
  }
  if (raw.action==='resume' && (await client.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status IN ('failed','unknown','running')",[runId])).rowCount) throw conflict('Resuelve o reintenta la tarea fallida/incierta antes de continuar.');
  const control=raw.action==='pause'?'paused':raw.action==='cancel'?'cancelled':'active';
  await client.query('UPDATE search_run_state SET control=$2,revision=revision+1,updated_at=now() WHERE run_id=$1',[runId,control]);
  if (control==='active') await client.query("UPDATE workflow_runs SET status='running',error=NULL,finished_at=NULL WHERE id=$1",[runId]);
  return {id:runId,control,revision:state.revision+1,dispatch:control==='active'};
 });
 if (raw.action==='cancel' && !(await pool.query("SELECT 1 FROM search_steps WHERE run_id=$1 AND status='running'",[runId])).rowCount) await auditSearch(runId);
 return result;
}
export async function ensureFreshSearch(runId) {
 const state=(await pool.query('SELECT s.*,h.revision AS current_history_revision FROM search_run_state s CROSS JOIN history_state h WHERE s.run_id=$1 AND h.id=1',[runId])).rows[0];
 if(state && (state.report_dirty || String(state.history_revision)!==String(state.current_history_revision))) await auditSearch(runId,{final:false,refresh:true});
 else if(state && state.report_revision>0 && (state.report_files_revision!==state.report_revision || state.report_files_error)) {
  const run=(await pool.query('SELECT result FROM workflow_runs WHERE id=$1',[runId])).rows[0];
  if(run?.result?.report_revision) await writeSearchReport(runId,run.result);
 }
}
export async function getSearchResults(runId,{limit=25,offset=0}={}) {
 validId(runId);await ensureFreshSearch(runId);
 const state=(await pool.query('SELECT * FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
 if (!state) throw Object.assign(new Error('Búsqueda no encontrada'),{status:404});
 const candidates=(await pool.query(`SELECT * FROM search_candidates WHERE run_id=$1 ORDER BY CASE evaluation->>'classification' WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2 ELSE 3 END,coalesce((evaluation->'sort_key'->>0)::integer,9),coalesce((evaluation->'sort_key'->>1)::integer,100),coalesce((evaluation->'sort_key'->>2)::integer,9),created_at,id LIMIT $2 OFFSET $3`,[runId,limit,offset])).rows;
 return {state,candidates};
}

export async function getSearchCandidate(id,{includeText=false}={}) {
 validId(id);
 const candidate=(await pool.query('SELECT * FROM search_candidates WHERE id=$1',[id])).rows[0];
 if(!candidate) throw Object.assign(new Error('Candidato no encontrado'),{status:404});
 candidate.events=(await pool.query('SELECT * FROM search_candidate_events WHERE candidate_id=$1 ORDER BY id',[id])).rows;
 candidate.version=Number(candidate.version);
 candidate.links=(await pool.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1 ORDER BY url',[id])).rows.map(row=>row.url);
 candidate.document=(await pool.query('SELECT * FROM search_documents WHERE candidate_id=$1',[id])).rows[0] || null;
 if(candidate.document && !includeText) delete candidate.document.text;
 candidate.reads=(await pool.query('SELECT * FROM search_document_reads WHERE candidate_id=$1 ORDER BY route',[id])).rows;
 candidate.overrides=(await pool.query('SELECT * FROM search_candidate_overrides WHERE candidate_id=$1',[id])).rows;
 candidate.attempts=(await pool.query('SELECT a.* FROM search_step_attempts a JOIN search_steps s ON s.id=a.step_id WHERE s.candidate_id=$1 ORDER BY a.id',[id])).rows;
 candidate.tasks=(await pool.query('SELECT id,kind,status,input,result,error FROM search_steps WHERE candidate_id=$1 ORDER BY created_at,id',[id])).rows;
 return candidate;
}
export async function trackSearchCandidate(id) {
 const candidate=await getSearchCandidate(id);
 if(candidate.opportunity_id) return {id:candidate.opportunity_id,existing:true};
 if(!['A','B'].includes(candidate.evaluation?.classification) || candidate.history?.needs_review) throw conflict('Solo se incorporan A/B con identidad resuelta.');
 const history=await candidateHistory(pool,candidate);
 if(history.excluded || history.needs_review) throw conflict('Historial cambiado; revisa el proceso antes de incorporarlo.');
 let saved;
 if(history.already_known && history.matches.length===1) saved={id:history.matches[0].id};
 else saved=await saveOffer(null,offerInput({company:candidate.company,title:candidate.title,url:candidate.url,availability:'desconocida',review_state:'nueva',application_state:'sin_candidatura',notes:`Investigada en búsqueda ${candidate.run_id}. Clase ${candidate.evaluation.classification}. Consulta sus citas y pendientes en resultados.`,reason:'Oferta real incorporada desde resultados de búsqueda.'}));
 for(const url of candidate.links.filter(url=>url!==candidate.url)) await appendPublication(saved.id,{url});
 await pool.query('UPDATE search_candidates SET opportunity_id=$2 WHERE id=$1',[id,saved.id]);
 return saved;
}

async function editableCandidate(client,id,version,reason) {
 validId(id);
 if(!Number.isSafeInteger(version) || typeof reason!=='string' || !reason.trim() || reason.length>2000) throw new Error('Indica versión actual y motivo concreto de la corrección.');
 const found=(await client.query('SELECT run_id FROM search_candidates WHERE id=$1',[id])).rows[0];
 if(!found) throw Object.assign(new Error('Pista no encontrada'),{status:404});
 const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[found.run_id])).rows[0];
 const candidate=(await client.query('SELECT * FROM search_candidates WHERE id=$1 FOR UPDATE',[id])).rows[0];
 if(candidate.version!==version) throw conflict('La pista cambió; vuelve a consultar su versión.');
 if((await client.query("SELECT 1 FROM search_steps WHERE candidate_id=$1 AND status='running'",[id])).rowCount) throw conflict('Hay una tarea en curso para esta pista; espera antes de corregirla.');
 return {run,candidate};
}
async function candidateEvent(client,id,kind,value,reason) {
 await client.query('INSERT INTO search_candidate_events(candidate_id,kind,value,reason) VALUES($1,$2,$3,$4)',[id,kind,value,reason.trim()]);
 await client.query('UPDATE search_candidates SET version=version+1 WHERE id=$1',[id]);
 await client.query('UPDATE search_run_state SET report_dirty=true WHERE run_id=(SELECT run_id FROM search_candidates WHERE id=$1)',[id]);
}
export async function resolveSearchIdentity(id,raw) {
 if(!['distinct','same_process','duplicate'].includes(raw?.resolution)) throw new Error('Resolución de identidad inválida');
 const result=await transaction(async client=>{
  const {run,candidate}=await editableCandidate(client,id,raw.version,raw.reason);
  let opportunityId=candidate.opportunity_id,targetId=null;
  if(raw.resolution==='distinct') {
   for(const link of (await client.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1',[id])).rows) if((await checkHistory({url:link.url},client)).already_known) throw conflict('Un ID/enlace ya identifica un proceso conocido; no puede declararse otro proceso.');
   opportunityId=null;
  }
  if(raw.resolution==='same_process') {
   opportunityId=validId(raw.target_offer_id);
   if(!(await client.query('SELECT id FROM opportunities WHERE id=$1 FOR UPDATE',[opportunityId])).rowCount) throw new Error('Proceso de destino no encontrado');
   for(const link of (await client.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1',[id])).rows) await addPublication(client,opportunityId,link.url);
  }
  if(raw.resolution==='duplicate') {
   targetId=validId(raw.duplicate_candidate_id);
   const target=(await client.query('SELECT * FROM search_candidates WHERE id=$1 AND run_id=$2 FOR UPDATE',[targetId,run.id])).rows[0];
   if(!target || target.id===id || target.identity_resolution==='duplicate') throw new Error('Elige otra pista principal de esta misma ejecución, sin cadena de duplicados.');
   await client.query('UPDATE search_candidates SET process_id=$2 WHERE COALESCE(process_id,id)=$1',[candidate.process_id || candidate.id,target.process_id || target.id]);
   if(opportunityId && target.opportunity_id && opportunityId!==target.opportunity_id) throw conflict('Las pistas pertenecen a procesos diferentes del seguimiento; revisa su fusión antes de unirlas.');
   await client.query('INSERT INTO search_candidate_links(candidate_id,url,publication_key) SELECT $2,url,publication_key FROM search_candidate_links WHERE candidate_id=$1 ON CONFLICT DO NOTHING',[id,targetId]);
   if(target.opportunity_id) for(const link of (await client.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1',[id])).rows) await addPublication(client,target.opportunity_id,link.url);
   await candidateEvent(client,targetId,'alias_merged',{duplicate_candidate_id:id},raw.reason);
  }
  await client.query('UPDATE search_candidates SET identity_resolution=$2,duplicate_candidate_id=$3,opportunity_id=$4,stage=$5,reason=$6 WHERE id=$1',[id,raw.resolution,targetId,opportunityId,raw.resolution==='duplicate'?'excluded':candidate.stage,raw.reason]);
  if(raw.resolution!=='duplicate' && candidate.stage==='blocked' && !(await client.query('SELECT 1 FROM search_documents WHERE candidate_id=$1',[id])).rowCount) {
   const history=await checkHistory({...candidate,opportunity_id:opportunityId},client);
   if(!history.excluded) {await client.query("UPDATE search_candidates SET stage='lead' WHERE id=$1",[id]);await enqueue(client,run.id,'read',`${id}:read`,{candidateId:id,priority:50});}
  }
  if(raw.resolution==='duplicate') {
   const evaluation={classification:'C',computable:false,zone:null,country:null,exclusions:[{rule:'duplicate',evidence:`Mismo proceso que ${targetId}; confirmado por usuario.`}],pending:[],fit:'desconocido'};
   await client.query('UPDATE search_candidates SET evaluation=$2 WHERE id=$1',[id,evaluation]);
  }
  await candidateEvent(client,id,'identity_resolved',{resolution:raw.resolution,target_offer_id:opportunityId,duplicate_candidate_id:targetId},raw.reason);
  return {id,run_id:run.id};
 });
 await ensureFreshSearch(result.run_id);return getSearchCandidate(id);
}
export async function correctSearchCandidate(id,raw) {
 const allowed=['country','publication','fit',...decisionRules.map(rule=>`decision:${rule.id}`)];
 if(!raw || !allowed.includes(raw.field) || typeof raw.evidence!=='string' || !raw.evidence.trim() || raw.evidence.length>10000) throw new Error('Campo o evidencia de corrección inválidos');
 const result=await transaction(async client=>{
  const {run}=await editableCandidate(client,id,raw.version,raw.reason);
  const document=(await client.query('SELECT * FROM search_documents WHERE candidate_id=$1',[id])).rows[0];
  if(document?.status!=='complete' || !document.text.includes(raw.evidence)) throw new Error('La evidencia debe ser una cita literal del documento conservado.');
  let value=raw.value;
  if(raw.field==='publication') {if(typeof value!=='string' || !validDate(value)) throw new Error('Fecha inválida');}
  else if(raw.field==='country') {if(typeof value!=='string' || !/^[A-Z]{2}$/.test(value)) throw new Error('Usa código ISO de país de dos letras');}
  else if(raw.field==='fit') {if(![...fitValues,'desconocido'].includes(value)) throw new Error('Encaje inválido');value={state:value==='desconocido'?'desconocido':'acreditado',value,evidence:value==='desconocido'?'':raw.evidence};}
  else {if(!['cumple','incumple','desconocido'].includes(value)) throw new Error('Veredicto inválido');value={state:value==='desconocido'?'desconocido':'acreditado',value,evidence:value==='desconocido'?'':raw.evidence};}
  await client.query('INSERT INTO search_candidate_overrides(candidate_id,field,value,evidence,reason) VALUES($1,$2,$3,$4,$5) ON CONFLICT(candidate_id,field) DO UPDATE SET value=excluded.value,evidence=excluded.evidence,reason=excluded.reason,created_at=now()',[id,raw.field,JSON.stringify(value),raw.evidence,raw.reason]);
  await candidateEvent(client,id,'correction',{field:raw.field,value,evidence:raw.evidence},raw.reason);
  return {run_id:run.id};
 });
 await ensureFreshSearch(result.run_id);return getSearchCandidate(id);
}
