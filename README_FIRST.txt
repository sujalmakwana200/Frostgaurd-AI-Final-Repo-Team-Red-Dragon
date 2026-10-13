FrostGuard fix pack — correctly named files.

Copy to repo root AS NEW FILES:   security.py, .env.example, .gitignore (replace), requirements.txt (replace), tests/ (whole folder)
Read as a guide, do not copy:     FIXES.md
Patches (open side by side, paste blocks into the original — never rename over it):
  api_patch.py            -> api.py
  main_dashboard_patch.py -> main_dashboard.py
  knn_adapter_patch.py    -> knn_adapter.py
  bridge_patch.py         -> Bridge.py (only if you keep it; FIXES.md says delete it)
