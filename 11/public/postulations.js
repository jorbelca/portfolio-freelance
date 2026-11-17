export function matchesOfferUrl(offer,query) {
  const term=query.trim().toLowerCase();
  return !term || [offer.url,...(offer.publications || []).map(item=>item.url)].some(url=>url?.toLowerCase().includes(term));
}

export function applicationsToday(offers,now=new Date()) {
  const today=now.toLocaleDateString('sv-SE',{timeZone:'Europe/Madrid'});
  return offers.filter(offer=>offer.application_state && offer.application_state!=='sin_candidatura' && offer.submitted_at?.slice(0,10)===today).length;
}
