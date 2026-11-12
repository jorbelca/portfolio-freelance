import {randomUUID} from 'node:crypto';
import {pool, transaction} from './db.js';
import {publicationIdentity,samePublication} from './identity.js';
import {checkApplicationChange, actionInput, cleanUrl, validId} from './domain.js';
const fail = (message, status=400) => Object.assign(new Error(message), {status});
export async function recordEvent(client, id, kind, value, reason='') {
  await client.query('INSERT INTO opportunity_events(opportunity_id,kind,value,reason) VALUES($1,$2,$3,$4)', [id,kind,value,reason]);
}
async function lock(client, id) {
  validId(id);
  const row = (await client.query('SELECT * FROM opportunities WHERE id=$1 FOR UPDATE', [id])).rows[0];
  if (!row) throw fail('Proceso no encontrado',404);
  return row;
}
export async function addPublication(client, id, url) {
  if (!url) return;
  const identity=publicationIdentity(url);
  // Serializa variantes del mismo ID antes de comprobar su propietario.
  await client.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[identity || url]);
  const publications=(await client.query('SELECT opportunity_id,url FROM publications')).rows;
  const previous=publications.find(publication=>samePublication(publication.url,url));
  if (previous && previous.opportunity_id !== id) throw fail('El enlace pertenece a otro proceso. Revisa la posible duplicidad.',409);
  if (publications.some(publication=>publication.url===url)) return;
  const namespace = new URL(url).origin;
  const source = (await client.query('INSERT INTO sources(id,namespace,label) VALUES($1,$2,$2) ON CONFLICT(namespace) DO UPDATE SET namespace=excluded.namespace RETURNING id',[randomUUID(),namespace])).rows[0];
  await client.query('INSERT INTO publications(id,opportunity_id,source_id,url,is_primary) VALUES($1,$2,$3,$4,NOT EXISTS(SELECT 1 FROM publications WHERE opportunity_id=$2))',[randomUUID(),id,source.id,url]);
}
export async function saveOffer(id, input, version) {
  return transaction(async client => {
    const previous = id ? await lock(client,id) : null;
    if (previous && (!Number.isSafeInteger(version) || previous.version !== version)) throw fail('El proceso cambió. Recarga antes de guardar.',409);
    const application = previous ? (await client.query('SELECT state,submitted_at FROM applications WHERE opportunity_id=$1',[id])).rows[0] : null;
    checkApplicationChange(application?.state || 'sin_candidatura', input.application_state);
    const changed = previous && (previous.availability !== input.availability || previous.review_state !== input.review_state || (application?.state || 'sin_candidatura') !== input.application_state);
    if (changed && !input.reason) throw fail('Indica el motivo del cambio de estado.');
    if (input.company_id) {
      const company = (await client.query('SELECT name FROM companies WHERE id=$1',[input.company_id])).rows[0];
      if (!company || company.name !== input.company) throw fail('Selecciona la empresa existente o crea una nueva; editar el nombre no renombra otras ofertas.');
    } else {
      input.company_id = randomUUID();
      await client.query('INSERT INTO companies(id,name) VALUES($1,$2)',[input.company_id,input.company]);
    }
    id ||= randomUUID();
    if (previous) {
      await client.query('UPDATE opportunities SET company_id=$1,title=$2,availability=$3,review_state=$4,notes=$5,version=version+1,updated_at=now(),state_changed_at=CASE WHEN $7 THEN now() ELSE state_changed_at END WHERE id=$6',[input.company_id,input.title,input.availability,input.review_state,input.notes,id,Boolean(changed)]);
    } else {
      await client.query('INSERT INTO opportunities(id,company_id,title,availability,review_state,notes,state_changed_at) VALUES($1,$2,$3,$4,$5,$6,now())',[id,input.company_id,input.title,input.availability,input.review_state,input.notes]);
    }
    if (input.application_state !== 'sin_candidatura' && (application?.state !== input.application_state || input.submitted_at !== undefined)) {
      const submitted = input.submitted_at === undefined ? application?.submitted_at ?? null : input.submitted_at;
      const stampSubmission = !application && input.application_state === 'enviada' && input.submitted_at === undefined;
      await client.query('INSERT INTO applications(id,opportunity_id,state,submitted_at) VALUES($1,$2,$3,CASE WHEN $5 THEN now() ELSE $4::timestamptz END) ON CONFLICT(opportunity_id) DO UPDATE SET state=excluded.state,submitted_at=excluded.submitted_at,updated_at=now()',[randomUUID(),id,input.application_state,submitted,stampSubmission]);
    }
    await addPublication(client,id,input.url);
    await recordEvent(client,id,previous?'updated':'created',input,input.reason);
    return {id};
  });
}
export async function appendPublication(id, raw) {
  const url = cleanUrl(raw.url);
  if (!url) throw fail('Falta el enlace público');
  return transaction(async client => {
    await lock(client,id);
    await addPublication(client,id,url);
    await client.query('UPDATE opportunities SET version=version+1,updated_at=now() WHERE id=$1',[id]);
    await recordEvent(client,id,'publication_added',{url});
    return {id};
  });
}
export async function saveAction(opportunityId, actionId, raw) {
  const input = actionInput(raw);
  return transaction(async client => {
    await lock(client,opportunityId);
    if (actionId) {
      validId(actionId);
      if (!Number.isSafeInteger(raw.version)) throw fail('Falta la versión de la acción');
      const result = await client.query("UPDATE follow_up_actions SET description=$1,due_on=$2,state=$3,completed_at=CASE WHEN $3='completada' THEN coalesce(completed_at,now()) ELSE NULL END,version=version+1 WHERE id=$4 AND opportunity_id=$5 AND version=$6 RETURNING id",[input.description,input.due_on,input.state,actionId,opportunityId,raw.version]);
      if (!result.rowCount) throw fail('La acción cambió o no existe. Recarga.',409);
    } else {
      actionId = randomUUID();
      await client.query("INSERT INTO follow_up_actions(id,opportunity_id,description,due_on,state,completed_at) VALUES($1,$2,$3,$4,$5,CASE WHEN $5='completada' THEN now() END)",[actionId,opportunityId,input.description,input.due_on,input.state]);
    }
    await client.query('UPDATE opportunities SET version=version+1,updated_at=now() WHERE id=$1',[opportunityId]);
    await recordEvent(client,opportunityId,'action_saved',{id:actionId,...input});
    return {id:actionId};
  });
}
export async function checkHistory(raw,client=pool) {
  if (!raw || typeof raw!=='object' || Array.isArray(raw)) throw fail('Consulta de historial inválida');
  for (const key of ['company','title','url']) if (raw[key]!==undefined && raw[key]!==null && (typeof raw[key]!=='string' || raw[key].length>2000)) throw fail('Consulta de historial inválida');
  const url=cleanUrl(raw.url), identity=publicationIdentity(url);
  const rows=(await client.query(`SELECT s.*,p.url AS publication_url FROM offer_summary s LEFT JOIN publications p ON p.opportunity_id=s.id`)).rows;
  const exact=new Map(),possible=new Map();
  for (const row of rows) {
    const {publication_url,...offer}=row;
    if (url && publication_url && samePublication(url,publication_url)) exact.set(row.id,offer);
    if (raw.company?.trim() && raw.title?.trim() && row.company.toLowerCase()===raw.company.trim().toLowerCase() && row.title.toLowerCase()===raw.title.trim().toLowerCase()) possible.set(row.id,offer);
  }
  const matches=[...new Map([...possible,...exact]).values()];
  const ambiguous=exact.size>1;
  return {excluded:[...exact.values()].some(row=>row.excluded),already_known:exact.size>0,needs_review:ambiguous || (!exact.size && possible.size>0),identity,matches};
}
