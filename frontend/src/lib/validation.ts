import type { ProjectInput } from '../types/project'
const configuredMinimum = Number(
  import.meta.env.VITE_AUTH_MIN_PASSWORD_LENGTH || 8,
)
export const minimumPasswordLength =
  Number.isInteger(configuredMinimum) && configuredMinimum >= 6
    ? configuredMinimum
    : 8
export function validateAuth(
  email: string,
  password: string,
  confirmation?: string,
) {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
    return 'Ingresa un correo electrónico válido.'
  if (!password) return 'Ingresa tu contraseña.'
  if (confirmation !== undefined) {
    if (password.length < minimumPasswordLength)
      return `La contraseña debe tener al menos ${minimumPasswordLength} caracteres.`
    if (password !== confirmation) return 'Las contraseñas no coinciden.'
  }
  return null
}
export function validateProject(input: ProjectInput) {
  if (!input.name.trim() || input.name.trim().length > 120)
    return 'El nombre debe tener entre 1 y 120 caracteres.'
  if (!['thesis', 'general'].includes(input.project_type))
    return 'Selecciona el uso del proyecto.'
  if (input.description.length > 2000)
    return 'La descripción no puede superar los 2000 caracteres.'
  return null
}
