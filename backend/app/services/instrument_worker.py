"""Proceso documental cancelable, sin originales en disco ni mensajes de librerías en la API."""

import asyncio
import base64
import json
import sys

import psutil
from fastapi import HTTPException

from app.services.analysis_worker import kill_process_tree


async def inspect_instrument(name, data, settings, *, timeout=20, memory_mb=192):
    if len(data) > min(settings.max_file_bytes, 10 * 1024 * 1024):
        raise HTTPException(
            413, "El instrumento supera el límite de carga: hasta 10 MB y el máximo configurado para archivos."
        )
    payload = json.dumps(
        {
            "name": name,
            "data": base64.b64encode(data).decode("ascii"),
            "max_file_bytes": settings.max_file_bytes,
            "max_expanded_bytes": settings.max_expanded_bytes,
        }
    ).encode()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.services.instrument_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    communication = asyncio.create_task(process.communicate(payload))
    try:
        async with asyncio.timeout(timeout):
            while not communication.done():
                try:
                    child = psutil.Process(process.pid)
                    rss = child.memory_info().rss + sum(p.memory_info().rss for p in child.children(recursive=True))
                    if rss > memory_mb * 1024 * 1024 or rss + psutil.Process().memory_info().rss > 450 * 1024 * 1024:
                        raise HTTPException(413, "El instrumento supera el límite de memoria de extracción.")
                except psutil.NoSuchProcess:
                    pass
                await asyncio.wait({communication}, timeout=0.1)
            stdout, _ = await communication
        if process.returncode or len(stdout) > 3 * 1024 * 1024:
            raise HTTPException(422, "La extracción documental no pudo finalizar dentro de sus límites.")
        output = json.loads(stdout)
        if "error" in output:
            raise HTTPException(output["status"], output["error"])
        return output
    except TimeoutError:
        raise HTTPException(422, "La extracción del instrumento superó los 20 segundos y se detuvo.") from None
    finally:
        if process.returncode is None:
            kill_process_tree(process.pid)
            await process.wait()
        if not communication.done():
            communication.cancel()
        await asyncio.gather(communication, return_exceptions=True)


if __name__ == "__main__":
    from types import SimpleNamespace

    from app.services.profiling import inspect_file

    try:
        job = json.loads(sys.stdin.buffer.read(16 * 1024 * 1024))
        result = inspect_file(
            job["name"],
            base64.b64decode(job["data"], validate=True),
            "instrument",
            SimpleNamespace(max_file_bytes=job["max_file_bytes"], max_expanded_bytes=job["max_expanded_bytes"]),
        )
    except HTTPException as exc:
        result = {"status": exc.status_code, "error": exc.detail}
    except Exception:
        result = {"status": 422, "error": "No se pudo extraer el instrumento dentro de los límites permitidos."}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
