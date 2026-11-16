import {pool,transaction} from './db.js';
import {claimBrowserTask,submitBrowserDiscovery,submitBrowserRead,submitBrowserApplication} from './search.js';
import {captureTask,createBrowserVisit} from './browser-capture.js';
import {dispatchSearch} from './workflow.js';
const active=new Set();
export async function runBrowserTask(runId,{openBrowser=createBrowserVisit,capture=captureTask,dispatch=dispatchSearch}={}) {
 if(active.has(runId)) return;
 active.add(runId);let task,browser;
 try {
  task=await claimBrowserTask(runId);
  if(task.status==='skipped') return;
  const run=(await pool.query('SELECT settings_snapshot FROM workflow_runs WHERE id=$1',[runId])).rows[0];
  browser=await openBrowser();
  const input=await capture(task,{visit:async url=>{
   const state=(await pool.query('SELECT control FROM search_run_state WHERE run_id=$1',[runId])).rows[0];
   if(state?.control!=='active') throw new Error('Búsqueda pausada o cancelada');
   return browser.visit(url);
  },reasoning_effort:run.settings_snapshot.reasoning_effort || 'max',model:run.settings_snapshot.provider==='openai'?undefined:run.settings_snapshot.model || undefined});
  const submit=task.kind==='discover'?submitBrowserDiscovery:task.kind==='read'?submitBrowserRead:submitBrowserApplication;
  await submit(runId,task.step_id,input);
 } catch(error) {
  if(task?.step_id) await transaction(async client=>{
   const message=`Navegador autónomo: ${String(error.message).slice(0,1800)}`;
   const updated=await client.query("UPDATE search_steps SET status='unknown',error=$2,finished_at=now() WHERE id=$1 AND status='running' RETURNING id",[task.step_id,message]);
   if(!updated.rowCount) return;
   await client.query("UPDATE search_step_attempts SET status='unknown',error=$2,finished_at=now() WHERE step_id=$1 AND status='running'",[task.step_id,message]);
   await client.query("UPDATE search_run_state SET control=CASE WHEN control='cancelled' THEN control ELSE 'paused' END,revision=revision+1 WHERE run_id=$1",[runId]);
   await client.query('UPDATE workflow_runs SET error=$2 WHERE id=$1',[runId,message]);
  });
  else console.error('No se pudo reclamar tarea de navegador:',error.message);
  return;
 } finally {await browser?.close().catch(()=>{});active.delete(runId);}
 await dispatch(runId);
}
