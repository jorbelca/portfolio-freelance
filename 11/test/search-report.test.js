import test from 'node:test';
import assert from 'node:assert/strict';
import {reportMarkdown} from '../src/search-report.js';
test('informe trazable: déficit explícito y B no presentada como recomendada',()=>{
 const text=reportMarkdown({cutoff:'2026-11-12T10:00:00Z',timezone:'Europe/Madrid',openings:1,max_openings:100,spain:1,quota_spain:13,europe:0,quota_europe:7,deficit_spain:12,deficit_europe:7,reason:'fuentes agotadas',fulfilled:false},[{id:'fixture',title:'Developer [aislado]',company:'Fixture',source:'remotive',url:'https://example.test/job',evaluation:{classification:'B',computable:true,country:'España',fit:'condicionado',pending:[{owner:'candidato',resolution:'Acreditar prácticas'}]}}]);
 assert.match(text,/Objetivo de cupos no cumplido/);assert.match(text,/España 12; Europa 7/);assert.match(text,/Fuente: remotive/);assert.match(text,/Pendiente \(candidato\)/);assert.match(text,/Developer \\\[aislado/);
});
