export const availabilityStates = ['desconocida','abierta','pausada','cerrada','cubierta','cancelada'];
export const reviewStates = ['nueva','en_revision','guardada','descartada'];
export const applicationStates = ['sin_candidatura','enviada','en_revision','prueba','entrevista','oferta','aceptada','incorporada','rechazada_empresa','oferta_rechazada','rechazada_sin_detalle','retirada','sin_respuesta'];
export const actionStates = ['pendiente','completada','cancelada'];
export function validId(value) {
  if (typeof value !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) throw new Error('Identificador inválido');
  return value;
}
export function checkApplicationChange(previous, next) {
  if (previous !== 'sin_candidatura' && next === 'sin_candidatura') throw new Error('No se puede borrar una candidatura cambiando su estado. Requiere una corrección de historial explícita.');
}
export function isExcluded({application_state, availability, review_state}) {
  return application_state !== 'sin_candidatura' || review_state === 'descartada' || ['pausada','cerrada','cubierta','cancelada'].includes(availability);
}
export function validDate(value) {
  if (value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0,10) !== value)) throw new Error('Fecha inválida');
  return value || null;
}
export function validTimestamp(value) {
  if (value === null || value === '') return null;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,3})?Z$/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('Fecha de inscripción inválida');
  validDate(value.slice(0,10));
  return new Date(value).toISOString();
}
export function cleanUrl(value) {
  if (!value) return null;
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Enlace público inválido');
  url.hash = '';
  for (const key of [...url.searchParams.keys()]) {
    if (/^(utm_.*|tmp_ctoken|hash|requestParams|token|session|confirmation)$/i.test(key)) url.searchParams.delete(key);
  }
  return url.href;
}
export function offerInput(body) {
  if (!body || typeof body !== 'object') throw new Error('Datos inválidos');
  for (const key of ['company', 'title']) {
    if (typeof body[key] !== 'string' || !body[key].trim() || body[key].length > 500) throw new Error(`Revisa ${key}`);
  }
  if (!availabilityStates.includes(body.availability) || !reviewStates.includes(body.review_state) || !applicationStates.includes(body.application_state)) throw new Error('Estado inválido');
  for (const key of ['notes', 'reason']) {
    if (body[key] !== undefined && (typeof body[key] !== 'string' || body[key].length > 20000)) throw new Error(`Revisa ${key}`);
  }
  const submitted = body.submitted_at === undefined ? undefined : validTimestamp(body.submitted_at);
  if (submitted && body.application_state === 'sin_candidatura') throw new Error('La fecha de inscripción requiere una candidatura.');
  return {submitted_at: submitted, company: body.company.trim(), company_id: body.company_id ? validId(body.company_id) : null,
    title: body.title.trim(), url: cleanUrl(body.url), availability: body.availability,
    review_state: body.review_state, application_state: body.application_state,
    notes: body.notes ?? '', reason: body.reason?.trim() || ''};
}
export function actionInput(body) {
  if (!body || typeof body.description !== 'string' || !body.description.trim() || body.description.length > 20000 || !actionStates.includes(body.state)) throw new Error('Revisa la acción');
  return {description: body.description.trim(), due_on: validDate(body.due_on), state: body.state};
}
export function validateSettings(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Configuración inválida');
  for (const key of ['max_openings', 'batch_size', 'max_age_days', 'quota_spain', 'quota_europe']) {
    if (!Number.isSafeInteger(value[key]) || value[key] < 1) throw new Error(`Revisa ${key}`);
  }
  if (value.batch_size > value.max_openings || typeof value.history_ready !== 'boolean') throw new Error('Revisa lotes e historial');
  new Intl.DateTimeFormat('es', {timeZone: value.timezone});
  if (typeof value.source_prompt !== 'string' || !value.source_prompt.trim()) throw new Error('Falta el prompt del perfil');
  if (typeof value.model !== 'string' || value.model.length > 200) throw new Error('Modelo inválido');
  if (!['codex','openai'].includes(value.provider ?? 'codex')) throw new Error('Motor no admitido');
  if (value.provider === 'openai' && !value.model.trim()) throw new Error('Elige un modelo para la API de OpenAI');
  const keys = ['provider','max_openings','batch_size','max_age_days','quota_spain','quota_europe','history_ready','timezone','model','source_prompt'];
  if (Object.keys(value).some(key => !keys.includes(key))) throw new Error('Variable no admitida');
  return value;
}
