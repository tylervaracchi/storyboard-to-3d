# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Test: External Validator (opencv strategy)
Run inside the UE editor Python console:
    exec(open(r'<plugin>/Content/Python/tests/test_external_validator.py').read())

Exercises the free, local 'opencv' strategy (SceneMatcher wrapper) with
the two sample panels shipped in samples/. Does NOT call any paid API.
"""

import unreal
import sys
from pathlib import Path

# Add plugin Python root to path (tests/ -> Python/)
plugin_path = Path(__file__).parent.parent
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

# Plugin root (Python/ -> Content/ -> StoryboardTo3D/)
plugin_root = plugin_path.parent.parent
samples_dir = plugin_root / "samples"


def test_external_validator():
    """Test the ExternalValidator opencv strategy with sample images"""

    unreal.log("=" * 70)
    unreal.log("TEST: External Validator (opencv strategy)")
    unreal.log("=" * 70)

    passed = 0
    failed = 0

    try:
        from core.external_validator import ExternalValidator
    except Exception as e:
        unreal.log_error(f"Could not import ExternalValidator: {e}")
        return False

    sample_1 = samples_dir / "sample_panel_01.png"
    sample_2 = samples_dir / "sample_panel_02.png"

    if not sample_1.exists() or not sample_2.exists():
        unreal.log_error(f"Sample images not found in: {samples_dir}")
        unreal.log_error("Expected sample_panel_01.png and sample_panel_02.png")
        return False

    validator = ExternalValidator(strategy="opencv")

    # ------------------------------------------------------------------
    # Test 1: identical images should score very high
    # ------------------------------------------------------------------
    unreal.log("\n[Test 1] Identical images (panel 01 vs itself)...")
    result = validator.validate(str(sample_1), str(sample_1))
    unreal.log(f"  score:    {result['score']}")
    unreal.log(f"  strategy: {result['strategy']}")

    if result['score'] is not None and result['score'] >= 80:
        unreal.log("  PASS: identical images scored >= 80")
        passed += 1
    else:
        unreal.log_error(f"  FAIL: expected score >= 80, got {result['score']}")
        failed += 1

    # ------------------------------------------------------------------
    # Test 2: different panels should still return a valid 0-100 score
    # ------------------------------------------------------------------
    unreal.log("\n[Test 2] Different images (panel 01 vs panel 02)...")
    result = validator.validate(str(sample_1), str(sample_2))
    unreal.log(f"  score:    {result['score']}")
    if result['details'].get('aspects'):
        for aspect, data in result['details']['aspects'].items():
            unreal.log(f"  aspect {aspect}: {data.get('score', 'N/A')}")

    if result['score'] is not None and 0 <= result['score'] <= 100:
        unreal.log("  PASS: got a valid 0-100 score for differing images")
        passed += 1
    else:
        unreal.log_error(f"  FAIL: expected 0-100 score, got {result['score']}")
        failed += 1

    # ------------------------------------------------------------------
    # Test 3: agreement check against a hypothetical self-score of 84
    # (the value all models tended to report in the calibration study)
    # ------------------------------------------------------------------
    unreal.log("\n[Test 3] agrees_with_self_score(84, tolerance=15)...")
    agrees = validator.agrees_with_self_score(84, tolerance=15)
    external = result['score']
    expected = external is not None and abs(84 - external) <= 15
    unreal.log(f"  external score: {external}, agrees: {agrees}")

    if agrees == expected:
        unreal.log("  PASS: agreement result matches expectation")
        passed += 1
    else:
        unreal.log_error(f"  FAIL: expected agrees={expected}, got {agrees}")
        failed += 1

    # ------------------------------------------------------------------
    # Test 4: missing file must return score=None, never raise
    # ------------------------------------------------------------------
    unreal.log("\n[Test 4] Missing file (defensive failure path)...")
    try:
        result = validator.validate(str(samples_dir / "does_not_exist.png"),
                                    str(sample_1))
        if result['score'] is None and result['details'].get('error'):
            unreal.log("  PASS: missing file returned score=None with reason")
            passed += 1
        else:
            unreal.log_error(f"  FAIL: expected score=None, got {result}")
            failed += 1
    except Exception as e:
        unreal.log_error(f"  FAIL: validate() raised (must never raise): {e}")
        failed += 1

    # ------------------------------------------------------------------
    # Test 5: get_configured() honors the default 'off' setting
    # ------------------------------------------------------------------
    unreal.log("\n[Test 5] get_configured() with default settings...")
    try:
        from core.settings_manager import get_setting
        mode = get_setting('validation.external_validation', 'off')
        configured = ExternalValidator.get_configured()

        if str(mode).lower() == 'off':
            if configured is None:
                unreal.log("  PASS: setting is 'off' and get_configured() is None")
                passed += 1
            else:
                unreal.log_error("  FAIL: setting is 'off' but a validator was returned")
                failed += 1
        else:
            if configured is not None and configured.strategy == str(mode).lower():
                unreal.log(f"  PASS: setting '{mode}' produced matching validator")
                passed += 1
            else:
                unreal.log_error(f"  FAIL: setting '{mode}' but got {configured}")
                failed += 1
    except Exception as e:
        unreal.log_error(f"  FAIL: get_configured() check raised: {e}")
        failed += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    unreal.log("\n" + "=" * 70)
    unreal.log(f"RESULTS: {passed} passed, {failed} failed")
    unreal.log("=" * 70)

    return failed == 0


if __name__ == '__main__':
    test_external_validator()
