import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {timingSafeEqual} from 'node:crypto';
import {pool, transaction} from './db.js';
import {offerInput, validateSettings, validId, availabilityStates, reviewStates, applicationStates, actionStates} from './domain.js';
import {saveOffer, saveAction, appendPublication, checkHistory} from './store.js';
import {workflowStatus,startRun,recoverRuns,runTask,finishRun} from './workflow.js';
import {handleMcpHttp,integrationInfo} from './mcp.js';
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
    if (/^\/api\/workflow\/runs\/[0-9a-f-]{36}$/.test(path) && req.method==='GET') {
      const id=validId(path.split('/')[4]);
      const run=(await pool.query('SELECT * FROM workflow_runs WHERE id=$1',[id])).rows[0];
      if (!run) return send(res,404,{error:'Ejecución no encontrada'});
      run.tasks=(await pool.query('SELECT * FROM workflow_tasks WHERE run_id=$1 ORDER BY position',[id])).rows;
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
    if (path === '/api/catalogs' && req.method === 'GET') return send(res,200,{availability:availabilityStates,review_state:reviewStates,application_state:applicationStates,action_state:actionStates});
    if (path === '/api/companies' && req.method === 'GET') return send(res,200,(await pool.query('SELECT id,name FROM companies WHERE ($1::text IS NULL OR name ILIKE $1) ORDER BY name,id LIMIT $2 OFFSET $3',[url.searchParams.has('q')?`%${url.searchParams.get('q')}%`:null,...pagination(url)])).rows);
    if (path === '/api/settings' && req.method === 'GET') return send(res,200,(await pool.query('SELECT * FROM settings_summary WHERE id=1')).rows[0]);
    if (path === '/api/settings' && ['PUT','PATCH'].includes(req.method)) {
      const input = await body(req);
      const updated = await transaction(async client => {
        await client.query('SELECT id FROM search_settings WHERE id=1 FOR UPDATE');
        const current=(await client.query('SELECT * FROM settings_summary WHERE id=1')).rows[0];
        if (input.revision!==current.revision) return null;
        const value=validateSettings(req.method==='PATCH'?{...current.value,...patchInput(input.patch,Object.keys(current.value))}:input.value);
        const result = await client.query('UPDATE search_settings SET max_openings=$1,batch_size=$2,max_age_days=$3,timezone=$4,history_ready=$5,model=$6,source_prompt=$7,revision=revision+1 WHERE id=1 AND revision=$8 RETURNING id',[value.max_openings,value.batch_size,value.max_age_days,value.timezone,value.history_ready,value.model,value.source_prompt,input.revision]);
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
    const match = path.match(/^\/api\/offers\/([0-9a-f-]{36})(?:\/(events|publications|actions)(?:\/([0-9a-f-]{36}))?)?$/);
    if (match) {
      const id=validId(match[1]), section=match[2], childId=match[3];
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
        return send(res,offer?200:404,offer || {error:'Proceso no encontrado'});
      }
      if (req.method === 'GET' && !childId) {
        const queries = {
          events:'SELECT * FROM opportunity_events WHERE opportunity_id=$1 ORDER BY id DESC LIMIT $2 OFFSET $3',
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
}).listen(port, '127.0.0.1', () => console.log(`Panel disponible en ${origin}`));
