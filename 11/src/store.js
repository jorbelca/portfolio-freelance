import {randomUUID} from 'node:crypto';
import {pool, transaction} from './db.js';
import {offerState} from '../public/offer-state.js';
import {publicationIdentity,samePublication} from '../public/identity.js';
import {checkApplicationChange, actionInput, cleanUrl, validId} from './domain.js';
const fail = (message, status=400) => Object.assign(new Error(message), {status});
export async function recordEvent(client, id, kind, value, reason='') {
  await client.query('INSERT INTO opportunity_events(opportunity_id,kind,value,reason) VALUES($1,$2,$3,$4)', [id,kind,value,reason]);
}
async function lock(client, id, {allowMerged=false}={}) {
  validId(id);
  const row = (await client.query('SELECT * FROM opportunities WHERE id=$1 FOR UPDATE', [id])).rows[0];
  if (!row) throw fail('Proceso no encontrado',404);
  if (!allowMerged && (await client.query('SELECT 1 FROM opportunity_merges WHERE source_id=$1 AND undone_at IS NULL',[id])).rowCount) throw fail('Proceso fusionado; consulta su registro principal.',409);
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
export async function createRejectionReason(raw) {
  const name = typeof raw?.name === 'string' ? raw.name.trim().replace(/\s+/g,' ') : '';
  if (!name || name.length>100 || name.includes('\0')) throw fail('Introduce una causa de 1 a 100 caracteres.');
  return (await pool.query(`INSERT INTO rejection_reasons(name) VALUES($1)
    ON CONFLICT (lower(name)) DO UPDATE SET name=rejection_reasons.name RETURNING id,name`,[name])).rows[0];
}
export async function saveOffer(id, input, version, {requireRejectionReason=false}={}) {
  return transaction(async client => {
    const previous = id ? await lock(client,id) : null;
    if (previous && (!Number.isSafeInteger(version) || previous.version !== version)) throw fail('El proceso cambió. Recarga antes de guardar.',409);
    const application = previous ? (await client.query('SELECT state,submitted_at FROM applications WHERE opportunity_id=$1',[id])).rows[0] : null;
    checkApplicationChange(application?.state || 'sin_candidatura', input.application_state);
    const changed = previous && (previous.availability !== input.availability || previous.review_state !== input.review_state || (application?.state || 'sin_candidatura') !== input.application_state);
    if (changed && !input.reason) throw fail('Indica el motivo del cambio de estado.');
    const rejected = offerState(input)==='rechazada';
    if (!rejected && input.rejection_reason_id) throw fail('La causa solo se puede asignar a una oferta rechazada.');
    const rejectionReasonId = rejected ? (input.rejection_reason_id === undefined ? previous?.rejection_reason_id ?? null : input.rejection_reason_id) : null;
    const wasRejected = previous && offerState({...previous,application_state:application?.state || 'sin_candidatura'})==='rechazada';
    if (requireRejectionReason && rejected && !rejectionReasonId && (!wasRejected || input.rejection_reason_id===null)) {
      throw fail('Selecciona una causa del catálogo con rejection_reason_id. Consulta list_rejection_reasons.');
    }
    if (input.rejection_reason_id && !(await client.query('SELECT 1 FROM rejection_reasons WHERE id=$1',[rejectionReasonId])).rowCount) throw fail('La causa de rechazo no existe.');
    if (input.company_id) {
      const company = (await client.query('SELECT name FROM companies WHERE id=$1',[input.company_id])).rows[0];
      if (!company || company.name !== input.company) throw fail('Selecciona la empresa existente o crea una nueva; editar el nombre no renombra otras ofertas.');
    } else {
      input.company_id = randomUUID();
      await client.query('INSERT INTO companies(id,name) VALUES($1,$2)',[input.company_id,input.company]);
    }
    id ||= randomUUID();
    if (previous) {
      await client.query('UPDATE opportunities SET company_id=$1,title=$2,availability=$3,review_state=$4,notes=$5,version=version+1,updated_at=now(),state_changed_at=CASE WHEN $7 THEN now() ELSE state_changed_at END,rejection_reason_id=$8 WHERE id=$6',[input.company_id,input.title,input.availability,input.review_state,input.notes,id,Boolean(changed),rejectionReasonId]);
    } else {
      await client.query('INSERT INTO opportunities(id,company_id,title,availability,review_state,notes,state_changed_at,rejection_reason_id) VALUES($1,$2,$3,$4,$5,$6,now(),$7)',[id,input.company_id,input.title,input.availability,input.review_state,input.notes,rejectionReasonId]);
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

export async function checkOffersBatch(raw,client=pool) {
  if (!raw || typeof raw!=='object' || Array.isArray(raw) || Object.keys(raw).some(key=>key!=='urls') || !Array.isArray(raw.urls) || raw.urls.length<1 || raw.urls.length>100) throw fail('Indica entre 1 y 100 URLs.');
  const urls=raw.urls.map(url=>{
    if (typeof url!=='string' || !url || url.length>2000) throw fail('URL inválida.');
    return cleanUrl(url);
  });
  const identities=urls.map(publicationIdentity);
  const {rows}=await client.query(`WITH input AS (
    SELECT * FROM unnest($1::text[],$2::text[]) WITH ORDINALITY AS i(url,identity,position)
  ) SELECT i.position,EXISTS (
    SELECT 1 FROM publications p JOIN applications a ON a.opportunity_id=p.opportunity_id
    WHERE p.url=i.url OR (i.identity IS NOT NULL AND publication_identity(p.url)=i.identity)
  ) AS applied FROM input i ORDER BY i.position`,[urls,identities]);
  return {results:rows.map((row,index)=>({url:raw.urls[index],applied:row.applied}))};
}

export async function mergeOffers(targetId,raw) {
  validId(targetId);validId(raw.source_id);
  if(targetId===raw.source_id || !Number.isSafeInteger(raw.version) || !Number.isSafeInteger(raw.source_version) || !['target','source'].includes(raw.application_from) || typeof raw.reason!=='string' || !raw.reason.trim() || raw.reason.length>2000) throw fail('Indica dos procesos, sus versiones, la candidatura que conservar y el motivo.');
  return transaction(async client=>{
    // Orden estable para dos fusiones concurrentes sobre los mismos procesos.
    for(const id of [targetId,raw.source_id].sort()) await lock(client,id);
    const target=(await client.query('SELECT * FROM offer_summary WHERE id=$1',[targetId])).rows[0];
    const source=(await client.query('SELECT * FROM offer_summary WHERE id=$1',[raw.source_id])).rows[0];
    if(target.version!==raw.version || source.version!==raw.source_version) throw fail('Una oferta cambió; recarga ambas antes de fusionar.',409);
    const applications=(await client.query('SELECT * FROM applications WHERE opportunity_id=ANY($1::uuid[]) FOR UPDATE',[[targetId,source.id]])).rows;
    const chosen=applications.find(row=>row.opportunity_id===(raw.application_from==='target'?targetId:source.id));
    if(applications.length && !chosen) throw fail('No puedes eliminar una candidatura: elige el registro que la conserva.',409);
    const targetApplication=applications.find(row=>row.opportunity_id===targetId) || null;
    const movedPublications=(await client.query('SELECT id,is_primary FROM publications WHERE opportunity_id=$1 FOR UPDATE',[source.id])).rows;
    const movedActions=(await client.query('SELECT id FROM follow_up_actions WHERE opportunity_id=$1 FOR UPDATE',[source.id])).rows.map(row=>row.id);
    const movedCandidates=(await client.query('SELECT id FROM search_candidates WHERE opportunity_id=$1 FOR UPDATE',[source.id])).rows.map(row=>row.id);
    const reparentedMerges=(await client.query("SELECT source_id FROM opportunity_merges WHERE target_id=$1 AND undone_at IS NULL FOR UPDATE",[source.id])).rows.map(row=>row.source_id);
    const targetSnapshot={availability:target.availability,review_state:target.review_state,notes:target.notes,state_changed_at:target.state_changed_at,rejection_reason_id:target.rejection_reason_id};
    if(chosen) await client.query('INSERT INTO applications(id,opportunity_id,state,submitted_at,created_at,updated_at) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(opportunity_id) DO UPDATE SET state=excluded.state,submitted_at=excluded.submitted_at,updated_at=excluded.updated_at',[randomUUID(),targetId,chosen.state,chosen.submitted_at,chosen.created_at,chosen.updated_at]);
    await recordEvent(client,targetId,'offers_merged',{target,source,applications,application_from:raw.application_from},raw.reason);
    const hasPrimary=(await client.query('SELECT 1 FROM publications WHERE opportunity_id=$1 AND is_primary',[targetId])).rowCount;
    if(hasPrimary) await client.query('UPDATE publications SET is_primary=false WHERE opportunity_id=$1',[source.id]);
    await client.query('UPDATE publications SET opportunity_id=$1 WHERE opportunity_id=$2',[targetId,source.id]);
    await client.query('UPDATE follow_up_actions SET opportunity_id=$1,version=version+1 WHERE opportunity_id=$2',[targetId,source.id]);
    await client.query('UPDATE search_candidates SET opportunity_id=$1,version=version+1 WHERE opportunity_id=$2',[targetId,source.id]);
    const blocked=['pausada','cerrada','cubierta','cancelada'];
    const availability=blocked.includes(target.availability)?target.availability:blocked.includes(source.availability)?source.availability:target.availability;
    const review=target.review_state==='descartada' || source.review_state==='descartada'?'descartada':target.review_state;
    const applicationOffer=raw.application_from==='source'?source:target;
    const rejectionReasonId=(target.review_state==='descartada' && target.rejection_reason_id)
      || (source.review_state==='descartada' && source.rejection_reason_id)
      || applicationOffer.rejection_reason_id;
    const notes=[target.notes,source.notes && `[Fusionada: ${source.company} — ${source.title}]\n${source.notes}`].filter(Boolean).join('\n\n');
    if(notes.length>20000) throw fail('Las notas combinadas superan 20000 caracteres; reduce su tamaño antes de fusionar.');
    await client.query('UPDATE opportunities SET availability=$2,review_state=$3,notes=$4,version=version+1,updated_at=now(),state_changed_at=$5,rejection_reason_id=$6 WHERE id=$1',[targetId,availability,review,notes,applicationOffer.state_changed_at,rejectionReasonId]);
    await client.query("UPDATE opportunity_merges SET target_id=$1 WHERE target_id=$2 AND undone_at IS NULL",[targetId,source.id]);
    await client.query(`INSERT INTO opportunity_merges(source_id,target_id,reason,target_snapshot,target_application,moved_publications,moved_action_ids,moved_candidate_ids,reparented_merges,target_version_after,source_version_at_merge)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
      ON CONFLICT(source_id) DO UPDATE SET target_id=excluded.target_id,reason=excluded.reason,created_at=now(),undone_at=NULL,undo_reason=NULL,target_snapshot=excluded.target_snapshot,target_application=excluded.target_application,moved_publications=excluded.moved_publications,moved_action_ids=excluded.moved_action_ids,moved_candidate_ids=excluded.moved_candidate_ids,reparented_merges=excluded.reparented_merges,target_version_after=excluded.target_version_after,source_version_at_merge=excluded.source_version_at_merge`,
      [source.id,targetId,raw.reason,targetSnapshot,{exists:Boolean(targetApplication),row:targetApplication},JSON.stringify(movedPublications),movedActions,movedCandidates,reparentedMerges,target.version+1,source.version]);
    return {id:targetId,merged_id:source.id};
  });
}

export async function listOfferMerges(targetId) {
  validId(targetId);
  const target=(await pool.query('SELECT version FROM offer_summary WHERE id=$1',[targetId])).rows[0];
  if(!target) throw fail('Proceso no encontrado',404);
  const rows=(await pool.query(`SELECT m.source_id,m.target_id,m.reason,m.created_at,m.target_snapshot,m.target_version_after,m.source_version_at_merge,
    o.version AS source_version,c.name AS company,o.title,
    m.source_id=(SELECT newest.source_id FROM opportunity_merges newest WHERE newest.target_id=$1 AND newest.undone_at IS NULL ORDER BY newest.created_at DESC,newest.source_id DESC LIMIT 1) AS is_latest
    FROM opportunity_merges m JOIN opportunities o ON o.id=m.source_id JOIN companies c ON c.id=o.company_id
    WHERE m.target_id=$1 AND m.undone_at IS NULL ORDER BY m.created_at DESC,m.source_id DESC`,[targetId])).rows;
  return {items:rows.map(row=>{
    const current=Number(row.source_version)===row.source_version_at_merge && Number(target.version)===row.target_version_after;
    const undoable=Boolean(row.target_snapshot && current && row.is_latest);
    const reason=!row.target_snapshot?'Esta fusión es anterior al guardado de snapshots reversibles.':!row.is_latest?'Deshaz primero la fusión más reciente.':!current?'El proceso cambió después de la fusión; revísalo antes de separarlo.':null;
    return {source_id:row.source_id,target_id:row.target_id,company:row.company,title:row.title,reason:row.reason,created_at:row.created_at,source_version:Number(row.source_version),target_version:Number(target.version),undoable,undo_blocked_reason:reason};
  })};
}

export async function unmergeOffer(targetId,raw) {
  validId(targetId);validId(raw?.source_id);
  if(targetId===raw.source_id || !Number.isSafeInteger(raw.version) || !Number.isSafeInteger(raw.source_version) || typeof raw.reason!=='string' || !raw.reason.trim() || raw.reason.length>2000) throw fail('Indica las versiones actuales y un motivo para separar los procesos.');
  return transaction(async client=>{
    for(const id of [targetId,raw.source_id].sort()) await lock(client,id,{allowMerged:id===raw.source_id});
    const target=(await client.query('SELECT * FROM offer_summary WHERE id=$1',[targetId])).rows[0];
    const source=(await client.query('SELECT o.*,c.name AS company FROM opportunities o JOIN companies c ON c.id=o.company_id WHERE o.id=$1',[raw.source_id])).rows[0];
    const merge=(await client.query('SELECT * FROM opportunity_merges WHERE source_id=$1 AND target_id=$2 AND undone_at IS NULL FOR UPDATE',[raw.source_id,targetId])).rows[0];
    if(!target || !source || !merge) throw fail('No existe esa fusión activa.',409);
    if(target.version!==raw.version || source.version!==raw.source_version) throw fail('Uno de los procesos cambió; recarga antes de deshacer la fusión.',409);
    const latest=(await client.query("SELECT source_id FROM opportunity_merges WHERE target_id=$1 AND undone_at IS NULL ORDER BY created_at DESC,source_id DESC LIMIT 1",[targetId])).rows[0];
    if(latest?.source_id!==source.id) throw fail('Deshaz primero la fusión más reciente.',409);
    if(!merge.target_snapshot || target.version!==merge.target_version_after || source.version!==merge.source_version_at_merge) throw fail('El proceso cambió después de la fusión o no tiene snapshot reversible. Revisa el historial antes de separarlo.',409);

    const movedPublications=merge.moved_publications || [];
    for(const publication of movedPublications) {
      const restored=await client.query('UPDATE publications SET opportunity_id=$2,is_primary=$3 WHERE id=$1 AND opportunity_id=$4',[publication.id,source.id,publication.is_primary,targetId]);
      if(!restored.rowCount) throw fail('Cambió un enlace desde la fusión; no se separaron los procesos.',409);
    }
    if(merge.moved_action_ids.length) {
      const restored=await client.query('UPDATE follow_up_actions SET opportunity_id=$2,version=version+1 WHERE id=ANY($1::uuid[]) AND opportunity_id=$3',[merge.moved_action_ids,source.id,targetId]);
      if(restored.rowCount!==merge.moved_action_ids.length) throw fail('Cambió una acción desde la fusión; no se separaron los procesos.',409);
    }
    if(merge.moved_candidate_ids.length) {
      const restored=await client.query('UPDATE search_candidates SET opportunity_id=$2,version=version+1 WHERE id=ANY($1::uuid[]) AND opportunity_id=$3',[merge.moved_candidate_ids,source.id,targetId]);
      if(restored.rowCount!==merge.moved_candidate_ids.length) throw fail('Cambió una pista desde la fusión; no se separaron los procesos.',409);
    }
    if(merge.target_application.exists) {
      const previous=merge.target_application.row;
      await client.query('INSERT INTO applications(id,opportunity_id,state,submitted_at,created_at,updated_at) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(opportunity_id) DO UPDATE SET id=excluded.id,state=excluded.state,submitted_at=excluded.submitted_at,created_at=excluded.created_at,updated_at=excluded.updated_at',[previous.id,targetId,previous.state,previous.submitted_at,previous.created_at,previous.updated_at]);
    } else await client.query('DELETE FROM applications WHERE opportunity_id=$1',[targetId]);

    const snapshot=merge.target_snapshot;
    await client.query('UPDATE opportunities SET availability=$2,review_state=$3,notes=$4,state_changed_at=$5,rejection_reason_id=$6,version=version+1,updated_at=now() WHERE id=$1',[targetId,snapshot.availability,snapshot.review_state,snapshot.notes,snapshot.state_changed_at,snapshot.rejection_reason_id ?? null]);
    await client.query('UPDATE opportunities SET version=version+1,updated_at=now() WHERE id=$1',[source.id]);
    if(merge.reparented_merges.length) {
      const restored=await client.query("UPDATE opportunity_merges SET target_id=$2 WHERE source_id=ANY($1::uuid[]) AND target_id=$3 AND undone_at IS NULL",[merge.reparented_merges,source.id,targetId]);
      if(restored.rowCount!==merge.reparented_merges.length) throw fail('Cambió una fusión subordinada; no se separaron los procesos.',409);
    }
    await client.query('UPDATE opportunity_merges SET undone_at=now(),undo_reason=$2 WHERE source_id=$1',[source.id,raw.reason]);
    const restoredTargetVersion=target.version+1,restoredSourceVersion=source.version+1;
    for(const [parent,version] of [[targetId,restoredTargetVersion],[source.id,restoredSourceVersion]]) await client.query(`UPDATE opportunity_merges SET target_version_after=$2 WHERE source_id=(SELECT source_id FROM opportunity_merges WHERE target_id=$1 AND undone_at IS NULL ORDER BY created_at DESC,source_id DESC LIMIT 1)`,[parent,version]);
    await recordEvent(client,targetId,'offers_unmerged',{source_id:source.id,source_company:source.company,source_title:source.title,restored_version:restoredTargetVersion},raw.reason);
    await recordEvent(client,source.id,'offers_unmerged',{target_id:targetId,restored_version:restoredSourceVersion},raw.reason);
    return {id:targetId,restored_id:source.id};
  });
}
