# Palmer Penguins (fixture público)

`penguins.csv` se conserva sin transformar desde [allisonhorst/palmerpenguins](https://github.com/allisonhorst/palmerpenguins/blob/main/inst/extdata/penguins.csv).
SHA-256: `f204db2c753b0937caac3cb35258562c14f073e4bbc76be24b4c51ce22767a93`.
Datos de Kristen Gorman y Palmer Station LTER; distribución del paquete por Allison Horst, Alison Hill y Kristen Gorman. Licencia de los datos: [CC0](https://allisonhorst.github.io/palmerpenguins/#license).

Referencia independiente de lectura: `csv.DictReader`, interpretando literalmente `NA` como ausente según la documentación del dataset. Son 344 filas, 8 columnas, 2 ausencias en cada una de las cuatro medidas y 11 en `sex` (19 celdas en total). El perfilado prudente predeterminado reconoce las 8 ausencias numéricas y conserva los 11 `NA` de texto como ambiguos. Con la decisión explícita `missing_value_overrides={'sex': ['NA']}` coincide con la referencia en las 19 celdas. No se aplica esa decisión al resto de los datasets ni se modifica el fixture.

## Titanic de Seaborn (regresión pública)

`titanic.csv` conserva los bytes de [mwaskom/seaborn-data, commit a29a014](https://github.com/mwaskom/seaborn-data/blob/a29a0141d20e156043ec257a64c8de3b3a03fd6e/titanic.csv). SHA-256: `81787d320d7f7b03df935e91de8bd19e11d45c5bbcab86ef4d4a76dc91b7d4f2`. Lectura independiente con `csv.DictReader`: 891 filas, 15 columnas, 869 celdas vacías (177 edad, 688 cubierta y 2 en cada representación del puerto). El [procesamiento original de Seaborn](https://github.com/mwaskom/seaborn-data/blob/a29a0141d20e156043ec257a64c8de3b3a03fd6e/process/titanic.py) documenta columnas derivadas. Las equivalencias se comprueban en las pruebas; producción no incorpora reglas por sus nombres ni elimina columnas.

`titanic_planning_failures.json` congela dos respuestas estructuradas reales de `gemini-3.5-flash-lite` sobre metadatos de ese fixture, sin muestras ni CSV completo enviados. Los IDs son sintéticos. Son datos de regresión no confiables, **contienen planes inválidos** y nunca se usan como respuestas alternativas de producción. Primera respuesta: el descriptivo promete columnas ausentes de variables; corrección: añade una de ellas y deja otras omitidas. Las pruebas también renombran arbitrariamente todas las columnas y usan un CSV sintético heterogéneo, para detectar dependencias de nombres conocidos.


## Sesión 6 (sintético)

`instrumento_sesion6.pdf`: una página generada localmente con ReportLab, sin datos
personales, con texto extraíble y preguntas sobre horas, tiempo, puntaje y grupo.
Revisado mediante render PNG y extracción pypdf. No representa un instrumento validado.

`regresion_sesion6.csv`: fixture nueva de 45 registros (15 por grupo A/B/C), generada
por aritmética determinista. Sus referencias usan `statistics` y SciPy. No es el
archivo `statia_sesion6_datos_sinteticos.csv` citado en las pruebas manuales; ese
original no fue proporcionado. No atribuirle sus medias, DE ni correlación conocidas.

`session5_system.txt`: literal SYSTEM conservado desde
`1ac0983b768953b7b5b1bc477a6b59b031c6d216:backend/app/services/gemini.py`.
Permite verificar el hash del payload real auditado el 16 de noviembre sin cambiar
la evidencia histórica al evolucionar las instrucciones del proveedor. No se usa
como prompt alternativo ni respuesta de producción.
