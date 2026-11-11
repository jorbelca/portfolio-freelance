import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import pg from 'pg';

test('tareas persistentes: orden, exclusión mutua, caché, fallo parcial y recuperación',{skip:!process.env.DATABASE_URL,timeout:60000},async()=>{
  const admin=new pg.Client({connectionString:process.env.DATABASE_URL});
  const schema='test_tasks_'+randomUUID().replaceAll('-','');
  let pool,created=false;
  await admin.connect();
  const previous=process.env.DATABASE_URL;
  try {
    await admin.query(`CREATE SCHEMA ${schema}`);created=true;
    await admin.query(`SET search_path TO ${schema}`);
    for (const file of ['001.sql','002.sql','003.sql','004.sql','005.sql']) {
      await admin.query((await readFile(new URL(`../sql/${file}`,import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,''));
      if (file==='001.sql') await admin.query('INSERT INTO settings(id,value) VALUES(1,$1)',[JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'))]);
    }
    const scoped=new URL(previous);scoped.searchParams.set('options',`-c search_path=${schema}`);process.env.DATABASE_URL=scoped.href;
    const workflow=await import('../src/workflow.js');
    ({pool}=await import('../src/db.js'));
    const id=randomUUID(),text='Documento aislado. Empresa de prueba.';
    await admin.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'extraction','running',1,$2,$3)",[id,{model:''},text]);
    for (const [index,task] of ['company','title','country'].entries()) await admin.query('INSERT INTO workflow_tasks(run_id,task_id,position) VALUES($1,$2,$3)',[id,task,index+1]);
    let calls=0;
    const extract=async()=>{calls++;return {value:'Empresa de prueba',evidence:'Empresa de prueba',state:'acreditado'};};
    await assert.rejects(workflow.runTask(id,'title',undefined,extract),{status:409});
    await assert.rejects(workflow.runTask(id,'company','texto diferente',extract),{status:409});
    await assert.rejects(workflow.finishRun(id,'9'),{status:409});
    let release,started;
    const waiting=new Promise(resolve=>{started=resolve;});
    const first=workflow.runTask(id,'company',undefined,async()=>{started();await new Promise(resolve=>{release=resolve;});return extract();});
    await waiting;
    await assert.rejects(workflow.runTask(id,'company',undefined,extract),{status:409});
    release(); assert.equal((await first).status,'succeeded');
    assert.equal((await workflow.runTask(id,'company',undefined,extract)).result.value,'Empresa de prueba');
    assert.equal(calls,1);
    const invalid=await workflow.runTask(id,'title',undefined,async()=>({value:'Inventado',evidence:'No existe en el texto',state:'acreditado'}));
    assert.equal(invalid.status,'failed'); assert.equal(invalid.result,null);
    assert.equal((await workflow.runTask(id,'country',undefined,async()=>({state:'desconocido',value:'desconocido',evidence:''}))).status,'succeeded');
    assert.equal((await workflow.finishRun(id,'9')).status,'failed');
    assert.equal((await workflow.finishRun(id,'9')).status,'failed');
    const run=(await admin.query('SELECT * FROM workflow_runs WHERE id=$1',[id])).rows[0];
    assert.equal(run.result.company.value,'Empresa de prueba'); assert.equal(run.result.title.state,'error');
    const second=randomUUID();
    await admin.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'contract','running',1,'{}','Documento aislado')",[second]);
    await admin.query("INSERT INTO workflow_tasks(run_id,task_id,position,status) VALUES($1,'contract',1,'running')",[second]);
    await workflow.recoverRuns();
    assert.equal((await admin.query('SELECT status FROM workflow_tasks WHERE run_id=$1',[second])).rows[0].status,'unknown');
    await assert.rejects(workflow.runTask(second,'contract',undefined,extract),{status:409});
    await assert.rejects(workflow.finishRun(second,'10'),{status:409});
  } finally {
    process.env.DATABASE_URL=previous;
    if (pool) await pool.end();
    if (created) await admin.query(`DROP SCHEMA ${schema} CASCADE`);
    await admin.end();
  }
});
