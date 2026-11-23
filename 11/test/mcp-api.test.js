import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,mkdir,rm,readdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import net from 'node:net';
import pg from 'pg';
import {publicationIdentity} from '../public/identity.js';
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
    for(const asset of ['app.js','offer-state.js','workflow-state.js','postulations.js','identity.js']) {
      const response=await fetch(`${base}/${asset}`);
      assert.equal(response.status,200,asset);
      assert.match(response.headers.get('content-type'),/javascript/);
      assert.ok((await response.text()).length>0);
    }
    client=new Client({name:'isolated-integration-test',version:'1'});
    await client.connect(new StreamableHTTPClientTransport(new URL(`${base}/mcp`),{requestInit:{headers:{Authorization:`Bearer ${token}`}}}));
    const call=async(name,args={})=>client.callTool({name,arguments:args});
    const ok=async(name,args={})=>{const result=await call(name,args);assert.equal(result.isError,undefined,JSON.stringify(result));return result.structuredContent.data;};
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
    const rejectionCatalog=await ok('list_rejection_reasons');
    assert.ok(rejectionCatalog.items.some(item=>item.name==='Motivo no comunicado'));
    const cause=await ok('create_rejection_reason',{name:'Horario incompatible'});
    assert.deepEqual(await ok('create_rejection_reason',{name:'  horario  incompatible  '}),cause);
    const causePatch={rejection_reason_id:cause.id};
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:offer.version,patch:causePatch})).structuredContent.error.code,'INVALID_INPUT');
    const rejection={application_state:'rechazada_empresa',reason:'Rechazo en esquema aislado'};
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:offer.version,patch:{...rejection,rejection_reason_id:randomUUID()}})).structuredContent.error.code,'INVALID_INPUT');
    assert.equal((await call('patch_offer',{id:offer.id,expected_version:offer.version,patch:rejection})).structuredContent.error.code,'INVALID_INPUT');
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{...rejection,...causePatch}});
    assert.equal((await ok('get_offer',{id:offer.id})).rejection_reason_id,cause.id);
    assert.equal((await ok('list_offers',{application_state:'rechazada_empresa'})).items.find(item=>item.id===offer.id).rejection_reason,cause.name);
    offer=await ok('get_offer',{id:offer.id});
    assert.notEqual(offer.state_changed_at,changedAt); assert.equal(offer.submitted_at,'2026-11-10T00:00:00.000Z');
    await ok('patch_offer',{id:offer.id,expected_version:offer.version,patch:{submitted_at:null}});
    assert.equal((await ok('get_offer',{id:offer.id})).rejection_reason,cause.name);
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
    const workdaySaved='https://juliusbaer.wd3.myworkdayjobs.com/en-US/External/job/Junior-Frontend-Engineer-100---f-m-d-_r-20206-1';
    const workdayVariant='https://juliusbaer.wd3.myworkdayjobs.com/External/job/Madrid/Junior-Frontend-Engineer-100---f-m-d-_r-20206-1?utm_source=spain-devjobs.com&utm_medium=job_board';
    const indraSaved='https://careers.indragroup.com/Minsait/job/Madrid-Desarrolladora-Junior-Java-MD/978237755/';
    const indraVariant=indraSaved.replace('/Minsait/','/');
    const indraUrls=[indraVariant,`${indraVariant.slice(0,-1)}?utm_source=job_board&source=search#details`,indraVariant.replace('978237755','978237756'),indraVariant.replace('careers.indragroup.com','jobs.example.test')];
    const euresSaved='https://europa.eu/eures/portal/jv-se/jv-details/NjM3MTAyNSAxMjE';
    const euresVariant=euresSaved+'?jvDisplayLanguage=sv&lang=en';
    const identityUrls=[
      euresSaved,
      euresVariant,
      'https://www.infojobs.net/a/dev/of-i123abc?utm_source=x',
      'https://es.linkedin.com/jobs/view/dev-123456',
      'https://apply.workable.com/a/j/AB12/',
      'https://job-boards.greenhouse.io/a/jobs/123',
      'https://jobs.lever.co/a/12345678-abcd-1234-abcd-123456789abc',
      'https://api.smartrecruiters.com/v1/companies/a/postings/123',
      'https://emploive.com/home/jobs/8612917',
      workdaySaved,
      workdayVariant,
      indraSaved,
      ...indraUrls,
      'https://example.test/careers',
      'https://infojobs.net.evil.com/of-i123'
    ];
    for(const url of identityUrls) {
      assert.equal((await admin.query('SELECT publication_identity($1) AS identity',[url])).rows[0].identity,publicationIdentity(url));
    }
    await ok('add_publication',{offer_id:offer.id,url:'https://es.linkedin.com/jobs/view/dev-123456'});
    assert.deepEqual(await ok('check_offers_batch',{urls:['https://www.linkedin.com/jobs/view/123456','https://www.linkedin.com/jobs/view/123457']}),{results:[{url:'https://www.linkedin.com/jobs/view/123456',applied:true},{url:'https://www.linkedin.com/jobs/view/123457',applied:false}]});
    await admin.query("DELETE FROM publications WHERE url='https://es.linkedin.com/jobs/view/dev-123456'");
    await ok('add_publication',{offer_id:offer.id,url:workdaySaved});
    const workdayUrls=[workdayVariant,workdayVariant.replace('r-20206-1','r-20206'),workdayVariant.replace('juliusbaer','another-company')];
    assert.deepEqual(await ok('check_offers_batch',{urls:workdayUrls}),{results:workdayUrls.map((url,index)=>({url,applied:index===0}))});
    assert.equal((await ok('check_history',{url:workdayVariant})).matches[0].id,offer.id);
    await admin.query('DELETE FROM publications WHERE url=$1',[workdaySaved]);
    await ok('add_publication',{offer_id:offer.id,url:indraSaved});
    assert.deepEqual(await ok('check_offers_batch',{urls:indraUrls}),{results:indraUrls.map((url,index)=>({url,applied:index<2}))});
    assert.equal((await ok('check_history',{url:indraVariant})).matches[0].id,offer.id);
    await admin.query('DELETE FROM publications WHERE url=$1',[indraSaved]);
    await ok('add_publication',{offer_id:offer.id,url:euresSaved});
    assert.equal((await ok('check_offers_batch',{urls:[euresVariant]})).results[0].applied,true);
    assert.equal((await ok('check_history',{url:euresVariant})).matches[0].id,offer.id);
    await admin.query('DELETE FROM publications WHERE url=$1',[euresSaved]);
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
    assert.equal(merged.rejection_reason_id,null);
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
    assert.equal(restoredTarget.rejection_reason_id,cause.id);
    assert.equal(restoredTarget.notes,targetBeforeMerge.notes);assert.equal(restoredTarget.application_state,targetBeforeMerge.application_state);assert.equal(restoredTarget.submitted_at,targetBeforeMerge.submitted_at);
    assert.equal(restoredSource.application_state,'enviada');assert.equal(restoredSource.submitted_at,'2026-11-09T00:00:00.000Z');assert.equal(restoredSource.notes,'Nota del duplicado');
    assert.equal((await ok('list_publications',{offer_id:offer.id})).items.length,2);assert.equal((await ok('list_publications',{offer_id:duplicate.id})).items.length,1);
    assert.ok((await ok('list_actions',{offer_id:duplicate.id})).items.some(item=>item.id===sourceAction.id));
    assert.equal((await ok('list_offer_merges',{offer_id:offer.id})).items.length,0);
    assert.equal((await ok('list_offer_events',{offer_id:offer.id})).items.some(event=>event.kind==='offers_unmerged'),true);
    assert.equal((await ok('check_history',{url:'https://example.test/duplicate'})).matches[0].id,duplicate.id);

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
