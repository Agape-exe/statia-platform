"""Solo pruebas: backend real elegido por ruta, puente loopback y proveedores simulados."""

import argparse
import json
import platform
import sys
from urllib.parse import urlsplit
from uuid import UUID

parser = argparse.ArgumentParser()
parser.add_argument("backend_root")
parser.add_argument("bridge")
parser.add_argument("project")
parser.add_argument("conversation")
parser.add_argument("request_id")
parser.add_argument("mode", choices=["terra-fail", "terra-success", "gemini-success"])
args = parser.parse_args()
assert urlsplit(args.bridge).hostname == "127.0.0.1"
# Evitar el bloqueo COM/WMI del host de pruebas; platform conserva su fallback WinAPI.
# No afecta rutas, proveedores, SQL ni estadísticas, y no se aplica fuera de Windows.
if sys.platform == "win32":

    def unavailable_wmi(*args):
        raise OSError("WMI no disponible en el host de pruebas")

    platform._wmi_query = unavailable_wmi
sys.path.insert(0, args.backend_root)

# Estos imports deben ocurrir después de seleccionar el checkout histórico exacto.
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.chat import AssistantReply  # noqa: E402

config = Settings(
    _env_file=None,
    supabase_url=args.bridge,
    supabase_publishable_key="public-synthetic",
    gemini_api_key="gemini-synthetic",
    openai_api_key="openai-synthetic",
    openai_terra_enabled=True,
)
app = create_app(config)


class Simulated:
    calls = 0

    def check_available(self):
        pass

    async def generate(self, context, correction=None):
        self.calls += 1
        if args.mode == "terra-fail":
            raise HTTPException(503, "Fallo Terra sintético")
        return AssistantReply(response="Explicación sintética de las mediciones.", suggested_stage="goal")


gemini, terra = Simulated(), Simulated()
app.state.provider = gemini
app.state.openai_provider = terra
with TestClient(app) as client:
    response = client.post(
        f"/projects/{UUID(args.project)}/conversations/{UUID(args.conversation)}/turns",
        json={"request_id": str(UUID(args.request_id)), "content": "Describe las mediciones"},
        headers={"Authorization": "Bearer synthetic-a"},
    )
    print(
        json.dumps(
            {
                "status": response.status_code,
                "gemini_calls": gemini.calls,
                "terra_calls": terra.calls,
                "reply": response.json(),
            }
        )
    )
