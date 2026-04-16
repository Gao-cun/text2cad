from pathlib import Path

length_mm = 20.0
width_mm = 20.0
height_mm = 20.0
fixed_x = 0.0
load_x = 20.0
bbox_tol = 0.1
load_vector_n = (0.0, 0.0, -10.0)
young_modulus_mpa = 200000.0
poisson_ratio = 0.3

REPO_ROOT = Path(__file__).resolve().parent
STEP_PATH = REPO_ROOT / "model.step"
STL_PATH = REPO_ROOT / "model.stl"
MSH_PATH = REPO_ROOT / "model.msh"
