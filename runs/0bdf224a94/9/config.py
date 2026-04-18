from pathlib import Path

length_mm = 120.0
width_mm = 100.0
height_mm = 120.0
fixed_x = 0.0
load_x = 30.0
bbox_tol = 0.2
load_vector_n = (0.0, 0.0, -4.9)
young_modulus_mpa = 3500.0
poisson_ratio = 0.36

REPO_ROOT = Path(__file__).resolve().parent
STEP_PATH = REPO_ROOT / "model.step"
STL_PATH = REPO_ROOT / "model.stl"
MSH_PATH = REPO_ROOT / "model.msh"
