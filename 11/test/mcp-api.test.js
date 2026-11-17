import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,mkdir,rm,readdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import net from 'node:net';
import pg from 'pg';
import {publicationIdentity} from '../src/identity.js';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';

test('MCP HTTP comparte validaciones, versiones y seguimiento en un esquema aislado eliminado al terminar',{skip:!process.env.DATABASE_URL,timeout:120000},async()=>{
  const admin=new pg.Client({connectionString:process.env.DATABASE_URL});
  const schema='test_mcp_'+randomUUID().replaceAll('-','');
  let child,client,created=false,artifactRun;
  await admin.connect();
  try {
    await admin.query('BEGIN'); await admin.query(`CREATE SCHEMA ${schema}`); await admin.query(`SET LOCAL search_path TO ${schema}`);
    const sql=async name=>(await readFile(new URL(`../sql/${name}`,import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,'');
    const defaults=JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'));
    for(const file of (await readdir(new URL('../sql/',import.meta.url))).filter(file=>/^\d+\.sql$/.test(file)).sort()) {
      await admin.query(await sql(file));
      if(file==='001.sql') await admin.query('INSERT INTO settings(id,value) VALUES(1,$1)',[defaults]);
    }
    await admin.query('COMMIT'); created=true;
    await admin.query(`SET search_path TO ${schema}`);
    assert.equal((await admin.query('SELECT current_schema() AS schema')).rows[0].schema,schema);
    const scoped=new URL(process.env.DATABASE_URL); scoped.searchParams.set('options',`-c search_path=${schema}`);
    const probe=new pg.Client({connectionString:scoped.href}); await probe.connect();
    try {assert.equal((await probe.query('SELECT current_schema() AS schema')).rows[0].schema,schema);} finally {await probe.end();}
    const listener=net.createServer(); listener.listen(0,'127.0.0.1'); await once(listener,'listening'); const port=listener.address().port;
    await new Promise(resolve=>listener.close(resolve));
    const token=randomUUID()+randomUUID(),base=`http://127.0.0.1:${port}`;
    child=spawn(process.execPath,[new URL('../src/server.js',import.meta.url).pathname],{env:{...process.env,DATABASE_URL:scoped.href,PORT:String(port),MCP_TOKEN:token,N8N_TOKEN:token+'-n8n'},stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('El servicio aislado no arrancó')),10000);
      child.once('error',error=>{clearTimeout(timer);reject(error);});
      child.once('exit',()=>{clearTimeout(timer);reject(new Error('El servicio aislado terminó antes de arrancar'));});
      child.stdout.on('data',chunk=>{if(chunk.toString().includes('Panel disponible')){clearTimeout(timer);resolve();}});
    });
    for(const asset of ['app.js','offer-state.js','workflow-state.js']) {
      const response=await fetch(`${base}/${asset}`);
      assert.equal(response.status,200,asset);
      assert.match(response.headers.get('content-type'),/javascript/);
      assert.ok((await response.text()).length>0);
    }
    client=new Client({name:'isolated-integration-test',version:'1'});
    await client.connect(new StreamableHTTPClientTransport(new URL(`${base}/mcp`),{requestInit:{headers:{Authorization:`Bearer ${token}`}}}));
    const call=async(name,args={})=>client.callTool({name,arguments:args});
    const ok=async(name,args={})=>{const result=await call(name,args);assert.equal(result.isError,undefined,JSON.stringify(result));return result.structuredContent.data;};
    const schedule=await ok('get_schedule');assert.equal(schedule.enabled,false);
    const configuredSchedule=await ok('set_schedule',{revision:schedule.revision,enabled:false,interval_minutes:60,next_run_at:'2026-12-01T09:00:00.000Z'});
    assert.equal(configuredSchedule.interval_minutes,60);
    assert.equal((await call('set_schedule',{revision:schedule.revision,enabled:true,interval_minutes:60,next_run_at:'2026-12-01T09:00:00.000Z'})).structuredContent.error.code,'CONFLICT');
    const forbiddenTick=await fetch(`${base}/api/workflow/schedule/tick`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:'{}'});assert.equal(forbiddenTick.status,401);
    const searchConfig=await ok('get_search_configuration');
    assert.equal(searchConfig.value.professional_years,null);
    assert.equal(searchConfig.value.technical_degree,false);
    const savedConfig=await ok('set_search_configuration',{expected_revision:searchConfig.revision,value:{...searchConfig.value,max_required_years:2}});
    assert.equal(savedConfig.value.max_required_years,2);
    assert.equal(savedConfig.revision,searchConfig.revision+1);
    assert.equal((await call('set_search_configuration',{expected_revision:searchConfig.revision,value:searchConfig.value})).structuredContent.error.code,'CONFLICT');
    assert.equal((await call('set_search_configuration',{expected_revision:savedConfig.revision,value:{...savedConfig.value,sources:[]}})).isError,true);
    assert.equal(savedConfig.value.criteria.length,11);
    const criteria=savedConfig.value.criteria.map(rule=>rule.id==='contract'?{...rule,instruction:'Admite contrato temporal explícito.',pending:'Confirmar duración acordada'}:rule);
    const revised=await ok('set_search_configuration',{expected_revision:savedConfig.revision,value:{...savedConfig.value,criteria,fit_instruction:'Valora solo funciones y autonomía acreditadas.'}});
    assert.deepEqual(revised.value.criteria,criteria);
    const {criteria:omitted,fit_instruction:omittedFit,...legacy}=revised.value;
    const preserved=await ok('set_search_configuration',{expected_revision:revised.revision,value:legacy});
    assert.deepEqual(preserved.value.criteria,criteria);assert.equal(preserved.value.fit_instruction,'Valora solo funciones y autonomía acreditadas.');
    assert.equal((await call('set_search_configuration',{expected_revision:preserved.revision,value:{...preserved.value,fit_instruction:''}})).isError,true);
    for(const bad of [criteria.slice(1),[criteria[0],...criteria.slice(0,-1)],criteria.map(rule=>({...rule,instruction:''}))]) {
      assert.equal((await call('set_search_configuration',{expected_revision:preserved.revision,value:{...preserved.value,criteria:bad}})).isError,true);
    }
    const catalog=await ok('get_models',{});assert.ok(catalog.providers.some(item=>item.id==='codex'));
    const settings=await ok('get_settings',{include_prompt:true});
    assert.equal(settings.value.provider,'codex');
    const chosen=await ok('patch_settings',{expected_revision:settings.revision,patch:{provider:'openai',model:'chosen-test-model'}});
    assert.equal(chosen.value.provider,'openai');
    await ok('patch_settings',{expected_revision:chosen.revision,patch:{provider:'codex',model:settings.value.model}});
    Object.assign(settings,await ok('get_settings',{include_prompt:true}));
    const updated=await ok('patch_settings',{expected_revision:settings.revision,patch:{quota_spain:5,model_retries:2,model_timeout_seconds:30,public_alternatives:false}});
    assert.equal(updated.value.model_retries,2);
    assert.equal((await call('patch_settings',{expected_revision:updated.revision,patch:{model_retries:4}})).isError,true);
    assert.equal(updated.value.model_timeout_seconds,30);assert.equal(updated.value.public_alternatives,false);
    assert.equal((await call('patch_settings',{expected_revision:updated.revision,patch:{model_timeout_seconds:121}})).isError,true);
    assert.equal(updated.value.source_prompt,settings.value.source_prompt); assert.equal(updated.value.quota_spain,5);
    assert.equal((await call('patch_settings',{expected_revision:settings.revision,patch:{quota_spain:6}})).structuredContent.error.code,'CONFLICT');
    assert.equal((await call('patch_settings',{expected_revision:updated.revision,patch:{batch_size:defaults.max_openings+1}})).structuredContent.error.code,'INVALID_INPUT');
    const createdOffer=await ok('create_offer',{offer:{company:'Fixture en esquema aislado',title:'Fixture de integración',url:'https://example.test/isolated/1',availability:'abierta',review_state:'nueva',application_state:'sin_candidatura',notes:'Nota inicial'}});
    let offer=await ok('get_offer',{id:createdOffer.id});
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{notes:'Nota modificada solo en el esquema aislado'}});
    const next=await ok('get_offer',{id:offer.id}); assert.equal(next.title,offer.title); assert.equal(next.company_id,offer.company_id); assert.equal(next.application_state,'sin_candidatura');
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:offer.version,patch:{notes:'Cambio obsoleto'}})).structuredContent.error.code,'CONFLICT');
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:next.version,patch:{application_state:'enviada'}})).structuredContent.error.code,'INVALID_INPUT');
    await ok('patch_offer',{id:offer.id,expected_version:next.version,patch:{application_state:'enviada',reason:'Prueba aislada de historial'}});
    offer=await ok('get_offer',{id:offer.id});
    assert.ok(offer.submitted_at);
    assert.equal(offer.submitted_at,offer.state_changed_at);
    assert.ok(offer.state_changed_at);
    const changedAt=offer.state_changed_at;
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{submitted_at:'2026-11-10T00:00:00.000Z'}});
    offer=await ok('get_offer',{id:offer.id});
    assert.equal(offer.submitted_at,'2026-11-10T00:00:00.000Z'); assert.equal(offer.state_changed_at,changedAt);
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{notes:'Conservar fecha'}});
    offer=await ok('get_offer',{id:offer.id});
    assert.equal(offer.submitted_at,'2026-11-10T00:00:00.000Z'); assert.equal(offer.state_changed_at,changedAt);
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{application_state:'rechazada_empresa',reason:'Rechazo en esquema aislado'}});
    offer=await ok('get_offer',{id:offer.id});
    assert.notEqual(offer.state_changed_at,changedAt); assert.equal(offer.submitted_at,'2026-11-10T00:00:00.000Z');
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{submitted_at:null}});
    offer=await ok('get_offer',{id:offer.id});
    const rejectionDate=offer.state_changed_at;
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{notes:'Inscripción histórica sin fecha conocida'}});
    offer=await ok('get_offer',{id:offer.id});
    assert.equal(offer.submitted_at,null); assert.equal(offer.state_changed_at,rejectionDate);
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:offer.version,patch:{application_state:'sin_candidatura',reason:'Intento inválido de borrar historial'}})).structuredContent.error.code,'INVALID_INPUT');
    await ok('add_publication',{offer_id:offer.id,url:'https://example.test/isolated/alias'});
    assert.equal((await ok('check_history',{url:'https://example.test/isolated/alias'})).excluded,true);
    const batchUrls=['https://example.test/isolated/alias?utm_source=test','https://example.test/not-applied'];
    assert.deepEqual(await ok('check_offers_batch',{urls:batchUrls}),{results:batchUrls.map((url,index)=>({url,applied:index===0}))});
    assert.equal((await call('check_offers_batch',{urls:[]})).isError,true);
    const identityUrls=[
      'https://www.infojobs.net/a/dev/of-i123abc?utm_source=x',
      'https://es.linkedin.com/jobs/view/dev-123456',
      'https://apply.workable.com/a/j/AB12/',
      'https://job-boards.greenhouse.io/a/jobs/123',
      'https://jobs.lever.co/a/12345678-abcd-1234-abcd-123456789abc',
      'https://api.smartrecruiters.com/v1/companies/a/postings/123',
      'https://emploive.com/home/jobs/8612917',
      'https://example.test/careers',
      'https://infojobs.net.evil.com/of-i123'
    ];
    for(const url of identityUrls) {
      assert.equal((await admin.query('SELECT publication_identity($1) AS identity',[url])).rows[0].identity,publicationIdentity(url));
    }
    await ok('add_publication',{offer_id:offer.id,url:'https://es.linkedin.com/jobs/view/dev-123456'});
    assert.deepEqual(await ok('check_offers_batch',{urls:['https://www.linkedin.com/jobs/view/123456','https://www.linkedin.com/jobs/view/123457']}),{results:[{url:'https://www.linkedin.com/jobs/view/123456',applied:true},{url:'https://www.linkedin.com/jobs/view/123457',applied:false}]});
    await admin.query("DELETE FROM publications WHERE url='https://es.linkedin.com/jobs/view/dev-123456'");
    const action=await ok('create_action',{offer_id:offer.id,description:'Fixture aislada',state:'pendiente'});
    const actions=await ok('list_actions',{offer_id:offer.id});
    await ok('update_action',{offer_id:offer.id,action_id:action.id,expected_version:actions.items[0].version,description:'Fixture aislada',state:'completada'});
    assert.equal((await ok('list_actions',{offer_id:offer.id})).items[0].state,'completada');
    const first=await ok('list_offers',{limit:1}); assert.equal(first.items.length,1);
    assert.deepEqual(first.items[0].publications.map(item=>item.url),['https://example.test/isolated/1','https://example.test/isolated/alias']); assert.equal(first.next_offset,1);
    assert.equal((await ok('list_offers',{limit:1,offset:1})).items.length,0);
    assert.equal((await ok('list_offers',{q:'sin coincidencia en el esquema aislado'})).items.length,0);
    assert.equal((await ok('list_companies')).items.length,1);
    assert.equal((await ok('list_publications',{offer_id:offer.id})).items.length,2);
    assert.equal((await ok('list_offer_events',{offer_id:offer.id,limit:1})).items.length,1);
    const duplicate=await ok('create_offer',{offer:{company:offer.company,title:offer.title,url:'https://example.test/duplicate',availability:'desconocida',review_state:'nueva',application_state:'sin_candidatura',notes:'Nota del duplicado'}});
    assert.equal((await ok('check_offers_batch',{urls:['https://example.test/duplicate']})).results[0].applied,false);
    const duplicateOffer=await ok('get_offer',{id:duplicate.id});
    const sourceAction=await ok('create_action',{offer_id:duplicate.id,description:'Acción duplicada',state:'pendiente'});
    const mergeSource=await ok('get_offer',{id:duplicate.id});
    offer=await ok('get_offer',{id:offer.id});
    const targetBeforeMerge=offer;
    assert.equal((await call('merge_offers',{target_id:offer.id,source_id:duplicate.id,expected_version:offer.version,source_version:duplicateOffer.version,application_from:'target',reason:'Mismo proceso confirmado'})).structuredContent.error.code,'CONFLICT');
    assert.equal((await call('merge_offers',{target_id:offer.id,source_id:duplicate.id,expected_version:offer.version,source_version:mergeSource.version,application_from:'source',reason:'No se permite borrar candidatura previa'})).structuredContent.error.code,'CONFLICT');
    await admin.query("INSERT INTO applications(id,opportunity_id,state,submitted_at) VALUES($1,$2,'enviada','2026-11-09T00:00:00Z')",[randomUUID(),duplicate.id]);
    await ok('merge_offers',{target_id:offer.id,source_id:duplicate.id,expected_version:offer.version,source_version:mergeSource.version,application_from:'source',reason:'Mismo proceso confirmado; conservar inscripción acreditada del duplicado'});
    const merged=await ok('get_offer',{id:offer.id});
    assert.equal(merged.application_state,'enviada');assert.equal(merged.submitted_at,'2026-11-09T00:00:00.000Z');
    assert.equal(merged.state_changed_at,mergeSource.state_changed_at);assert.match(merged.notes,/Nota del duplicado/);
    assert.equal((await ok('list_publications',{offer_id:offer.id})).items.length,3);
    assert.ok((await ok('list_actions',{offer_id:offer.id})).items.some(item=>item.id===sourceAction.id));
    assert.equal((await ok('check_history',{url:'https://example.test/duplicate'})).matches[0].id,offer.id);
    assert.equal((await ok('check_history',{url:'https://example.test/duplicate'})).excluded,true);
    assert.equal((await ok('check_offers_batch',{urls:['https://example.test/duplicate']})).results[0].applied,true);
    assert.equal((await ok('list_offers')).items.length,1);
    assert.equal((await admin.query('SELECT count(*)::int AS n FROM opportunities WHERE id=$1',[duplicate.id])).rows[0].n,1);
    const mergedEvents=(await ok('list_offer_events',{offer_id:offer.id})).items;
    const mergeEvent=mergedEvents.find(event=>event.kind==='offers_merged');
    assert.equal(mergeEvent.value.applications.length,2);assert.ok(mergeEvent.value.applications.some(item=>item.state==='rechazada_empresa'));
    assert.ok(mergedEvents.some(event=>event.opportunity_id===duplicate.id));
    const archived=await fetch(`${base}/api/offers/${duplicate.id}`);assert.equal(archived.status,410);assert.equal((await archived.json()).target_id,offer.id);
    const archivedMcp=await call('get_offer',{id:duplicate.id});assert.equal(archivedMcp.structuredContent.error.code,'MERGED');assert.equal(archivedMcp.structuredContent.error.target_id,offer.id);
    assert.equal((await call('patch_offer',{id:duplicate.id,expected_version:mergeSource.version,patch:{notes:'No se edita el archivo'}})).isError,true);
    const newer=await ok('create_offer',{offer:{company:offer.company,title:offer.title,url:'https://example.test/newer-duplicate',availability:'desconocida',review_state:'nueva',application_state:'sin_candidatura',notes:'Nota de la fusión posterior'}});
    const newerState=await ok('get_offer',{id:newer.id}),targetAfterMerge=await ok('get_offer',{id:offer.id});
    await ok('merge_offers',{target_id:offer.id,source_id:newer.id,expected_version:targetAfterMerge.version,source_version:newerState.version,application_from:'target',reason:'Misma convocatoria confirmada en otra URL'});
    const stack=await ok('list_offer_merges',{offer_id:offer.id});
    assert.equal(stack.items.length,2);assert.equal(stack.items[0].source_id,newer.id);assert.equal(stack.items[0].undoable,true);assert.equal(stack.items[1].undoable,false);
    assert.equal((await call('unmerge_offer',{target_id:offer.id,source_id:duplicate.id,expected_version:(await ok('get_offer',{id:offer.id})).version,source_version:mergeSource.version,reason:'Prueba de que se respeta el orden inverso'})).structuredContent.error.code,'CONFLICT');
    const latest=await ok('get_offer',{id:offer.id});
    await ok('unmerge_offer',{target_id:offer.id,source_id:newer.id,expected_version:latest.version,source_version:newerState.version,reason:'La última asociación se añadió por error'});
    let remaining=await ok('list_offer_merges',{offer_id:offer.id});
    assert.equal(remaining.items.length,1);assert.equal(remaining.items[0].source_id,duplicate.id);assert.equal(remaining.items[0].undoable,true);
    const beforeLastUndo=await ok('get_offer',{id:offer.id});
    await ok('unmerge_offer',{target_id:offer.id,source_id:duplicate.id,expected_version:beforeLastUndo.version,source_version:remaining.items[0].source_version,reason:'Se confirmó que eran convocatorias distintas'});
    const restoredTarget=await ok('get_offer',{id:offer.id}),restoredSource=await ok('get_offer',{id:duplicate.id});
    assert.equal(restoredTarget.notes,targetBeforeMerge.notes);assert.equal(restoredTarget.application_state,targetBeforeMerge.application_state);assert.equal(restoredTarget.submitted_at,targetBeforeMerge.submitted_at);
    assert.equal(restoredSource.application_state,'enviada');assert.equal(restoredSource.submitted_at,'2026-11-09T00:00:00.000Z');assert.equal(restoredSource.notes,'Nota del duplicado');
    assert.equal((await ok('list_publications',{offer_id:offer.id})).items.length,2);assert.equal((await ok('list_publications',{offer_id:duplicate.id})).items.length,1);
    assert.ok((await ok('list_actions',{offer_id:duplicate.id})).items.some(item=>item.id===sourceAction.id));
    assert.equal((await ok('list_offer_merges',{offer_id:offer.id})).items.length,0);
    assert.equal((await ok('list_offer_events',{offer_id:offer.id})).items.some(event=>event.kind==='offers_unmerged'),true);
    assert.equal((await ok('check_history',{url:'https://example.test/duplicate'})).matches[0].id,duplicate.id);

    assert.equal((await call('get_run',{id:randomUUID()})).structuredContent.error.code,'NOT_FOUND');
    assert.equal((await call('start_run',{request_id:randomUUID(),module:'contract',text:'Fixture nunca enviada al modelo: admisión pausada'})).structuredContent.error.code,'CONFLICT');
    assert.equal((await ok('list_runs')).items.length,0);
    const workflow=await ok('get_workflow');
    assert.equal(workflow.modules.find(module=>module.id==='extraction').tasks.length,15);
    assert.equal((await call('start_run',{request_id:randomUUID(),module:'extraction',text:'Fixture aislada: no se ejecuta con admisión pausada'})).structuredContent.error.code,'CONFLICT');
    await admin.query(`SET search_path TO ${schema}`);
    const runId=randomUUID();
    await admin.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'extraction','succeeded',1,'{}','Fixture solo en esquema aislado')",[runId]);
    await admin.query("INSERT INTO workflow_tasks(run_id,task_id,position,status,result) VALUES($1,'company',1,'succeeded',$2)",[runId,{state:'desconocido',value:'desconocido',evidence:''}]);
    const run=await ok('get_run',{id:runId});
    assert.equal(run.tasks[0].task_id,'company'); assert.equal(run.tasks[0].result.state,'desconocido');
    assert.equal(run.input_text,undefined); assert.equal(run.settings_snapshot,undefined);
    await admin.query("INSERT INTO workflow_tasks(run_id,task_id,position,status) SELECT $1,'campo_'||n,n,'pending' FROM generate_series(2,32) n",[runId]);
    const runPage=await ok('get_run',{id:runId});assert.equal(runPage.tasks.length,25);assert.equal(runPage.task_page.total,32);assert.equal(runPage.task_page.next_offset,25);assert.equal(runPage.task_page.counts.pending,31);
    const taskPage=await ok('list_run_tasks',{run_id:runId,limit:10,offset:20});assert.equal(taskPage.items.length,10);assert.equal(taskPage.items[0].position,21);assert.equal(taskPage.next_offset,30);
    const filtered=await ok('list_run_tasks',{run_id:runId,task_status:'pending',limit:10});assert.equal(filtered.items[0].position,2);assert.equal(filtered.filtered_total,31);assert.equal(filtered.counts.succeeded,1);
    const emptyTasks=await ok('list_run_tasks',{run_id:runId,offset:100});assert.equal(emptyTasks.items.length,0);assert.equal(emptyTasks.total,32);assert.equal(emptyTasks.next_offset,null);
    assert.equal((await call('list_run_tasks',{run_id:randomUUID()})).structuredContent.error.code,'NOT_FOUND');
    assert.equal((await fetch(`${base}/api/workflow/runs/${runId}/tasks?task_status=inventado`)).status,400);
    assert.equal((await fetch(`${base}/api/workflow/runs/${runId}/tasks?limit=101`)).status,400);
    const searchRun=randomUUID(),searchCandidate=randomUUID();
    await admin.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'search','succeeded',1,'{}','Prueba aislada de paginación')",[searchRun]);
    await admin.query("INSERT INTO search_candidates(id,run_id,source,url,company,title,hint) VALUES($1,$2,'arbeitnow','https://example.test/pagination','Empresa aislada','Developer','{}')",[searchCandidate,searchRun]);
    await admin.query("INSERT INTO search_steps(id,run_id,candidate_id,task_key,kind,priority,status,created_at) VALUES($1,$2,$3,'1','read',10,'pending','2026-11-13T10:00:00Z'),($4,$2,$3,'2','extract_company',10,'unknown','2026-11-13T10:01:00Z')",[randomUUID(),searchRun,searchCandidate,randomUUID()]);
    const searchTasks=await ok('list_run_tasks',{run_id:searchRun,task_status:'unknown'});assert.equal(searchTasks.items.length,1);assert.equal(searchTasks.items[0].position,2);assert.equal(searchTasks.items[0].candidate_id,searchCandidate);assert.equal(searchTasks.total,2);assert.equal(searchTasks.next_offset,null);

    artifactRun=randomUUID();
    const artifactDirectory=new URL(`../reports/${artifactRun}/`,import.meta.url);
    await admin.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'search','running',1,$2,'Prueba aislada de recuperación del informe')",[artifactRun,{...defaults,search_config:searchConfig}]);
    const artifactStep=randomUUID();
    await admin.query("INSERT INTO search_steps(id,run_id,task_key,kind,priority,status) VALUES($1,$2,'audit:fixture','audit',1,'pending')",[artifactStep,artifactRun]);
    await admin.query('INSERT INTO search_run_state(run_id,selected_step) VALUES($1,$2)',[artifactRun,artifactStep]);
    await mkdir(new URL('registro.json/',artifactDirectory),{recursive:true});
    const auditCallback=await fetch(`${base}/api/search/runs/${artifactRun}/steps/${artifactStep}`,{method:'POST',headers:{Authorization:`Bearer ${token}-n8n`,'Content-Type':'application/json'},body:JSON.stringify({kind:'audit',execution_id:'1'})});
    assert.equal(auditCallback.status,200);assert.equal((await auditCallback.json()).status,'succeeded');
    const pendingReport=await ok('get_run',{id:artifactRun});
    assert.equal(pendingReport.status,'succeeded');assert.ok(pendingReport.search.report_files_error);
    assert.equal(pendingReport.search.report_files_revision,0);
    const failedDownload=await call('get_search_report',{run_id:artifactRun});assert.equal(failedDownload.structuredContent.error.code,'UNAVAILABLE');
    assert.equal((await readdir(artifactDirectory)).some(name=>name.endsWith('.tmp')),false);
    await rm(new URL('registro.json/',artifactDirectory),{recursive:true});
    const recoveredReport=await ok('get_search_report',{run_id:artifactRun});assert.match(recoveredReport.content,/# Búsqueda de empleo/);
    const recoveredRun=await ok('get_run',{id:artifactRun});
    assert.equal(recoveredRun.search.report_files_error,null);assert.equal(recoveredRun.search.report_files_revision,recoveredRun.search.report_revision);
    assert.equal(recoveredRun.search.report_revision,pendingReport.search.report_revision);assert.equal(recoveredRun.tasks.length,1);assert.equal(recoveredRun.tasks[0].status,'succeeded');assert.equal(recoveredRun.status,'succeeded');
    const register=JSON.parse(await readFile(new URL('registro.json',artifactDirectory),'utf8'));assert.equal(register.report.report_revision,recoveredRun.search.report_revision);
    await rm(new URL('informe.md',artifactDirectory));
    assert.match((await ok('get_search_report',{run_id:artifactRun})).content,/# Búsqueda de empleo/);
    assert.equal((await ok('get_run',{id:artifactRun})).search.report_revision,recoveredRun.search.report_revision);

    const discovery=await (await fetch(`${base}/api/integration`)).text(); assert.equal(discovery.includes(token),false);
    assert.equal((await fetch(`${base}/mcp`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status,401);
    assert.equal((await fetch(`${base}/mcp`,{method:'POST',headers:{Origin:'https://example.test',Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:'{}'})).status,403);
  } finally {
    if(client) await client.close();
    if(child && child.exitCode===null) {child.kill();await once(child,'exit');}
    await admin.query('ROLLBACK');
    if(created) await admin.query(`DROP SCHEMA ${schema} CASCADE`);
    await admin.end();
    if(artifactRun) await rm(new URL(`../reports/${artifactRun}/`,import.meta.url),{recursive:true,force:true});
  }
});
