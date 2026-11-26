import {cleanUrl,publicationIdentity} from './identity.js';
import {normalizeCompanyName} from './company-heatmap.js';
import {offerState} from './offer-state.js';

const madridDate=now=>now.toLocaleDateString('sv-SE',{timeZone:'Europe/Madrid'});

export function matchesOfferUrl(offer,query) {
  const term=query.trim();
  if (!term) return true;
  let normalized;
  try { normalized=cleanUrl(term); } catch {}
  const identity=publicationIdentity(normalized);
  const fragment=term.toLowerCase();
  return [offer.url,...(offer.publications || []).map(item=>item.url)].filter(Boolean).some(url=>{
    if (identity) return publicationIdentity(url)===identity;
    return url.toLowerCase().includes(fragment) || Boolean(normalized && cleanUrl(url)===normalized);
  });
}

export function filterPostulations(offers,{company,url,state,days},now=new Date()) {
  const companyTerm=normalizeCompanyName(company.trim());
  const urlTerm=url.trim();
  const hasSearch=Boolean(companyTerm || urlTerm);
  const today=madridDate(now);
  let firstDay;
  if (days) {
    const start=new Date(`${today}T00:00:00Z`);
    start.setUTCDate(start.getUTCDate()-days+1);
    firstDay=start.toISOString().slice(0,10);
  }
  return offers.filter(offer=>{
    const submitted=offer.submitted_at?.slice(0,10);
    const matchesCompany=Boolean(companyTerm) && normalizeCompanyName(offer.company).includes(companyTerm);
    const matchesUrl=Boolean(urlTerm) && matchesOfferUrl(offer,urlTerm);
    return (!state || offerState(offer)===state)
      && (!hasSearch || matchesCompany || matchesUrl)
      && (!firstDay || (submitted && submitted>=firstDay && submitted<=today));
  });
}

export function applicationsToday(offers,now=new Date()) {
  const today=madridDate(now);
  return offers.filter(offer=>offer.application_state && offer.application_state!=='sin_candidatura' && offer.submitted_at?.slice(0,10)===today).length;
}

export function rejectionsToday(offers,now=new Date()) {
  const today=madridDate(now);
  return offers.filter(offer=>(offer.application_state || offer.review_state==='descartada')
    && offerState(offer)==='rechazada'
    && offer.state_changed_at
    && madridDate(new Date(offer.state_changed_at))===today).length;
}
