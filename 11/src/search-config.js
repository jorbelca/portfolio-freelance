import {z} from 'zod';
import {randomUUID} from 'node:crypto';
import {pool,transaction} from './db.js';
import {supportedSource} from './sources.js';
import {decisionRules} from './evaluation.js';
const short=z.string().trim().min(1).max(200);
export const searchConfigSchema=z.object({
 recover_previous:z.boolean().optional(),reuse_evidence:z.boolean().optional(),
 fit_instruction:z.string().trim().min(1).max(8000).optional(),
 residence:z.string().trim().min(1).max(1000),technical_degree:z.boolean(),professional_years:z.number().min(0).max(80).nullable(),
 internship_details:z.string().max(4000),relocation:z.enum(['si','no','desconocido']),work_authorization:z.string().max(4000),max_required_years:z.number().int().min(0).max(80),
 skills:z.array(z.object({name:short,evidence:z.string().trim().min(1).max(2000),priority:z.number().int().min(1).max(100)}).strict()).min(1).max(200),
 qualifications:z.array(z.string().trim().min(1).max(500)).max(100),
 languages:z.array(z.object({language:z.string().trim().min(1).max(100),level:z.enum(['A1','A2','B1','B2','C1','C2','nativo'])}).strict()).max(50),
 sources:z.array(z.object({source:z.string().max(200).refine(supportedSource,'Fuente no admitida'),enabled:z.boolean(),max_pages:z.number().int().min(1).max(100).default(3)}).strict()).min(1).max(50),
 queries:z.array(z.object({zone:z.enum(['spain','europe','any']),language:z.enum(['es','en']),term:short}).strict()).min(1).max(100),
 criteria:z.array(z.object({id:z.enum(decisionRules.map(rule=>rule.id)),label:short,instruction:z.string().trim().min(1).max(8000),pending:z.string().trim().min(1).max(1000)}).strict()).length(decisionRules.length).optional(),
 excluded_employers:z.array(z.string().trim().min(1).max(500)).max(100)
}).strict().superRefine((value,ctx)=>{
 if(value.criteria && new Set(value.criteria.map(rule=>rule.id)).size!==decisionRules.length) ctx.addIssue({code:'custom',path:['criteria'],message:'Incluye cada criterio exactamente una vez'});
 for (const [key,items] of Object.entries({skills:value.skills.map(row=>row.name),qualifications:value.qualifications,languages:value.languages.map(row=>row.language),sources:value.sources.map(row=>row.source),queries:value.queries.map(row=>`${row.zone}:${row.language}:${row.term}`),excluded_employers:value.excluded_employers})) {
  if (new Set(items.map(item=>item.toLowerCase())).size!==items.length) ctx.addIssue({code:'custom',path:[key],message:'Hay valores duplicados'});
 }
 if (!value.sources.some(row=>row.enabled)) ctx.addIssue({code:'custom',path:['sources'],message:'Habilita al menos una fuente'});
});
export async function getSearchConfig(client=pool) {
 if (client===pool) return transaction(async scoped=>{await scoped.query('SELECT id FROM search_configuration WHERE id=1 FOR SHARE');return getSearchConfig(scoped);});
 const row=(await client.query('SELECT * FROM search_configuration WHERE id=1')).rows[0];
 const value={...row,professional_years:row.professional_years===null?null:Number(row.professional_years)};delete value.id;delete value.revision;
 value.skills=(await client.query('SELECT name,evidence,priority FROM profile_skills WHERE configuration_id=1 ORDER BY priority,name')).rows;
 value.qualifications=(await client.query('SELECT name FROM profile_qualifications WHERE configuration_id=1 ORDER BY name')).rows.map(row=>row.name);
 value.languages=(await client.query('SELECT language,level FROM profile_languages WHERE configuration_id=1 ORDER BY language')).rows;
 value.sources=(await client.query('SELECT source,enabled,max_pages FROM search_source_settings WHERE configuration_id=1 ORDER BY source')).rows;
 value.queries=(await client.query('SELECT zone,language,term FROM search_queries WHERE configuration_id=1 ORDER BY zone,language,term')).rows;
 value.excluded_employers=(await client.query('SELECT name FROM excluded_employers WHERE configuration_id=1 ORDER BY name')).rows.map(row=>row.name);
 const criteria=(await client.query('SELECT rule_id AS id,label,instruction,pending FROM search_criteria WHERE configuration_id=1')).rows;
 value.criteria=decisionRules.map(rule=>criteria.find(saved=>saved.id===rule.id) || {...rule});
 return {revision:row.revision,value};
}
export async function saveSearchConfig(raw) {
 if (!Number.isSafeInteger(raw?.revision)) throw new Error('Falta la revisión de configuración');
 const result=searchConfigSchema.safeParse(raw.value);
 if (!result.success) throw new Error(result.error.issues.map(issue=>`${issue.path.join('.')}: ${issue.message}`).join('; '));
 const value=result.data;
 return transaction(async client=>{
  const current=(await client.query('SELECT revision FROM search_configuration WHERE id=1 FOR UPDATE')).rows[0];
  if (current.revision!==raw.revision) throw Object.assign(new Error('La configuración ha cambiado. Recarga antes de guardar.'),{status:409});
  await client.query('UPDATE search_configuration SET revision=revision+1,residence=$1,technical_degree=$2,professional_years=$3,internship_details=$4,relocation=$5,work_authorization=$6,max_required_years=$7,fit_instruction=COALESCE($8,fit_instruction),recover_previous=COALESCE($9,recover_previous),reuse_evidence=COALESCE($10,reuse_evidence) WHERE id=1',[value.residence,value.technical_degree,value.professional_years,value.internship_details,value.relocation,value.work_authorization,value.max_required_years,value.fit_instruction,value.recover_previous,value.reuse_evidence]);
  for (const table of ['profile_skills','profile_qualifications','profile_languages','search_source_settings','search_queries','excluded_employers']) await client.query(`DELETE FROM ${table} WHERE configuration_id=1`);
  for (const row of value.skills) await client.query('INSERT INTO profile_skills VALUES(1,$1,$2,$3)',[row.name,row.evidence,row.priority]);
  for (const name of value.qualifications) await client.query('INSERT INTO profile_qualifications VALUES(1,$1)',[name]);
  for (const row of value.languages) await client.query('INSERT INTO profile_languages VALUES(1,$1,$2)',[row.language,row.level]);
  for (const row of value.sources) await client.query('INSERT INTO search_source_settings(configuration_id,source,enabled,max_pages) VALUES(1,$1,$2,$3)',[row.source,row.enabled,row.max_pages]);
  for (const row of value.queries) await client.query('INSERT INTO search_queries VALUES($1,1,$2,$3,$4)',[randomUUID(),row.zone,row.language,row.term]);
  for (const name of value.excluded_employers) await client.query('INSERT INTO excluded_employers VALUES(1,$1)',[name]);
  if(value.criteria) {
   for(const rule of value.criteria) await client.query('INSERT INTO search_criteria(configuration_id,rule_id,label,instruction,pending) VALUES(1,$1,$2,$3,$4) ON CONFLICT(configuration_id,rule_id) DO UPDATE SET label=excluded.label,instruction=excluded.instruction,pending=excluded.pending',[rule.id,rule.label,rule.instruction,rule.pending]);
  }
  return getSearchConfig(client);
 });
}
