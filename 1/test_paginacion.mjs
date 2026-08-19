// Comprueba el nodo "Añade Metadata {documento,pagina}" del workflow de RAG. Extrae el
// código real del JSON (no una copia: si el nodo cambia en la UI y se reexporta, este test
// lo ve) y lo ejecuta con un $input y un $ falsos.
//
//     node test_paginacion.mjs
//
// El defecto original era `pagina` como constante literal 1. El arreglo depende de dos
// cosas que un test de "un PDF, una página" no puede distinguir de una implementación rota:
//   1. que `pagina` sea la posición real en el array de páginas (no el índice del item de
//      salida, que compactaría la numeración si se saltan páginas en blanco);
//   2. que `documento` se resuelva con $('Separar Archivos...').itemMatching(i) y no con
//      la forma más obvia .item — en n8n real, dentro de un nodo Code en modo "Run Once for
//      All Items" (el modo por defecto), $('Nodo').item e $input.item ignoran en qué vuelta
//      del bucle estás y devuelven SIEMPRE el item 0 del nodo actual. Con un solo PDF eso
//      pasa desapercibido; con el lote de 2+ PDF que admite el formulario (multipleFiles),
//      .item pegaría el nombre del primer documento a las páginas de todos los demás.
// El caso de lote de 2 PDFs de más abajo es el que distingue ambas implementaciones.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const doc = JSON.parse(readFileSync(new URL('./Tarea 2 - RAG Citas.json', import.meta.url), 'utf8'));
const nodo = doc.nodes.find((n) => n.name === 'Añade Metadata {documento,pagina}');
assert.ok(nodo, 'no existe el nodo "Añade Metadata {documento,pagina}" en el workflow');
assert.equal(nodo.type, 'n8n-nodes-base.code', 'se esperaba que el nodo fuera n8n-nodes-base.code (¿sigue siendo un Set?)');

const fn = new Function('$input', '$', nodo.parameters.jsCode);

// Ejecuta el nodo con una lista de "PDFs" ya extraídos: cada uno { documento, text }, donde
// text es lo que dejaría "Extraer Texto PDF" en json.text (array de páginas, o string si
// joinPages estuviera activo).
function ejecutar(pdfs) {
  const items = pdfs.map((pdf) => ({ json: { text: pdf.text } }));
  const documentos = pdfs.map((pdf) => pdf.documento);

  const $input = { all: () => items };

  // $ falso: solo entiende $('Separar Archivos (1 item por PDF)'). Deliberadamente NO
  // expone `.item` (a diferencia del `.itemMatching(i)` real) para que, si el código
  // vuelve a usar la forma `.item`, el test reviente con un TypeError claro en vez de
  // colar en falso devolviendo el mismo documento para todo el lote por casualidad.
  const $ = (nombre) => {
    assert.equal(nombre, 'Separar Archivos (1 item por PDF)');
    return {
      itemMatching: (i) => ({ json: { documento: documentos[i] } }),
    };
  };

  return fn($input, $);
}

// --- PDF de 3 páginas: pagina 1,2,3 y texto correcto en cada una -----------------------
let out = ejecutar([{ documento: 'contrato-alquiler', text: ['pág uno', 'pág dos', 'pág tres'] }]);
assert.equal(out.length, 3);
assert.deepEqual(out.map((it) => it.json.pagina), [1, 2, 3]);
assert.deepEqual(out.map((it) => it.json.texto), ['pág uno', 'pág dos', 'pág tres']);
assert.deepEqual(out.map((it) => it.pairedItem), [{ item: 0 }, { item: 0 }, { item: 0 }]);

// --- documento se propaga igual a todos los items de un mismo PDF ----------------------
assert.ok(out.every((it) => it.json.documento === 'contrato-alquiler'));

// --- PDF de 1 sola página ----------------------------------------------------------------
out = ejecutar([{ documento: 'escritura', text: ['única página'] }]);
assert.equal(out.length, 1);
assert.equal(out[0].json.pagina, 1);
assert.equal(out[0].json.documento, 'escritura');

// --- joinPages reactivado en la UI: text llega como string, no como array --------------
// Debe tratarse como una única página, no iterar carácter a carácter.
out = ejecutar([{ documento: 'nota', text: 'todo el texto junto, sin separar por página' }]);
assert.equal(out.length, 1, 'un string debe producir 1 item, no uno por carácter');
assert.equal(out[0].json.pagina, 1);
assert.equal(out[0].json.texto, 'todo el texto junto, sin separar por página');

// --- página en blanco en medio: se salta, y la numeración NO se recompacta -------------
// Si se recompactara, la página real 3 se citaría como "página 2": la misma clase de cita
// falsa que este cambio pretende eliminar, solo que desplazada en vez de fija en 1.
out = ejecutar([{ documento: 'contrato-mixto', text: ['página uno', '   ', 'página tres'] }]);
assert.equal(out.length, 2);
assert.deepEqual(out.map((it) => it.json.pagina), [1, 3]);
assert.deepEqual(out.map((it) => it.json.texto), ['página uno', 'página tres']);

// --- PDF enteramente en blanco: cero items ------------------------------------------------
out = ejecutar([{ documento: 'vacio', text: ['', '   \n\t  '] }]);
assert.equal(out.length, 0);

// --- lote de 2 PDFs a la vez (el formulario admite multipleFiles): cada página debe llevar
// el documento de SU PROPIO PDF, no el del primero del lote. Este es el caso que distingue
// itemMatching(i) de .item — con .item, en n8n real, todas las páginas de pdf-b llevarían
// erróneamente el documento pdf-a.
out = ejecutar([
  { documento: 'pdf-a', text: ['a1', 'a2'] },
  { documento: 'pdf-b', text: ['b1'] },
]);
assert.equal(out.length, 3);
assert.deepEqual(
  out.map((it) => [it.json.documento, it.json.pagina, it.json.texto]),
  [
    ['pdf-a', 1, 'a1'],
    ['pdf-a', 2, 'a2'],
    ['pdf-b', 1, 'b1'],
  ],
);
assert.deepEqual(out.map((it) => it.pairedItem), [{ item: 0 }, { item: 0 }, { item: 1 }]);

console.log('OK: nodo "Añade Metadata {documento,pagina}" — fan-out por página real, joinPages defensivo, páginas en blanco sin recompactar, lote multi-PDF con documento correcto por item');
