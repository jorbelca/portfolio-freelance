import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {InMemoryTransport} from '@modelcontextprotocol/sdk/inMemory.js';
import {createMcpServer,apiClient,integrationInfo} from '../src/mcp.js';

async function connect(request,readOnly=false) {
  const server=createMcpServer({request,readOnly});
  const client=new Client({name:'test-client',version:'1.0.0'});
  const [a,b]=InMemoryTransport.createLinkedPair();
  await server.connect(b); await client.connect(a);
  return {client,close:async()=>{await client.close(); await server.close();}};
}
test('MCP limita herramientas y recursos al seguimiento de postulaciones',async()=>{
  const calls=[];
  const request=async(...args)=>{calls.push(args); if(args[1]==='PATCH') throw Object.assign(new Error('Versión obsoleta'),{status:409}); return [];};
  const {client,close}=await connect(request);
  try {
    const {tools}=await client.listTools();
    assert.deepEqual(tools.map(t=>t.name),['get_catalogs','list_offers','get_offer','list_companies','list_rejection_reasons','create_rejection_reason','create_offer','patch_offer','check_offers_batch','check_history','list_offer_events','list_publications','list_actions','add_publication','merge_offers','list_offer_merges','unmerge_offer','create_action','update_action']);
    assert.equal((await client.listResources()).resources.some(r=>r.uri==='empleo://settings'),false);
    assert.equal((await client.listResourceTemplates()).resourceTemplates.length,0);
    await assert.rejects(client.listPrompts(),/Method not found/);
    for(const name of ['start_run','patch_settings','get_workflow']) assert.equal((await client.callTool({name,arguments:{}})).isError,true);
    for(const urls of [[],Array(101).fill('https://example.test'),['javascript:alert(1)']]) assert.equal((await client.callTool({name:'check_offers_batch',arguments:{urls}})).isError,true);
    assert.equal(calls.length,0);
    const urls=['https://www.linkedin.com/jobs/view/123'];
    await client.callTool({name:'check_offers_batch',arguments:{urls}});
    assert.deepEqual(calls.pop(),['offers/check-batch','POST',{urls}]);
    const id=randomUUID();
    const failed=await client.callTool({name:'patch_offer',arguments:{id,expected_version:1,patch:{notes:'Cambio'}}});
    assert.equal(failed.structuredContent.error.code,'CONFLICT');
    assert.deepEqual(calls.pop(),[`offers/${id}`,'PATCH',{version:1,patch:{notes:'Cambio'}}]);
  } finally {await close();}
  const readonly=await connect(request,true);
  try {assert.ok((await readonly.client.listTools()).tools.every(t=>t.annotations.readOnlyHint));} finally {await readonly.close();}
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

test('el catálogo público coincide con todas las herramientas reales sin llamar a la API',async()=>{
  const info=integrationInfo('http://127.0.0.1:3210');
  const {client,close}=await connect(()=>{throw new Error('No debe llamar a la API');});
  try {
    const {tools}=await client.listTools();
    assert.deepEqual(info.tools.map(tool=>tool.name),tools.map(tool=>tool.name));
    for(const tool of info.tools) {
      const registered=tools.find(item=>item.name===tool.name);
      assert.equal(tool.description,registered.description);
      assert.equal(tool.readOnly,registered.annotations.readOnlyHint);
      assert.deepEqual(JSON.parse(JSON.stringify(tool.inputSchema)),registered.inputSchema);
      assert.match(tool.method,/^(GET|POST|PUT|PATCH)$/);
      assert.match(tool.path,/^\/api\//);
      assert.ok(tool.returns.length>20);
    }
    assert.equal(info.tools.find(tool=>tool.name==='check_offers_batch').inputSchema.properties.urls.maxItems,100);
    assert.ok(info.http_endpoints.some(item=>item.path==='/api/search/runs/{run_id}/next'));
    if(process.env.MCP_TOKEN) assert.equal(JSON.stringify(info).includes(process.env.MCP_TOKEN),false);
  } finally {await close();}
});
