import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import {pool,transaction} from './db.js';
import {startSearchRun} from './search.js';
export const scheduleSchema=z.object({revision:z.number().int().positive(),enabled:z.boolean(),interval_minutes:z.number().int().min(15).max(525600),next_run_at:z.string().datetime()}).strict();
export async function getSchedule(client=pool) {
 return (await client.query('SELECT * FROM workflow_schedule WHERE id=1')).rows[0];
}
export async function saveSchedule(input) {
 const parsed=scheduleSchema.safeParse(input);
 if(!parsed.success) throw new Error('Programación inválida: intervalo de 15 a 525600 minutos y fecha UTC requerida.');
 const value=parsed.data;
 if(!Number.isFinite(Date.parse(value.next_run_at))) throw new Error('Fecha de programación inválida');
 const result=await pool.query('UPDATE workflow_schedule SET enabled=$1,interval_minutes=$2,next_run_at=$3,revision=revision+1 WHERE id=1 AND revision=$4 RETURNING *',[value.enabled,value.interval_minutes,value.next_run_at,value.revision]);
 if(!result.rowCount) throw Object.assign(new Error('La programación ha cambiado; vuelve a leerla.'),{status:409});
 return result.rows[0];
}
export async function tickSchedule() {
 return transaction(async client=>{
  const control=(await client.query('SELECT enabled FROM workflow_control WHERE id=1 FOR UPDATE')).rows[0];
  const schedule=(await client.query('SELECT *,next_run_at<=now() AS due FROM workflow_schedule WHERE id=1 FOR UPDATE')).rows[0];
  if(!schedule.enabled || !schedule.due) {
   const status=schedule.enabled?'not_due':'disabled';
   await client.query('UPDATE workflow_schedule SET last_checked_at=now(),last_status=$1,last_error=NULL WHERE id=1',[status]);
   return {status};
  }
  let status,error=null,run;
  if(!control.enabled) status='paused';
  else if((await client.query("SELECT 1 FROM workflow_runs WHERE status IN ('queued','running','unknown') LIMIT 1")).rowCount) status='busy';
  else if(!(await client.query('SELECT history_ready FROM search_settings WHERE id=1')).rows[0].history_ready) status='history_pending';
  else {
   await client.query('SAVEPOINT schedule_run');
   try {run=await startSearchRun({id:randomUUID()},client);status='started';}
   catch(failure) {await client.query('ROLLBACK TO SAVEPOINT schedule_run');status='configuration_error';error=failure.message;}
   await client.query('RELEASE SAVEPOINT schedule_run');
  }
  await client.query(`UPDATE workflow_schedule SET last_checked_at=now(),last_status=$1,last_error=$2,
   last_run_id=COALESCE($3,last_run_id),next_run_at=CASE WHEN $1='started' THEN now()+interval_minutes*interval '1 minute' ELSE next_run_at END WHERE id=1`,[status,error,run?.id]);
  return {status,...(run?{run_id:run.id}:{}),...(error?{error}:{})};
 });
}
