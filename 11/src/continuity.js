import {randomUUID} from 'node:crypto';
import {isDeepStrictEqual} from 'node:util';
import {publicationIdentity,samePublication} from './identity.js';
import {cleanUrl} from './domain.js';
import {validateExtraction} from './codex.js';
export const publicationKey=url=>publicationIdentity(url) || `url:${cleanUrl(url)}`;
export async function previousCandidate(client,runId,lead) {
 const rows=(await client.query(`SELECT c.id,c.run_id,c.process_id,c.url,c.opportunity_id,c.identity_resolution,
  ARRAY(SELECT url FROM search_candidate_links WHERE candidate_id=c.id) AS links
  FROM search_candidates c WHERE c.run_id<>$1 AND c.identity_resolution<>'duplicate'
  AND (c.publication_key=$2 OR c.url=$3 OR c.publication_key IS NULL
   OR EXISTS(SELECT 1 FROM search_candidate_links l WHERE l.candidate_id=c.id AND (l.url=$3 OR l.publication_key=$2))) ORDER BY c.created_at DESC,c.id DESC`,[runId,publicationKey(lead.url),lead.url])).rows;
 return rows.find(row=>samePublication(row.url,lead.url) || row.links.some(url=>samePublication(url,lead.url)));
}
export async function insertCandidate(client,run,lead,{prior,rank=0}={}) {
 prior ??= await previousCandidate(client,run.id,lead);
 const id=randomUUID();
 const processId=prior?.process_id || prior?.id || id;
 const links=new Set([lead.url,...(prior?.links || [])]);
 const current=(await client.query("SELECT id FROM search_candidates WHERE run_id=$1 AND COALESCE(process_id,id)=$2 AND identity_resolution<>'duplicate' ORDER BY created_at,id LIMIT 1",[run.id,processId])).rows[0];
 if(current) {
  for(const url of links) await client.query('INSERT INTO search_candidate_links(candidate_id,url,publication_key) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',[current.id,url,publicationKey(url)]);
  return null;
 }
 const inserted=await client.query(`INSERT INTO search_candidates(id,run_id,source,external_id,url,company,title,hint,process_id,prior_candidate_id,publication_key,opportunity_id,identity_resolution)
  VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) ON CONFLICT(run_id,url) DO NOTHING RETURNING id`,
 [id,run.id,lead.source,lead.external_id || '',lead.url,lead.company.slice(0,500),lead.title.slice(0,500),{...lead,discovery_order:rank},processId,prior?.id || null,publicationKey(lead.url),prior?.opportunity_id || null,prior?.identity_resolution || 'pending']);
 if(!inserted.rowCount) return null;
 for(const url of links) await client.query('INSERT INTO search_candidate_links(candidate_id,url,publication_key) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',[id,url,publicationKey(url)]);
 return id;
}
export async function previousFinalists(client,run) {
 const profile=run.settings_snapshot.search_config.value;
 const rows=(await client.query(`SELECT * FROM (
  SELECT DISTINCT ON (COALESCE(c.process_id,c.id)) c.id,c.process_id,c.run_id,c.source,c.external_id,c.url,c.company,c.title,c.opportunity_id,c.identity_resolution,c.evaluation,c.created_at,
   ARRAY(SELECT url FROM search_candidate_links WHERE candidate_id=c.id) AS links
  FROM search_candidates c WHERE c.run_id<>$1 AND c.identity_resolution<>'duplicate' AND c.evaluation IS NOT NULL ORDER BY COALESCE(c.process_id,c.id),c.created_at DESC,c.id DESC
 ) latest WHERE evaluation->>'classification' IN ('A','B') AND source=ANY($2::text[]) AND title ILIKE ANY($3::text[])
 ORDER BY CASE evaluation->>'classification' WHEN 'A' THEN 0 ELSE 1 END,created_at DESC,id DESC`,[run.id,profile.sources.filter(row=>row.enabled).map(row=>row.source),profile.queries.map(row=>`%${row.term.replace(/[\\%_]/g,'\\$&')}%`)])).rows;
 const seen=new Map(),finalists=[];
 for(const row of rows) {
  const keys=new Set([`process:${row.process_id || row.id}`,...[row.url,...row.links].map(publicationKey)]);
  if([...keys].some(key=>seen.has(key))) continue;
  finalists.push(row);for(const key of keys) seen.set(key,row);
 }
 return {rows:finalists.slice(0,run.settings_snapshot.max_openings),truncated:finalists.length>run.settings_snapshot.max_openings};
}
export async function inheritCorrections(client,run,candidate,document) {
 if(!candidate.prior_candidate_id) return;
 const prior=(await client.query('SELECT d.text,r.settings_snapshot FROM search_documents d JOIN search_candidates c ON c.id=d.candidate_id JOIN workflow_runs r ON r.id=c.run_id WHERE d.candidate_id=$1',[candidate.prior_candidate_id])).rows[0];
 const corrections=(await client.query('SELECT * FROM search_candidate_overrides WHERE candidate_id=$1',[candidate.prior_candidate_id])).rows;
 if(!corrections.length) return;
 const sameText=prior?.text===document.text,sameProfile=isDeepStrictEqual(prior?.settings_snapshot?.search_config?.value,run.settings_snapshot.search_config.value);
 const inherited=[];
 for(const correction of corrections) {
  if(!sameText || !document.text.includes(correction.evidence) || (!['country','publication'].includes(correction.field) && !sameProfile)) continue;
  await client.query('INSERT INTO search_candidate_overrides(candidate_id,field,value,evidence,reason) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',[candidate.id,correction.field,correction.value,correction.evidence,correction.reason]);
  inherited.push(correction.field);
 }
 await client.query("INSERT INTO search_candidate_events(candidate_id,kind,value,reason) VALUES($1,'continuity',$2,$3)",[candidate.id,{prior_candidate_id:candidate.prior_candidate_id,inherited,not_reused:corrections.filter(row=>!inherited.includes(row.field)).map(row=>row.field)},'Correcciones previas comprobadas contra la ficha y el perfil actuales; las no reutilizadas conservan su evidencia en la observación anterior.']);
}
export async function reusableExtraction(client,run,candidate,kind,text) {
 if(!run.settings_snapshot.search_config.value.reuse_evidence || !candidate.prior_candidate_id || !run.settings_snapshot.analysis_contract) return null;
 const prior=(await client.query(`SELECT s.id,s.result FROM search_steps s JOIN search_candidates c ON c.id=s.candidate_id
  JOIN workflow_runs r ON r.id=c.run_id JOIN search_documents d ON d.candidate_id=c.id
  WHERE c.id=$1 AND s.kind=$2 AND s.status='succeeded' AND d.status='complete' AND d.text=$3 AND r.settings_snapshot->>'analysis_contract'=$4`,[candidate.prior_candidate_id,kind,text,run.settings_snapshot.analysis_contract])).rows[0];
 if(!prior?.result || prior.result.skipped) return null;
 try {validateExtraction(prior.result,text);return prior;} catch {return null;}
}
