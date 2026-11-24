export const sourceCatalog={
  'browser:google':{label:'Google — navegador',engine:'google',url:'https://www.google.com/search'},
  'browser:bing':{label:'Bing — navegador',engine:'bing',url:'https://www.bing.com/search'}
};
export function sourceSpec(source) {
 const spec=sourceCatalog[source];
 if(!spec) throw new Error('Solo se admiten buscadores por navegador');
 return spec;
}
export function supportedSource(source) {return Object.hasOwn(sourceCatalog,source);}
export function browserSearchUrl(source,{term,zone,language}) {
 const spec=sourceSpec(source);
 if(typeof term!=='string' || !term.trim()) throw new Error('Tarea de búsqueda en navegador inválida');
 const suffix=zone==='spain'?' Spain España':zone==='europe'?' Europe jobs':'';
 const url=new URL(spec.url);url.searchParams.set('q',`${term.trim()} ${language==='en'?'job vacancy':'oferta de empleo'}${suffix}`);
 if(spec.engine==='google') url.searchParams.set('hl',language==='en'?'en':'es');
 return url.href;
}
export function plainText(html) {
  return String(html || '').replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&#(x[\da-f]+|\d+);/gi,(_,code)=>{const n=code[0].toLowerCase()==='x'?parseInt(code.slice(1),16):Number(code);return n>0 && n<=0x10ffff?String.fromCodePoint(n):' ';}).replace(/&(amp|lt|gt|quot|apos|nbsp);/g,(_,name)=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '})[name]).replace(/\s+/g,' ').trim();
}
export function readJobPosting(html) {
  const postings=[];
  const visit=value=>{
    if (!value || typeof value!=='object') return;
    if (Array.isArray(value)) {value.forEach(visit);return;}
    if ([value['@type']].flat().includes('JobPosting')) postings.push(value);
    if (value['@graph']) visit(value['@graph']);
  };
  for (const match of String(html || '').matchAll(/<script\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)) {
    try {visit(JSON.parse(match[1]));} catch {}
  }
  if (postings.length!==1) return {complete:false,reason:postings.length?'Varias vacantes en la página; identidad pendiente.':'Sin ficha estructurada verificable; conservar como pista.'};
  const job=postings[0],description=plainText(job.description);
  if (typeof job.title!=='string' || description.length<200 || !job.hiringOrganization?.name) return {complete:false,reason:'Descripción estructurada incompleta.'};
  return {complete:true,job,text:JSON.stringify({...job,description},null,2)};
}
