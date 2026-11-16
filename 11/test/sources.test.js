import test from 'node:test';
import assert from 'node:assert/strict';
import {isPublicAddress,verifyPublicBrowserUrl} from '../src/public-http.js';
import {browserSearchUrl,plainText,readJobPosting,sourceSpec,supportedSource} from '../src/sources.js';

test('solo admite Google y Bing por navegador, sin adaptadores de portales',()=>{
 assert.equal(supportedSource('browser:google'),true);
 assert.equal(supportedSource('browser:bing'),true);
 for(const source of ['arbeitnow','remotive','smartrecruiters:Scalian:es','greenhouse:acme','lever:acme']) {
  assert.equal(supportedSource(source),false);
  assert.throws(()=>sourceSpec(source));
 }
 const google=new URL(browserSearchUrl('browser:google',{term:'software developer junior',zone:'spain',language:'en'}));
 assert.equal(google.origin,'https://www.google.com');assert.equal(google.pathname,'/search');
 assert.equal(google.searchParams.get('q'),'software developer junior job vacancy Spain España');assert.equal(google.searchParams.get('hl'),'en');
 const bing=new URL(browserSearchUrl('browser:bing',{term:'React',zone:'europe',language:'es'}));
 assert.equal(bing.searchParams.get('q'),'React oferta de empleo Europe jobs');assert.equal(bing.searchParams.has('hl'),false);
 assert.throws(()=>browserSearchUrl('browser:google',{term:' '}));
});

test('URLs de navegador solo HTTPS y direcciones públicas',async()=>{
 for(const ip of ['127.0.0.1','10.2.3.4','169.254.169.254','172.31.1.1','192.168.1.1','100.64.0.1','::1','::ffff:127.0.0.1','2002:7f00:1::','2001:db8::1','bad']) assert.equal(isPublicAddress(ip),false,ip);
 assert.equal(isPublicAddress('8.8.8.8'),true);assert.equal(isPublicAddress('2606:4700:4700::1111'),true);
 assert.equal(await verifyPublicBrowserUrl('https://8.8.8.8/jobs/123'),'https://8.8.8.8/jobs/123');
 await assert.rejects(()=>verifyPublicBrowserUrl('http://8.8.8.8/job'));
 await assert.rejects(()=>verifyPublicBrowserUrl('https://127.0.0.1/job'));
 await assert.rejects(()=>verifyPublicBrowserUrl('https://8.8.8.8:8443/job'));
});

test('texto visible y JobPosting estructurado sin ejecutar contenido',()=>{
 assert.equal(plainText('<script>secret</script><p>A &amp; B &#x41;</p>'),'A & B A');
 assert.equal(readJobPosting('<h1>Login</h1>').complete,false);
 const job={'@type':'JobPosting',title:'Test aislado',hiringOrganization:{name:'Fixture'},description:'Descripción de prueba. '.repeat(20)};
 const script=value=>`<script type="application/ld+json">${JSON.stringify(value)}</script>`;
 assert.equal(readJobPosting(script(job)).complete,true);
 assert.equal(readJobPosting(script([job,job])).complete,false);
 assert.equal(readJobPosting(script({...job,description:'breve'})).complete,false);
});
