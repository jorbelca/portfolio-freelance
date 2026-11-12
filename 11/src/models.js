import {readFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
const schema={type:'object',additionalProperties:false,properties:{value:{type:'string'},evidence:{type:'string'},state:{type:'string',enum:['acreditado','desconocido']}},required:['value','evidence','state']};
async function request(path,options={},fetcher=fetch) {
 if(!process.env.OPENAI_API_KEY) throw new Error('Falta OPENAI_API_KEY en 11/.env. Reinicia el servidor después de configurarla.');
 const response=await fetcher(`https://api.openai.com/v1/${path}`,{...options,headers:{Authorization:`Bearer ${process.env.OPENAI_API_KEY}`,'Content-Type':'application/json'},signal:AbortSignal.timeout(Number(process.env.CODEX_TIMEOUT_MS || 120000)),redirect:'error'});
 // No devolver el cuerpo del proveedor: puede contener datos del documento o credenciales.
 if(!response.ok) throw new Error(`OpenAI API: HTTP ${response.status}. Comprueba clave, acceso al modelo y cuota; no se cambia de motor automáticamente.`);
 return response.json();
}
export async function openaiExtraction(prompt,model,fetcher=fetch) {
 if(typeof model!=='string' || !model.trim()) throw new Error('La API requiere un modelo explícito');
 const result=await request('responses',{method:'POST',body:JSON.stringify({model,input:prompt,store:false,text:{format:{type:'json_schema',name:'extraction',strict:true,schema}}})},fetcher);
 if(result.status!=='completed') throw new Error('La API no completó la respuesta');
 const content=(result.output || []).filter(item=>item.type==='message').flatMap(item=>item.content || []);
 if(content.some(item=>item.type==='refusal')) throw new Error('El modelo rechazó la tarea');
 return JSON.parse(content.filter(item=>item.type==='output_text').map(item=>item.text).join(''));
}
export async function modelCatalog() {
 const codex={id:'codex',models:[],message:'No hay catálogo local. Introduce el identificador exacto. La disponibilidad se verifica al ejecutar.'};
 try {
  const cache=JSON.parse(await readFile(join(process.env.CODEX_HOME || join(homedir(),'.codex'),'models_cache.json'),'utf8'));
  codex.models=(cache.models || []).filter(model=>model.visibility==='list' && typeof model.slug==='string').map(model=>({id:model.slug,label:model.display_name || model.slug}));
  codex.message=`Catálogo local de Codex (${cache.fetched_at || 'fecha desconocida'}). Usa tu sesión; el catálogo no garantiza cuota ni acceso actual.`;
 }catch{}
 const openai={id:'openai',models:[],configured:Boolean(process.env.OPENAI_API_KEY),message:'Falta OPENAI_API_KEY en 11/.env. Esta conexión utiliza la cuota y facturación de tu proyecto API.'};
 if(openai.configured) {
  try {const result=await request('models');openai.models=(result.data || []).map(model=>({id:model.id,label:model.id})).sort((a,b)=>a.id.localeCompare(b.id));openai.message='Modelos visibles para tu clave. Elige uno que admita Responses y salida estructurada; no todos son compatibles.';}
  catch {openai.message='No se pudo consultar el catálogo API. Comprueba clave y conexión; puedes introducir el modelo manualmente.';}
 }
 return {providers:[codex,openai]};
}
