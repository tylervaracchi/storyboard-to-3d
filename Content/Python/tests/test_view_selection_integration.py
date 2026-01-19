# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Integration Verification Test for Intelligent View Selection

Tests that Optimization #3 is properly integrated into active_panel_widget.py

Run this in Unreal Python console:
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\test_view_selection_integration.py').read())
"""

import unreal


def test_import_availability():
    """Test 1: Verify IntelligentViewSelector can be imported"""
    unreal.log("\n" + "="*70)
    unreal.log("TEST 1: Import Availability")
    unreal.log("="*70)

    try:
        from core.intelligent_view_selector import IntelligentViewSelector
        unreal.log("PASS: IntelligentViewSelector imported successfully")
        return True
    except ImportError as e:
        unreal.log_error(f"FAIL: Could not import IntelligentViewSelector: {e}")
        return False


def test_integration_points():
    """Test 2: Verify all integration points exist in active_panel_widget"""
    unreal.log("\n" + "="*70)
    unreal.log("TEST 2: Integration Points")
    unreal.log("="*70)

    try:
        from ui.widgets.active_panel_widget import ActivePanelWidget

        # Create a mock instance (not fully initialized, just for checking attributes)
        widget = ActivePanelWidget.__new__(ActivePanelWidget)

        # Check class has the new method
        if not hasattr(ActivePanelWidget, '_detect_scene_complexity'):
            unreal.log_error("FAIL: _detect_scene_complexity method not found")
            return False
        else:
            unreal.log("PASS: _detect_scene_complexity method exists")

        # Check import constant exists
        import ui.widgets.active_panel_widget as apw_module
        if not hasattr(apw_module, 'INTELLIGENT_VIEW_SELECTOR_AVAILABLE'):
            unreal.log_error("FAIL: INTELLIGENT_VIEW_SELECTOR_AVAILABLE constant not found")
            return False
        else:
            unreal.log(f"PASS: INTELLIGENT_VIEW_SELECTOR_AVAILABLE = {apw_module.INTELLIGENT_VIEW_SELECTOR_AVAILABLE}")

        unreal.log("PASS: All integration points verified")
        return True

    except Exception as e:
        unreal.log_error(f"FAIL: Integration verification failed: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())
        return False


def test_view_selector_strategies():
    """Test 3: Verify all 5 strategies include hero camera"""
    unreal.log("\n" + "="*70)
    unreal.log("TEST 3: Hero Camera Inclusion in All Strategies")
    unreal.log("="*70)

    try:
        from core.intelligent_view_selector import IntelligentViewSelector

        selector = IntelligentViewSelector()
        strategies = ['MINIMAL', 'FOCUSED', 'REFINEMENT', 'EXPLORATION', 'COMPREHENSIVE']

        all_pass = True
        for strategy in strategies:
            # Check VIEW_SETS definition
            view_set = selector.VIEW_SETS.get(strategy)
            if not view_set:
                unreal.log_error(f"FAIL: Strategy '{strategy}' not found in VIEW_SETS")
                all_pass = False
                continue

            rgb_views = view_set.get('rgb', [])
            if 'hero' not in rgb_views:
                unreal.log_error(f"FAIL: Strategy '{strategy}' does not include 'hero' in RGB views: {rgb_views}")
                all_pass = False
            else:
                unreal.log(f"PASS: {strategy} includes hero - RGB views: {rgb_views}")

        if all_pass:
            unreal.log("\n PASS: All 5 strategies include hero camera")
        else:
            unreal.log_error("\n FAIL: Some strategies missing hero camera")

        return all_pass

    except Exception as e:
        unreal.log_error(f"FAIL: Strategy verification failed: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())
        return False


def test_runtime_safety_check():
    """Test 4: Verify runtime safety check forces hero inclusion"""
    unreal.log("\n" + "="*70)
    unreal.log("TEST 4: Runtime Safety Check")
    unreal.log("="*70)

    try:
        from core.intelligent_view_selector import IntelligentViewSelector

        selector = IntelligentViewSelector()

        # Test with iteration 1 (should use EXPLORATION)
        result = selector.select_views(
            iteration=1,
            previous_score=None,
            num_actors=3,
            shot_type='medium',
            scene_complexity='medium'
        )

        if 'hero' not in result.rgb_views:
            unreal.log_error(f"FAIL: Runtime safety check failed - hero not in views: {result.rgb_views}")
            return False
        else:
            unreal.log(f"PASS: Hero camera included in iteration 1: {result.rgb_views}")

        # Test with high score (should use MINIMAL which is just ['hero'])
        result = selector.select_views(
            iteration=5,
            previous_score=90,
            num_actors=2,
            shot_type='medium',
            scene_complexity='simple'
        )

        if 'hero' not in result.rgb_views:
            unreal.log_error(f"FAIL: Runtime safety check failed - hero not in high-score views: {result.rgb_views}")
            return False
        else:
            unreal.log(f"PASS: Hero camera included in high-score iteration: {result.rgb_views}")

        unreal.log("\n PASS: Runtime safety check working correctly")
        return True

    except Exception as e:
        unreal.log_error(f"FAIL: Runtime safety check failed: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())
        return False


def test_code_search_verification():
    """Test 5: Verify integration code exists by searching the file"""
    unreal.log("\n" + "="*70)
    unreal.log("TEST 5: Code Search Verification")
    unreal.log("="*70)

    try:
        import os
        file_path = r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\ui\widgets\active_panel_widget.py'

        if not os.path.exists(file_path):
            unreal.log_error(f"FAIL: File not found: {file_path}")
            return False

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for key integration markers
        checks = [
            ('Import statement', 'from core.intelligent_view_selector import IntelligentViewSelector'),
            ('Initialization', 'self.view_selector = IntelligentViewSelector()'),
            ('Feature flag', 'self.use_intelligent_view_selection = True'),
            ('View selection logic', 'OPTIMIZATION #3: Intelligent view selection'),
            ('Scene complexity method', 'def _detect_scene_complexity'),
            ('Reset call', 'self.view_selector.reset()'),
            ('Feature summary', 'Intelligent View Selection'),
        ]

        all_found = True
        for name, search_string in checks:
            if search_string in content:
                unreal.log(f"PASS: Found {name}")
            else:
                unreal.log_error(f"FAIL: Missing {name} (searched for: {search_string})")
                all_found = False

        if all_found:
            unreal.log("\n PASS: All integration code found in file")
        else:
            unreal.log_error("\n FAIL: Some integration code missing")

        return all_found

    except Exception as e:
        unreal.log_error(f"FAIL: Code search verification failed: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())
        return False


def run_all_tests():
    """Run all integration verification tests"""
    unreal.log("\n" + "="*70)
    unreal.log("INTELLIGENT VIEW SELECTION - INTEGRATION VERIFICATION")
    unreal.log("="*70)
    unreal.log("Testing Optimization #3 integration into active_panel_widget.py")
    unreal.log("="*70 + "\n")

    tests = [
        ("Import Availability", test_import_availability),
        ("Integration Points", test_integration_points),
        ("Hero Camera in All Strategies", test_view_selector_strategies),
        ("Runtime Safety Check", test_runtime_safety_check),
        ("Code Search Verification", test_code_search_verification),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            unreal.log_error(f"TEST CRASHED: {test_name} - {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            results.append((test_name, False))

    # Print summary
    unreal.log("\n" + "="*70)
    unreal.log("TEST SUMMARY")
    unreal.log("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = " PASS" if result else " FAIL"
        unreal.log(f"{status}: {test_name}")

    unreal.log("="*70)
    unreal.log(f"TOTAL: {passed}/{total} tests passed")
    unreal.log("="*70)

    if passed == total:
        unreal.log("\n SUCCESS: All integration tests passed!")
        unreal.log("Optimization #3 is ready for deployment.")
        return True
    else:
        unreal.log_error(f"\n WARNING: {total - passed} test(s) failed!")
        unreal.log_error("Please review the integration and fix issues before deployment.")
        return False


# Run tests when script is executed
if __name__ == "__main__":
    success = run_all_tests()

    if success:
        unreal.log("\n NEXT STEPS:")
        unreal.log("1. Test in actual positioning workflow (run a panel through iterative loop)")
        unreal.log("2. Verify logs show view selection strategy changes")
        unreal.log("3. Confirm hero camera is always included in captures")
        unreal.log("4. Monitor cost savings in logs")
        unreal.log("\nTo disable feature (for A/B testing):")
        unreal.log("Set self.use_intelligent_view_selection = False in __init__")
