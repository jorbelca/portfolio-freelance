import pg from 'pg';
export const pool = process.env.DATABASE_URL
  ? new pg.Pool({connectionString: process.env.DATABASE_URL, max: 4, connectionTimeoutMillis: 10000})
  : null;
export async function transaction(callback) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally { client.release(); }
}
