# 🚀 Quick Start - AI Positioning Tests

## Run Tests in 3 Steps

### Step 1: Check Your Settings

Open Unreal → Tools → **StoryboardTo3D** → Settings → **AI Tab**

✅ Verify:
- AI Provider selected (OpenAI/Claude/LLaVA)
- API Key entered and valid
- Click "Test Connection" to verify

### Step 2: Run All Tests

Open Unreal Python Console (press `~` then type `py`):

```python
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\run_all_positioning_tests.py').read())
```

Wait 2-5 minutes for all tests to complete.

### Step 3: Check Results

Look for in the output log:

```
🎉 ALL TESTS PASSED!
✅ Your positioning system is ready for production integration!
```

**Or** if some failed:

```
⚠️ PARTIAL SUCCESS
3 out of 5 phases passed.
```

Check `Saved/PositioningTests/test_report_*.json` for details.

---

## Run Individual Phases

If a phase fails, run it individually for debugging:

```python
# Phase 1: AI Communication
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase1_ai_io.py').read())

# Phase 2: Actor Movement  
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase2_movement.py').read())

# Phase 3: Scene Capture
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase3_capture.py').read())

# Phase 4: Single Iteration
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase4_single_iteration.py').read())

# Phase 5: Full Loop
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase5_iterative_loop.py').read())
```

---

## What Each Phase Tests

| Phase | What It Tests | Time |
|-------|---------------|------|
| 1 | AI can receive images and return positioning JSON | 30s |
| 2 | Actors can be moved programmatically in UE | 45s |
| 3 | Scene can be captured as images for AI | 60s |
| 4 | Complete single iteration: capture→AI→move | 90s |
| 5 | Iterative refinement with convergence | 3-5min |

---

## Troubleshooting

### "AI provider not initialized"
→ Go to Settings → AI tab, set up API key

### "Failed to spawn actor"
→ Make sure you have a level open in editor

### "Screenshot not found"  
→ Normal async behavior, tests handle this

### "No storyboard found"
→ Tests work in synthetic mode without storyboards

---

## Next Steps After Tests Pass

1. **Integrate** into `scene_builder.py`
2. **Hook up** to Generate button
3. **Test** with real storyboard panels
4. **Tune** convergence threshold and max iterations

---

## Need Help?

Check full documentation: `README.md` in this folder
