# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ENTITY VALIDATOR
Multi-layer defense against AI hallucinations in actor positioning

CRITICAL: This prevents the system from accepting hallucinated entities
that don't exist in the scene. Always validate BEFORE fuzzy matching.
"""

import unreal
from typing import Optional, List, Dict, Tuple

# Try to import rapidfuzz for better fuzzy matching
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    # Fallback to difflib
    from difflib import SequenceMatcher
    RAPIDFUZZ_AVAILABLE = False
    print("rapidfuzz not available. Using difflib fallback.")
    print("For better matching: pip install rapidfuzz")


class EntityValidator:
    """
    Multi-layer validation pipeline to prevent hallucinations

    Validation Layers:
    1. Exact match check
    2. Case-insensitive check
    3. Fuzzy matching with threshold
    4. Confidence-based selection
    5. Semantic type validation

    Research-backed thresholds:
    - 90%: Industry standard for legitimate variations
    - 75%: Minimum threshold (below = likely hallucination)
    - NIL return: Essential when no good match exists
    """

    def __init__(self,
                 fuzzy_threshold: float = 75.0,
                 confidence_threshold: float = 90.0,
                 enable_logging: bool = True):
        """
        Initialize validator with thresholds

        Args:
            fuzzy_threshold: Minimum similarity score (0-100) to accept match
            confidence_threshold: Score above which match is considered high confidence
            enable_logging: Whether to log validation decisions
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.confidence_threshold = confidence_threshold
        self.enable_logging = enable_logging

        # Statistics tracking
        self.stats = {
            'total_validations': 0,
            'exact_matches': 0,
            'fuzzy_matches': 0,
            'rejections': 0,
            'hallucinations_blocked': 0
        }

    def validate_actor(self,
                      ai_actor: str,
                      detected_actors: List[str]) -> Optional[str]:
        """
        Validates AI entity reference against detected entities

        Args:
            ai_actor: Actor name proposed by AI
            detected_actors: List of actors actually present in scene

        Returns:
            Actual actor name if valid, None if hallucination
        """

        self.stats['total_validations'] += 1

        if not ai_actor or not detected_actors:
            self._log_rejection(ai_actor, "Empty input")
            return None

        # LAYER 1: Exact match check (fastest)
        if ai_actor in detected_actors:
            self.stats['exact_matches'] += 1
            self._log_success(ai_actor, ai_actor, 100.0, "exact")
            return ai_actor

        # LAYER 2: Case-insensitive check
        for actor in detected_actors:
            if ai_actor.lower() == actor.lower():
                self.stats['exact_matches'] += 1
                self._log_success(ai_actor, actor, 100.0, "case-insensitive")
                return actor

        # LAYER 3: Semantic type check (reject invalid entity types)
        if not self._is_valid_entity_type(ai_actor):
            self._log_rejection(ai_actor, "Invalid entity type (e.g., weather, atmosphere)")
            self.stats['rejections'] += 1
            return None

        # LAYER 4: Fuzzy matching with threshold
        matches = []
        for actor in detected_actors:
            score = self._calculate_similarity(ai_actor, actor)
            if score >= self.fuzzy_threshold:
                matches.append((actor, score))

        if not matches:
            # No match above threshold - HALLUCINATION
            self._log_rejection(
                ai_actor,
                f"No match above {self.fuzzy_threshold}% threshold",
                detected_actors
            )
            self.stats['hallucinations_blocked'] += 1
            self.stats['rejections'] += 1
            return None

        # LAYER 5: Confidence-based selection
        best_match = max(matches, key=lambda x: x[1])
        actor, score = best_match

        # Check confidence
        match_type = "high-confidence" if score >= self.confidence_threshold else "low-confidence"

        if score < self.confidence_threshold:
            self._log_warning(ai_actor, actor, score)
        else:
            self._log_success(ai_actor, actor, score, "fuzzy")

        self.stats['fuzzy_matches'] += 1
        return actor

    def validate_all_actors(self,
                           ai_actors: List[str],
                           detected_actors: List[str]) -> List[str]:
        """
        Validates list of AI actors, filters out hallucinations

        Args:
            ai_actors: List of actor names proposed by AI
            detected_actors: List of actors actually present in scene

        Returns:
            List of validated actor names (hallucinations removed)
        """

        validated = []
        rejected = []

        for ai_actor in ai_actors:
            result = self.validate_actor(ai_actor, detected_actors)
            if result:
                validated.append(result)
            else:
                rejected.append(ai_actor)

        if rejected:
            unreal.log_error(
                f" HALLUCINATIONS DETECTED AND REJECTED: {rejected}"
            )
            unreal.log_error(
                f"   Available actors were: {detected_actors}"
            )

        if self.enable_logging:
            unreal.log(
                f" Validated {len(validated)}/{len(ai_actors)} actors "
                f"({len(rejected)} rejected)"
            )

        return validated

    def validate_with_attributes(self,
                                ai_entity: Dict,
                                detected_entities: List[Dict]) -> Optional[str]:
        """
        Advanced validation with attribute checking

        Args:
            ai_entity: Dict with 'name' and optional attributes (color, size, etc.)
            detected_entities: List of dicts with 'id', 'name', attributes

        Returns:
            Entity ID if valid, None if invalid
        """

        ai_name = ai_entity.get('name', '')

        # First validate name existence
        matched_entities = []
        for entity in detected_entities:
            entity_name = entity.get('name', '')
            score = self._calculate_similarity(ai_name, entity_name)

            if score >= self.fuzzy_threshold:
                matched_entities.append((entity, score))

        if not matched_entities:
            self._log_rejection(ai_name, "No name match",
                              [e.get('name') for e in detected_entities])
            return None

        # If attributes provided, verify them
        ai_attributes = {k: v for k, v in ai_entity.items() if k != 'name'}

        if ai_attributes:
            # Filter by attribute match
            valid_matches = []
            for entity, score in matched_entities:
                if self._verify_attributes(entity, ai_attributes):
                    valid_matches.append((entity, score))

            if not valid_matches:
                self._log_rejection(ai_name, "Attributes don't match")
                return None

            matched_entities = valid_matches

        # Return best match
        best_entity, score = max(matched_entities, key=lambda x: x[1])
        return best_entity.get('id', best_entity.get('name'))

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity score between two strings
        Returns: Score from 0-100
        """

        str1 = str1.lower().strip()
        str2 = str2.lower().strip()

        if RAPIDFUZZ_AVAILABLE:
            # Use rapidfuzz for better matching
            return fuzz.ratio(str1, str2)
        else:
            # Fallback to difflib
            ratio = SequenceMatcher(None, str1, str2).ratio()
            return ratio * 100.0

    def _is_valid_entity_type(self, entity_name: str) -> bool:
        """
        Reject semantically invalid entity types

        AI sometimes hallucinates environmental concepts as actors
        """

        invalid_patterns = [
            'weather', 'atmosphere', 'lighting', 'shadow', 'shadows',
            'background', 'scenery', 'ambient', 'environment',
            'fog', 'mist', 'rain', 'snow', 'wind',
            'sun', 'moon', 'sky', 'ground', 'floor', 'ceiling'
        ]

        entity_lower = entity_name.lower()
        return not any(pattern in entity_lower for pattern in invalid_patterns)

    def _verify_attributes(self, entity: Dict, ai_attributes: Dict) -> bool:
        """Verify entity attributes match AI expectations"""

        for attr, expected_value in ai_attributes.items():
            if attr in entity:
                actual_value = entity[attr]

                # String comparison
                if isinstance(expected_value, str) and isinstance(actual_value, str):
                    if expected_value.lower() not in actual_value.lower():
                        return False
                # Numeric comparison (with tolerance)
                elif isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                    if abs(expected_value - actual_value) > 0.1 * expected_value:
                        return False

        return True

    def _log_success(self, ai_actor: str, matched_actor: str,
                    score: float, match_type: str):
        """Log successful validation"""
        if self.enable_logging:
            unreal.log(
                f" Matched: '{ai_actor}' → '{matched_actor}' "
                f"(score: {score:.1f}%, type: {match_type})"
            )

    def _log_warning(self, ai_actor: str, matched_actor: str, score: float):
        """Log low-confidence match"""
        if self.enable_logging:
            unreal.log_warning(
                f" LOW CONFIDENCE: '{ai_actor}' → '{matched_actor}' "
                f"(score: {score:.1f}% < {self.confidence_threshold}%)"
            )

    def _log_rejection(self, ai_actor: str, reason: str,
                      available: Optional[List[str]] = None):
        """Log rejection"""
        if self.enable_logging:
            msg = f" REJECTED: '{ai_actor}' - {reason}"
            if available:
                msg += f" (available: {available})"
            unreal.log_warning(msg)

    def get_statistics(self) -> Dict:
        """Get validation statistics"""
        stats = self.stats.copy()

        if stats['total_validations'] > 0:
            stats['exact_match_rate'] = stats['exact_matches'] / stats['total_validations']
            stats['fuzzy_match_rate'] = stats['fuzzy_matches'] / stats['total_validations']
            stats['rejection_rate'] = stats['rejections'] / stats['total_validations']
            stats['hallucination_rate'] = stats['hallucinations_blocked'] / stats['total_validations']

        return stats

    def print_statistics(self):
        """Print validation statistics"""
        stats = self.get_statistics()

        unreal.log("\n" + "="*60)
        unreal.log("ENTITY VALIDATOR STATISTICS")
        unreal.log("="*60)
        unreal.log(f"Total validations: {stats['total_validations']}")
        unreal.log(f"Exact matches: {stats['exact_matches']}")
        unreal.log(f"Fuzzy matches: {stats['fuzzy_matches']}")
        unreal.log(f"Rejections: {stats['rejections']}")
        unreal.log(f"Hallucinations blocked: {stats['hallucinations_blocked']}")

        if stats['total_validations'] > 0:
            unreal.log(f"\nRates:")
            unreal.log(f"Exact match rate: {stats['exact_match_rate']*100:.1f}%")
            unreal.log(f"Fuzzy match rate: {stats['fuzzy_match_rate']*100:.1f}%")
            unreal.log(f"Rejection rate: {stats['rejection_rate']*100:.1f}%")
            unreal.log(f"Hallucination rate: {stats['hallucination_rate']*100:.1f}%")

        unreal.log("="*60)


# Convenience function
def validate_actors(ai_actors: List[str],
                   scene_actors: List[str],
                   threshold: float = 75.0) -> List[str]:
    """
    Quick validation function for drop-in use

    Usage:
        # AI suggests these
        ai_actors = ["Oat", "Dog", "Character1"]

        # Scene actually has these
        scene_actors = ["Oat"]

        # Validate (blocks hallucinations)
        valid_actors = validate_actors(ai_actors, scene_actors)
        # Returns: ["Oat"]  (Dog and Character1 rejected)
    """
    validator = EntityValidator(fuzzy_threshold=threshold)
    return validator.validate_all_actors(ai_actors, scene_actors)


# Self-test
if __name__ == "__main__":
    print("Testing EntityValidator...")

    # Mock unreal.log functions for testing
    class MockUnreal:
        @staticmethod
        def log(msg): print(f"[LOG] {msg}")
        @staticmethod
        def log_warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def log_error(msg): print(f"[ERROR] {msg}")

    unreal = MockUnreal()

    validator = EntityValidator()
    scene_actors = ["Oat", "Ball", "Bench"]

    # Test exact match
    result = validator.validate_actor("Oat", scene_actors)
    assert result == "Oat", "Exact match should work"

    # Test case insensitive
    result = validator.validate_actor("oat", scene_actors)
    assert result == "Oat", "Case insensitive should work"

    # Test fuzzy match
    result = validator.validate_actor("Bal", scene_actors)
    assert result == "Ball", "Fuzzy match should work"

    # Test hallucination rejection
    result = validator.validate_actor("Dog", scene_actors)
    assert result is None, "Should reject hallucination"

    result = validator.validate_actor("Character1", scene_actors)
    assert result is None, "Should reject hallucination"

    # Test batch validation
    ai_actors = ["Oat", "Dog", "Ball", "Character1", "bench"]
    validated = validator.validate_all_actors(ai_actors, scene_actors)
    assert len(validated) == 3, f"Should validate 3 actors, got {len(validated)}"
    assert "Oat" in validated
    assert "Ball" in validated
    assert "Bench" in validated

    # Print statistics
    validator.print_statistics()

    print("\n ALL TESTS PASSED")
