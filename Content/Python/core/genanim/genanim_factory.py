# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GenAnim Factory

Builds a configured generative text-to-animation provider from plugin
settings, mirroring core/gen3d/gen3d_factory.py: a classlessly-callable
get_configured() that returns an instance or None and never raises.

Settings (read via core.settings_manager.get_setting):
  genanim.enabled   default False. The feature is opt-in; when off (or
                    the settings system is unavailable) get_configured()
                    returns None and callers behave exactly as before.
  genanim.provider  'tripo' (default, alias 'tripo3d') or 'deepmotion'
                    (alias 'saymotion').

A provider is only returned when it also reports itself available:
  tripo:       TRIPO_API_KEY (or plugin config) AND a rig task id
               (TRIPO_RIG_TASK_ID / 'genanim.tripo_rig_task_id').
  deepmotion:  DEEPMOTION_CLIENT_ID + DEEPMOTION_CLIENT_SECRET (or plugin
               config) AND the partner-issued base URL
               (DEEPMOTION_API_BASE / 'genanim.deepmotion_base_url').
"""

from typing import Optional

try:
    import unreal
except ImportError:
    unreal = None


def _log(message):
    """Log an info message via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def _log_warning(message):
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {}".format(message))


def _is_truthy(value):
    # type: (object) -> bool
    """Interpret a setting value as a boolean. Accepts real booleans and
    the usual string spellings; everything else is False."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'enabled')


def get_configured():
    # type: () -> Optional[object]
    """
    Build a GenAnimProvider from the 'genanim.*' global settings.

    Returns:
        A ready provider instance (Tripo or DeepMotion), or None when the
        feature is disabled (the default), the provider name is
        unrecognized, the provider is not fully configured, or settings
        cannot be read. Never raises.
    """
    try:
        from core.settings_manager import get_setting
    except Exception as e:
        _log_warning("[GenAnim] Settings manager unavailable: {}. "
                     "Generative animation disabled.".format(e))
        return None

    try:
        enabled = get_setting('genanim.enabled', False)
    except Exception as e:
        _log_warning("[GenAnim] Could not read 'genanim.enabled': {}. "
                     "Generative animation disabled.".format(e))
        return None

    if not _is_truthy(enabled):
        return None

    try:
        provider_name = get_setting('genanim.provider', 'tripo')
    except Exception as e:
        _log_warning("[GenAnim] Could not read 'genanim.provider': {}. "
                     "Defaulting to 'tripo'.".format(e))
        provider_name = 'tripo'

    provider_name = str(provider_name or 'tripo').strip().lower()

    try:
        from .tripo_provider import TripoAnimProvider
        from .deepmotion_provider import DeepMotionProvider
    except Exception as e:
        _log_warning("[GenAnim] Provider modules unavailable: {}. "
                     "Generative animation disabled.".format(e))
        return None

    provider_map = {
        'tripo': TripoAnimProvider,
        'tripo3d': TripoAnimProvider,
        'deepmotion': DeepMotionProvider,
        'saymotion': DeepMotionProvider
    }

    provider_class = provider_map.get(provider_name)
    if provider_class is None:
        _log_warning("[GenAnim] Unknown genanim.provider value '{}' "
                     "(expected 'tripo' or 'deepmotion'). Generative "
                     "animation disabled.".format(provider_name))
        return None

    try:
        provider = provider_class()
    except Exception as e:
        _log_warning("[GenAnim] Failed to construct provider '{}': {}. "
                     "Generative animation disabled.".format(
                         provider_name, e))
        return None

    try:
        available = provider.is_available()
    except Exception as e:
        _log_warning("[GenAnim] Provider '{}' availability check failed: "
                     "{}. Generative animation disabled.".format(
                         provider_name, e))
        return None

    if not available:
        _log_warning("[GenAnim] genanim.enabled is set but provider '{}' is "
                     "not fully configured (see the key / rig id / base URL "
                     "requirements in genanim_factory.py). Generative "
                     "animation disabled.".format(provider_name))
        return None

    _log("[GenAnim] Provider configured: {}. {}".format(
        provider.name, provider.pricing_note))
    return provider
