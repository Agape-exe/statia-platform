"""Medición local reproducible de RSS API + hijo; no usa credenciales ni datos de usuarios.

Desde backend: .venv/Scripts/python scripts/measure_analysis_memory.py
"""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


async def main():
    app = create_app(Settings(_env_file=None))
    parent = psutil.Process()
    baseline = parent.memory_info().rss
    fid = str(uuid4())
    # 400 000 celdas, límite de ejecución por archivo; nombres arbitrarios, sin ramas por dataset.
    columns = [f"medida_{i}" for i in range(19)] + ["grupo"]
    lines = [",".join(columns)]
    for i in range(20000):
        lines.append(",".join([str((i % 997) + j * 0.17) for j in range(19)] + ["A" if i % 2 else "B"]))
    data = ("\n".join(lines) + "\n").encode()
    variables = [
        {"file_id": fid, "sheet": "tabla", "column": name, "role": "group" if name == "grupo" else "outcome"}
        for name in columns
    ]
    plan = {
        "schema_version": 1,
        "title": "Medición sintética de memoria",
        "objective": "Describir medidas sintéticas",
        "variables": variables,
        "procedure": "descriptive",
        "method": "Descriptivos",
        "justification": "Verificar límites",
        "requirements": ["Datos sintéticos"],
        "limitations": ["Medición local, no Render"],
        "expected_outputs": ["Tablas y PNG"],
    }
    spec = {
        "components": [{"source_index": 0, "method": "descriptive", "descriptive_intervals": False}],
        "decisions_confirmed": True,
        "decisions": [
            {"variable": v, "statistical_type": "nominal" if v["role"] == "group" else "continuous"} for v in variables
        ],
    }
    job = {
        "run_id": str(uuid4()),
        "project_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "proposal_id": str(uuid4()),
        "plan": plan,
        "specification": spec,
        "files": [
            {
                "id": fid,
                "original_name": "sintetico.csv",
                "file_type": "csv",
                "metadata": {"selected_sheet": "tabla"},
                "data": base64.b64encode(data).decode(),
            }
        ],
    }
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.services.statistics.worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "MPLBACKEND": "Agg",
        },
    )
    payload = json.dumps(job).encode()
    task = asyncio.create_task(child.communicate(payload))
    peak_child, peak_total = 0, baseline
    start = asyncio.get_running_loop().time()
    try:
        async with asyncio.timeout(45):
            while not task.done():
                try:
                    current = psutil.Process(child.pid)
                    rss = current.memory_info().rss + sum(p.memory_info().rss for p in current.children(recursive=True))
                    peak_child = max(peak_child, rss)
                    peak_total = max(peak_total, parent.memory_info().rss + rss)
                except psutil.NoSuchProcess:
                    pass
                await asyncio.wait({task}, timeout=0.02)
            output, _ = await task
        result = json.loads(output)
        print(
            json.dumps(
                {
                    "platform": sys.platform,
                    "rows": 20000,
                    "cells": 400000,
                    "original_bytes": len(data),
                    "baseline_api_mib": round(baseline / 1048576, 1),
                    "peak_child_mib": round(peak_child / 1048576, 1),
                    "peak_combined_mib": round(peak_total / 1048576, 1),
                    "seconds": round(asyncio.get_running_loop().time() - start, 2),
                    "status": result.get("result", {}).get("status", result.get("error")),
                    "output_bytes": len(output),
                    "app_version": app.version,
                },
                ensure_ascii=False,
            )
        )
        if (
            child.returncode
            or result.get("error")
            or result.get("result", {}).get("status") not in ("completed", "partial")
        ):
            raise SystemExit("La medición no completó un análisis; revisar el contrato o el entorno.")
    finally:
        if child.returncode is None:
            from app.services.analysis_worker import kill_process_tree

            kill_process_tree(child.pid)
            await child.wait()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
