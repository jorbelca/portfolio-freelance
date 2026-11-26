import {offerStates,offerState,statePatch} from './offer-state.js';
import {filterPostulations,applicationsToday,rejectionsToday} from './postulations.js';
import {renderCompanyHeatmap} from './company-heatmap.js';
import {launchBlocked,launchBlockReason,taskStatusLabel} from './workflow-state.js';
const $ = selector => document.querySelector(selector);
let searchConfig;
const taskOffsets={},taskStatuses={};
let offers=[], companies=[], rejectionReasons=[], selected=null, settings, workflow, runs=[], posting=false, requestId=null, selectedRunId=null;
const fields=['company','company_id','title','url','notes'];
document.addEventListener('invalid',event=>{for(let parent=event.target.parentElement;parent;parent=parent.parentElement) if(parent.tagName==='DETAILS') parent.open=true;},true);
function message(text) {
  $('#message').textContent=text;
  const feedback=$('#refresh-feedback');
  if(feedback) {feedback.textContent='';feedback.hidden=true;}
}
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
function renderRejectionChart() {
  const rejected=offers.filter(item=>offerState(item)==='rechazada');
  const causes=new Map();
  for (const offer of rejected) {
    const cause=offer.rejection_reason || 'Sin causa registrada';
    causes.set(cause,(causes.get(cause) || 0)+1);
  }
  const entries=[...causes].sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0],'es'));
  const chart=$('#rejection-chart');
  chart.replaceChildren();
  $('#rejection-total').textContent=`${rejected.length} ofertas rechazadas — ${entries.length} causas`;
  $('#rejection-empty').hidden=entries.length>0;
  for (const [cause,count] of entries) {
    const row=document.createElement('li'),label=document.createElement('span'),bar=document.createElement('progress'),value=document.createElement('span');
    label.textContent=cause;
    bar.max=rejected.length;bar.value=count;bar.setAttribute('aria-label',`${cause}: ${count} de ${rejected.length} rechazos`);
    value.className='rejection-count';value.textContent=`${count} — ${Math.round(count/rejected.length*100)} %`;
    row.append(label,bar,value);chart.append(row);
  }
}
function render() {
  renderCompanyHeatmap(offers);
  renderRejectionChart();
  renderTodayCounts();
  $('#offer-editor-home').append($('#offer-editor'));
  $('#offers').replaceChildren();
  const visible=filterPostulations(offers,{
    company:$('#offer-company-search').value,
    url:$('#offer-url-search').value,
    state:$('#filter').value,
    days:Number($('#offer-days-filter').value)
  });
  $('#offer-search-count').textContent=`${visible.length} de ${offers.length} ofertas`;
  if (!visible.length) {
    const row=document.createElement('tr'), cell=document.createElement('td'); cell.colSpan=6; cell.textContent='Sin ofertas para mostrar.'; row.append(cell); $('#offers').append(row);
  }
  $('#count-all').textContent=offers.length;
  const rejectedCount=offers.filter(item=>offerState(item)==='rechazada').length;
  $('#count-rejected').textContent=rejectedCount;
  $('#count-rejected-percent').textContent=`(${offers.length ? Math.round(rejectedCount/offers.length*100) : 0}%)`;
  $('#count-active').textContent=offers.filter(item=>offerState(item)==='inscrita').length;
  for (const offer of visible) {
    const row=document.createElement('tr'); row.dataset.offerId=offer.id; row.dataset.offerState=offerState(offer);
    for (const value of [offer.company,offer.title,'']) {
      const cell=document.createElement('td'); cell.textContent=value.replaceAll('_',' ').replaceAll('·','—'); row.append(cell);
    }
    const stateSelect=document.createElement('select'),stateControl=document.createElement('span'),stateArrow=document.createElement('span');
    stateControl.className='offer-state-control';
    stateArrow.className='select-arrow';stateArrow.setAttribute('aria-hidden','true');
    stateSelect.id=`offer-${offer.id}-application-state`;
    stateSelect.dataset.tool='patch_offer';
    stateSelect.setAttribute('aria-label',`Estado de postulación: ${offer.title} — ${offer.company}`);
    for (const [state,label] of Object.entries(offerStates)) {
      option(stateSelect,state,label);
      stateSelect.lastElementChild.disabled=state==='pendiente' && offer.application_state!=='sin_candidatura';
    }
    stateSelect.value=offerState(offer);
    stateControl.append(stateSelect,stateArrow);
    stateSelect.onchange=async()=>{
      const next=stateSelect.value;
      if (next===offerState(offer)) return;
      stateSelect.disabled=true;
      try {
        await api(`offers/${offer.id}`,'PATCH',{version:offer.version,patch:statePatch(offer,next)});
      } catch(error) {stateSelect.value=offerState(offer);message(error.message);stateSelect.disabled=false;return;}
      try {
        try {if (selected?.id===offer.id) await refreshSelected(); else await load();}
        catch(error) {message(`Estado guardado; no se pudo recargar la oferta: ${error.message}`);return;}
        try {await refreshWorkflow();message('Estado de postulación e informes actualizados.');}
        catch(error) {message(`Estado guardado; no se pudo actualizar el panel: ${error.message}`);}
      } finally {stateSelect.disabled=false;}
    };
    row.children[2].replaceChildren(stateControl);
    if (row.dataset.offerState==='rechazada') {
      const cause=document.createElement('small');
      cause.className='rejection-reason';
      cause.textContent=offer.rejection_reason || 'Sin causa registrada';
      row.children[2].append(cause);
    }
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
function renderTodayCounts() {
  $('#count-today').textContent=applicationsToday(offers);
  $('#count-rejected-today').textContent=`${rejectionsToday(offers)} rechazos hoy`;
}
const reasonSelect=$('[name=rejection_reason_id]');
function showRejectionReasons(id) {
  reasonSelect.replaceChildren(new Option('Sin causa registrada',''));
  for (const reason of rejectionReasons) reasonSelect.add(new Option(reason.name,reason.id));
  reasonSelect.value=id || '';
}
function showRejectionFields() {
  $('#rejection-fields').hidden=$('[name=status]').value!=='rechazada';
}
$('[name=status]').onchange=showRejectionFields;
$('#add-rejection-reason').onclick=async event=>{
  const button=event.currentTarget, input=$('#new-rejection-reason');
  button.disabled=true;
  try {
    const reason=await api('rejection-reasons','POST',{name:input.value});
    if (!rejectionReasons.some(item=>item.id===reason.id)) rejectionReasons.push(reason);
    showRejectionReasons(reason.id);
    input.value='';
    reasonSelect.focus();
    message('Causa añadida al catálogo. Guarda la oferta para asignarla.');
  } catch(error) {message(error.message);}
  finally {button.disabled=false;}
};
async function load() {
  [offers,companies,rejectionReasons]=await Promise.all([api('offers'),api('companies'),api('rejection-reasons')]);
  showRejectionReasons(reasonSelect.value);
  const select=$('[name=company_id]'); select.replaceChildren(); option(select,'','Crear empresa');
  for (const company of companies) option(select,company.id,`${company.name} — ${company.id.slice(0,8)}`);
  render();
}
async function selectOffer(offer) {
  selected=offer;
  for (const key of fields) $('[name='+key+']').value=offer[key] || '';
  $('[name=submitted_on]').value=offer.submitted_at?.slice(0,10) || '';
  $('[name=company]').readOnly=true;
  $('[name=status]').value=offerState(offer);
  showRejectionReasons(offer.rejection_reason_id);
  showRejectionFields();
  $('[name=status] option[value=pendiente]').disabled=offer.application_state!=='sin_candidatura';
  $('[name=url]').readOnly=true;
  $('#form-title').textContent='Gestionar proceso';
  $('#offer-detail').hidden=false;
  const mergeSelect=$('#merge-form [name=source_id]');mergeSelect.replaceChildren(new Option('Selecciona el duplicado',''));
  for(const other of offers.filter(item=>item.id!==offer.id)) mergeSelect.add(new Option(`${other.company} — ${other.title} — ${offerState(other)}`,other.id));
  const [events,publications,actions,merges]=await Promise.all([api(`offers/${offer.id}/events`),api(`offers/${offer.id}/publications`),api(`offers/${offer.id}/actions`),api(`offers/${offer.id}/merges`)]);
  $('#events').textContent=JSON.stringify(events,null,2);
  const latestMerge=merges.items[0],unmergeForm=$('#unmerge-form');
  $('#unmerge-details').hidden=!latestMerge;
  if(latestMerge) {
    unmergeForm.reset();unmergeForm.elements.source_id.value=latestMerge.source_id;unmergeForm.elements.source_version.value=latestMerge.source_version;
    $('#unmerge-status').textContent=`Fusión más reciente: ${latestMerge.company} — ${latestMerge.title}. ${latestMerge.undoable?'Puedes separarla y restaurar ambos historiales.':latestMerge.undo_blocked_reason}`;
    $('#unmerge-submit').disabled=!latestMerge.undoable;
  }
  $('#publications').replaceChildren();
  for (const p of publications) {
    const li=document.createElement('li'), a=document.createElement('a'); a.href=p.url; a.textContent=p.url; a.target='_blank'; a.rel='noopener noreferrer'; li.append(a); $('#publications').append(li);
  }
  $('#actions').replaceChildren();
  for (const action of actions) {
    const li=document.createElement('li'); li.textContent=`${action.description} — ${action.due_on?.slice(0,10) || 'Sin fecha'} — ${action.state} `;
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
$('#offer-company-search').oninput=render;
$('#offer-days-filter').onchange=render;
$('#offer-url-search').oninput=()=>{if ($('#offer-url-search').value.trim()) $('#filter').value='';render();};
$('#reset-offer-filters').onclick=()=>{
  $('#offer-company-search').value=''; $('#offer-url-search').value=''; $('#offer-days-filter').value=''; $('#filter').value=''; render();
};
$('#reset').onclick=()=>{
  selected=null; $('#offer-form').reset(); showRejectionFields(); $('[name=status] option[value=pendiente]').disabled=false; $('[name=company]').readOnly=false; $('[name=url]').readOnly=false;
  $('#form-title').textContent='Registrar oferta'; $('#events').textContent='Selecciona una oferta.'; $('#offer-detail').hidden=true; render();
};
$('#offer-form').onsubmit=async event=>{
  event.preventDefault(); const value=Object.fromEntries(new FormData(event.target));
  try {
    Object.assign(value,{availability:selected?.availability || 'desconocida',review_state:selected?.review_state || 'nueva',application_state:selected?.application_state || 'sin_candidatura'},statePatch(selected,value.status));
    if (value.submitted_on !== (selected?.submitted_at?.slice(0,10) || '')) value.submitted_at=value.submitted_on?`${value.submitted_on}T00:00:00.000Z`:null;
    delete value.submitted_on;
    value.rejection_reason_id=value.status==='rechazada' ? value.rejection_reason_id || null : null;
    delete value.status;
    if (selected) {value.version=selected.version; await api(`offers/${selected.id}`,'PUT',value);} else await api('offers','POST',value);
  } catch(error) {message(error.message);return;}
  try {
    if (selected) await refreshSelected(); else {$('#reset').click(); await load();}
    message('Proceso e historial guardados.');
  } catch(error) {message(`Cambios guardados; no se pudo recargar el proceso: ${error.message}`);}
};
$('#publication-form').onsubmit=async event=>{
  event.preventDefault(); if (!selected) return;
  try {await api(`offers/${selected.id}/publications`,'POST',Object.fromEntries(new FormData(event.target))); event.target.reset(); await refreshSelected(); message('Publicación añadida al mismo proceso.');} catch(error) {message(error.message);}
};
$('#merge-form').onsubmit=async event=>{
  event.preventDefault();if(!selected) return;
  const value=Object.fromEntries(new FormData(event.target));
  const source=offers.find(item=>item.id===value.source_id);if(!source) return;
  try {
    await api(`offers/${selected.id}/merge`,'POST',{...value,version:selected.version,source_version:source.version});
    event.target.reset();await refreshSelected();message('Duplicado fusionado. Enlaces e historial conservados.');
  } catch(error) {message(error.message);}
};
$('#unmerge-form').onsubmit=async event=>{
  event.preventDefault();if(!selected) return;
  const value=Object.fromEntries(new FormData(event.target));
  try {
    await api(`offers/${selected.id}/unmerge/${value.source_id}`,'POST',{version:selected.version,source_version:Number(value.source_version),reason:value.reason});
    await refreshSelected();message('Fusión deshecha; ambos procesos y sus enlaces están separados.');
  } catch(error) {message(error.message);}
};
$('#action-form').onsubmit=async event=>{
  event.preventDefault(); if (!selected) return;
  try {await api(`offers/${selected.id}/actions`,'POST',{...Object.fromEntries(new FormData(event.target)),state:'pendiente'}); event.target.reset(); await refreshSelected(); message('Acción guardada.');} catch(error) {message(error.message);}
};
const profileKeys=['recover_previous','reuse_evidence','fit_instruction','residence','technical_degree','professional_years','internship_details','relocation','work_authorization','max_required_years'];
const configRows={
 skills:[['name','Tecnología o habilidad'],['evidence','Dónde la has usado'],['priority','Preferencia (1 = mayor)','number']],
 languages:[['language','Idioma'],['level','Nivel',['A1','A2','B1','B2','C1','C2','nativo']]],
 sources:[['source','Buscador web',['browser:google','browser:bing']],['enabled','Activo','checkbox'],['max_pages','Páginas por búsqueda','number']],
 queries:[['term','Puesto o especialidad'],['zone','Zona de búsqueda',['any','spain','europe']],['language','Idioma del anuncio',['es','en']]]
};
function addConfigRow(group,value={}) {
 const row=document.createElement('div');row.className='config-row';row.dataset.collection=group;
 for(const [key,label,type] of configRows[group]) {
  const wrapper=document.createElement('label');wrapper.textContent=label;
  const field=document.createElement(Array.isArray(type)?'select':'input');field.dataset.field=key;field.setAttribute('aria-label',label);field.required=type!=='checkbox';
  if(Array.isArray(type)) for(const item of type) option(field,item,({any:'Cualquier zona',spain:'España',europe:'Resto de Europa',es:'Español',en:'Inglés','browser:google':'Google (navegador)','browser:bing':'Bing (navegador)'})[item] || item);
  else {field.type=type || 'text';if(type==='number'){field.min=1;field.max=100;}}
  if(type==='checkbox') field.checked=value[key] ?? true;else field.value=value[key] ?? (type==='number'?3:Array.isArray(type)?type[0]:'');
  wrapper.append(field);row.append(wrapper);
 }
 const remove=document.createElement('button');remove.type='button';remove.textContent='Quitar';remove.setAttribute('aria-label',`Quitar fila de ${group}`);remove.onclick=()=>row.remove();row.append(remove);
 $(`#${group==='skills'||group==='languages'?'profile':'search'}-${group}`).append(row);
}
function updateConfigSummaries() {
 const terms=[...document.querySelectorAll('#search-queries [data-field="term"]')].map(field=>field.value.trim()).filter(Boolean);
 const skills=document.querySelectorAll('#profile-skills .config-row').length,languages=document.querySelectorAll('#profile-languages .config-row').length;
 const sources=[...document.querySelectorAll('#search-sources [data-field="enabled"]')].filter(field=>field.checked).length;
 $('#queries-summary').textContent=terms.length?`Puestos y lugares — ${terms.length} puestos configurados`:'Puestos y lugares — añade qué trabajo buscas';
 $('#profile-summary').textContent=`Tu perfil para valorar las ofertas — ${skills} habilidades — ${languages} idiomas`;
 $('#skills-summary').textContent=`Habilidades — ${skills}`;
 $('#languages-summary').textContent=`Idiomas — ${languages}`;
 $('#search-advanced-summary').textContent=`Ajustes avanzados (opcional) — ${sources} páginas activas`;
}
function showSearchConfig() {
 for(const key of profileKeys) {const input=$(`#profile-${key}`);if(input.type==='checkbox') input.checked=searchConfig.value[key];else input.value=searchConfig.value[key] ?? '';}
 $('#profile-qualifications').value=searchConfig.value.qualifications.join('\n');$('#search-excluded').value=searchConfig.value.excluded_employers.join('\n');
 for(const group of Object.keys(configRows)) {$(`#${group==='skills'||group==='languages'?'profile':'search'}-${group}`).replaceChildren();for(const row of searchConfig.value[group]) addConfigRow(group,row);}
 const criteria=$('#search-criteria');criteria.replaceChildren();
 for(const rule of searchConfig.value.criteria) {
  const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent=rule.label;detail.dataset.criterion=rule.id;detail.append(summary);
  for(const [key,label,max] of [['label','Nombre',200],['instruction','Instrucción de esta tarea',8000],['pending','Qué confirmar si se desconoce',1000]]) {
   const wrapper=document.createElement('label'),field=document.createElement(key==='instruction'?'textarea':'input');wrapper.textContent=label;field.dataset.criterionField=key;field.id=`criterion-${rule.id}-${key}`;field.value=rule[key];field.required=true;field.maxLength=max;if(key==='instruction') field.rows=5;wrapper.append(field);detail.append(wrapper);
  }
  criteria.append(detail);
 }
 $('#search-config-json').value=JSON.stringify(searchConfig.value,null,2);$('#search-config-state').textContent=`Revisión ${searchConfig.revision}`;updateConfigSummaries();
}
for(const [button,group] of [['add-skill','skills'],['add-language','languages'],['add-source','sources'],['add-query','queries']]) $(`#${button}`).onclick=()=>addConfigRow(group);
$('#search-config-form').addEventListener('input',updateConfigSummaries);$('#search-config-form').addEventListener('change',updateConfigSummaries);
$('#search-config-form').addEventListener('click',event=>{if(event.target.matches('#add-skill,#add-language,#add-source,#add-query,.config-row button')) updateConfigSummaries();});
$('#search-config-form').onsubmit=async event=>{
 event.preventDefault();$('#save-search-config').disabled=true;
 try {
  const value={};for(const key of profileKeys){const field=$(`#profile-${key}`);value[key]=field.type==='checkbox'?field.checked:key==='professional_years'?(field.value===''?null:Number(field.value)):key==='max_required_years'?Number(field.value):field.value;}
  value.qualifications=$('#profile-qualifications').value.split('\n').map(item=>item.trim()).filter(Boolean);value.excluded_employers=$('#search-excluded').value.split('\n').map(item=>item.trim()).filter(Boolean);
  for(const group of Object.keys(configRows)) value[group]=[...document.querySelectorAll(`[data-collection="${group}"]`)].map(row=>Object.fromEntries([...row.querySelectorAll('[data-field]')].map(field=>[field.dataset.field,field.type==='checkbox'?field.checked:field.type==='number'?Number(field.value):field.value])));
  value.criteria=[...document.querySelectorAll('[data-criterion]')].map(row=>({id:row.dataset.criterion,...Object.fromEntries([...row.querySelectorAll('[data-criterion-field]')].map(field=>[field.dataset.criterionField,field.value]))}));
  searchConfig=await api('search/config','PUT',{revision:searchConfig.revision,value});showSearchConfig();message('Perfil, fuentes y consultas guardados.');
 }catch(error){message(error.message);}finally{$('#save-search-config').disabled=false;}
};
let models={providers:[]};
let modelChoices={codex:'',openai:''};
function showModels() {
 const provider=$('#cfg-provider').value,entry=models.providers.find(item=>item.id===provider);
 const select=$('#model-choice');select.replaceChildren();
 if(provider==='codex') option(select,'','Predeterminado: GPT-6-Luna');
 for(const model of entry?.models || []) option(select,model.id,model.label);
 option(select,'__custom','Introducir otro modelo');
 const current=$('#cfg-model').value;
 select.value=[...select.options].some(item=>item.value===current)?current:'__custom';
 $('#custom-model-label').hidden=select.value!=='__custom';
 $('#cfg-model').required=provider==='openai';
 $('#model-status').textContent=provider==='openai'&&!entry?.configured
  ?'Para usar OpenAI, configura OPENAI_API_KEY en 11/.env. El consumo se cobra al proyecto de API.'
  :provider==='openai'
   ?'Lista de modelos de tu clave. No todos sirven para analizar ofertas.'
   :'El modelo predeterminado es GPT-6-Luna. El esfuerzo de razonamiento se configura por separado.';
}
$('#cfg-provider').onchange=()=>{const previous=Object.keys(modelChoices).find(key=>key!==$('#cfg-provider').value);modelChoices[previous]=$('#cfg-model').value;$('#cfg-model').value=modelChoices[$('#cfg-provider').value];showModels();};
$('#model-choice').onchange=()=>{$('#custom-model-label').hidden=$('#model-choice').value!=='__custom';if($('#model-choice').value!=='__custom') $('#cfg-model').value=$('#model-choice').value;else $('#cfg-model').focus();};
$('#refresh-models').onclick=async()=>{try{models=await api('models');showModels();}catch(error){message(error.message);}};
const numericSettings=['model_timeout_seconds','model_retries','max_openings','batch_size','max_age_days','quota_spain','quota_europe'];
const settingsFields=['reasoning_effort','max_openings','batch_size','max_age_days','timezone','history_ready','model_timeout_seconds','model_retries','quota_spain','quota_europe','source_prompt'];
function showSettings() {
  for (const key of settingsFields) {
    const value=settings.value[key];
    const field=$(`#cfg-${key}`); if (field.type==='checkbox') field.checked=value; else field.value=value;
  }
  $('#cfg-provider').value=settings.value.provider || 'codex';
  $('#cfg-model').value=settings.value.model || '';
  modelChoices[$('#cfg-provider').value]=$('#cfg-model').value;showModels();
  $('#settings-revision').textContent=`v${settings.revision}`;
  document.body.dataset.settingsRevision=settings.revision;
}
$('#settings-form').onsubmit=async event=>{
  event.preventDefault();
  const value={};
  for (const key of settingsFields) value[key]=$(`#cfg-${key}`).type==='checkbox'?$(`#cfg-${key}`).checked:numericSettings.includes(key)?Number($(`#cfg-${key}`).value):$(`#cfg-${key}`).value;
  value.provider=$('#cfg-provider').value;value.model=$('#cfg-model').value;
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
  $('#run-active').textContent=runs.filter(run=>['queued','running','unknown'].includes(run.status)).length;
  $('#run-submit').disabled=launchBlocked(workflow,runs,settings.value,runModule(),posting);
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
    button.textContent=`${runLabels[run.status]} — ${run.module==='search'?'Búsqueda de ofertas':run.module==='extraction'?'Análisis de ficha':'Contrato'}`;
    const meta=document.createElement('p');meta.className='muted';meta.textContent=`${new Date(run.created_at).toLocaleString('es-ES')} — configuración v${run.settings_revision}`;
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
  if(location.hash==='#results') await refreshResults();
}
let resultsRunId=null;
async function refreshResults() {
 const searches=runs.filter(run=>run.module==='search'),select=$('#results-run'),panel=$('#search-results');
 resultsRunId=searches.some(run=>run.id===resultsRunId)?resultsRunId:searches[0]?.id;
 select.replaceChildren();for(const run of searches) option(select,run.id,`${new Date(run.created_at).toLocaleString('es-ES')} — ${runLabels[run.status]}`);
 select.value=resultsRunId || '';panel.replaceChildren();
 if(!resultsRunId) {panel.textContent='Todavía no has ejecutado ninguna búsqueda.';return;}
 const run=searches.find(run=>run.id===resultsRunId);
 if(run.result) {const status=document.createElement('p');status.className='notice';status.textContent=`España ${run.result.spain}/${run.result.quota_spain} — Europa ${run.result.europe}/${run.result.quota_europe}. ${run.result.reason || ''}`;panel.append(status);}
 const content=document.createElement('div');
 await renderSearchPanel(run,content,true);
 if(resultsRunId===run.id) panel.append(content);
}
$('#results-run').onchange=()=>{resultsRunId=$('#results-run').value;refreshResults().catch(error=>message(error.message));};
async function renderRunDetail(id) {
  const run=await api(`workflow/runs/${id}?limit=25&offset=${taskOffsets[id] || 0}${taskStatuses[id]?`&task_status=${taskStatuses[id]}`:''}`);
  if (id!==selectedRunId) return;
  const panel=$('#run-detail');panel.replaceChildren();panel.dataset.runId=id;panel.dataset.status=run.status;
  const heading=document.createElement('h3');heading.textContent=`${run.module==='search'?'Búsqueda de ofertas':run.module==='extraction'?'Análisis de ficha':'Contrato'} — ${runLabels[run.status]}`;panel.append(heading);
  const counts=run.task_page.counts,total=run.task_page.total,complete=(counts.succeeded || 0)+(counts.failed || 0);
  if (total) {
    const label=document.createElement('p');label.textContent=['succeeded','failed'].includes(run.status)?`${complete} tareas ejecutadas — ${counts.pending || 0} sin ejecutar al cerrar`:`${complete} de ${total} tareas terminadas`;panel.append(label);
    const progress=document.createElement('progress');progress.max=total;progress.value=complete;progress.setAttribute('aria-label','Tareas terminadas');panel.append(progress);
  }
  if (run.error) {const error=document.createElement('p');error.className='notice';error.textContent=run.error;panel.append(error);}
  const labels=Object.fromEntries(workflow.modules.flatMap(module=>module.tasks || []).map(task=>[task.id,task.label]));
  if(run.module==='search') await renderSearchPanel(run,panel);
  const taskControls=document.createElement('div'),filterLabel=document.createElement('label'),taskFilter=document.createElement('select');
  filterLabel.textContent='Filtrar tareas por estado';taskFilter.id='task-status-filter';
  for(const [value,label] of [['','Todas'],['pending','Pendientes'],['running','En ejecución'],['succeeded','Terminadas'],['failed','Fallidas'],['unknown','Inciertas']]) option(taskFilter,value,`${label}${value?` (${counts[value] || 0})`:''}`);
  taskFilter.value=taskStatuses[id] || '';taskFilter.onchange=async()=>{taskStatuses[id]=taskFilter.value;taskOffsets[id]=0;try{await renderRunDetail(id);}catch(error){message(error.message);}};
  filterLabel.append(taskFilter);taskControls.append(filterLabel);
  const taskRange=document.createElement('p');taskRange.textContent=`Tareas mostradas: ${run.tasks.length?run.task_page.offset+1:0}–${run.task_page.offset+run.tasks.length} de ${run.task_page.filtered_total} — ${total} en total`;taskControls.append(taskRange);
  for(const [label,offset] of [['Tareas anteriores',Math.max(0,(taskOffsets[id] || 0)-25)],['Tareas siguientes',run.task_page.next_offset]]) {
   const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=label==='Tareas anteriores'?!taskOffsets[id]:offset===null;
   button.onclick=async()=>{taskOffsets[id]=offset;try{await renderRunDetail(id);}catch(error){message(error.message);}};taskControls.append(button);
  }
  panel.append(taskControls);
  for (const task of run.tasks) {
    const article=document.createElement('article');article.className='task-result';article.dataset.taskId=task.task_id;article.dataset.status=task.status;
    const title=document.createElement('h4');title.textContent=`${String(task.position).padStart(2,'0')} — ${labels[task.task_id] || task.task_id}`;
    const status=document.createElement('span');status.className=`badge ${task.status}`;
    status.textContent=taskStatusLabel(task,run.status);
    article.append(title,status);
    if (task.result?.state==='acreditado') {
      const value=document.createElement('p');value.textContent=task.result.value;
      const quote=document.createElement('blockquote');quote.textContent=task.result.evidence;article.append(value,quote);
    }
    if(task.result && !task.result.state) {const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Datos de la operación';pre.textContent=JSON.stringify(task.result,null,2);details.append(summary,pre);article.append(details);}
    if (task.error) {const error=document.createElement('p');error.textContent=task.error;article.append(error);}
    panel.append(article);
  }
  if (!total && run.result) {const p=document.createElement('p');p.textContent=run.result.value;panel.append(p);if(run.result.evidence){const q=document.createElement('blockquote');q.textContent=run.result.evidence;panel.append(q);}}
  if (run.n8n_execution_id) {const link=document.createElement('a');link.href=`http://localhost:5678/workflow/${run.module==='search'?'empleoSearch03':run.module==='extraction'?'empleoExtraction02':'empleoContract01'}/executions/${encodeURIComponent(run.n8n_execution_id)}`;link.target='_blank';link.rel='noopener';link.textContent=`Ejecución ${run.n8n_execution_id} en n8n ↗`;panel.append(link);}
  const meta=document.createElement('p');meta.className='muted';meta.textContent=`ID: ${id} — ${new Date(run.created_at).toLocaleString('es-ES')}`;panel.append(meta);
}
async function renderSearchPanel(run,panel,resultsOnly=false) {
 const data=await api(`search/runs/${run.id}/results?limit=25&offset=0`);
 if(resultsOnly) {
  for(let offset=data.candidates.length;data.candidates.length && offset%25===0;offset+=25) {
   const page=await api(`search/runs/${run.id}/results?limit=25&offset=${offset}`);
   data.candidates.push(...page.candidates);if(page.candidates.length<25) break;
  }
 }
 const state=data.state;
 if(!resultsOnly) {
 const controls=document.createElement('div');controls.className='search-controls';
 let browserTask;
 try {browserTask=await api(`search/runs/${run.id}/browser-task`);}
 catch(error) {const notice=document.createElement('p');notice.className='notice';notice.textContent=`No se pudo consultar la tarea de navegador: ${error.message}. Actualiza el estado para reintentar.`;controls.append(notice);}
 if(browserTask && ['running','unknown'].includes(run.status)) {
  const notice=document.createElement('p');notice.className='notice';
  notice.textContent=state.control==='paused'?'Búsqueda pausada. Reanúdala para continuar la navegación.':browserTask.status==='running'?'El navegador automático está revisando la página.':`${{discover:'La búsqueda espera consultar el buscador',read:'La búsqueda espera leer la ficha',browser_apply:'La búsqueda espera comprobar el formulario público'}[browserTask.kind] || 'La búsqueda espera navegación'}. El navegador automático continuará la tarea; si aparece un error, revísalo antes de reintentar. No se rellenará ni enviará ningún formulario.`;
  controls.append(notice);
 }
 if(((run.task_page.counts.failed || 0)+(run.task_page.counts.unknown || 0)) && !run.tasks.some(task=>['failed','unknown'].includes(task.status))) {const hint=document.createElement('p');hint.className='notice';hint.textContent='Hay tareas fallidas o inciertas fuera de esta página. Usa el filtro de tareas para revisarlas y resolverlas.';controls.append(hint);}
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
 const controlLabel=document.createElement('p');controlLabel.textContent=`Búsqueda: ${run.status==='succeeded'?'cerrada':state.control==='active'?'activa':state.control==='paused'?'pausada':'cancelada'} — control v${state.revision}`;controls.append(controlLabel);panel.append(controls);
 if(run.result) {
  const report=document.createElement('section');report.className='search-summary';const title=document.createElement('h3');title.textContent=run.status!=='succeeded'?'Avance de la búsqueda':run.result.fulfilled?'Reparto verificado':'Búsqueda cerrada con déficit';
  const totals=document.createElement('p');totals.textContent=`España ${run.result.spain}/${run.result.quota_spain} — Europa ${run.result.europe}/${run.result.quota_europe} — Fichas ${run.result.openings}/${run.result.max_openings}. Motivo: ${run.result.reason}.`;
  const deficits=document.createElement('p');deficits.textContent=`Faltan ${run.result.deficit_spain} de España y ${run.result.deficit_europe} del resto de Europa. Corte: ${new Date(run.result.cutoff).toLocaleString('es-ES',{timeZone:run.result.timezone})}.`;
  report.append(title,totals,deficits);
  if(run.result.summary) {
   const summary=run.result.summary,p=document.createElement('p');
   p.textContent=`Total computable: ${summary.computable}/${run.result.quota_spain+run.result.quota_europe} — A ${summary.classes.A} — B ${summary.classes.B} — C ${summary.classes.C} — Pistas ${summary.classes.pista}. B que cuentan: ${summary.b_computable}; fuera del cupo: ${summary.b_not_computable}. Encaje de finalistas: favorable ${summary.fit.favorable}, condicionado ${summary.fit.condicionado}, débil ${summary.fit['débil']}, desconocido ${summary.fit.desconocido}.`;
   report.append(p);
   if(summary.fit['débil']>summary.computable/2) {const warning=document.createElement('p');warning.className='notice';warning.textContent='Predominan los encajes débiles entre las finalistas computables.';report.append(warning);}
  }
 const link=document.createElement('a');link.href='#results';link.textContent='Ver ofertas clasificadas →';link.onclick=()=>{resultsRunId=run.id;};report.append(link);panel.append(report);
 }
 }
 if(!resultsOnly) return;
 const diagnostics=document.createElement('section'),diagnosticTitle=document.createElement('h3');
 diagnosticTitle.textContent='Estado de la búsqueda y fuentes';diagnostics.append(diagnosticTitle);
 if(run.error) {const error=document.createElement('p');error.className='notice';error.textContent=run.error;diagnostics.append(error);}
 if(data.state.report_files_error) {const error=document.createElement('p');error.className='notice';error.textContent=data.state.report_files_error;diagnostics.append(error);}
 const issues=data.diagnostics || [];
 if(!issues.length) {const status=document.createElement('p');status.textContent=['queued','running'].includes(run.status)?'Búsqueda en curso. Aún no hay diagnósticos de las fuentes.':run.status==='unknown'?'Resultado incierto. Revisa la ejecución antes de volver a iniciarla.':run.status==='failed'?'La búsqueda ha fallado. Consulta las tareas en Ejecutar.':'No hay fallos registrados en las tareas.';diagnostics.append(status);}
 for(const task of issues) {
  const item=document.createElement('article'),title=document.createElement('h4'),reason=document.createElement('p');
  const result=task.result || {},status=result.status || task.status;
  const labels={captcha:'Bloqueada por CAPTCHA',blocked:'Acceso bloqueado',error:'Error',failed:'Tarea fallida',unknown:'Resultado incierto',ok:'Fuente consultada',succeeded:'Consulta terminada'};
  const source={'browser:google':'Google','browser:bing':'Bing'}[task.input?.source] || task.input?.source || task.kind;
  title.textContent=`${source}${task.input?.term?' — '+task.input.term:''} — ${result.skipped?'Consulta omitida tras bloqueo':labels[status] || status}`;
  item.className=['captcha','blocked','error','failed','unknown'].includes(status) || task.error?'notice':'source-diagnostic';
  reason.textContent=task.error || result.reason || (task.kind==='discover'?`Páginas leídas: ${result.pages ?? 0}. Ofertas recibidas: ${result.received ?? 0}; aceptadas: ${result.accepted ?? 0}.`:'Sin causa adicional registrada.');
  item.append(title,reason);diagnostics.append(item);
 }
 panel.append(diagnostics);
 const groups=new Map();
 for(const [key,label] of [['A','Recomendadas y verificadas'],['B','Pendientes de comprobar'],['C','Excluidas'],['pista','Sin clasificar — pistas']]) {
  const section=document.createElement('section'),heading=document.createElement('h3');
  heading.textContent=`${key==='pista'?'':key+' — '}${label} (${data.candidates.filter(item=>(item.evaluation?.classification || 'pista')===key).length})`;section.append(heading);groups.set(key,section);panel.append(section);
  if(!data.candidates.some(item=>(item.evaluation?.classification || 'pista')===key)) {const empty=document.createElement('p');empty.className='muted';empty.textContent='Sin ofertas en este grupo.';section.append(empty);}
 }
 const heading=document.createElement('h3');heading.textContent='Ofertas y pistas investigadas';panel.prepend(heading);
 for(const candidate of data.candidates) {
  const article=document.createElement('article');article.className='search-result';article.dataset.candidateId=candidate.id;article.dataset.classification=candidate.evaluation?.classification || 'pista';
  const title=document.createElement('h4');title.textContent=`${candidate.title} — ${candidate.company}`;
  const classification=document.createElement('p');const evaluation=candidate.evaluation;
  classification.textContent=evaluation?`${{A:'A — Recomendada y verificada',B:'B — Pendiente',C:'C — Excluida',pista:'Pista sin ficha completa'}[evaluation.classification]} — ${evaluation.computable?'Computable':'No computable'}${evaluation.country?` — ${evaluation.country}`:''}`:candidate.stage==='blocked'?'Identidad o lectura pendiente — No computable':candidate.stage==='extracting'?'Ficha completa — análisis en curso':candidate.stage==='reading'?'Lectura en curso':'Pista sin ficha completa — No computable';
  const sourceLabel={'browser:google':'Google','browser:bing':'Bing'}[candidate.source] || candidate.source;
  const link=document.createElement('a');link.href=candidate.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=`Ver en ${sourceLabel} ↗`;
  article.append(title,classification,link);
  if(candidate.prior_candidate_id) {const continuity=document.createElement('p');continuity.textContent=`Recuperada de una búsqueda anterior — Proceso ${candidate.process_id || candidate.id}`;article.append(continuity);}
  if(evaluation?.fit_explanation) {const fit=document.createElement('p');fit.textContent=`Encaje ${evaluation.fit}: ${evaluation.fit_explanation}${evaluation.fit_evidence?' Cita: «'+evaluation.fit_evidence+'»':''}`;article.append(fit);}
  for(const exclusion of evaluation?.exclusions || []) {const p=document.createElement('p');p.textContent=`${exclusion.rule}: ${exclusion.evidence}`;article.append(p);}
  if(evaluation?.pending?.length) {const details=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('ul');summary.textContent=`${evaluation.pending.length} pendientes por resolver`;for(const pending of evaluation.pending){const li=document.createElement('li');li.textContent=`${pending.owner}: ${pending.resolution}`;list.append(li);}details.append(summary,list);article.append(details);}
  if(candidate.reason) {const p=document.createElement('p');p.textContent=candidate.reason;article.append(p);}
  const detailsButton=document.createElement('button');detailsButton.type='button';detailsButton.textContent='Ver detalles de la oferta';
  detailsButton.onclick=async()=>{detailsButton.disabled=true;try{const detail=await api(`search/candidates/${candidate.id}?include_text=true`);renderCandidateTools(detail,article,data.candidates);const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Descripción y datos extraídos';details.open=true;if(detail.document?.text){const description=document.createElement('p');description.className='offer-description';description.textContent=detail.document.text;details.append(description);}for(const task of detail.tasks.filter(item=>item.kind.startsWith('extract_'))) {const field=document.createElement('p');field.textContent=`${task.kind.slice(8)}: ${task.result?.value || 'No consta'}`;details.append(field);if(task.result?.evidence){const quote=document.createElement('blockquote');quote.textContent=task.result.evidence;details.append(quote);}}details.prepend(summary);article.append(details);}catch(error){message(error.message);detailsButton.disabled=false;}};article.append(detailsButton);
  if(['A','B'].includes(evaluation?.classification) && !candidate.history?.needs_review) {
   const track=document.createElement('button');track.type='button';track.textContent=candidate.opportunity_id?'Ya en seguimiento':'Añadir al seguimiento';track.disabled=Boolean(candidate.opportunity_id);
   track.onclick=async()=>{track.disabled=true;try{await api(`search/candidates/${candidate.id}/track`,'POST',{});await load();await refreshWorkflow();message('Oferta incorporada al seguimiento; no se ha enviado candidatura.');}catch(error){message(error.message);track.disabled=false;}};article.append(track);
  }
  groups.get(candidate.evaluation?.classification || 'pista').append(article);
 }
 return;

}
function renderCandidateTools(candidate,article,candidates) {
 const application=candidate.application_check;
 if(application) {
  const status={pending:'Pendiente de revisar',accessible:'Formulario público accesible',login_required:'Requiere iniciar sesión',captcha:'Protegido por CAPTCHA',closed:'La vacante aparece cerrada',blocked:'Acceso bloqueado',unknown:'No se pudo confirmar'}[application.status] || application.status;
  const check=document.createElement('section'),heading=document.createElement('h5'),result=document.createElement('p');heading.textContent='Comprobación de candidatura';result.textContent=`${status}${application.form_found===true?' — formulario visible':''}`;check.append(heading,result);
  if(application.required_fields?.length) {const p=document.createElement('p');p.textContent=`Campos obligatorios visibles: ${application.required_fields.join(', ')}`;check.append(p);}
  if(application.evidence || application.reason) {const quote=document.createElement('blockquote');quote.textContent=application.evidence || application.reason;check.append(quote);}
  if(application.application_url) {const link=document.createElement('a');link.href=application.application_url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Abrir página de candidatura ↗';check.append(link);}
  article.append(check);
 }
 const section=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Resolver identidad o corregir un dato';section.append(summary);
 const identity=document.createElement('form'),resolution=document.createElement('select'),target=document.createElement('select'),reason=document.createElement('input'),save=document.createElement('button');
 const labelled=(text,field)=>{const label=document.createElement('label');label.textContent=text;label.append(field);return label;};
 for(const [value,label] of [['distinct','Es otra convocatoria'],['same_process','Es un proceso del seguimiento'],['duplicate','Es duplicada de otra pista']]) option(resolution,value,label);
 const targets=()=>{target.replaceChildren();option(target,'','Seleccionar destino');for(const item of resolution.value==='same_process'?offers:candidates.filter(item=>item.id!==candidate.id)) option(target,item.id,`${item.title} — ${item.company}`);target.hidden=resolution.value==='distinct';target.required=resolution.value!=='distinct';};resolution.onchange=targets;targets();reason.required=true;reason.maxLength=2000;save.textContent='Guardar resolución';
 identity.append(labelled('Identidad',resolution),labelled('Proceso principal',target),labelled('Motivo de la resolución',reason),save);
 identity.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await api(`search/candidates/${candidate.id}/identity`,'POST',{version:candidate.version,resolution:resolution.value,...(resolution.value==='same_process'?{target_offer_id:target.value}:resolution.value==='duplicate'?{duplicate_candidate_id:target.value}:{}),reason:reason.value});await refreshWorkflow();message('Identidad y recuentos actualizados.');}catch(error){message(error.message);save.disabled=false;}};section.append(identity);
 const correction=document.createElement('form'),field=document.createElement('select'),value=document.createElement('input'),verdict=document.createElement('select'),evidence=document.createElement('textarea'),why=document.createElement('input'),apply=document.createElement('button');
 for(const [key,label] of [['country','País del puesto (código ISO)'],['publication','Fecha de publicación'],['fit','Encaje profesional'],...['seniority','experience','education','technology','languages','contract','functions','remote','video','availability','channel'].map(key=>[`decision:${key}`,key])]) option(field,key,label);
 for(const [key,label] of [['cumple','Cumple'],['incumple','Incumple'],['desconocido','Desconocido']]) option(verdict,key,label);
 const type=()=>{const decision=field.value.startsWith('decision:') || field.value==='fit';value.hidden=decision;value.required=!decision;verdict.hidden=!decision;verdict.replaceChildren();for(const [key,label] of field.value==='fit'?[['favorable','Favorable'],['condicionado','Condicionado'],['débil','Débil'],['desconocido','Desconocido']]:[['cumple','Cumple'],['incumple','Incumple'],['desconocido','Desconocido']]) option(verdict,key,label);value.type=field.value==='publication'?'date':'text';value.placeholder=field.value==='country'?'ES, GB, DE…':'';};field.onchange=type;type();evidence.required=true;evidence.rows=3;evidence.maxLength=10000;why.required=true;why.maxLength=2000;apply.textContent='Guardar corrección con evidencia';
 correction.append(labelled('Dato a corregir',field),labelled('Valor corregido',value),labelled('Veredicto corregido',verdict),labelled('Cita literal del documento',evidence),labelled('Motivo de la corrección',why),apply);
 correction.onsubmit=async event=>{event.preventDefault();apply.disabled=true;try{await api(`search/candidates/${candidate.id}/correction`,'POST',{version:candidate.version,field:field.value,value:field.value.startsWith('decision:') || field.value==='fit'?verdict.value:value.value,evidence:evidence.value,reason:why.value});await refreshWorkflow();message('Corrección, evidencias y recuentos guardados.');}catch(error){message(error.message);apply.disabled=false;}};section.append(correction);article.append(section);
}
function runModule() {return document.querySelector('[name=run-module]:checked').value;}
function updateRunScope() {
  const module=runModule();
  $('#run-submit').textContent=posting?'Iniciando…':({search:'Iniciar búsqueda completa',extraction:'Analizar esta oferta',contract:'Extraer contrato'})[module];
  if(workflow && settings) {
   const reason=launchBlockReason(workflow,runs,settings.value,module,posting);
   $('#run-submit').disabled=Boolean(reason);
   $('#run-blocker').textContent=reason;$('#run-blocker').hidden=!reason;
   $('#enable-workflow').hidden=workflow.control.enabled;
   $('#pause-workflow').hidden=!workflow.control.enabled;
  }
  const search=runModule()==='search';$('#run-text').required=!search;$('#run-text').closest('label').hidden=search;
  if(search) {$('#run-scope').textContent=`Recorrido completo: buscar → revisar → evaluar → resultados. Máximo ${settings.value.max_openings} lecturas; objetivo ${settings.value.quota_spain} España + ${settings.value.quota_europe} Europa. Motor: ${settings.value.provider==='openai'?'API de OpenAI':'Codex (suscripción)'} — modelo: ${settings.value.model || 'gpt-6-luna'} — thinking ${settings.value.reasoning_effort || 'max'}. Puedes pausar entre tareas.`;return;}
  $('#run-scope').textContent=runModule()==='extraction'?'15 llamadas consecutivas al modelo. Cada dato se guarda por separado con su cita literal. Puede tardar varios minutos. No clasifica ni verifica páginas externas.':'Una llamada al modelo para extraer únicamente el contrato y su cita.';
}
document.querySelectorAll('[name=run-module]').forEach(input=>{input.onchange=()=>{requestId=null;updateRunScope();};});
for (const id of ['enable-workflow','pause-workflow']) $(`#${id}`).onclick=async()=>{
  $('#enable-workflow').disabled=true; $('#pause-workflow').disabled=true;
  try {await api('workflow/control','PUT',{enabled:id==='enable-workflow',revision:workflow.control.revision}); await refreshWorkflow();} catch(error) {message(error.message); await refreshWorkflow().catch(()=>{});}
};
$('#refresh-workflow').onclick=async()=>{
  const button=$('#refresh-workflow');button.disabled=true;
  message('');
  try {
    const refreshOffers=document.body.dataset.page==='seguimiento'?(selected?refreshSelected():load()):Promise.resolve();
    await Promise.all([refreshWorkflow(),refreshOffers]);
    const feedback=$('#refresh-feedback');feedback.textContent='Estado actualizado';feedback.hidden=false;
  } catch(error) {message(error.message);}
  finally {button.disabled=false;}
};
$('#run-text').oninput=()=>{requestId=null;};
$('#run-form').onsubmit=async event=>{
  event.preventDefault(); if (posting) return;
  posting=true; updateRunScope(); requestId ||= crypto.randomUUID();
  try {const run=await api('workflow/runs','POST',{id:requestId,module:runModule(),text:$('#run-text').value}); selectedRunId=run.id; requestId=null; message('Ejecución iniciada. Sigue el progreso en «Ejecuciones y resultados».');document.querySelector('#runs').scrollIntoView({behavior:'smooth',block:'start'});} catch(error) {message(error.message);} finally {posting=false; await refreshWorkflow().catch(error=>message(error.message));}
};
function renderEndpointCatalog(integration) {
  const container=$('#endpoint-catalog');
  container.replaceChildren();
  const endpoints=[...integration.tools,...integration.http_endpoints];
  for (const endpoint of endpoints) {
    const item=document.createElement('details'),summary=document.createElement('summary');
    item.className='endpoint';
    item.dataset.search=[endpoint.name,endpoint.method,endpoint.path,endpoint.description,endpoint.returns].filter(Boolean).join(' ').toLowerCase();
    summary.textContent=`${endpoint.method} ${endpoint.path}${endpoint.name?` — ${endpoint.name}`:' — Solo HTTP'}`;
    item.append(summary);
    if (endpoint.name) {
      const description=document.createElement('p');
      description.textContent=`${endpoint.readOnly?'Consulta':'Modifica datos o controla tareas'} — ${endpoint.description}`;
      item.append(description);
    }
    const output=document.createElement('p');output.textContent=`Devuelve: ${endpoint.returns}`;item.append(output);
    const label=document.createElement('h4');label.textContent=endpoint.name?'Parámetros MCP (JSON Schema)':'Parámetros HTTP';item.append(label);
    const input=document.createElement('pre');input.textContent=endpoint.inputSchema?JSON.stringify(endpoint.inputSchema,null,2):endpoint.input;item.append(input);
    container.append(item);
  }
  const filter=()=>{
    const term=$('#endpoint-filter').value.trim().toLowerCase();
    for (const item of container.children) item.hidden=!item.dataset.search.includes(term);
    $('#endpoint-count').textContent=`${[...container.children].filter(item=>!item.hidden).length} de ${endpoints.length} operaciones — ${integration.tools.length} herramientas MCP`;
  };
  $('#endpoint-filter').oninput=filter;
  filter();
}

function route() {
  if (['run-form','runs','enable-workflow'].includes(location.hash.slice(1))) return;
  const page=['control','configuration','results','seguimiento','integrations'].includes(location.hash.slice(1))?location.hash.slice(1):'control';
  document.body.dataset.page=page;
  for (const view of document.querySelectorAll('[data-view]')) view.hidden=view.dataset.view!==page;
  for (const link of document.querySelectorAll('[data-page]')) link.classList.toggle('active',link.dataset.page===page);
  $('#page-title').textContent={control:'Ejecutar',results:'Resultados de la búsqueda',configuration:'Configura tu búsqueda',seguimiento:'Postulaciones',integrations:'Conecta tu asistente'}[page];
  $('#page-subtitle').textContent={control:'Elige el alcance, inicia una ejecución y consulta sus resultados.',results:'Ofertas separadas por clasificación, con sus detalles y comprobaciones.',configuration:'Elige qué buscar, qué perfil usar y qué modelo lo analizará.',seguimiento:'Gestiona candidaturas, publicaciones y próximos pasos.',integrations:'Herramientas MCP para consultar, configurar y operar la aplicación.'}[page];
}
window.addEventListener('hashchange',()=>{route();if(location.hash==='#results') refreshResults().catch(error=>message(error.message));}); route();
try {
  for (const [state,label] of Object.entries(offerStates)) {option($('[name=status]'),state,label); option($('#filter'),state,label);}
  await load(); searchConfig=await api('search/config');showSearchConfig(); models=await api('models'); settings=await api('settings'); showSettings(); await refreshWorkflow();
  const integration=await api('integration');
  $('#integration-state').textContent=integration.configured?'MCP configurado — stdio y HTTP disponibles':'Falta configurar MCP_TOKEN en 11/.env y reiniciar el servicio.';
  $('#mcp-stdio-config').value=JSON.stringify(integration.stdio,null,2);
  $('#mcp-http-config').value=JSON.stringify(integration.http,null,2);
  document.body.dataset.mcpEndpoint=integration.endpoint;
  renderEndpointCatalog(integration);
  document.body.dataset.appState='ready';
  setInterval(renderTodayCounts,60000);
  setInterval(()=>{if (!document.hidden && !$('#run-detail').contains(document.activeElement) && runs.some(run=>['queued','running'].includes(run.status))) refreshWorkflow().catch(error=>message(error.message));},3000);
} catch(error) {
  $('#connection-banner').hidden=false; $('#connection-banner').textContent=error.message;
  document.body.dataset.appState='error';
  for (const control of document.querySelectorAll('form input, form select, form textarea, form button, #enable-workflow, #pause-workflow')) control.disabled=true;
} finally {
  $('main').setAttribute('aria-busy','false');
}
