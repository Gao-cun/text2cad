from __future__ import annotations

import json

import numpy as np
import pyvista as pv

from textcad_agent.cad_backend import build_mesh_artifacts
from textcad_agent.tools import _annotate_vtk_regions, _build_cad, _solve_fea


def test_annotate_vtk_regions_writes_fixed_and_load_arrays(tmp_path):
    vtk_path = tmp_path / "fea_result.vtk"
    mesh = pv.PolyData(
        np.array(
            [
                [0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [9.9, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [5.0, 0.0, 0.0],
            ]
        )
    )
    mesh.point_data["u"] = np.zeros((mesh.n_points, 3))
    mesh.save(vtk_path)

    config_data = {
        "fixed_x": 0.0,
        "load_x": 10.0,
        "bbox_tol": 0.2,
    }

    annotated = _annotate_vtk_regions(vtk_path, config_data)
    reread = pv.read(vtk_path)

    np.testing.assert_array_equal(annotated.point_data["is_fixed"], np.array([1, 1, 0, 0, 0], dtype=np.uint8))
    np.testing.assert_array_equal(annotated.point_data["is_load"], np.array([0, 0, 1, 1, 0], dtype=np.uint8))
    np.testing.assert_array_equal(reread.point_data["is_fixed"], annotated.point_data["is_fixed"])
    np.testing.assert_array_equal(reread.point_data["is_load"], annotated.point_data["is_load"])


def test_build_cad_accepts_boundbox_min_max_style_access(tmp_path):
    (tmp_path / "generated_model.py").write_text(
        "\n".join(
            [
                "import cadquery as cq",
                "",
                "def build_model():",
                "    body = cq.Workplane('XY').box(10, 10, 10)",
                "    bb = body.val().BoundingBox()",
                "    return body.translate((-bb.min.X, 0, 0))",
                "",
                "MODEL = build_model()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "REPO_ROOT = Path(__file__).resolve().parent",
                'STEP_PATH = REPO_ROOT / "model.step"',
                'STL_PATH = REPO_ROOT / "model.stl"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _build_cad(str(tmp_path))

    assert (tmp_path / "model.step").exists()
    assert (tmp_path / "model.stl").exists()
    assert "Exported STEP" in result["stdout"]


def test_build_cad_tolerates_empty_edge_fillet_from_llm_code(tmp_path):
    (tmp_path / "generated_model.py").write_text(
        "\n".join(
            [
                "import cadquery as cq",
                "",
                "def build_model():",
                "    return cq.Workplane('XY').box(10, 10, 10).edges('>X and <X').fillet(1.0)",
                "",
                "MODEL = build_model()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "REPO_ROOT = Path(__file__).resolve().parent",
                'STEP_PATH = REPO_ROOT / "model.step"',
                'STL_PATH = REPO_ROOT / "model.stl"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _build_cad(str(tmp_path))

    assert (tmp_path / "model.step").exists()
    assert (tmp_path / "model.stl").exists()
    assert "Exported STL" in result["stdout"]


def test_build_mesh_falls_back_to_actual_bbox_faces_when_config_x_is_not_on_face(tmp_path):
    (tmp_path / "generated_model.py").write_text(
        "\n".join(
            [
                "import cadquery as cq",
                "",
                "def build_model():",
                "    return cq.Workplane('XY').box(20, 10, 10).translate((20, 0, 0))",
                "",
                "MODEL = build_model()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "analysis_config.json").write_text(
        json.dumps(
            {
                "length_mm": 20.0,
                "width_mm": 10.0,
                "height_mm": 10.0,
                "fixed_x": 5.0,
                "load_x": 50.0,
                "bbox_tol": 0.2,
                "load_vector_n": [0.0, -1.0, 0.0],
                "young_modulus_mpa": 3500.0,
                "poisson_ratio": 0.36,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "REPO_ROOT = Path(__file__).resolve().parent",
                "length_mm = 20.0",
                "width_mm = 10.0",
                "height_mm = 10.0",
                "fixed_x = 5.0",
                "load_x = 50.0",
                "bbox_tol = 0.2",
                "load_vector_n = (0.0, -1.0, 0.0)",
                "young_modulus_mpa = 3500.0",
                "poisson_ratio = 0.36",
                'STEP_PATH = REPO_ROOT / "model.step"',
                'STL_PATH = REPO_ROOT / "model.stl"',
                'MSH_PATH = REPO_ROOT / "model.msh"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _build_cad(str(tmp_path))
    result = build_mesh_artifacts(tmp_path)
    metadata = json.loads((tmp_path / "mesh_boundary_metadata.json").read_text(encoding="utf-8"))

    assert result["msh_path"] == str(tmp_path / "model.msh")
    assert (tmp_path / "model.msh").exists()
    assert metadata["requested_fixed_x"] == 5.0
    assert metadata["requested_load_x"] == 50.0
    assert np.isclose(metadata["effective_fixed_x"], 10.0)
    assert np.isclose(metadata["effective_load_x"], 30.0)
    assert len(metadata["fallback_reasons"]) == 2

    fea_summary = _solve_fea(str(tmp_path))
    assert fea_summary["max_disp_mm"] is not None
    assert fea_summary["left_max_disp_mm"] == 0.0
    assert fea_summary["right_max_disp_mm"] is not None
