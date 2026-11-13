import {publicGet} from './public-http.js';
import {publicationIdentity,samePublication} from './identity.js';
import {cleanUrl} from './domain.js';
export const sourceCatalog={
  arbeitnow:{label:'Arbeitnow',url:'https://www.arbeitnow.com/api/job-board-api'},
  arbeitnow_uk:{label:'Arbeitnow UK',url:'https://www.arbeitnow.co.uk/api/job-board-api'},
  remotive:{label:'Remotive',url:'https://remotive.com/api/remote-jobs?category=software-dev'}
};
export function sourceSpec(source) {
 if(Object.hasOwn(sourceCatalog,source)) return sourceCatalog[source];
 const match=typeof source==='string' && source.match(/^smartrecruiters:([a-z0-9_-]{1,100})(?::([a-z]{2}))?$/i);
 if(!match) throw new Error('Fuente no admitida');
 const url=new URL(`https://api.smartrecruiters.com/v1/companies/${encodeURIComponent(match[1])}/postings`);url.searchParams.set('limit','100');if(match[2]) url.searchParams.set('country',match[2].toLowerCase());
 return {label:`SmartRecruiters · ${match[1]}`,url:url.href,tenant:match[1],country:match[2]?.toLowerCase()};
}
export function supportedSource(source) {try {sourceSpec(source);return true;}catch{return false;}}
export function plainText(html) {
  return String(html || '').replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&#(x[\da-f]+|\d+);/gi,(_,code)=>{const n=code[0].toLowerCase()==='x'?parseInt(code.slice(1),16):Number(code);return n>0 && n<=0x10ffff?String.fromCodePoint(n):' ';}).replace(/&(amp|lt|gt|quot|apos|nbsp);/g,(_,name)=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '})[name]).replace(/\s+/g,' ').trim();
}
export function parseFeed(source,data) {
  const spec=sourceSpec(source);
  if(spec.tenant) {
   if(!Array.isArray(data.content)) throw new Error('La fuente cambió su formato');
   return data.content.filter(row=>!spec.country || row.location?.country?.toLowerCase()===spec.country).map(row=>{
    if(typeof row.id!=='string' || !/^\d+$/.test(row.id) || typeof row.name!=='string' || !row.company?.name) throw new Error('Pista corporativa incompleta');
    return {source,title:row.name,company:row.company.name,url:`https://jobs.smartrecruiters.com/${encodeURIComponent(spec.tenant)}/${row.id}`,external_id:row.id,description:'',location:row.location?.fullLocation || '',publication:row.releasedDate || null,remote:row.location?.remote===true};
   });
  }
  const rows=source==='remotive'?data.jobs:data.data;
  if (!Array.isArray(rows)) throw new Error('La fuente cambió su formato');
  return rows.map(row=>{
    if (typeof row.title!=='string' || typeof row.company_name!=='string' || typeof row.url!=='string') throw new Error('Pista incompleta en la fuente');
    return {source,title:row.title,company:row.company_name,url:cleanUrl(row.url),external_id:String(row.id ?? row.slug ?? ''),description:plainText(row.description),location:row.candidate_required_location ?? row.location ?? '',publication:row.publication_date ?? null,created_at:row.created_at ?? null,remote:source==='remotive' || row.remote===true};
  });
}
export async function discoverSource(source,get=publicGet,{maxPages=3}={}) {
  const spec=sourceSpec(source);
  if(!Number.isSafeInteger(maxPages) || maxPages<1 || maxPages>100) throw new Error('Límite de páginas inválido');
  let url=spec.url,checked_at,pages=0;const leads=[];
  for(;url && pages<maxPages;pages++) {
   const response=await get(url);
   if(response.status!==200) throw new Error(`${spec.label}: HTTP ${response.status}`);
   const data=JSON.parse(response.text);leads.push(...parseFeed(source,data));checked_at=response.checked_at;
   if(spec.tenant) {
    const current=new URL(url),offset=Number(current.searchParams.get('offset') || 0)+100;
    if(Number(data.totalFound)>offset) {current.searchParams.set('offset',String(offset));url=current.href;} else url=null;
   } else if(source!=='remotive' && data.links?.next) {
    const next=new URL(data.links.next),initial=new URL(spec.url);
    if(next.origin!==initial.origin || next.pathname!==initial.pathname) throw new Error('Paginación de fuente fuera del endpoint permitido');
    url=next.href;
   } else url=null;
  }
  return {source,checked_at,leads,pages,truncated:Boolean(url)};
}
export function readJobPosting(html) {
  const postings=[];
  const visit=value=>{
    if (!value || typeof value!=='object') return;
    if (Array.isArray(value)) {value.forEach(visit);return;}
    if ([value['@type']].flat().includes('JobPosting')) postings.push(value);
    if (value['@graph']) visit(value['@graph']);
  };
  for (const match of html.matchAll(/<script\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)) {
    try {visit(JSON.parse(match[1]));} catch {}
  }
  if (postings.length!==1) return {complete:false,reason:postings.length?'Varias vacantes en la página; identidad pendiente.':'Sin ficha estructurada verificable; conservar como pista.'};
  const job=postings[0],description=plainText(job.description);
  if (typeof job.title!=='string' || description.length<200 || !job.hiringOrganization?.name) return {complete:false,reason:'Descripción estructurada incompleta.'};
  return {complete:true,job,text:JSON.stringify({...job,description},null,2)};
}

export function candidateReadUrl(candidate) {
 const spec=sourceSpec(candidate.source);
 if(!spec.tenant) return candidate.url;
 if(typeof candidate.external_id!=='string' || !/^\d+$/.test(candidate.external_id)) throw new Error('ID público de ficha corporativa inválido');
 return `https://api.smartrecruiters.com/v1/companies/${encodeURIComponent(spec.tenant)}/postings/${candidate.external_id}`;
}
export function readingRoutes(candidate,{alternatives=false}={}) {
 const spec=sourceSpec(candidate.source),identity=publicationIdentity(candidate.url);
 const match=identity?.match(/^smartrecruiters:([a-z0-9_-]+):(\d+)$/i);
 if(!match) {
  if(spec.tenant) throw new Error('La pista corporativa no tiene una identidad pública verificable.');
  return [{format:'html',url:candidateReadUrl(candidate)}];
 }
 const tenant=spec.tenant || match[1],id=spec.tenant?candidate.external_id:match[2];
 const api={format:'smartrecruiters',url:`https://api.smartrecruiters.com/v1/companies/${encodeURIComponent(tenant)}/postings/${id}`,tenant,external_id:id};
 if(!samePublication(api.url,candidate.url)) throw new Error('La pista y la API no identifican el mismo anuncio.');
 const html={format:'html',url:`https://jobs.smartrecruiters.com/${encodeURIComponent(tenant)}/${id}`};
 const routes=spec.tenant || new URL(candidate.url).hostname==='api.smartrecruiters.com'?[api,html]:[{...html,url:candidate.url},api];
 return alternatives?routes:routes.slice(0,1);
}
export function readSourceDocument(candidate,response,route) {
 const spec=route?.format==='smartrecruiters'?{tenant:route.tenant}:sourceSpec(candidate.source);
 const expectedId=route?.external_id || candidate.external_id;
 if(spec.tenant && response.url && !samePublication(response.url,candidate.url)) return {complete:false,reason:'La API redirigió a otra identidad.'};
 if(route?.format==='html' || !spec.tenant) {
  const document=readJobPosting(response.text);
  if(document.complete && publicationIdentity(candidate.url)?.startsWith('smartrecruiters:') &&
   ((response.url && !samePublication(response.url,candidate.url)) || (document.job.url && !samePublication(document.job.url,candidate.url)))) return {complete:false,reason:'La ficha pública no acredita la misma identidad.'};
  return document;
 }
 let data;try{data=JSON.parse(response.text);}catch{return {complete:false,reason:'La API corporativa no devolvió JSON válido.'};}
 if(data.id!==expectedId || data.company?.identifier?.toLowerCase()!==spec.tenant.toLowerCase()) return {complete:false,reason:'La identidad de la ficha no coincide con la pista.'};
 const sections=data.jobAd?.sections || {},description=plainText(sections.jobDescription?.text),qualifications=plainText(sections.qualifications?.text);
 if(typeof data.name!=='string' || typeof data.company?.name!=='string' || description.length<200) return {complete:false,reason:'Ficha corporativa incompleta.'};
 const job={'@type':'JobPosting',title:data.name,hiringOrganization:{name:data.company.name},datePosted:data.releasedDate,jobLocation:{address:{addressCountry:data.location?.country?.toUpperCase(),addressLocality:data.location?.city}},description,qualifications,url:typeof data.postingUrl==='string'?cleanUrl(data.postingUrl):candidate.url};
 const source_payload={id:data.id,name:data.name,company:data.company,location:data.location,releasedDate:data.releasedDate,active:data.active,typeOfEmployment:data.typeOfEmployment,sections};
 const text=[`Empresa: ${data.company.name}`,`Puesto: ${data.name}`,`País de adscripción: ${data.location?.country || 'no indicado'}`,`Ubicación: ${data.location?.fullLocation || ''}`,`Publicado (releasedDate): ${data.releasedDate || 'no indicado'}`,`Relación contractual publicada: ${data.typeOfEmployment?.label || 'no indicada'}`,`Estado activo en API: ${String(data.active)}`,`Modalidad publicada: ${data.location?.remote===true?'remoto':data.location?.hybrid===true?'híbrido':'sin declaración explícita'}`,...Object.entries(sections).map(([name,section])=>`${name}: ${plainText(section.text)}`)].join('\n\n');
 return {complete:true,job,text,source_payload};
}
