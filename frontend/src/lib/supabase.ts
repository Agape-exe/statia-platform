import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL?.trim()
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim()
export const supabase =
  url && /^https?:\/\/[^\s/]+/.test(url) && key
    ? createClient(url, key, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      })
    : null
export function getSupabase() {
  if (!supabase)
    throw new Error('Configura frontend/.env.local para conectar Supabase.')
  return supabase
}
