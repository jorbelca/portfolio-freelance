import {mkdir,writeFile,rename} from 'node:fs/promises';
import {validId} from './domain.js';
import {pool} from './db.js';
import {compareCandidates} from './evaluation.js';
import {randomUUID} from 'node:crypto';
const reportWrites=new Map();
const escape=value=>String(value ?? '').replace(/[\\`*_{}\[\]<>|]/g,'\\$&').replace(/[\r\n]+/g,' ');
export function reportMarkdown(report,candidates) {
 const lines=[`# Búsqueda de empleo`, ``, `Fecha de corte: ${new Date(report.cutoff).toLocaleString('es-ES',{timeZone:report.timezone})} (${report.timezone}).`, `Fichas: ${report.openings}/${report.max_openings}. España: ${report.spain}/${report.quota_spain}. Resto de Europa: ${report.europe}/${report.quota_europe}.`, `Déficit: España ${report.deficit_spain}; Europa ${report.deficit_europe}.`, `Motivo de cierre: ${report.reason}. ${report.fulfilled?'Reparto verificado.':'Objetivo de cupos no cumplido.'}`,``];
 const countries={};for(const row of candidates) if(row.evaluation?.computable && row.evaluation.country) countries[row.evaluation.country]=(countries[row.evaluation.country] || 0)+1;
 lines.push(`Desglose computable por país: ${Object.entries(countries).map(([country,count])=>`${escape(country)}: ${count}`).join('; ') || 'ninguno'}.`,``);
 for(const [classification,title] of [['A','A · Recomendadas y verificadas'],['B','B · Pendientes'],['C','C · Excluidas'],['pista','Pistas sin ficha completa']]) {
  lines.push(`## ${title}`,``);
  const rows=candidates.filter(row=>(row.evaluation?.classification || 'pista')===classification);
  if(!rows.length) lines.push('Sin resultados.',``);
  for(const row of rows) {
   lines.push(`### ${escape(row.title)} · ${escape(row.company)}`,``, `[Fuente: ${escape(row.source)}](${row.url.replace(/\(/g,'%28').replace(/\)/g,'%29')})`, `ID: ${row.id}. Computable: ${row.evaluation?.computable?'sí':'no'}. País: ${escape(row.evaluation?.country || 'no acreditado')}. Encaje: ${escape(row.evaluation?.fit || 'sin evaluar')}.`,``);
   if(row.reason) lines.push(escape(row.reason),``);
   for(const item of row.evaluation?.exclusions || []) lines.push(`- Exclusión ${escape(item.rule)}: ${escape(item.evidence)}`);
   for(const item of row.evaluation?.pending || []) lines.push(`- Pendiente (${escape(item.owner)}): ${escape(item.resolution)}`);
   for(const correction of row.overrides || []) lines.push(`- Corrección manual ${escape(correction.field)}: ${escape(typeof correction.value==='object'?correction.value.value:correction.value)}. Evidencia: «${escape(correction.evidence)}». Motivo: ${escape(correction.reason)}.`);
   for(const task of row.evidence || []) if(task.result?.state==='acreditado') lines.push(`- ${escape(task.kind)}: ${escape(task.result.value)}. Evidencia: «${escape(task.result.evidence)}».`);
   lines.push('');
  }
 }
 lines.push('## Límites', '', 'No se han enviado candidaturas. Las B contienen condiciones sin resolver; las pistas no equivalen a fichas completas. Las citas acreditan el texto leído, no aseguran ausencia de errores semánticos del modelo.');
 return lines.join('\n')+'\n';
}
export async function writeSearchReport(runId,report) {
 const previous=reportWrites.get(runId) || Promise.resolve();
 const current=previous.catch(()=>{}).then(()=>writeReportFiles(runId,report));reportWrites.set(runId,current);
 try {return await current;} finally {if(reportWrites.get(runId)===current) reportWrites.delete(runId);}
}
async function writeReportFiles(runId,report) {
 validId(runId);
 const state=(await pool.query('SELECT report_revision FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
 if(report.report_revision && state?.report_revision!==report.report_revision) return {stale:true};
 const candidates=(await pool.query('SELECT * FROM search_candidates WHERE run_id=$1 ORDER BY created_at,id',[runId])).rows;
 candidates.sort(compareCandidates);
 const tasks=(await pool.query("SELECT candidate_id,kind,result FROM search_steps WHERE run_id=$1 AND status='succeeded' AND (kind LIKE 'extract_%' OR kind LIKE 'decide_%') ORDER BY created_at,id",[runId])).rows;
 for(const candidate of candidates) {candidate.overrides=(await pool.query('SELECT field,value,evidence,reason FROM search_candidate_overrides WHERE candidate_id=$1',[candidate.id])).rows;candidate.evidence=tasks.filter(task=>task.candidate_id===candidate.id);delete candidate.hint;}
 const directory=new URL(`../reports/${runId}/`,import.meta.url);await mkdir(directory,{recursive:true});
 for(const [name,value] of [['informe.md',reportMarkdown(report,candidates)],['registro.json',JSON.stringify({report,candidates},null,2)+'\n']]) {
  const target=new URL(name,directory),temporary=new URL(`${name}.${randomUUID()}.tmp`,directory);await writeFile(temporary,value,{mode:0o600});await rename(temporary,target);
 }
 return {report:`/api/search/runs/${runId}/report`,register:`/api/search/runs/${runId}/register`};
}
