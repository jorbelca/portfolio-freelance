import {loadEnvFile} from 'node:process';
import {fileURLToPath} from 'node:url';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {apiClient,createMcpServer} from './mcp.js';
try {loadEnvFile(fileURLToPath(new URL('../.env',import.meta.url)));} catch(error) {if(error.code!=='ENOENT') throw error;}
if (!process.env.MCP_TOKEN) throw new Error('Configura MCP_TOKEN en 11/.env y reinicia el servicio web.');
const server=createMcpServer({request:apiClient({baseUrl:process.env.EMPLEO_API_URL || `http://127.0.0.1:${process.env.PORT || 3210}`,token:process.env.MCP_TOKEN}),readOnly:process.env.EMPLEO_MCP_READ_ONLY==='1'});
await server.connect(new StdioServerTransport());
