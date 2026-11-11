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
