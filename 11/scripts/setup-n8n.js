import {spawn} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const cwd=fileURLToPath(new URL('..',import.meta.url));
async function docker(args,input) {
  await new Promise((resolve,reject)=>{
    const child=spawn('docker',['compose',...args],{cwd,stdio:['pipe','ignore','inherit']});
    child.once('error',reject); child.once('close',code=>code===0?resolve():reject(new Error(`Docker terminó con código ${code}`)));
    child.stdin.on('error',()=>{}); child.stdin.end(input);
  });
}
if (!process.env.N8N_TOKEN || process.env.N8N_TOKEN.length<32) throw new Error('Configura N8N_TOKEN con al menos 32 caracteres en .env');
const workflows=await Promise.all(['01-contrato.json','02-extracciones.json'].map(async file=>JSON.parse(await readFile(new URL(`../workflows/${file}`,import.meta.url),'utf8'))));
for (const workflow of workflows) for (const node of workflow.nodes) if (node.type==='n8n-nodes-base.httpRequest') node.parameters.url=node.parameters.url.replace(':3210/',`:${Number(process.env.PORT || 3210)}/`);
const credentials=[{id:'empleoPanelHeader',name:'Empleo · puente local',type:'httpHeaderAuth',data:{name:'Authorization',value:`Bearer ${process.env.N8N_TOKEN}`}}];
await docker(['up','-d']);
try {
  await docker(['exec','-T','n8n','sh','-c','umask 077; cat > /tmp/empleo-credential.json'],JSON.stringify(credentials));
  await docker(['exec','-T','n8n','n8n','import:credentials','--input=/tmp/empleo-credential.json']);
  for (const workflow of workflows) {
    await docker(['exec','-T','n8n','sh','-c','umask 077; cat > /tmp/empleo-workflow.json'],JSON.stringify(workflow));
    await docker(['exec','-T','n8n','n8n','import:workflow','--input=/tmp/empleo-workflow.json']);
    await docker(['exec','-T','n8n','n8n','publish:workflow',`--id=${workflow.id}`]);
  }
} finally {
  await docker(['exec','-T','n8n','rm','-f','/tmp/empleo-credential.json','/tmp/empleo-workflow.json']);
}
await docker(['restart','n8n']);
console.log('Workflow publicado y credencial instalada. El panel controla la admisión de nuevas ejecuciones.');
