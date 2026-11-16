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
    "student_t": r"\bstudent\b",
    "welch_t": r"\bwelch\b",
    "anova": r"\banova\b",
    "paired_t": r"\bt (?:de student )?pareada\b|\bpaired_t\b",
    "mann_whitney": r"\bmann[–\s_-]*whitney\b",
    "wilcoxon": r"\bwilcoxon\b",
    "kruskal": r"\bkruskal\b",
    "chi_square": r"\bchi[–\s_-]*(?:cuadrado|square)\b|\bchi2\b",
    "fisher_exact": r"\bfisher\b",
}


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(c))


def named_methods(source):
    text = normalized(source.method)
    found = {code for code, pattern in ALIASES.items() if re.search(pattern, text)}
    if "anova" in found and "welch_t" in found:
        found.difference_update({"anova", "welch_t"})
        found.add("welch_anova")
        if re.search(r"\bt\s+(?:de\s+)?welch\b", text):
            found.add("welch_t")
        if re.search(r"\bclasico\b|\bclasica\b", text):
            found.add("anova")
    if "paired_t" in found:
        found.discard("student_t")
    # Literal catalog codes are also accepted in old plans.
    if text in {"welch_anova", "chi_square", "fisher_exact", "student_t", "welch_t", "mann_whitney"}:
        return {text}
    return found
