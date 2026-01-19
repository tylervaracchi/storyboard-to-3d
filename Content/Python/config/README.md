# API & Configuration System - Documentation

## 🔒 Security-First Design

The StoryboardTo3D plugin now features a professional, secure API and configuration management system.

## 📁 File Structure

```
/config/
    config_manager.py    # Centralized configuration management
    __init__.py         # Package exports

/api/
    ai_client.py        # Optimized AI client with secure key handling
    __init__.py         # Package exports

/ui/
    settings_dialog.py  # Professional settings interface

.env.example           # Template for environment variables
.gitignore            # Excludes .env files from version control
```

## 🔑 API Key Management

### Environment Variables (Recommended)

1. **Create `.env` file** in your home directory:
   ```
   ~/.storyboard_to_3d/.env
   ```

2. **Add your API keys**:
   ```bash
   OPENAI_API_KEY=sk-your-openai-key-here
   ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
   ```

3. **Keys are automatically loaded** on startup

### Settings Dialog

1. Open Settings: `Edit → Settings` or `Ctrl+,`
2. Go to API tab
3. Enter API key (will be saved securely)
4. Click "Test Connection"

## ⚙️ Configuration System

### Configuration Locations

- **Settings**: `~/.storyboard_to_3d/settings.json`
- **Environment**: `~/.storyboard_to_3d/.env`
- **Backup**: Auto-created in config directory

### Configuration Categories

#### API Settings
```python
"api": {
    "provider": "OpenAI GPT-4 Vision",
    "timeout": 30,
    "max_retries": 3,
    "max_tokens": 500
}
```

#### UI Settings
```python
"ui": {
    "theme": "dark",
    "window_width": 1800,
    "window_height": 900,
    "auto_save": true,
    "auto_save_interval": 300
}
```

#### Generation Settings
```python
"generation": {
    "default_panel_duration": 3.0,
    "create_cameras": true,
    "create_lights": true,
    "use_hdri": true
}
```

#### Project Settings
```python
"project": {
    "content_root": "/Game/StoryboardTo3D",
    "auto_sync_content_browser": true,
    "backup_on_save": true
}
```

## 🎯 Usage Examples

### Python API

```python
from config import get_config, get, set, get_api_key

# Get configuration instance
config = get_config()

# Get values
theme = get("ui.theme")
provider = get("api.provider")

# Set values
set("ui.window_width", 1920)
set("generation.default_panel_duration", 5.0)

# API keys
api_key = get_api_key("OpenAI GPT-4 Vision")
```

### AI Client

```python
from api.ai_client import create_ai_client

# Create client (uses config automatically)
client = create_ai_client()

# Test connection
success, message = client.test_connection()

# Analyze panel
analysis = client.analyze_panel("path/to/panel.jpg")

# Analyze script
script_data = client.analyze_script(script_text)
```

## 🛡️ Security Features

1. **No Hardcoded Keys**: All API keys in environment variables
2. **Masked Display**: Keys shown as bullets in UI
3. **Secure Storage**: Keys never saved in plain text
4. **Git Ignored**: .env files excluded from version control
5. **Fallback Support**: Works without API (mock mode)

## 🔧 Advanced Features

### Import/Export Settings

```python
# Export settings
config.export_config("my_settings.json")

# Import settings
config.import_config("my_settings.json")
```

### Reset to Defaults

```python
# Reset all settings
config.reset_to_defaults()

# Reset specific section
config.reset_to_defaults("api")
```

### Connection Testing

```python
# Test API connection
client = create_ai_client()
success, message = client.test_connection()
print(message)  # ✅ OpenAI GPT-4 Vision connection successful
```

## 🚀 Quick Start

1. **Copy `.env.example`** to `~/.storyboard_to_3d/.env`
2. **Add your API keys** to `.env`
3. **Launch UI**: `import main; main.show_window()`
4. **Open Settings**: `Edit → Settings`
5. **Test Connection**: Click "Test Connection" in API tab

## 📊 Benefits

- ✅ **Professional**: Enterprise-grade configuration management
- ✅ **Secure**: API keys never exposed in code
- ✅ **Flexible**: Multiple configuration sources
- ✅ **User-Friendly**: Intuitive settings dialog
- ✅ **Robust**: Retry logic and error handling
- ✅ **Testable**: Mock mode for development

## 🧪 Testing

Run the test suite:
```python
import test_optimized_api
test_optimized_api.main()
```

This will:
- Test configuration system
- Test AI client
- Create example .env file
- Test settings dialog
- Verify all optimizations

## 📝 Notes

- Environment variables take precedence over config file
- Settings are auto-saved on dialog close
- Mock mode activates when no API key is found
- All paths support both Windows and Unix
