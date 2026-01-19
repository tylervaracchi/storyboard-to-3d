# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
═══════════════════════════════════════════════════════════════════════════════
                    CAMERA BINDING - COMPLETE TEST SUITE
                              Quick Reference
═══════════════════════════════════════════════════════════════════════════════

YOU'RE HERE BECAUSE: The green GENERATE button creates scenes but the camera
                     might not be bound to the camera cut track.

═══════════════════════════════════════════════════════════════════════════════


 QUICK START - TEST NOW
═══════════════════════════════════════════════════════════════════════════════

1. Open Unreal Engine
2. Press ~ key (opens console)
3. Type: py
4. Paste this:

exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_generate_button_flow.py').read())

5. Read the output in Output Log
6. Look for:  camera_binding: True or  camera_binding: False


 IF CAMERA BINDING FAILED
═══════════════════════════════════════════════════════════════════════════════

OPTION 1: Automatic Fix (Try this first)
─────────────────────────────────────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\fix_camera_binding.py').read())


OPTION 2: Manual Fix (Always works)
────────────────────────────────────
1. Open your sequence in Sequencer
2. Find the Camera Cut track
3. See the red section? Right-click it
4. Select your camera from the menu
5. Done!


 DOCUMENTATION
═══════════════════════════════════════════════════════════════════════════════

Full Guide:
───────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\CAMERA_BINDING_GUIDE.py').read())

Tests README:
─────────────
D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\README.md


 ALL AVAILABLE TESTS
═══════════════════════════════════════════════════════════════════════════════

Test What Happens When You Click GENERATE:
───────────────────────────────────────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_generate_button_flow.py').read())

Test Which Binding Method Works:
─────────────────────────────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_04_camera_binding.py').read())

Test Complete Workflow:
───────────────────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_07_complete_workflow.py').read())

Run ALL Tests:
──────────────
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\run_all_tests.py').read())


 EXPECTED RESULTS
═══════════════════════════════════════════════════════════════════════════════

PERFECT (Everything works):
───────────────────────────
 sequence_created: True
 camera_spawnable: True
 camera_cut_track: True
 camera_binding: True

COMMON (Binding fails):
───────────────────────
 sequence_created: True
 camera_spawnable: True
 camera_cut_track: True
 camera_binding: False   ← Use fix_camera_binding.py

BAD (Generation failed):
────────────────────────
 sequence_created: False
→ Check Output Log for errors


 WHAT EACH TEST DOES
═══════════════════════════════════════════════════════════════════════════════

test_generate_button_flow.py:
─────────────────────────────
- Simulates clicking GENERATE button
- Creates test sequence with mock data
- Verifies all stages completed
- Checks if camera is properly bound
- Best for: Quick verification after UI changes

test_04_camera_binding.py:
──────────────────────────
- Tests 5 different binding methods
- Direct GUID
- MovieSceneObjectBindingID
- Full properties
- Editor property
- Direct assignment
- Best for: Finding which method works in your UE version

test_07_complete_workflow.py:
─────────────────────────────
- Tests complete workflow step-by-step
- Shows exactly where failures occur
- More detailed than test_generate_button_flow
- Best for: Debugging specific stage failures

run_all_tests.py:
─────────────────
- Runs ALL sequencer tests
- Generates detailed report file
- Creates WORKING_SOLUTION.py with best method
- Best for: Comprehensive system check


 DEBUGGING WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

Step 1: Verify Generation Works
────────────────────────────────
1. Click GENERATE button in UI
2. Wait 10 seconds
3. Open Content Browser
4. Look in StoryboardSequences folder
5. See Seq_Panel_XXX? → Go to Step 2
6. Don't see it? → Check Output Log for errors

Step 2: Test Camera Binding
────────────────────────────
1. Run test_generate_button_flow.py
2. Check result:
   -  camera_binding: True → All good! Done.
   -  camera_binding: False → Go to Step 3

Step 3: Try Automatic Fix
──────────────────────────
1. Run fix_camera_binding.py
2. Check result:
   -  SUCCESS → Done!
   -  FAILED → Go to Step 4

Step 4: Manual Fix
──────────────────
1. Open sequence in Sequencer
2. Right-click camera cut section
3. Select camera
4. Done!


 FILE STRUCTURE
═══════════════════════════════════════════════════════════════════════════════

D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\
│
├── tests/
│   ├── README.md                       ← Read this first
│   ├── test_generate_button_flow.py    ← START HERE for testing
│   ├── test_04_camera_binding.py       ← Method comparison
│   ├── test_07_complete_workflow.py    ← Detailed workflow test
│   └── run_all_tests.py                ← Run everything
│
├── fix_camera_binding.py               ← Auto-fix script
├── CAMERA_BINDING_GUIDE.py             ← Full documentation
└── THIS_FILE.py                        ← Quick reference

Core code that does the binding:
├── core/
│   └── scene_builder_sequencer.py      ← Stage 7: camera binding

UI code with GENERATE button:
└── ui/widgets/
    └── active_panel_widget.py          ← generate_scene_from_panel()


 WHY THIS ISSUE EXISTS
═══════════════════════════════════════════════════════════════════════════════

The UE 5.6 Python API for camera binding is incomplete/buggy.

What works:
 Creating sequences
 Adding cameras as spawnables
 Creating camera cut tracks
 Adding sections to tracks

What's broken:
 Binding cameras to sections via Python

But:
 Manual UI binding always works (C++ internally)

Epic is aware of this. Might be fixed in future UE versions.


 UNDERSTANDING THE CODE
═══════════════════════════════════════════════════════════════════════════════

When you click GENERATE:
────────────────────────
active_panel_widget.py: generate_scene_from_panel()
  ↓ Creates analysis data
scene_builder_sequencer.py: build_scene()
  ↓ Queues 9 stages
Stage 7: _stage_add_camera_cut_track()
  ↓ This is where binding happens
  section.set_camera_binding_id(binding_id)  ← FAILS HERE

The problem line is around line 500 in scene_builder_sequencer.py


 FIXING IN YOUR CODE
═══════════════════════════════════════════════════════════════════════════════

If you want to update scene_builder_sequencer.py:

Current code (Stage 7):
───────────────────────
try:
    binding_id = unreal.MovieSceneObjectBindingID()
    binding_id.set_editor_property('guid', camera_guid)
    section.set_camera_binding_id(binding_id)
except:
    # Silently fails

Better code:
────────────
try:
    binding_id = unreal.MovieSceneObjectBindingID()
    binding_id.set_editor_property('guid', camera_guid)
    section.set_camera_binding_id(binding_id)

    # Verify it worked
    current = section.get_camera_binding_id()
    if current and hasattr(current, 'guid'):
        if str(current.guid) == str(camera_guid):
            unreal.log("Camera bound successfully")
        else:
            unreal.log_warning("Camera binding failed - manual fix needed")
    else:
        unreal.log_warning("Camera binding failed - manual fix needed")
except Exception as e:
    unreal.log_error(f"Camera binding error: {e}")


 SUPPORT
═══════════════════════════════════════════════════════════════════════════════

Still stuck? Check:
1. Output Log for detailed errors
2. test_report_*.txt files in tests folder
3. Verify all paths match your installation
4. Make sure you're using UE 5.6


 SUCCESS CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

Camera binding is working if:
□ test_generate_button_flow.py shows  camera_binding: True
□ Sequence opens in Sequencer automatically
□ Camera Cut track shows camera view (not red)
□ Playing sequence uses camera perspective
□ No errors in Output Log

If all checked:  You're done!


═══════════════════════════════════════════════════════════════════════════════
                                END OF GUIDE
═══════════════════════════════════════════════════════════════════════════════

To print this guide:
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\QUICK_REFERENCE.py').read())

"""

print(__doc__)
