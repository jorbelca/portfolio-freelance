export const offerStates={pendiente:'Pendiente',inscrita:'Inscrito',rechazada:'Rechazado'};
export function offerState(offer) {
  if (offer.review_state==='descartada') return 'rechazada';
  const state=offer.application_state;
  if (state.startsWith('rechazada') || state==='oferta_rechazada') return 'rechazada';
  if (state==='retirada') return 'rechazada';
  return state==='sin_candidatura'?'pendiente':'inscrita';
}
export function statePatch(offer,next) {
  if (!Object.hasOwn(offerStates,next)) throw new Error('Estado inválido');
  if (offer && offerState(offer)===next) return {};
  if (next==='pendiente' && offer && offer.application_state!=='sin_candidatura') throw new Error('Una inscripción existente no puede volver a pendiente.');
  const patch={review_state:'guardada',reason:`Estado cambiado a ${offerStates[next]}.`};
  patch.application_state={pendiente:'sin_candidatura',inscrita:'enviada',rechazada:'rechazada_sin_detalle'}[next];
  return patch;
}
