from app.models.analysis import ProcedureInfo


def entry(code, name, families, types, design, groups, assumptions, statistics, effects, limitations):
    return ProcedureInfo(code=code, name=name, families=families, variable_types=types, design=design,
                         groups=groups, assumptions=assumptions, parameters=['confidence_level', 'two-sided'],
                         statistics=statistics, effects=effects, limitations=limitations)


CATALOG = {p.code: p for p in [
    entry('descriptive', 'Estadística descriptiva', ['descriptive', 'exploratory'], 'Cuantitativas y categóricas; ordinal con orden confirmado',
          'No aplicable', '0–20', ['IC de media: muestreo independiente y normalidad aproximada de la media'],
          ['n', 'faltantes', 'media', 'mediana', 'moda', 'SD', 'varianza', 'cuartiles', 'IQR', 'frecuencias', 'IC media'], [],
          ['Sin IC de media para ordinales ni variables constantes; máximo 100 categorías.']),
    entry('pearson', 'Correlación de Pearson', ['correlation'], 'Dos o más cuantitativas', 'Observaciones independientes', 'No aplicable',
          ['Relación lineal', 'Normalidad bivariada para inferencia', 'Independencia pendiente de diseño'],
          ['r', 'p', 'n por pareja', 'IC Fisher z'], ['r'], ['IC solo con n > 3; no implica causalidad.']),
    entry('spearman', 'Correlación de Spearman', ['correlation'], 'Cuantitativas u ordinales con orden explícito', 'Observaciones independientes', 'No aplicable',
          ['Relación monótona', 'Independencia pendiente de diseño'], ['rho', 'p asintótico', 'n por pareja'], ['rho'],
          ['Sin IC; p asintótico poco preciso con n <= 500 y empates.']),
    entry('student_t', 't de Student independiente', ['group_comparison', 'inferential'], 'Una cuantitativa y una agrupación nominal/binaria/ordinal',
          'Independiente confirmado', '2', ['Varianzas iguales confirmadas', 'Normalidad aproximada', 'Independencia pendiente de diseño'],
          ['t', 'gl', 'p', 'IC diferencia'], ['diferencia', 'd de Cohen (SD combinada)', 'g de Hedges (J exacto)'], ['Sin IC de d/g.']),
    entry('welch_t', 't de Welch', ['group_comparison', 'inferential'], 'Una cuantitativa y una agrupación nominal/binaria/ordinal',
          'Independiente confirmado', '2', ['Normalidad aproximada', 'Independencia pendiente de diseño; permite varianzas distintas'],
          ['t', 'gl Welch–Satterthwaite', 'p', 'IC diferencia'], ['diferencia', 'd de Cohen (SD combinada)', 'g de Hedges (J exacto)'],
          ['SD combinada es un estandarizador descriptivo con heterocedasticidad; sin IC de d/g.']),
    entry('anova', 'ANOVA de un factor', ['group_comparison', 'inferential'], 'Una cuantitativa y una agrupación nominal/binaria/ordinal',
          'Independiente confirmado', '3–20', ['Varianzas iguales confirmadas', 'Normalidad aproximada', 'Independencia pendiente de diseño'],
          ['F', 'gl entre y dentro', 'p'], ['eta cuadrado clásico'], ['Sin post-hoc ni IC de eta cuadrado.']),
    entry('welch_anova', 'ANOVA de Welch', ['group_comparison', 'inferential'], 'Una cuantitativa y una agrupación nominal/binaria/ordinal',
          'Independiente confirmado', '3–20', ['Normalidad aproximada', 'Independencia pendiente de diseño; permite varianzas distintas'],
          ['F Welch', 'gl corregidos', 'p'], [], ['Efecto global e IC no implementados para Welch; sin post-hoc.']),
]}
