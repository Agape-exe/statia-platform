import re
import unicodedata

ACTION_LABELS = {
    'reuse': 'Reutilizar archivos', 'new_files': 'Cargar archivos nuevos', 'instrument_yes': 'Sí, utilicé un instrumento',
    'instrument_no': 'No tengo instrumento', 'instruments_done': 'Continuar con los datasets',
    'files_ready': 'Comprender los archivos adjuntos', 'keep_goal': 'Continuar con la finalidad actual',
}
UUID_TEXT = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
NO_PROPOSALS = re.compile(r'\b(?:sin (?:crear |preparar |generar )?|no (?:quiero|necesito|deseo|prepares|generes|propongas|crees) )(?:(?:ningun[ao]?|nuev[oa]s?) )?(?:planes?|propuestas?)\b')
PROPOSAL_REQUEST = re.compile(
    r'\b(?:genera|prepara|elabora|crea|disena|plantea|propon|presenta|ofrece|dame|quiero|deseo|necesito|solicito|sugiere)'
    r'(?:r|me)? (?:que (?:me )?(?:prepares|generes|propongas|plantees) )?(?:hasta |como maximo )?'
    r'(?:(?P<count>una?|dos|tres|cuatro|\d{1,3}) )?(?:sol[ao] |unic[ao] |nuev[ao]s? )?'
    r'(?:propuestas?|planes?|alternativas? (?:independientes? )?de analisis)\b'
)


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn').strip(' .!¿?¡\n')


def proposal_limit(text):
    text = ' '.join(normalize(text).split())
    if NO_PROPOSALS.search(text):
        return None
    request = PROPOSAL_REQUEST.search(text)
    if not request:
        return None
    count = request['count']
    return min(4, max(1, int(count))) if count and count.isdecimal() else {
        'un': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4,
    }.get(count, 4)


def statistical_request(text):
    text = normalize(text)
    if NO_PROPOSALS.search(text):
        return False
    if proposal_limit(text) is not None:
        return True
    if re.search(r'preguntas?|codigos?|items?|opciones?', text) and re.search(r'instrumento|cuestionario|documento|pdf|docx', text) and not re.search(r'plan|ejecut|correlacion|anova|frecuencias de (?:la |las )?variable', text):
        return False
    if re.search(r'(?:que|cual|cuales|explica|describe|muestra|recupera|busca|identifica).*\b(?:preguntas?|codigos?|items?|opciones?)\b', text) and re.search(r'instrumento|cuestionario|documento|pdf|docx', text):
        return False
    if re.search(r'que (es|significa)|como funciona|explicame|puedes explicar', text) and not re.search(r'quiero (compar|analiz|explor)|deseo (compar|analiz|explor)', text):
        return False
    intent = re.search(r'quiero|deseo|me gustaria|necesito|recomiend|sugier|prop[oó]n|que analisis|puedes|compara|analiza|explora|no .*conozco|no se', text)
    subject = re.search(r'anal[iy]s|analiz|alternativas|compar|explor|describ|descript|distribu|correla|relacion|asocia|mejoraron|diferenc|investig|welch|rendimiento|estim|determina', text)
    return bool(intent and subject)


def interaction_mode(turn):
    text = normalize(turn.content)
    if turn.action == 'files_ready':
        return 'understanding'
    if turn.action != 'message':
        return 'planning'
    if proposal_limit(text) is not None:
        return 'planning'
    if re.search(r'^(?:comprende|comprender|ayudame a comprender|quiero comprender|necesito comprender|revisa|identifica|describe) (?:los |mis |estos |las )?(?:archivos|adjuntos|datasets|columnas|hojas)', text) and not re.search(r'\bplan|propuesta|ejecut', text):
        return 'understanding'
    if re.search(r'instrumento|cuestionario|documento|\bpdf\b|\bdocx\b', text) and re.search(r'\?|^(?:que|cual|puedes|podrias|dime|explica|describe|muestra|recupera|busca|identifica|consulta)|necesito.*(?:preguntas|codigos|opciones)', text) and not statistical_request(text):
        return 'document'
    if re.search(r'solo (?:necesito |quiero )?(?:una )?(?:comprension|descripcion de los archivos)', text):
        return 'understanding'
    if NO_PROPOSALS.search(text):
        return 'methodology' if re.search(r'metodo|procedimiento|comparar opciones', text) else 'understanding'
    if not statistical_request(text) and (turn.content.rstrip().endswith('?') or re.search(r'que (?:es|significa)|como funciona|explica|metodolog|contexto|objetivos.*guardad', text)):
        return 'methodology'
    return 'planning'


def technical_details_requested(text):
    text = normalize(text)
    return bool(re.search(r'(?:muestra|incluye|dame|ver|necesito|solicito).*?(?:uuid|run_id|identificadores? tecnicos?|detalles tecnicos|auditoria)', text)
                and not re.search(r'\bno\b|sin (?:uuid|identificadores|detalles)', text))


def action_of(message):
    action = message.get('metadata', {}).get('turn_action')
    if action:
        return action
    return next((a for a, label in ACTION_LABELS.items() if message['content'] == label), 'message')


def goal_evidence(messages):
    return [m['content'][:6000] for m in messages if m['role'] == 'user' and action_of(m) == 'message' and statistical_request(m['content'])][-4:]


def recommendations_requested(text):
    text = normalize(text)
    if re.search(r'sin propuestas|sin planes|solo (?:necesito |quiero )?(?:una )?(?:descrip|comprension)|no (?:quiero|necesito|deseo) (?:planes|propuestas)', text):
        return False
    explicit = re.search(r'recomiend|sugier|propon|alternativas|que analisis|no se.*analisis', text)
    # Desconocer los datos no transforma una petición descriptiva en una cuota de planes.
    return bool(explicit or re.search(r'no .*conozco|desconozco', text) and not re.search(r'describ|descrip|comprend|identific', text))


def friendly_text(text, files, run_ids=()):
    if not run_ids:
        text = re.sub(r'https?://[^\s)`]+/storage/v1/object/[^\s)`]+', 'recurso privado', text)
        text = re.sub(UUID_TEXT.pattern + r'(?:/[^\s)`]+)+', 'archivo privado', text, flags=re.I)
    for file in files:
        if file.get('storage_path'):
            text = text.replace(file['storage_path'], file.get('original_name', 'archivo de datos'))
        text = text.replace(file['id'], file.get('original_name', 'archivo de datos'))
    if not run_ids:
        text = re.sub(r'\brun_id`?\s*[:=]?\s*`?' + UUID_TEXT.pattern + r'`?', 'ejecución guardada', text, flags=re.I)
        text = re.sub(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b', 'fecha de la ejecución', text)
    return UUID_TEXT.sub(lambda match: match[0] if match[0] in run_ids else 'archivo del proyecto', text)


def humanize_reply(reply, files, run_ids=()):
    human_fields = {'response', 'detected_goal', 'suggested_title', 'goal_change_reason', 'context_summary',
                    'questions', 'warnings', 'title', 'objective', 'method', 'justification', 'requirements',
                    'limitations', 'expected_outputs', 'independence', 'valid_observations', 'missing_data',
                    'outliers', 'normality', 'definition', 'correction', 'confidence_interval', 'multiplicity_reason'}
    def visit(value):
        if isinstance(value, dict):
            return {key: friendly_text(item, files, run_ids) if key in human_fields and isinstance(item, str)
                    else [friendly_text(t, files, run_ids) for t in item] if key in human_fields and isinstance(item, list)
                    else visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value
    data = visit(reply.model_dump(mode='json'))
    # La bienvenida ya fue persistida al crear el chat; conservar el contenido sustantivo.
    data['response'] = re.sub(r'(?is)^\s*¡?hola[^.!?\n]*[.!?]\s*', '', data['response'])
    data['response'] = re.sub(r'(?is)^\s*soy (?:statia|(?:tu |el )?asistente)[^.!?\n]*[.!?]\s*', '', data['response'])
    return type(reply).model_validate(data)
