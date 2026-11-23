import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js';
import {StreamableHTTPServerTransport} from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import {z} from 'zod';
import {toolEndpoints,httpEndpoints} from './api-catalog.js';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {availabilityStates,reviewStates,applicationStates,actionStates} from './domain.js';

const uuid=z.string().uuid();
const revision=z.number().int().positive();
const publicUrl=z.string().url().refine(value=>/^https?:\/\//.test(value),'Usa http o https');
const page={limit:z.number().int().min(1).max(100).default(25),offset:z.number().int().min(0).default(0)};
const offerSchema=z.object({company:z.string().trim().min(1).max(500),company_id:uuid.nullable().optional(),title:z.string().trim().min(1).max(500),url:publicUrl.optional(),availability:z.enum(availabilityStates),review_state:z.enum(reviewStates),application_state:z.enum(applicationStates),submitted_at:z.string().datetime().nullable().optional(),rejection_reason_id:uuid.nullable().optional(),notes:z.string().max(20000).optional(),reason:z.string().max(20000).optional()}).strict();
const actionSchema={description:z.string().trim().min(1).max(20000),due_on:z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),state:z.enum(actionStates)};
const errorSchema=z.object({code:z.string(),status:z.number().int(),message:z.string(),recovery:z.string(),retryable:z.boolean(),target_id:uuid.optional()});
const outputSchema={ok:z.boolean(),data:z.unknown().optional(),error:errorSchema.optional()};
const instructions='Gestiona únicamente el seguimiento de postulaciones. Consulta get_catalogs y lee la versión antes de modificar una oferta o acción. Ante un conflicto, relee y revisa el cambio. No inventes datos ni envíes candidaturas.';

export function integrationInfo(origin) {
  return {endpoint:`${origin}/mcp`,transports:['stdio','streamable-http'],authentication:'Bearer MCP_TOKEN (solo servidor; no se muestra en la web)',configured:Boolean(process.env.MCP_TOKEN),
    stdio:{mcpServers:{empleo:{command:process.execPath,args:[fileURLToPath(new URL('./mcp-stdio.js',import.meta.url))]}}},
    http:{url:`${origin}/mcp`,headers:{Authorization:'Bearer <MCP_TOKEN de 11/.env>'}},guide:'/MCP.md',...integrationCatalog()};
}

export function apiClient({baseUrl,token,fetchImpl=fetch}) {
  const base=new URL(baseUrl);
  if (!['http:','https:'].includes(base.protocol) || base.username || base.password) throw new Error('EMPLEO_API_URL inválida');
  return async (path,method='GET',value) => {
    let response;
    try {
      response=await fetchImpl(new URL(`/api/${path}`,base),{method,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:value===undefined?undefined:JSON.stringify(value),signal:AbortSignal.timeout(15000),redirect:'error'});
    } catch {
      throw Object.assign(new Error('No se pudo confirmar la respuesta del servicio. Consulta el estado antes de repetir cambios.'),{status:0});
    }
    const result=await response.json();
    if (!response.ok) throw Object.assign(new Error(result.error || 'La operación falló'),{status:response.status,target_id:response.status===410?result.target_id:undefined});
    return result;
  };
}
function toolError(error) {
  const status=error.status || 0;
  const code=({400:'INVALID_INPUT',401:'UNAUTHORIZED',403:'FORBIDDEN',404:'NOT_FOUND',409:'CONFLICT',410:'MERGED',413:'INPUT_TOO_LARGE',429:'BUSY',503:'UNAVAILABLE'})[status] || 'RESULT_UNCONFIRMED';
  const recovery=status===410?'Consulta get_offer con target_id: es el registro principal conservado.':status===409?'Consulta de nuevo revision/version y el estado actual. Revisa el cambio antes de reenviarlo.':status===401||status===403?'Revisa MCP_TOKEN en el cliente y el servidor.':status===404?'Consulta el listado y usa un ID existente.':status===400||status===413?'Corrige los argumentos según el esquema de la herramienta.':'Consulta el estado del workflow y la ejecución. No repitas automáticamente una escritura no confirmada.';
  const data={ok:false,error:{code,status,message:error.message,recovery,retryable:false,...(status===410 && uuid.safeParse(error.target_id).success?{target_id:error.target_id}:{})}};
  return {isError:true,structuredContent:data,content:[{type:'text',text:JSON.stringify(data)}]};
}
const query=input=>new URLSearchParams(Object.fromEntries(Object.entries(input).filter(([,v])=>v!==undefined).map(([k,v])=>[k,String(v)]))).toString();
const nonempty=schema=>schema.refine(value=>Object.keys(value).length>0,'Indica al menos un cambio');

export function integrationCatalog() {
  const tools=[];
  createMcpServer({catalog:tools});
  return {tools,http_endpoints:httpEndpoints};
}

export function createMcpServer({request,readOnly=false,catalog}) {
  const server=catalog?null:new McpServer({name:'empleo-workflow',version:'1.0.0'},{instructions,maxToolInputElements:200});
  function tool(name,description,inputSchema,read,handler,idempotent=read) {
    if (readOnly && !read) return;
    if (catalog) {
      const [method,path,returns]=toolEndpoints[name];
      catalog.push({name,description,method,path,returns,readOnly:read,inputSchema:z.toJSONSchema(z.object(inputSchema).strict(),{target:'draft-7',io:'input'})});
      return;
    }
    server.registerTool(name,{description,inputSchema:z.object(inputSchema).strict(),outputSchema,annotations:{readOnlyHint:read,destructiveHint:!read,idempotentHint:idempotent,openWorldHint:false}},async args=>{
      try {const data={ok:true,data:await handler(args)}; return {structuredContent:data,content:[{type:'text',text:JSON.stringify(data)}]};} catch(error) {return toolError(error);}
    });
  }
  const list=async(path,args)=>({items:await request(`${path}?${query(args)}`),limit:args.limit,offset:args.offset,next_offset:null});
  const paged=async(path,args)=>{const result=await list(path,args); if(result.items.length===args.limit) result.next_offset=args.offset+args.limit; return result;};
  tool('get_catalogs','Devuelve los estados válidos. No deduzcas estados por sus etiquetas visuales.',{},true,()=>request('catalogs'));
  tool('list_offers','Lista procesos del seguimiento con paginación y filtros opcionales. No crea ofertas.',{...page,q:z.string().max(500).optional(),application_state:z.enum(applicationStates).optional()},true,args=>paged('offers',args));
  tool('get_offer','Obtiene un proceso, sus estados independientes y version actual.',{id:uuid},true,({id})=>request(`offers/${id}`));
  tool('list_companies','Lista empresas con IDs reutilizables. Nombres iguales no prueban identidad.',{...page,q:z.string().max(500).optional()},true,args=>paged('companies',args));
  tool('list_rejection_reasons','Lista las causas de rechazo reutilizables con su ID.',page,true,args=>paged('rejection-reasons',args));
  tool('create_rejection_reason','Añade una causa genérica si falta en el catálogo. Devuelve la existente si ya tiene el mismo nombre.',{name:z.string().trim().min(1).max(100)},false,args=>request('rejection-reasons','POST',args));
  tool('create_offer','Registra una oferta real. Si el estado es rechazado, incluye rejection_reason_id del catálogo. Usa company_id si ya conoces la empresa. No envía candidaturas. Si se pierde la respuesta, consulta historial y listado antes de volver a crear.',{offer:offerSchema},false,({offer})=>request('offers','POST',offer));
  tool('patch_offer','Cambia solo campos indicados con expected_version de get_offer. Para cambiar estados incluye reason. Para pasar a rechazado, incluye rejection_reason_id del catálogo (o conserva una causa ya asignada). Conserva el resto de datos y los bloqueos de candidaturas previas.',{id:uuid,expected_version:revision,patch:nonempty(offerSchema.omit({url:true}).partial())},false,({id,expected_version,patch})=>request(`offers/${id}`,'PATCH',{version:expected_version,patch}));
  tool('check_offers_batch','Comprueba hasta 100 URLs antes de abrir o analizar ofertas. applied=true confirma una candidatura registrada por URL o ID público exacto, incluidos enlaces alternativos. false solo indica ausencia de coincidencia confirmada en Neon; no deduzcas que nunca se postuló. Un fallo no equivale a false.',{urls:z.array(publicUrl.max(2000)).min(1).max(100)},true,args=>request('offers/check-batch','POST',args));
  tool('check_history','Cruza URL o empresa/título antes de investigar o registrar una oferta. needs_review no confirma identidad; excluded y already_known evitan repeticiones.',{url:publicUrl.optional(),company:z.string().max(500).optional(),title:z.string().max(500).optional()},true,args=>{
    if(!args.url && !(args.company && args.title)) throw Object.assign(new Error('Indica URL o empresa y título.'),{status:400});
    return request('history/check','POST',args);
  });
  for(const [name,section,description] of [['list_offer_events','events','Consulta el historial del proceso.'],['list_publications','publications','Consulta enlaces alternativos del mismo proceso.'],['list_actions','actions','Consulta acciones de seguimiento con ID, estado y version.']]) tool(name,description,{offer_id:uuid,...page},true,({offer_id,...args})=>paged(`offers/${offer_id}/${section}`,args));
  tool('add_publication','Añade un enlace público alternativo a un proceso. No fusiona procesos distintos.',{offer_id:uuid,url:publicUrl},false,({offer_id,url})=>request(`offers/${offer_id}/publications`,'POST',{url}));
  tool('merge_offers','Fusiona dos procesos confirmados como idénticos. Conserva archivo, enlaces, acciones e historial; elige explícitamente qué candidatura sigue vigente. Lee ambas versiones primero.',{target_id:uuid,source_id:uuid,expected_version:revision,source_version:revision,application_from:z.enum(['target','source']),reason:z.string().trim().min(1).max(2000)},false,({target_id,expected_version,...input})=>request(`offers/${target_id}/merge`,'POST',{version:expected_version,...input}));
  tool('list_offer_merges','Lista fusiones activas de un proceso e indica si la más reciente todavía se puede deshacer.',{offer_id:uuid},true,({offer_id})=>request(`offers/${offer_id}/merges`));
  tool('unmerge_offer','Deshace la fusión reversible más reciente. Lee list_offer_merges y ambas versiones; no se permite si hay cambios posteriores.',{target_id:uuid,source_id:uuid,expected_version:revision,source_version:revision,reason:z.string().trim().min(1).max(2000)},false,({target_id,source_id,expected_version,source_version,reason})=>request(`offers/${target_id}/unmerge/${source_id}`,'POST',{version:expected_version,source_version,reason}));
  tool('create_action','Crea una acción de seguimiento. Ante respuesta perdida, consulta list_actions antes de repetir.',{offer_id:uuid,...actionSchema},false,({offer_id,...input})=>request(`offers/${offer_id}/actions`,'POST',input));
  tool('update_action','Actualiza una acción con su version; usa list_actions para leerla antes.',{offer_id:uuid,action_id:uuid,expected_version:revision,...actionSchema},false,({offer_id,action_id,expected_version,...input})=>request(`offers/${offer_id}/actions/${action_id}`,'PUT',{version:expected_version,...input}));
  if (catalog) return;
  server.registerResource('guide','empleo://guide',{description:'Guía operativa de MCP, límites y recuperación de errores.',mimeType:'text/markdown'},async uri=>({contents:[{uri:uri.href,mimeType:'text/markdown',text:await readFile(new URL('../MCP.md',import.meta.url),'utf8')}]}));
  server.registerResource('catalogs','empleo://catalogs',{mimeType:'application/json'},async uri=>({contents:[{uri:uri.href,mimeType:'application/json',text:JSON.stringify(await request('catalogs'))}]}));
  return server;
}

export async function handleMcpHttp(req,res,parsedBody,origin) {
  const server=createMcpServer({request:apiClient({baseUrl:origin,token:process.env.MCP_TOKEN})});
  const transport=new StreamableHTTPServerTransport({sessionIdGenerator:undefined,enableJsonResponse:true});
  res.on('close',()=>{void server.close();});
  await server.connect(transport);
  await transport.handleRequest(req,res,parsedBody);
}
