# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Gen3D Package

Optional generative text-to-3D fallback for the asset matcher: when the
asset library has no match for a described entity, a configured provider
(Meshy or Tripo3D) can generate a model, which is downloaded, imported
into /Game/StoryboardTo3D/Generated, recorded in a reuse manifest, and
registered in the in-memory asset cache.

The feature is opt-in via the 'gen3d.enabled' setting (default False);
see gen3d_factory.get_configured() for the full configuration surface.
Every module here guards its 'import unreal' so the package is importable
outside the Unreal Editor.

Public API:
    get_configured()          -> configured provider instance or None
    Gen3DProvider, Gen3DError -> base class / error type
    MeshyProvider, TripoProvider
    import_generated_model(file_path, asset_name) -> asset path or None
    manifest.lookup(description) / manifest.record(description, path, provider)
"""

from .base_provider import Gen3DProvider, Gen3DError
from .meshy_provider import MeshyProvider
from .tripo_provider import TripoProvider
from .gen3d_factory import get_configured
from .importer import import_generated_model, sanitize_asset_name
from . import manifest

__all__ = [
    'Gen3DProvider',
    'Gen3DError',
    'MeshyProvider',
    'TripoProvider',
    'get_configured',
    'import_generated_model',
    'sanitize_asset_name',
    'manifest',
]
