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


def _selection():
    return _object({'variable': _variable(), 'values': _array(_text())})


def _comparison():
    schema = _object({
        'design': _text(enum=['independent', 'paired', 'unknown']),
        'groups': _array(_text('Dos etiquetas exactas que se compararán.')),
        'filters': _array(_selection()),
        'strata': {**_selection(), 'nullable': True},
        'independence': _text('Qué evidencia sustenta independencia y qué debe verificarse.'),
        'valid_observations': _text('Definir las filas válidas; los recuentos se informarán al ejecutar.'),
        'missing_data': _text('Excluir del cálculo solo ausencias en variables necesarias; no modificar originales.'),
        'outliers': _text(), 'normality': _text(),
        'variance_assumption': _text(enum=['unequal_allowed', 'equal_required', 'unassessed']),
        'effect_size': _object({
            'name': _text(enum=['cohen_d', 'hedges_g', 'glass_delta', 'mean_difference']),
            'standardizer': _text(enum=['pooled_sd', 'average_variance_sd', 'reference_group_sd', 'none']),
            'definition': _text('Fórmula simbólica o definición exacta y denominador; sin valores calculados.'),
            'correction': _text('Corrección de Hedges si corresponde, o explicar por qué no aplica.'),
            'confidence_interval': _text('Cómo se estimará el intervalo de confianza en la ejecución posterior.'),
        }),
        'purpose': _text(enum=['exploratory', 'confirmatory']),
        'multiplicity': _text(enum=['holm', 'none', 'pending']),
        'multiplicity_reason': _text('Justificar la estrategia según finalidad y cantidad de contrastes.'),
    })
    return {**schema, 'nullable': True, 'description': 'Detalles para una comparación de dos grupos. Usar null para ANOVA global, descripción y correlación. No inventar dos grupos cuando hay tres o más categorías.'}


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
        'comparison': _comparison(),
        'components': _array(_object({
            'procedure': _text(enum=['descriptive', 'exploratory', 'group_comparison', 'correlation', 'paired_comparison', 'inferential']),
            'method': _text(), 'variables': _array(_variable()),
        })),
    })


def reply_schema():
    """Nueva instancia por llamada: el SDK puede transformar el diccionario."""
    return _object({
        'response': _text('Respuesta conversacional en español; no inventar estadísticas.'),
        'suggested_stage': _text(enum=['understanding', 'clarification', 'goal', 'proposal']),
        'detected_goal': _text(nullable=True),
        'suggested_title': _text(nullable=True),
        'questions': _array(_text()),
        'clarification_required': {'type': 'boolean'},
        'involved_file_ids': _array(_text()),
        'selected_variables': _array(_variable()),
        'proposals': _array(_plan()),
        'warnings': _array(_text()),
        'confirmation_required': {'type': 'boolean'},
        'goal_change': {'type': 'boolean'},
        'goal_change_reason': _text(nullable=True),
        'context_summary': _text(nullable=True),
    })
