from pathlib import Path

# Shared MVP contract for future LLM/agent-generated inputs.
length_mm = 100.0
width_mm = 10.0
height_mm = 10.0
fixed_x = 0.0
load_x = 100.0
bbox_tol = 0.2
load_vector_n = (0.0, -50.0, 0.0)

young_modulus_mpa = 3500.0
poisson_ratio = 0.36

REPO_ROOT = Path(__file__).resolve().parent.parent
STEP_PATH = REPO_ROOT / "beam.step"
MSH_PATH = REPO_ROOT / "beam.msh"
