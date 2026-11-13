import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {timingSafeEqual} from 'node:crypto';
import {pool, transaction} from './db.js';
import {offerInput, validateSettings, validId, availabilityStates, reviewStates, applicationStates, actionStates} from './domain.js';
import {saveOffer, saveAction, appendPublication, checkHistory, mergeOffers} from './store.js';
import {workflowStatus,startRun,recoverRuns,runTask,finishRun,dispatchSearch} from './workflow.js';
import {handleMcpHttp,integrationInfo} from './mcp.js';
import {getSearchConfig,saveSearchConfig} from './search-config.js';
import {searchNext,runSearchStep,controlSearch,getSearchResults,getSearchCandidate,trackSearchCandidate,ensureFreshSearch,resolveSearchIdentity,correctSearchCandidate} from './search.js';
import {getSchedule,saveSchedule,tickSchedule} from './schedule.js';
import {modelCatalog} from './models.js';
const port = Number(process.env.PORT || 3210);
const origin = `http://127.0.0.1:${port}`;
const send = (res, status, value) => {
  res.writeHead(status, {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'});
  res.end(JSON.stringify(value));
};
async function body(req) {
  let input = '';
  for await (const chunk of req) {
    input += chunk;
    if (Buffer.byteLength(input) > 300000) throw Object.assign(new Error('Petición demasiado grande'), {status: 413});
  }
  try { return JSON.parse(input); } catch {throw new Error('JSON inválido');}
}
function authenticated(req,token=process.env.N8N_TOKEN) {
  const received = req.headers.authorization || '';
  const expected = `Bearer ${token}`;
  return token && Buffer.byteLength(received) === Buffer.byteLength(expected) && timingSafeEqual(Buffer.from(received), Buffer.from(expected));
}
function pagination(url) {
  const limit=url.searchParams.has('limit')?Number(url.searchParams.get('limit')):null;
  const offset=Number(url.searchParams.get('offset') || 0);
  if ((limit!==null && (!Number.isSafeInteger(limit) || limit<1 || limit>100)) || !Number.isSafeInteger(offset) || offset<0) throw new Error('Paginación inválida: limit 1–100, offset >= 0.');
  return [limit,offset];
}
async function runTasks(id,module,url) {
  const [requested,offset]=pagination(url),limit=requested ?? 25,status=url.searchParams.get('task_status');
  if(status && !['pending','running','succeeded','failed','unknown'].includes(status)) throw new Error('Estado de tarea inválido');
  const table=module==='search'?'search_steps':'workflow_tasks';
  const counts=Object.fromEntries((await pool.query(`SELECT status,count(*)::integer AS count FROM ${table} WHERE run_id=$1 GROUP BY status`,[id])).rows.map(row=>[row.status,row.count]));
  const total=Object.values(counts).reduce((sum,count)=>sum+count,0),filteredTotal=status?(counts[status] || 0):total;
  const columns=module==='search'?'id,candidate_id,kind AS task_id,status,result,error,started_at,finished_at,row_number() OVER (ORDER BY created_at,id)::integer AS position':'*';
  const items=(await pool.query(`WITH tasks AS (SELECT ${columns} FROM ${table} WHERE run_id=$1) SELECT * FROM tasks WHERE ($4::text IS NULL OR status=$4) ORDER BY position LIMIT $2 OFFSET $3`,[id,limit,offset,status])).rows;
  return {items,total,filtered_total:filteredTotal,counts,limit,offset,next_offset:offset+items.length<filteredTotal?offset+items.length:null};
}
function patchInput(value,keys) {
  if (!value || typeof value!=='object' || Array.isArray(value) || !Object.keys(value).length || Object.keys(value).some(key=>!keys.includes(key))) throw new Error('Cambios vacíos o campos no admitidos.');
  return value;
}
await recoverRuns();
http.createServer(async (req, res) => {
  try {
    if (![`127.0.0.1:${port}`, `host.docker.internal:${port}`].includes(req.headers.host)) return send(res, 403, {error: `Abre ${origin}`});
    if (req.headers.origin && req.headers.origin !== origin) return send(res, 403, {error: 'Origen inválido'});
    const url=new URL(req.url,origin),path=url.pathname;
    if (path==='/mcp') {
      if (!process.env.MCP_TOKEN) return send(res,503,{error:'Configura MCP_TOKEN en .env y reinicia el servicio.'});
      if (!authenticated(req,process.env.MCP_TOKEN)) return send(res,401,{error:'MCP_TOKEN requerido'});
      if (req.method!=='POST') return send(res,405,{jsonrpc:'2.0',id:null,error:{code:-32000,message:'Usa POST. Transporte HTTP sin sesiones ni SSE persistente.'}});
      let parsed;
      try {parsed=await body(req);} catch(error) {return send(res,error.status || 400,{jsonrpc:'2.0',id:null,error:{code:error.status===413?-32600:-32700,message:error.message}});}
      return await handleMcpHttp(req,res,parsed,origin);
    }
    if (path === '/' && req.method === 'GET') {
      res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'"});
      return res.end(await readFile(new URL('../public/index.html', import.meta.url)));
    }
    if (['/app.js', '/offer-state.js', '/style.css'].includes(path) && req.method === 'GET') {
      res.writeHead(200, {'Content-Type': path.endsWith('.js') ? 'text/javascript' : 'text/css'});
      return res.end(await readFile(new URL(`../public${path}`, import.meta.url)));
    }
    if (path==='/MCP.md' && req.method==='GET') {
      res.writeHead(200,{'Content-Type':'text/plain; charset=utf-8'});
      return res.end(await readFile(new URL('../MCP.md',import.meta.url)));
    }
    if (req.method !== 'GET' && req.headers['x-empleo-client'] !== 'panel' && !authenticated(req) && !authenticated(req,process.env.MCP_TOKEN)) return send(res, 401, {error: 'Credencial requerida'});
    if (path==='/api/integration' && req.method==='GET') return send(res,200,integrationInfo(origin));
    if (path === '/api/runtime' && req.method === 'GET') return send(res, 200, {databaseConfigured: Boolean(pool)});
    if (path.startsWith('/api/') && !pool) return send(res, 503, {error: 'Neon pendiente de configuración. Añade DATABASE_URL en 11/.env, ejecuta la migración y reinicia el servicio.'});
    if (path==='/api/workflow/schedule' && req.method==='GET') return send(res,200,await getSchedule());
    if (path==='/api/workflow/schedule' && req.method==='PUT') return send(res,200,await saveSchedule(await body(req)));
    if (path==='/api/workflow/schedule/tick' && req.method==='POST') {
      if(!authenticated(req)) return send(res,401,{error:'N8N_TOKEN requerido'});
      const result=await tickSchedule();
      if(result.run_id) void dispatchSearch(result.run_id);
      return send(res,200,result);
    }
    if (path === '/api/workflow' && req.method === 'GET') return send(res,200,await workflowStatus());
    if (path === '/api/workflow/control' && req.method === 'PUT') {
      const value=await body(req);
      if (typeof value.enabled!=='boolean' || !Number.isSafeInteger(value.revision)) throw new Error('Control inválido');
      const result=await pool.query('UPDATE workflow_control SET enabled=$1,revision=revision+1 WHERE id=1 AND revision=$2 RETURNING *',[value.enabled,value.revision]);
      return send(res,result.rowCount?200:409,result.rows[0] || {error:'El control ha cambiado. Actualiza el estado.'});
    }
    if (path === '/api/workflow/runs' && req.method === 'GET') {
      const [limit,offset]=pagination(url),status=url.searchParams.get('status');
      if (status && !['queued','running','succeeded','failed','unknown'].includes(status)) throw new Error('Estado de ejecución inválido');
      return send(res,200,(await pool.query('SELECT id,module,status,settings_revision,n8n_execution_id,result,error,created_at,started_at,finished_at FROM workflow_runs WHERE ($1::text IS NULL OR status=$1) ORDER BY created_at DESC,id DESC LIMIT $2 OFFSET $3',[status,limit ?? 50,offset])).rows);
    }
    if (path === '/api/workflow/runs' && req.method === 'POST') return send(res,202,await startRun(await body(req)));
    if (/^\/api\/workflow\/runs\/[0-9a-f-]{36}(?:\/tasks)?$/.test(path) && req.method==='GET') {
      const id=validId(path.split('/')[4]);
      let run=(await pool.query('SELECT * FROM workflow_runs WHERE id=$1',[id])).rows[0];
      if(run?.module==='search') {await ensureFreshSearch(id);run=(await pool.query('SELECT * FROM workflow_runs WHERE id=$1',[id])).rows[0];}
      if (!run) return send(res,404,{error:'Ejecución no encontrada'});
      const {items,...taskPage}=await runTasks(id,run.module,url);
      if(path.endsWith('/tasks')) return send(res,200,{items,...taskPage});
      run.tasks=items;run.task_page=taskPage;
      if(run.module==='search') run.search=(await pool.query('SELECT * FROM search_run_state WHERE run_id=$1',[id])).rows[0];
      delete run.task_claimed;
      if (url.searchParams.get('include_input')!=='true') delete run.input_text;
      if (url.searchParams.get('include_settings')!=='true') delete run.settings_snapshot;
      return send(res,200,run);
    }
    if (/^\/api\/workflow\/runs\/[0-9a-f-]{36}\/resolve$/.test(path) && req.method === 'POST') {
      const id=validId(path.split('/')[4]),input=await body(req);
      if (typeof input.reason!=='string' || !input.reason.trim() || input.reason.length>2000) throw new Error('Documenta qué has comprobado en n8n.');
      const result=await pool.query("UPDATE workflow_runs SET status='failed',error=concat(error,E'\nRevisión manual: ',$2::text),finished_at=now() WHERE id=$1 AND status='unknown' RETURNING id",[id,input.reason.trim()]);
      return send(res,result.rowCount?200:409,result.rows[0] || {error:'Solo se puede resolver una ejecución de resultado incierto.'});
    }
    const candidateRoute=path.match(/^\/api\/search\/candidates\/([0-9a-f-]{36})(?:\/(track|identity|correction))?$/);
    if(candidateRoute) {
      if(req.method==='GET' && !candidateRoute[2]) return send(res,200,await getSearchCandidate(candidateRoute[1],{includeText:url.searchParams.get('include_text')==='true'}));
      if(req.method==='POST' && candidateRoute[2]==='identity') return send(res,200,await resolveSearchIdentity(candidateRoute[1],await body(req)));
      if(req.method==='POST' && candidateRoute[2]==='correction') return send(res,200,await correctSearchCandidate(candidateRoute[1],await body(req)));
      if(req.method==='POST' && candidateRoute[2]==='track') return send(res,200,await trackSearchCandidate(candidateRoute[1]));
    }
    const searchRoute=path.match(/^\/api\/search\/runs\/([0-9a-f-]{36})\/(next|control|results|steps|report|register)(?:\/([0-9a-f-]{36}))?$/);
    if (searchRoute) {
      const id=validId(searchRoute[1]),section=searchRoute[2];
      if (['report','register'].includes(section) && req.method==='GET') {
        await ensureFreshSearch(id);
        const artifactState=(await pool.query('SELECT report_revision,report_files_revision,report_files_error FROM search_run_state WHERE run_id=$1',[id])).rows[0];
        if(artifactState && (artifactState.report_files_error || artifactState.report_files_revision!==artifactState.report_revision)) return send(res,503,{error:artifactState.report_files_error || 'Informe actualizándose; vuelve a consultar.'});
        const filename=section==='report'?'informe.md':'registro.json';
        const artifactPath=new URL(`../reports/${id}/${filename}`,import.meta.url);
        let content;try {content=await readFile(artifactPath,'utf8');}catch {
          if(!artifactState?.report_revision) return send(res,404,{error:'El informe se genera al terminar un lote o cerrar la búsqueda.'});
          await pool.query('UPDATE search_run_state SET report_files_revision=0 WHERE run_id=$1',[id]);
          await ensureFreshSearch(id);
          try {content=await readFile(artifactPath,'utf8');}catch {return send(res,503,{error:'Los archivos del informe no están disponibles. Comprueba espacio y permisos de reports.'});}
        }
        const latestState=(await pool.query('SELECT s.report_revision,s.report_files_revision,s.report_files_error,s.report_dirty,s.history_revision,h.revision AS current_history_revision FROM search_run_state s CROSS JOIN history_state h WHERE s.run_id=$1 AND h.id=1',[id])).rows[0];
        if(latestState && (latestState.report_dirty || latestState.report_files_error || latestState.report_revision!==artifactState.report_revision || latestState.report_files_revision!==latestState.report_revision || String(latestState.history_revision)!==String(latestState.current_history_revision))) return send(res,503,{error:'El informe ha cambiado durante la lectura; vuelve a consultar la versión actual.'});
        if(url.searchParams.get('format')==='json') {const offset=Number(url.searchParams.get('offset') || 0),max=Number(url.searchParams.get('max_chars') || 20000);if(!Number.isSafeInteger(offset) || offset<0 || !Number.isSafeInteger(max) || max<1 || max>100000) throw new Error('Fragmento de informe inválido');return send(res,200,{run_id:id,content:content.slice(offset,offset+max),offset,next_offset:offset+max<content.length?offset+max:null});}
        res.writeHead(200,{'Content-Type':section==='report'?'text/markdown; charset=utf-8':'application/json; charset=utf-8','Content-Disposition':`attachment; filename="${id}-${filename}"`,'Cache-Control':'no-store'});return res.end(content);
      }
      if (section==='results' && req.method==='GET') {const [limit,offset]=pagination(url);return send(res,200,await getSearchResults(id,{limit:limit ?? 25,offset}));}
      if (section==='control' && req.method==='POST') {
        const result=await controlSearch(id,await body(req));
        if (result.dispatch) void dispatchSearch(id);
        return send(res,200,result);
      }
      if (!authenticated(req)) return send(res,401,{error:'Credencial n8n requerida'});
      if (section==='next' && req.method==='POST') return send(res,200,await searchNext(id));
      if (section==='steps' && searchRoute[3] && req.method==='POST') {const value=await body(req);return send(res,200,await runSearchStep(id,searchRoute[3],value.kind,value.execution_id));}
    }
    if (path === '/api/catalogs' && req.method === 'GET') return send(res,200,{availability:availabilityStates,review_state:reviewStates,application_state:applicationStates,action_state:actionStates});
    if (path === '/api/companies' && req.method === 'GET') return send(res,200,(await pool.query('SELECT id,name FROM companies WHERE ($1::text IS NULL OR name ILIKE $1) ORDER BY name,id LIMIT $2 OFFSET $3',[url.searchParams.has('q')?`%${url.searchParams.get('q')}%`:null,...pagination(url)])).rows);
    if (path === '/api/search/config' && req.method === 'GET') return send(res,200,await getSearchConfig());
    if (path === '/api/search/config' && req.method === 'PUT') return send(res,200,await saveSearchConfig(await body(req)));
    if (path === '/api/models' && req.method === 'GET') return send(res,200,await modelCatalog());
    if (path === '/api/settings' && req.method === 'GET') return send(res,200,(await pool.query('SELECT * FROM settings_summary WHERE id=1')).rows[0]);
    if (path === '/api/settings' && ['PUT','PATCH'].includes(req.method)) {
      const input = await body(req);
      const updated = await transaction(async client => {
        await client.query('SELECT id FROM search_settings WHERE id=1 FOR UPDATE');
        const current=(await client.query('SELECT * FROM settings_summary WHERE id=1')).rows[0];
        if (input.revision!==current.revision) return null;
        const value=validateSettings(req.method==='PATCH'?{...current.value,...patchInput(input.patch,Object.keys(current.value))}:input.value);
        const result = await client.query('UPDATE search_settings SET max_openings=$1,batch_size=$2,max_age_days=$3,timezone=$4,history_ready=$5,model=$6,source_prompt=$7,provider=$9,model_retries=COALESCE($10,model_retries),model_timeout_seconds=COALESCE($11,model_timeout_seconds),public_alternatives=COALESCE($12,public_alternatives),revision=revision+1 WHERE id=1 AND revision=$8 RETURNING id',[value.max_openings,value.batch_size,value.max_age_days,value.timezone,value.history_ready,value.model,value.source_prompt,input.revision,value.provider ?? 'codex',value.model_retries,value.model_timeout_seconds,value.public_alternatives]);
        if (!result.rowCount) return null;
        await client.query("UPDATE search_quotas SET target=CASE zone WHEN 'spain' THEN $1::integer ELSE $2::integer END WHERE settings_id=1",[value.quota_spain,value.quota_europe]);
        return (await client.query('SELECT * FROM settings_summary WHERE id=1')).rows[0];
      });
      return send(res,updated?200:409,updated || {error:'Configuración modificada. Recarga.'});
    }
    if (path === '/api/offers' && req.method === 'GET') {
      const state=url.searchParams.get('application_state');
      if (state && !applicationStates.includes(state)) throw new Error('Estado de candidatura inválido');
      return send(res,200,(await pool.query(`SELECT summary.*,coalesce((SELECT jsonb_agg(jsonb_build_object('id',p.id,'url',p.url,'is_primary',p.is_primary) ORDER BY p.is_primary DESC,p.created_at,p.id) FROM publications p WHERE p.opportunity_id=summary.id),'[]'::jsonb) AS publications FROM offer_summary summary WHERE ($1::text IS NULL OR company ILIKE $1 OR title ILIKE $1) AND ($2::text IS NULL OR application_state=$2) ORDER BY updated_at DESC,id DESC LIMIT $3 OFFSET $4`,[url.searchParams.has('q')?`%${url.searchParams.get('q')}%`:null,state,...pagination(url)])).rows);
    }
    if (path === '/api/offers' && req.method === 'POST') return send(res,201,await saveOffer(null,offerInput(await body(req))));
    const match = path.match(/^\/api\/offers\/([0-9a-f-]{36})(?:\/(events|publications|actions|merge)(?:\/([0-9a-f-]{36}))?)?$/);
    if (match) {
      const id=validId(match[1]), section=match[2], childId=match[3];
      if (section==='merge' && req.method==='POST') return send(res,200,await mergeOffers(id,await body(req)));
      if (['PUT','PATCH'].includes(req.method) && !section) {
        const raw = await body(req);
        let value=raw;
        if (req.method==='PATCH') {
          const current=(await pool.query('SELECT * FROM offer_summary WHERE id=$1',[id])).rows[0];
          if (!current) return send(res,404,{error:'Proceso no encontrado'});
          value={...current,...patchInput(raw.patch,['company','company_id','title','availability','review_state','application_state','submitted_at','notes','reason'])};
          if (!Object.hasOwn(raw.patch,'submitted_at')) delete value.submitted_at;
        }
        return send(res,200,await saveOffer(id,offerInput(value),raw.version));
      }
      if (req.method==='GET' && !section) {
        const offer=(await pool.query('SELECT * FROM offer_summary WHERE id=$1',[id])).rows[0];
        if(!offer) {const merged=(await pool.query('SELECT target_id FROM opportunity_merges WHERE source_id=$1',[id])).rows[0];if(merged) return send(res,410,{error:'Proceso fusionado',target_id:merged.target_id});}
        return send(res,offer?200:404,offer || {error:'Proceso no encontrado'});
      }
      if (req.method === 'GET' && !childId) {
        const queries = {
          events:'SELECT * FROM opportunity_events WHERE opportunity_id=$1 OR opportunity_id IN (SELECT source_id FROM opportunity_merges WHERE target_id=$1) ORDER BY id DESC LIMIT $2 OFFSET $3',
          publications:'SELECT p.*,s.label AS source FROM publications p JOIN sources s ON s.id=p.source_id WHERE opportunity_id=$1 ORDER BY is_primary DESC,p.created_at,p.id LIMIT $2 OFFSET $3',
          actions:'SELECT * FROM follow_up_actions WHERE opportunity_id=$1 ORDER BY due_on NULLS LAST,created_at,id LIMIT $2 OFFSET $3'
        };
        if (queries[section]) return send(res,200,(await pool.query(queries[section],[id,...pagination(url)])).rows);
      }
      if (section === 'publications' && req.method === 'POST' && !childId) return send(res,201,await appendPublication(id,await body(req)));
      if (section === 'actions' && ((req.method === 'POST' && !childId) || (req.method === 'PUT' && childId))) return send(res,childId?200:201,await saveAction(id,childId,await body(req)));
    }
    if (path === '/api/history/check' && req.method === 'POST') return send(res,200,await checkHistory(await body(req)));
    if (/^\/api\/tasks\/[a-z_]+$/.test(path) && req.method==='POST') {
      if (!authenticated(req)) return send(res,401,{error:'Credencial n8n requerida'});
      const input=await body(req),id=validId(input.run_id),taskId=path.split('/')[3];
      if (taskId==='finish') return send(res,200,await finishRun(id,input.execution_id));
      const task=await runTask(id,taskId,input.text);
      // Compatibilidad con el workflow de contrato ya publicado.
      return send(res,200,taskId==='contract'?(task.result || {error:task.error}):{task_id:taskId,status:task.status});
    }
    send(res, 404, {error: 'Ruta desconocida'});
  } catch (error) {
    if (res.headersSent) {res.end(); return;}
    if (error.code === '23505') return send(res, 409, {error: 'Ese enlace o identificador ya existe. Revisa el proceso registrado.'});
    const infrastructure = error.code || /Codex/.test(error.message);
    send(res, error.status || (infrastructure ? 503 : 400), {error: infrastructure ? (error.message.startsWith('Codex') ? error.message : 'No se pudo completar la operación en Neon. Comprueba la conexión y las migraciones.') : error.message});
  }
}).listen(port, process.env.HOST || '127.0.0.1', () => console.log(`Panel disponible en ${origin}`));
