import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesOfferUrl,filterPostulations,applicationsToday} from '../public/postulations.js';

test('URL search matches primary and alternative URLs, ignores case and surrounding whitespace',()=>{
  const offer={url:'https://example.com/Job/123',publications:[{url:'https://portal.es/456'}]};
  assert.equal(matchesOfferUrl(offer,' HTTPS://EXAMPLE.COM/job/123 '),true);
  assert.equal(matchesOfferUrl(offer,'portal.es/456'),true);
  assert.equal(matchesOfferUrl(offer,'missing'),false);
  assert.equal(matchesOfferUrl({},''),true);
  assert.equal(matchesOfferUrl({},'missing'),false);
});

test('URL search finds the saved Workday application by tenant and full requisition ID',()=>{
  const saved='https://juliusbaer.wd3.myworkdayjobs.com/en-US/External/job/Junior-Frontend-Engineer-100---f-m-d-_r-20206-1';
  const variant='https://juliusbaer.wd3.myworkdayjobs.com/External/job/Madrid/Junior-Frontend-Engineer-100---f-m-d-_r-20206-1?utm_source=spain-devjobs.com&utm_medium=job_board';
  const offer={url:'https://example.com/job/123',publications:[{url:saved}]};
  assert.equal(matchesOfferUrl(offer,variant),true);
  assert.equal(matchesOfferUrl(offer,variant.replace('juliusbaer','another-company')),false);
  assert.equal(matchesOfferUrl(offer,variant.replace('r-20206-1','r-20206')),false);
  assert.equal(matchesOfferUrl(offer,'https://example.com/job/123?utm_source=test#details'),true);
  assert.equal(matchesOfferUrl(offer,'https://example.com/job/123?id=456'),false);
});

test('URL search identifies Indra offers with and without a brand prefix',()=>{
  const saved='https://careers.indragroup.com/Minsait/job/Madrid-Desarrolladora-Junior-Java-MD/978237755/';
  const variant='https://careers.indragroup.com/job/Madrid-Desarrolladora-Junior-Java-MD/978237755/';
  const offer={url:saved};
  assert.equal(matchesOfferUrl(offer,variant),true);
  assert.equal(matchesOfferUrl(offer,`${variant.slice(0,-1)}?utm_source=job_board&source=search#details`),true);
  assert.equal(matchesOfferUrl(offer,variant.replace('978237755','978237756')),false);
  assert.equal(matchesOfferUrl(offer,variant.replace('careers.indragroup.com','jobs.example.com')),false);
  assert.equal(matchesOfferUrl(offer,`${variant}similar/`),false);
});

test('URL search finds the same EURES offer with language parameters',()=>{
  const saved='https://europa.eu/eures/portal/jv-se/jv-details/NjM3MTAyNSAxMjE';
  const variant=saved+'?jvDisplayLanguage=sv&lang=en';
  assert.equal(matchesOfferUrl({url:saved},variant),true);
  assert.equal(matchesOfferUrl({url:variant},saved),true);
  assert.equal(matchesOfferUrl({url:saved},variant.replace('MjE','MjI')),false);
  assert.equal(matchesOfferUrl({url:saved},variant.replace('europa.eu','europa.eu.example.test')),false);
});

test('today counts only the current Madrid day, including rejected applications once',()=>{
  const offers=[
    {application_state:'enviada',submitted_at:'2026-11-17T00:00:00Z',publications:[{},{}]},
    {application_state:'rechazada_empresa',submitted_at:'2026-11-17T10:00:00Z'},
    {application_state:'enviada',submitted_at:'2026-11-16T00:00:00Z'},
    {application_state:'rechazada_empresa',submitted_at:null},
    {application_state:'sin_candidatura',submitted_at:'2026-11-17T00:00:00Z'},
    {}
  ];
  assert.equal(applicationsToday(offers,new Date('2026-11-16T23:30:00Z')),2);
  assert.equal(applicationsToday(offers,new Date('2026-11-16T22:30:00Z')),1);
  assert.equal(applicationsToday(offers,new Date('2026-11-17T23:30:00Z')),0);
  assert.equal(applicationsToday([],new Date('2026-11-17T12:00:00Z')),0);
});

test('company or URL search combines with submission period and status filters',()=>{
  const today=new Date('2026-11-16T23:30:00Z');
  const base={company:'Ágora Digital',url:'https://example.com/jobs/123',application_state:'enviada'};
  const dated=(date,changes={})=>({...base,...changes,submitted_at:date && `${date}T00:00:00Z`});
  const offers=[
    dated('2026-11-17'),dated('2026-11-11'),dated('2026-11-10'),dated(null),dated('2026-11-18'),
    dated('2026-11-17',{company:'Otra empresa'}),
    dated('2026-11-17',{url:'https://example.com/jobs/456'}),
    dated('2026-11-17',{application_state:'rechazada_empresa'})
  ];
  const filters={company:' AGORA ',url:'jobs/123',state:'inscrita',days:7};
  assert.deepEqual(filterPostulations(offers,filters,today),[offers[0],offers[1],offers[5],offers[6]]);
  assert.deepEqual(filterPostulations(offers,{...filters,days:1},today),[offers[0],offers[5],offers[6]]);
  assert.deepEqual(filterPostulations(offers,{...filters,days:0},today),offers.slice(0,7));
});
