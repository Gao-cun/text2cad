from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textcad_agent.cad_backend import export_cad_artifacts, resolve_workspace

def main() -> None:
    result = export_cad_artifacts(resolve_workspace())
    print(f"Exported STEP: {result['step_path']}")
    print(f"Exported STL: {result['stl_path']}")


if __name__ == "__main__":
    main()
