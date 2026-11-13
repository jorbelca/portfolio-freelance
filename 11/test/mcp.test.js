import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {InMemoryTransport} from '@modelcontextprotocol/sdk/inMemory.js';
import {createMcpServer,apiClient} from '../src/mcp.js';

async function connect(request,readOnly=false) {
  const server=createMcpServer({request,readOnly});
  const client=new Client({name:'test-client',version:'1.0.0'});
  const [a,b]=InMemoryTransport.createLinkedPair();
  await server.connect(b); await client.connect(a);
  return {client,close:async()=>{await client.close(); await server.close();}};
}
test('MCP negocia protocolo, publica herramientas estrictas y no reenvía argumentos inválidos',async()=>{
  const calls=[];
  const {client,close}=await connect(async(...args)=>{calls.push(args);return {id:args[2]?.id || randomUUID(),status:'queued'};});
  try {
    const {tools}=await client.listTools();
    assert.equal(tools.length,35);
    assert.equal(tools.find(t=>t.name==='get_workflow').annotations.readOnlyHint,true);
    assert.equal(tools.find(t=>t.name==='start_run').annotations.idempotentHint,true);
    assert.equal(tools.find(t=>t.name==='patch_settings').inputSchema.additionalProperties,false);
    for(const input of [
      {name:'start_run',arguments:{request_id:randomUUID(),module:'discovery',text:'Documento de prueba aislado'}},
      {name:'patch_settings',arguments:{expected_revision:1,patch:{quota_spain:0}}},
      {name:'patch_settings',arguments:{expected_revision:1,patch:{}}},
      {name:'get_workflow',arguments:{unexpected:true}}
    ]) assert.equal((await client.callTool(input)).isError,true);
    assert.equal(calls.length,0);
    const id=randomUUID(),args={request_id:id,module:'contract',text:'  Documento de prueba aislado \n'};
    const result=await client.callTool({name:'start_run',arguments:args});
    assert.equal(result.structuredContent.ok,true);
    assert.deepEqual(calls[0],['workflow/runs','POST',{id,module:'contract',text:args.text}]);
    await client.callTool({name:'start_run',arguments:{...args,module:'extraction'}});
    assert.deepEqual(calls[1],['workflow/runs','POST',{id,module:'extraction',text:args.text}]);
  } finally {await close();}
});
test('MCP expone cambios parciales, errores recuperables, recursos y modo de consulta',async()=>{
  const calls=[];
  const request=async(...args)=>{
    calls.push(args);
    if(args[1]==='PATCH') throw Object.assign(new Error('Configuración modificada'),{status:409});
    return {revision:2,value:{model:'',source_prompt:'Texto de fixture solo en memoria'}};
  };
  const {client,close}=await connect(request);
  try {
    const result=await client.callTool({name:'get_settings',arguments:{}});
    assert.equal(result.structuredContent.data.value.source_prompt,undefined);
    assert.deepEqual(result.structuredContent.data.omitted_fields,['source_prompt']);
    const failed=await client.callTool({name:'patch_settings',arguments:{expected_revision:1,patch:{batch_size:3}}});
    assert.equal(failed.isError,true); assert.equal(failed.structuredContent.error.code,'CONFLICT');
    assert.deepEqual(calls.at(-1),['settings','PATCH',{revision:1,patch:{batch_size:3}}]);
    assert.equal(failed.structuredContent.error.retryable,false);
    const resources=await client.listResources(); assert.ok(resources.resources.some(r=>r.uri==='empleo://guide'));
    assert.match((await client.readResource({uri:'empleo://guide'})).contents[0].text,/expected_revision/);
    assert.ok((await client.listPrompts()).prompts.some(p=>p.name==='operate_workflow'));
  } finally {await close();}
  const readonly=await connect(request,true);
  try {const {tools}=await readonly.client.listTools(); assert.ok(tools.every(t=>t.annotations.readOnlyHint)); assert.ok(!tools.some(t=>t.name==='start_run'));} finally {await readonly.close();}
});
test('el cliente API no usa cabecera de panel y no sigue redirecciones con el secreto',async()=>{
  let call;
  const request=apiClient({baseUrl:'http://127.0.0.1:3210',token:'test-only',fetchImpl:async(...args)=>{call=args;return new Response(JSON.stringify({error:'Versión obsoleta'}),{status:409});}});
  await assert.rejects(request('settings','PATCH',{revision:1,patch:{model:''}}),error=>error.status===409);
  assert.equal(call[1].headers.Authorization,'Bearer test-only');
  assert.equal(call[1].headers['X-Empleo-Client'],undefined);
  assert.equal(call[1].redirect,'error');
  assert.throws(()=>apiClient({baseUrl:'https://user:secret@example.test',token:'test-only'}));
});
