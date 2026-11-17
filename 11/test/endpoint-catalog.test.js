import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('el catálogo muestra entradas y respuestas, filtra y usa texto seguro',async()=>{
  class Element {
    children=[];dataset={};textContent='';value='';hidden=false;
    append(...items){this.children.push(...items);}
    replaceChildren(){this.children=[];}
  }
  const elements=Object.fromEntries(['#endpoint-catalog','#endpoint-filter','#endpoint-count'].map(id=>[id,new Element()]));
  const context=vm.createContext({$:id=>elements[id],document:{createElement:()=>new Element()}});
  const source=await readFile(new URL('../public/app.js',import.meta.url),'utf8');
  vm.runInContext(source.slice(source.indexOf('function renderEndpointCatalog('),source.indexOf('function route()')),context);
  const description='<img src=x onerror=alert(1)>';
  context.renderEndpointCatalog({tools:[{name:'check_offers_batch',method:'POST',path:'/api/offers/check-batch',description,returns:'results: [{url, applied}]',readOnly:true,inputSchema:{type:'object',properties:{urls:{type:'array'}}}}],http_endpoints:[{method:'GET',path:'/api/runtime',returns:'databaseConfigured',input:'Sin parámetros.'}]});
  const items=elements['#endpoint-catalog'].children;
  assert.equal(items.length,2);
  assert.ok(items[0].children[1].textContent.includes(description));
  assert.match(items[0].children[2].textContent,/applied/);
  assert.match(items[0].children[4].textContent,/urls/);
  assert.match(items[1].children[0].textContent,/Solo HTTP/);
  elements['#endpoint-filter'].value=' CHECK_OFFERS_BATCH ';elements['#endpoint-filter'].oninput();
  assert.equal(items[0].hidden,false);assert.equal(items[1].hidden,true);
  assert.match(elements['#endpoint-count'].textContent,/1 de 2/);
  elements['#endpoint-filter'].value='no existe';elements['#endpoint-filter'].oninput();
  assert.match(elements['#endpoint-count'].textContent,/0 de 2/);
});
