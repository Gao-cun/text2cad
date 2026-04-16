from __future__ import annotations

import cadquery as cq

import config


def build_beam() -> cq.Workplane:
    # Translate the box so the cantilever spans x in [0, length_mm].
    return (
        cq.Workplane("XY")
        .box(config.length_mm, config.width_mm, config.height_mm)
        .translate((config.length_mm / 2.0, 0.0, 0.0))
    )


def main() -> None:
    beam = build_beam()
    cq.exporters.export(beam, str(config.STEP_PATH))
    print(f"Exported STEP: {config.STEP_PATH}")


if __name__ == "__main__":
    main()
