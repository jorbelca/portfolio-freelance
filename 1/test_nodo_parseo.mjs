// Comprueba el nodo "Parsear Clasificación" del workflow de triage. Extrae el código real
// del JSON (no una copia: si el nodo cambia en la UI y se reexporta, este test lo ve) y lo
// ejecuta con un $input y un $env falsos.
//
//     node test_nodo_parseo.mjs
//
// Cubre las dos reglas que el prompt por sí solo no puede garantizar: el recorte de confianza
// cuando el modelo declara una categoría rival, y el umbral asimétrico de 'ruido'.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const doc = JSON.parse(readFileSync(new URL('./Tarea 1 - Triage.json', import.meta.url), 'utf8'));
const nodo = doc.nodes.find((n) => n.name === 'Parsear Clasificación');
assert.ok(nodo, 'no existe el nodo "Parsear Clasificación" en el workflow');

const parsear = new Function('$input', '$env', nodo.parameters.jsCode);

const ENV = { TRIAGE_CONFIANZA_UMBRAL: '0.7', TRIAGE_CONFIANZA_UMBRAL_RUIDO: '0.9' };
const uno = (output, env = ENV) => parsear({ all: () => [{ json: { output } }] }, env)[0].json;

// --- recorte por categoría rival ------------------------------------------------------
// e07 de la evaluación: el modelo aplicó el desempate plazo > cliente_nuevo y aun así se
// puntuó 1.00. Declarada la rival, la confianza se recorta y el correo va a revisión.
let r = uno({ categoria: 'plazo', categoria_rival: 'cliente_nuevo', motivo: 'x', confianza: 1 });
assert.equal(r.confianza, 0.6);
assert.equal(r.accion, 'revision_humana');
assert.equal(r.decidido_por, 'umbral');

// Una rival que repite la categoría elegida no es rival de nada.
assert.equal(uno({ categoria: 'plazo', categoria_rival: 'plazo', motivo: 'x', confianza: 1 }).confianza, 1);

// Si el modelo omite la rival, el flujo no se cae: se trata como 'ninguna'.
assert.equal(uno({ categoria: 'plazo', motivo: 'x', confianza: 1 }).categoria_rival, 'ninguna');

// --- umbral asimétrico de 'ruido' -----------------------------------------------------
// Archivar es la única rama sin rastro: exige 0.9, no el 0.7 general.
assert.equal(uno({ categoria: 'ruido', categoria_rival: 'ninguna', motivo: 'x', confianza: 0.9 }).umbral_aplicado, 0.9);
assert.equal(uno({ categoria: 'ruido', categoria_rival: 'ninguna', motivo: 'x', confianza: 0.9 }).accion, 'archivado');

// e24 salió a 0.90 y e22 a 1.00, pero un ruido a 0.85 ya no se archiva solo.
r = uno({ categoria: 'ruido', categoria_rival: 'ninguna', motivo: 'x', confianza: 0.85 });
assert.equal(r.accion, 'revision_humana');
assert.equal(r.decidido_por, 'umbral');

// La asimetría afecta solo a ruido: 0.85 en cualquier otra categoría sigue pasando.
assert.equal(uno({ categoria: 'cliente_nuevo', categoria_rival: 'ninguna', motivo: 'x', confianza: 0.85 }).accion, 'ficha_creada');

// --- robustez -------------------------------------------------------------------------
// El modelo devuelve el JSON envuelto en prosa.
assert.equal(uno('texto {"categoria":"duda","categoria_rival":"ruido","motivo":"x","confianza":0.5} más texto').accion, 'revision_humana');

// Confianza ausente o no numérica cuenta como 0.
assert.equal(uno({ categoria: 'cliente_nuevo', categoria_rival: 'ninguna', motivo: 'x' }).confianza, 0);

// Umbral mal configurado: NaN hace la comparación false. Falla cerrado a revisión humana,
// nunca archiva por defecto.
assert.equal(uno({ categoria: 'ruido', categoria_rival: 'ninguna', motivo: 'x', confianza: 1 },
  { TRIAGE_CONFIANZA_UMBRAL: 'sin_configurar' }).accion, 'revision_humana');

console.log('OK: nodo "Parsear Clasificación" — recorte por rival y umbral asimétrico de ruido');
