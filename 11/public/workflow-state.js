export function launchBlocked(workflow,runs,settings,module,posting=false) {
  return posting || !workflow.reachable || !workflow.control.enabled
    || runs.some(run=>['queued','running','unknown'].includes(run.status))
    || (module==='search' && !settings.history_ready);
}

export function taskStatusLabel(task,runStatus) {
  if(task.status==='succeeded') return task.result?.state==='desconocido'?'No consta en el texto':task.result?.state==='acreditado'?'Con evidencia':'Completada';
  if(task.status==='pending') return ['succeeded','failed'].includes(runStatus)?'No ejecutada: cierre':'En espera';
  return {queued:'En cola',running:'Ejecutando',failed:'Fallida',unknown:'Resultado incierto'}[task.status] || task.status;
}
