import {readFile, readdir} from 'node:fs/promises';
import {pool} from './db.js';
if (!pool) throw new Error('Configura DATABASE_URL en .env antes de migrar');
try {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('SELECT pg_advisory_xact_lock(110011)');
    await client.query('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())');
    const files = (await readdir(new URL('../sql/', import.meta.url))).filter(name => /^\d+\.sql$/.test(name)).sort();
    for (const name of files) {
      if ((await client.query('SELECT 1 FROM schema_migrations WHERE name=$1', [name])).rowCount) continue;
      const sql = await readFile(new URL(`../sql/${name}`, import.meta.url), 'utf8');
      await client.query(sql.replace(/^BEGIN;\s*/i, '').replace(/COMMIT;\s*$/i, ''));
      if (name === '001.sql') {
        const defaults = JSON.parse(await readFile(new URL('../defaults.json', import.meta.url), 'utf8'));
        await client.query('INSERT INTO settings(id,value) VALUES(1,$1) ON CONFLICT(id) DO NOTHING', [defaults]);
      }
      await client.query('INSERT INTO schema_migrations(name) VALUES($1)', [name]);
    }
    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally { client.release(); }
  console.log('Migración completada');
} finally { await pool.end(); }
