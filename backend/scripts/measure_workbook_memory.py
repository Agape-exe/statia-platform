"""RSS de perfilado multihoja junto a la API cargada, con datos sintéticos locales."""

import io
import json
import sys
import threading
import time
from pathlib import Path

import psutil
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.profiling import inspect_file  # noqa: E402


def main():
    app = create_app(Settings(_env_file=None))
    book, output = Workbook(write_only=True), io.BytesIO()
    # Cuatro tablas independientes, 400 000 celdas de registros en total.
    for index in range(4):
        sheet = book.create_sheet(f"Mediciones {index}")
        sheet.append([f"medida {i}" for i in range(20)])
        for row in range(5000):
            sheet.append([row * 0.37 + column * 0.11 for column in range(20)])
    book.save(output)
    book.close()
    data = output.getvalue()
    process, stop = psutil.Process(), threading.Event()
    baseline = peak = process.memory_info().rss

    def monitor():
        nonlocal peak
        while not stop.wait(0.01):
            peak = max(peak, process.memory_info().rss)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    start = time.monotonic()
    monitor_thread.start()
    try:
        metadata = inspect_file("sintético.xlsx", data, "dataset", app.state.settings)
    finally:
        stop.set()
        monitor_thread.join()
    peak = max(peak, process.memory_info().rss)
    available = sum(entry["status"] == "available" for entry in metadata["sheet_profiles"])
    result = {
        "sheets_available": available,
        "cells": 400000,
        "file_bytes": len(data),
        "baseline_rss_mib": round(baseline / 1048576, 2),
        "peak_rss_mib": round(peak / 1048576, 2),
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "environment": sys.platform,
        "passed": available == 4 and peak < 450 * 1048576,
    }
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
