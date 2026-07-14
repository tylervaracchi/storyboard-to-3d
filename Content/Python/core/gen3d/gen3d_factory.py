# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Gen3D Factory

Builds a configured generative text-to-3D provider from plugin settings,
mirroring the shape of ExternalValidator.get_configured() in
core/external_validator.py: a classlessly-callable get_configured() that
returns an instance or None and never raises.

Settings (read via core.settings_manager.get_setting):
  gen3d.enabled   default False. The feature is opt-in; when off (or the
                  settings system is unavailable) get_configured() returns
                  None and callers behave exactly as before.
  gen3d.provider  'meshy' (default) or 'tripo' (alias 'tripo3d').

A provider is only returned when its API key is also resolvable
(MESHY_API_KEY / TRIPO_API_KEY environment variables, or the plugin
config pattern; see Gen3DProvider._resolve_api_key).
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
    Build a Gen3DProvider from the 'gen3d.*' global settings.

    Returns:
        A ready provider instance (Meshy or Tripo), or None when the
        feature is disabled (the default), the provider name is
        unrecognized, no API key is available, or settings cannot be
        read. Never raises.
    """
    try:
        from core.settings_manager import get_setting
    except Exception as e:
        _log_warning("[Gen3D] Settings manager unavailable: {}. "
                     "Generative 3D disabled.".format(e))
        return None

    try:
        enabled = get_setting('gen3d.enabled', False)
    except Exception as e:
        _log_warning("[Gen3D] Could not read 'gen3d.enabled': {}. "
                     "Generative 3D disabled.".format(e))
        return None

    if not _is_truthy(enabled):
        return None

    try:
        provider_name = get_setting('gen3d.provider', 'meshy')
    except Exception as e:
        _log_warning("[Gen3D] Could not read 'gen3d.provider': {}. "
                     "Defaulting to 'meshy'.".format(e))
        provider_name = 'meshy'

    provider_name = str(provider_name or 'meshy').strip().lower()

    try:
        from .meshy_provider import MeshyProvider
        from .tripo_provider import TripoProvider
    except Exception as e:
        _log_warning("[Gen3D] Provider modules unavailable: {}. "
                     "Generative 3D disabled.".format(e))
        return None

    provider_map = {
        'meshy': MeshyProvider,
        'tripo': TripoProvider,
        'tripo3d': TripoProvider
    }

    provider_class = provider_map.get(provider_name)
    if provider_class is None:
        _log_warning("[Gen3D] Unknown gen3d.provider value '{}' (expected "
                     "'meshy' or 'tripo'). Generative 3D disabled.".format(
                         provider_name))
        return None

    try:
        provider = provider_class()
    except Exception as e:
        _log_warning("[Gen3D] Failed to construct provider '{}': {}. "
                     "Generative 3D disabled.".format(provider_name, e))
        return None

    try:
        available = provider.is_available()
    except Exception as e:
        _log_warning("[Gen3D] Provider '{}' availability check failed: {}. "
                     "Generative 3D disabled.".format(provider_name, e))
        return None

    if not available:
        _log_warning("[Gen3D] gen3d.enabled is set but no API key was found "
                     "for provider '{}' (set MESHY_API_KEY / TRIPO_API_KEY "
                     "or the plugin config). Generative 3D disabled.".format(
                         provider_name))
        return None

    _log("[Gen3D] Provider configured: {}. {}".format(
        provider.name, provider.pricing_note))
    return provider
