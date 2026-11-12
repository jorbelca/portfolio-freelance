import {offerStates,offerState,statePatch} from './offer-state.js';
const $ = selector => document.querySelector(selector);
let searchConfig;
const searchOffsets={};
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
        await refreshWorkflow();message('Estado de postulación e informes actualizados.');
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
const profileKeys=['residence','technical_degree','professional_years','internship_details','relocation','work_authorization','max_required_years'];
const configRows={
 skills:[['name','Habilidad'],['evidence','Evidencia'],['priority','Prioridad','number']],
 languages:[['language','Idioma'],['level','Nivel',['A1','A2','B1','B2','C1','C2','nativo']]],
 sources:[['source','Fuente'],['enabled','Habilitada','checkbox'],['max_pages','Páginas máximas','number']],
 queries:[['zone','Cupo',['any','spain','europe']],['language','Idioma',['es','en']],['term','Término del título']]
};
function addConfigRow(group,value={}) {
 const row=document.createElement('div');row.className='config-row';row.dataset.collection=group;
 for(const [key,label,type] of configRows[group]) {
  const wrapper=document.createElement('label');wrapper.textContent=label;
  const field=document.createElement(Array.isArray(type)?'select':'input');field.dataset.field=key;field.setAttribute('aria-label',label);field.required=type!=='checkbox';
  if(Array.isArray(type)) for(const item of type) option(field,item,({any:'Cualquier cupo',spain:'España',europe:'Resto de Europa',es:'Español',en:'Inglés'})[item] || item);
  else {field.type=type || 'text';if(type==='number'){field.min=1;field.max=100;}}
  if(type==='checkbox') field.checked=value[key] ?? true;else field.value=value[key] ?? (type==='number'?3:Array.isArray(type)?type[0]:'');
  wrapper.append(field);row.append(wrapper);
 }
 const remove=document.createElement('button');remove.type='button';remove.textContent='Quitar';remove.setAttribute('aria-label',`Quitar fila de ${group}`);remove.onclick=()=>row.remove();row.append(remove);
 $(`#${group==='skills'||group==='languages'?'profile':'search'}-${group}`).append(row);
}
function showSearchConfig() {
 for(const key of profileKeys) {const input=$(`#profile-${key}`);if(key==='technical_degree') input.checked=searchConfig.value[key];else input.value=searchConfig.value[key] ?? '';}
 $('#profile-qualifications').value=searchConfig.value.qualifications.join('\n');$('#search-excluded').value=searchConfig.value.excluded_employers.join('\n');
 for(const group of Object.keys(configRows)) {$(`#${group==='skills'||group==='languages'?'profile':'search'}-${group}`).replaceChildren();for(const row of searchConfig.value[group]) addConfigRow(group,row);}
 $('#search-config-json').value=JSON.stringify(searchConfig.value,null,2);$('#search-config-state').textContent=`Revisión ${searchConfig.revision}`;
}
for(const [button,group] of [['add-skill','skills'],['add-language','languages'],['add-source','sources'],['add-query','queries']]) $(`#${button}`).onclick=()=>addConfigRow(group);
$('#search-config-form').onsubmit=async event=>{
 event.preventDefault();$('#save-search-config').disabled=true;
 try {
  const value={};for(const key of profileKeys){const field=$(`#profile-${key}`);value[key]=key==='technical_degree'?field.checked:key==='professional_years'?(field.value===''?null:Number(field.value)):key==='max_required_years'?Number(field.value):field.value;}
  value.qualifications=$('#profile-qualifications').value.split('\n').map(item=>item.trim()).filter(Boolean);value.excluded_employers=$('#search-excluded').value.split('\n').map(item=>item.trim()).filter(Boolean);
  for(const group of Object.keys(configRows)) value[group]=[...document.querySelectorAll(`[data-collection="${group}"]`)].map(row=>Object.fromEntries([...row.querySelectorAll('[data-field]')].map(field=>[field.dataset.field,field.type==='checkbox'?field.checked:field.type==='number'?Number(field.value):field.value])));
  searchConfig=await api('search/config','PUT',{revision:searchConfig.revision,value});showSearchConfig();message('Perfil, fuentes y consultas guardados.');
 }catch(error){message(error.message);}finally{$('#save-search-config').disabled=false;}
};
let models={providers:[]};
let modelChoices={codex:'',openai:''};
function showModels() {
 const provider=$('#cfg-provider').value,entry=models.providers.find(item=>item.id===provider);
 const select=$('#model-choice');select.replaceChildren();
 if(provider==='codex') option(select,'','Predeterminado de la sesión');
 for(const model of entry?.models || []) option(select,model.id,model.label);
 option(select,'__custom','Otro modelo: introducir identificador');
 const current=$('#cfg-model').value;
 select.value=[...select.options].some(item=>item.value===current)?current:'__custom';
 $('#custom-model-label').hidden=select.value!=='__custom';
 $('#cfg-model').required=provider==='openai';
 $('#model-status').textContent=entry?.message || 'Consultando modelos…';
}
$('#cfg-provider').onchange=()=>{const previous=Object.keys(modelChoices).find(key=>key!==$('#cfg-provider').value);modelChoices[previous]=$('#cfg-model').value;$('#cfg-model').value=modelChoices[$('#cfg-provider').value];showModels();};
$('#model-choice').onchange=()=>{$('#custom-model-label').hidden=$('#model-choice').value!=='__custom';if($('#model-choice').value!=='__custom') $('#cfg-model').value=$('#model-choice').value;else $('#cfg-model').focus();};
$('#refresh-models').onclick=async()=>{try{models=await api('models');showModels();}catch(error){message(error.message);}};
const numericSettings=['max_openings','batch_size','max_age_days','quota_spain','quota_europe'];
function showSettings() {
  for (const [key,value] of Object.entries(settings.value)) {
    const field=$(`#cfg-${key}`); if (key==='history_ready') field.checked=value; else field.value=value;
  }
  $('#cfg-provider').value=settings.value.provider || 'codex';
  modelChoices[$('#cfg-provider').value]=settings.value.model;showModels();
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
  $('#next-step').textContent=blocked?(blocked.status==='unknown'?'Revisa la ejecución incierta':'Análisis en curso'):!workflow.reachable?'Conecta el motor n8n':!workflow.control.enabled?'Permite nuevas ejecuciones':'Listo para buscar ofertas';
  $('#next-step-detail').textContent=blocked?'Consulta las tareas y sus evidencias. Los resultados válidos se conservan.':`Objetivo configurado: ${settings.value.quota_spain} España + ${settings.value.quota_europe} Europa · ${settings.value.max_openings} fichas máximo · historial ${settings.value.history_ready?'confirmado':'pendiente de confirmar para búsqueda'}.`;
  $('#next-step-link').textContent=blocked?'Ver ejecución ↓':!workflow.control.enabled?'Revisar control ↓':'Buscar ofertas ↓';
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
    button.textContent=`${runLabels[run.status]} · ${run.module==='search'?'Búsqueda de ofertas':run.module==='extraction'?'Análisis de ficha':'Contrato'}`;
    const meta=document.createElement('p');meta.className='muted';meta.textContent=`${new Date(run.created_at).toLocaleString('es-ES')} · configuración v${run.settings_revision}`;
    button.onclick=async()=>{selectedRunId=run.id;await refreshWorkflow().catch(error=>message(error.message));};
    article.append(button,meta);
    if (run.status==='unknown' && run.module!=='search') {
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
  const heading=document.createElement('h3');heading.textContent=`${run.module==='search'?'Búsqueda de ofertas':run.module==='extraction'?'Análisis de ficha':'Contrato'} · ${runLabels[run.status]}`;panel.append(heading);
  const complete=run.tasks.filter(task=>['succeeded','failed'].includes(task.status)).length;
  if (run.tasks.length) {
    const label=document.createElement('p');label.textContent=['succeeded','failed'].includes(run.status)?`${complete} tareas ejecutadas · ${run.tasks.filter(task=>task.status==='pending').length} sin ejecutar al cerrar`:`${complete} de ${run.tasks.length} tareas terminadas`;panel.append(label);
    const progress=document.createElement('progress');progress.max=run.tasks.length;progress.value=complete;progress.setAttribute('aria-label','Tareas terminadas');panel.append(progress);
  }
  if (run.error) {const error=document.createElement('p');error.className='notice';error.textContent=run.error;panel.append(error);}
  const labels=Object.fromEntries(workflow.modules.flatMap(module=>module.tasks || []).map(task=>[task.id,task.label]));
  if(run.module==='search') await renderSearchPanel(run,panel);
  for (const task of run.tasks) {
    const article=document.createElement('article');article.className='task-result';article.dataset.taskId=task.task_id;article.dataset.status=task.status;
    const title=document.createElement('h4');title.textContent=`${String(task.position).padStart(2,'0')} · ${labels[task.task_id] || task.task_id}`;
    const status=document.createElement('span');status.className=`badge ${task.status}`;
    status.textContent=task.status==='succeeded'?(task.result.state==='desconocido'?'No consta en el texto':task.result.state==='acreditado'?'Con evidencia':'Completada'):task.status==='pending'?(['succeeded','failed'].includes(run.status)?'No ejecutada: cierre':'En espera'):runLabels[task.status];
    article.append(title,status);
    if (task.result?.state==='acreditado') {
      const value=document.createElement('p');value.textContent=task.result.value;
      const quote=document.createElement('blockquote');quote.textContent=task.result.evidence;article.append(value,quote);
    }
    if(task.result && !task.result.state) {const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Datos de la operación';pre.textContent=JSON.stringify(task.result,null,2);details.append(summary,pre);article.append(details);}
    if (task.error) {const error=document.createElement('p');error.textContent=task.error;article.append(error);}
    panel.append(article);
  }
  if (!run.tasks.length && run.result) {const p=document.createElement('p');p.textContent=run.result.value;panel.append(p);if(run.result.evidence){const q=document.createElement('blockquote');q.textContent=run.result.evidence;panel.append(q);}}
  if (run.n8n_execution_id) {const link=document.createElement('a');link.href=`http://localhost:5678/workflow/${run.module==='search'?'empleoSearch03':run.module==='extraction'?'empleoExtraction02':'empleoContract01'}/executions/${encodeURIComponent(run.n8n_execution_id)}`;link.target='_blank';link.rel='noopener';link.textContent=`Ejecución ${run.n8n_execution_id} en n8n ↗`;panel.append(link);}
  const meta=document.createElement('p');meta.className='muted';meta.textContent=`ID: ${id} · ${new Date(run.created_at).toLocaleString('es-ES')}`;panel.append(meta);
}
async function renderSearchPanel(run,panel) {
 const data=await api(`search/runs/${run.id}/results?limit=25&offset=${searchOffsets[run.id] || 0}`);
 const state=data.state;
 const controls=document.createElement('div');controls.className='search-controls';
 if(['running','unknown'].includes(run.status)) {
  for(const action of state.control==='active'?['pause','cancel']:['resume','cancel']) {
   const button=document.createElement('button');button.type='button';button.textContent={pause:'Pausar esta búsqueda',resume:'Reanudar búsqueda',cancel:'Cancelar y conservar resultados'}[action];button.dataset.action=action;
   button.onclick=async()=>{button.disabled=true;try {await api(`search/runs/${run.id}/control`,'POST',{action,revision:state.revision});await refreshWorkflow();} catch(error) {message(error.message);button.disabled=false;}};controls.append(button);
  }
  for(const task of run.tasks.filter(task=>['failed','unknown'].includes(task.status))) {
   const form=document.createElement('form'),label=document.createElement('label'),reason=document.createElement('input'),button=document.createElement('button');label.textContent=`Comprobación para reintentar ${task.task_id}`;reason.required=true;reason.maxLength=2000;label.append(reason);button.textContent='Reintentar solo esta tarea';form.append(label,button);
   form.onsubmit=async event=>{event.preventDefault();button.disabled=true;try{await api(`search/runs/${run.id}/control`,'POST',{action:'retry',revision:state.revision,step_id:task.id,reason:reason.value});await refreshWorkflow();}catch(error){message(error.message);button.disabled=false;}};controls.append(form);
  }
 }
 const controlLabel=document.createElement('p');controlLabel.textContent=`Búsqueda: ${run.status==='succeeded'?'cerrada':state.control==='active'?'activa':state.control==='paused'?'pausada':'cancelada'} · control v${state.revision}`;controls.append(controlLabel);panel.append(controls);
 if(run.result) {
  const report=document.createElement('section');report.className='search-summary';const title=document.createElement('h3');title.textContent=run.status!=='succeeded'?'Avance de la búsqueda':run.result.fulfilled?'Reparto verificado':'Búsqueda cerrada con déficit';
  const totals=document.createElement('p');totals.textContent=`España ${run.result.spain}/${run.result.quota_spain} · Europa ${run.result.europe}/${run.result.quota_europe} · Fichas ${run.result.openings}/${run.result.max_openings}. Motivo: ${run.result.reason}.`;
  const deficits=document.createElement('p');deficits.textContent=`Faltan ${run.result.deficit_spain} de España y ${run.result.deficit_europe} del resto de Europa. Corte: ${new Date(run.result.cutoff).toLocaleString('es-ES',{timeZone:run.result.timezone})}.`;
  report.append(title,totals,deficits);for(const [label,path] of [['Descargar informe',run.result.files?.report],['Descargar registro',run.result.files?.register]]) if(path){const link=document.createElement('a');link.href=path;link.textContent=label;link.style.marginRight='16px';report.append(link);}panel.append(report);
 }
 const heading=document.createElement('h3');heading.textContent='Ofertas y pistas investigadas';panel.append(heading);
 if(!data.candidates.length) {const empty=document.createElement('p');empty.textContent='Todavía no hay resultados en esta página.';panel.append(empty);}
 for(const candidate of data.candidates) {
  const article=document.createElement('article');article.className='search-result';article.dataset.candidateId=candidate.id;article.dataset.classification=candidate.evaluation?.classification || 'pista';
  const title=document.createElement('h4');title.textContent=`${candidate.title} · ${candidate.company}`;
  const classification=document.createElement('p');const evaluation=candidate.evaluation;
  classification.textContent=evaluation?`${{A:'A · Recomendada y verificada',B:'B · Pendiente',C:'C · Excluida',pista:'Pista sin ficha completa'}[evaluation.classification]} · ${evaluation.computable?'Computable':'No computable'}${evaluation.country?` · ${evaluation.country}`:''}`:candidate.stage==='blocked'?'Identidad o lectura pendiente · No computable':candidate.stage==='extracting'?'Ficha completa · análisis en curso':candidate.stage==='reading'?'Lectura en curso':'Pista sin ficha completa · No computable';
  const link=document.createElement('a');link.href=candidate.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=`Ver en ${candidate.source==='remotive'?'Remotive':candidate.source} ↗`;
  article.append(title,classification,link);
  for(const exclusion of evaluation?.exclusions || []) {const p=document.createElement('p');p.textContent=`${exclusion.rule}: ${exclusion.evidence}`;article.append(p);}
  if(evaluation?.pending?.length) {const details=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('ul');summary.textContent=`${evaluation.pending.length} pendientes por resolver`;for(const pending of evaluation.pending){const li=document.createElement('li');li.textContent=`${pending.owner}: ${pending.resolution}`;list.append(li);}details.append(summary,list);article.append(details);}
  if(candidate.reason) {const p=document.createElement('p');p.textContent=candidate.reason;article.append(p);}
  const detailsButton=document.createElement('button');detailsButton.type='button';detailsButton.textContent='Ver citas y comprobaciones';
  detailsButton.onclick=async()=>{detailsButton.disabled=true;try{const detail=await api(`search/candidates/${candidate.id}?include_text=true`);renderCandidateTools(detail,article,data.candidates);const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Documento, tareas y evidencia';pre.textContent=JSON.stringify(detail,null,2);details.open=true;details.append(summary,pre);article.append(details);}catch(error){message(error.message);detailsButton.disabled=false;}};article.append(detailsButton);
  if(['A','B'].includes(evaluation?.classification) && !candidate.history?.needs_review) {
   const track=document.createElement('button');track.type='button';track.textContent=candidate.opportunity_id?'Ya en seguimiento':'Añadir al seguimiento';track.disabled=Boolean(candidate.opportunity_id);
   track.onclick=async()=>{track.disabled=true;try{await api(`search/candidates/${candidate.id}/track`,'POST',{});await load();await refreshWorkflow();message('Oferta incorporada al seguimiento; no se ha enviado candidatura.');}catch(error){message(error.message);track.disabled=false;}};article.append(track);
  }
  panel.append(article);
 }
 const paging=document.createElement('div');
 for(const [label,offset] of [['Anterior',Math.max(0,(searchOffsets[run.id] || 0)-25)],['Siguiente',(searchOffsets[run.id] || 0)+25]]) {
  const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=label==='Anterior'?!searchOffsets[run.id]:data.candidates.length<25;
  button.onclick=async()=>{searchOffsets[run.id]=offset;await renderRunDetail(run.id);};paging.append(button);
 }panel.append(paging);
}
function renderCandidateTools(candidate,article,candidates) {
 const section=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Resolver identidad o corregir un dato';section.append(summary);
 const identity=document.createElement('form'),resolution=document.createElement('select'),target=document.createElement('select'),reason=document.createElement('input'),save=document.createElement('button');
 const labelled=(text,field)=>{const label=document.createElement('label');label.textContent=text;label.append(field);return label;};
 for(const [value,label] of [['distinct','Es otra convocatoria'],['same_process','Es un proceso del seguimiento'],['duplicate','Es duplicada de otra pista']]) option(resolution,value,label);
 const targets=()=>{target.replaceChildren();option(target,'','Seleccionar destino');for(const item of resolution.value==='same_process'?offers:candidates.filter(item=>item.id!==candidate.id)) option(target,item.id,`${item.title} · ${item.company}`);target.hidden=resolution.value==='distinct';target.required=resolution.value!=='distinct';};resolution.onchange=targets;targets();reason.required=true;reason.maxLength=2000;save.textContent='Guardar resolución';
 identity.append(labelled('Identidad',resolution),labelled('Proceso principal',target),labelled('Motivo de la resolución',reason),save);
 identity.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await api(`search/candidates/${candidate.id}/identity`,'POST',{version:candidate.version,resolution:resolution.value,...(resolution.value==='same_process'?{target_offer_id:target.value}:resolution.value==='duplicate'?{duplicate_candidate_id:target.value}:{}),reason:reason.value});await refreshWorkflow();message('Identidad y recuentos actualizados.');}catch(error){message(error.message);save.disabled=false;}};section.append(identity);
 const correction=document.createElement('form'),field=document.createElement('select'),value=document.createElement('input'),verdict=document.createElement('select'),evidence=document.createElement('textarea'),why=document.createElement('input'),apply=document.createElement('button');
 for(const [key,label] of [['country','País del puesto (código ISO)'],['publication','Fecha de publicación'],...['seniority','experience','education','technology','languages','contract','functions','remote','video','availability','channel'].map(key=>[`decision:${key}`,key])]) option(field,key,label);
 for(const [key,label] of [['cumple','Cumple'],['incumple','Incumple'],['desconocido','Desconocido']]) option(verdict,key,label);
 const type=()=>{const decision=field.value.startsWith('decision:');value.hidden=decision;value.required=!decision;verdict.hidden=!decision;value.type=field.value==='publication'?'date':'text';value.placeholder=field.value==='country'?'ES, GB, DE…':'';};field.onchange=type;type();evidence.required=true;evidence.rows=3;evidence.maxLength=10000;why.required=true;why.maxLength=2000;apply.textContent='Guardar corrección con evidencia';
 correction.append(labelled('Dato a corregir',field),labelled('Valor corregido',value),labelled('Veredicto corregido',verdict),labelled('Cita literal del documento',evidence),labelled('Motivo de la corrección',why),apply);
 correction.onsubmit=async event=>{event.preventDefault();apply.disabled=true;try{await api(`search/candidates/${candidate.id}/correction`,'POST',{version:candidate.version,field:field.value,value:field.value.startsWith('decision:')?verdict.value:value.value,evidence:evidence.value,reason:why.value});await refreshWorkflow();message('Corrección, evidencias y recuentos guardados.');}catch(error){message(error.message);apply.disabled=false;}};section.append(correction);article.append(section);
}
function updateRunScope() {
  const search=$('#run-module').value==='search';$('#run-text').required=!search;$('#run-text').closest('label').hidden=search;
  if(search) {$('#run-scope').textContent=`Busca en las fuentes habilitadas. Máximo ${settings.value.max_openings} lecturas; objetivo ${settings.value.quota_spain} España + ${settings.value.quota_europe} Europa. Motor: ${settings.value.provider==='openai'?'API de OpenAI':'Codex (suscripción)'} · modelo: ${settings.value.model || 'predeterminado'}. Cada ficha completa puede consumir 15 extracciones y 11 evaluaciones. Puedes pausar entre tareas.`;return;}
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
  await load(); searchConfig=await api('search/config');showSearchConfig(); models=await api('models'); settings=await api('settings'); showSettings(); await refreshWorkflow();
  const integration=await api('integration');
  $('#integration-state').textContent=integration.configured?'MCP configurado · stdio y HTTP disponibles':'Falta configurar MCP_TOKEN en 11/.env y reiniciar el servicio.';
  $('#mcp-stdio-config').value=JSON.stringify(integration.stdio,null,2);
  $('#mcp-http-config').value=JSON.stringify(integration.http,null,2);
  document.body.dataset.mcpEndpoint=integration.endpoint;
  document.body.dataset.appState='ready';
  setInterval(()=>{if (!document.hidden && !$('#run-detail').contains(document.activeElement) && runs.some(run=>['queued','running'].includes(run.status))) refreshWorkflow().catch(error=>message(error.message));},3000);
} catch(error) {
  $('#connection-banner').hidden=false; $('#connection-banner').textContent=error.message;
  document.body.dataset.appState='error';
  for (const control of document.querySelectorAll('form input, form select, form textarea, form button, #enable-workflow, #pause-workflow')) control.disabled=true;
} finally {
  $('main').setAttribute('aria-busy','false');
}
