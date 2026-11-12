import {readFile,writeFile} from 'node:fs/promises';
import {searchTaskKinds} from '../src/search.js';
const original=JSON.parse(await readFile(new URL('../workflows/01-contrato.json',import.meta.url),'utf8'));
const trigger=structuredClone(original.nodes[0]);trigger.webhookId='empleo-search';trigger.parameters.path='empleo-search';trigger.parameters.responseMode='onReceived';
const next=structuredClone(original.nodes[1]);next.id='next';next.name='Elegir siguiente tarea persistida';next.position=[280,0];
next.parameters.url="={{ 'http://host.docker.internal:3210/api/search/runs/' + $('Recibir ejecución del panel').first().json.body.run_id + '/next' }}";
next.parameters.jsonBody='{}';delete next.parameters.options.response;
const active={id:'active',name:'Quedan tareas y ejecución activa',type:'n8n-nodes-base.if',typeVersion:2.2,position:[560,0],parameters:{conditions:{options:{caseSensitive:true,leftValue:'',typeValidation:'strict',version:2},conditions:[{id:'continue',leftValue:'={{ $json.continue }}',rightValue:true,operator:{type:'boolean',operation:'true',singleValue:true}}],combinator:'and'},options:{}}};
const route={id:'route',name:'Una responsabilidad por nodo',type:'n8n-nodes-base.switch',typeVersion:3.2,position:[840,0],parameters:{mode:'expression',numberOutputs:searchTaskKinds.length,output:`={{ ${JSON.stringify(searchTaskKinds)}.indexOf($json.kind) }}`}};
const nodes=[trigger,next,active,route],connections={};
const edge=(node,index=0)=>({node,type:'main',index});
connections[trigger.name]={main:[[edge(next.name)]]};connections[next.name]={main:[[edge(active.name)]]};connections[active.name]={main:[[edge(route.name)],[]]};connections[route.name]={main:[]};
for (const [index,kind] of searchTaskKinds.entries()) {
 const task=structuredClone(original.nodes[1]);task.id=kind;task.name=`${String(index+1).padStart(2,'0')} · ${kind}`;task.position=[1120,index*150];
 task.parameters.url="={{ 'http://host.docker.internal:3210/api/search/runs/' + $json.run_id + '/steps/' + $json.step_id }}";
 task.parameters.jsonBody="={{ JSON.stringify({kind:$json.kind,execution_id:$execution.id}) }}";delete task.parameters.options.response;
 nodes.push(task);connections[route.name].main.push([edge(task.name)]);connections[task.name]={main:[[edge(next.name)]]};
}
await writeFile(new URL('../workflows/03-busqueda.json',import.meta.url),JSON.stringify({id:'empleoSearch03',name:'Empleo - búsqueda, filtro y presentación por tareas',active:false,settings:{executionOrder:'v1'},nodes,connections},null,2)+'\n');
