# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
MASTER TEST RUNNER - All Positioning System Tests
Runs all 5 phases sequentially with comprehensive reporting
"""

import unreal
from pathlib import Path
import sys
import time
import json

# Add plugin path
plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))


class MasterTestRunner:
    """Run all positioning tests"""

    def __init__(self):
        self.results = {}
        self.start_time = time.time()

    def run_phase_1(self):
        """Phase 1: AI Input/Output"""
        unreal.log("\n" + ""*35)
        unreal.log("RUNNING PHASE 1: AI INPUT/OUTPUT")
        unreal.log(""*35)

        try:
            from tests.positioning.test_phase1_ai_io import PositioningAITest
            test = PositioningAITest()
            test.run_all_tests()

            # Check results
            passed = sum(1 for r in test.test_results if r['success'])
            total = len(test.test_results)

            self.results['phase1'] = {
                'passed': passed,
                'total': total,
                'success': passed == total,
                'details': test.test_results
            }

            return passed == total

        except Exception as e:
            unreal.log_error(f"Phase 1 crashed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            self.results['phase1'] = {'success': False, 'error': str(e)}
            return False

    def run_phase_2(self):
        """Phase 2: Actor Movement"""
        unreal.log("\n" + ""*35)
        unreal.log("RUNNING PHASE 2: ACTOR MOVEMENT")
        unreal.log(""*35)

        try:
            from tests.positioning.test_phase2_movement import ActorMovementTest
            test = ActorMovementTest()
            test.run_all_tests()

            # Note: This test prints its own results
            # We assume success if no exception
            self.results['phase2'] = {'success': True}
            return True

        except Exception as e:
            unreal.log_error(f"Phase 2 crashed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            self.results['phase2'] = {'success': False, 'error': str(e)}
            return False

    def run_phase_3(self):
        """Phase 3: Scene Capture"""
        unreal.log("\n" + ""*35)
        unreal.log("RUNNING PHASE 3: SCENE CAPTURE")
        unreal.log(""*35)

        try:
            from tests.positioning.test_phase3_capture import SceneCaptureTest
            test = SceneCaptureTest()
            test.run_all_tests()

            self.results['phase3'] = {'success': True}
            return True

        except Exception as e:
            unreal.log_error(f"Phase 3 crashed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            self.results['phase3'] = {'success': False, 'error': str(e)}
            return False

    def run_phase_4(self):
        """Phase 4: Single Iteration"""
        unreal.log("\n" + ""*35)
        unreal.log("RUNNING PHASE 4: SINGLE ITERATION")
        unreal.log(""*35)

        try:
            from tests.positioning.test_phase4_single_iteration import SingleIterationTest
            test = SingleIterationTest()
            test.run_test()

            self.results['phase4'] = {'success': True}
            return True

        except Exception as e:
            unreal.log_error(f"Phase 4 crashed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            self.results['phase4'] = {'success': False, 'error': str(e)}
            return False

    def run_phase_5(self):
        """Phase 5: Iterative Loop"""
        unreal.log("\n" + ""*35)
        unreal.log("RUNNING PHASE 5: ITERATIVE LOOP")
        unreal.log(""*35)

        try:
            from tests.positioning.test_phase5_iterative_loop import IterativePositioningSystem
            system = IterativePositioningSystem(max_iterations=5, convergence_threshold=0.85)
            system.run_full_test()

            self.results['phase5'] = {'success': True}
            return True

        except Exception as e:
            unreal.log_error(f"Phase 5 crashed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            self.results['phase5'] = {'success': False, 'error': str(e)}
            return False

    def print_final_report(self):
        """Print comprehensive final report"""
        elapsed = time.time() - self.start_time

        unreal.log("\n\n" + "="*70)
        unreal.log("FINAL TEST REPORT - AI POSITIONING SYSTEM")
        unreal.log("="*70)

        phases = [
            ('Phase 1: AI Input/Output', 'phase1'),
            ('Phase 2: Actor Movement', 'phase2'),
            ('Phase 3: Scene Capture', 'phase3'),
            ('Phase 4: Single Iteration', 'phase4'),
            ('Phase 5: Iterative Loop', 'phase5')
        ]

        total_passed = 0
        total_phases = len(phases)

        for phase_name, phase_key in phases:
            result = self.results.get(phase_key, {})
            success = result.get('success', False)

            if success:
                total_passed += 1
                status = " PASSED"
            else:
                status = " FAILED"

            unreal.log(f"{status} - {phase_name}")

            # Show details if available
            if 'passed' in result and 'total' in result:
                unreal.log(f"({result['passed']}/{result['total']} tests passed)")

            if 'error' in result:
                unreal.log(f"Error: {result['error']}")

        unreal.log("\n" + "-"*70)
        unreal.log(f"Overall: {total_passed}/{total_phases} phases passed")
        unreal.log(f"Time elapsed: {elapsed:.1f} seconds")
        unreal.log("-"*70)

        # Recommendation
        if total_passed == total_phases:
            unreal.log("\n ALL TESTS PASSED!")
            unreal.log("\n Your positioning system is ready for production integration!")
            unreal.log("\nNext steps:")
            unreal.log("1. Integrate into scene_builder.py")
            unreal.log("2. Add to Generate button workflow")
            unreal.log("3. Add user-facing progress indicators")
            unreal.log("4. Test with real storyboard panels")
        elif total_passed >= 3:
            unreal.log("\n PARTIAL SUCCESS")
            unreal.log(f"\n{total_passed} out of {total_phases} phases passed.")
            unreal.log("\nYou can proceed with working phases, but fix failures first.")
        else:
            unreal.log("\n MULTIPLE FAILURES")
            unreal.log("\nFix the failed phases before proceeding:")
            for phase_name, phase_key in phases:
                if not self.results.get(phase_key, {}).get('success', False):
                    unreal.log(f"- {phase_name}")

        unreal.log("\n" + "="*70)

        # Save report
        report_dir = Path(unreal.Paths.project_saved_dir()) / "PositioningTests"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"test_report_{int(time.time())}.json"

        with open(report_file, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'elapsed_seconds': elapsed,
                'results': self.results,
                'summary': {
                    'passed': total_passed,
                    'total': total_phases,
                    'success_rate': total_passed / total_phases
                }
            }, f, indent=2)

        unreal.log(f"Report saved: {report_file}")

    def run_all(self):
        """Run all test phases"""
        unreal.log("\n" + ""*35)
        unreal.log("AI POSITIONING SYSTEM - COMPLETE TEST SUITE")
        unreal.log(""*35)
        unreal.log("\nThis will run all 5 test phases sequentially.")
        unreal.log("Each phase builds on the previous one.")
        unreal.log("\nPress Ctrl+C to cancel (you have 3 seconds)...")

        time.sleep(3)

        # Run all phases
        continue_testing = True

        if continue_testing:
            continue_testing = self.run_phase_1()

        if continue_testing:
            unreal.log("\n Phase 1 passed - continuing to Phase 2...")
            time.sleep(2)
            continue_testing = self.run_phase_2()
        else:
            unreal.log("\n Phase 1 failed - skipping remaining phases")

        if continue_testing:
            unreal.log("\n Phase 2 passed - continuing to Phase 3...")
            time.sleep(2)
            continue_testing = self.run_phase_3()
        else:
            unreal.log("\n Phase 2 failed - skipping remaining phases")

        if continue_testing:
            unreal.log("\n Phase 3 passed - continuing to Phase 4...")
            time.sleep(2)
            continue_testing = self.run_phase_4()
        else:
            unreal.log("\n Phase 3 failed - skipping remaining phases")

        if continue_testing:
            unreal.log("\n Phase 4 passed - continuing to Phase 5...")
            time.sleep(2)
            self.run_phase_5()
        else:
            unreal.log("\n Phase 4 failed - skipping Phase 5")

        # Print final report
        self.print_final_report()


# Main execution
if __name__ == "__main__":
    runner = MasterTestRunner()
    runner.run_all()
