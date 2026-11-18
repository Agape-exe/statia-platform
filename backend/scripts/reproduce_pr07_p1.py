"""Ejecuta reproducciones sintéticas contra el app real auditado, sin cambiar Git.

No importa credenciales ni contacta proveedores: reutiliza transportes simulados y
datasets sintéticos de las regresiones. El retorno no cero de pytest es esperado
en la revisión auditada, porque las aserciones describen la conducta corregida.
"""

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITED = "d04a67980a414bd85e84449ef624a242ea02e099"


def main():
    archive = subprocess.check_output(["git", "archive", AUDITED, "backend/app"], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="statia-p1-baseline-") as directory:
        target = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(target, filter="data")
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(target / "backend"), str(ROOT / "backend/tests"), str(ROOT / "backend")]
            ),
        }
        for test_file, selection, expected_tests, expected_failures in [
            ("test_inferential_products.py", "mixed_products_validate_prepare_and_are_actually_calculated", 4, 3),
            ("test_requested_scope.py", "explicit_products_cannot_disappear and reduced", 2, 2),
        ]:
            report = target / (test_file + ".xml")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    str(ROOT / "backend/tests" / test_file),
                    "-k",
                    selection,
                    "--tb=short",
                    "--junitxml",
                    str(report),
                ],
                cwd=target,
                env=env,
                check=False,
            )
            if result.returncode != 1:
                raise SystemExit(f"Resultado inesperado en la reproducción histórica: {result.returncode}")
            suite = ET.parse(report).getroot().find("testsuite")
            assert suite is not None
            assert int(suite.attrib["tests"]) == expected_tests
            assert int(suite.attrib["failures"]) == expected_failures
            assert int(suite.attrib["errors"]) == int(suite.attrib["skipped"]) == 0


if __name__ == "__main__":
    main()
