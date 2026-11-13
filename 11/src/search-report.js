import {mkdir,writeFile,rename,rm} from 'node:fs/promises';
import {validId} from './domain.js';
import {pool} from './db.js';
import {compareCandidates} from './evaluation.js';
import {randomUUID} from 'node:crypto';
const reportWrites=new Map();
const escape=value=>String(value ?? '').replace(/[\\`*_{}\[\]<>|]/g,'\\$&').replace(/[\r\n]+/g,' ');
export function candidateTotals(candidates) {
 const totals={classes:{A:0,B:0,C:0,pista:0},computable:0,b_computable:0,b_not_computable:0,fit:{favorable:0,condicionado:0,'débil':0,desconocido:0}};
 for(const {evaluation} of candidates) {
  const classification=evaluation?.classification || 'pista';
  totals.classes[classification]=(totals.classes[classification] || 0)+1;
  if(classification==='B') totals[evaluation.computable?'b_computable':'b_not_computable']++;
  if(['A','B'].includes(classification) && evaluation.computable) {
   totals.computable++;
   const fit=Object.hasOwn(totals.fit,evaluation.fit)?evaluation.fit:'desconocido';totals.fit[fit]++;
  }
 }
 return totals;
}
export function reportMarkdown(report,candidates) {
 const lines=[`# Búsqueda de empleo`, ``, `Fecha de corte: ${new Date(report.cutoff).toLocaleString('es-ES',{timeZone:report.timezone})} (${report.timezone}).`, `Fichas: ${report.openings}/${report.max_openings}. España: ${report.spain}/${report.quota_spain}. Resto de Europa: ${report.europe}/${report.quota_europe}.`, `Déficit: España ${report.deficit_spain}; Europa ${report.deficit_europe}.`, `Motivo de cierre: ${report.reason}. ${report.fulfilled?'Reparto verificado.':'Objetivo de cupos no cumplido.'}`,``];
 const totals=candidateTotals(candidates);
 lines.push(`Total computable: ${totals.computable}/${report.quota_spain+report.quota_europe}. Clases: A ${totals.classes.A}; B ${totals.classes.B}; C ${totals.classes.C}; pistas ${totals.classes.pista}.`, `B computables: ${totals.b_computable}; B no computables: ${totals.b_not_computable}.`, `Encaje entre finalistas computables: favorable ${totals.fit.favorable}; condicionado ${totals.fit.condicionado}; débil ${totals.fit['débil']}; desconocido ${totals.fit.desconocido}.`,``);
 if(totals.fit['débil']>totals.computable/2) lines.push('Predominan los encajes débiles entre las finalistas computables.',``);
 const countries={};for(const row of candidates) if(row.evaluation?.computable && row.evaluation.country) countries[row.evaluation.country]=(countries[row.evaluation.country] || 0)+1;
 lines.push(`Desglose computable por país: ${Object.entries(countries).map(([country,count])=>`${escape(country)}: ${count}`).join('; ') || 'ninguno'}.`,``);
 for(const [classification,title] of [['A','A · Recomendadas y verificadas'],['B','B · Pendientes'],['C','C · Excluidas'],['pista','Pistas sin ficha completa']]) {
  lines.push(`## ${title}`,``);
  const rows=candidates.filter(row=>(row.evaluation?.classification || 'pista')===classification);
  if(!rows.length) lines.push('Sin resultados.',``);
  if(classification==='C' && rows.length) {
   lines.push('| Puesto · empresa | Causa | Evidencia | Fuente |','| --- | --- | --- | --- |');
   for(const row of rows) lines.push(`| ${escape(row.title)} · ${escape(row.company)} | ${(row.evaluation.exclusions || []).map(item=>escape(item.rule)).join('; ')} | ${(row.evaluation.exclusions || []).map(item=>escape(item.evidence)).join('; ')} | [${escape(row.source)}](${row.url.replace(/\(/g,'%28').replace(/\)/g,'%29')}) |`);
   lines.push('');continue;
  }
  for(const row of rows) {
   lines.push(`### ${escape(row.title)} · ${escape(row.company)}`,``, `[Fuente: ${escape(row.source)}](${row.url.replace(/\(/g,'%28').replace(/\)/g,'%29')})`, `ID de proceso: ${row.process_id || row.id}. Observación: ${row.id}. Computable: ${row.evaluation?.computable?'sí':'no'}. País: ${escape(row.evaluation?.country || 'no acreditado')}. Encaje: ${escape(row.evaluation?.fit || 'sin evaluar')}.`,``);
   if(row.evaluation?.fit_explanation) lines.push(`Encaje: ${escape(row.evaluation.fit_explanation)}${row.evaluation.fit_evidence?' Evidencia: «'+escape(row.evaluation.fit_evidence)+'».':''}`,``);
   if(classification==='B') lines.push(row.evaluation.computable?'**B computable**: cuenta en el cupo; mantiene condiciones pendientes.':'**B no computable**: queda fuera del cupo hasta resolver sus pendientes.',``);
   if(row.prior_candidate_id) lines.push(`Continuidad: observación anterior ${row.prior_candidate_id}. Ficha actual releída y contada en esta ejecución.`,``);
   if(row.evaluation?.publication_source) lines.push(`Fecha original conservada: ${escape(row.evaluation.publication_source.date)} de ${row.evaluation.publication_source.prior_candidate_id}.`,``);
   if(row.checked_at) lines.push(`Comprobada: ${escape(row.checked_at)}.`,``);
   if(row.reason) lines.push(escape(row.reason),``);
   for(const item of row.evaluation?.exclusions || []) lines.push(`- Exclusión ${escape(item.rule)}: ${escape(item.evidence)}`);
   for(const item of row.evaluation?.pending || []) lines.push(`- Pendiente (${escape(item.owner)}): ${escape(item.resolution)}`);
   for(const correction of row.overrides || []) lines.push(`- Corrección manual ${escape(correction.field)}: ${escape(typeof correction.value==='object'?correction.value.value:correction.value)}. Evidencia: «${escape(correction.evidence)}». Motivo: ${escape(correction.reason)}.`);
   for(const task of row.evidence || []) {
    if(task.input?.reused_from_step) lines.push(`- Extracción reutilizada: ${escape(task.kind)} desde la observación ${escape(task.input.prior_candidate_id)}.`);
    if(task.result?.state==='acreditado') lines.push(`- ${escape(task.kind)}: ${escape(task.result.value)}. Evidencia: «${escape(task.result.evidence)}».`);
   }
   lines.push('');
  }
 }
 lines.push('## Límites', '', 'No se han enviado candidaturas. Las B contienen condiciones sin resolver; las pistas no equivalen a fichas completas. Las citas acreditan el texto leído, no aseguran ausencia de errores semánticos del modelo.');
 return lines.join('\n')+'\n';
}
export async function writeSearchReport(runId,report) {
 const previous=reportWrites.get(runId) || Promise.resolve();
 const current=previous.catch(()=>{}).then(async()=>{
  try {
   const result=await writeReportFiles(runId,report);
   if(!result.stale) await pool.query('UPDATE search_run_state SET report_files_revision=$2,report_files_error=NULL WHERE run_id=$1 AND report_revision=$2',[runId,report.report_revision]);
   return result;
  } catch {
   const error='No se pudieron guardar los archivos del informe. Comprueba espacio y permisos de reports; la próxima consulta intentará regenerarlos sin repetir la búsqueda.';
   await pool.query('UPDATE search_run_state SET report_files_error=$3 WHERE run_id=$1 AND report_revision=$2',[runId,report.report_revision,error]);
   return {pending:true,error};
  }
 });reportWrites.set(runId,current);
 try {return await current;} finally {if(reportWrites.get(runId)===current) reportWrites.delete(runId);}
}
async function writeReportFiles(runId,report) {
 validId(runId);
 const state=(await pool.query('SELECT report_revision FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
 if(report.report_revision && state?.report_revision!==report.report_revision) return {stale:true};
 const candidates=(await pool.query('SELECT c.*,d.checked_at FROM search_candidates c LEFT JOIN search_documents d ON d.candidate_id=c.id WHERE c.run_id=$1 ORDER BY c.created_at,c.id',[runId])).rows;
 candidates.sort(compareCandidates);
 const tasks=(await pool.query("SELECT candidate_id,kind,input,result FROM search_steps WHERE run_id=$1 AND status='succeeded' AND (kind LIKE 'extract_%' OR kind LIKE 'decide_%' OR kind='assess_fit') ORDER BY created_at,id",[runId])).rows;
 for(const candidate of candidates) {candidate.overrides=(await pool.query('SELECT field,value,evidence,reason FROM search_candidate_overrides WHERE candidate_id=$1',[candidate.id])).rows;candidate.evidence=tasks.filter(task=>task.candidate_id===candidate.id);delete candidate.hint;}
 for(const candidate of candidates) candidate.reads=(await pool.query('SELECT * FROM search_document_reads WHERE candidate_id=$1 ORDER BY route',[candidate.id])).rows;
 const directory=new URL(`../reports/${runId}/`,import.meta.url);await mkdir(directory,{recursive:true});
 const staged=[];
 try {
  for(const [name,value] of [['informe.md',reportMarkdown(report,candidates)],['registro.json',JSON.stringify({report,candidates},null,2)+'\n']]) {
   const target=new URL(name,directory),temporary=new URL(`${name}.${randomUUID()}.tmp`,directory);
   staged.push({temporary,target});await writeFile(temporary,value,{mode:0o600});
  }
  const latest=(await pool.query('SELECT report_revision FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
  if(latest?.report_revision!==report.report_revision) return {stale:true};
  for(const {temporary,target} of staged) await rename(temporary,target);
 } finally {
  await Promise.all(staged.map(({temporary})=>rm(temporary,{force:true}).catch(()=>{})));
 }

 return {report:`/api/search/runs/${runId}/report`,register:`/api/search/runs/${runId}/register`};
}
