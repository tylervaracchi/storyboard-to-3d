# Camera Binding Tests - README

## Overview
These tests verify that camera binding works when clicking the green **GENERATE** button in StoryboardTo3D.

## The Issue
When generating a 3D scene from a storyboard, the system:
1. ✅ Creates a Level Sequence
2. ✅ Adds a camera as a spawnable
3. ✅ Creates a Camera Cut Track
4. ❓ **Binds camera to cut track** ← This sometimes fails

If step 4 fails, the camera cut section shows as **red/empty** instead of showing the camera view.

## Quick Test

Open Unreal Python console (`~` key, type `py`) and run:

```python
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_generate_button_flow.py').read())
```

Look for this in the output:
```
✅ sequence_created: True
✅ camera_spawnable: True
✅ camera_cut_track: True
❌ camera_binding: False    ← If False, binding failed
```

## Quick Fix

If binding failed, run:

```python
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\fix_camera_binding.py').read())
```

This will automatically try all known binding methods.

## Manual Fix (Always Works)

1. Open sequence in Sequencer
2. Find Camera Cut track (red section)
3. Right-click the section
4. Select your camera from menu
5. Done!

## Available Tests

### test_generate_button_flow.py
**What it does:** Tests the complete GENERATE button flow including viewport locking
**When to use:** After clicking GENERATE button to verify it worked
**Expected output:** Reports which steps succeeded/failed including viewport lock status

### test_viewport_locking.py
**What it does:** Tests viewport locking API and automatic camera view
**When to use:** To verify Shift+C functionality works automatically
**Expected output:** Shows if viewport successfully locked to camera cuts

### test_04_camera_binding.py
**What it does:** Tests all 5 camera binding methods
**When to use:** To find which binding method works in your UE version
**Expected output:** Shows which methods succeeded

### test_07_complete_workflow.py
**What it does:** Tests the entire workflow step-by-step
**When to use:** For detailed debugging of the full pipeline
**Expected output:** Reports success/failure for each step

### run_all_tests.py
**What it does:** Runs ALL tests and generates a report
**When to use:** For comprehensive testing
**Expected output:** Creates test_report_*.txt file

## The Code Flow

When you click GENERATE:
```
active_panel_widget.py: generate_scene_from_panel()
  ↓
scene_builder_sequencer.py: build_scene()
  ↓
Stage 1: Create sequence ✅
Stage 2: Load level ✅
Stage 3: Open sequencer ✅
Stage 4: Spawn characters ✅
Stage 5: Spawn props ✅
Stage 6: Setup camera ✅
Stage 7: Add camera cut track ❓ ← PROBLEM HERE
Stage 8: Setup lighting ✅
Stage 9: Finalize ✅
```

**Stage 7** is where camera binding happens, around line 500 in `scene_builder_sequencer.py`.

## Files in This Directory

```
tests/
├── test_generate_button_flow.py    ← Start here
├── test_04_camera_binding.py       ← Method comparison
├── test_07_complete_workflow.py    ← Full pipeline test
├── run_all_tests.py                ← Run everything
├── test_01_basic_sequence.py       ← Basic sequence creation
├── test_02_camera_spawnable.py     ← Camera spawnable test
├── test_03_camera_cut_track.py     ← Cut track creation test
├── test_05_binding_id_research.py  ← API research
└── test_06_alternative_binding.py  ← Alternative methods

One level up:
├── fix_camera_binding.py           ← Auto-fix script
└── CAMERA_BINDING_GUIDE.py         ← Full documentation
```

## Common Issues

### "Sequence not found"
- Wait 5-10 seconds after clicking GENERATE
- The sequence builds asynchronously
- Check Content Browser for Seq_Panel_XXX

### "Camera not found"
- Sequence exists but has no camera spawnable
- Bug in scene_builder_sequencer.py Stage 6
- Check Output Log for errors

### "Camera cut track not found"
- Sequence exists but no cut track
- Bug in scene_builder_sequencer.py Stage 7
- Track creation is failing

### "Binding exists but wrong GUID"
- Camera bound to wrong object
- Rare but possible if multiple cameras exist
- Manually rebind via right-click

## Understanding the Output

### Good Result:
```
✅ sequence_created: True
✅ camera_spawnable: True
✅ camera_cut_track: True
✅ camera_binding: True
```
Everything works! No action needed.

### Common Result:
```
✅ sequence_created: True
✅ camera_spawnable: True
✅ camera_cut_track: True
❌ camera_binding: False
```
Everything except binding works. Use manual fix.

### Bad Result:
```
❌ sequence_created: False
```
Core problem - sequence generation failed.
Check Output Log for errors.

## Recommended Workflow

1. Click GENERATE button in UI
2. Wait 10 seconds
3. Run `test_generate_button_flow.py`
4. If camera_binding is False:
   - Run `fix_camera_binding.py` OR
   - Use manual right-click method
5. Verify in Sequencer

## Technical Details

**The Working Method** (from test results):
```python
binding_id = unreal.MovieSceneObjectBindingID()
binding_id.set_editor_property('guid', camera_guid)
section.set_camera_binding_id(binding_id)
```

This is implemented in `scene_builder_sequencer.py` at Stage 7, but the Python API is inconsistent in UE 5.6.

**Why Manual Works:**
The right-click method uses C++ internally, which has reliable camera binding. Python API is incomplete.

## Getting Help

1. Check Output Log for errors
2. Run `run_all_tests.py` for comprehensive report
3. Read `CAMERA_BINDING_GUIDE.py` for full documentation
4. Verify paths match your installation

## Success Criteria

Camera binding is working if:
- [ ] Sequence opens automatically in Sequencer
- [ ] Camera Cut track visible at top
- [ ] Section shows camera view (not red)
- [ ] Playing sequence uses camera perspective
- [ ] test_generate_button_flow.py shows ✅ camera_binding

If all checked, you're done! 🎉

## Next Steps

If tests pass but you still have issues:
1. Check show-specific asset library
2. Verify assets exist in Content Browser
3. Test with simple scene (1 character, no props)
4. Check for conflicting plugins

---

**Last Updated:** Based on test results from scene_builder_sequencer.py
**UE Version:** 5.6
**Plugin:** StoryboardTo3D
