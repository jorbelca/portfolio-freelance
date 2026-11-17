import {offerState} from './offer-state.js';

export function companyStats(offers) {
  const groups=new Map();
  for (const offer of offers) {
    const name=offer.company.normalize('NFKC').trim().replace(/\s+/g,' ');
    const key=name.toLocaleLowerCase('es');
    if (!groups.has(key)) groups.set(key,{name,total:0,inscrita:0,rechazada:0,pendiente:0});
    const company=groups.get(key);
    company.total++;
    company[offerState(offer)]++;
  }
  return [...groups.values()].sort((a,b)=>b.total-a.total || a.name.localeCompare(b.name,'es'));
}

export function companyColor(company,min,max) {
  const intensity=max>min?(company.rechazada-min)/(max-min):0;
  return `rgb(180 35 35 / ${Math.max(0,Math.min(1,intensity))*.65})`;
}

export function renderCompanyHeatmap(offers) {
  const grid=document.querySelector('#company-heatmap');
  const search=document.querySelector('#company-search');
  const detail=document.querySelector('#company-summary');
  grid.replaceChildren();
  const stats=companyStats(offers);
  const rejections=stats.map(company=>company.rechazada);
  const min=rejections.length?Math.min(...rejections):0;
  const max=rejections.length?Math.max(...rejections):0;
  document.querySelector('#company-scale-min').textContent=`Mínimo: ${min} rechazos`;
  document.querySelector('#company-scale-max').textContent=`Máximo: ${max} rechazos`;
  const normalize=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es');
  const summary=company=>`${company.name}: ${company.total} ofertas · ${company.inscrita} inscritas · ${company.rechazada} rechazadas · ${company.pendiente} pendientes`;
  for (const company of stats) {
    const cell=document.createElement('button');
    cell.type='button';
    cell.className='company-cell';
    cell.textContent=company.name;
    cell.title=summary(company);
    cell.setAttribute('aria-label',summary(company));
    cell.dataset.company=normalize(company.name);
    cell.style.backgroundColor=companyColor(company,min,max);
    const show=()=>{detail.textContent=summary(company);};
    cell.onmouseenter=show;
    cell.onfocus=show;
    cell.onclick=show;
    grid.append(cell);
  }
  const highlight=()=>{
    const query=normalize(search.value.trim());
    let matches=0;
    for (const cell of grid.children) {
      const match=Boolean(query) && cell.dataset.company.includes(query);
      cell.classList.toggle('company-match',match);
      cell.classList.toggle('company-dimmed',Boolean(query) && !match);
      if (match) matches++;
    }
    document.querySelector('#company-count').textContent=`${stats.length} empresas${query?` · ${matches} coincidencias`:''}`;
  };
  search.oninput=highlight;
  detail.textContent=stats.length?'Selecciona una empresa para ver sus cifras.':'No hay empresas con ofertas registradas.';
  highlight();
}
