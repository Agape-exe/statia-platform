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


def _variable(*, planning=False):
    return _object({
        'file_id': _text('ID exacto de un dataset asociado.'),
        'sheet': _text('Hoja seleccionada, exactamente como aparece en el contexto.'),
        'column': _text('Nombre exacto de una columna existente.'),
        'role': _text(enum=['outcome', 'predictor', 'group', 'time', 'pair_id', 'description'] + (['filter'] if planning else [])),
    })


def _selection(*, planning=False):
    return _object({'variable': _variable(planning=planning), 'values': _array(_text())})


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


def _plan(planning):
    properties = {
        'title': _text(),
        'objective': _text(),
        'variables': _array(_variable(planning=planning)),
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
            'method': _text(), 'variables': _array(_variable(planning=planning)),
        })),
    }
    if planning:
        from app.services.plan_capabilities import LABELS
        from app.services.statistics.catalog import CATALOG
        properties['filters'] = _array(_selection(planning=True))
        properties['method'] = _text(enum=[*CATALOG, 'integral'])
        properties['components']['items']['properties']['method'] = _text(enum=list(CATALOG))
        properties['expected_outputs'] = _array(_object({
            'product': _text('ID del producto permitido para el método.', enum=list(LABELS)),
            'component': _text('plan para productos del plan o índice del componente integral.',
                               enum=['plan', '1', '2', '3', '4']),
        }))
        effect = properties['comparison']['properties']['effect_size']['properties']
        effect['name'] = _text(enum=['cohen_d', 'hedges_g', 'mean_difference'])
        effect['standardizer'] = _text(enum=['pooled_sd', 'none'])
        effect['confidence_interval'] = _text(enum=[
            'Intervalo de confianza para la diferencia de medias.',
            'Intervalo de confianza para la media de las diferencias pareadas.',
        ])
    return _object(properties)


def reply_schema(interaction_mode=None, *, structured=True):
    """Nueva instancia por llamada: el SDK puede transformar el diccionario."""
    properties = {
        'response': _text('Respuesta conversacional en español; no inventar estadísticas.'),
        'suggested_stage': _text(enum=['understanding', 'clarification', 'goal', 'proposal']),
        'detected_goal': _text(nullable=True),
        'suggested_title': _text(nullable=True),
        'questions': _array(_text()),
        'clarification_required': {'type': 'boolean'},
        'involved_file_ids': _array(_text()),
        'selected_variables': _array(_variable(planning=structured)),
        'proposals': _array(_plan(structured)),
        'warnings': _array(_text()),
        'confirmation_required': {'type': 'boolean'},
        'goal_change': {'type': 'boolean'},
        'goal_change_reason': _text(nullable=True),
        'context_summary': _text(nullable=True),
    }
    if interaction_mode in {"understanding", "methodology", "document"}:
        for field in ("proposals", "confirmation_required", "selected_variables", "goal_change", "goal_change_reason"):
            properties.pop(field)
        properties["suggested_stage"] = _text(enum=["understanding", "clarification", "goal"])
    return _object(properties)
