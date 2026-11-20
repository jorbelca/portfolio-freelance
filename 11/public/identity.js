export function cleanUrl(value) {
  if (!value) return null;
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Enlace público inválido');
  url.hash = '';
  for (const key of [...url.searchParams.keys()]) {
    if (/^(utm_.*|tmp_ctoken|hash|requestParams|token|session|confirmation)$/i.test(key)) url.searchParams.delete(key);
  }
  return url.href;
}

// El tenant forma parte del ID: dos empresas pueden reutilizar un código ATS.
export function publicationIdentity(value) {
  const cleaned=cleanUrl(value);
  if (!cleaned) return null;
  const url=new URL(cleaned), host=url.hostname.toLowerCase().replace(/^www\./,''), path=url.pathname;
  let match;
  if (host==='infojobs.net' && (match=path.match(/\/(of-i[0-9a-f]+)(?:\/|$)/i))) return `infojobs:${match[1].toLowerCase()}`;
  if ((host==='linkedin.com' || host.endsWith('.linkedin.com')) && (match=path.match(/\/jobs\/view\/(?:[^/]*-)?(\d+)\/?$/))) return `linkedin:${match[1]}`;
  if (host==='apply.workable.com' && (match=path.match(/^\/([^/]+)\/j\/([a-z0-9]+)(?:\/|$)/i))) return `workable:${match[1].toLowerCase()}:${match[2].toUpperCase()}`;
  if (['boards.greenhouse.io','job-boards.greenhouse.io'].includes(host) && (match=path.match(/^\/([^/]+)\/jobs\/(\d+)(?:\/|$)/))) return `greenhouse:${match[1].toLowerCase()}:${match[2]}`;
  if (host==='jobs.lever.co' && (match=path.match(/^\/([^/]+)\/([0-9a-f-]{36})(?:\/|$)/i))) return `lever:${match[1].toLowerCase()}:${match[2].toLowerCase()}`;
  if(host==='api.smartrecruiters.com' && (match=path.match(/^\/v1\/companies\/([^/]+)\/postings\/(\d+)(?:\/|$)/))) return `smartrecruiters:${match[1].toLowerCase()}:${match[2]}`;
  if (host==='jobs.smartrecruiters.com' && (match=path.match(/^\/([^/]+)\/(\d+)(?:-|\/|$)/))) return `smartrecruiters:${match[1].toLowerCase()}:${match[2]}`;
  if (host==='emploive.com' && (match=path.match(/^(?:\/home)?\/jobs\/(\d+)(?:\/|$)/))) return `emploive:${match[1]}`;
  if (host==='europa.eu' && (match=path.match(/^\/eures\/portal\/jv-se\/jv-details\/([A-Za-z0-9_-]+=*)\/?$/))) return `eures:${match[1]}`;
  if (host==='careers.indragroup.com' && (match=path.match(/^\/(?:[a-z0-9-]+\/)?job\/[^/]+\/(\d+)\/?$/i))) return `indra:${match[1]}`;
  if (/^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$/.test(host) && (match=path.match(/^\/(?:[^/]+\/)?[^/]+\/job\/(?:[^/]+\/)*[^/]*_((?:jr|r)-?\d+(?:-\d+)*)\/?$/i))) return `workday:${host}:${match[1].toLowerCase()}`;
  return null;
}
export function samePublication(left,right) {
  if (cleanUrl(left)===cleanUrl(right)) return true;
  const identity=publicationIdentity(left);
  return Boolean(identity && identity===publicationIdentity(right));
}
