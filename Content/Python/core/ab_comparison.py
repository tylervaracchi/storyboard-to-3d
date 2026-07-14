# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
A/B Provider Comparison Utility

Runs the same storyboard analysis/generation callable against two different
AI providers on the same panel, isolating each run by snapshotting and
restoring the transforms of every actor tagged 'StoryboardGenerated' in the
current editor level. This lets a user compare, side by side, how two models
(for example GPT-4o vs Claude Sonnet) position the same scene without one
run contaminating the other.

This module is a pure orchestration utility. It deliberately takes callables
and provider objects as arguments so it never has to import the UI layer.

Intended UI usage (from a widget such as active_panel_widget):

    from core.ab_comparison import ABComparison
    from core.ai_providers.provider_factory import AIProviderFactory

    provider_a = AIProviderFactory.create_provider('gpt4v')
    provider_b = AIProviderFactory.create_provider('claude')

    def analyze_fn(panel_image, provider):
        # The widget adapts its existing analyze/generate pipeline here,
        # pointing it at the supplied provider for this one pass. It should
        # return a dict summary (match_score, iterations, cost, etc.).
        return widget.run_positioning_pass(panel_image, ai_client=provider)

    comparison = ABComparison()
    outcome = comparison.run_comparison(
        panel_image, provider_a, provider_b, analyze_fn
    )
    # outcome['a'] and outcome['b'] each hold:
    #   provider label, placed-actor counts, extracted scores, raw result,
    #   elapsed time, error (if any), and snapshot-restore statistics.
    # The widget can then render both summaries side by side.

Notes:
- The snapshot records transforms of currently tagged actors. Restore puts
  those transforms back and removes tagged actors that appeared during a
  run. Tagged actors destroyed during a run cannot be resurrected; those
  are logged and counted in the restore stats.
- Outside the Unreal Editor (no 'unreal' module) the snapshot/restore steps
  become logged no-ops so the comparison logic itself stays testable.
"""

import time
from typing import Any, Callable, Dict, List, Optional

# Guard the unreal import so this module can be imported outside the editor
# (for example in unit tests of the orchestration logic).
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False

STORYBOARD_TAG = 'StoryboardGenerated'

# Numeric score keys we know how to surface from a callable's result dict.
SCORE_KEYS = (
    'match_score',
    'initial_accuracy',
    'final_accuracy',
    'improvement',
    'score',
    'accuracy',
    'composite_objective_score',
    'ssim',
    'psnr',
    'mse',
    'total_iterations',
    'iterations',
    'total_cost',
    'cost',
)


def _log(message):
    """Log info through unreal when available, else print."""
    if UNREAL_AVAILABLE:
        unreal.log(f"[ABComparison] {message}")
    else:
        print(f"[ABComparison] {message}")


def _log_warning(message):
    """Log warning through unreal when available, else print."""
    if UNREAL_AVAILABLE:
        unreal.log_warning(f"[ABComparison] {message}")
    else:
        print(f"[ABComparison] WARNING: {message}")


class ABComparison:
    """
    Orchestrates an A/B comparison of two AI providers on one panel.

    The comparison flow:
        1. Snapshot transforms of all 'StoryboardGenerated' tagged actors.
        2. Run analyze_fn(panel_image, provider_a), capture its summary and
           the tagged-actor count it produced.
        3. Restore the snapshot (transforms back, new tagged actors removed).
        4. Run analyze_fn(panel_image, provider_b), capture likewise.
        5. Restore the snapshot again.
        6. Return {'a': {...}, 'b': {...}} for the UI to display.
    """

    def __init__(self):
        self._actor_subsystem = None

    # ------------------------------------------------------------------
    # Editor actor access (guarded for version differences and non-UE use)
    # ------------------------------------------------------------------

    def _get_actor_subsystem(self):
        """Get the EditorActorSubsystem, with logged fallbacks."""
        if not UNREAL_AVAILABLE:
            return None
        if self._actor_subsystem is not None:
            return self._actor_subsystem
        try:
            if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorActorSubsystem'):
                self._actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            else:
                _log_warning("EditorActorSubsystem not available in this engine version")
        except Exception as e:
            _log_warning(f"Could not get EditorActorSubsystem: {e}")
        return self._actor_subsystem

    def _get_all_level_actors(self) -> List[Any]:
        """Return all level actors using the best available API."""
        if not UNREAL_AVAILABLE:
            return []
        subsystem = self._get_actor_subsystem()
        if subsystem is not None:
            try:
                return list(subsystem.get_all_level_actors())
            except Exception as e:
                _log_warning(f"EditorActorSubsystem.get_all_level_actors failed: {e}")
        # Fallback for older engine versions
        if hasattr(unreal, 'EditorLevelLibrary'):
            try:
                _log_warning("Falling back to EditorLevelLibrary.get_all_level_actors")
                return list(unreal.EditorLevelLibrary.get_all_level_actors())
            except Exception as e:
                _log_warning(f"EditorLevelLibrary fallback failed: {e}")
        return []

    def _get_tagged_actors(self) -> List[Any]:
        """Return all actors tagged with STORYBOARD_TAG."""
        tagged = []
        for actor in self._get_all_level_actors():
            if actor is None:
                continue
            try:
                if hasattr(actor, 'tags') and STORYBOARD_TAG in actor.tags:
                    tagged.append(actor)
            except Exception:
                # A stale/garbage actor reference; skip it
                continue
        return tagged

    def _safe_path(self, actor) -> Optional[str]:
        """Return a stable identifier for an actor, or None."""
        try:
            if hasattr(actor, 'get_path_name'):
                return actor.get_path_name()
            if hasattr(actor, 'get_name'):
                return actor.get_name()
        except Exception:
            pass
        return None

    def _safe_label(self, actor) -> str:
        """Return a human-readable actor label for logging."""
        try:
            if hasattr(actor, 'get_actor_label'):
                return str(actor.get_actor_label())
            if hasattr(actor, 'get_name'):
                return str(actor.get_name())
        except Exception:
            pass
        return '<unknown actor>'

    def _destroy_actor(self, actor) -> bool:
        """Destroy an actor using the best available API."""
        if not UNREAL_AVAILABLE:
            return False
        subsystem = self._get_actor_subsystem()
        if subsystem is not None:
            try:
                return bool(subsystem.destroy_actor(actor))
            except Exception as e:
                _log_warning(f"destroy_actor via subsystem failed: {e}")
        if hasattr(unreal, 'EditorLevelLibrary'):
            try:
                _log_warning("Falling back to EditorLevelLibrary.destroy_actor")
                return bool(unreal.EditorLevelLibrary.destroy_actor(actor))
            except Exception as e:
                _log_warning(f"EditorLevelLibrary.destroy_actor failed: {e}")
        return False

    # ------------------------------------------------------------------
    # Snapshot / restore
    # ------------------------------------------------------------------

    def snapshot_tagged_actors(self) -> List[Dict[str, Any]]:
        """
        Snapshot transforms of all StoryboardGenerated-tagged actors.

        Returns:
            List of entries: {'actor', 'path', 'label', 'transform'}.
        """
        snapshot = []
        for actor in self._get_tagged_actors():
            path = self._safe_path(actor)
            if path is None:
                continue
            transform = None
            try:
                if hasattr(actor, 'get_actor_transform'):
                    transform = actor.get_actor_transform()
            except Exception as e:
                _log_warning(f"Could not read transform for {self._safe_label(actor)}: {e}")
            if transform is None:
                continue
            snapshot.append({
                'actor': actor,
                'path': path,
                'label': self._safe_label(actor),
                'transform': transform,
            })
        _log(f"Snapshotted {len(snapshot)} tagged actor transform(s)")
        return snapshot

    def restore_snapshot(self, snapshot: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Restore a snapshot taken by snapshot_tagged_actors().

        Puts saved transforms back on surviving snapshot actors and removes
        tagged actors that were spawned after the snapshot. Snapshot actors
        that were destroyed in the meantime cannot be restored; they are
        logged and counted.

        Returns:
            Stats dict: {'restored', 'removed', 'missing'}.
        """
        snap_by_path = {entry['path']: entry for entry in snapshot}
        current_paths = set()
        restored = 0
        removed = 0

        for actor in self._get_tagged_actors():
            path = self._safe_path(actor)
            if path is None:
                continue
            current_paths.add(path)
            entry = snap_by_path.get(path)
            if entry is not None:
                try:
                    if hasattr(actor, 'set_actor_transform'):
                        actor.set_actor_transform(entry['transform'], False, False)
                        restored += 1
                    else:
                        _log_warning(f"Actor {entry['label']} has no set_actor_transform")
                except Exception as e:
                    _log_warning(f"Could not restore transform for {entry['label']}: {e}")
            else:
                # Spawned during the run; remove it to get back to baseline
                label = self._safe_label(actor)
                if self._destroy_actor(actor):
                    removed += 1
                else:
                    _log_warning(f"Could not remove run-spawned actor {label}")

        missing = 0
        for entry in snapshot:
            if entry['path'] not in current_paths:
                missing += 1
                _log_warning(
                    f"Snapshot actor {entry['label']} no longer exists; cannot restore it"
                )

        _log(f"Restore: {restored} restored, {removed} removed, {missing} missing")
        return {'restored': restored, 'removed': removed, 'missing': missing}

    # ------------------------------------------------------------------
    # Result summarization
    # ------------------------------------------------------------------

    def _provider_label(self, provider) -> str:
        """Derive a display label for a provider object."""
        if provider is None:
            return 'None'
        try:
            if hasattr(provider, 'get_provider_info'):
                info = provider.get_provider_info()
                if isinstance(info, dict) and info.get('name'):
                    return str(info['name'])
        except Exception:
            pass
        for attr in ('name', 'model', 'provider'):
            try:
                value = getattr(provider, attr, None)
            except Exception:
                value = None
            if value:
                return str(value)
        return provider.__class__.__name__

    def _extract_scores(self, result) -> Dict[str, float]:
        """
        Pull any known numeric score fields out of a callable's result.

        Accepts a dict (including a nested 'scores' dict) or a bare number.
        Booleans are excluded; only int/float values are returned.
        """
        scores = {}
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            scores['score'] = float(result)
            return scores
        if not isinstance(result, dict):
            return scores

        sources = [result]
        nested = result.get('scores')
        if isinstance(nested, dict):
            sources.append(nested)

        for source in sources:
            for key in SCORE_KEYS:
                value = source.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    scores[key] = float(value)
        return scores

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_comparison(self,
                       panel_image: str,
                       provider_a: Any,
                       provider_b: Any,
                       analyze_fn: Callable[[str, Any], Any]) -> Dict[str, Any]:
        """
        Run the same analyze/generate callable against two providers.

        Args:
            panel_image: Path (or identifier) of the storyboard panel image
                that analyze_fn understands.
            provider_a: First AI provider object (e.g. from AIProviderFactory).
            provider_b: Second AI provider object.
            analyze_fn: Callable invoked as analyze_fn(panel_image, provider).
                Should return a dict summary; any dict is accepted and known
                numeric score fields are surfaced in 'scores'.

        Returns:
            {
                'panel_image': panel_image,
                'baseline_actor_count': int,
                'a': {per-run summary for provider_a},
                'b': {per-run summary for provider_b},
            }
            Each per-run summary contains: 'provider', 'result', 'scores',
            'placed_actor_count', 'spawned_during_run', 'elapsed_seconds',
            'error', and 'restore' stats.
        """
        if not callable(analyze_fn):
            raise TypeError("analyze_fn must be callable as analyze_fn(panel_image, provider)")

        snapshot = self.snapshot_tagged_actors()
        baseline_count = len(snapshot)

        outcome = {
            'panel_image': panel_image,
            'baseline_actor_count': baseline_count,
        }

        for key, provider in (('a', provider_a), ('b', provider_b)):
            label = self._provider_label(provider)
            _log(f"Running provider {key.upper()}: {label}")

            run_summary = {
                'provider': label,
                'result': None,
                'scores': {},
                'placed_actor_count': baseline_count,
                'spawned_during_run': 0,
                'elapsed_seconds': 0.0,
                'error': None,
                'restore': None,
            }

            start = time.time()
            try:
                result = analyze_fn(panel_image, provider)
                run_summary['result'] = result
                run_summary['scores'] = self._extract_scores(result)
            except Exception as e:
                run_summary['error'] = str(e)
                _log_warning(f"Provider {label} run failed: {e}")
            run_summary['elapsed_seconds'] = time.time() - start

            # Count what the run left in the level before restoring
            placed = len(self._get_tagged_actors())
            run_summary['placed_actor_count'] = placed
            run_summary['spawned_during_run'] = max(0, placed - baseline_count)

            # Put the level back to the snapshot state for the next run
            run_summary['restore'] = self.restore_snapshot(snapshot)

            outcome[key] = run_summary
            _log(
                f"Provider {label}: {placed} tagged actor(s) placed, "
                f"{run_summary['elapsed_seconds']:.1f}s, scores={run_summary['scores']}"
            )

        return outcome
