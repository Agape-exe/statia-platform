export function errorMessage(error: unknown): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : ''
  const messages: Record<string, string> = {
    invalid_credentials: 'El correo o la contraseña son incorrectos.',
    email_not_confirmed: 'Confirma tu correo electrónico antes de ingresar.',
    user_already_exists: 'Ya existe una cuenta con este correo.',
    weak_password:
      'La contraseña no cumple los requisitos de seguridad configurados en Supabase.',
    over_email_send_rate_limit:
      'Se enviaron demasiados correos. Espera unos minutos e inténtalo de nuevo.',
    over_request_rate_limit: 'Demasiados intentos. Espera unos minutos.',
    signup_disabled: 'El registro está deshabilitado en Supabase.',
    '42P01': 'No se encontró la tabla de proyectos. Ejecuta la migración SQL.',
    '42501': 'No tienes permiso para realizar esta operación.',
  }
  if (messages[code]) return messages[code]
  return 'No se pudo completar la operación. Comprueba tu conexión y la configuración de Supabase e inténtalo de nuevo.'
}
