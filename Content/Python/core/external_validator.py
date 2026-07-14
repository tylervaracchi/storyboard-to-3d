# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
External Validator for StoryboardTo3D

WHY THIS MODULE EXISTS (SIGGRAPH 2026 Posters finding):
The calibration study behind this plugin showed that VLM self-scores are
NOT a reliable stop signal. All three tested models reported roughly
84/100 confidence regardless of actual output quality, while their real
positioning success rates ranged from 16.7% (GPT-4o) to 83.3%
(Claude Sonnet 4.5). The poster's first implication: pair VLMs with
external validators, do not trust self-scores alone.

This module provides that external validator. Three strategies:

  "opencv"        Local image comparison via ai_vision.scene_matcher
                  (PIL/numpy structural, color, lighting, and edge
                  comparison). Zero API cost.
  "second_model"  A DIFFERENT provider/model than the generator scores
                  the hero capture against the storyboard, returning
                  only a 0-100 score plus a one-sentence reason as JSON.
  "both"          Runs both and returns min(opencv, second_model) as
                  the conservative estimate.

Every failure path returns score=None with a logged reason. validate()
never raises.

------------------------------------------------------------------------
INTENDED INTEGRATION HOOK (documented, deliberately NOT wired yet):

  File:   Content/Python/ui/widgets/active_panel_widget.py
  Method: ActivePanelWidget._finish_capture_sequence()
          (defined around line 4756 at the time of writing)
  Where:  The early-stop accept-threshold check around lines 4849-4864,
          specifically this exact expression:

      should_stop_early = (self.last_match_score and
                           self.last_match_score > 80) or oscillation_detected

  Intended wiring: before honoring a self-score early stop, call
  ExternalValidator.get_configured(). If it returns a validator, run
  validator.validate(storyboard_path, hero_capture_path) and only allow
  the score-based early stop when the external score also clears the
  threshold, or validator.agrees_with_self_score(self.last_match_score)
  is True. If validation returns score=None, fall back to the current
  self-score-only behavior and log that external validation was skipped.

  A secondary hook is the checkpoint accept/revert logic in
  ActivePanelWidget._apply_ai_adjustments() (the block around lines
  4634-4703 that reads analysis.get('match_score')), where an external
  score could gate whether a "NEW BEST" checkpoint is saved.

  Wiring is left out of this pass on purpose: _finish_capture_sequence
  runs inside a QTimer-driven iteration loop in a nearly 7000-line
  widget, and adding a potentially slow or failing call there needs
  in-editor testing, not a blind edit.
------------------------------------------------------------------------

Usage:

    from core.external_validator import ExternalValidator

    validator = ExternalValidator(strategy="opencv")
    result = validator.validate(storyboard_path, capture_path)
    if result["score"] is not None:
        print(result["score"], result["details"])
        print(validator.agrees_with_self_score(self_score=84))
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# unreal is only available inside the editor. Guard it so this module can
# also be imported (and the opencv strategy unit-tested) outside UE.
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False


def _log(message):
    """Log info, falling back to print outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def _log_warning(message):
    """Log warning, falling back to print outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {}".format(message))


def _log_error(message):
    """Log error, falling back to print outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_error'):
        unreal.log_error(message)
    else:
        print("ERROR: {}".format(message))


class ExternalValidator:
    """
    Cross-checks a VLM's self-reported match score with an independent
    signal. See module docstring for the research motivation.
    """

    STRATEGIES = ('opencv', 'second_model', 'both')
    DEFAULT_TOLERANCE = 15

    # Scoring prompt for the second_model strategy. Asks ONLY for a
    # 0-100 score and a one-sentence reason, returned as JSON, so the
    # validator model cannot drift into positioning suggestions.
    SECOND_MODEL_PROMPT = (
        "You are an impartial validator. Image 1 is a storyboard panel "
        "(the target). Image 2 is a screenshot of a 3D scene that was "
        "built to match it. Rate how well image 2 matches image 1 in "
        "composition, subject placement, and content. Respond with ONLY "
        "a JSON object and no other text, in exactly this form: "
        '{"score": <number 0-100>, "reason": "<one sentence>"}'
    )

    def __init__(self, strategy='opencv', provider_name=None, provider_config=None):
        """
        Args:
            strategy: 'opencv', 'second_model', or 'both'
            provider_name: provider for the second_model strategy
                ('llava', 'gpt4v', 'claude', or 'auto'). Should be a
                DIFFERENT provider than the one generating the scene;
                a warning is logged if it matches the configured
                generator provider.
            provider_config: optional dict of extra kwargs passed to
                AIProviderFactory.create_provider (api_key, model, ...)
        """
        if strategy not in self.STRATEGIES:
            _log_warning(
                "[ExternalValidator] Unknown strategy '{}', "
                "falling back to 'opencv'".format(strategy))
            strategy = 'opencv'

        self.strategy = strategy
        self.provider_name = provider_name
        self.provider_config = dict(provider_config) if provider_config else {}
        self.last_result = None

        _log("[ExternalValidator] Initialized (strategy: {})".format(strategy))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, storyboard_path: str, capture_path: str) -> Dict[str, Any]:
        """
        Validate a hero capture against its storyboard panel.

        Args:
            storyboard_path: path to the storyboard panel image
            capture_path: path to the rendered hero capture image

        Returns:
            {
                'score': float or None,   # 0-100, None on any failure
                'strategy': str,          # strategy that produced it
                'details': dict           # per-strategy breakdown
            }
            Never raises. Every failure path logs a reason and returns
            score=None.
        """
        result = {
            'score': None,
            'strategy': self.strategy,
            'details': {}
        }

        try:
            path_error = self._check_paths(storyboard_path, capture_path)
            if path_error:
                _log_error("[ExternalValidator] {}".format(path_error))
                result['details']['error'] = path_error
                self.last_result = result
                return result

            if self.strategy == 'opencv':
                score, details = self._validate_opencv(storyboard_path, capture_path)
            elif self.strategy == 'second_model':
                score, details = self._validate_second_model(storyboard_path, capture_path)
            else:
                score, details = self._validate_both(storyboard_path, capture_path)

            result['score'] = score
            result['details'] = details

            if score is None:
                _log_warning(
                    "[ExternalValidator] Validation produced no score "
                    "(strategy: {}). Reason: {}".format(
                        self.strategy, details.get('error', 'unknown')))
            else:
                _log("[ExternalValidator] External score: {:.1f}/100 "
                     "(strategy: {})".format(score, self.strategy))

        except Exception as e:
            # Belt and braces: validate() must never raise.
            _log_error("[ExternalValidator] Unexpected failure: {}".format(e))
            result['score'] = None
            result['details'] = {'error': str(e)}

        self.last_result = result
        return result

    def agrees_with_self_score(self, self_score, tolerance: int = DEFAULT_TOLERANCE) -> bool:
        """
        Compare the model's self-reported score with the most recent
        external validation score.

        Args:
            self_score: the VLM's self-reported 0-100 match score
            tolerance: max allowed absolute gap (default 15 points)

        Returns:
            True only when a valid external score exists and it is
            within tolerance of the self-score. Any missing data
            returns False (the conservative answer: agreement is not
            confirmed).
        """
        if self.last_result is None:
            _log_warning("[ExternalValidator] agrees_with_self_score called "
                         "before validate(); returning False")
            return False

        external_score = self.last_result.get('score')
        if external_score is None:
            _log_warning("[ExternalValidator] No external score available; "
                         "cannot confirm agreement, returning False")
            return False

        if self_score is None:
            _log_warning("[ExternalValidator] self_score is None; "
                         "returning False")
            return False

        try:
            gap = abs(float(self_score) - float(external_score))
        except (TypeError, ValueError) as e:
            _log_warning("[ExternalValidator] Could not compare scores: "
                         "{}".format(e))
            return False

        agrees = gap <= tolerance
        _log("[ExternalValidator] Self-score {} vs external {:.1f}: gap {:.1f} "
             "({} tolerance {})".format(
                 self_score, external_score, gap,
                 "within" if agrees else "EXCEEDS", tolerance))
        return agrees

    @classmethod
    def get_configured(cls) -> Optional['ExternalValidator']:
        """
        Build a validator from the 'validation.external_validation'
        global setting (see core/settings_manager.py defaults).

        Setting values: 'off' (default), 'opencv', 'second_model', 'both'.

        Returns:
            An ExternalValidator instance, or None when the feature is
            off, the setting is unrecognized, or settings cannot be
            read. Never raises.
        """
        try:
            from core.settings_manager import get_setting
        except Exception as e:
            _log_warning("[ExternalValidator] Settings manager unavailable: "
                         "{}. External validation disabled.".format(e))
            return None

        try:
            mode = get_setting('validation.external_validation', 'off')
            mode = str(mode or 'off').strip().lower()
        except Exception as e:
            _log_warning("[ExternalValidator] Could not read "
                         "'validation.external_validation': {}. "
                         "External validation disabled.".format(e))
            return None

        if mode in ('', 'off', 'none', 'disabled', 'false'):
            return None

        if mode not in cls.STRATEGIES:
            _log_warning("[ExternalValidator] Unknown external_validation "
                         "value '{}' (expected off/opencv/second_model/both). "
                         "External validation disabled.".format(mode))
            return None

        provider_name = None
        try:
            provider_name = get_setting('validation.second_model_provider', None)
        except Exception:
            provider_name = None

        try:
            return cls(strategy=mode, provider_name=provider_name)
        except Exception as e:
            _log_error("[ExternalValidator] Failed to construct validator: "
                       "{}".format(e))
            return None

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _check_paths(self, storyboard_path, capture_path) -> Optional[str]:
        """Return an error string if either input path is unusable."""
        try:
            if not storyboard_path or not Path(storyboard_path).exists():
                return "Storyboard image not found: {}".format(storyboard_path)
            if not capture_path or not Path(capture_path).exists():
                return "Capture image not found: {}".format(capture_path)
        except (OSError, TypeError, ValueError) as e:
            return "Could not check input paths: {}".format(e)
        return None

    def _validate_opencv(self, storyboard_path, capture_path) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Wrap the existing SceneMatcher image comparison (composition,
        color, lighting, edge content). Local computation, no API cost.
        Returns (score, details).
        """
        try:
            # Lazy import: scene_matcher imports unreal at module level,
            # so importing it here keeps this module loadable outside UE.
            from ai_vision.scene_matcher import SceneMatcher
        except Exception as e:
            reason = "SceneMatcher unavailable: {}".format(e)
            _log_error("[ExternalValidator] {}".format(reason))
            return None, {'error': reason}

        try:
            matcher = SceneMatcher()
            comparison = matcher.compare_images(storyboard_path, capture_path)

            if comparison.get('error'):
                reason = "SceneMatcher error: {}".format(comparison['error'])
                _log_error("[ExternalValidator] {}".format(reason))
                return None, {'error': reason}

            score = float(comparison.get('match_percentage', 0.0))
            details = {
                'method': 'scene_matcher',
                'aspects': comparison.get('aspects', {}),
                'recommendations': comparison.get('recommendations', [])
            }
            return score, details

        except Exception as e:
            reason = "SceneMatcher comparison failed: {}".format(e)
            _log_error("[ExternalValidator] {}".format(reason))
            return None, {'error': reason}

    def _validate_second_model(self, storyboard_path, capture_path) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Score the capture against the storyboard using a different
        provider/model than the generator. Returns (score, details).
        """
        provider, provider_error = self._create_second_provider()
        if provider is None:
            _log_error("[ExternalValidator] {}".format(provider_error))
            return None, {'error': provider_error}

        try:
            response = provider.analyze_images(
                [storyboard_path, capture_path],
                self.SECOND_MODEL_PROMPT,
                max_tokens=200
            )
        except Exception as e:
            reason = "Second-model call failed: {}".format(e)
            _log_error("[ExternalValidator] {}".format(reason))
            return None, {'error': reason}

        if not isinstance(response, dict) or not response.get('success'):
            err = ''
            if isinstance(response, dict):
                err = response.get('error', 'unknown provider error')
            reason = "Second-model analysis unsuccessful: {}".format(err)
            _log_error("[ExternalValidator] {}".format(reason))
            return None, {'error': reason}

        score, reason_text, parse_error = self._parse_score_response(
            response.get('response', ''))

        if score is None:
            reason = "Could not parse score from second model: {}".format(parse_error)
            _log_error("[ExternalValidator] {}".format(reason))
            return None, {
                'error': reason,
                'raw_response': str(response.get('response', ''))[:500]
            }

        details = {
            'method': 'second_model',
            'provider': getattr(provider, 'name', str(self.provider_name)),
            'reason': reason_text,
            'cost': response.get('cost', 0.0)
        }
        return score, details

    def _validate_both(self, storyboard_path, capture_path) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Run both strategies; the conservative estimate is
        min(score_opencv, score_second_model). If only one strategy
        produces a score, that score is used and a note is logged.
        Returns (score, details).
        """
        opencv_score, opencv_details = self._validate_opencv(
            storyboard_path, capture_path)
        model_score, model_details = self._validate_second_model(
            storyboard_path, capture_path)

        details = {
            'method': 'both',
            'opencv': {'score': opencv_score, 'details': opencv_details},
            'second_model': {'score': model_score, 'details': model_details}
        }

        available = [s for s in (opencv_score, model_score) if s is not None]

        if not available:
            reason = "Both strategies failed to produce a score"
            _log_error("[ExternalValidator] {}".format(reason))
            details['error'] = reason
            return None, details

        if len(available) == 1:
            _log_warning("[ExternalValidator] Only one strategy produced a "
                         "score; using it without the conservative min")
            return available[0], details

        return min(available), details

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_second_provider(self):
        """
        Create the validator's provider via the existing factory.
        Returns (provider_or_None, error_message_or_None).
        """
        try:
            from core.ai_providers.provider_factory import AIProviderFactory
        except Exception as e:
            return None, "Provider factory unavailable: {}".format(e)

        provider_name = self.provider_name or 'auto'

        # Warn (do not fail) if the validator provider matches the
        # configured generator provider: the research point is to use a
        # DIFFERENT model than the one that generated the scene.
        try:
            from core.ai_settings import get_ai_settings
            generator_provider = get_ai_settings().get_provider()
            if (provider_name != 'auto'
                    and generator_provider
                    and generator_provider != 'auto'
                    and provider_name == generator_provider):
                _log_warning(
                    "[ExternalValidator] Validator provider '{}' matches the "
                    "generator provider. Cross-model validation works best "
                    "with a different model.".format(provider_name))
        except Exception:
            pass  # Purely advisory check; never block validation on it

        try:
            provider = AIProviderFactory.create_provider(
                provider_name, **self.provider_config)
        except Exception as e:
            return None, "Failed to create provider '{}': {}".format(
                provider_name, e)

        if provider is None:
            return None, ("No AI provider available for second_model "
                          "validation (provider: {})".format(provider_name))

        try:
            if not provider.is_available():
                return None, "Provider '{}' is not available (missing API " \
                             "key or service offline?)".format(provider_name)
        except Exception as e:
            return None, "Provider availability check failed: {}".format(e)

        return provider, None

    def _parse_score_response(self, response_text):
        """
        Extract {"score": N, "reason": "..."} from the model response.
        Returns (score_or_None, reason_text, parse_error_or_None).
        """
        if not response_text or not isinstance(response_text, str):
            return None, '', 'empty response'

        # Fast path: the prompt asks for bare JSON, so try json.loads first
        data = None
        try:
            data = json.loads(response_text)
        except (ValueError, TypeError):
            data = None

        # Robust path: markdown fences, prose wrapping, malformed JSON
        if data is None:
            try:
                from core.json_extractor import RobustJSONExtractor
                data = RobustJSONExtractor.extract_and_parse(response_text)
            except Exception:
                data = None

        if isinstance(data, list) and data:
            data = data[0]

        if isinstance(data, dict) and 'score' in data:
            try:
                score = self._clamp_score(float(data['score']))
                reason_text = str(data.get('reason', ''))
                return score, reason_text, None
            except (TypeError, ValueError):
                pass

        # Fallback: regex for a score number anywhere in the text
        match = re.search(r'"?score"?\s*[:=]\s*(\d+(?:\.\d+)?)',
                          response_text, re.IGNORECASE)
        if match:
            try:
                score = self._clamp_score(float(match.group(1)))
                return score, '', None
            except (TypeError, ValueError):
                pass

        return None, '', 'no score field found in response'

    @staticmethod
    def _clamp_score(value: float) -> float:
        """Clamp a score into the 0-100 range."""
        return max(0.0, min(100.0, value))
