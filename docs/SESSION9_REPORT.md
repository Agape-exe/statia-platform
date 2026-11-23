# Sesión 09 — Estabilización documental y rediseño UX/UI

Fecha: 21 de noviembre de 2026. Repositorio `Agape-exe/statia-platform`.
Base: `fix/cierre-validacion-tesis`, `71c03d8`, limpia al inicio y con los commits
de las sesiones 07 y 08 incluidos. Rama de entrega:
`fix/estabilizacion-instrumentos-ux-sesion9`. Se utilizó la base solicitada
expresamente, sin actualizar ni desarrollar sobre `develop` o `main`.

**Estado: APTO para validación manual controlada.** Los servicios externos y el
instrumento original del incidente siguen pendientes de validación real. No se
hicieron push, PR, merge, despliegues, cambios remotos ni llamadas reales a proveedores.

## Seguimiento de la validación manual

### Intención conversacional y alcance de una tabla de frecuencias

Se reprodujeron las tres incidencias en una conversación nueva de la API
local con Auth, almacenamiento y proveedor simulados. Se usaron
nhanes_dermatology.csv y DEQ_J.pdf disponibles en Descargas. El perfil
detectó 3 419 registros y 8 columnas, y el PDF aportó 5 fragmentos. Su
SHA-256 coincidió con el PDF público del CDC. La tesis conservó Contexto
revisión 1. No se leyó el historial remoto de
la conversación original. [Cuestionario DEQ del CDC](https://wwwn.cdc.gov/nchs/data/nhanes/public/2017/questionnaires/DEQ_J.pdf).

| Incidencia | Causa reproducida en fbfe927 |
| --- | --- |
| A. Comprensión anuncia un plan | La intención ya era comprensión y el contrato descartaba planes. El validador omitía una frase completa si contenía «no». «Porcentajes no ponderados» dejaba pasar el anuncio «he preparado la propuesta» con cero tarjetas. |
| B. Frecuencias exige resúmenes globales | «Frecuencias categóricas» aportaba el producto explícito. «Propuesta descriptiva» activaba la equivalencia léxica a resúmenes globales. «Frecuencias absolutas y porcentajes» quedaba parcialmente sin reconocer y marcaba el alcance como ambiguo. Los dos productos figuraron en el mismo turno fuente. |
| C. Vuelve a preguntar por grupos | El estado ambiguo activaba la respuesta local de aclaración antes de la segunda llamada al proveedor. La plantilla preguntaba siempre si se quería agrupar y no registraba que ya se habían pedido todos los registros sin agrupaciones. |

La reproducción controlada dejó cero propuestas durante la comprensión y
volcó ambos productos al preparar la solicitud. El Contexto solo llegó como
documento de investigación y su revisión. Las respuestas del proveedor, el
mensaje de acción de comprensión y los objetivos del Contexto no fueron
fuentes de los productos requeridos. Se identificó también un riesgo de
continuidad en conversaciones existentes. El estado acumulaba productos
entre planes independientes y se consultaba el alcance más reciente al
aceptar una tarjeta anterior.

Tras el ajuste, con los mismos archivos, el anuncio sin tarjetas se
rechazó y la corrección del proveedor simulado entregó una comprensión
informativa. El turno de frecuencias registró un solo producto, la
columna solicitada y las exclusiones. Persistió una tarjeta, sin
aclaraciones ni ejecuciones. El código de producción no contiene reglas
para archivos, disciplinas ni nombres de variables específicos.

- Las preguntas sobre contenido pasan por comprensión y las consultas de
  significado, posibles métodos y diferencias por conversación
  metodológica. Las consultas documentales mantienen su ruta y permiso.
  Comprensión y conversación no cambian a un plan ni consumen una
  aclaración de comparación pendiente. Los comandos de análisis y las
  solicitudes de propuestas conservan su ruta de planificación.
- Los marcadores de alcance provienen de mensajes del usuario. Se guarda
  la procedencia por producto, se distingue una propuesta nueva de una
  continuación y se conserva la recuperación de solicitudes fallidas.
  Las cachés anteriores se reconstruyen a partir de la evidencia
  disponible. Los productos reconocidos o declarados por el proveedor
  no sustituyen la solicitud del usuario.
- Una tabla de frecuencias puede incluir categorías, recuentos,
  porcentajes, denominador y ausencias. La mención de un descriptivo
  en ese contexto no agrega un resumen global. Las exclusiones
  explícitas de agrupación, filtros, variables adicionales, productos
  y gráficos se validan junto con el contrato previo. Las preguntas
  sobre variables o decisiones indispensables siguen disponibles. Un
  plan que contradice una exclusión ya resuelta produce un diagnóstico
  específico y se puede reintentar con el mismo identificador.
- El alcance se congela en el mensaje de origen de cada tarjeta nueva.
  Aceptar valida contra ese alcance, aunque otro turno prepare un plan
  distinto. Los planes anteriores sin alcance de origen conservan la
  lectura compatible. No hay migraciones ni cambios al contrato Plan v1.
- Aceptar todavía deja cero ejecuciones. La ejecución mantiene sus
  confirmaciones y llama al motor existente. La capa de publicación
  omite los gráficos excluidos y, en una solicitud exclusiva de
  frecuencias, publica una tabla coherente con el alcance. El cálculo
  interno puede producir artefactos descartados antes de guardar. Se
  conservan advertencias, denominador, ausencias y resultados históricos.

Las regresiones HTTP cubren comprensión en ambos tipos de proyecto,
preguntas libres y metodológicas, Contexto amplio, solicitud exclusiva,
rechazo previo, una decisión realmente necesaria y un reintento con el
mismo identificador. También ejecutan el motor real sobre datos
sintéticos tras aceptación y confirmación. La prueba verifica una tabla,
ausencias, denominador, ausencia de PNG y repetición idempotente. El test
de frontend verifica el paso de una respuesta de comprensión sin
tarjeta a una tarjeta con exactamente el producto persistido. Las
regresiones previas revalidan alternativas parciales, tipos, consultas
documentales e inferencia existente.

La batería general de backend pasó con 682 pruebas aprobadas y una omitida.
Tras ampliar las formas explícitas de pedir un plan y afinar el diagnóstico
de alcance ya resuelto, se ejecutaron las suites afectadas sobre el código
final y pasaron 154 pruebas. En frontend pasaron 133 pruebas, TypeScript,
lint, formato y build. Las seis suites PGlite, los controles de calidad de
Python y la comprobación de dependencias también pasaron. Se mantienen los
avisos existentes del cliente de pruebas y del tamaño de un fragmento JS.

Los commits locales son `639a40b` para separar conversación, requisitos y
alcance de cada tarjeta, y `6ae5a58` para conservar el diagnóstico al fallar
un plan con restricciones resueltas. La entrega permanece en
`fix/estabilizacion-instrumentos-ux-sesion9`.

#### Procedimiento para revalidar con Gemini real

Realizar este recorrido en una sesión de validación autorizada para
invocar Gemini. En este seguimiento todas sus respuestas fueron simuladas.

1. Reiniciar la API local con esta rama para cargar los cambios. Abrir
   el proyecto de tesis de exposición solar, comprobar revisión 1 y
   verificar que el CSV y PDF estén asociados a la conversación. Seleccionar
   Gemini. La comprensión de metadatos no requiere compartir el texto
   documental. Conceder ese permiso solo si se quiere consultar el PDF.
2. Pulsar **Comprender los archivos adjuntos**. Confirmar que se muestran
   estructura y advertencias, y que el turno no anuncia ni agrega
   tarjetas y no produce resultados. Preguntar «¿Qué contiene mi
   dataset?» y «¿Qué procedimientos podrían utilizarse para esta
   variable?». Deben ser respuestas informativas sin tarjetas nuevas.
3. Enviar como mensaje nuevo «Prepara una única propuesta descriptiva de
   frecuencias categóricas de sun_reaction con todos los registros. Solo
   quiero una tabla con categorías, frecuencias absolutas y porcentajes,
   denominador y valores ausentes. Sin filtros, sin comparaciones ni
   agrupaciones, sin gráficos, sin otras variables, sin pruebas
   inferenciales y sin resultados adicionales. No ejecutes antes de aceptar».
4. Revisar la única tarjeta. Debe citar la columna exacta y presentar
   solo **Frecuencias categóricas** como producto. No debe volver a
   preguntar por agrupaciones ni mencionar que la propuesta se acepta
   en Contexto. Recargar y comprobar que siguen la tarjeta y el historial.
5. Aceptar en su tarjeta. Verificar que el enlace de preparación es una
   acción aparte y aún no hay ejecución. Si el recorrido incluye
   resultados, verificar las decisiones sobre tipo y ausencias, preparar
   y confirmar explícitamente el cálculo. Revisar la única tabla con N
   válido, ausentes y porcentajes sobre valores presentes, sin PNG.
6. Rechazar una propuesta de prueba y pedir otra con un alcance
   independiente. Verificar la separación de productos. Si aparece un
   fallo real, registrar solo su categoría en **X-Statia-Validation**
   y repetir mediante **Reintentar**, comprobando que el mensaje conserva
   su identificador y se guarda una sola vez.

### T3 — Planificación estadística y tarjetas de revisión (22 de noviembre de 2026)

La validación manual reportó que los recorridos PDF y DOCX avanzaron. El
seguimiento de T3 usó variantes de los mensajes reportados, una copia pública
de los archivos y proveedores simulados. No se inspeccionó el cuerpo privado
devuelto por Gemini ni la respuesta HTTP original de los fallos.

#### S9-PLAN-01 — Anuncio de propuestas sin tarjetas

En la versión bc3fae5, «Genera hasta tres alternativas de análisis estadístico
descriptivo basadas en los objetivos confirmados del Contexto» se clasificaba
como metodología. El clasificador no reconocía el verbo inicial como petición
de plan y encontraba la mención de Contexto. En ese modo, el parser descartaba
los objetos de propuesta aunque el proveedor los devolviera. También se
reprodujo un segundo camino: si la respuesta solo anunciaba tres propuestas,
la prosa podía pasar sin que el servidor exigiera un objeto revisable.

El endpoint persiste las propuestas junto al mensaje de origen y las devuelve
al consultar la conversación. La interfaz presenta tarjetas a partir de esas
filas. Ambos caminos reproducidos explican cómo podía aparecer el anuncio sin
tarjetas. La evidencia disponible no distingue si Gemini devolvió una lista
vacía o si un turno clasificado como metodología descartó la lista original.
El aviso genérico de evidencia pertenece a la rama de errores no planificadores.

#### S9-PLAN-02 — Validación de una propuesta individual

Una variante con «tablas y gráficos» y «No ejecutes cálculos todavía» activaba
la aclaración de alcance en el reconocedor anterior. Trataba «gráficos» como
un producto no especificado aunque la frase solo pedía describir los
entregables. Este bloqueo local es distinto del 502 que reportó el usuario.
El mismo mensaje genérico del 502 se reprodujo, por separado, omitiendo una
columna seleccionada en el objetivo y devolviendo una propuesta de tesis con
metodología sin confirmar. Cada causa tiene su propia categoría. El texto
genérico original no permite confirmar cuál falló en la llamada real.

El objetivo y las columnas exactas deben ser coherentes y el plan debe
incluir su procedimiento, justificación, requisitos, limitaciones y salidas
verificables. En un descriptivo, las comprobaciones posteriores de ausencias y
tipos pueden figurar en requisitos y limitaciones. La aceptación sigue
sujeta a los filtros, relaciones y decisiones metodológicas que correspondan
al procedimiento. Contexto confirmado orienta el plan y no confirma por sí
solo independencia, pareamiento ni orden de una escala.

#### Corrección y comprobaciones

- Una petición explícita entra a planificación y establece el máximo de
  propuestas. La instrucción de aplazar cálculos conserva la solicitud de
  preparación. La discusión metodológica conserva su contrato sin propuestas.
- El backend valida cada alternativa y utiliza el número de planes
  efectivamente validados para el aviso. Si hay dos válidas y una inválida,
  puede conservar las dos con un aviso parcial. Una frase de éxito sin
  propuestas estructuradas se rechaza. Una aclaración imprescindible puede
  devolverse sin planes. La aceptación se hace en el asistente y el guardado
  del documento de investigación se hace en Contexto.
- Los adaptadores comprueban por separado el esquema de cada propuesta en
  solicitudes explícitas. Una alternativa incompleta entra a la corrección
  acotada y el diagnóstico conserva su posición. Plan v1, el esquema de
  transporte y SQL siguen siendo compatibles. Los fallos del turno conservan
  el mensaje y su identificador para un reintento idempotente.
- La propuesta usa los nombres y tipos completos del perfil de la hoja
  seleccionada. El resumen global del libro puede omitir detalle. En una
  regresión omitió 34 columnas y un plan sobre la última columna omitida
  fue recuperado y aceptado. El presupuesto de contexto se conserva.
- La vista distingue orientación metodológica, aclaración para preparar un
  plan y tarjetas persistidas. En la tarjeta se muestran los tipos de perfil
  de las columnas. Pendiente de aceptación, aceptado, rechazado y ejecución
  mantienen sus estados y acciones. Se revisó en navegador la tarjeta con
  sus variables y el paso de pendiente a aceptada en la vista sintética.

En el recorrido local con los archivos públicos, la revisión 1 permaneció
intacta. Tras un turno documental con evidencia, el asistente presentó
tres planes para revisar y luego una propuesta individual. El perfil de
«Form Responses 1» conservó 492 filas y 46 columnas, incluso cuando el
resumen global omitió 23 en ese turno. Una columna de uso de portátil
conservó el tipo mixto y quedó fuera de los resúmenes numéricos propuestos.
Aceptar y rechazar guardó las decisiones y dejó cero ejecuciones.

La primera batería completa de backend tuvo 677 pruebas aprobadas, una
omitida por falta de evidencia local A/D de Terra y un fallo de conservación
del historial al cambiar de proveedor. Se corrigió limitando el nuevo aviso
de tarjetas a las solicitudes explícitas. En el código final pasaron esa
regresión y las 277 pruebas de las suites relevantes. También pasaron 132
pruebas de frontend, las seis suites locales PGlite, el tipado, lint, formato,
build y la comprobación de dependencias. Se conservan los avisos de
deprecación de Starlette y de tamaño de un fragmento JS de Vite.

Los commits locales del ajuste son `cc6a09e` para planificación y contratos,
`95744a1` para la presentación y `cf90031` para conservar las explicaciones
de los turnos sin petición explícita. Se entrega en la rama de Sesión 09.

#### Repetir T3 sin llamadas a proveedores

1. Desde **backend**, ejecuta las regresiones de tesis, perfiles y
   persistencia con los dobles de proveedor.

   ~~~powershell
   .\.venv\Scripts\python.exe -m pytest -q tests/test_thesis_stability.py tests/test_excel_multihoja.py tests/test_chat_api.py
   ~~~

2. Desde **frontend**, activa Vite con **npm run dev** y abre
   **/visual/index.html?screen=asistente** en la URL local de Vite.
   Continúa sin compartir, abre **Revisar dataset y variables** y
   comprueba que la tarjeta tenga objetivo, procedimiento, nombres
   de columnas y tipos. Acepta la propuesta de prueba y abre el plan
   aceptado. La ejecución debe seguir disponible como acción aparte.
   Recarga la vista para restablecer el escenario sintético.
3. Ejecuta **npm test** desde **frontend** para verificar que las
   tarjetas regresan al remontar el chat y que las aclaraciones no
   se muestran como planes ejecutables.
4. Para cotejar el fallo histórico en modo de solo lectura, revisa en
   **Red** el GET del detalle de la conversación y compara los objetos
   de **proposals** con el identificador del mensaje anunciado en
   **source_message_id**. Si conservas el 502 de T3, anota únicamente
   la categoría de **X-Statia-Validation**. No reenvíes el mensaje
   ni exportes encabezados completos.

Queda pendiente cotejar los dos turnos históricos del proyecto privado y
la categoría del 502 original. No se ejecutó un proveedor real ni se
cambiaron documentos, resultados históricos, Supabase remoto o el motor
estadístico.

### T2 — Consulta numerada con un DOCX ya asociado (22 de noviembre de 2026)

Se reprodujo el fallo con el mensaje exacto de la validación. La API lo
clasificó como consulta documental, cargó los instrumentos asociados y recibió
el consentimiento explícito del turno. La búsqueda podía reconocer los tres
temas del mensaje. El detector de referencias interpretó el punto final y el
salto antes de los marcadores «2.» y «3.» como separadores de códigos. Así
formó «entretenerse2» y «verificable3» con las palabras finales de los dos
primeros puntos de la lista.

La presencia de esas referencias activó la búsqueda estricta por código y
desactivó la temática. Ninguno de los 117 fragmentos incluía esos códigos. Todos
quedaron fuera antes de puntuar y aplicar los límites de envío. Con cero
fragmentos seleccionados, el turno se completó como «no_match», con origen
determinista y sin invocar al proveedor ni llegar a validar una respuesta.
La consulta de las pruebas anteriores expresaba los mismos temas en prosa y
carecía del patrón de lista que disparó el defecto.

El normalizador de consultas ahora separa los marcadores numéricos de lista
antes de detectar referencias. La clasificación por código usa la misma
normalización. Los códigos reales conservan sus equivalencias y el buscador
sigue reconociendo referencias partidas por saltos de línea en la evidencia.
El texto original del mensaje, el consentimiento, el vocabulario bilingüe, los
límites y las validaciones de citas se conservan.

El turno lee los vínculos de conversation_files y las filas de project_files
del mismo proyecto. Usa metadata.fragments de la extracción versionada en cada
consulta. No depende de un índice persistido ni de la vista previa de 16 000
caracteres. Para instrumentos sin versión, la lectura autorizada puede
reconstruir los fragmentos temporalmente desde el original privado. Los
registros con versión 1 no requieren nueva carga, extracción ni migración
para esta corrección.

Con el mensaje exacto y la misma instantánea JSON de los archivos públicos,
en una conversación de tesis ya creada con revisión 1, la API real devolvió
estos resultados usando el almacén y proveedor simulados:

| Recuperador | Fragmentos disponibles | Fragmentos seleccionados | Llamadas al doble |
| --- | ---: | ---: | ---: |
| 6ac3b06 | 117 | 0 | 0 |
| Corregido | 117 | 10 | 1 |

En la repetición corregida se seleccionaron los índices 24–26, 30, 34 y 46–50
y el backend validó una cita literal. La regresión automatizada usa filas
versionadas ya asociadas, una conversación con historial y una vista previa
deliberadamente ajena a la evidencia. Falla con el recuperador anterior.
Con la corrección comprueba el contexto de revisión 1, la llegada al doble,
la integridad del historial y que no se descarga el original. Una segunda
consulta numerada sobre temas ausentes se resuelve como «no_match», sin
invocar al doble. Las regresiones cubren LF, CRLF y códigos auténticos
partidos. No se añadieron registros de producción.

El commit local `35b5e36` incluye la corrección y las regresiones. Pasaron 85
pruebas dirigidas y 242 en las suites relevantes de backend. También pasaron
calidad Python, dependencias, TypeScript, lint, formato y build del frontend.
El procedimiento de solo lectura se ejecutó con la instantánea pública y
confirmó igualdad del SHA-256 y de los fragmentos extraídos.

Se comprobó que la configuración local del frontend usa el puerto 8001 y
que, durante el diagnóstico, el servidor escuchaba en él sin recarga
automática. La respuesta histórica no identifica por sí sola la revisión
del proceso que la produjo. Queda pendiente el cotejo de las filas y del
original privados de la conversación real. No se invocó a Gemini ni a Terra.

#### Comprobar la conversación existente en modo de solo lectura

1. Abre la conversación existente sin enviar otro mensaje. En la pestaña
   **Red** de las herramientas del navegador, localiza el GET de
   /projects/{proyecto}/conversations/{conversación} y guarda solo su
   respuesta JSON en **.local/session9/t2-conversacion.json** desde la raíz del
   repo. Guarda el texto exacto del mensaje en **.local/session9/t2-consulta.txt**
   como UTF-8. Mantén las copias en local y excluidas de Git. No hace falta
   guardar cabeceras, tokens o un archivo HAR.
2. Para cotejar la extracción, puedes descargar el original con
   **Descargar original** y guardarlo como **.local/session9/t2-original.docx**.
   Este paso es opcional.
3. Desde **backend**, ejecuta el bloque. Lee los metadatos privados
   que hayas guardado e imprime únicamente estados, recuentos y resultados
   de comparación. No vuelve a enviar el turno ni contacta al proveedor.

~~~powershell
@'
import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.services.instrument_context import retrieve_instruments
from app.services.profiling import inspect_file

folder = Path('../.local/session9')
detail = json.loads((folder / 't2-conversacion.json').read_text(encoding='utf-8-sig'))
query = (folder / 't2-consulta.txt').read_text(encoding='utf-8-sig')
files = [f for f in detail['files'] if f['file_role'] == 'instrument']
for authorized in (False, True):
    outcomes = retrieve_instruments(files, query, authorized)
    print('Permiso:', authorized, 'Instrumentos asociados:', len(files))
    for outcome in outcomes.values():
        print(outcome['retrieval'], outcome['fragments_available'],
              len(outcome['fragments_shared']), outcome.get('retrieval_method', ''),
              'vista previa legada:', outcome['legacy_excerpt_only'])
original = folder / 't2-original.docx'
if original.is_file() and len(files) == 1 and files[0]['file_type'] == 'docx':
    raw = original.read_bytes()
    stored = files[0]['metadata']
    digest = stored.get('content_sha256')
    fresh = inspect_file(original.name, raw, 'instrument', Settings(_env_file=None))
    print('SHA-256 igual:', digest == hashlib.sha256(raw).hexdigest() if digest else 'sin hash')
    print('Fragmentos identicos:', stored.get('fragments') == fresh['fragments'])
'@ | .\.venv\Scripts\python.exe -
~~~

4. Espera «not_authorized» y cero fragmentos compartidos con permiso
   falso. Con permiso verdadero y los metadatos de la copia pública,
   se espera «matched», 117 disponibles y 10 seleccionados.
   Si el registro privado arroja otro resultado, comprueba la versión de la
   extracción y compara el hash y los fragmentos con el original descargado.
   Ejecuta la prueba HTTP local de la conversación persistida para confirmar
   el enrutamiento sin enviar mensajes a la conversación real:

   ~~~powershell
   .\.venv\Scripts\python.exe -m pytest -q tests/test_thesis_stability.py -k previously_persisted
   ~~~

El proceso local sin recarga debe reiniciarse para cargar el código corregido.
Recargar solo la página no actualiza el proceso Python. La comprobación
anterior usa directamente el código del árbol de trabajo.

### T2 — Recuperación bilingüe de un instrumento Word (22 de noviembre de 2026)

T1 con el PDF resultó satisfactoria según la validación manual reportada. Para T2
se examinó la copia pública de `Questionnaire_WP4_individual_EN_v0.docx` y
`UII_individual_public.xlsx`. El objeto privado de la conversación original sigue
pendiente de cotejo. [Archivos públicos ODDEA en Zenodo](https://zenodo.org/records/23841446).

| Archivo público | SHA-256 |
| --- | --- |
| `Questionnaire_WP4_individual_EN_v0.docx` | `a837b857621e97ec38de3a906602ac69e2ff9f36e042934643747dfd7aec469a` |
| `UII_individual_public.xlsx` | `8dc8980e50834f60617919ca03007955446ffc25e029284fd9d8f8d20b7f3e04` |

El extractor real produjo 117 fragmentos, con estado `partial`. Conservó texto de
párrafos, encabezados y celdas por orden de aparición dentro de cada parte Word.
El cuerpo contiene el enunciado sobre tiempo de uso de dispositivos (índice 25),
filas por tipo de dispositivo y un bloque de habilidades con escala e ítem de
habilidades en línea (índices 46–49). Word localiza estos fragmentos por parte y
párrafo. La extracción de texto no conserva la cuadrícula visual de la tabla.

La consulta original en español reprodujo `no_match` con permiso activo. El
recuperador anterior recorría los 117 fragmentos y comparaba las palabras
normalizadas literalmente. La consulta no contenía códigos y los términos en
inglés no coincidían con los términos españoles. El backend terminó el turno
antes de invocar al proveedor. El límite de envío se aplica después de la búsqueda.

La búsqueda ahora combina términos literales con un vocabulario español–inglés
acotado. Las referencias exactas por código mantienen prioridad. Para una consulta
con varios temas se reserva evidencia de cada tema encontrado y, cuando aparecen
filas de una tabla Word, se prioriza la pregunta cercana y su contexto. Se conservan
las ubicaciones, el máximo de 10 fragmentos y 12 000 caracteres y la edición de datos
sensibles previa al contexto del proveedor. El vocabulario cubre varias disciplinas y
puede ampliarse. Fuera de sus términos, sigue disponible la búsqueda literal.

El turno temático exige citas textuales comprobables dentro de un solo fragmento
compartido. Las partes sin respaldo se declaran insuficientes. El DOCX público
permite recuperar evidencia sobre uso de dispositivos y habilidades digitales, incluida
una habilidad en línea. Esa evidencia no acredita por sí sola acceso a dispositivos
ni acceso y uso de internet como medidas independientes. La escala descrita en texto
es recuperable. Algunas series numéricas se ocultan por el filtro de privacidad.

El recorrido local con los archivos públicos y la API real seleccionó los índices
24–26, 30, 34 y 46–50. Con permiso denegado registró `not_authorized` y el proveedor
simulado recibió cero invocaciones. Con el permiso activo recibió una invocación
con la revisión 1 y aceptó una cita textual acompañada del aviso de insuficiencia.
Las pruebas de integración con fixtures también verificaron el diagnóstico
`no_match` y el rechazo de preguntas y opciones inventadas. La respuesta de un
proveedor real y el objeto privado de la conversación quedan pendientes de cotejo.

El libro público conserva las 492 filas y las 46 columnas de `Form Responses 1`.
`columns_omitted` se refiere al detalle duplicado del resumen global del libro.
El recorrido local mantuvo las 46 columnas en el perfil y la vista de filas y
omitió 23 en el resumen. El número depende del espacio restante en el turno.
Una regresión con datos sintéticos reprodujo exactamente 34 columnas omitidas
en el resumen y aceptó un plan sobre la última columna omitida.
Se mantuvieron el presupuesto de contexto, el motor estadístico y los resultados
históricos. La corrección no requiere cambios de dependencias, migraciones ni variables
de entorno de la aplicación. La conciliación de la migración 009 sigue pendiente.

Commits locales del ajuste: `205f36c` (recuperación y regresiones DOCX) y
`b2f011a` (regresión de Excel). El frontend índigo/lavanda conserva la revisión
visual de la entrega inicial. Este ajuste no modifica sus componentes.

La batería general de backend tuvo 666 pruebas aprobadas y una omisión heredada
por falta de evidencia local A/D de Terra. La ejecución dirigida tuvo 239 pruebas
aprobadas. En frontend pasaron 131 pruebas, TypeScript, oxlint, Prettier y el build.
También pasaron el control de calidad de Python y `pip check`. Vite emitió un aviso
de tamaño de un fragmento JS y pytest mostró un aviso deprecación de Starlette.

#### Repetir T2 localmente con los originales

1. Guarda ambos originales fuera de Git. En PowerShell ejecuta `Get-FileHash -Algorithm SHA256`
   sobre cada archivo y compara con la tabla. Si un hash difiere, coteja la evidencia
   que imprima el recorrido con esa versión del documento.
2. Desde `backend`, ejecuta el siguiente bloque con las rutas de tus originales.
   Usa la API y los extractores reales con autenticación, almacenamiento y proveedor
   simulados. Se confirma la revisión 1 dentro del proyecto de prueba. El comando
   no requiere credenciales ni inicia un servidor contra Supabase.

```powershell
$env:STATIA_T2_DOCX = 'C:\ruta\Questionnaire_WP4_individual_EN_v0.docx'
$env:STATIA_T2_XLSX = 'C:\ruta\UII_individual_public.xlsx'
@'
import os
import sys
from pathlib import Path

sys.path.insert(0, 'tests')
from test_chat_api import new, reply, turn
from test_session6 import local, upload
from test_thesis_stability import thesis_context
from app.services.instrument_context import PARTIAL_EVIDENCE

case = local.__wrapped__()
client, store, provider = next(case)
try:
    thesis_context(store, 1)
    path = new(client, store)
    assert turn(client, path, action='instrument_yes').status_code == 200
    docx = Path(os.environ['STATIA_T2_DOCX'])
    xlsx = Path(os.environ['STATIA_T2_XLSX'])
    upload(client, path, docx.name, docx.read_bytes(), role='instrument')
    assert turn(client, path, action='instruments_done').status_code == 200
    dataset = upload(client, path, xlsx.name, xlsx.read_bytes())
    query = ('Que preguntas del instrumento tratan el acceso a dispositivos digitales, '
             'el acceso y uso de internet y las competencias digitales?')
    assert turn(client, path, content=query, share_instrument_text=False).status_code == 200
    blocked = client.get(path).json()['messages'][-1]['metadata']['instrument_retrieval'][0]
    assert blocked['retrieval'] == 'not_authorized' and not provider.contexts
    quote = chr(171) + 'Basic online skills' + chr(187)
    provider.replies.append(reply(response=quote + '\n' + PARTIAL_EVIDENCE))
    result = turn(client, path, content=query, share_instrument_text=True)
    assert result.status_code == 200, result.text
    assert len(provider.contexts) == 1
    context = provider.contexts[0][0]
    assert context['research_context']['revision'] == 1
    assert context['instrument_text_authorized'] is True
    doc = next(f['instrument'] for f in context['files'] if f['role'] == 'instrument')
    assert doc['retrieval'] == 'matched' and doc['retrieval_method'] == 'thematic'
    print('DOCX:', doc['status'], doc['fragments_available'], 'fragmentos disponibles')
    for f in doc['fragments_shared']:
        print(f['index'], f['location'], f['text'])
    book = next(f for f in context['files'] if f['role'] == 'dataset')
    summary = book['workbook_sheets'][0]
    base = f"/projects/{store.project_id}/files/{dataset['id']}"
    profile = client.get(base + '/profile').json()['profile']
    rows = client.get(base + '/rows?limit=1').json()
    assert len(book['columns']) == len(profile['columns']) == len(rows['columns']) == 46
    assert profile['row_count'] == 492
    print('XLSX:', summary['sheet'], profile['row_count'], len(rows['columns']))
    print('Omitidas en el resumen:', summary.get('columns_omitted', 0))
finally:
    case.close()
'@ | .\.venv\Scripts\python.exe -
```

3. Coteja cada extracto con el original. Para los hashes de la tabla, se esperan
   117 fragmentos disponibles y evidencia en los índices 25, 30, 34, 46, 47 y 49
   entre los seleccionados. El número de columnas omitidas del resumen puede variar
   con el contexto. El perfil y la vista de filas deben conservar las 46.
4. Para probar opciones de tabla, temas sin coincidencia y rechazo de texto
   inventado con el doble de proveedor, ejecuta desde `backend`:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q tests/test_instruments.py tests/test_thesis_stability.py tests/test_excel_multihoja.py
   ```

#### T1 — Recuperación por código y ajustes del asistente

Los commits locales `6679d0f` y `913568c` corrigen la búsqueda y la presentación.

La prueba de seguimiento reportó que la consulta de `SLQ030`, `SLQ050` y `SLQ120`
terminaba antes de Gemini con el diagnóstico de texto disponible sin coincidencias.
Se reprodujo ese resultado con el recuperador anterior y la copia pública del CDC,
con `share_instrument_text=true`. El objeto privado de la conversación y su metadata
quedan pendientes de cotejo. [Cuestionario público del CDC](https://wwwn.cdc.gov/nchs/data/nhanes/public/2017/questionnaires/SLQ_J.pdf).

El flujo local de carga ejecutó el extractor real en su proceso acotado. El PDF
público tiene 63 565 bytes y cuatro páginas. La cuarta carece de texto extraíble,
por lo que el estado fue `partial`. Las otras tres produjeron cinco fragmentos y
5 157 caracteres, con página y desplazamiento. Los tres ítems estaban presentes
en los fragmentos de la página 2 (desplazamientos 0 y 1 200) y la página 3
(desplazamiento 0). La API guardó los fragmentos en `project_files.metadata` y
el original byte por byte en el almacenamiento simulado.

El patrón anterior omitía el punto entre el prefijo y los dígitos. Una consulta
compacta o con espacios buscaba un código en cada fragmento y descartaba los que
solo contenían la forma con punto. Al fallar los tres códigos juntos, el backend
terminaba el turno antes de invocar al proveedor. El índice recorre todos los
fragmentos conservados en `metadata.fragments`. La vista previa de 16 000
caracteres es independiente y sirve de respaldo para el legado sin fragmentos.
La selección para el proveedor se aplica después de buscar y conserva los límites
de diez fragmentos y 12 000 caracteres. Una regresión multipágina comprueba que
una consulta larga en varios formatos recupera los ítems situados después de
la vista previa, incluso cuando uno de los códigos solicitados no existe.

El buscador y el validador de afirmaciones usan ahora la misma equivalencia entre
formas compactas, con punto y con espacios. La equivalencia conserva ceros y sufijos,
y el validador comprueba la evidencia de cada fragmento por separado para los
códigos. La API local, con Auth, almacenamiento y proveedor simulados, recuperó
los tres enunciados de la copia pública en una consulta con grafías mixtas. Con el
permiso activo persistió `share_instrument_text=true` y pasó cuatro de cinco
fragmentos al doble. Con el permiso desactivado registró `not_authorized` y el
doble recibió cero invocaciones. El original público quedó fuera de Git.

«Nueva conversación» persistía si el turno era de comprensión sin finalidad o si
la consulta documental terminaba en una respuesta local antes de generar un título.
El backend asigna un título provisional al completar la próxima consulta informativa
o acción de comprensión y reutilización. Los títulos manuales siguen teniendo
prioridad. Una conversación antigua que solo tiene archivos adjuntos toma el título
al completar ese turno. Los eventos de asociación muestran «Archivos asociados».
Las tarjetas, registros y revisión de variables reservan «hoja» para XLSX, y los
proveedores reciben la instrucción de describir los CSV como tablas de registros y
columnas. Se mantienen las referencias técnicas del plan y el rediseño índigo/lavanda.

### Repetir con el PDF de la conversación

1. En **Archivos asociados**, descarga el instrumento `SLQ_J.pdf` original. Compara
   su SHA-256 mediante `Get-FileHash -Algorithm SHA256` con el de la copia pública
   usada en esta prueba, `ef7cb3ff1f9a81031e75425fc5d062341cc6d41fceded62439c0b68f26991e15`.
   Si el hash difiere, usa el archivo descargado como entrada del siguiente paso.
2. En la rama `fix/estabilizacion-instrumentos-ux-sesion9`, entra a `backend`. Ajusta
   la ruta del PDF y ejecuta este diagnóstico local. Usa el flujo HTTP real de carga
   y turno con el doble de proveedor y almacenamiento de las pruebas.

   ```powershell
   $env:STATIA_VALIDATION_PDF = 'C:\ruta\a\SLQ_J.pdf'
   @'
   import os
   import sys
   from pathlib import Path

   sys.path.insert(0, 'tests')
   from test_chat_api import api, attach_dataset, new, reply, turn
   from app.services.instrument_context import codes

   pdf = Path(os.environ['STATIA_VALIDATION_PDF'])
   fixture = api.__wrapped__()
   client, store, provider = next(fixture)
   try:
       path = new(client, store)
       assert turn(client, path, action='instrument_yes').status_code == 200
       upload = client.post(path + '/files', files={'file': (pdf.name, pdf.read_bytes())},
                            data={'file_role': 'instrument'})
       assert upload.status_code == 201, upload.text
       metadata = upload.json()['metadata']
       assert turn(client, path, action='instruments_done').status_code == 200
       attach_dataset(client, path)
       query = ('Recupera las preguntas del instrumento con sus opciones y paginas. '
                'Busca SLQ030, SLQ.050 y SLQ 120.')
       assert turn(client, path, content=query, share_instrument_text=False).status_code == 200
       assert not provider.contexts
       provider.replies.append(reply(response='Los extractos incluyen SLQ.030, SLQ050 y SLQ 120.'))
       result = turn(client, path, content=query, share_instrument_text=True)
       assert result.status_code == 200, result.text
       assert len(provider.contexts) == 1
       context = provider.contexts[0][0]
       assert context['instrument_text_authorized'] is True
       assert store.data['chat_requests'][-1]['payload']['share_instrument_text'] is True
       evidence = next(item['instrument'] for item in context['files'] if 'instrument' in item)
       print(metadata['extraction_status'], metadata['pages'], evidence['fragments_available'])
       for code in ('slq030', 'slq050', 'slq120'):
           matches = [item for item in evidence['fragments_shared'] if code in codes(item['text'])]
           assert matches, code
           print(code, [(item['location'], item['offset']) for item in matches])
   finally:
       fixture.close()
   '@ | .\.venv\Scripts\python -
   Remove-Item Env:STATIA_VALIDATION_PDF
   ```

3. En la copia pública se esperan `slq030` y `slq050` en la página 2 y `slq120`
   en la 3. Contrasta los enunciados y las opciones con el PDF. Para comprobar
   la pantalla autenticada en un entorno de pruebas con proveedor simulado,
   abre la conversación, selecciona Gemini en el simulador, activa **Lectura
   autorizada**, y envía la consulta como un mensaje nuevo. Comprueba que el
   `POST /turns` lleva `share_instrument_text: true` y que la nueva respuesta
   tiene `instrument_retrieval` en estado `matched` y ubicaciones en las páginas
   2 y 3. Repite con `SLQ030`, `SLQ.030` y `SLQ 030` como consultas separadas.
   En la conversación original, deja pendiente la prueba de respuesta de Gemini
   real para cuando se autorice. Este seguimiento usó un dataset sintético para
   el turno HTTP, sin acceder al CSV privado ni ejecutar cálculos.

### Comprobaciones del seguimiento

- Backend dirigido con instrumentos, tesis, planificación, API de chat, Gemini,
  Terra, Excel y estadística. Pasaron 324 pruebas y se omitió la comprobación
  histórica A/D por falta de su evidencia local. Tras el último ajuste en el
  validador, volvieron a pasar las suites de instrumentos y tesis (63 pruebas).
- Frontend completo. Pasaron 131 pruebas. TypeScript, lint, formato y build
  aprobados. Persiste el aviso de Vite por el tamaño del chunk principal.
- Ruff y el control `check_analysis_quality.py` aprobaron el código de producción
  tocado y el conjunto que controla el proyecto. Una revisión adicional de estilo
  sobre `test_planning.py` señaló infracciones preexistentes fuera de ese conjunto.
- El diagnóstico local anterior se ejecutó con la copia pública y comprobó las
  páginas y desplazamientos. El entorno autenticado y Gemini real quedan
  pendientes de validación externa.

## 1. Causas raíz identificadas

- El recuperador exigía encontrar los códigos de la consulta dentro de tokens
  léxicos exactos. Las variantes de presentación con espacios, guiones o guiones
  bajos podían descartar texto que sí se había extraído correctamente. Los casos
  sintéticos iniciales reprodujeron siete fallos de diez comprobaciones nuevas:
  seis de recuperación por variantes de códigos y uno de diagnóstico sin texto.
- La tokenización incluía guiones dentro de las palabras y no normalizaba formas
  equivalentes de códigos. También faltaba normalización de compatibilidad Unicode.
- La selección podía consumir todos los cupos con coincidencias antes de incluir
  las alternativas contiguas. En Word, una tabla puede producir varios fragmentos,
  uno por párrafo/celda; recuperar la pregunta no garantizaba recuperar sus opciones.
- Una búsqueda sin coincidencias y una extracción vacía recibían el mismo mensaje,
  que sugería OCR sin haber demostrado que esa fuera la causa. El retorno estático
  ocurría **antes de invocar al proveedor**; no era un fallo atribuible a Gemini.
- El enrutamiento reconocía únicamente códigos compactos, y el estado de carga de
  instrumentos podía interceptar una consulta por código antes de clasificarla.
- Las consultas documentales/metodológicas se excluían correctamente de la finalidad
  estadística, pero con ello también perdían su título sugerido. Un chat dedicado
  exclusivamente al documento podía seguir como «Nueva conversación».
- El consentimiento estaba alejado del adjunto. El frontend lo transmitía como
  bandera de cada turno; la revisión no encontró evidencia de que el backend
  ignorara una bandera verdadera. Había, en cambio, una experiencia poco visible
  y un mensaje de cambio de proveedor que sugería conservar autorizaciones que
  realmente debían renovarse.

**Límite del diagnóstico:** no se proporcionó el PDF original `SLQ_J.pdf` ni trazas
del turno fallido en este checkout. No se afirma haber reproducido exactamente ese
archivo o identificado su maquetación concreta. Se reprodujeron y corrigieron
causas generales verificables del mismo falso negativo. No se presupone que el
original necesite OCR, ni se lo descargó de una fuente ajena para sustituirlo.

## 2. Corrección de recuperación PDF/DOCX

La extracción real existente conserva texto, fragmentos, ubicaciones y advertencias;
no se reemplazó pypdf ni el lector DOCX seguro. Las regresiones usan PDF y paquetes
DOCX reales generados en memoria, con estructuras educativas, comunitarias,
administrativas y de evaluación, sin documentos de usuarios.

- Búsqueda por palabras, frases tokenizadas, encabezados y códigos.
- Normalización Unicode de compatibilidad, mayúsculas y acentos para búsqueda.
- Equivalencias acotadas de separadores entre prefijos alfabéticos y números,
  incluidos saltos de línea. Se conservan ceros y sufijos: no se aproxima un código
  ausente a otro parecido ni se confunde `R12` con `R120` o `R12A`.
- Prioridad por códigos solicitados y por documentos, seguida de vecindad para
  alternativas, continuaciones y celdas. Los límites globales siguen vigentes.
- Las evidencias compartidas conservan su texto original. El validador admite la
  referencia canónica solo si existe esa evidencia y mantiene la comprobación de
  citas literales y la prohibición de afirmar una lectura completa.
- Ubicaciones DOCX comprensibles: cuerpo, encabezado, pie o notas y párrafo. Las
  rutas XML originales siguen intactas en la metadata histórica; no se presentan
  como fuente habitual del mensaje.
- Diagnósticos distintos para ausencia de instrumentos, falta de autorización,
  extracción vacía y búsqueda sin coincidencias. No encontrar una coincidencia
  no demuestra que el contenido no exista en el original.

## 3. Comportamiento del consentimiento

Al asociar instrumentos sin una decisión vigente aparece una confirmación contextual
con el título solicitado, explicación del uso de fragmentos, proveedor y documentos
afectados. Las acciones son «Permitir consultar fragmentos» y «Continuar sin compartir».
Cerrar el diálogo sin una elección previa equivale a continuar sin compartir.

La elección no se activa automáticamente. Se mantiene en memoria por proyecto,
conversación y proveedor mientras permanezca montado el asistente. No se vuelve a
preguntar en cada mensaje. Añadir un instrumento, cambiar de proveedor, recargar o
salir y volver al asistente requiere una nueva elección. No se añadió persistencia
permanente ni una tabla de permisos.

Una franja junto al compositor muestra «Lectura autorizada» o «Contenido no
compartido» y permite cambiar la elección. Las tarjetas muestran el estado de
extracción informado por el servidor; una autorización no implica que el proveedor
haya leído todo el archivo. La siguiente solicitud lleva la bandera correcta.
Las cargas mixtas no generan comprensión automática antes de resolver la elección.
Autorizar no reenvía ni reintenta mensajes anteriores.

Los reintentos conservan su UUID y payload. Mientras haya uno pendiente se bloquean
los cambios de las opciones de compartición; «Escribir otra solicitud» permite
descartarlo y cambiar opciones para una solicitud nueva. Los mensajes ya compartidos
siguen formando parte del historial, como informa la interfaz.

## 4. Arquitectura y seguridad documental

Flujo: original privado → extracción acotada → fragmentos persistidos con ubicación
→ índice léxico temporal por consulta → selección acotada → contexto del proveedor
autorizado → validación de evidencias → respuesta con fuentes.

No se añadió un índice remoto, embeddings, OCR, infraestructura ni llamadas de red
para recuperar documentos. Se conservan los límites existentes: 80 páginas PDF,
240 000 caracteres y 600 fragmentos de extracción; por turno, diez fragmentos y
12 000 caracteres entre todos los instrumentos. También se conservan los controles
de tamaño, ZIP/XML, recursos externos, objetos activos, cifrado, proceso hijo,
tiempo y memoria. DOC antiguo sigue requiriendo conversión segura.

Los originales y la metadata histórica no se reescriben. El fallback autorizado de
instrumentos antiguos sigue siendo temporal. Storage continúa privado; Auth, JWT
del usuario, clave publicable, RLS y aislamiento no se modificaron. No se ejecutan
macros, código ni instrucciones incrustadas; no se descargan recursos externos.

## 5. Nueva identidad visual

La identidad cambia globalmente de verde a índigo, lavanda y gris perla mediante
tokens CSS. Abarca login, registro, dashboard, proyectos, navegación, formularios,
diálogos, Contexto, Datos, chat, propuestas y Resultados. Se conserva el icono de
marca existente, con nueva aplicación de color. No hay biblioteca visual nueva.

Las superficies son claras, las sombras discretas y los paneles más compactos.
El verde queda para estados de éxito/confirmación; rojo y ámbar conservan sus usos
semánticos. Las notas informativas usan índigo suave y texto explícito.

## 6. Paleta y tokens definitivos

| Token | Valor | Uso |
| --- | --- | --- |
| `--primary` | `#4F46E5` | Acciones y marca |
| `--primary-strong` | `#3730A3` | Hover y texto de énfasis |
| `--lavender` | `#8B5CF6` | Acentos y foco |
| `--lavender-strong` | `#6D28D9` | Marca y acentos legibles |
| `--lavender-soft` | `#DDD6FE` | Contraste en acceso oscuro |
| `--surface-lavender` | `#F5F3FF` | Franja de autorización |
| `--surface-soft` | `#EEF2FF` | Mensajes del usuario y selección |
| `--canvas` | `#F8FAFC` | Fondo |
| `--surface` | `#FFFFFF` | Tarjetas |
| `--ink` | `#1E293B` | Texto principal |
| `--muted` | `#5F6E85` | Texto secundario accesible |
| `--border` | `#E2E8F0` | Bordes |
| `--border-strong` | `#C7D2FE` | Selección y controles |
| `--success` | `#166534` | Éxito |
| `--danger` | `#B91C1C` | Error/peligro |
| `--warning` | `#92400E` | Advertencia |
| `--auth-bg` | `#242052` | Superficie oscura de acceso |

Radios reutilizables de 8/12/16 px, escala de espacio 4/8/12/16/24/32 px y dos
sombras compartidas. La tipografía conserva Segoe UI/system-ui, sin descargas de
fuentes. El gris secundario propuesto se ajustó: `#64748B` sobre `#EEF2FF` daba
4,26:1; `#5F6E85` da 4,63:1. Principal sobre blanco: 6,29:1. Estas comprobaciones
puntuales no constituyen una certificación completa WCAG.

## 7. Mejoras del chat

- Tres zonas en escritorio; historial temporal/plegable en tablet y móvil.
- Encabezado compacto, proveedor visible y acciones con etiquetas accesibles.
- Mensajes con ancho ajustado al contenido, identidad del autor y tratamiento
  diferente de eventos del sistema, advertencias y errores.
- «Información del sistema» sustituye la etiqueta técnica de acción determinista.
  Un mensaje histórico sin proveedor acreditado se presenta como Statia; nunca se
  atribuye al proveedor seleccionado actualmente. El modelo acreditado permanece
  en metadata y en la información emergente de procedencia.
- Compositor accesible, textarea ajustable, adjunto visible, estado de procesamiento,
  Enter/Shift+Enter/IME e idempotencia conservados.
- Distinción visible de formatos de instrumentos y datasets. Archivos asociados
  abiertos inicialmente, con tarjetas compactas y detalles/descarga expandibles.
- Títulos derivados de nuevas consultas documentales cuando el nombre sigue siendo
  provisional. No hay renombrado masivo ni modificación de títulos manuales.

## 8. Propuestas, resultados y gráficos

Las propuestas mantienen objetivo, procedimiento y justificación visibles; dataset,
variables, supuestos, limitaciones y productos quedan en secciones revisables. La
aceptación/rechazo conserva sus servicios y validaciones. Los planes aceptados se
pueden desplegar, sin ejecutar automáticamente.

Resultados usa nombres legibles de métodos, tablas con desplazamiento propio,
advertencias abiertas cuando existen y metadatos técnicos plegables. Se evita repetir
el resultado seleccionado en el listado y se conservan los anuncios accesibles de
estado. Las rutas de imágenes se sustituyen por títulos del procedimiento y número
de gráfico; siguen disponibles en la trazabilidad técnica.

«Ampliar gráfico» abre el mismo blob privado original, con desplazamiento por teclado
y tamaño nativo. No descarga otra copia, no llama a ejecución ni recalcula. La prueba
de regresión verifica una consulta al artefacto, ausencia de ejecución e inmutabilidad
del resultado. Los PNG históricos mantienen sus colores, ejes, categorías y orden;
una imagen rasterizada con etiquetas largas no puede remaquetarse solo con CSS.

No se alteraron los cálculos, denominadores, valores presentes, ausencias físicas ni
categorías sustantivas/no sustantivas. La clasificación semántica optativa de Sesión 08
continúa sin aplicar reglas universales a textos como Unknown o None.

## 9. Navegación, responsive y revisión visual

Se reutilizaron Vite en `localhost:5173` y API en `127.0.0.1:8001`, que ya estaban
activos; no se interrumpieron ni duplicaron. `/health` respondió 200.

Se inspeccionó la aplicación mediante navegador local, con los componentes reales
y servicios sintéticos aislados de `frontend/visual/index.html`. La entrada bloquea
fetch de servicios; solo permite explícitamente leer el PNG sintético local para
presentarlo como artefacto. No usa una sesión real ni datos de investigadores y no
se incluye en el build público. Su banner identifica siempre la simulación.

| Tamaño | Revisión realizada |
| --- | --- |
| 1440 × 900 | Acceso, dashboard, formulario de proyecto, chat de tres zonas y consentimiento |
| 1280 × 800 | Chat, mensajes, propuesta/plan aceptado, Contexto y Resultados |
| 820 × 1180 | Contexto, Datos y chat con historial oculto, compositor y navegación |
| 390 × 844 | Dashboard, registro, chat, consentimiento, plan aceptado, Contexto, tablas y gráfico ampliado |

Iteraciones verificadas: reducción del encabezado móvil, eliminación de títulos
repetidos, texto secundario con mayor contraste, navegación móvil compacta también
fuera del chat y tarjeta de revisión confirmada de Contexto con ayuda secundaria
plegable. Sus controles de edición, revisión, importación y conflictos se preservan.

La revisión encontró que una tabla de 600 px ampliaba toda la página móvil hasta
655 px. Se corrigió el mínimo intrínseco del grid de Resultados. Comprobación final:
viewport 390 px, página 375 px (descontando scrollbar), tabla visible 300 px y contenido
600 px con scroll interno. En chat móvil: página 390 px y borde inferior del compositor
837,2 px dentro de 844 px. En tablet: página 820 px y compositor dentro de 1180 px.

Capturas sintéticas locales, excluidas de Git en `.local/session9/`: `chat-desktop.jpg`,
`chat-laptop.jpg`, `chat-tablet.jpg`, `chat-mobile.jpg`, `plan-aceptado.jpg`,
`datos-tablet.jpg`, `contexto-mobile.jpg`, `resultados-mobile.jpg`, `login-desktop.jpg`.
La figura sintética versionada se generó con el módulo Charts existente, sin cambiarlo.
Se comprobó igualdad binaria entre workspace e índice Git; `.gitattributes` evita
que normalizar saltos de línea corrompa su firma PNG en otros checkouts.

No se probó un teléfono físico, teclado virtual real, lector de pantalla, Safari o
Firefox. La revisión responsive fue en viewports de un navegador de escritorio.

## 10. Archivos modificados

```text
.gitattributes
.gitignore
backend/app/services/conversation.py
backend/app/services/instrument_context.py
backend/tests/test_instruments.py
backend/tests/test_thesis_stability.py
docs/ARCHITECTURE.md
docs/SESSION9_PLAN.md
docs/SESSION9_REPORT.md
docs/SETUP.md
frontend/src/components/AnalysisResultCard.tsx
frontend/src/components/AnalysisResults.tsx
frontend/src/components/AssistantProviderSelector.tsx
frontend/src/components/ChatComposer.tsx
frontend/src/components/ComponentStates.tsx
frontend/src/components/DatasetCard.tsx
frontend/src/components/InstrumentAccess.tsx
frontend/src/components/ProposalCard.tsx
frontend/src/components/StatisticalChat.tsx
frontend/src/components/ThesisContext.tsx
frontend/src/index.css
frontend/src/lib/analysis-methods.ts
frontend/src/lib/assistant-provider.ts
frontend/src/lib/instrument.ts
frontend/src/pages/AuthPage.tsx
frontend/src/pages/Workspace.tsx
frontend/src/test/analysis.test.tsx
frontend/src/test/chat.test.tsx
frontend/src/test/fixtures/frequencies.synthetic.png
frontend/src/test/providers.test.tsx
frontend/src/test/visual-preview.tsx
frontend/visual/index.html
```

## 11. Commits locales

- `5eb2616` — `docs(sesion09): registrar plan de estabilización y alcance`.
- `f0be1dc` — `fix(instrumentos): recuperar referencias equivalentes y diferenciar diagnósticos`.
- `c2a7ac0` — `feat(interfaz): renovar identidad y aclarar el flujo documental`.
- `docs(sesion09): documentar validaciones y límites de la entrega` — commit final
  de este informe; su hash se consulta con `git log -1 --oneline`.

Identidad Git existente, sin coautores artificiales. Todos son locales. Árbol Git
limpio verificado después del commit de cierre; evidencia de pruebas y capturas
permanece ignorada, sin incorporarse al historial.

## 12. Pruebas aprobadas

| Comprobación | Resultado |
| --- | --- |
| Backend general en 29 procesos aislados | 647 aprobadas, 1 omitida, 0 fallidas |
| Regresión documental/API final | 67 aprobadas: 34 instrumentos, 21 tesis y 12 chat |
| Backend consolidado final | **650 aprobadas, 1 omitida**, sin fallos pendientes |
| Frontend general, 12 archivos | **130 aprobadas** |
| Revalidación posterior de acceso/proveedores | 48 aprobadas |
| Revalidación del último ajuste visual de Contexto | 9 aprobadas |
| PostgreSQL/PGlite local | **6 suites aprobadas**: proyectos, chat, proveedores, resultados, Contexto y DOCX |
| Configuración de producción frontend | 2 aprobadas |
| TypeScript estricto, oxlint, Prettier y build | Aprobados al cierre; incluye la entrada sintética y su HTML en las comprobaciones aplicables |
| Calidad Python | Lint y formato aprobados, 70 archivos; lint adicional de conversación aprobado |
| `pip check` | Sin dependencias rotas |
| Diff/secretos | Sin errores de whitespace ni patrones de claves/JWT/llaves privadas en líneas añadidas |
| Inmutabilidad de alcance | Sin diff en motor estadístico, migraciones, lockfiles, requisitos o entornos |
| Aislamiento de revisión visual | Sin entrada, textos de simulación ni fixtures sintéticas en `dist` |

El consolidado backend sustituye únicamente las 31 pruebas iniciales de instrumentos
por su revisión final de 34 tras añadir Unicode/tablas y códigos partidos en línea.
La última regresión de 67 también revalida el enrutamiento, títulos y diagnósticos.
No se presenta como una segunda pasada general completa. Las pruebas estadísticas
existentes ejecutaron el motor Python real con datos sintéticos: descriptivos,
correlaciones, Welch e integrales; los proveedores/Auth/Storage de los recorridos
HTTP son simulados. PGlite emula Auth/Storage localmente; no valida Supabase remoto.

Cobertura nueva: códigos equivalentes en ambos formatos, acentos/palabras, búsqueda
sin coincidencias, ausencia de texto, identificadores cercanos no equivalentes,
Unicode de ancho completo, salto de línea y tabla Word con seis opciones separadas.
Se conserva la cobertura de multipágina, preguntas tardías, múltiples instrumentos,
archivos dañados/cifrados, ZIP/XML inseguros y contenido malicioso como dato.

La primera prueba frontend posterior al cambio del selector requería el nombre
técnico del modelo dentro de la opción. Se actualizó al diseño compacto conservando
la prueba de procedencia acreditada. Los errores intermedios de tipado/formato y
la aserción que confundía recurso técnico oculto con recurso eliminado se corrigieron;
no se dejaron comprobaciones fallidas ni se ocultó trazabilidad para pasar pruebas.

## 13. Pruebas omitidas

Una omisión heredada: `test_legacy_a_d_bytes_and_converter_unchanged_without_import_or_execution`
de `test_terra_diagnostic.py`, por ausencia del archivo local no versionado
`backend/test_terra_statia_env.py`. No se inventó ni regeneró esa evidencia.

Por restricción expresa no se ejecutaron proveedores reales, Supabase remoto,
migraciones remotas, despliegues o pruebas en Render/Vercel. Los seguimientos T1
y T2 usaron archivos públicos sin consultar objetos privados. No se ejecutó producción con
credenciales de despliegue ni se intentó autenticar una cuenta desde el navegador.

## 14. Regresiones y validaciones pendientes

Sin regresiones conocidas de alta gravedad al cierre. Quedan la validación del PDF
original, otros documentos reales con maquetación compleja, respuestas reales de
ambos proveedores, aislamiento con dos cuentas reales y dispositivos/navegadores
adicionales. El desbordamiento visual detectado se corrigió y volvió a inspeccionarse.

## 15. Dependencias nuevas

Ninguna. Manifiestos y lockfiles sin cambios. Se reutilizan bibliotecas existentes,
incluidos pypdf, defusedxml, React, iconos y Matplotlib para la fixture sintética.

## 16. Migraciones nuevas

Ninguna. No se modificó ni ejecutó la migración 009. Según el usuario, ya fue aplicada
manualmente al Supabase de validación. Antes de futuros despliegues se debe conciliar
ese hecho con el historial de migraciones y comprobar el destino. No se presenta
esa confirmación del usuario como una inspección remota de esta sesión.

## 17. Variables de entorno nuevas

Ninguna. No se leyeron valores secretos para mostrarlos ni se modificaron credenciales
o archivos de entorno. No hay claves administrativas nuevas ni uso de `service_role`.

## 18. Riesgos y limitaciones conocidos

- La búsqueda es léxica y acotada: no traduce conceptos entre idiomas, no resuelve
  sinónimos arbitrarios ni interpreta texto de imágenes. Una referencia fuera de
  los límites de extracción o compartición puede no recuperarse.
- La normalización de separadores permite buscar variantes de presentación; la
  identidad semántica de ítems con convenciones ambiguas debe contrastarse con sus
  fragmentos y el original. No se infieren correspondencias con columnas del dataset.
- La extracción PDF puede perder orden de tablas/columnas. Word conserva ubicaciones
  por parte/párrafo, no páginas estables ni numeración automática fiable.
- El consentimiento no es permanente: volver a montar el asistente requiere elegir
  de nuevo. Una revocación limita turnos futuros, no retira información ya compartida.
- Los gráficos históricos son imágenes inmutables; la ampliación facilita leerlos,
  pero no corrige su maquetación ni cambia categorías. No se regeneraron resultados.
- Persisten avisos existentes de Starlette/TestClient y del chunk base Vite de
  aproximadamente 500,98 kB. No se alteró el empaquetado para silenciar el aviso.
- Las capturas prueban presentación local con simulaciones identificadas; no son
  evidencia de Gemini, Terra, Auth o Storage reales ni una auditoría WCAG completa.

## 19. Comandos locales

Reutilizar servidores si ya están activos. Desde la raíz, en terminales separadas:

```powershell
Set-Location backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8001
```

```powershell
Set-Location frontend
npm run dev
```

Comprobaciones desde `backend`:

```powershell
.\.venv\Scripts\python -m pytest tests/test_instruments.py tests/test_thesis_stability.py tests/test_chat_api.py -q
.\.venv\Scripts\python scripts/check_analysis_quality.py
.\.venv\Scripts\python -m pip check
```

Desde `frontend`: `npm test`, `npm run typecheck`, `npm run lint`,
`npm run format:check`, `npm run build`, `npm run test:deployment` y
`npx prettier --check visual/index.html`. Desde `supabase`: `npm test` solo ejecuta
las suites locales PGlite. No ejecutar scripts diagnósticos con `--live`.

Vista sintética local: `http://localhost:5173/visual/index.html?screen=dashboard`;
también admite `asistente`, `contexto`, `datos`, `resultados`, `login`, `registro`.
No usar esa entrada para datos reales ni confundirla con la aplicación autenticada.

## 20. Plan de validación manual con instrumentos reales

1. En el entorno autorizado, confirmar que 009 y el historial de migraciones están
   conciliados. No volver a ejecutarla automáticamente. Verificar bucket privado.
2. Abrir un proyecto de tesis con Contexto confirmado y otro General. Confirmar
   revisión, edición, deshacer, revisión antes de guardar e importación JSON. En
   dos pestañas provocar un conflicto y verificar que se conserva el borrador.
3. Asociar el PDF original del incidente y consultar sus códigos/preguntas sin
   autorizar. Verificar ausencia de contenido enviado y diagnóstico de permiso.
   Autorizar, enviar una consulta nueva y contrastar preguntas, alternativas y
   páginas con el original. No considerar aprobada esa comprobación todavía.
4. Repetir con DOCX de otra disciplina, párrafos y tablas, y PDF largo/multipágina.
   Consultar encabezados, frases y referencias con separadores; probar también
   un código inexistente, documento sin texto y extracción parcial. Distinguir
   los tres diagnósticos y comprobar que no se inventan opciones ni citas.
5. Descargar originales y contrastar sus hashes. Probar carga mixta de instrumento
   y CSV/XLSX/JSON; confirmar roles, elección de permiso, perfil y advertencias.
   En Excel recorrer hojas sin cambiar la hoja congelada del plan.
6. Cambiar proveedor y volver a autorizar; revocar y enviar otra consulta. Conservar
   mensajes, revisar metadatos y comprobar el UUID/payload en reintentos. No debe
   aparecer un mensaje duplicado ni reenviarse una consulta al pulsar autorizar.
7. Con autorización específica futura, validar Gemini y Terra reales por separado:
   confirmar que reciben fragmentos verificables, sus fuentes y el Contexto vigente.
   Registrar los fallos reales sin sustituirlos por respuestas simuladas.
8. Revisar/aceptar un descriptivo, una correlación y ANOVA de Welch sin cambiar la
   semántica del plan. Ejecutar solo tras confirmar decisiones; cotejar tablas,
   supuestos, denominadores, PNG y ZIP. Abrir resultados previos sin recalcularlos.
9. Con dos usuarios reales, verificar RLS y acceso a proyectos, conversaciones,
   perfiles, originales y artefactos. No usar credenciales administrativas.
10. Repetir el recorrido autenticado en escritorio, tablet y teléfono, con teclado,
    mensajes largos, tablas anchas, ampliación de gráficos y teclado virtual. Revisar
    lector de pantalla y navegadores adicionales antes de certificar accesibilidad.

## 21. Estado final

**APTO para validación manual controlada**, con las limitaciones externas descritas.
Recuperación generalizable, consentimiento contextual, identidad global y revisión
visual local implementados; motor estadístico, resultados históricos, originales,
seguridad y lógica multihoja conservados. No equivale a aprobación con archivos reales
o proveedores reales y no autoriza merge, push ni despliegue.
