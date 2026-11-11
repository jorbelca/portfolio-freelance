import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import pg from 'pg';

test('migración conserva historial y separa procesos, publicaciones, candidaturas y acciones', {skip:!process.env.DATABASE_URL}, async () => {
  const client=new pg.Client({connectionString:process.env.DATABASE_URL,connectionTimeoutMillis:10000});
  await client.connect();
  try {
    await client.query('BEGIN');
    // Las fixtures viven en un esquema aislado dentro de una transacción siempre revertida.
    const schema='test_'+randomUUID().replaceAll('-','');
    await client.query(`CREATE SCHEMA ${schema}`);
    await client.query(`SET LOCAL search_path TO ${schema}`);
    await client.query((await readFile(new URL('../sql/001.sql',import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,''));
    const defaults=JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'));
    await client.query('INSERT INTO settings(id,value,revision) VALUES(1,$1,7)',[defaults]);
    const id=randomUUID(), second=randomUUID();
    await client.query("INSERT INTO offers(id,company,title,url,status,notes,next_action,follow_up,version) VALUES($1,'Fixture aislada','Dev','https://example.test/jobs/1','cerrada','Nota','Revisar','2026-11-12',3)",[id]);
    await client.query("INSERT INTO offers(id,company,title,status) VALUES($1,'Fixture aislada','Dev','rechazada')",[second]);
    await client.query('INSERT INTO offer_events(offer_id,value) VALUES($1,$2)',[id,{status:'aplicada'}]);
    await client.query(await readFile(new URL('../sql/002.sql',import.meta.url),'utf8'));
    const summary=(await client.query('SELECT * FROM offer_summary WHERE id=$1',[id])).rows[0];
    assert.equal(summary.version,3);
    assert.equal(summary.notes,'Nota');
    assert.equal(summary.availability,'cerrada');
    assert.equal(summary.application_state,'enviada');
    assert.equal(summary.excluded,true);
    assert.equal((await client.query('SELECT revision FROM settings_summary')).rows[0].revision,7);
    assert.equal((await client.query('SELECT count(*)::integer AS n FROM companies')).rows[0].n,2);
    assert.equal((await client.query('SELECT application_state FROM offer_summary WHERE id=$1',[second])).rows[0].application_state,'rechazada_sin_detalle');
    await client.query("UPDATE opportunities SET availability='abierta' WHERE id=$1",[id]);
    assert.equal((await client.query('SELECT excluded FROM offer_summary WHERE id=$1',[id])).rows[0].excluded,true);
    const sourceId=(await client.query('SELECT source_id FROM publications WHERE opportunity_id=$1',[id])).rows[0].source_id;
    await client.query("INSERT INTO publications(id,opportunity_id,source_id,url) VALUES($1,$2,$3,'https://example.test/alias')",[randomUUID(),id,sourceId]);
    assert.equal((await client.query("SELECT s.excluded FROM offer_summary s JOIN publications p ON p.opportunity_id=s.id WHERE p.url='https://example.test/alias'")).rows[0].excluded,true);
    await client.query("INSERT INTO follow_up_actions(id,opportunity_id,description,due_on) VALUES($1,$2,'Otra acción','2026-11-12')",[randomUUID(),id]);
    assert.equal((await client.query('SELECT count(*)::integer AS n FROM follow_up_actions WHERE opportunity_id=$1',[id])).rows[0].n,2);
    for (const query of [
      {text:"INSERT INTO publications(id,opportunity_id,source_id,url,is_primary) VALUES($1,$2,$3,'https://example.test/primary',true)",values:[randomUUID(),id,sourceId]},
      {text:"UPDATE follow_up_actions SET state='completada' WHERE opportunity_id=$1",values:[id]},
      {text:"UPDATE opportunities SET availability='inexistente' WHERE id=$1",values:[id]},
      {text:'UPDATE search_settings SET batch_size=max_openings+1',values:[]}
    ]) {
      await client.query('SAVEPOINT invalid_input');
      await assert.rejects(client.query(query));
      await client.query('ROLLBACK TO SAVEPOINT invalid_input');
    }
    assert.equal((await client.query('SELECT count(*)::integer AS n FROM legacy_offers')).rows[0].n,2);
    assert.equal((await client.query('SELECT count(*)::integer AS n FROM opportunity_events')).rows[0].n,1);
    await client.query(await readFile(new URL('../sql/003.sql',import.meta.url),'utf8'));
    await client.query(await readFile(new URL('../sql/004.sql',import.meta.url),'utf8'));
    const dates=(await client.query('SELECT submitted_at,state_changed_at FROM offer_summary WHERE id=$1',[id])).rows[0];
    assert.equal(dates.submitted_at,null); assert.equal(dates.state_changed_at,null);
    assert.equal((await client.query('SELECT enabled FROM workflow_control')).rows[0].enabled,false);
    const run=randomUUID();
    await client.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'contract','running',7,$2,'Prueba aislada')",[run,defaults]);
    await client.query('SAVEPOINT simultaneous_run');
    await assert.rejects(client.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'contract','queued',7,$2,'Prueba aislada')",[randomUUID(),defaults]));
    await client.query('ROLLBACK TO SAVEPOINT simultaneous_run');
    await client.query('UPDATE search_settings SET model=$1,revision=revision+1',['otro-modelo']);
    assert.equal((await client.query('SELECT settings_snapshot,settings_revision FROM workflow_runs WHERE id=$1',[run])).rows[0].settings_snapshot.model,defaults.model);
    await client.query("UPDATE workflow_runs SET status='unknown' WHERE id=$1",[run]);
    await client.query('SAVEPOINT uncertain_run');
    await assert.rejects(client.query("INSERT INTO workflow_runs(id,module,status,settings_revision,settings_snapshot,input_text) VALUES($1,'contract','queued',7,$2,'Prueba aislada')",[randomUUID(),defaults]));
    await client.query('ROLLBACK TO SAVEPOINT uncertain_run');
  } finally {
    await client.query('ROLLBACK');
    await client.end();
  }
});
