import {createHash, randomUUID} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {cleanUrl, offerInput, validDate} from '../src/domain.js';

const portals = new Set(['infojobs','indeed','voxjobs','trabajo.org','jobijoba']);
export function parseDone(text) {
  const rows = [];
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!/^- \d{4}-/.test(line)) continue;
    const match = line.match(/^- (\d{4}-\d{2}-\d{2}): (inscripción|desestimada) — (.+?) — hecho(?:\s.*)?$/u);
    if (!match) throw new Error(`Formato no reconocido en línea ${index + 1}`);
    const [, date, action, description] = match;
    validDate(date);
    const parts = description.split(' | ');
    const identity = parts.pop();
    const key = identity.match(/^([\w]+):([^\s]+)$/u);
    if (!key) throw new Error(`Identidad inválida en línea ${index + 1}`);
    let title, company;
    if (parts.length === 2) [title, company] = parts;
    else if (parts.length === 1) {
      const separator = parts[0].lastIndexOf(' — ');
      if (separator < 0) throw new Error(`Falta empresa o portal en línea ${index + 1}`);
      title = parts[0].slice(0, separator);
      company = parts[0].slice(separator + 3);
    } else throw new Error(`Campos ambiguos en línea ${index + 1}`);
    const companyUnknown = portals.has(company.toLowerCase());
    const urls = [...new Set([...line.matchAll(/@url:(\S+)/g)].map(m => cleanUrl(m[1])))];
    const row = {line: index + 1, raw: line, date, action, portal: key[1], externalId: key[2] === 'sin-ID' ? null : key[2], urls, companyUnknown};
    row.input = offerInput({title, company: companyUnknown ? 'Empresa no indicada' : company,
      url: urls[0], availability: 'desconocida', review_state: action === 'desestimada' ? 'descartada' : 'guardada',
      application_state: action === 'inscripción' ? 'enviada' : 'sin_candidatura', submitted_at: null,
      notes: `Origen: Obsidian, Agenda/DONE.md, línea ${row.line}.\n${line}${companyUnknown ? `\nEmpresa no identificada en la nota; ${company} es el portal.` : ''}\nFecha histórica con precisión de día; hora desconocida.`,
      reason: 'Importación del historial real de Obsidian'});
    row.key = createHash('sha256').update(`Agenda/DONE.md\n${line}`).digest('hex');
    rows.push(row);
  }
  if (!rows.length) throw new Error('No se encontraron acciones de ofertas');
  return rows;
}

export async function importDone(client, rows) {
  // La transacción del llamador evita importaciones parciales y bloquea escrituras concurrentes.
  await client.query('LOCK TABLE opportunities, publications, opportunity_events IN SHARE ROW EXCLUSIVE MODE');
  const result = {entries: rows.length, created: 0, linked: 0, skipped: 0, ids: []};
  for (const row of rows) {
    const prior = (await client.query("SELECT opportunity_id FROM opportunity_events WHERE kind='obsidian_import' AND value->>'import_key'=$1", [row.key])).rows;
    if (prior.length) { result.skipped++; result.ids.push(prior[0].opportunity_id); continue; }
    const matches = (await client.query('SELECT DISTINCT opportunity_id FROM publications WHERE url=ANY($1::text[])', [row.urls])).rows;
    const identityMatches = (await client.query("SELECT DISTINCT opportunity_id FROM opportunity_events WHERE kind='obsidian_import' AND value->>'portal'=$1 AND value->>'external_id'=$2", [row.portal, row.externalId])).rows;
    const ids = [...new Set([...matches, ...identityMatches].map(r => r.opportunity_id))];
    if (ids.length > 1) throw new Error(`La línea ${row.line} coincide con varias ofertas; se cancela la importación`);
    let id = ids[0];
    if (!id) {
      id = randomUUID();
      const companyId = randomUUID();
      await client.query('INSERT INTO companies(id,name) VALUES($1,$2)', [companyId, row.input.company]);
      // submitted_at usa la misma convención de fecha civil UTC que el formulario; no acredita una hora.
      await client.query('INSERT INTO opportunities(id,company_id,title,availability,review_state,notes,state_changed_at) VALUES($1,$2,$3,$4,$5,$6,$7::date::timestamp AT TIME ZONE \'UTC\')', [id, companyId, row.input.title, row.input.availability, row.input.review_state, row.input.notes, row.date]);
      result.created++;
    } else {
      // El estado actual y el título conocido tienen prioridad sobre un apunte histórico.
      await client.query("UPDATE opportunities SET notes=notes || E'\n\n' || $2,state_changed_at=coalesce(state_changed_at,$3::date::timestamp AT TIME ZONE 'UTC'),review_state=CASE WHEN $4='desestimada' AND NOT EXISTS(SELECT 1 FROM applications WHERE opportunity_id=$1) THEN 'descartada' ELSE review_state END,version=version+1,updated_at=now() WHERE id=$1", [id, row.input.notes, row.date, row.action]);
      result.linked++;
    }
    if (row.action === 'inscripción') {
      await client.query("INSERT INTO applications(id,opportunity_id,state,submitted_at) VALUES($1,$2,'enviada',$3::date::timestamp AT TIME ZONE 'UTC') ON CONFLICT(opportunity_id) DO UPDATE SET submitted_at=coalesce(applications.submitted_at,excluded.submitted_at)", [randomUUID(), id, row.date]);
    }
    for (const url of row.urls) {
      const namespace = new URL(url).origin;
      const source = (await client.query('INSERT INTO sources(id,namespace,label) VALUES($1,$2,$2) ON CONFLICT(namespace) DO UPDATE SET namespace=excluded.namespace RETURNING id', [randomUUID(), namespace])).rows[0];
      await client.query('INSERT INTO publications(id,opportunity_id,source_id,url,is_primary) VALUES($1,$2,$3,$4,NOT EXISTS(SELECT 1 FROM publications WHERE opportunity_id=$2)) ON CONFLICT(url) DO NOTHING', [randomUUID(), id, source.id, url]);
    }
    await client.query("INSERT INTO opportunity_events(opportunity_id,kind,actor,reason,value) VALUES($1,'obsidian_import','migracion',$2,$3)", [id, row.input.reason, {import_key: row.key, source: 'Agenda/DONE.md', line: row.line, original: row.raw, date: row.date, date_precision: 'day', action: row.action, portal: row.portal, external_id: row.externalId, company_unknown: row.companyUnknown, urls: row.urls}]);
    result.ids.push(id);
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const rows = parseDone(await readFile(process.argv[2], 'utf8'));
  if (!process.argv.includes('--apply')) {
    console.log(JSON.stringify({entries: rows.length, registered: rows.filter(r => r.action === 'inscripción').length, discarded: rows.filter(r => r.action === 'desestimada').length, unknownCompany: rows.filter(r => r.companyUnknown).length, mode: 'preview'}));
  } else {
    const {pool, transaction} = await import('../src/db.js');
    try {
      const report = await transaction(async client => {
        const result = await importDone(client, rows);
        const summaries = (await client.query('SELECT id,excluded FROM offer_summary WHERE id=ANY($1::uuid[])', [result.ids])).rows;
        if (summaries.length !== new Set(result.ids).size || summaries.some(r => !r.excluded)) throw new Error('El historial no está completamente excluido');
        return {...result, uniqueOffers: summaries.length, allExcluded: true};
      });
      console.log(JSON.stringify(report));
    } finally { await pool.end(); }
  }
}
