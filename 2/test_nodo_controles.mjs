// Comprueba el nodo "Parsear y Aplicar Controles" del triage de incidencias. Extrae el código
// real del JSON (no una copia: si el nodo cambia en la UI y se reexporta, este test lo ve) y lo
// ejecuta con un $input y un $env falsos.
//
//     node test_nodo_controles.mjs
//
// Cubre las tres reglas que el prompt por sí solo NO garantiza, cada una porque falló de verdad
// en una ejecución contra Gemini:
//   1. Recorte de confianza cuando el modelo declara una imputación rival.
//   2. Umbral asimétrico: declarar "no hay plazo" exige más confianza que el resto.
//   3. Regla dura §6 de la rúbrica: si el fundamento sale de los estatutos, el sistema no cierra
//      el caso. En i01 el modelo citó literalmente el art. 4º de CDP-001 y aun así devolvió
//      'comun' con confianza 1.00 y rival 'ninguna', así que salió parte a proveedor sin que
//      nadie lo leyera. El test fija que eso ya no puede pasar.
//      La regla NO toca la imputación: medido sobre las 45 incidencias, forzar 'mixto' rompía 6
//      clasificaciones correctas y bajaba el acierto del 23.8% al 15.6%. Lo que fija ahora es la
//      acción, y quien enruta es 'Switch Acción' leyendo ese campo.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const doc = JSON.parse(
  readFileSync(new URL('./Tarea B1 - Triage Incidencias.json', import.meta.url), 'utf8'),
);
const nodo = doc.nodes.find((n) => n.name === 'Parsear y Aplicar Controles');
assert.ok(nodo, 'no existe el nodo "Parsear y Aplicar Controles" en el workflow');

const controles = new Function('$input', '$env', nodo.parameters.jsCode);

const ENV = { FINCAS_CONFIANZA_UMBRAL: '0.7', FINCAS_UMBRAL_SIN_PLAZO: '0.9' };
const uno = (output, env = ENV) => controles({ all: () => [{ json: { output } }] }, env)[0].json;

const LEY = [{ norma: 'art. 10.1 LPH', cita: 'x', fuente: 'ley' }];
const ESTATUTOS = [{ norma: 'art. 4º de los Estatutos', cita: 'x', fuente: 'estatutos' }];
const base = (extra) => ({
  imputacion: 'comun',
  imputacion_rival: 'ninguna',
  elemento_normalizado: 'terraza',
  fundamento: LEY,
  urgencia: false,
  requiere_junta: false,
  plazos_activos: [],
  confianza: 1,
  ...extra,
});

// --- 1. recorte por imputación rival --------------------------------------------------
let r = uno(base({ imputacion_rival: 'privativo' }));
assert.equal(r.confianza, 0.6, 'una rival defendible tiene que capar la confianza a 0.6');
assert.equal(r.accion, 'revision_administrador');
assert.equal(r.decidido_por, 'umbral');

// Una rival que repite la imputación elegida no es rival de nada.
assert.equal(uno(base({ imputacion_rival: 'comun' })).confianza, 1);

// Si el modelo omite la rival, el flujo no se cae: se trata como 'ninguna'.
assert.equal(uno(base({ imputacion_rival: undefined })).imputacion_rival, 'ninguna');

// --- 2. umbral asimétrico -------------------------------------------------------------
// Sin plazo declarado hace falta 0.9: decir "aquí no corre ningún plazo" es la decisión que no
// deja rastro, y un plazo del art. 16 LCS perdido acaba en derrama.
assert.equal(uno(base({ confianza: 0.8 })).umbral_aplicado, 0.9);
assert.equal(uno(base({ confianza: 0.8 })).accion, 'revision_administrador');
// Con plazo activo basta 0.7, y el caso sí se resuelve solo.
r = uno(base({ confianza: 0.8, plazos_activos: ['siniestro_lcs16'] }));
assert.equal(r.umbral_aplicado, 0.7);
assert.equal(r.accion, 'parte_proveedor');
assert.equal(r.decidido_por, 'sistema');

// --- 3. regla dura de dependencia estatutaria -----------------------------------------
// El caso de i01: confianza perfecta, sin rival, y la cita sale de la escritura de la finca.
r = uno(base({ fundamento: ESTATUTOS, plazos_activos: ['siniestro_lcs16'] }));
assert.equal(r.accion, 'revision_administrador', 'la dependencia estatutaria para el automatismo');
assert.equal(r.decidido_por, 'estatutos', 'la vía tiene que decir QUÉ paró el automatismo');
// La clasificación del modelo se respeta: la regla decide quién firma, no qué es el caso.
assert.equal(r.imputacion, 'comun', 'la regla estatutaria no puede reescribir la imputación');

// Mezcla de ley y estatutos: basta una cita estatutaria para que decida un humano.
r = uno(base({ fundamento: [...LEY, ...ESTATUTOS], plazos_activos: ['siniestro_lcs16'] }));
assert.equal(r.accion, 'revision_administrador');
assert.equal(r.imputacion, 'comun');

// Solo ley: el sistema puede cerrar.
r = uno(base({ plazos_activos: ['siniestro_lcs16'] }));
assert.equal(r.imputacion, 'comun');
assert.equal(r.decidido_por, 'sistema');

// Si el modelo dudaba Y hay cláusula, manda su propia duda: la vía informa de lo primero que
// falló, no de lo último que se comprobó.
assert.equal(
  uno(base({ fundamento: ESTATUTOS, imputacion_rival: 'privativo' })).decidido_por,
  'umbral',
);

// --- 4. fallar cerrado ----------------------------------------------------------------
// Sin las env vars, Number(undefined) es NaN y NaN >= NaN es false: revisión humana, nunca
// una incidencia colada sin control. Pasó de verdad: el contenedor no tenía las variables.
r = uno(base({ plazos_activos: ['siniestro_lcs16'] }), {});
assert.ok(Number.isNaN(r.umbral_aplicado));
assert.equal(r.accion, 'revision_administrador');
assert.equal(r.decidido_por, 'umbral');

// Confianza no numérica o ausente cuenta como 0, no como "adelante".
assert.equal(uno(base({ confianza: 'muy alta' })).confianza, 0);
assert.equal(uno(base({ confianza: undefined })).accion, 'revision_administrador');

// El modelo puede devolver el JSON como string dentro de output.
assert.equal(uno(JSON.stringify(base({}))).imputacion, 'comun');

// --- 5. el agente no devuelve nada -----------------------------------------------------
// Pasó con i21: 'Cannot read properties of undefined (reading confianza)'. El correo ya estaba
// marcado como leído, así que el caso no llegó a ninguna tabla y solo se supo por la cobertura
// del eval. Ahora entra etiquetado, no desaparece.
for (const vacio of [undefined, null, 'no soy json', '']) {
  const r = uno(vacio);
  assert.equal(r.imputacion, 'sin_clasificar', `salida ${JSON.stringify(vacio)} sin etiquetar`);
  assert.equal(r.confianza, 0);
  assert.equal(r.accion, 'revision_administrador');
}
console.log('OK: 24 comprobaciones del nodo "Parsear y Aplicar Controles"');
