import test from 'node:test';
import assert from 'node:assert/strict';
import {isPublicAddress} from '../src/public-http.js';
import {plainText,parseFeed,readJobPosting,discoverSource} from '../src/sources.js';
test('bloquea direcciones privadas, metadatos y túneles IPv6',()=>{
  for (const ip of ['127.0.0.1','10.2.3.4','169.254.169.254','172.31.1.1','192.168.1.1','100.64.0.1','::1','::ffff:127.0.0.1','2002:7f00:1::','2001:db8::1','bad']) assert.equal(isPublicAddress(ip),false,ip);
  assert.equal(isPublicAddress('8.8.8.8'),true);
  assert.equal(isPublicAddress('2606:4700:4700::1111'),true);
});
test('fuentes validadas y texto sin instrucciones ejecutables',async()=>{
  assert.equal(plainText('<script>secret</script><p>A &amp; B &#x41;</p>'),'A & B A');
  assert.throws(()=>parseFeed('other',{}));
  assert.throws(()=>parseFeed('remotive',{jobs:[{}]}));
  const result=await discoverSource('arbeitnow',async()=>({status:200,checked_at:'today',text:JSON.stringify({data:[]})}));
  assert.deepEqual(result.leads,[]);
  await assert.rejects(()=>discoverSource('remotive',async()=>({status:403})));
});
test('no convierte página genérica ni múltiples anuncios en ficha completa',()=>{
  assert.equal(readJobPosting('<h1>Login</h1>').complete,false);
  const job={'@type':'JobPosting',title:'Test aislado',hiringOrganization:{name:'Fixture'},description:'Descripción de prueba. '.repeat(20)};
  const script=value=>`<script type="application/ld+json">${JSON.stringify(value)}</script>`;
  assert.equal(readJobPosting(script(job)).complete,true);
  assert.equal(readJobPosting(script([job,job])).complete,false);
  assert.equal(readJobPosting(script({...job,description:'breve'})).complete,false);
});
test('fuente corporativa por país, paginación acotada y sin aceptar tenants arbitrarios',async()=>{
 const {sourceSpec,supportedSource}=await import('../src/sources.js');
 assert.equal(supportedSource('smartrecruiters:Scalian:es'),true);assert.equal(supportedSource('smartrecruiters:../private:es'),false);
 assert.match(sourceSpec('smartrecruiters:Scalian:es').url,/country=es/);
 let calls=0;
 const result=await discoverSource('smartrecruiters:Scalian:es',async()=>{calls++;return {status:200,checked_at:'now',text:JSON.stringify({totalFound:300,content:[{id:'123',name:'Developer',company:{name:'Fixture'},location:{country:'es'}}]})};},{maxPages:2});
 assert.equal(calls,2);assert.equal(result.truncated,true);assert.equal(result.leads.length,2);assert.match(result.leads[0].url,/jobs.smartrecruiters.com\/Scalian\/123/);
 await assert.rejects(()=>discoverSource('arbeitnow',async()=>({status:200,text:JSON.stringify({data:[],links:{next:'https://evil.example/api'}})})));
});
test('lectura corporativa conserva la evidencia y rechaza identidad ajena o descripción parcial',async()=>{
 const {readSourceDocument,candidateReadUrl}=await import('../src/sources.js');
 const candidate={source:'smartrecruiters:Fixture:es',external_id:'123',url:'https://jobs.smartrecruiters.com/Fixture/123'};
 const data={id:'123',name:'Developer',company:{name:'Fixture',identifier:'Fixture'},location:{country:'es',remote:true},releasedDate:'2026-11-12T00:00:00Z',typeOfEmployment:{id:'permanent',label:'Full-time'},creator:{email:'no-conservar@example.test'},jobAd:{sections:{jobDescription:{text:'<p>Desarrollo de software. '.repeat(20)+'</p>'},qualifications:{text:'React'}}}};
 const read=value=>readSourceDocument(candidate,{text:JSON.stringify(value)});
 assert.equal(read(data).complete,true);assert.equal(read(data).job.jobLocation.address.addressCountry,'ES');
 assert.equal(read(data).source_payload.creator,undefined);assert.match(read(data).text,/Full-time/);assert.doesNotMatch(read(data).text,/permanent/);
 assert.equal(read({...data,id:'124'}).complete,false);assert.equal(read({...data,jobAd:{}}).complete,false);
 assert.match(candidateReadUrl(candidate),/api.smartrecruiters.com.*123$/);
});

test('alternativas públicas acotadas al mismo tenant/ID y lectura singular por ruta',async()=>{
 const {readingRoutes,readSourceDocument}=await import('../src/sources.js');
 const candidate={source:'smartrecruiters:Fixture:es',external_id:'123',url:'https://jobs.smartrecruiters.com/Fixture/123'};
 const routes=readingRoutes(candidate,{alternatives:true});assert.equal(routes.length,2);
 assert.equal(routes[0].format,'smartrecruiters');assert.equal(routes[1].format,'html');
 assert.equal(readingRoutes(candidate).length,1);
 assert.throws(()=>readingRoutes({...candidate,external_id:'124'},{alternatives:true}));
 const aggregator={...candidate,source:'remotive',external_id:'remotive-id'};
 const reverse=readingRoutes(aggregator,{alternatives:true});assert.equal(reverse[0].format,'html');assert.equal(reverse[1].external_id,'123');
 assert.equal(readingRoutes({...aggregator,url:'https://other.example/job/123'},{alternatives:true}).length,1);
 const job={'@type':'JobPosting',title:'Developer',hiringOrganization:{name:'Fixture'},description:'Desarrollo de software. '.repeat(20),url:candidate.url};
 const response={url:candidate.url,text:`<script type="application/ld+json">${JSON.stringify(job)}</script>`};
 assert.equal(readSourceDocument(candidate,response,routes[1]).complete,true);
 assert.equal(readSourceDocument(candidate,{...response,url:'https://jobs.smartrecruiters.com/Other/123'},routes[1]).complete,false);
 assert.equal(readSourceDocument(candidate,{...response,text:response.text.replace('/Fixture/123','/Fixture/124')},routes[1]).complete,false);
 const api={id:'123',name:'Developer',company:{name:'Fixture',identifier:'Fixture'},jobAd:{sections:{jobDescription:{text:job.description}}}};
 assert.equal(readSourceDocument(aggregator,{text:JSON.stringify(api)},reverse[1]).complete,true);
 assert.equal(readSourceDocument(aggregator,{text:JSON.stringify({...api,id:'124'})},reverse[1]).complete,false);
});
