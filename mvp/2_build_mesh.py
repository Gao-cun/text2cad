from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textcad_agent.cad_backend import build_mesh_artifacts, resolve_workspace

def main() -> None:
    result = build_mesh_artifacts(resolve_workspace())
    print(f"Exported mesh: {result['msh_path']}")


if __name__ == "__main__":
    main()
