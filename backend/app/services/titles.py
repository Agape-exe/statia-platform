"""Títulos locales derivados de una finalidad; sin llamadas al proveedor."""
import re

from app.services.conversation_text import ACTION_LABELS, normalize


def usable_title(value):
    return bool(value and normalize(value) not in {
        'nueva conversacion', 'nuevo chat', 'conversacion', 'comprender archivos',
        *(normalize(label) for label in ACTION_LABELS.values()),
    })


def compact_title(value):
    value = re.sub(r'\s+', ' ', value).strip(' .!?¿¡')
    if len(value) <= 80:
        return value
    return (value[:79].rsplit(' ', 1)[0] or value[:79]).rstrip(' ,;:') + '…'


def automatic_title(conversation, suggested, goal):
    """El fallback queda provisional hasta elegir un plan; nunca pisa títulos manuales."""
    if conversation.get('title_manual'):
        return None, False
    provisional = conversation.get('stage_data', {}).get('title_provisional', False)
    if usable_title(conversation.get('title')) and not provisional:
        return None, False
    if usable_title(suggested):
        return compact_title(suggested), False
    if not goal:
        return None, provisional
    text = re.sub(r'^(?:quiero|deseo|necesito|me gustar[ií]a)\s+', '', goal, flags=re.I)
    if re.search(r'recomiend|sugier|no .*conozco|no s[eé].*an[aá]lisis', text, re.I):
        text = 'Exploración estadística de los datos'
    return compact_title(text[0].upper() + text[1:]), True


def title_completed_activity(conversation, turn, result):
    """Da un título provisional al primer turno informativo sin finalidad estadística."""
    if conversation.get('title_manual') or usable_title(conversation.get('title')) or result.get('title'):
        return
    mode = result.get('metadata', {}).get('interaction_mode')
    if turn.action == 'message' and mode in ('document', 'methodology', 'understanding'):
        title = compact_title(turn.content)
    elif turn.action in ('files_ready', 'reuse'):
        title = 'Exploración de archivos' if turn.action == 'files_ready' else 'Archivos reutilizados'
    else:
        return
    if usable_title(title):
        result['title'] = title
        result['stage_data'] = {**result['stage_data'], 'title_provisional': True}
