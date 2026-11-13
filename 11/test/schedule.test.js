import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir} from 'node:fs/promises';
import pg from 'pg';
test('programación persistente: revisión, pausa, historial, exclusión mutua y reinicio sin ráfaga',{skip:!process.env.DATABASE_URL,timeout:120000},async()=>{
 const admin=new pg.Client({connectionString:process.env.DATABASE_URL}),schema='test_schedule_'+randomUUID().replaceAll('-','');
 const previous=process.env.DATABASE_URL;let pool;
 await admin.connect();
 try {
  await admin.query(`CREATE SCHEMA ${schema}`);await admin.query(`SET search_path TO ${schema}`);
  for(const file of (await readdir(new URL('../sql/',import.meta.url))).filter(file=>/^\d+\.sql$/.test(file)).sort()) {
  await admin.query((await readFile(new URL(`../sql/${file}`,import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,''));
  if(file==='001.sql') await admin.query('INSERT INTO settings(id,value) VALUES(1,$1)',[JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'))]);
  }
  const scoped=new URL(previous);scoped.searchParams.set('options',`-c search_path=${schema}`);process.env.DATABASE_URL=scoped.href;
  ({pool}=await import('../src/db.js'));
  const {getSchedule,saveSchedule,tickSchedule}=await import('../src/schedule.js');
  const initial=await getSchedule();assert.equal(initial.enabled,false);
  assert.equal((await tickSchedule()).status,'disabled');
  let config={revision:initial.revision,enabled:true,interval_minutes:15,next_run_at:'2020-01-01T00:00:00.000Z'};
  const saved=await saveSchedule(config);assert.equal(saved.revision,2);
  await assert.rejects(saveSchedule(config),{status:409});
  await assert.rejects(saveSchedule({...config,revision:2,interval_minutes:0}));
  assert.equal((await tickSchedule()).status,'paused');
  await admin.query('UPDATE workflow_control SET enabled=true');
  assert.equal((await tickSchedule()).status,'history_pending');
  await admin.query('UPDATE search_settings SET history_ready=true');
  await admin.query('UPDATE search_source_settings SET enabled=false');
  assert.equal((await tickSchedule()).status,'configuration_error');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM workflow_runs')).rows[0].n,0);
  assert.equal(new Date((await getSchedule()).next_run_at).getUTCFullYear(),2020);
  await admin.query("UPDATE search_source_settings SET enabled=(source='arbeitnow')");
  const ticks=await Promise.all([tickSchedule(),tickSchedule()]);
  assert.deepEqual(ticks.map(t=>t.status).sort(),['not_due','started']);
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM workflow_runs')).rows[0].n,1);
  const after=await getSchedule();assert.equal(after.revision,2);assert.ok(after.last_run_id);
  const run=(await admin.query('SELECT * FROM workflow_runs')).rows[0];assert.equal(run.status,'running');assert.equal(run.settings_snapshot.model_timeout_seconds,120);
  const seconds=(new Date(after.next_run_at)-new Date(run.started_at))/1000;assert.equal(seconds,900);
  await admin.query("UPDATE workflow_schedule SET next_run_at=now()-interval '3 days'");
  assert.equal((await tickSchedule()).status,'busy');
  await admin.query("UPDATE workflow_runs SET status='unknown'");assert.equal((await tickSchedule()).status,'busy');
  await admin.query("UPDATE workflow_runs SET status='failed'");
  assert.equal((await tickSchedule()).status,'started');assert.equal((await tickSchedule()).status,'not_due');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM workflow_runs')).rows[0].n,2);
  config={revision:after.revision,enabled:false,interval_minutes:60,next_run_at:new Date().toISOString()};
  await saveSchedule(config);assert.equal((await tickSchedule()).status,'disabled');
 } finally {
  if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();process.env.DATABASE_URL=previous;
 }
});
