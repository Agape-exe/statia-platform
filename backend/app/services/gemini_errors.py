"""Diagnósticos permitidos: nunca registrar el cuerpo de error del proveedor."""
import logging

from fastapi import HTTPException

MESSAGES = {
    'not_configured': 'Falta habilitar Gemini: un administrador debe configurar GEMINI_API_KEY en el backend.',
    'schema': 'Gemini rechazó el esquema de respuesta estructurada. Revisa el contrato enviado al proveedor.',
    'model': 'El modelo Gemini configurado no existe, no está habilitado o no admite esta operación. Revisa GEMINI_MODEL.',
    'credentials': 'Gemini rechazó la credencial del backend. Un administrador debe revisar GEMINI_API_KEY.',
    'permissions': 'Gemini denegó los permisos del proveedor. Revisa acceso, región y configuración de la cuenta.',
    'quota': 'Gemini no pudo completar la consulta por cuota o límite de solicitudes. Inténtalo más tarde.',
    'unavailable': 'El servicio Gemini está temporalmente no disponible. Puedes reintentar más tarde.',
    'timeout': 'Gemini tardó demasiado. Tu mensaje se conservó; puedes reintentar o revisar GEMINI_TIMEOUT_SECONDS.',
    'connectivity': 'No se pudo conectar con Gemini. Tu mensaje se conservó; comprueba la conectividad del backend.',
    'invalid_request': 'Gemini rechazó los parámetros de la solicitud. Revisa la configuración del proveedor.',
    'invalid_response': 'Gemini devolvió una respuesta JSON inválida o incompleta. No se guardó ninguna propuesta; puedes reintentar.',
    'sdk_contract': 'El SDK de Gemini no pudo procesar el contrato configurado. Revisa la versión del proveedor.',
    'provider': 'Gemini no pudo completar la consulta por un error interno del proveedor. Puedes reintentar.',
}


def diagnostic(category, http_status=502, upstream_status=None):
    # Solo valores internos y un código HTTP. No exc, message, details, prompt ni tokens.
    logging.getLogger(__name__).warning('Gemini error category=%s upstream_status=%s', category, upstream_status)
    message = MESSAGES[category]
    if upstream_status is not None:
        message += f' (Proveedor HTTP {upstream_status}; diagnóstico: gemini_{category}).'
    headers = {'X-Statia-Error': f'gemini_{category}'}
    if upstream_status is not None:
        headers['X-Gemini-Status'] = str(upstream_status)
    return HTTPException(http_status, message, headers=headers)


def api_diagnostic(error):
    status = int(error.code or 500)
    # Leer el mensaje solo para clasificar; nunca devolverlo ni registrarlo.
    message = str(error.message or '').lower()
    if status == 429:
        return diagnostic('quota', 429, status)
    if status in (408, 504):
        return diagnostic('timeout', 504, status)
    if status == 503:
        return diagnostic('unavailable', 503, status)
    if status == 401 or (status == 400 and any(term in message for term in ('api_key_invalid', 'api key not valid', 'api key expired'))):
        return diagnostic('credentials', upstream_status=status)
    if status == 403:
        return diagnostic('permissions', upstream_status=status)
    if status == 404 or (status == 400 and 'model' in message and any(term in message for term in ('not supported', 'not found', 'not enabled', 'does not support'))):
        return diagnostic('model', upstream_status=status)
    if status == 400:
        category = 'schema' if any(term in message for term in ('response_schema', 'response_json_schema', 'json schema', 'too many states', 'additional_properties')) else 'invalid_request'
        return diagnostic(category, upstream_status=status)
    return diagnostic('provider', upstream_status=status)
