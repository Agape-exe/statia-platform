// Verifica configuración de build con valores sintéticos; no prueba servicios remotos.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'

const valid = {
  VITE_SUPABASE_URL: 'https://supabase.example.org',
  VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_ejemplo_de_configuracion',
  VITE_API_URL: 'https://api.example.org',
}
const check = (overrides) => spawnSync(process.execPath, ['scripts/check-production-env.mjs'], {
  env: { ...process.env, ...valid, ...overrides }, encoding: 'utf8',
})

test('acepta orígenes HTTPS y clave publicable sin mostrar sus valores', () => {
  const result = check({})
  assert.equal(result.status, 0)
  assert.ok(!result.stdout.includes(valid.VITE_SUPABASE_PUBLISHABLE_KEY))
})

test('impide publicar con API local, valores ausentes, claves privadas o URLs con credenciales', () => {
  for (const overrides of [
    { VITE_API_URL: 'http://localhost:8000' },
    { VITE_API_URL: '' },
    { VITE_SUPABASE_URL: 'https://user:pass@example.org' },
    { VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_secret_valor_sintetico' },
    { VITE_GEMINI_API_KEY: 'valor_sintetico' },
  ]) assert.notEqual(check(overrides).status, 0)
})
