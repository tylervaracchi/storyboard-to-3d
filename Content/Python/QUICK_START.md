# Quick Start - OpenAI API Fixed & Ready
**Get up and running in 5 minutes**

## Step 1: Install Dependencies (2 minutes)

```bash
cd Plugins\StoryboardTo3D\Content\Python
pip install -r requirements.txt
```

**Required packages:**
- `requests` - HTTP client
- `tiktoken` - Token counting
- `json-repair` - JSON parsing
- `tenacity` - Retry logic

---

## Step 2: Set Your API Key (1 minute)

### Option A: Via Unreal Settings (Recommended)

1. Open Unreal Editor
2. Go to: **Tools → StoryboardTo3D Settings**
3. Navigate to **AI** tab
4. Enter your OpenAI API key
5. Select provider: **OpenAI GPT-4o** or **OpenAI GPT-5**
6. Click **Test Connection**

### Option B: Via Python

```python
from core.settings_manager import set_setting, save_settings

# Set API key
set_setting('ai_settings.openai_api_key', 'sk-your-actual-key-here')

# Set provider
set_setting('ai_settings.active_provider', 'OpenAI GPT-5')

# Set model
set_setting('ai_settings.openai_model', 'gpt-5')

# Save
save_settings()
```

### Option C: Environment Variable

```cmd
# Windows
set OPENAI_API_KEY=sk-your-actual-key-here

# Linux/Mac
export OPENAI_API_KEY=sk-your-actual-key-here
```

---

## Step 3: Test Connection (1 minute)

```python
from api.ai_client import AIClient

# Auto-loads from settings
client = AIClient()

# Test connection
success, message = client.test_connection()
print(message)

# Should print: ✅ Connection successful
```

---

## Step 4: Run Integration Tests (1 minute)

```bash
python tests\test_openai_integration.py
```

**Expected output:**
```
✅ API Key Validation
✅ Model Detection
✅ Model Availability
✅ JSON Output
...
✅ ALL TESTS PASSED - Production ready!
```

---

## Step 5: Use in Your Code

### Basic Text Request

```python
from api.ai_client import AIClient

client = AIClient()
response = client._make_request("Explain storyboarding in 20 words")
print(response)
```

### Image Analysis

```python
import base64
from api.ai_client import AIClient

# Load image
with open('storyboard_panel.png', 'rb') as f:
    image_data = base64.b64encode(f.read()).decode('utf-8')

# Analyze
client = AIClient()
response = client._make_request(
    "Describe this storyboard panel",
    image_base64=image_data
)
print(response)
```

### With Token Validation

```python
from utils.token_counter import TokenCounter
from api.ai_client import AIClient

prompt = "Your very long prompt here..."

# Check token count
counter = TokenCounter("gpt-4o")
validation = counter.validate_request(prompt, max_output_tokens=1000)

if validation['valid']:
    client = AIClient()
    response = client._make_request(prompt, max_tokens=1000)
else:
    print(f"⚠️ {validation['recommendation']}")
```

---

## What's Fixed?

✅ **GPT-5 model detection** (o3, o4 correctly identified)  
✅ **Response parsing** (robust multi-strategy extraction)  
✅ **Pro model support** (automatic "high" reasoning for -pro models)  
✅ **Exponential backoff** (intelligent retry logic)  
✅ **Settings integration** (reads from your global_settings.json)  
✅ **Error handling** (request IDs, better logging)  
✅ **Token counting** (prevent context overflow)  

---

## Common Issues & Quick Fixes

### "No API key configured"
```python
# Check settings
from core.settings_manager import get_setting
key = get_setting('ai_settings.openai_api_key', '')
print(f"Key status: {'Found' if key else 'Missing'}")
```

### "Model not found"
```python
# Verify model name
client = AIClient()
print(f"Using model: {client.model}")
print(f"Endpoint: {client.endpoint}")
```

### Empty responses
```python
# Enable debug logging (already in code)
# Look for [_make_request] and [_parse_response] in console
```

### Rate limits (429)
```python
# Already handled with exponential backoff
# Wait times: 1s, 2s, 4s, 8s (automatic)
```

---

## Next Steps

1. ✅ **Read full guide:** `OPENAI_DEBUGGING_GUIDE.md`
2. ✅ **Check settings:** `SETTINGS_INTEGRATION.md`
3. ✅ **Review fixes:** `FIXES_APPLIED.md`
4. ✅ **Run your Phase 1 tests:**
   ```python
   exec(open(r"tests\positioning\test_phase1_ai_io.py").read())
   ```

---

## Support

- **Debugging:** See `OPENAI_DEBUGGING_GUIDE.md`
- **Settings:** See `SETTINGS_INTEGRATION.md`
- **Technical details:** See `FIXES_APPLIED.md`

**You're production-ready! 🚀**
