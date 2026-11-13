import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {runInput} from '../src/workflow.js';
import {extractionTasks,extractionPrompt,tasksFor} from '../src/tasks.js';
test('solo admite el módulo implementado, con identificador idempotente y documento acotado',()=>{
  const value={id:randomUUID(),module:'contract',text:'Documento de prueba aislado'};
  assert.equal(runInput(value),value);
  assert.equal(runInput({...value,module:'extraction'}).module,'extraction');
  assert.equal(runInput({id:value.id,module:'search'}).module,'search');
  for (const change of [{id:'otro'},{module:'discovery'},{text:''},{text:' '},{text:'x'.repeat(100001)}]) assert.throws(()=>runInput({...value,...change}));
});
test('el workflow real autentica ambos saltos y devuelve identidad de ejecución',()=>{
  const workflow=JSON.parse(readFileSync(new URL('../workflows/01-contrato.json',import.meta.url)));
  const [trigger,request,result]=workflow.nodes;
  assert.equal(trigger.parameters.authentication,'headerAuth');
  assert.equal(request.credentials.httpHeaderAuth.id,trigger.credentials.httpHeaderAuth.id);
  assert.match(request.parameters.jsonBody,/run_id/);
  assert.ok(result.parameters.assignments.assignments.some(field=>field.value==='={{ $execution.id }}'));
  assert.equal(JSON.stringify(workflow).includes('Bearer '),false);
});

test('quince tareas permitidas con un nodo autenticado por tarea y cierre persistente',()=>{
  const workflow=JSON.parse(readFileSync(new URL('../workflows/02-extracciones.json',import.meta.url)));
  assert.equal(workflow.nodes.length,17);
  assert.equal(workflow.nodes[0].parameters.responseMode,'onReceived');
  assert.equal(new Set(extractionTasks.map(task=>task.id)).size,15);
  assert.equal(tasksFor('contract').length,1);
  assert.throws(()=>tasksFor('discovery'));
  for (const [index,task] of extractionTasks.entries()) {
    const node=workflow.nodes[index+1];
    assert.equal(node.id,task.id);
    assert.ok(node.parameters.url.endsWith(`/api/tasks/${task.id}`));
    assert.equal(node.credentials.httpHeaderAuth.id,'empleoPanelHeader');
    assert.equal(node.parameters.options.response,undefined);
    assert.equal(workflow.connections[workflow.nodes[index].name].main[0][0].node,node.name);
    const prompt=extractionPrompt(task.id,'Documento aislado');
    assert.ok(prompt.startsWith(task.instruction));
    assert.match(prompt,/No uses herramientas/);
    assert.match(prompt,/desconocido/);
  }
  assert.throws(()=>extractionPrompt('arbitrary','Documento'));
  assert.ok(workflow.nodes.at(-1).parameters.url.endsWith('/tasks/finish'));
});
test('búsqueda n8n: nodo singular por operación, cierre por estado persistido y sin secretos',async()=>{
 const {searchTaskKinds}=await import('../src/search.js');
 const workflow=JSON.parse(readFileSync(new URL('../workflows/03-busqueda.json',import.meta.url)));
 assert.equal(workflow.nodes.length,searchTaskKinds.length+4);
 const routing=workflow.nodes.find(node=>node.id==='route');assert.equal(routing.parameters.numberOutputs,searchTaskKinds.length);
 assert.equal(routing.parameters.output,'={{ '+JSON.stringify(searchTaskKinds)+'.indexOf($json.kind) }}');
 assert.equal(workflow.nodes[0].parameters.authentication,'headerAuth');
 assert.equal(workflow.nodes[0].parameters.responseMode,'onReceived');
 for(const kind of searchTaskKinds) {
  const node=workflow.nodes.find(node=>node.id===kind);assert.ok(node);
  assert.equal(node.credentials.httpHeaderAuth.id,'empleoPanelHeader');
  assert.equal(workflow.connections[node.name].main[0][0].node,'Elegir siguiente tarea persistida');
 }
 assert.equal(JSON.stringify(workflow).includes('Bearer '),false);
});

test('programación n8n: comprobación cada minuto autenticada sin acceso directo a modelos',()=>{
 const workflow=JSON.parse(readFileSync(new URL('../workflows/04-programacion.json',import.meta.url)));
 assert.equal(workflow.nodes.length,2);
 const [clock,tick]=workflow.nodes;
 assert.equal(clock.type,'n8n-nodes-base.scheduleTrigger');
 assert.deepEqual(clock.parameters.rule.interval,[{field:'minutes',minutesInterval:1}]);
 assert.equal(workflow.settings.timezone,'Europe/Madrid');
 assert.ok(tick.parameters.url.endsWith('/api/workflow/schedule/tick'));
 assert.equal(tick.credentials.httpHeaderAuth.id,'empleoPanelHeader');
 assert.equal(workflow.connections[clock.name].main[0][0].node,tick.name);
 assert.equal(JSON.stringify(workflow).includes('Bearer '),false);
});

import {scheduleSchema} from '../src/schedule.js';
test('programación valida límites, campos y fechas UTC',()=>{
 const value={revision:1,enabled:false,interval_minutes:1440,next_run_at:'2026-11-14T09:00:00.000Z'};
 assert.equal(scheduleSchema.safeParse(value).success,true);
 for(const change of [{interval_minutes:14},{interval_minutes:525601},{interval_minutes:1.5},{revision:0},{enabled:'true'},{next_run_at:'2026-02-30T00:00:00Z'},{next_run_at:'2026-11-14T09:00'},{extra:true}]) assert.equal(scheduleSchema.safeParse({...value,...change}).success,false);
});
