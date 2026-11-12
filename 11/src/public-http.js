import https from 'node:https';
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
export async function publicGet(value,{maxBytes=3000000,timeoutMs=20000,redirects=4}={}) {
  let target=cleanUrl(value);
  for (let hop=0;hop<=redirects;hop++) {
    const url=new URL(target);
    if (url.protocol!=='https:' || (url.port && url.port!=='443')) throw new Error('Solo se permiten fuentes HTTPS públicas en el puerto 443.');
    const addresses=await lookup(url.hostname,{all:true});
    if (!addresses.length || addresses.some(item=>!isPublicAddress(item.address))) throw new Error('La fuente resuelve a una dirección no pública.');
    const address=addresses[0];
    const response=await new Promise((resolve,reject)=>{
      const request=https.get(url,{headers:{'User-Agent':'EmpleoResearch/1.0','Accept':'application/json,text/html'},lookup:(_host,options,callback)=>options.all?callback(null,[address]):callback(null,address.address,address.family)},res=>{
        let size=0;const chunks=[];
        res.on('data',chunk=>{size+=chunk.length;if(size>maxBytes) res.destroy(new Error('Documento demasiado grande'));else chunks.push(chunk);});
        res.once('error',reject);
        res.once('end',()=>resolve({status:res.statusCode,headers:res.headers,text:Buffer.concat(chunks).toString('utf8')}));
      });
      const timer=setTimeout(()=>request.destroy(new Error('La fuente agotó el tiempo de espera')),timeoutMs);
      request.once('error',reject);request.once('close',()=>clearTimeout(timer));
    });
    if ([301,302,303,307,308].includes(response.status)) {
      if (!response.headers.location || hop===redirects) throw new Error('Redirección incompleta o excesiva');
      target=cleanUrl(new URL(response.headers.location,url).href);
      continue;
    }
    return {...response,url:target,checked_at:new Date().toISOString()};
  }
}
