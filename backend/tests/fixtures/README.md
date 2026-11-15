# Palmer Penguins (fixture público)

`penguins.csv` se conserva sin transformar desde [allisonhorst/palmerpenguins](https://github.com/allisonhorst/palmerpenguins/blob/main/inst/extdata/penguins.csv).
SHA-256: `f204db2c753b0937caac3cb35258562c14f073e4bbc76be24b4c51ce22767a93`.
Datos de Kristen Gorman y Palmer Station LTER; distribución del paquete por Allison Horst, Alison Hill y Kristen Gorman. Licencia de los datos: [CC0](https://allisonhorst.github.io/palmerpenguins/#license).

Referencia independiente de lectura: `csv.DictReader`, interpretando literalmente `NA` como ausente según la documentación del dataset. Son 344 filas, 8 columnas, 2 ausencias en cada una de las cuatro medidas y 11 en `sex` (19 celdas en total). El perfilado prudente predeterminado reconoce las 8 ausencias numéricas y conserva los 11 `NA` de texto como ambiguos. Con la decisión explícita `missing_value_overrides={'sex': ['NA']}` coincide con la referencia en las 19 celdas. No se aplica esa decisión al resto de los datasets ni se modifica el fixture.
