import test from 'node:test';
import assert from 'node:assert/strict';
import {previousFinalists,reusableExtraction,inheritCorrections} from '../src/continuity.js';

test('recupera finalistas una vez por proceso o URL y da prioridad a A',async()=>{
 const rows=[
  {id:'a',process_id:'process-a',source:'lever',url:'https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000001',company:'Acme',title:'Developer A',evaluation:{classification:'A'},links:[]},
  {id:'alias',process_id:'process-alias',source:'lever',url:'https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000001',company:'Acme',title:'Developer alias',evaluation:{classification:'A'},links:[]},
  {id:'b',process_id:'process-b',source:'lever',url:'https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000002',company:'Acme',title:'Developer B',evaluation:{classification:'B'},links:[]},
  {id:'c',process_id:'process-c',source:'lever',url:'https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000003',company:'Acme',title:'Developer C',evaluation:{classification:'B'},links:[]}
 ];
 let sql,values;
 const client={query:async(query,params)=>{sql=query;values=params;return {rows};}};
 const profile={queries:[{term:'Developer'}]};
 const result=await previousFinalists(client,{id:'current',settings_snapshot:{search_config:{value:profile},max_openings:2}});
 assert.match(sql,/c\.evaluation IS NOT NULL/);
 assert.deepEqual(values,['current',['%Developer%']]);
 assert.deepEqual(result.rows.map(row=>row.id),['a','b']);
 assert.equal(result.truncated,true);
});

test('reutiliza solo extracciones válidas del mismo documento y contrato',async()=>{
 const text='Desarrollador de software en Acme.';
 let result={state:'acreditado',value:'Acme',evidence:'Acme'};
 const client={query:async()=>({rows:[{id:'prior-step',result}]})};
 const run={settings_snapshot:{search_config:{value:{reuse_evidence:true}},analysis_contract:'contract-v1'}};
 const candidate={prior_candidate_id:'prior-candidate'};
 assert.equal((await reusableExtraction(client,run,candidate,'extract_company',text)).id,'prior-step');
 result={state:'acreditado',value:'Otra empresa',evidence:'No aparece'};
 assert.equal(await reusableExtraction(client,run,candidate,'extract_company',text),null);
 assert.equal(await reusableExtraction(client,{settings_snapshot:{search_config:{value:{reuse_evidence:false}},analysis_contract:'contract-v1'}},candidate,'extract_company',text),null);
});

test('hereda correcciones solo con texto idéntico, cita literal y perfil compatible',async()=>{
 const text='Publicado el 14 de noviembre. País: España. Contrato indefinido. React.';
 const profile={residence:'España',skills:[{name:'React'}]};
 const corrections=[
  {field:'publication',value:'2026-11-14',evidence:'Publicado el 14 de noviembre',reason:'Fecha visible'},
  {field:'country',value:'ES',evidence:'País: España',reason:'País visible'},
  {field:'decision:contract',value:{state:'acreditado',value:'cumple',evidence:'Contrato indefinido'},evidence:'Contrato indefinido',reason:'Contrato visible'},
  {field:'fit',value:{state:'acreditado',value:'favorable',evidence:'Python'},evidence:'Python',reason:'Cita no presente'}
 ];
 async function apply(priorText,priorProfile,currentProfile=profile) {
  const writes=[];
  const client={query:async(sql,values=[])=>{
   if(sql.startsWith('SELECT d.text')) return {rows:[{text:priorText,settings_snapshot:{search_config:{value:priorProfile}}}]};
   if(sql.startsWith('SELECT * FROM search_candidate_overrides')) return {rows:corrections};
   if(sql.startsWith('INSERT INTO search_candidate_overrides')) {writes.push({sql,values});return {rowCount:1};}
   if(sql.startsWith("INSERT INTO search_candidate_events")) {writes.push({sql,values});return {rowCount:1};}
   throw new Error(`Consulta inesperada: ${sql}`);
  }};
  await inheritCorrections(client,{settings_snapshot:{search_config:{value:currentProfile}}},{prior_candidate_id:'prior'},{text});
  return writes;
 }
 const same=await apply(text,{...profile,recover_previous:false,reuse_evidence:false,sources:[{source:'old-source'}],queries:[{term:'old-query'}],excluded_employers:['Old employer']});
 assert.deepEqual(same.filter(write=>write.sql.startsWith('INSERT INTO search_candidate_overrides')).map(write=>write.values[1]),['publication','country','decision:contract']);
 assert.deepEqual(same.at(-1).values[1].inherited,['publication','country','decision:contract']);
 const changedProfile=await apply(text,{...profile,residence:'Francia'});
 assert.deepEqual(changedProfile.filter(write=>write.sql.startsWith('INSERT INTO search_candidate_overrides')).map(write=>write.values[1]),['publication','country']);
 assert.deepEqual(changedProfile.at(-1).values[1].not_reused,['decision:contract','fit']);
 const changedText=await apply('Documento actualizado.',profile);
 assert.deepEqual(changedText.filter(write=>write.sql.startsWith('INSERT INTO search_candidate_overrides')),[]);
 assert.deepEqual(changedText.at(-1).values[1].inherited,[]);
});
