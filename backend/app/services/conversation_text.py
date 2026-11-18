import re
import unicodedata

ACTION_LABELS = {
    'reuse': 'Reutilizar archivos', 'new_files': 'Cargar archivos nuevos', 'instrument_yes': 'Sí, utilicé un instrumento',
    'instrument_no': 'No tengo instrumento', 'instruments_done': 'Continuar con los datasets',
    'files_ready': 'Comprender los archivos adjuntos', 'keep_goal': 'Continuar con la finalidad actual',
}
UUID_TEXT = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn').strip(' .!¿?¡\n')


def statistical_request(text):
    text = normalize(text)
    if re.search(r'que (es|significa)|como funciona|explicame|puedes explicar', text) and not re.search(r'quiero (compar|analiz|explor)|deseo (compar|analiz|explor)', text):
        return False
    intent = re.search(r'quiero|deseo|me gustaria|necesito|recomiend|sugier|prop[oó]n|que analisis|puedes|compara|analiza|explora|no .*conozco|no se', text)
    subject = re.search(r'anal[iy]s|analiz|alternativas|compar|explor|describ|distribu|correla|relacion|asocia|mejoraron|diferenc|investig|welch|rendimiento|estim|determina', text)
    return bool(intent and subject)


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
    for file in files:
        text = text.replace(file['id'], file.get('original_name', 'archivo de datos'))
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
