import test from 'node:test';
import assert from 'node:assert/strict';
import {cleanUrl, offerInput, validateSettings, validDate, checkApplicationChange, isExcluded, actionInput} from '../src/domain.js';
import {validateExtraction} from '../src/codex.js';
import {readFileSync} from 'node:fs';
test('limpia seguimiento conservando el ID público', () => {
  assert.equal(cleanUrl('https://jobs.example/j/123?utm_source=x&requestParams=secret#private'), 'https://jobs.example/j/123');
  assert.throws(() => cleanUrl('javascript:alert(1)'));
  assert.throws(() => cleanUrl('https://user:secret@example.com'));
});
test('valida altas y fechas sin normalizar días imposibles', () => {
  const input = {company:' Acme ',title:'Dev',availability:'abierta',review_state:'nueva',application_state:'enviada'};
  assert.equal(offerInput(input).company,'Acme');
  assert.equal(offerInput({...input,submitted_at:'2026-11-10T00:00:00Z'}).submitted_at,'2026-11-10T00:00:00.000Z');
  for (const submitted_at of ['2026-02-30T00:00:00Z','2026-11-10','2026-11-10T24:00:00Z',123,{}]) assert.throws(()=>offerInput({...input,submitted_at}));
  assert.throws(()=>offerInput({...input,application_state:'sin_candidatura',submitted_at:'2026-11-10T00:00:00Z'}));
  assert.equal(offerInput(input).submitted_at,undefined);
  assert.throws(() => validDate('2026-02-30'));
  assert.throws(() => offerInput({...input,application_state:'inventado'}));
  assert.throws(() => offerInput({...input,company_id:'incorrecto'}));
});
test('la configuración inicial exige registrar el historial', () => {
  const defaults = JSON.parse(readFileSync(new URL('../defaults.json',import.meta.url)));
  assert.equal(validateSettings(defaults).history_ready,false);
  assert.throws(()=>validateSettings({...defaults,public_alternatives:'true'}));
  assert.equal(validateSettings({...defaults,public_alternatives:false}).public_alternatives,false);
  for(const model_timeout_seconds of [4,121,1.5,'30',null]) assert.throws(()=>validateSettings({...defaults,model_timeout_seconds}));
  assert.equal(validateSettings({...defaults,model_timeout_seconds:30}).model_timeout_seconds,30);
  for(const model_retries of [-1,4,1.5,'1',null]) assert.throws(()=>validateSettings({...defaults,model_retries}));
  assert.equal(validateSettings({...defaults,model_retries:0}).model_retries,0);
  assert.throws(() => validateSettings({...defaults,batch_size:101}));
});
test('rechaza evidencia inventada y desconocidos contradictorios', () => {
  const text='Contrato indefinido. Jornada completa.';
  assert.equal(validateExtraction({value:'indefinido',evidence:'Contrato indefinido',state:'acreditado'},text).value,'indefinido');
  assert.throws(() => validateExtraction({value:'indefinido',evidence:'permanente',state:'acreditado'},text));
  assert.throws(() => validateExtraction({value:'indefinido',evidence:'',state:'desconocido'},text));
});

test('reapertura no elimina candidatura ni desbloquea una rechazada', () => {
  const base={availability:'abierta',review_state:'guardada',application_state:'sin_candidatura'};
  assert.equal(isExcluded(base),false);
  for (const application_state of ['enviada','entrevista','rechazada_empresa','oferta_rechazada','retirada','sin_respuesta','incorporada']) assert.equal(isExcluded({...base,application_state}),true);
  assert.equal(isExcluded({...base,review_state:'descartada'}),true);
  assert.equal(isExcluded({...base,availability:'pausada'}),true);
  assert.throws(()=>checkApplicationChange('rechazada_empresa','sin_candidatura'));
  assert.doesNotThrow(()=>checkApplicationChange('rechazada_empresa','entrevista'));
});
test('cada acción conserva estado y fecha propios', () => {
  assert.equal(actionInput({description:' Revisar ',state:'pendiente'}).description,'Revisar');
  assert.throws(()=>actionInput({description:'',state:'pendiente'}));
  assert.throws(()=>actionInput({description:'Revisar',state:'inventado'}));
  assert.throws(()=>actionInput({description:'Revisar',state:'pendiente',due_on:'2026-02-30'}));
});
