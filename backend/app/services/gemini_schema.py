"""Contrato de transporte conservador, separado de las reglas internas Pydantic.

No exportar model_json_schema(): extra=forbid, defaults y límites pertenecen
a la validación del servidor, no al subconjunto Schema de cada proveedor.
"""


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties)}


def _text(description=None, *, nullable=False, enum=None):
    schema = {'type': 'string'}
    if description:
        schema['description'] = description
    if nullable:
        schema['nullable'] = True
    if enum:
        schema['enum'] = enum
    return schema


def _array(items):
    return {'type': 'array', 'items': items}


def _variable():
    return _object({
        'file_id': _text('ID exacto de un dataset asociado.'),
        'sheet': _text('Hoja seleccionada, exactamente como aparece en el contexto.'),
        'column': _text('Nombre exacto de una columna existente.'),
        'role': _text(enum=['outcome', 'predictor', 'group', 'time', 'pair_id', 'description']),
    })


def _plan():
    return _object({
        'title': _text(),
        'objective': _text(),
        'variables': _array(_variable()),
        'procedure': _text(enum=['descriptive', 'exploratory', 'group_comparison', 'correlation',
                                 'paired_comparison', 'inferential', 'integral']),
        'method': _text('Procedimiento propuesto, sin resultados calculados.'),
        'justification': _text(),
        'requirements': _array(_text()),
        'limitations': _array(_text()),
        'expected_outputs': _array(_text()),
        'joins': _array(_object({
            'left': _variable(), 'right': _variable(), 'justification': _text(),
            'confirmed_by_user': {'type': 'boolean'},
        })),
        'methodology_confirmed': {'type': 'boolean'},
    })


def reply_schema():
    """Nueva instancia por llamada: el SDK puede transformar el diccionario."""
    return _object({
        'response': _text('Respuesta conversacional en español; no inventar estadísticas.'),
        'suggested_stage': _text(enum=['understanding', 'clarification', 'goal', 'proposal']),
        'detected_goal': _text(nullable=True),
        'suggested_title': _text(nullable=True),
        'questions': _array(_text()),
        'involved_file_ids': _array(_text()),
        'selected_variables': _array(_variable()),
        'proposals': _array(_plan()),
        'warnings': _array(_text()),
        'confirmation_required': {'type': 'boolean'},
        'goal_change': {'type': 'boolean'},
        'goal_change_reason': _text(nullable=True),
        'context_summary': _text(nullable=True),
    })
