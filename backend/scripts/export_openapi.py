"""Write the OpenAPI spec to a file (used to generate frontend types).

Usage: uv run python scripts/export_openapi.py ../frontend/openapi.json
"""

import json
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
with tempfile.TemporaryDirectory() as tmp:
    app = create_app(Settings(data_dir=Path(tmp), secret_key="x"), migrate=False)
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"wrote {out}")
