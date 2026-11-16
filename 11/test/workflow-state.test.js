import test from 'node:test';
import assert from 'node:assert/strict';
import {launchBlocked,taskStatusLabel} from '../public/workflow-state.js';

test('la consola exige historial solo para buscar y respeta motor, admisión y ejecuciones activas',()=>{
 const workflow={reachable:true,control:{enabled:true}},settings={history_ready:false};
 assert.equal(launchBlocked(workflow,[],settings,'search'),true);
 assert.equal(launchBlocked(workflow,[],settings,'contract'),false);
 assert.equal(launchBlocked(workflow,[],settings,'extraction'),false);
 settings.history_ready=true;
 assert.equal(launchBlocked(workflow,[],settings,'search'),false);
 for(const status of ['queued','running','unknown']) assert.equal(launchBlocked(workflow,[{status}],settings,'search'),true);
 assert.equal(launchBlocked({...workflow,reachable:false},[],settings,'search'),true);
 assert.equal(launchBlocked({...workflow,control:{enabled:false}},[],settings,'search'),true);
 assert.equal(launchBlocked(workflow,[],settings,'search',true),true);
});

test('las tareas sin resultado no rompen la vista y conservan su estado real',()=>{
 for(const result of [null,undefined,{}, {skipped:true}]) assert.equal(taskStatusLabel({status:'succeeded',result},'succeeded'),'Completada');
 assert.equal(taskStatusLabel({status:'succeeded',result:{state:'acreditado'}},'running'),'Con evidencia');
 assert.equal(taskStatusLabel({status:'succeeded',result:{state:'desconocido'}},'running'),'No consta en el texto');
 assert.equal(taskStatusLabel({status:'pending'},'failed'),'No ejecutada: cierre');
 assert.equal(taskStatusLabel({status:'pending'},'running'),'En espera');
 assert.equal(taskStatusLabel({status:'unknown'},'running'),'Resultado incierto');
});

test('cada bloqueo explica la acción necesaria antes de lanzar',async()=>{
 const {launchBlockReason}=await import('../public/workflow-state.js');
 const workflow={reachable:true,control:{enabled:true}},settings={history_ready:true};
 assert.equal(launchBlockReason(workflow,[],settings,'search'),'');
 assert.match(launchBlockReason({...workflow,control:{enabled:false}},[],settings,'search'),/Habilitar ejecuciones/);
 assert.match(launchBlockReason(workflow,[{status:'unknown'}],settings,'search'),/incierto/);
 assert.match(launchBlockReason(workflow,[],{history_ready:false},'search'),/Configuración/);
 assert.equal(launchBlockReason(workflow,[],{history_ready:false},'contract'),'');
});
