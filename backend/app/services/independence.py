"""Procedencia metodológica conservadora: filas distintas no prueban independencia."""
import re

from app.services.conversation_text import action_of, normalize


def user_independence_evidence(messages, previous=None):
    evidence = list(previous or [])
    for message in messages:
        if message['role'] != 'user' or action_of(message) != 'message':
            continue
        text = normalize(message['content'])
        # Se exige el conjunto, no solo un identificador distinto por fila.
        random = re.search(r'muestreo aleatorio (?:simple|individual)|seleccion aleatoria individual', text)
        once = re.search(r'una (?:sola |unica )?(?:medicion|observacion) por (?:individuo|participante|sujeto)', text)
        unlinked = re.search(r'sin (?:pareamiento|emparejamiento).*sin (?:conglomerados|agrupamiento)|sin (?:pareamiento|emparejamiento) ni (?:conglomerados|agrupamiento)', text)
        denied = re.search(r'no (?:hubo |hay |fue |se uso |utilizamos )?(?:un )?muestreo aleatorio|no sabemos|desconocemos', text)
        contradicted = re.search(r'(?:hay|hubo|tenemos|existen|son) (?:mediciones repetidas|datos pareados|conglomerados)', text)
        if denied or contradicted:
            evidence = []
        if random and once and unlinked and not denied and not contradicted:
            evidence = ['El usuario informa muestreo aleatorio individual, una medición por individuo y ausencia de pareamiento y conglomerados. Revalidar el diseño antes de ejecutar.']
    return evidence


def validate_independence(text, context=None, *, require_pending=True):
    text = normalize(text)
    # La suficiencia del diseño es informada, nunca una garantía derivada del perfil.
    pending = bool(re.search(r'pendiente|verificar|comprobar|evaluar|no (?:se puede |esta |se ha )?(?:garantiz|confirm|verific)|no deducir', text))
    evidence = (context or {}).get('independence_evidence')
    for clause in re.split(r'[.;\n]', text):
        if not require_pending and 'independen' not in clause:
            continue
        negated = re.search(r'no .*?(?:garantiz|confirmad|verificad|asegurad|demostrad)', clause)
        if re.search(r'garantiz\w*.{0,60}independen|independen.{0,60}garantiz', clause) and not negated:
            raise ValueError('No garantizar independencia por filas o individuos distintos; documenta el diseño informado o un supuesto pendiente.')
        if not evidence and re.search(r'confirmada|verificada|asegurada|demostrada', clause) and not negated:
            raise ValueError('La independencia no está confirmada: falta evidencia metodológica del usuario.')
    if require_pending and not evidence and not pending:
        raise ValueError('Sin evidencia metodológica suficiente del usuario, registra independencia como supuesto pendiente de verificar, no confirmado.')
