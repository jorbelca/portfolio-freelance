import test from 'node:test';
import assert from 'node:assert/strict';
import {reportMarkdown,candidateTotals} from '../src/search-report.js';
test('informe trazable: déficit explícito y B no presentada como recomendada',()=>{
 const text=reportMarkdown({cutoff:'2026-11-12T10:00:00Z',timezone:'Europe/Madrid',openings:1,max_openings:100,spain:1,quota_spain:13,europe:0,quota_europe:7,deficit_spain:12,deficit_europe:7,reason:'fuentes agotadas',fulfilled:false},[{id:'fixture',title:'Developer [aislado]',company:'Fixture',source:'remotive',url:'https://example.test/job',evaluation:{classification:'B',computable:true,country:'España',fit:'condicionado',fit_explanation:'Depende de las prácticas.',fit_evidence:'Se admiten prácticas',pending:[{owner:'candidato',resolution:'Acreditar prácticas'}]}}]);
 assert.match(text,/Objetivo de cupos no cumplido/);assert.match(text,/España 12; Europa 7/);assert.match(text,/Fuente: remotive/);assert.match(text,/Pendiente \(candidato\)/);assert.match(text,/Depende de las prácticas/);assert.match(text,/Se admiten prácticas/);assert.match(text,/Developer \\\[aislado/);
});

test('totales distinguen B computables, desconocidos y mayoría de encajes débiles sin contar C',()=>{
 const rows=[
  {evaluation:{classification:'A',computable:true,fit:'débil'}},
  {evaluation:{classification:'B',computable:true,fit:'débil'}},
  {evaluation:{classification:'B',computable:true,fit:'favorable'}},
  {evaluation:{classification:'B',computable:false,fit:'favorable'}},
  {evaluation:{classification:'C',computable:false,fit:'débil'}},
  {evaluation:null}
 ];
 assert.deepEqual(candidateTotals(rows),{classes:{A:1,B:3,C:1,pista:1},computable:3,b_computable:2,b_not_computable:1,fit:{favorable:1,condicionado:0,'débil':2,desconocido:0}});
 const report={cutoff:'2026-11-13T10:00:00Z',timezone:'Europe/Madrid',openings:5,max_openings:100,spain:3,quota_spain:13,europe:0,quota_europe:7,deficit_spain:10,deficit_europe:7,reason:'fuentes agotadas',fulfilled:false};
 const candidates=rows.map((row,index)=>({...row,id:String(index),title:'Developer',company:'Empresa',source:'corporativa',url:'https://example.test/job',checked_at:'2026-11-13T10:02:00Z'}));
 candidates[4].evaluation.exclusions=[{rule:'age',evidence:'Fecha | antigua'}];
 const text=reportMarkdown(report,candidates);
 assert.match(text,/Total computable: 3\/20/);assert.match(text,/B computables: 2; B no computables: 1/);
 assert.match(text,/Predominan los encajes débiles/);assert.match(text,/\*\*B no computable\*\*/);
 assert.match(text,/\| Puesto · empresa \| Causa \| Evidencia \| Fuente \|/);
 assert.ok(text.includes('Fecha \\| antigua'));assert.match(text,/Comprobada: 2026-11-13T10:02:00Z/);
 assert.equal(candidateTotals([]).computable,0);
});
