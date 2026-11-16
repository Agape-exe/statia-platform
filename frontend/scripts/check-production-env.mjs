import { loadEnv } from 'vite'

// Solo nombres/categorías en errores: nunca imprimir valores de configuración.
const env = { ...loadEnv('production', process.cwd(), 'VITE_'), ...process.env }
for (const name of ['VITE_SUPABASE_URL', 'VITE_API_URL']) {
  let valid = false
  try {
    const url = new URL(env[name])
    valid = url.protocol === 'https:' && url.origin === env[name] &&
      !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  } catch { /* La configuración ausente también impide publicar. */ }
  if (!valid) throw new Error(`${name} debe ser un origen HTTPS público, sin barra final.`)
}
const key = env.VITE_SUPABASE_PUBLISHABLE_KEY || ''
let publicKey = key.startsWith('sb_publishable_')
try {
  publicKey ||= JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role === 'anon'
} catch { /* Las claves nuevas no son JWT. */ }
if (!publicKey) throw new Error('VITE_SUPABASE_PUBLISHABLE_KEY debe ser publicable o anon.')
for (const name of Object.keys(env).filter((name) => name.startsWith('VITE_'))) {
  if (/secret|service_role|gemini|private|token|password/i.test(name) && name !== 'VITE_AUTH_MIN_PASSWORD_LENGTH') {
    throw new Error(`Retira la variable privada ${name} del frontend.`)
  }
}
console.log('Configuración pública de producción validada (sin mostrar valores).')
