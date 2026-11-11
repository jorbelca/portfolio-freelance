import {readFile,writeFile} from 'node:fs/promises';
import {extractionTasks} from '../src/tasks.js';
const original=JSON.parse(await readFile(new URL('../workflows/01-contrato.json',import.meta.url),'utf8'));
const trigger=structuredClone(original.nodes[0]);
trigger.webhookId='empleo-extraction';
trigger.parameters.path='empleo-extraction';
trigger.parameters.responseMode='onReceived';
const nodes=[trigger],connections={};
for (const [index,task] of extractionTasks.entries()) {
  const node=structuredClone(original.nodes[1]);
  node.id=task.id; node.name=`${String(index+1).padStart(2,'0')} · ${task.label}`;
  node.position=[280*(index+1),0];
  node.parameters.url=`http://host.docker.internal:3210/api/tasks/${task.id}`;
  node.parameters.jsonBody="={{ JSON.stringify({run_id: $('Recibir ejecución del panel').first().json.body.run_id}) }}";
  delete node.parameters.options.response;
  nodes.push(node);
}
const finish=structuredClone(original.nodes[1]);
finish.id='finish';finish.name='Cerrar desde resultados de Neon';finish.position=[280*16,0];
finish.parameters.url='http://host.docker.internal:3210/api/tasks/finish';
finish.parameters.jsonBody="={{ JSON.stringify({run_id: $('Recibir ejecución del panel').first().json.body.run_id, execution_id: $execution.id}) }}";
delete finish.parameters.options.response;
nodes.push(finish);
for (let i=0;i<nodes.length-1;i++) connections[nodes[i].name]={main:[[{node:nodes[i+1].name,type:'main',index:0}]]};
await writeFile(new URL('../workflows/02-extracciones.json',import.meta.url),JSON.stringify({id:'empleoExtraction02',name:'Empleo - ficha en 15 tareas independientes',active:false,settings:{executionOrder:'v1'},nodes,connections},null,2)+'\n');
