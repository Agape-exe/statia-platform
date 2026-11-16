"""Entrada privada por stdin/stdout; sin herramientas ni código recibido del modelo."""
import base64
import json
import sys

from fastapi import HTTPException

from app.services.statistics.engine import calculate
from app.services.statistics.preparation import AnalysisError


def main():
    try:
        job = json.loads(sys.stdin.buffer.read(32 * 1024 * 1024 + 1))
        result, charts = calculate(job)
        response = {'result': result, 'charts': {name: base64.b64encode(data).decode('ascii') for name, data in charts.items()}}
    except (AnalysisError, HTTPException) as exc:
        response = {'error': str(exc.detail) if isinstance(exc, HTTPException) else str(exc)}
    except Exception:
        # No enviar trazas, valores de celdas ni credenciales a logs o al navegador.
        response = {'error': 'No se pudo calcular el análisis. Revisa el contrato, el formato y las magnitudes numéricas.'}
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
