import {spawn} from 'node:child_process';
import {mkdtemp, writeFile, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {openaiExtraction} from './models.js';
import {extractionPrompt} from './tasks.js';
export function validateExtraction(result, text) {
  if (!result || typeof result.value !== 'string' || typeof result.evidence !== 'string' || !['acreditado', 'desconocido'].includes(result.state)) throw new Error('Respuesta de Codex inválida');
  if (result.state === 'acreditado' && (!result.value.trim() || !result.evidence.trim() || !text.includes(result.evidence))) throw new Error('La cita no aparece en la ficha');
  if (result.state === 'desconocido' && (result.value !== 'desconocido' || result.evidence !== '')) throw new Error('Dato desconocido inconsistente');
  return result;
}
let busy = false;
export const extractContract=(text,model)=>extractField('contract',text,model);
export async function extractField(taskId, text, model) {
  return extractPrompt(extractionPrompt(taskId,text),text,model);
}
export async function extractPrompt(prompt,text,model) {
  if (typeof text !== 'string' || !text.trim() || text.length > 100000) throw new Error('Texto requerido, máximo 100.000 caracteres');
  const config=typeof model==='object' && model!==null?model:{model,provider:'codex'};
  if (!['codex','openai'].includes(config.provider ?? 'codex')) throw new Error('Motor no admitido');
  if (config.provider==='openai') return validateExtraction(await openaiExtraction(prompt,config.model),text);
  model=config.model || process.env.CODEX_MODEL;
  if (busy) throw Object.assign(new Error('Codex ocupado, reintenta después'), {status: 429});
  busy = true;
  let directory;
  try {
    directory = await mkdtemp(join(tmpdir(), 'empleo-'));
    const schema = {type: 'object', additionalProperties: false, properties: {
      value: {type: 'string'}, evidence: {type: 'string'}, state: {type: 'string', enum: ['acreditado', 'desconocido']}
    }, required: ['value', 'evidence', 'state']};
    await writeFile(join(directory, 'schema.json'), JSON.stringify(schema));
    const args = ['exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only', '-C', directory,
      '--output-schema', join(directory, 'schema.json'), '--output-last-message', join(directory, 'output.json')];
    if (model) args.push('--model', model);
    args.push('-');
    await new Promise((resolve, reject) => {
      // shortcut: una extracción simultánea por proceso, ampliar con cola persistente al añadir búsquedas.
      const child = spawn('codex', args, {stdio: ['pipe', 'ignore', 'ignore'], env: {
        PATH: process.env.PATH, HOME: process.env.HOME, TMPDIR: tmpdir()
      }});
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error('Codex agotó el tiempo de espera'));
      }, Number(process.env.CODEX_TIMEOUT_MS || 120000));
      child.once('error', error => {clearTimeout(timer); reject(error);});
      child.once('close', code => {clearTimeout(timer); code === 0 ? resolve() : reject(new Error('Codex falló. Comprueba sesión, modelo y cuota con codex login status.'));});
      child.stdin.on('error', () => {});
      child.stdin.end(prompt);
    });
    return validateExtraction(JSON.parse(await readFile(join(directory, 'output.json'), 'utf8')), text);
  } finally {
    busy = false;
    if (directory) await rm(directory, {recursive: true, force: true});
  }
}
