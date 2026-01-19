# AI-Driven Positioning System - Test Suite

Complete test suite for building and validating AI-driven actor positioning in Unreal Engine.

## 🎯 Overview

This test suite implements **incremental, solid testing** of AI positioning:

1. ✅ **Phase 1**: AI Input/Output (text & image analysis)
2. ✅ **Phase 2**: Actor Movement (transform API)
3. ✅ **Phase 3**: Scene Capture (viewport screenshots)
4. ✅ **Phase 4**: Single Iteration (complete cycle)
5. ✅ **Phase 5**: Iterative Loop (convergence system)

## 🚀 Quick Start

### Run All Tests

```python
# In Unreal Python console
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\run_all_positioning_tests.py').read())
```

### Run Individual Phase

```python
# Phase 1 only
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase1_ai_io.py').read())

# Phase 2 only
exec(open(r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python\tests\positioning\test_phase2_movement.py').read())

# ... and so on
```

## 📋 Phase Details

### Phase 1: AI Input/Output Testing

**What it tests:**
- AI can receive text prompts and return JSON
- AI can analyze images
- AI can compare two images (storyboard vs scene)
- JSON parsing and validation

**Expected output:**
```
✅ Basic Prompt: AI returned valid JSON
✅ Image Analysis: Response structure valid
✅ Two-Image Comparison: Comparison analysis complete
```

**What to check:**
- AI provider is configured in settings
- API keys are valid
- JSON response format is correct

---

### Phase 2: Actor Movement Testing

**What it tests:**
- Spawning actors programmatically
- Moving actors via Python API
- Rotating actors
- Creating sequences
- Adding actors to sequences as spawnables
- Keyframing transforms
- Programmatic transform updates

**Expected output:**
```
✅ Spawned actor
✅ Actor moved successfully
✅ Actor rotated successfully
✅ Sequence created
✅ Added to sequence
✅ Transform keyframes added
```

**What to check:**
- EditorActorSubsystem is accessible
- Transform changes persist
- Sequence system works

---

### Phase 3: Scene Capture Testing

**What it tests:**
- Viewport screenshot capture
- Camera perspective capture
- High-resolution capture
- Image encoding for AI
- SceneCapture2D component
- Multi-angle capture

**Expected output:**
```
✅ Viewport screenshot captured
✅ Camera perspective captured
✅ High-res capture completed
✅ Image encoded for AI (size check)
✅ SceneCapture2D accessible
✅ Multi-angle capture complete
```

**What to check:**
- Screenshots saved to: `Saved/Screenshots/`
- File sizes reasonable for AI APIs (< 20MB)
- LevelEditorSubsystem camera locking works

---

### Phase 4: Single Iteration Testing

**What it tests:**
- Complete positioning cycle:
  1. Spawn actor in wrong position
  2. Capture scene state
  3. Send to AI for analysis
  4. Parse positioning instructions
  5. Apply adjustments
  6. Verify improvement

**Expected output:**
```
Step 1: ✅ Spawned test scene
Step 2: ✅ Captured scene
Step 3: ✅ AI analysis complete (similarity: 0.X)
Step 4: ✅ Actor repositioned
Step 5: ✅ Distance to target: XX units
```

**What to check:**
- Actor actually moves based on AI instructions
- JSON parsing works correctly
- Distance to target decreases

---

### Phase 5: Iterative Loop Testing

**What it tests:**
- Multiple positioning iterations
- Convergence detection
- Similarity tracking
- Stopping criteria (max iterations OR threshold reached)
- Iteration history logging

**Expected output:**
```
Iteration 1: Similarity=0.30, Distance=450
Iteration 2: Similarity=0.55, Distance=280
Iteration 3: Similarity=0.72, Distance=150
Iteration 4: Similarity=0.88, Distance=85
✅ CONVERGED after 4 iterations!

Improvement: 450 → 85 units (81% improvement)
```

**What to check:**
- System stops at convergence threshold
- Similarity increases over iterations
- Objective distance decreases
- Iteration log saved with full data

---

## 📊 Understanding Results

### Success Indicators

✅ **All phases pass**: System is production-ready
✅ **Phases 1-4 pass**: Core functionality works, optimize Phase 5
⚠️ **Phases 1-3 pass**: Basic components work, debug Phase 4
❌ **Phase 1 fails**: Fix AI configuration first

### Common Issues

#### Phase 1 Failures
- **AI provider not initialized**: Check Settings → AI tab
- **API key invalid**: Test connection in settings
- **JSON parsing fails**: AI returning non-JSON text (add extraction logic)

#### Phase 2 Failures
- **Actor doesn't move**: Check EditorActorSubsystem available
- **Sequence creation fails**: Check asset creation permissions
- **Transform doesn't update**: Verify UE 5.6 API compatibility

#### Phase 3 Failures
- **Screenshot not found**: Async timing issue (increase sleep time)
- **Camera lock fails**: LevelEditorSubsystem not available
- **Image too large**: Enable compression or reduce resolution

#### Phase 4 Failures
- **AI doesn't return adjustments**: Prompt may need refinement
- **Actor position unchanged**: Check delta vs absolute positioning
- **Capture fails mid-iteration**: Viewport locked/unlocked issue

#### Phase 5 Failures
- **Doesn't converge**: Lower threshold or increase max iterations
- **Similarity doesn't increase**: AI prompt needs better guidance
- **Crashes after N iterations**: Memory leak or API rate limiting

---

## 🔧 Configuration

### Required Settings

1. **AI Provider**: Settings → AI Settings
   - Provider: OpenAI, Claude, or LLaVA
   - API Key: Valid and tested
   - Model: GPT-4V, Claude Sonnet 4, or similar vision model

2. **Test Data**:
   - At least one storyboard panel in a Show folder
   - Or the tests will work without reference images (synthetic mode)

3. **Unreal Settings**:
   - Python plugins enabled
   - EditorScripting utilities enabled

### Optional Tuning

**Phase 5 Parameters:**
```python
system = IterativePositioningSystem(
    max_iterations=5,           # Safety limit
    convergence_threshold=0.85  # 0.0-1.0 similarity target
)
```

**Capture Resolution:**
```python
options.resolution = unreal.Vector2D(1280, 720)  # Adjust for quality vs size
```

---

## 📁 Test Outputs

All tests save data to: `Saved/PositioningTests/`

### Screenshots
- `Saved/Screenshots/phase4_current_scene_*.png`
- `Saved/Screenshots/iteration_01_*.png`

### Iteration Logs
- `Saved/PositioningTests/Iterations/iteration_log_*.json`
  - Contains full iteration history
  - Similarity progression
  - Position changes
  - AI responses

### Test Reports
- `Saved/PositioningTests/test_report_*.json`
  - Overall pass/fail
  - Phase-by-phase results
  - Timing information

---

## 🎓 Understanding the System

### Convergence Logic

The system stops iterating when:

1. **Threshold reached**: `similarity >= 0.85` (configurable)
2. **Plateau detected**: < 5% improvement in last 3 iterations
3. **Max iterations**: Safety limit reached (prevents infinite loops)

### Similarity Scoring

AI provides similarity score (0.0 - 1.0):
- **0.0-0.3**: Very wrong positioning
- **0.3-0.6**: Partially correct
- **0.6-0.8**: Close, needs refinement
- **0.8-1.0**: Target achieved

### Position Adjustments

AI provides **delta adjustments** (relative):
```json
{
  "position_delta": {"x": -50, "y": 20, "z": 0},
  "rotation_delta": {"yaw": -15}
}
```

Not absolute positions (except Phase 4 for simplicity).

---

## 🚦 Next Steps After Testing

### If All Tests Pass

1. **Integrate into production**:
   - Add positioning system to `scene_builder.py`
   - Hook into Generate button workflow
   - Add progress UI for iterations

2. **Enhance**:
   - Multi-actor positioning
   - Storyboard comparison (not synthetic target)
   - Camera positioning too
   - Shot-type aware positioning

3. **Optimize**:
   - Cache AI responses
   - Batch process multiple panels
   - Reduce API calls with smarter prompts

### If Some Tests Fail

1. **Fix fundamentals first** (Phases 1-3)
2. **Debug single iteration** (Phase 4)
3. **Then tackle loop** (Phase 5)

---

## 🆘 Troubleshooting

### AI Not Responding
```python
# Test AI manually
from core.settings_manager import get_settings
from api.ai_client_enhanced import EnhancedAIClient

settings = get_settings()
ai_settings = settings.get('ai_settings', {})

# Extract provider and API key
provider = ai_settings.get('active_provider', 'OpenAI GPT-4 Vision')
api_key = ai_settings.get('openai_api_key') or ai_settings.get('anthropic_api_key')

# Create client with correct parameters
client = EnhancedAIClient(provider=provider, api_key=api_key)

# Try simple prompt
response = client.analyze_text("Hello, respond with: {'status': 'working'}")
print(response)
```

### Capture Not Working
```python
# Test viewport screenshot manually
import unreal
automation_lib = unreal.AutomationLibrary()
options = unreal.AutomationScreenshotOptions()
options.resolution = unreal.Vector2D(800, 600)
automation_lib.take_automation_screenshot("manual_test", options)
# Check Saved/Screenshots/
```

### Actor Not Moving
```python
# Test direct movement
import unreal
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
if actors:
    actor = actors[0]
    actor.set_actor_location(unreal.Vector(0, 0, 100), False, False)
    print(f"Moved to: {actor.get_actor_location()}")
```

---

## 📚 Additional Resources

- **Main Plugin**: `Plugins/StoryboardTo3D/Content/Python/`
- **Scene Builder**: `core/scene_builder.py`
- **AI Client**: `api/ai_client_enhanced.py`
- **Settings**: UI → Settings → AI tab

---

## ✅ Success Criteria

Your positioning system is ready when:

- [ ] All 5 phases pass
- [ ] Iterations converge (Phase 5)
- [ ] Distance to target decreases consistently
- [ ] AI responses are valid JSON
- [ ] Screenshots captured correctly
- [ ] Actors move based on AI instructions

---

**Built with solid, incremental testing methodology** ✨
