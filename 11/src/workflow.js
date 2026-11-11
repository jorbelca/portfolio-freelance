import {pool, transaction} from './db.js';
import {validId} from './domain.js';
import {validateExtraction,extractField} from './codex.js';
import {tasksFor,extractionTasks} from './tasks.js';
const base = process.env.N8N_URL || 'http://127.0.0.1:5678';
export function runInput(value) {
  validId(value?.id);
  if (!['contract','extraction'].includes(value.module) || typeof value.text !== 'string' || !value.text.trim() || value.text.length>100000) throw new Error('Selecciona un módulo disponible e introduce una ficha real (máximo 100.000 caracteres).');
  return value;
}
export async function workflowStatus() {
  const deadline=extractionTasks.length*(Number(process.env.CODEX_TIMEOUT_MS || 120000)+30000)+60000;
  await pool.query("UPDATE workflow_runs SET status='unknown',error='n8n no confirmó el cierre dentro del plazo. Comprueba su historial.',finished_at=now() WHERE module='extraction' AND status='running' AND started_at < now()-($1::double precision * interval '1 millisecond')",[deadline]);
  let reachable=false;
  try {reachable=(await fetch(`${base}/healthz/readiness`,{signal:AbortSignal.timeout(3000)})).ok;} catch {}
  return {reachable,editorUrl:'http://localhost:5678/workflow/empleoContract01',control:(await pool.query('SELECT * FROM workflow_control WHERE id=1')).rows[0],modules:[
    {id:'contract',label:'Extraer contrato',available:true,workflowId:'empleoContract01',tasks:tasksFor('contract')},
    {id:'extraction',label:'Analizar ficha · 15 tareas',available:true,workflowId:'empleoExtraction02',tasks:extractionTasks},
    {id:'discovery',label:'Descubrir y recuperar fichas',available:false},
    {id:'identity',label:'Cruzar historial y duplicados',available:false},
    {id:'evaluation',label:'Evaluar requisitos y clasificar A/B/C',available:false},
    {id:'audit',label:'Auditar cupos y generar informe',available:false}
  ]};
}
export async function startRun(raw) {
  const input=runInput(raw);
  const run=await transaction(async client=>{
    const control=(await client.query('SELECT * FROM workflow_control WHERE id=1 FOR UPDATE')).rows[0];
    const previous=(await client.query('SELECT id,status,module,input_text FROM workflow_runs WHERE id=$1',[input.id])).rows[0];
    if (previous) {
      if (previous.module!==input.module || previous.input_text!==input.text) throw Object.assign(new Error('El identificador ya pertenece a otra petición.'),{status:409});
      return {id:previous.id,status:previous.status,existing:true};
    }
    if (!control.enabled) throw Object.assign(new Error('Las nuevas ejecuciones están pausadas.'),{status:409});
    if ((await client.query("SELECT 1 FROM workflow_runs WHERE status IN ('queued','running','unknown')")).rowCount) throw Object.assign(new Error('Hay una ejecución activa o de resultado incierto. Revísala antes de lanzar otra.'),{status:409});
    const settings=(await client.query('SELECT * FROM settings_summary WHERE id=1')).rows[0];
    await client.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,$2,'queued',$3,$4,$5)",[input.id,input.module,settings.revision,settings.value,input.text]);
    for (const [index,task] of tasksFor(input.module).entries()) await client.query('INSERT INTO workflow_tasks(run_id,task_id,position) VALUES($1,$2,$3)',[input.id,task.id,index+1]);
    return {id:input.id,status:'queued'};
  });
  if (!run.existing) void dispatch(run.id,input.text,input.module);
  return run;
}
async function dispatch(id,text,module) {
  try {
    await pool.query("UPDATE workflow_runs SET status='running',started_at=now() WHERE id=$1",[id]);
    const response=await fetch(`${base}/webhook/${module==='extraction'?'empleo-extraction':'empleo-contract'}`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${process.env.N8N_TOKEN}`},body:JSON.stringify({run_id:id,text}),signal:AbortSignal.timeout(160000)});
    if (!response.ok) {
      if (response.status===404 || response.status===401 || response.status===403) throw Object.assign(new Error('Workflow sin publicar o credencial n8n incorrecta. Ejecuta npm run setup:n8n.'),{definitive:true});
      throw new Error('n8n no confirmó el resultado. Comprueba su historial antes de repetir.');
    }
    if (module==='extraction') return; // n8n confirma recepción; el último nodo cierra desde resultados persistidos.
    const data=await response.json();
    if (data.run_id!==id || !data.execution_id) throw new Error('Respuesta de n8n no identificada. Revisa su historial.');
    const ok=['acreditado','desconocido'].includes(data.result?.state);
    if (ok) validateExtraction(data.result,text);
    await finishRun(id,String(data.execution_id));
  } catch(error) {
    await pool.query("UPDATE workflow_runs SET status=$2,error=$3,finished_at=now() WHERE id=$1 AND status IN ('queued','running')",[id,error.definitive?'failed':'unknown',error.message]).catch(()=>{});
  }
}
export async function runTask(id,taskId,text,extract=extractField) {
  validId(id);
  if (!extractionTasks.some(task=>task.id===taskId)) throw new Error('Tarea no disponible');
  const claimed=await transaction(async client=>{
    const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[id])).rows[0];
    if (!run || run.status!=='running' || (text!==undefined && text!==run.input_text)) throw Object.assign(new Error('Ejecución no activa o texto diferente.'),{status:409});
    const task=(await client.query('SELECT * FROM workflow_tasks WHERE run_id=$1 AND task_id=$2',[id,taskId])).rows[0];
    if (!task) throw Object.assign(new Error('La tarea no pertenece a esta ejecución.'),{status:409});
    if (['succeeded','failed'].includes(task.status)) return {cached:task};
    if (task.status!=='pending' || (await client.query("SELECT 1 FROM workflow_tasks WHERE run_id=$1 AND position<$2 AND status NOT IN ('succeeded','failed')",[id,task.position])).rowCount) throw Object.assign(new Error('Tarea en curso, incierta o fuera de orden.'),{status:409});
    await client.query("UPDATE workflow_tasks SET status='running',started_at=now() WHERE run_id=$1 AND task_id=$2",[id,taskId]);
    return {text:run.input_text,model:run.settings_snapshot.model};
  });
  if (claimed.cached) return claimed.cached;
  let result=null,error=null;
  try {result=validateExtraction(await extract(taskId,claimed.text,claimed.model || process.env.CODEX_MODEL),claimed.text);}
  catch {error='No se obtuvo una extracción válida. Comprueba sesión, cuota, modelo y tiempo de espera; la tarea no se reintenta automáticamente.';}
  return (await pool.query("UPDATE workflow_tasks SET status=$3,result=$4,error=$5,finished_at=now() WHERE run_id=$1 AND task_id=$2 AND status='running' RETURNING *",[id,taskId,error?'failed':'succeeded',result,error])).rows[0] || {status:'unknown',error:'Servicio reiniciado; revisa n8n.'};
}
export async function finishRun(id,executionId) {
  validId(id);
  if (typeof executionId!=='string' || !/^\d{1,30}$/.test(executionId)) throw new Error('Identificador de ejecución n8n inválido');
  return transaction(async client=>{
    const run=(await client.query('SELECT * FROM workflow_runs WHERE id=$1 FOR UPDATE',[id])).rows[0];
    if (!run) throw Object.assign(new Error('Ejecución no encontrada'),{status:404});
    if (['succeeded','failed'].includes(run.status) && run.n8n_execution_id===executionId) return {id,status:run.status};
    if (run.status!=='running') throw Object.assign(new Error('Ejecución no activa; comprueba la incidencia.'),{status:409});
    const tasks=(await client.query('SELECT * FROM workflow_tasks WHERE run_id=$1 ORDER BY position',[id])).rows;
    if (!tasks.length || tasks.some(task=>!['succeeded','failed'].includes(task.status))) throw Object.assign(new Error('Quedan tareas sin terminar.'),{status:409});
    const failed=tasks.filter(task=>task.status==='failed');
    const result=run.module==='contract'?tasks[0].result:Object.fromEntries(tasks.map(task=>[task.task_id,task.result || {state:'error',error:task.error}]));
    const status=failed.length?'failed':'succeeded';
    await client.query('UPDATE workflow_runs SET status=$2,n8n_execution_id=$3,result=$4,error=$5,finished_at=now() WHERE id=$1',[id,status,executionId,result,failed.length?`${failed.length} tarea(s) fallida(s). Se conservan las extracciones válidas.`:null]);
    return {id,status};
  });
}
export async function recoverRuns() {
  if (pool) await transaction(async client=>{
    await client.query("UPDATE workflow_tasks SET status='unknown',error='Servicio reiniciado; comprueba n8n.' WHERE status='running'");
    await client.query("UPDATE workflow_runs SET status='unknown',error='Servicio reiniciado. Revisa la ejecución en n8n antes de repetir.' WHERE status IN ('queued','running')");
  });
}
