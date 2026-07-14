# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GenAnim Package

Optional generative text-to-animation fallback for the animation
matcher, mirroring core/gen3d: when the show's animation_library.json
has no clip for a character's action text, a configured provider (Tripo
animate_retarget presets or DeepMotion SayMotion text2motion) can
generate a clip, which is downloaded, imported into
/Game/StoryboardTo3D/GeneratedAnims, recorded in a reuse manifest, and
registered back into the animation library.

The feature is opt-in via the 'genanim.enabled' setting (default False);
see genanim_factory.get_configured() for the full configuration surface.
Imported clips arrive on the provider's skeleton; retargeting onto
project characters uses UE5's standard IK Retargeter workflow (see
importer.py). Every module here guards its 'import unreal' so the
package is importable outside the Unreal Editor.

Public API:
    get_configured()             -> configured provider instance or None
    GenAnimProvider, GenAnimError -> base class / error type
    TripoAnimProvider, DeepMotionProvider
    import_generated_animation(file_path, asset_name) -> asset path or None
    manifest.lookup(action_text) / manifest.record(action_text, path, provider)
"""

from .base_provider import GenAnimProvider, GenAnimError
from .tripo_provider import TripoAnimProvider, map_action_to_preset
from .deepmotion_provider import DeepMotionProvider
from .genanim_factory import get_configured
from .importer import import_generated_animation, sanitize_asset_name
from . import manifest

__all__ = [
    'GenAnimProvider',
    'GenAnimError',
    'TripoAnimProvider',
    'DeepMotionProvider',
    'map_action_to_preset',
    'get_configured',
    'import_generated_animation',
    'sanitize_asset_name',
    'manifest',
]
