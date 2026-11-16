export function launchBlockReason(workflow,runs,settings,module,posting=false) {
  if(posting) return 'Iniciando la ejecución…';
  if(!workflow.reachable) return 'El motor n8n no está conectado. Revisa el servicio y pulsa Actualizar estado.';
  const active=runs.find(run=>['queued','running','unknown'].includes(run.status));
  if(active) return active.status==='unknown'?'Hay una ejecución con resultado incierto. Revísala en Ejecuciones y resultados antes de iniciar otra.':'Ya hay una ejecución en curso. Puedes seguir su progreso en Ejecuciones y resultados.';
  if(!workflow.control.enabled) return 'Los nuevos inicios están pausados. Pulsa Habilitar ejecuciones y después inicia la opción elegida.';
  if(module==='search' && !settings.history_ready) return 'Confirma el historial de candidaturas en Configuración antes de iniciar una búsqueda completa.';
  return '';
}
export function launchBlocked(workflow,runs,settings,module,posting=false) {
  return Boolean(launchBlockReason(workflow,runs,settings,module,posting));
}

export function taskStatusLabel(task,runStatus) {
  if(task.status==='succeeded') return task.result?.state==='desconocido'?'No consta en el texto':task.result?.state==='acreditado'?'Con evidencia':'Completada';
  if(task.status==='pending') return ['succeeded','failed'].includes(runStatus)?'No ejecutada: cierre':'En espera';
  return {queued:'En cola',running:'Ejecutando',failed:'Fallida',unknown:'Resultado incierto'}[task.status] || task.status;
}
