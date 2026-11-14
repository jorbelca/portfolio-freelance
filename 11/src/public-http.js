import {lookup} from 'node:dns/promises';
import {isIP} from 'node:net';
import {cleanUrl} from './domain.js';

export function isPublicAddress(address) {
  const kind=isIP(address);
  if (kind===6) return /^[23][0-9a-f]{3}:/i.test(address) && !/^2001:(?:0:|db8:|10:|20:)/i.test(address) && !/^2002:/i.test(address);
  if (kind!==4) return false;
  const [a,b]=address.split('.').map(Number);
  return !([0,10,127].includes(a) || a>=224 || (a===100 && b>=64 && b<=127) || (a===169 && b===254) || (a===172 && b>=16 && b<=31) || (a===192 && [0,2,168].includes(b)) || (a===198 && [18,19,51].includes(b)) || (a===203 && b===0));
}
export async function verifyPublicBrowserUrl(value) {
  const target=cleanUrl(value),url=new URL(target);
  if(url.protocol!=='https:' || (url.port && url.port!=='443')) throw new Error('El navegador solo puede abrir páginas públicas HTTPS en el puerto 443.');
  const addresses=isIP(url.hostname)?[{address:url.hostname}]:await lookup(url.hostname,{all:true});
  if(!addresses.length || addresses.some(item=>!isPublicAddress(item.address))) throw new Error('El enlace del navegador no resuelve exclusivamente a direcciones públicas.');
  return target;
}
