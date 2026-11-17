import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesOfferUrl,applicationsToday} from '../public/postulations.js';

test('URL search matches primary and alternative URLs, ignores case and surrounding whitespace',()=>{
  const offer={url:'https://example.com/Job/123',publications:[{url:'https://portal.es/456'}]};
  assert.equal(matchesOfferUrl(offer,' HTTPS://EXAMPLE.COM/job/123 '),true);
  assert.equal(matchesOfferUrl(offer,'portal.es/456'),true);
  assert.equal(matchesOfferUrl(offer,'missing'),false);
  assert.equal(matchesOfferUrl({},''),true);
  assert.equal(matchesOfferUrl({},'missing'),false);
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
