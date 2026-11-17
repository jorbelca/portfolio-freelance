import test from 'node:test';
import assert from 'node:assert/strict';
import {companyStats,companyColor} from '../public/company-heatmap.js';

test('agrupa procesos por empresa sin contar sus publicaciones y reutiliza los estados de la bandeja',()=>{
  const offer=(company_id,company,application_state,review_state='guardada')=>({company_id,company,application_state,review_state,publications:[{},{}]});
  assert.deepEqual(companyStats([
    offer('a','Empresa A','enviada'),offer('a','Empresa A','rechazada_sin_detalle'),
    offer('a','Empresa A','sin_candidatura'),offer('b','Empresa B','retirada'),
    offer('c','Empresa B','sin_candidatura','descartada')
  ]),[
    {name:'Empresa A',total:3,inscrita:1,rechazada:1,pendiente:1},
    {name:'Empresa B',total:1,inscrita:0,rechazada:1,pendiente:0},
    {name:'Empresa B',total:1,inscrita:0,rechazada:1,pendiente:0}
  ]);
  assert.deepEqual(companyStats([]),[]);
});

test('dos rechazos tienen más intensidad que uno aunque ambos sean el 100 %',()=>{
  assert.equal(companyColor({inscrita:0,rechazada:0},0,2),'rgb(180 35 35 / 0)');
  assert.equal(companyColor({inscrita:0,rechazada:1},0,2),'rgb(180 35 35 / 0.325)');
  assert.equal(companyColor({inscrita:0,rechazada:2},0,2),'rgb(180 35 35 / 0.65)');
  assert.equal(companyColor({inscrita:10,rechazada:1},0,2),companyColor({inscrita:0,rechazada:1},0,2));
  assert.equal(companyColor({rechazada:1},1,3),'rgb(180 35 35 / 0)');
  assert.equal(companyColor({rechazada:2},1,3),'rgb(180 35 35 / 0.325)');
  assert.equal(companyColor({rechazada:3},1,3),'rgb(180 35 35 / 0.65)');
  assert.equal(companyColor({rechazada:1},1,1),'rgb(180 35 35 / 0)');
  assert.equal(companyColor({rechazada:0},0,0),'rgb(180 35 35 / 0)');
});
