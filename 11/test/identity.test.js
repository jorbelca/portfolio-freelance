import test from 'node:test';
import assert from 'node:assert/strict';
import {publicationIdentity,samePublication} from '../src/identity.js';
import {checkHistory} from '../src/store.js';
test('reconoce variantes sin confundir tenant, portal ni enlaces genéricos',()=>{
  assert.equal(samePublication('https://www.infojobs.net/a/dev/of-i123abc?utm_source=x','https://www.infojobs.net/b/other/of-i123abc'),true);
  assert.equal(samePublication('https://emploive.com/home/jobs/8612917','https://emploive.com/jobs/8612917/junior'),true);
  assert.equal(samePublication('https://www.linkedin.com/jobs/view/dev-123456','https://es.linkedin.com/jobs/view/123456'),true);
  assert.equal(samePublication('https://boards.greenhouse.io/a/jobs/123','https://job-boards.greenhouse.io/a/jobs/123'),true);
  assert.equal(samePublication('https://apply.workable.com/a/j/AB12/','https://apply.workable.com/b/j/AB12/'),false);
  assert.equal(samePublication('https://jobs.smartrecruiters.com/a/123-dev','https://jobs.smartrecruiters.com/a/123-other'),true);
  assert.equal(publicationIdentity('https://example.com/careers'),null);
  assert.equal(publicationIdentity('https://infojobs.net.evil.com/of-i123'),null);
  assert.throws(()=>publicationIdentity('javascript:alert(1)'));
});
test('el historial excluye por identidad alternativa y deja coincidencias de texto en revisión',async()=>{
  const row={id:'one',company:'WIRIS',title:'Junior',excluded:true,publication_url:'https://emploive.com/jobs/8612917/junior'};
  const client={query:async()=>({rows:[row]})};
  const result=await checkHistory({url:'https://emploive.com/home/jobs/8612917'},client);
  assert.equal(result.excluded,true);
  assert.equal(result.already_known,true);
  assert.equal(result.needs_review,false);
  const possible=await checkHistory({company:'wiris',title:'Junior'},client);
  assert.equal(possible.excluded,false);
  assert.equal(possible.needs_review,true);
  const ambiguous=await checkHistory({url:row.publication_url},{query:async()=>({rows:[row,{...row,id:'two'}]})});
  assert.equal(ambiguous.needs_review,true);
});
