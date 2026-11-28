"""Reconocimiento conservador de nombres en planes v1, contrastado con catálogo/datos.

Plan v1 almacena el método como texto. No interpreta requisitos ni inventa un
contrato del proveedor; varios nombres requieren una decisión explícita.
"""

import re
import unicodedata

ALIASES = {
    "descriptive": r"\bdescriptiv\w*|\bfrecuencias\b",
    "pearson": r"\bpearson\b",
    "spearman": r"\bspearman\b",
    "student_t": r"\bstudent(?:_t)?\b",
    "welch_t": r"\bwelch(?:_t)?\b",
    "anova": r"\banova\b",
    "paired_t": r"\bt (?:de student )?(?:pareada|para (?:muestras |datos )?(?:paread[ao]s|dependientes))\b|\bpaired_t\b",
    "mann_whitney": r"\bmann[–—\s_-]*whitney\b",
    "wilcoxon": r"\bwilcoxon\b",
    "kruskal": r"\bkruskal\b",
    "chi_square": r"\bchi[–—\s_-]*(?:cuadrado|square)\b|\bchi[2²]\b",
    "fisher_exact": r"\bfisher(?:_exact)?\b",
}
WELCH_ANOVA = re.compile(r"\b(?:anova(?: de)? (?:\(\s*)?welch|welch anova|welch_anova|f de welch)\b")
CLASSIC_OR_WELCH = re.compile(r"\banova clasic[oa] o (?:de )?welch\b")
UNSUPPORTED_TERMS = (
    "regresion",
    "logistica",
    "games-howell",
    "tukey",
    "medidas repetidas",
    "ancova",
    "manova",
    "permutacion",
    "bootstrap",
)


def supported_request(source):
    return not any(term in normalized(source.method) for term in UNSUPPORTED_TERMS)


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(c))


def named_methods(source):
    columns = {normalized(v.column) for v in getattr(source, "variables", ())}
    return methods_in_text(source.method, columns)


def unquote_column_references(text, columns):
    # El formato Markdown también puede delimitar un método o producto.
    return re.sub(r"`([^`]+)`", lambda match: " " if match[1] in columns else match[1], text)


def methods_in_text(text, columns=()):
    text = unquote_column_references(normalized(text), columns)
    text = re.sub(r"\b(?:z de fisher|welch\s*[-–—]\s*holm)\b", "", text)
    text = re.sub(r"(\bchi[–—\s_-]*cuadrado)(?: de)? pearson\b", r"\1", text)
    found = set()
    if CLASSIC_OR_WELCH.search(text):
        found.update({"anova", "welch_anova"})
        text = CLASSIC_OR_WELCH.sub(" ", text)
    if WELCH_ANOVA.search(text):
        found.add("welch_anova")
        text = WELCH_ANOVA.sub(" ", text)
    found.update(code for code, pattern in ALIASES.items() if re.search(pattern, text))
    if "paired_t" in found:
        found.discard("student_t")
    return found
