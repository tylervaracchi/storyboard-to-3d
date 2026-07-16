# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tripo3D Animation Retarget Provider

Coded against the Tripo3D platform docs at
https://platform.tripo3d.ai/docs/animation and https://docs.tripo3d.ai/
(checked 2026-07-14). NOTE: the official docs pages are JavaScript
rendered and could not be fully machine-read at implementation time; the
endpoint, auth, and response envelope are shared with the already-shipped
text-to-3D tier (core/gen3d/tripo_provider.py), while the retarget body
shape and the preset list were cross-verified via the official
VAST-AI-Research tripo-js-sdk and are marked VERIFY-BEFORE-USE below.

Tripo is NOT prompt-driven for animation: it retargets clips from a fixed
preset library onto a previously RIGGED model. This provider therefore:

  1. Maps free action text to a preset via a keyword table
     (map_action_to_preset). No keyword hit means an honest failure,
     never a wrong clip.
  2. Creates an 'animate_retarget' task against a pre-provisioned rig
     task id and downloads the resulting FBX (the proxy character
     performing the preset, animation baked).

  Create task:  POST https://api.tripo3d.ai/v2/openapi/task
  Poll task:    GET  https://api.tripo3d.ai/v2/openapi/task/{task_id}
  Auth header:  Authorization: Bearer <TRIPO_API_KEY>   (keys begin 'tsk_')

  Create body (VERIFY-BEFORE-USE, cross-checked against the official
  tripo-js-sdk, fetched 2026-07-14):
    {"type": "animate_retarget",
     "original_model_task_id": "<rig task id>",
     "animations": ["preset:walk"],
     "out_format": "fbx",
     "bake_animation": true}

  Poll response: same {"code": 0, "data": {...}} envelope and status
  values as the text-to-3D tier; 'success' is the confirmed
  terminal-success status. Output URLs live under data.output; the key
  carrying the animated file for retarget tasks is best-known
  (VERIFY-BEFORE-USE): 'model' is tried first, then 'pbr_model',
  'base_model', and 'animation'.

ONE-TIME RIG SETUP (not automated here): run type=animate_prerigcheck
(free) then an animate_rig task with the Mixamo rig spec (25 credits,
about $0.25) on a proxy character model, and store the resulting rig
task id in the 'genanim.tripo_rig_task_id' setting or the
TRIPO_RIG_TASK_ID environment variable. Each retargeted clip then costs
10 credits (about $0.10). The Mixamo-style rig is the one UE5's IK
Retargeter auto-detects, so imported clips remap onto project characters
through the standard IK Retargeter workflow.

Known presets (from the SDK; full current list VERIFY-BEFORE-USE at
https://platform.tripo3d.ai/docs/animation): idle, walk, run, jump,
climb, slash, shoot, dive, hurt, fall, turn.

API key: TRIPO_API_KEY environment variable, then the plugin
config_manager pattern (see GenAnimProvider._resolve_api_key). The same
key as the gen3d Tripo tier; no new vendor onboarding.
"""

import os
import re
from typing import Any, Dict, Optional, Tuple

from .base_provider import GenAnimProvider, GenAnimError, _log, _log_warning

try:
    import unreal  # noqa: F401  (parity guard; not directly used here)
except ImportError:
    unreal = None


TRIPO_API_BASE = "https://api.tripo3d.ai/v2/openapi/task"
TRIPO_OUTPUT_PREFERENCE = ('model', 'pbr_model', 'base_model', 'animation')

# Ordered keyword table mapping action-text tokens to Tripo presets.
# First preset whose keyword set intersects the text's tokens wins, so
# more specific motions are listed before the idle catch-all.
TRIPO_PRESET_KEYWORDS = (
    ('preset:run', ('run', 'runs', 'running', 'sprint', 'sprinting',
                    'jog', 'jogging', 'dash', 'dashing', 'chase',
                    'chasing', 'flee', 'fleeing')),
    ('preset:walk', ('walk', 'walks', 'walking', 'stroll', 'strolling',
                     'wander', 'wandering', 'pace', 'pacing', 'march',
                     'marching', 'stride', 'striding')),
    ('preset:jump', ('jump', 'jumps', 'jumping', 'leap', 'leaping',
                     'hop', 'hopping', 'vault', 'vaulting', 'bound',
                     'bounding')),
    ('preset:climb', ('climb', 'climbs', 'climbing', 'scale', 'scales',
                      'scaling', 'clamber', 'clambering')),
    ('preset:fall', ('fall', 'falls', 'falling', 'trip', 'trips',
                     'tripping', 'collapse', 'collapses', 'collapsing',
                     'stumble', 'stumbles', 'stumbling', 'tumble',
                     'tumbles', 'tumbling')),
    ('preset:slash', ('slash', 'slashes', 'slashing', 'sword', 'swing',
                      'swings', 'swinging', 'attack', 'attacks',
                      'attacking', 'strike', 'strikes', 'striking',
                      'fight', 'fights', 'fighting', 'punch', 'punches',
                      'punching', 'brawl', 'brawling')),
    ('preset:shoot', ('shoot', 'shoots', 'shooting', 'fire', 'fires',
                      'firing', 'gun', 'aim', 'aims', 'aiming', 'bow')),
    ('preset:dive', ('dive', 'dives', 'diving', 'dodge', 'dodges',
                     'dodging', 'roll', 'rolls', 'rolling', 'lunge',
                     'lunges', 'lunging')),
    ('preset:hurt', ('hurt', 'wounded', 'injured', 'flinch', 'flinching',
                     'stagger', 'staggering', 'recoil', 'recoiling')),
    ('preset:turn', ('turn', 'turns', 'turning', 'spin', 'spins',
                     'spinning', 'pivot', 'pivots', 'pivoting')),
    ('preset:idle', ('idle', 'stand', 'stands', 'standing', 'wait',
                     'waits', 'waiting', 'still', 'stationary',
                     # Nearest-preset mappings: Tripo has no float/hover
                     # motion, but a gentle idle beats a frozen bind pose
                     # for ghosts and other floaters.
                     'float', 'floats', 'floating', 'hover', 'hovers',
                     'hovering', 'drift', 'drifts', 'drifting', 'glide',
                     'glides', 'gliding', 'bob', 'bobbing', 'fly',
                     'flies', 'flying', 'looms', 'looming')),
)


def map_action_to_preset(action_text):
    # type: (str) -> Optional[str]
    """
    Map free action text to a Tripo animation preset via keyword lookup.

    Args:
        action_text: Free-form action text ("the hero is sprinting away").

    Returns:
        A preset id like 'preset:run', or None when no keyword matches
        (callers should fail honestly rather than guess).
    """
    tokens = set(t for t in re.split(
        r'[^a-z0-9]+', str(action_text or '').lower()) if t)
    if not tokens:
        return None
    for preset, keywords in TRIPO_PRESET_KEYWORDS:
        if tokens.intersection(keywords):
            return preset
    return None


class TripoAnimProvider(GenAnimProvider):
    """Tripo3D animate_retarget provider
    (https://platform.tripo3d.ai/docs/animation)."""

    name = 'tripo'
    # Retarget body-shape toggle (VERIFY-BEFORE-USE ambiguity): the
    # official docs show a SINGULAR 'animation' field, the tripo-js-sdk
    # a plural 'animations' list. False = singular (primary).
    _retarget_body_alt = False

    def generate(self, action_text, **kwargs):
        # type: (str, **Any) -> Dict[str, Any]
        """Run the base generation; when the vendor task itself fails
        (accepted but errored server-side), retry ONCE with the
        alternate retarget body shape. Failed Tripo tasks are not
        charged, so the retry costs nothing extra on failure."""
        result = GenAnimProvider.generate(self, action_text, **kwargs)
        if (isinstance(result, dict) and result.get('status') == 'failed'
                and not self._retarget_body_alt
                and 'failed' in str(result.get('error', '')).lower()):
            _log_warning("[GenAnim] Tripo retarget failed with the primary "
                         "body shape; retrying once with the alternate "
                         "'animations' list form")
            self._retarget_body_alt = True
            try:
                result = GenAnimProvider.generate(self, action_text, **kwargs)
            finally:
                self._retarget_body_alt = False
        return result
    pricing_note = ("Tripo3D animate_retarget costs 10 credits (about $0.10) "
                    "per clip on a one-time rigged proxy character (rig: 25 "
                    "credits). Preset library only, not prompt-driven. "
                    "Pricing: https://docs.tripo3d.ai/get-started/pricing.html")

    def get_api_key(self):
        # type: () -> Optional[str]
        """TRIPO_API_KEY env var, then plugin config ('api.keys.tripo3d').
        Shared with the gen3d Tripo tier."""
        return self._resolve_api_key('TRIPO_API_KEY', 'tripo3d')

    def get_rig_task_id(self):
        # type: () -> Optional[str]
        """The pre-provisioned rig task id every retarget runs against:
        TRIPO_RIG_TASK_ID env var, then the 'genanim.tripo_rig_task_id'
        setting. See the one-time rig setup note in the module docstring."""
        rig_id = os.environ.get('TRIPO_RIG_TASK_ID')
        if rig_id:
            return str(rig_id).strip() or None
        rig_id = self._get_setting('genanim.tripo_rig_task_id', None)
        if rig_id:
            return str(rig_id).strip() or None
        return None

    def is_available(self):
        # type: () -> bool
        """Requires the API key. A rig task id is needed per call - either
        the character's own rig id (from the gen3d auto-rig chain, passed
        as a kwarg) or the global 'genanim.tripo_rig_task_id' setting;
        calls without either fail honestly at task creation."""
        return bool(self.get_api_key())

    # ------------------------------------------------------------------
    # GenAnimProvider hooks
    # ------------------------------------------------------------------

    def _headers(self):
        # type: () -> Dict[str, str]
        return {
            'Authorization': 'Bearer {}'.format(self.get_api_key()),
            'Content-Type': 'application/json'
        }

    def _create_task(self, action_text, **kwargs):
        # type: (str, **Any) -> str
        """Map the action text to a preset and create an animate_retarget
        task; returns the task id.

        kwargs['rig_task_id'] retargets onto a SPECIFIC character's own
        rig (produced by the gen3d auto-rig chain) so the clip comes back
        as that character performing the preset; without it the global
        pre-provisioned proxy rig from settings is used."""
        preset = map_action_to_preset(action_text)
        if not preset:
            raise GenAnimError(
                "No Tripo preset matches action text '{}' (presets cover "
                "locomotion/combat basics only)".format(
                    str(action_text)[:80]))

        rig_task_id = kwargs.get('rig_task_id') or self.get_rig_task_id()
        if not rig_task_id:
            raise GenAnimError(
                "No Tripo rig task id available (no per-character rig id "
                "and no TRIPO_RIG_TASK_ID / 'genanim.tripo_rig_task_id')")

        _log("[GenAnim] Tripo mapped action '{}' to {}".format(
            str(action_text)[:80], preset))

        # VERIFY-BEFORE-USE ambiguity between the official docs (singular
        # 'animation') and the tripo-js-sdk (plural 'animations' list);
        # generate() retries once with the alternate form when the task
        # itself fails server-side.
        body = {
            'type': 'animate_retarget',
            'original_model_task_id': rig_task_id,
            'out_format': 'fbx',
            'bake_animation': True,
            # Clips import ANIMATION-ONLY onto the character's existing
            # skeleton; shipping the mesh again just slows the download
            'export_with_geometry': False
        }
        if self._retarget_body_alt:
            body['animations'] = [preset]
        else:
            body['animation'] = preset

        data = self._request_json(
            'POST', TRIPO_API_BASE, headers=self._headers(), json_body=body)
        payload = self._unwrap(data)

        task_id = payload.get('task_id')
        if not task_id:
            raise GenAnimError(
                "Tripo create-task response had no task_id: {}".format(
                    str(data)[:200]))
        return str(task_id)

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        data = self._request_json(
            'GET', '{}/{}'.format(TRIPO_API_BASE, task_id),
            headers=self._headers())
        return self._unwrap(data)

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map Tripo status values to the base provider's states.

        'success' confirmed via the gen3d tier; other values best-known
        (VERIFY-BEFORE-USE, see module docstring). Unknown statuses keep
        polling until the timeout rather than aborting.
        """
        status = str(task_data.get('status', '')).strip().lower()

        if status == 'success':
            return 'succeeded', None
        if status in ('failed', 'cancelled', 'canceled', 'banned',
                      'expired', 'unknown'):
            return 'failed', 'status {}'.format(status)
        if status in ('queued', 'waiting', 'pending'):
            return 'pending', None
        if status in ('running', 'processing', 'generating'):
            return 'running', None

        _log_warning("[GenAnim] Unknown Tripo task status '{}'; continuing "
                     "to poll".format(status))
        return 'running', None

    def _clip_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Animated-file URLs live under data.output. The exact key for
        retarget tasks is VERIFY-BEFORE-USE; 'model' is tried first.
        Extension is sniffed from the URL with '.fbx' as the default
        (out_format=fbx is requested at create time)."""
        output = task_data.get('output')
        if not isinstance(output, dict):
            return None

        for key in TRIPO_OUTPUT_PREFERENCE:
            url = output.get(key)
            if url:
                return str(url), self._extension_from_url(url, default='.fbx')
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap(data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Unwrap Tripo's {"code": 0, "data": {...}} response envelope.
        A non-zero code is an API-level failure."""
        code = data.get('code', 0)
        if code != 0:
            raise GenAnimError("Tripo API returned code {}: {}".format(
                code, str(data.get('message', data))[:200]))

        payload = data.get('data')
        if not isinstance(payload, dict):
            raise GenAnimError(
                "Tripo response had no 'data' object: {}".format(
                    str(data)[:200]))
        return payload
