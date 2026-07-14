# Contributing to StoryboardTo3D

Thanks for your interest! This started as MS thesis research and is now open
for community development. PRs and issues are welcome.

## Layout

- `Content/Python/` — everything interesting. `main.py` boots the PySide6 UI;
  `core/` has the scene builder, camera system, and AI providers; `ai_vision/`
  has viewport capture and scene comparison; `analysis/` has sketch and depth
  analysis.
- `Source/StoryboardTo3D/` — small C++ editor module: toolbar button, dock tab,
  and the Python bridge. Most contributions never need to touch it.
- `samples/` — sample panels + an asset library that works in any project.

## Dev setup

1. Clone into a UE project's `Plugins/` folder (see README installation).
2. Python edits hot-reload: close and reopen the plugin window, or run
   `import importlib; importlib.reload(module)` in the UE Python console.
3. C++ edits require an editor rebuild (VS 2022).

## Testing

The test suite under `Content/Python/tests/` runs **inside the UE editor**
(everything imports `unreal`), not under pytest on the command line:

```python
# In the UE Python console:
import sys
sys.path.append(r"<project>/Plugins/StoryboardTo3D/Content/Python/tests")
exec(open(r"<project>/Plugins/StoryboardTo3D/Content/Python/tests/run_all_tests.py").read())
```

CI runs syntax compilation and ruff error checks on every PR — please make
sure `python -m compileall Content/Python` passes locally.

## PR expectations

- One focused change per PR.
- Note which UE version(s) you tested in.
- No hardcoded personal paths (`C:\Users\...`, `D:\...`) — resolve paths from
  `unreal.Paths` or the plugin directory.
- Keep API keys out of code and commits; configuration goes through
  `~/.storyboard_to_3d/` or environment variables.
