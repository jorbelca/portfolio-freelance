import {offerStates,offerState,statePatch} from './offer-state.js';
const $ = selector => document.querySelector(selector);
let offers=[], companies=[], selected=null, settings, workflow, runs=[], posting=false, requestId=null, selectedRunId=null;
const fields=['company','company_id','title','url','notes'];
function message(text) { $('#message').textContent=text; }
async function api(path,method='GET',value) {
  const response=await fetch(`/api/${path}`,{method,headers:{'Content-Type':'application/json','X-Empleo-Client':'panel'},body:value===undefined?undefined:JSON.stringify(value)});
  const result=await response.json();
  if (!response.ok) throw new Error(result.error);
  return result;
}
function option(select,value,label=value) {
  const element=document.createElement('option'); element.value=value; element.textContent=label.replaceAll('_',' '); select.append(element);
}
function displayDate(value,dateOnly=false) {
  return value ? new Date(value).toLocaleDateString('es-ES',dateOnly?{timeZone:'UTC'}:undefined) : 'Sin fecha';
}
function render() {
  $('#offer-editor-home').append($('#offer-editor'));
  $('#offers').replaceChildren();
  const visible=offers.filter(item=>!$('#filter').value || offerState(item)===$('#filter').value);
  if (!visible.length) {
    const row=document.createElement('tr'), cell=document.createElement('td'); cell.colSpan=6; cell.textContent='Sin ofertas para mostrar.'; row.append(cell); $('#offers').append(row);
  }
  $('#count-all').textContent=offers.length;
  $('#count-pending').textContent=offers.filter(item=>offerState(item)==='pendiente').length;
  $('#count-active').textContent=offers.filter(item=>offerState(item)==='inscrita').length;
  for (const offer of visible) {
    const row=document.createElement('tr'); row.dataset.offerId=offer.id; row.dataset.offerState=offerState(offer);
    for (const value of [offer.company,offer.title,'']) {
      const cell=document.createElement('td'); cell.textContent=value.replaceAll('_',' '); row.append(cell);
    }
    const stateSelect=document.createElement('select');
    stateSelect.id=`offer-${offer.id}-application-state`;
    stateSelect.dataset.tool='patch_offer';
    stateSelect.setAttribute('aria-label',`Estado de postulación: ${offer.title} · ${offer.company}`);
    for (const [state,label] of Object.entries(offerStates)) {
      option(stateSelect,state,label);
      stateSelect.lastElementChild.disabled=state==='pendiente' && offer.application_state!=='sin_candidatura';
    }
    stateSelect.value=offerState(offer);
    stateSelect.onchange=async()=>{
      const next=stateSelect.value;
      if (next===offerState(offer)) return;
      stateSelect.disabled=true;
      try {
        await api(`offers/${offer.id}`,'PATCH',{version:offer.version,patch:statePatch(offer,next)});
        if (selected?.id===offer.id) await refreshSelected(); else await load();
        message('Estado de postulación guardado.');
      } catch(error) {stateSelect.value=offerState(offer); message(error.message);}
      finally {stateSelect.disabled=false;}
    };
    row.children[2].replaceChildren(stateSelect);
    const dates=document.createElement('td'); dates.className='offer-dates';
    for (const [label,value,dateOnly] of [['Alta',offer.created_at,false],['Inscripción',offer.submitted_at,true],['Estado',offer.state_changed_at,false]]) {
      if (!value) continue;
      const line=document.createElement('div'); line.textContent=`${label}: ${displayDate(value,dateOnly)}`; dates.append(line);
    }
    row.append(dates);
    const links=document.createElement('td'); links.className='offer-links';
    for (const publication of offer.publications || []) {
      const link=document.createElement('a'); link.href=publication.url;
      link.textContent=new URL(publication.url).hostname.replace(/^www\./,'');
      link.target='_blank'; link.rel='noopener noreferrer'; links.append(link);
    }
    if (!links.childElementCount) links.textContent='Sin enlaces';
    row.append(links);
    const cell=document.createElement('td'), button=document.createElement('button'); button.textContent=selected?.id===offer.id?'Cerrar':'Detalles';
    button.type='button'; button.setAttribute('aria-expanded',String(selected?.id===offer.id));
    button.setAttribute('aria-controls','offer-editor');
    button.id=`offer-${offer.id}-open`;
    button.onclick=async()=>{try {if (selected?.id===offer.id) {$('#reset').click(); return;} await selectOffer(offer); render(); $('#offer-editor').scrollIntoView({behavior:'smooth',block:'nearest'});} catch(error) {message(error.message);}};
    cell.append(button); row.append(cell); $('#offers').append(row);
    if (selected?.id===offer.id) {
      const detailRow=document.createElement('tr'), detailCell=document.createElement('td');
      detailRow.dataset.offerDetail=offer.id; detailCell.colSpan=6;
      detailCell.append($('#offer-editor')); detailRow.append(detailCell); $('#offers').append(detailRow);
    }
  }
}
async function load() {
  [offers,companies]=await Promise.all([api('offers'),api('companies')]);
  const select=$('[name=company_id]'); select.replaceChildren(); option(select,'','Crear empresa');
  for (const company of companies) option(select,company.id,`${company.name} · ${company.id.slice(0,8)}`);
  render();
}
async function selectOffer(offer) {
  selected=offer;
  for (const key of fields) $('[name='+key+']').value=offer[key] || '';
  $('[name=submitted_on]').value=offer.submitted_at?.slice(0,10) || '';
  $('[name=company]').readOnly=true;
  $('[name=status]').value=offerState(offer);
  $('[name=status] option[value=pendiente]').disabled=offer.application_state!=='sin_candidatura';
  $('[name=url]').readOnly=true;
  $('#form-title').textContent='Gestionar proceso';
  $('#offer-detail').hidden=false;
  const [events,publications,actions]=await Promise.all([api(`offers/${offer.id}/events`),api(`offers/${offer.id}/publications`),api(`offers/${offer.id}/actions`)]);
  $('#events').textContent=JSON.stringify(events,null,2);
  $('#publications').replaceChildren();
  for (const p of publications) {
    const li=document.createElement('li'), a=document.createElement('a'); a.href=p.url; a.textContent=p.url; a.target='_blank'; a.rel='noopener noreferrer'; li.append(a); $('#publications').append(li);
  }
  $('#actions').replaceChildren();
  for (const action of actions) {
    const li=document.createElement('li'); li.textContent=`${action.description} · ${action.due_on?.slice(0,10) || 'Sin fecha'} · ${action.state} `;
    li.dataset.actionId=action.id; li.dataset.state=action.state;
    for (const state of action.state==='pendiente'?['completada','cancelada']:['pendiente']) {
      const button=document.createElement('button'); button.type='button'; button.textContent=state==='pendiente'?'Reabrir':state==='completada'?'Completar':'Cancelar';
      button.id=`action-${action.id}-${state}`;
      button.onclick=async()=>{try {await api(`offers/${offer.id}/actions/${action.id}`,'PUT',{...action,due_on:action.due_on?.slice(0,10),state}); await refreshSelected();} catch(error) {message(error.message);}};
      li.append(button);
    }
    $('#actions').append(li);
  }
  if (!actions.length) $('#actions').textContent='No hay acciones registradas.';
}
async function refreshSelected() {
  const id=selected.id; await load(); await selectOffer(offers.find(item=>item.id===id));
}
$('[name=company_id]').onchange=event=>{
  const company=companies.find(item=>item.id===event.target.value);
  $('[name=company]').value=company?.name || ''; $('[name=company]').readOnly=Boolean(company);
};
$('#filter').onchange=render;
$('#reset').onclick=()=>{
  selected=null; $('#offer-form').reset(); $('[name=status] option[value=pendiente]').disabled=false; $('[name=company]').readOnly=false; $('[name=url]').readOnly=false;
  $('#form-title').textContent='Registrar oferta'; $('#events').textContent='Selecciona una oferta.'; $('#offer-detail').hidden=true; render();
};
$('#offer-form').onsubmit=async event=>{
  event.preventDefault(); const value=Object.fromEntries(new FormData(event.target));
  try {
    Object.assign(value,{availability:selected?.availability || 'desconocida',review_state:selected?.review_state || 'nueva',application_state:selected?.application_state || 'sin_candidatura'},statePatch(selected,value.status));
    if (value.submitted_on !== (selected?.submitted_at?.slice(0,10) || '')) value.submitted_at=value.submitted_on?`${value.submitted_on}T00:00:00.000Z`:null;
    delete value.submitted_on;
    delete value.status;
    if (selected) {value.version=selected.version; await api(`offers/${selected.id}`,'PUT',value);} else await api('offers','POST',value);
    if (selected) await refreshSelected(); else {$('#reset').click(); await load();} message('Proceso e historial guardados.');
  } catch(error) {message(error.message);}
};
$('#publication-form').onsubmit=async event=>{
  event.preventDefault(); if (!selected) return;
  try {await api(`offers/${selected.id}/publications`,'POST',Object.fromEntries(new FormData(event.target))); event.target.reset(); await refreshSelected(); message('Publicación añadida al mismo proceso.');} catch(error) {message(error.message);}
};
$('#action-form').onsubmit=async event=>{
  event.preventDefault(); if (!selected) return;
  try {await api(`offers/${selected.id}/actions`,'POST',{...Object.fromEntries(new FormData(event.target)),state:'pendiente'}); event.target.reset(); await refreshSelected(); message('Acción guardada.');} catch(error) {message(error.message);}
};
const numericSettings=['max_openings','batch_size','max_age_days','quota_spain','quota_europe'];
function showSettings() {
  for (const [key,value] of Object.entries(settings.value)) {
    const field=$(`#cfg-${key}`); if (key==='history_ready') field.checked=value; else field.value=value;
  }
  $('#settings-revision').textContent=`v${settings.revision}`;
  document.body.dataset.settingsRevision=settings.revision;
}
$('#settings-form').onsubmit=async event=>{
  event.preventDefault();
  const value={};
  for (const key of Object.keys(settings.value)) value[key]=key==='history_ready'?$(`#cfg-${key}`).checked:numericSettings.includes(key)?Number($(`#cfg-${key}`).value):$(`#cfg-${key}`).value;
  $('#save-settings').disabled=true;
  try {settings=await api('settings','PUT',{revision:settings.revision,value}); showSettings(); $('#settings-save-state').textContent=` Revisión ${settings.revision} guardada.`; message('Configuración guardada para las próximas ejecuciones.');} catch(error) {message(error.message);} finally {$('#save-settings').disabled=false;}
};
const runLabels={queued:'En cola',running:'Ejecutando',succeeded:'Completada',failed:'Fallida',unknown:'Resultado incierto'};
async function refreshWorkflow() {
  [workflow,runs]=await Promise.all([api('workflow'),api('workflow/runs')]);
  $('#engine-state').textContent=workflow.reachable?'Conectado':'Sin conexión';
  $('#admission-state').textContent=workflow.control.enabled?'Permitidas':'Pausadas';
  $('#enable-workflow').disabled=workflow.control.enabled;
  $('#pause-workflow').disabled=!workflow.control.enabled;
  document.body.dataset.workflowEnabled=workflow.control.enabled;
  document.body.dataset.controlRevision=workflow.control.revision;
  const active=runs.some(run=>['queued','running','unknown'].includes(run.status));
  $('#run-active').textContent=runs.filter(run=>['queued','running','unknown'].includes(run.status)).length;
  $('#run-submit').disabled=posting || !workflow.reachable || !workflow.control.enabled || active;
  const blocked=runs.find(run=>['queued','running','unknown'].includes(run.status));
  $('#next-step').textContent=blocked?(blocked.status==='unknown'?'Revisa la ejecución incierta':'Análisis en curso'):!workflow.reachable?'Conecta el motor n8n':!workflow.control.enabled?'Permite nuevas ejecuciones':'Listo para analizar una ficha';
  $('#next-step-detail').textContent=blocked?'Consulta las tareas y sus evidencias. Los resultados válidos se conservan.':`Objetivo configurado: ${settings.value.quota_spain} España + ${settings.value.quota_europe} Europa · ${settings.value.max_openings} fichas máximo · historial ${settings.value.history_ready?'confirmado':'pendiente de confirmar para búsqueda'}.`;
  $('#next-step-link').textContent=blocked?'Ver ejecución ↓':!workflow.control.enabled?'Revisar control ↓':'Analizar una ficha ↓';
  $('#next-step-link').href=blocked?'#runs':!workflow.control.enabled?'#enable-workflow':'#run-form';
  if (!$('#pipeline').children.length) for (const module of workflow.modules) {
    const card=document.createElement('article');card.className=`module-card ${module.available?'ready':'pending'}`;
    card.dataset.moduleId=module.id; card.dataset.available=module.available;
    const heading=document.createElement('h3');heading.textContent=module.label;
    const badge=document.createElement('span');badge.className='badge';badge.textContent=module.available?'Conectado':'Pendiente';card.append(heading,badge);
    if (module.tasks) {
      const details=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('ol');
      summary.textContent=`Ver ${module.tasks.length} ${module.tasks.length===1?'tarea':'tareas'} y sus límites`;
      for (const task of module.tasks) {const item=document.createElement('li');item.textContent=`${task.label}: ${task.instruction}`;item.dataset.taskId=task.id;list.append(item);}
      details.append(summary,list);card.append(details);
      const link=document.createElement('a');link.href=`http://localhost:5678/workflow/${module.workflowId}`;link.target='_blank';link.rel='noopener';link.textContent='Abrir workflow en n8n ↗';card.append(link);
    }
    $('#pipeline').append(card);
  }
  $('#runs').replaceChildren();
  if (!runs.length) $('#runs').textContent='Todavía no hay ejecuciones.';
  selectedRunId ||= runs[0]?.id;
  for (const run of runs) {
    const article=document.createElement('article'); article.className='run';
    article.dataset.runId=run.id; article.dataset.status=run.status;
    const button=document.createElement('button');button.type='button';button.className='run-select';button.dataset.tool='get_run';
    button.setAttribute('aria-pressed',String(run.id===selectedRunId));
    button.textContent=`${runLabels[run.status]} · ${run.module==='extraction'?'Análisis de ficha':'Contrato'}`;
    const meta=document.createElement('p');meta.className='muted';meta.textContent=`${new Date(run.created_at).toLocaleString('es-ES')} · configuración v${run.settings_revision}`;
    button.onclick=async()=>{selectedRunId=run.id;await refreshWorkflow().catch(error=>message(error.message));};
    article.append(button,meta);
    if (run.status==='unknown') {
      const form=document.createElement('form'),label=document.createElement('label'),input=document.createElement('input'),button=document.createElement('button');
      label.textContent='Resultado de tu comprobación en n8n'; input.required=true; input.maxLength=2000; label.append(input); button.textContent='Cerrar incidencia y permitir otro intento'; form.append(label,button);
      form.onsubmit=async event=>{event.preventDefault(); try {await api(`workflow/runs/${run.id}/resolve`,'POST',{reason:input.value}); await refreshWorkflow();} catch(error) {message(error.message);}}; article.append(form);
    }
    $('#runs').append(article);
  }
  if (selectedRunId) await renderRunDetail(selectedRunId);
  updateRunScope();
}
async function renderRunDetail(id) {
  const run=await api(`workflow/runs/${id}`);
  if (id!==selectedRunId) return;
  const panel=$('#run-detail');panel.replaceChildren();panel.dataset.runId=id;panel.dataset.status=run.status;
  const heading=document.createElement('h3');heading.textContent=`${run.module==='extraction'?'Análisis de ficha':'Contrato'} · ${runLabels[run.status]}`;panel.append(heading);
  const complete=run.tasks.filter(task=>['succeeded','failed'].includes(task.status)).length;
  if (run.tasks.length) {
    const label=document.createElement('p');label.textContent=`${complete} de ${run.tasks.length} tareas terminadas`;panel.append(label);
    const progress=document.createElement('progress');progress.max=run.tasks.length;progress.value=complete;progress.setAttribute('aria-label','Tareas terminadas');panel.append(progress);
  }
  if (run.error) {const error=document.createElement('p');error.className='notice';error.textContent=run.error;panel.append(error);}
  const labels=Object.fromEntries(workflow.modules.flatMap(module=>module.tasks || []).map(task=>[task.id,task.label]));
  for (const task of run.tasks) {
    const article=document.createElement('article');article.className='task-result';article.dataset.taskId=task.task_id;article.dataset.status=task.status;
    const title=document.createElement('h4');title.textContent=`${String(task.position).padStart(2,'0')} · ${labels[task.task_id] || task.task_id}`;
    const status=document.createElement('span');status.className=`badge ${task.status}`;
    status.textContent=task.status==='succeeded'?(task.result.state==='desconocido'?'No consta en el texto':'Con evidencia'):task.status==='pending'?'En espera':runLabels[task.status];
    article.append(title,status);
    if (task.result?.state==='acreditado') {
      const value=document.createElement('p');value.textContent=task.result.value;
      const quote=document.createElement('blockquote');quote.textContent=task.result.evidence;article.append(value,quote);
    }
    if (task.error) {const error=document.createElement('p');error.textContent=task.error;article.append(error);}
    panel.append(article);
  }
  if (!run.tasks.length && run.result) {const p=document.createElement('p');p.textContent=run.result.value;panel.append(p);if(run.result.evidence){const q=document.createElement('blockquote');q.textContent=run.result.evidence;panel.append(q);}}
  if (run.n8n_execution_id) {const link=document.createElement('a');link.href=`http://localhost:5678/workflow/${run.module==='extraction'?'empleoExtraction02':'empleoContract01'}/executions/${encodeURIComponent(run.n8n_execution_id)}`;link.target='_blank';link.rel='noopener';link.textContent=`Ejecución ${run.n8n_execution_id} en n8n ↗`;panel.append(link);}
  const meta=document.createElement('p');meta.className='muted';meta.textContent=`ID: ${id} · ${new Date(run.created_at).toLocaleString('es-ES')}`;panel.append(meta);
}
function updateRunScope() {
  $('#run-scope').textContent=$('#run-module').value==='extraction'?'15 llamadas consecutivas al modelo. Cada dato se guarda por separado con su cita literal. Puede tardar varios minutos. No clasifica ni verifica páginas externas.':'Una llamada al modelo para extraer únicamente el contrato y su cita.';
}
$('#run-module').onchange=()=>{requestId=null;updateRunScope();};
for (const id of ['enable-workflow','pause-workflow']) $(`#${id}`).onclick=async()=>{
  $('#enable-workflow').disabled=true; $('#pause-workflow').disabled=true;
  try {await api('workflow/control','PUT',{enabled:id==='enable-workflow',revision:workflow.control.revision}); await refreshWorkflow();} catch(error) {message(error.message); await refreshWorkflow().catch(()=>{});}
};
$('#refresh-workflow').onclick=()=>refreshWorkflow().catch(error=>message(error.message));
$('#run-text').oninput=()=>{requestId=null;};
$('#run-form').onsubmit=async event=>{
  event.preventDefault(); if (posting) return;
  posting=true; $('#run-submit').disabled=true; requestId ||= crypto.randomUUID();
  try {const run=await api('workflow/runs','POST',{id:requestId,module:$('#run-module').value,text:$('#run-text').value}); selectedRunId=run.id; requestId=null; message('Ejecución enviada a n8n. Puedes seguirla abajo.');} catch(error) {message(error.message);} finally {posting=false; await refreshWorkflow().catch(error=>message(error.message));}
};
function route() {
  if (['run-form','runs','enable-workflow'].includes(location.hash.slice(1))) return;
  const page=['control','configuration','seguimiento','integrations'].includes(location.hash.slice(1))?location.hash.slice(1):'control';
  document.body.dataset.page=page;
  for (const view of document.querySelectorAll('[data-view]')) view.hidden=view.dataset.view!==page;
  for (const link of document.querySelectorAll('[data-page]')) link.classList.toggle('active',link.dataset.page===page);
  $('#page-title').textContent={control:'Tu búsqueda, bajo control.',configuration:'Configura el workflow.',seguimiento:'Sigue tus oportunidades.',integrations:'Conecta tu asistente.'}[page];
  $('#page-subtitle').textContent={control:'Ejecuta módulos y revisa su estado en n8n.',configuration:'Define los parámetros de las próximas ejecuciones.',seguimiento:'Gestiona candidaturas, publicaciones y próximos pasos.',integrations:'Herramientas MCP para consultar, configurar y operar la aplicación.'}[page];
}
window.addEventListener('hashchange',route); route();
try {
  for (const [state,label] of Object.entries(offerStates)) {option($('[name=status]'),state,label); option($('#filter'),state,label);}
  await load(); settings=await api('settings'); showSettings(); await refreshWorkflow();
  const integration=await api('integration');
  $('#integration-state').textContent=integration.configured?'MCP configurado · stdio y HTTP disponibles':'Falta configurar MCP_TOKEN en 11/.env y reiniciar el servicio.';
  $('#mcp-stdio-config').value=JSON.stringify(integration.stdio,null,2);
  $('#mcp-http-config').value=JSON.stringify(integration.http,null,2);
  document.body.dataset.mcpEndpoint=integration.endpoint;
  document.body.dataset.appState='ready';
  setInterval(()=>{if (!document.hidden && runs.some(run=>['queued','running'].includes(run.status))) refreshWorkflow().catch(error=>message(error.message));},3000);
} catch(error) {
  $('#connection-banner').hidden=false; $('#connection-banner').textContent=error.message;
  document.body.dataset.appState='error';
  for (const control of document.querySelectorAll('form input, form select, form textarea, form button, #enable-workflow, #pause-workflow')) control.disabled=true;
} finally {
  $('main').setAttribute('aria-busy','false');
}
