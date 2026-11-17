"""Reproducción descriptiva local: rutas reales de aceptación/preparación y motor real."""

import argparse
import base64
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument("backend_root")
parser.add_argument("bridge")
parser.add_argument("project")
parser.add_argument("conversation")
parser.add_argument("proposal")
args = parser.parse_args()
assert urlsplit(args.bridge).hostname == "127.0.0.1"
if sys.platform == "win32":

    def unavailable_wmi(*_):
        raise OSError("WMI no disponible en el host de pruebas")

    platform._wmi_query = unavailable_wmi
sys.path.insert(0, args.backend_root)
os.environ["PYTHONPATH"] = args.backend_root + os.pathsep + os.environ.get("PYTHONPATH", "")
if sys.platform == "win32":
    bootstrap = Path(tempfile.mkdtemp(prefix="statia-os-metadata-"))
    (bootstrap / "sitecustomize.py").write_text(
        "import platform\ndef no_wmi(*args):\n    raise OSError('WMI no disponible')\nplatform._wmi_query=no_wmi\n",
        encoding="utf-8",
    )
    os.environ["PYTHONPATH"] += os.pathsep + str(bootstrap)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.statistics.engine import calculate  # noqa: E402

app = create_app(Settings(_env_file=None, supabase_url=args.bridge, supabase_publishable_key="public-synthetic"))
path = f"/projects/{args.project}/conversations/{args.conversation}"
headers = {"Authorization": "Bearer synthetic-a"}
with TestClient(app) as client, httpx.Client(base_url=args.bridge, headers=headers) as store:
    accepted = client.patch(path + "/proposals/" + args.proposal, json={"status": "accepted"}, headers=headers)
    data = client.get(path, headers=headers).json()
    output = {"acceptance": accepted.status_code, "conversation_stage": data["conversation"]["current_stage"]}
    if accepted.status_code == 200:
        prepared = client.post(
            path + "/turns",
            json={"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": args.proposal},
            headers=headers,
        )
        assert prepared.status_code == 200, (prepared.text, store.get("/test/errors").json())
        output["preparation_status"] = client.get(path, headers=headers).json()["conversation"]["stage_data"][
            "execution_preparation"
        ]["result"]["status"]
    proposal = store.get("/rest/v1/analysis_proposals", params={"id": "eq." + args.proposal}).json()[0]
    plan = proposal["analysis_plan"]
    files = store.get("/rest/v1/project_files", params={"project_id": "eq." + args.project}).json()
    for file in files:
        raw = store.get("/storage/v1/object/authenticated/project-files/" + file["storage_path"])
        assert raw.status_code == 200
        file["data"] = base64.b64encode(raw.content).decode("ascii")
    spec = {
        "components": [{"source_index": 0, "method": "descriptive", "descriptive_intervals": False}],
        "decisions": [
            {"variable": v, "statistical_type": "nominal" if v["role"] == "group" else "continuous"}
            for v in plan["variables"]
        ],
        "decisions_confirmed": True,
    }
    job = {
        "run_id": str(uuid4()),
        "project_id": args.project,
        "conversation_id": args.conversation,
        "proposal_id": args.proposal,
        "plan": plan,
        "specification": spec,
        "files": files,
    }
    try:
        result, _ = calculate(job)
        output["calculation_status"] = result["status"]
        output["table_titles"] = [t["title"] for c in result["components"] for t in c["tables"]]
        output["table_rows"] = [len(t["rows"]) for c in result["components"] for t in c["tables"]]
    except ValueError:
        output["calculation_status"] = "blocked"
    print(json.dumps(output))
