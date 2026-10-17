// Ejecutar en cua_repl con la pestaña local como argumento; no inicia ejecuciones.
// Requiere un recorrido terminado de 12 acciones y un fallo temporal en la acción 5.
export async function verificarUI(tab) {
  const page = tab.playwright;
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  const text = id => page.locator('#' + id).innerText();
  await page.getByRole('button', {name: /Ejecución 12/}).click();
  assert(await text('state') === 'Completada', 'La ejecución debe estar completada');
  assert(await text('confirmed') === '12', 'Deben verse 12 acciones confirmadas');
  assert(await text('attempts') === '13', 'Debe verse el reintento adicional');

  await page.getByLabel('Buscar acciones').fill('proxy-b');
  assert(await text('visibleCount') === '5 de 12 acciones', 'El filtro de proxy debe mostrar cinco acciones');
  await page.getByLabel('Filtrar por estado').selectOption({label: 'Fallidas'});
  assert(await page.getByText('No hay acciones con este filtro', {exact: true}).isVisible(), 'Debe mostrarse el estado vacío');
  await page.getByLabel('Buscar acciones').fill('');
  await page.getByLabel('Filtrar por estado').selectOption({label: 'Todos los estados'});

  await page.getByRole('button', {name: 'Ver acción 5', exact: true}).click();
  assert(await page.getByText('Intento 1 · HTTP 503', {exact: true}).isVisible(), 'Debe verse el intento fallido');
  assert(await page.getByText('Intento 2 · HTTP 201', {exact: true}).isVisible(), 'Debe verse la confirmación posterior');
  assert(await text('detailProxy') === 'proxy-a', 'El reintento debe conservar la ruta');
  await page.getByRole('button', {name: 'Cerrar', exact: true}).press('Escape');
  const focus = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'));
  assert(focus === 'Ver acción 5', 'Escape debe devolver el foco a la acción');

  await page.getByRole('button', {name: /Actividad/}).click();
  await page.getByLabel('Filtrar eventos por acción').fill('5');
  const filteredEvents = await page.locator('#events .event').allTextContents({});
  assert(filteredEvents.length >= 3 && filteredEvents.every(event => event.includes('#05')), 'El registro debe filtrar la acción y conservar sus reintentos');
  await page.getByLabel('Filtrar eventos por acción').fill('');
  await page.getByRole('button', {name: /Rutas 3/}).click();
  const routes = await page.locator('#routes tr').allTextContents({});
  assert(routes.length === 3 && routes[0].includes('5 / 5') && routes[1].includes('5 / 5') && routes[2].includes('2 / 2'), 'Debe verse el reparto 5/5/2');

  await page.getByRole('button', {name: /Ejecución 12/}).click();
  await page.getByText('Exportar', {exact: true}).click();
  assert(await page.getByRole('link', {name: 'Acciones CSV'}).getAttribute('href', {}) === '/api/informe.csv', 'CSV debe apuntar al informe real');
  assert(await page.getByRole('link', {name: 'Informe JSON'}).getAttribute('href', {}) === '/api/informe.json', 'JSON debe apuntar al informe real');
  assert(await page.getByRole('link', {name: 'Acciones CSV'}).getAttribute('download', {}) === 'demo9.csv', 'CSV debe descargarse sin navegar fuera del panel');
  assert(await page.getByRole('link', {name: 'Informe JSON'}).getAttribute('download', {}) === 'demo9.json', 'JSON debe descargarse sin navegar fuera del panel');
  await page.getByText('Exportar', {exact: true}).click();
  assert(await text('audit') === 'Registros conciliados', 'El informe debe estar conciliado');
  return 'UI verificada: filtros, detalle, teclado, actividad, rutas y exportaciones';
}
