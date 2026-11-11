import test from 'node:test';
import assert from 'node:assert/strict';
import {offerStates,offerState,statePatch} from '../public/offer-state.js';

test('un solo estado visible conserva el detalle histórico al guardar sin cambios',()=>{
  assert.deepEqual(Object.keys(offerStates),['pendiente','inscrita','rechazada']);
  for (const application_state of ['enviada','en_revision','prueba','entrevista','oferta','aceptada','sin_respuesta','incorporada','oferta_rechazada','retirada']) {
    const offer={application_state,review_state:'guardada'};
    assert.deepEqual(statePatch(offer,offerState(offer)),{});
  }
  assert.equal(offerState({application_state:'entrevista',review_state:'guardada'}),'inscrita');
});
test('las ofertas descartadas se muestran como rechazadas conservando el historial',()=>{
  const discarded={application_state:'sin_candidatura',review_state:'descartada'};
  assert.equal(offerState(discarded),'rechazada');
  assert.deepEqual(statePatch(discarded,'rechazada'),{});
  assert.equal(offerState({...discarded,...statePatch(discarded,'inscrita')}),'inscrita');
  assert.equal(offerState({application_state:'retirada',review_state:'guardada'}),'rechazada');
  assert.throws(()=>statePatch(discarded,'descartada'));
});
test('rechazar mantiene la exclusión y pendiente no puede borrar una inscripción',()=>{
  const offer={application_state:'entrevista',review_state:'guardada'};
  assert.throws(()=>statePatch(offer,'pendiente'));
  assert.throws(()=>statePatch(offer,'invalido'));
  const rejected=statePatch({application_state:'sin_candidatura',review_state:'nueva'},'rechazada');
  assert.equal(rejected.application_state,'rechazada_sin_detalle');
  assert.equal(rejected.review_state,'guardada');
  assert.ok(rejected.reason);
});
