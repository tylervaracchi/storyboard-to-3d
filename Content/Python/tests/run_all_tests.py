# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test Runner - Main Test Execution Script
Run all tests and generate detailed report
"""

import unreal
import sys
from pathlib import Path
from datetime import datetime

# Add tests directory to path
test_dir = Path(__file__).parent
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

def run_all_tests():
    """Run all API tests and collect results"""

    unreal.log("\n" + "="*80)
    unreal.log("UE 5.6 SEQUENCER API TEST SUITE")
    unreal.log(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    unreal.log("="*80)

    results = {}

    # Test 1: Basic Sequence Creation
    unreal.log("\n[TEST 1] Basic Sequence Creation")
    unreal.log("-"*40)
    from test_01_basic_sequence import test_basic_sequence_creation
    results['basic_sequence'] = test_basic_sequence_creation()

    # Test 2: Camera Spawnable Methods
    unreal.log("\n[TEST 2] Camera Spawnable Methods")
    unreal.log("-"*40)
    from test_02_camera_spawnable import test_camera_spawnable_methods
    results['camera_spawnable'] = test_camera_spawnable_methods()

    # Test 3: Camera Cut Track Creation
    unreal.log("\n[TEST 3] Camera Cut Track Creation")
    unreal.log("-"*40)
    from test_03_camera_cut_track import test_camera_cut_track_creation
    results['camera_cut_track'] = test_camera_cut_track_creation()

    # Test 4: Camera Binding Methods
    unreal.log("\n[TEST 4] Camera Binding Methods")
    unreal.log("-"*40)
    from test_04_camera_binding import test_camera_binding_methods
    results['camera_binding'] = test_camera_binding_methods()

    # Test 5: Object Binding ID Investigation
    unreal.log("\n[TEST 5] MovieSceneObjectBindingID Investigation")
    unreal.log("-"*40)
    from test_05_binding_id_research import research_binding_id_structure
    results['binding_id'] = research_binding_id_structure()

    # Test 6: Alternative Binding Approaches
    unreal.log("\n[TEST 6] Alternative Binding Approaches")
    unreal.log("-"*40)
    from test_06_alternative_binding import test_alternative_binding_methods
    results['alternative'] = test_alternative_binding_methods()

    # Test 7: Complete Workflow
    unreal.log("\n[TEST 7] Complete Workflow Test")
    unreal.log("-"*40)
    from test_07_complete_workflow import test_complete_workflow
    workflow_results = test_complete_workflow()
    results['workflow'] = all(workflow_results.values()) if isinstance(workflow_results, dict) else workflow_results

    # Generate detailed report
    generate_report(results, workflow_results if isinstance(workflow_results, dict) else {})

    return results


def generate_report(results, workflow_details):
    """Generate detailed test report"""

    unreal.log("\n" + "="*80)
    unreal.log("TEST RESULTS SUMMARY")
    unreal.log("="*80)

    # Overall results
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r)
    failed_tests = total_tests - passed_tests

    unreal.log(f"\nTotal Tests: {total_tests}")
    unreal.log(f"Passed: {passed_tests}")
    unreal.log(f"Failed: {failed_tests}")
    unreal.log(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

    # Individual test results
    unreal.log("\n Individual Test Results:")
    unreal.log("-"*40)

    for test_name, result in results.items():
        status = " PASSED" if result else " FAILED"
        unreal.log(f"{test_name}: {status}")

    # Workflow details
    if workflow_details:
        unreal.log("\n Workflow Steps:")
        unreal.log("-"*40)
        for step, success in workflow_details.items():
            status = "" if success else ""
            unreal.log(f"{status} {step.replace('_', ' ').title()}")

    # Key findings
    unreal.log("\n KEY FINDINGS:")
    unreal.log("-"*40)

    # Check API version
    if results.get('basic_sequence'):
        unreal.log("UE 5.6 API detected (uses add_track instead of add_master_track)")
    else:
        unreal.log("API version unclear or incompatible")

    # Camera spawnable status
    if results.get('camera_spawnable'):
        unreal.log("Camera can be added as spawnable")
    else:
        unreal.log("Problem adding camera as spawnable")

    # Cut track status
    if results.get('camera_cut_track'):
        unreal.log("Camera cut track can be created")
    else:
        unreal.log("Problem creating camera cut track")

    # Binding status
    if results.get('camera_binding'):
        unreal.log("Camera binding methods available")
    elif workflow_details.get('binding_verified'):
        unreal.log("Camera binding works but requires specific approach")
    else:
        unreal.log("Camera binding is problematic")

    # Recommendations
    unreal.log("\n RECOMMENDATIONS:")
    unreal.log("-"*40)

    if not results.get('camera_binding') and not workflow_details.get('binding_verified'):
        unreal.log("1. Camera binding is failing - consider manual UI binding as workaround")
        unreal.log("2. Check if UE 5.6 has auto-binding when single camera exists")
        unreal.log("3. May need to use editor-specific APIs or C++ exposed methods")

    if results.get('camera_cut_track') but not results.get('camera_binding'):
        unreal.log("1. Track creation works but binding fails")
        unreal.log("2. The issue is specifically with set_camera_binding_id()")
        unreal.log("3. Consider using the manual right-click method in UI")

    # Save report to file
    save_report_to_file(results, workflow_details)


def save_report_to_file(results, workflow_details):
    """Save detailed report to file"""

    report_file = test_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(report_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("UE 5.6 SEQUENCER API TEST REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

        # Summary
        total = len(results)
        passed = sum(1 for r in results.values() if r)
        f.write(f"SUMMARY\n")
        f.write(f"Total Tests: {total}\n")
        f.write(f"Passed: {passed}\n")
        f.write(f"Failed: {total - passed}\n")
        f.write(f"Success Rate: {(passed/total)*100:.1f}%\n\n")

        # Individual results
        f.write("INDIVIDUAL TEST RESULTS\n")
        f.write("-"*40 + "\n")
        for test_name, result in results.items():
            f.write(f"{test_name}: {'PASSED' if result else 'FAILED'}\n")

        # Workflow details
        if workflow_details:
            f.write("\nWORKFLOW STEPS\n")
            f.write("-"*40 + "\n")
            for step, success in workflow_details.items():
                f.write(f"{step}: {'SUCCESS' if success else 'FAILED'}\n")

        # Findings
        f.write("\nKEY FINDINGS\n")
        f.write("-"*40 + "\n")

        if results.get('basic_sequence'):
            f.write("- UE 5.6 API confirmed (uses add_track)\n")

        if results.get('camera_spawnable'):
            f.write("- Camera spawnable methods work\n")

        if results.get('camera_cut_track'):
            f.write("- Camera cut track creation works\n")

        if not results.get('camera_binding'):
            f.write("- Camera binding is problematic\n")
            f.write("- Manual UI binding may be required\n")

        f.write("\nRECOMMENDATIONS\n")
        f.write("-"*40 + "\n")

        if not results.get('camera_binding'):
            f.write("1. Use manual UI binding as primary method\n")
            f.write("2. Implement automatic retry logic\n")
            f.write("3. Add user notification about manual step\n")

    unreal.log(f"\n Report saved to: {report_file}")

    # Also create a summary file with just the working solution
    create_solution_file(results, workflow_details)


def create_solution_file(results, workflow_details):
    """Create a file with just the working solution"""

    solution_file = test_dir / "WORKING_SOLUTION.py"

    with open(solution_file, 'w') as f:
        f.write('"""\n')
        f.write('WORKING SOLUTION FOR UE 5.6 CAMERA CUT TRACK\n')
        f.write(f'Based on test results from {datetime.now().strftime("%Y-%m-%d")}\n')
        f.write('"""\n\n')
        f.write('import unreal\n\n')

        f.write('def create_sequence_with_camera_cut():\n')
        f.write('    """Working method to create sequence with camera cut track"""\n')
        f.write('    \n')
        f.write('    # 1. Create sequence\n')
        f.write('    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()\n')
        f.write('    level_sequence = asset_tools.create_asset(\n')
        f.write('        asset_name="MySequence",\n')
        f.write('        package_path="/Game/Sequences",\n')
        f.write('        asset_class=unreal.LevelSequence,\n')
        f.write('        factory=unreal.LevelSequenceFactoryNew()\n')
        f.write('    )\n')
        f.write('    \n')
        f.write('    # 2. Open in sequencer\n')
        f.write('    unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(level_sequence)\n')
        f.write('    \n')
        f.write('    # 3. Create camera\n')
        f.write('    camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(\n')
        f.write('        unreal.CineCameraActor,\n')
        f.write('        location=unreal.Vector(-500, 0, 200),\n')
        f.write('        rotation=unreal.Rotator(-10, 0, 0)\n')
        f.write('    )\n')
        f.write('    \n')
        f.write('    # 4. Add camera to sequence\n')
        f.write('    level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)\n')
        f.write('    if level_seq_editor:\n')
        f.write('        camera_binding = level_seq_editor.add_spawnable_from_instance(level_sequence, camera_actor)\n')
        f.write('    else:\n')
        f.write('        camera_binding = level_sequence.add_spawnable_from_instance(camera_actor)\n')
        f.write('    \n')
        f.write('    # 5. Create camera cut track (UE 5.6 uses add_track)\n')
        f.write('    camera_cut_track = level_sequence.add_track(unreal.MovieSceneCameraCutTrack)\n')
        f.write('    \n')
        f.write('    # 6. Add section\n')
        f.write('    section = camera_cut_track.add_section()\n')
        f.write('    \n')

        if not results.get('camera_binding'):
            f.write('    # 7. MANUAL STEP REQUIRED\n')
            f.write('    # Camera binding via Python is problematic in UE 5.6\n')
            f.write('    # User must right-click the camera cut section and select the camera\n')
            f.write('    unreal.log("MANUAL STEP: Right-click the red camera cut section and select your camera")\n')
        else:
            f.write('    # 7. Bind camera (if this works in your version)\n')
            f.write('    camera_guid = camera_binding.get_id()\n')
            f.write('    try:\n')
            f.write('        section.set_camera_binding_id(camera_guid)\n')
            f.write('    except:\n')
            f.write('        unreal.log("Camera binding failed - manual selection required")\n')

        f.write('    \n')
        f.write('    # 8. Clean up\n')
        f.write('    unreal.EditorLevelLibrary.destroy_actor(camera_actor)\n')
        f.write('    \n')
        f.write('    return level_sequence\n')

    unreal.log(f"Working solution saved to: {solution_file}")


if __name__ == "__main__":
    results = run_all_tests()

    # Show quick action items
    unreal.log("\n" + "="*80)
    unreal.log("QUICK ACTIONS")
    unreal.log("="*80)

    if not results.get('camera_binding'):
        unreal.log("\n Camera binding is not working via Python API")
        unreal.log("\n Workaround Options:")
        unreal.log("1. Add UI notification to prompt manual binding")
        unreal.log("2. Implement post-generation checklist")
        unreal.log("3. Create macro/script for UI automation")
        unreal.log("\n Manual Fix:")
        unreal.log("Right-click camera cut section → Select camera from menu")
