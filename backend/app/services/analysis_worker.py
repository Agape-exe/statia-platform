"""Un proceso numérico por API, cancelable de verdad y sin persistencia local."""
import asyncio
import json
import os
import sys

import psutil
from fastapi import HTTPException


async def run_calculation(job, *, timeout=45, memory_mb=320):
    payload = json.dumps(job, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(payload) > 32 * 1024 * 1024:
        raise HTTPException(413, 'Los originales exceden el límite de ejecución conjunta de 20 MB.')
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'app.services.statistics.worker',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'MPLBACKEND': 'Agg'},
    )
    communication = asyncio.create_task(process.communicate(payload))
    try:
        async with asyncio.timeout(timeout):
            while not communication.done():
                try:
                    child = psutil.Process(process.pid)
                    rss = child.memory_info().rss + sum(p.memory_info().rss for p in child.children(recursive=True))
                    if rss > memory_mb * 1024 * 1024:
                        raise HTTPException(413, 'El análisis supera el límite de memoria. Reduce filas, columnas o componentes.')
                except psutil.NoSuchProcess:
                    pass
                await asyncio.wait({communication}, timeout=.1)
            stdout, _ = await communication
        if process.returncode or len(stdout) > 24 * 1024 * 1024:
            raise HTTPException(422, 'La ejecución no pudo finalizar dentro de sus límites.')
        output = json.loads(stdout)
        if output.get('error'):
            raise HTTPException(422, output['error'])
        return output
    except TimeoutError:
        raise HTTPException(504, 'El cálculo superó los 45 segundos y se detuvo. Reduce el trabajo y vuelve a intentar.') from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        if not communication.done():
            communication.cancel()
        await asyncio.gather(communication, return_exceptions=True)
