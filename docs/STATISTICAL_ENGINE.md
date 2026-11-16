# Motor estadístico — Sesión 03

## Contrato y procedimientos

Plan v1 se conserva sin reescribir. ExecutionSpec v1 decide métodos por índice de componente, tipos por referencia `{file_id,sheet,column}`, unidades, marcadores ausentes/conservados, orden ordinal, filtros aceptados, grupos, diseño, confianza, alternativa bilateral y multiplicidad. El preparador reconoce nombres/códigos del catálogo en el campo `method` de planes antiguos, pero solo los admite tras contrastar familia, roles, decisiones y originales. Varios nombres conservan la ambigüedad; no interpreta libremente toda la prosa. Un integral antiguo sin componentes o una familia no soportada requiere revisar la propuesta.

`statistics/automatic.py` produce `ExecutionPreparation` v1: READY, NEEDS_CLARIFICATION, BLOCKED_UNCERTAINTY o UNSUPPORTED, especificación todavía sin confirmar, motivos, evidencia verificada/inferida/declarada por el usuario, advertencias, preguntas e impedimentos. Las aclaraciones pending/answered/unknown separan falta de respuesta e incertidumbre reconocida. Unknown no se vuelve a preguntar automáticamente ni habilita READY; puede revisarse por acción explícita. No calcula contrastes ni elige por significación. Comparaciones cuantitativas genéricas pueden usar Welch según el número real de grupos; asociaciones categóricas genéricas consideran dimensiones/esperadas para chi-cuadrado o Fisher. Los métodos expresamente aceptados se conservan, incluso si requieren revisar la propuesta. Independencia no documentada, códigos de escala desconocida y marcadores ambiguos se aclaran; no se convierten en confirmaciones por haber aceptado el plan. El campo aditivo `Plan.filters` permite mantener el alcance en una propuesta descriptiva alternativa sin copiar una comparación inferencial; comparte validación y preparación con los filtros anteriores de comparison.

La preparación utiliza el mismo proceso acotado, exclusión y límites de recursos. `validate_spec(..., require_confirmation=False)` permite validar un borrador conservando `decisions_confirmed=False`; la ejecución sigue exigiendo confirmación. El modo avanzado usa las mismas comprobaciones previas de estructura/tamaños/variación, además de las validaciones del motor. Un cambio sustancial de método exige una propuesta revisada. La huella incluye plan, hashes de originales, respuestas y especificación; el UUID automático se deriva de propuesta/huella para que una preparación idéntica reutilice el resultado, incluso tras recargar o desde otro dispositivo. Antes de calcular se vuelve a evaluar esa preparación con los originales recién descargados. Ver [flujo y límites de automatización](EXECUTION_UX.md).

| Código | Procedimiento real | Efecto / intervalo disponible |
| --- | --- | --- |
| descriptive | Cuantitativos y frecuencias, agrupación categórica opcional | IC t de media cuando N>1 y SD>0; sin inferencia para ordinales |
| pearson | Correlación de Pearson por parejas completas | r; IC Fisher z cuando N>3 |
| spearman | Rangos medios, orden ordinal explícito | rho; p asintótico; sin IC |
| student_t | t independiente con igualdad confirmada | Diferencia, IC t, d combinada, g con J exacto |
| welch_t | t independiente heterocedástica | Diferencia, IC Welch, d combinada, g con J exacto |
| anova | ANOVA de un factor con igualdad confirmada | η² clásico; sin IC global |
| welch_anova | ANOVA de Welch | Sin efecto global específico ni IC global |
| paired_t | t de diferencias de pares identificados | Diferencia e IC t; d_z; sin IC de d_z |
| mann_whitney | U asintótica bilateral, empates/continuidad | r biserial de rangos; sin IC |
| wilcoxon | Pareado asintótico, zero_method=wilcox, continuidad | Sin efecto estandarizado ni IC; ≥10 diferencias no nulas |
| kruskal | H de Kruskal–Wallis corregido por empates | Sin efecto global/IC ni post-hoc de rangos |
| chi_square | Pearson de independencia sin Yates | V de Cramér convencional; sin IC |
| fisher_exact | Fisher exacto bilateral 2×2 | Odds ratio de producto cruzado cuando está definido; sin IC |

Post-hoc opcional de ANOVA: todas las parejas con t de Welch y Holm en una familia separada, **elegido antes del cálculo**. No se activa por significación global. Conserva p originales y ajustados; los IC por pareja son individuales, no simultáneos. No se implementan Tukey/Games–Howell ni selección retrospectiva de métodos.

Diagnósticos de comparación cuantitativa: Shapiro (hasta 5000 observaciones seleccionadas uniformemente), Levene centrado en mediana, conteos de atípicos por 1.5 IQR y boxplot. No eligen el método. La independencia entre personas/pares permanece pendiente del diseño. Las varianzas nulas, muestras insuficientes y grupos vacíos se informan, sin producir infinitos como resultados válidos.

## Fórmulas y variantes

- Descriptivos: varianza y SD con denominador n−1; cuartiles de interpolación lineal de NumPy. Moda solo si hay repetición, hasta 20 modas en tabla, con conteo total interno. IC de media: `media ± t_(1−α/2,n−1) * SD/sqrt(n)`. No se presenta IC para una constante ni una sola observación. Categorías: frecuencias relativas/porcentajes sobre valores válidos, faltantes aparte. Ordinales: frecuencias y categorías medianas inferior/superior, sin media de códigos.
- Dos grupos: diferencia `media1−media2` según el orden registrado. `s_p²=((n1−1)s1²+(n2−1)s2²)/(n1+n2−2)`. Student usa `SE=s_p*sqrt(1/n1+1/n2)` y gl `n1+n2−2`. Welch usa `SE=sqrt(s1²/n1+s2²/n2)` y `ν_W=(s1²/n1+s2²/n2)²/[(s1²/n1)²/(n1−1)+(s2²/n2)²/(n2−1)]`. IC con el SE y gl del contraste elegido.
- `d=(media1−media2)/s_p`; `g=J(ν_H)*d`, con **ν_H=n1+n2−2**, nunca ν_W. J exacto: `Γ(ν_H/2)/(sqrt(ν_H/2)*Γ((ν_H−1)/2))`, evaluado con log-gamma. No se utiliza la aproximación `1−3/(4ν_H−1)`. La SD combinada es un estandarizador descriptivo de cautelosa interpretación si las varianzas difieren; no implica que Welch asuma homocedasticidad. Los planes que exigen otro estandarizador deben revisarse, no se sustituyen silenciosamente.
- ANOVA clásico: `F=(SS_entre/(k−1))/(SS_dentro/(N−k))`; `η²=SS_entre/SS_total`. No se reutiliza η² en Welch.
- Welch ANOVA: `w_i=n_i/s_i²`, `W=Σw_i`, `m_w=Σw_i*m_i/W`, `Q=Σ(1−w_i/W)²/(n_i−1)`. `F=[Σw_i(m_i−m_w)²/(k−1)]/[1+2(k−2)Q/(k²−1)]`; gl1=k−1 y gl2=(k²−1)/(3Q).
- Pearson: SciPy pearsonr y su IC Fisher z, sin bootstrap. Spearman: SciPy spearmanr con rangos medios; su p asintótico puede ser impreciso con N≤500/empates, advertidos. Una constante o menos de tres parejas no tiene correlación calculable.
- t pareada: dos medidas de la misma fila y un identificador de par explícito, no nulo y único entre los casos presentes. Se excluyen pares incompletos; IDs repetidos bloquean. `t=media(D)/(SD(D)/sqrt(n))`, gl=n−1, `d_z=media(D)/SD(D)`. No se presenta d_z como d combinada ni se emparejan archivos/filas arbitrariamente.
- Mann–Whitney: U1 y `r_rb=2U1/(n1*n2)−1`, positivo cuando grupo 1 tiende a valores mayores; empates dan medio crédito. Aproximación normal con continuidad. Kruskal–Wallis usa corrección por empates. Ninguno es una prueba universal de medianas sin condiciones de forma.
- Wilcoxon: diferencias cuantitativas sin redondeo automático, `zero_method=wilcox`, p normal bilateral con continuidad. Registra ceros y número efectivo de diferencias no nulas; no usa exactitud falsa con empates/ceros.
- Chi-cuadrado: esperadas por producto de márgenes/N, Pearson sin Yates y `V=sqrt(chi²/[N*min(r−1,c−1)])`, sin corrección de sesgo. Esperadas <5 generan advertencia/supuesto incumplido; Fisher 2×2 es una alternativa que se debe seleccionar explícitamente. Fisher bilateral ordena por probabilidad hipergeométrica; odds ratio infinito/indefinido se registra como null con explicación.
- Holm: ordenar p, multiplicar por `m−rango+1`, máximo acumulado, acotar a 1 y restituir orden. ExecutionSpec.multiplicity ajusta los contrastes principales de toda la ejecución; la familia post-hoc se ajusta aparte. No se ajustan los IC ni los diagnósticos de distribución.

Las pruebas analíticas y tolerancias están en `test_statistics.py` y `test_statistics_additional.py`; referencias API primarias: [SciPy ttest_ind](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html), [ANOVA/Welch](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.f_oneway.html), [Mann–Whitney](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html), [Wilcoxon](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html) y [chi2_contingency](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html). El ANOVA se implementa con las fórmulas anteriores y se contrasta con la implementación independiente de SciPy y casos racionales exactos.

## Datos, límites y recursos

Python 3.12; versiones verificadas y fijadas: NumPy 2.5.5, SciPy 1.18.1, Matplotlib 3.11.2 y psutil 7.2.2. Sin pandas/statsmodels porque no son necesarios para este catálogo. Cada resultado conserva las versiones efectivas, incluyendo openpyxl.

Se releen CSV UTF-8 (coma/punto y coma/tab), JSON tabular y XLSX/hoja seleccionada. Se reutilizan límites y perfilado, pero la ejecución no hereda MISSING_VALUE_OVERRIDES globales. Nulos/vacíos son ausencias. En medidas suficientemente sustentadas como cuantitativas, un marcador no numérico inferido por un patrón consistente puede proponerse como ausencia automática, identificada como inferencia y revisable antes de confirmar. Las categorías y los centinelas ambiguos requieren respuesta por archivo/columna. La revisión permite declarar otros marcadores ausentes o conservados, también con perfiles anteriores. Los marcadores se comparan sin espacios exteriores (como en el perfil); para medidas cuantitativas un centinela numérico confirmado coincide entre representaciones equivalentes, por ejemplo -999 y -999.0 en CSV/JSON/XLSX. Las categorías retenidas conservan sus valores originales. Valores incompatibles, fórmulas XLSX sin valor numérico original y mezclas no resueltas bloquean; no hay coerción con errores descartados ni imputación. Los códigos pueden confirmarse categóricos/ordinales; un identificador detectado no se acepta como medida cuantitativa. Temporales e identificadores no tienen un descriptivo específico en este MVP.

Límites: 1–4 archivos, 10 MB por archivo, 20 MB originales conjuntos, 400 000 celdas por archivo, hasta 20 grupos, 100 categorías en tablas de frecuencias y ocho variables por correlación. Se conservan límites de perfilado/filas/expansión configurados. Máximo ocho PNG por componente; si se alcanza, se advierte que las tablas sí cubren las variables calculadas. Scatter usa hasta 2000 parejas uniformemente seleccionadas solo para visualización y lo etiqueta; los cálculos usan todos los casos válidos. Histogramas, cajas, dispersión, frecuencias, matriz de correlación y contingencia provienen exclusivamente de datos preparados. Agg funciona sin pantalla.

Un proceso numérico por API con hilos BLAS limitados a uno, 45 s de cálculo, 150 s de operación, concesión de 180 s y sin cola durable. Control RSS observado cada 100 ms: 320 MiB hijo y 450 MiB API+hijo, terminando el árbol al cancelar/exceder. Perfilado comparte exclusión. Configurar **un worker**. Límite de recursos de 24 MB conjuntos (incluido ZIP). No es una garantía de cgroup: picos entre sondeos o varias instancias requieren validación de infraestructura.

Se guardan tablas CSV (UTF-8 BOM, strings potencialmente fórmula neutralizados), PNG, resultados.json con precisión completa, resumen.md, especificación, snapshot del plan, manifiesto SHA-256 y ZIP. El ZIP contiene solo recursos producidos y nunca datasets originales; si falla un componente conserva su motivo. Los CSV/JSON conservan cifras completas; UI/Markdown redondean y presentan p<0.001. Null significa no disponible con motivo/advertencia, no cero. NaN/Infinity se eliminan del JSON y generan estado parcial.

El bucket `analysis-results` es privado y está separado de originales. Descargar exige JWT, pertenencia proyecto/ejecución y validación de bytes/hash. No se crean enlaces públicos. Persistencia y recuperación se describen en [ARCHITECTURE](ARCHITECTURE.md); pruebas reales manuales en [SETUP](SETUP.md).

## API

Todas las rutas exigen Bearer validado con Supabase Auth y están bajo `/projects/{project_id}`:

| Método / ruta | Uso |
| --- | --- |
| GET analysis-procedures | Catálogo tipado disponible |
| POST conversations/{conversation_id}/proposals/{proposal_id}/runs | `{request_id, specification}`; solo aceptadas; respuesta RunView |
| GET analysis-runs?conversation_id=...&limit=50&offset=0 | Listado de proyecto o conversación; máximo 100/página, sin JSON completo |
| GET analysis-runs/{run_id} | Estado, resultado completo y catálogo de recursos |
| GET analysis-runs/{run_id}/artifacts/{artifact_id} | Descarga privada individual con comprobación SHA-256 |
| GET analysis-runs/{run_id}/download | ZIP privado persistido |

401/403: sesión/permisos; 404: ajeno/inexistente; 409: ocupado, UUID/payload distinto, estado o hash incompatible; 413: límites; 422: datos/plan/método incompatibles; 502: persistencia; 504: tiempo excedido. Un rechazo temprano no borra el plan. Un fallo posterior al inicio se registra con error; el mismo UUID/payload puede reiniciar si no hay un resultado final guardado. Un resultado parcial o fallido ya calculado es inmutable por reintento: corregir decisiones y enviar otra solicitud.

## Fuera de alcance

P2 (regresión y métodos adicionales), joins, emparejamiento entre archivos, imputación/limpieza automática, exactitud/permutaciones para todos los métodos de rangos, IC de efectos estandarizados/V/Spearman, efecto global de Welch/Kruskal, post-hoc de rangos, PDF/Word, SVG, colas durables y recolección automática de huérfanos. No hay interfaces simuladas para estos métodos. No se ha acreditado todavía la instalación remota de la migración ni el recorrido autenticado completo con dos cuentas; ver el informe de validación.
