"""Lint y formato del código nuevo del motor/resultados, sin adoptar reglas globales del equipo."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "app/services/instruments.py",
    "app/services/instrument_worker.py",
    "app/services/instrument_context.py",
    "app/services/reply_contract.py",
    "tests/test_instruments.py",
    "tests/test_thesis_stability.py",
    "app/services/workbook.py",
    "tests/test_excel_multihoja.py",
    "app/services/descriptive_feasibility.py",
    "tests/test_hotfix_final.py",
    "app/services/data_preview.py",
    "app/services/interpretation_guards.py",
    "tests/test_session6b.py",
    "app/services/variable_types.py",
    "tests/test_session6.py",
    "tests/test_inferential_products.py",
    "tests/test_requested_scope.py",
    "app/services/requested_scope.py",
    "tests/test_plan_capabilities.py",
    "tests/test_provider_rollback.py",
    "tests/helpers",
    "app/services/provider_runtime.py",
    "app/services/openai_provider.py",
    "app/services/providers.py",
    "app/services/plan_capabilities.py",
    "tests/test_openai_provider.py",
    "tests/test_provider_selection.py",
    "app/api/research_context.py",
    "app/models/research_context.py",
    "app/services/research_context.py",
    "app/core/config.py",
    "app/main.py",
    "tests/test_app.py",
    "tests/test_research_context.py",
    "tests/test_gemini_resilience.py",
    "tests/test_gemini_diagnostic.py",
    "tests/test_terra_diagnostic.py",
    "app/api/analysis.py",
    "app/models/analysis.py",
    "app/services/statistics",
    "app/services/analysis.py",
    "app/services/analysis_context.py",
    "app/services/analysis_exports.py",
    "app/services/analysis_worker.py",
    "app/services/execution_preparation.py",
    "tests/test_automatic_preparation.py",
    "tests/test_execution_uncertainty.py",
    "tests/test_integral_execution.py",
    "tests/test_result_conversation.py",
    "tests/test_statistics.py",
    "tests/test_statistics_additional.py",
    "tests/test_analysis_api.py",
    "scripts",
]

if __name__ == "__main__":
    fix = "--fix" in sys.argv
    for args in [
        ["check", "--isolated", "--select", "E4,E7,E9,F,I", *(["--fix"] if fix else []), *TARGETS],
        ["format", "--isolated", "--line-length", "120", *([] if fix else ["--check"]), *TARGETS],
    ]:
        subprocess.run([sys.executable, "-m", "ruff", *args], cwd=ROOT, check=True)
