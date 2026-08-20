"""Generate the OpenAPI JSON spec without starting a server."""

import json
import sys
from pathlib import Path

# Ensure the api app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

spec = app.openapi()

spec["servers"] = [
    {"url": "http://localhost:8000", "description": "Development"},
]

output_path = Path(__file__).resolve().parent.parent / "openapi.json"
output_path.write_text(json.dumps(spec, indent=2))
print(f"OpenAPI spec written to {output_path}", file=sys.stderr)
