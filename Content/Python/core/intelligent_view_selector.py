# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Intelligent View Selector for AI-Powered 3D Positioning
Optimizes image selection to minimize token costs while maintaining accuracy

Author: AI Research Team
Date: 2025-01-31
"""

import unreal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import statistics


@dataclass
class ViewSelectionResult:
    """Result of view selection decision"""
    rgb_views: List[str]  # Which RGB captures to include
    depth_views: List[str]  # Which depth maps to include
    include_storyboard_depth: bool  # Whether to include storyboard depth
    strategy_name: str  # Name of strategy used
    reasoning: str  # Why this selection was made
    estimated_cost: float  # Estimated API cost for this iteration
    estimated_token_count: int  # Estimated tokens


class IntelligentViewSelector:
    """
    Intelligently selects which views to send to AI based on:
    - Iteration number (early vs late stage)
    - Previous similarity scores (converging vs struggling)
    - Scene complexity (simple vs complex)
    - Detected positioning challenges
    """

    # View set definitions (from research document)
    VIEW_SETS = {
        'MINIMAL': {
            'rgb': ['hero'],
            'depth': [],
            'storyboard_depth': False,
            'description': 'Minimal views for high-score verification'
        },
        'FOCUSED': {
            'rgb': ['hero', 'top'],
            'depth': ['hero'],
            'storyboard_depth': False,
            'description': 'Focused views for refinement'
        },
        'REFINEMENT': {
            'rgb': ['hero', 'front', 'top'],
            'depth': ['hero', 'top'],
            'storyboard_depth': True,
            'description': 'Refinement views for mid-stage iterations'
        },
        'EXPLORATION': {
            'rgb': ['hero', 'front', 'right', 'top'],
            'depth': ['hero', 'front', 'top'],
            'storyboard_depth': True,
            'description': 'Exploration views for early iterations'
        },
        'COMPREHENSIVE': {
            'rgb': ['hero', 'front', 'back', 'left', 'right', 'top', 'three_quarter'],
            'depth': ['hero', 'front', 'right', 'top'],
            'storyboard_depth': True,
            'description': 'Comprehensive views for struggling or complex scenes'
        }
    }

    # Pricing estimates (GPT-4o with detail settings)
    COST_PER_IMAGE = {
        'high_detail': 0.001275,  # ~765 tokens
        'low_detail': 0.00085,    # ~510 tokens
    }

    def __init__(self):
        """Initialize the view selector"""
        self.score_history = []
        self.view_history = []
        unreal.log("[IntelligentViewSelector] Initialized")

    def select_views(
        self,
        iteration: int,
        previous_score: Optional[float] = None,
        scene_complexity: str = 'medium',
        shot_type: str = 'medium',
        num_actors: int = 2,
        available_captures: Optional[Dict[str, str]] = None,
        force_strategy: Optional[str] = None
    ) -> ViewSelectionResult:
        """
        Select optimal views for current iteration

        Args:
            iteration: Current iteration number (1-based)
            previous_score: Similarity score from previous iteration (0-100)
            scene_complexity: 'simple', 'medium', or 'complex'
            shot_type: Shot type (wide, medium, close_up, over_shoulder, etc.)
            num_actors: Number of actors in scene
            available_captures: Dict of available captures (if None, assumes all available)
            force_strategy: Force a specific strategy (for testing/debugging)

        Returns:
            ViewSelectionResult with selected views and reasoning
        """
        # Add score to history
        if previous_score is not None:
            self.score_history.append(previous_score)

        # Determine strategy
        if force_strategy and force_strategy in self.VIEW_SETS:
            strategy_name = force_strategy
            reasoning = f"Forced strategy: {force_strategy}"
        else:
            strategy_name, reasoning = self._determine_strategy(
                iteration, previous_score, scene_complexity, shot_type, num_actors
            )

        # Get base view set
        base_set = self.VIEW_SETS[strategy_name].copy()

        # Apply scene-specific adjustments
        adjusted_set = self._apply_scene_adjustments(
            base_set, scene_complexity, shot_type, num_actors
        )

        # Ensure hero camera always included (non-negotiable)
        if 'hero' not in adjusted_set['rgb']:
            adjusted_set['rgb'].insert(0, 'hero')
            reasoning += " | Hero camera force-added (required)"

        # Filter to only available captures
        if available_captures is not None:
            adjusted_set['rgb'] = [
                v for v in adjusted_set['rgb'] if v in available_captures
            ]
            adjusted_set['depth'] = [
                v for v in adjusted_set['depth'] if v in available_captures
            ]

        # Determine depth map inclusion
        depth_decision = self._should_include_depth(
            iteration, previous_score, shot_type, num_actors
        )

        # Apply depth decision
        if not depth_decision['storyboard']:
            adjusted_set['storyboard_depth'] = False
        if not depth_decision['hero']:
            adjusted_set['depth'] = [d for d in adjusted_set['depth'] if d != 'hero']
        if not depth_decision['scouts']:
            adjusted_set['depth'] = [d for d in adjusted_set['depth'] if d == 'hero']

        # Calculate cost estimate
        estimated_cost, estimated_tokens = self._estimate_cost(adjusted_set)

        # Build result
        result = ViewSelectionResult(
            rgb_views=adjusted_set['rgb'],
            depth_views=adjusted_set['depth'],
            include_storyboard_depth=adjusted_set['storyboard_depth'],
            strategy_name=strategy_name,
            reasoning=reasoning,
            estimated_cost=estimated_cost,
            estimated_token_count=estimated_tokens
        )

        # Log decision
        self._log_decision(iteration, result)

        # Store in history
        self.view_history.append({
            'iteration': iteration,
            'strategy': strategy_name,
            'views': adjusted_set['rgb'],
            'depth': adjusted_set['depth'],
            'score': previous_score
        })

        return result

    def _determine_strategy(
        self,
        iteration: int,
        previous_score: Optional[float],
        scene_complexity: str,
        shot_type: str,
        num_actors: int
    ) -> Tuple[str, str]:
        """
        Determine which strategy to use based on current state

        Returns:
            (strategy_name, reasoning)
        """
        # RULE 1: First iteration always uses EXPLORATION
        if iteration == 1:
            return 'EXPLORATION', "First iteration - need comprehensive view for initial positioning"

        # RULE 2: High score → MINIMAL views
        if previous_score is not None and previous_score >= 85:
            return 'MINIMAL', f"High score ({previous_score:.1f}) - using minimal views to verify convergence"

        # RULE 3: Detect oscillation
        if len(self.score_history) >= 3:
            recent_scores = self.score_history[-3:]
            variance = statistics.variance(recent_scores) if len(recent_scores) > 1 else 0
            if variance > 100:
                return 'COMPREHENSIVE', f"Detected oscillation (variance={variance:.1f}) - switching to comprehensive views"

        # RULE 4: Struggling (low score) → COMPREHENSIVE views
        if previous_score is not None and previous_score < 55:
            return 'COMPREHENSIVE', f"Low score ({previous_score:.1f}) - using comprehensive views to improve"

        # RULE 5: Very complex scenes always get COMPREHENSIVE
        if scene_complexity == 'complex' or num_actors >= 7:
            return 'COMPREHENSIVE', f"Complex scene (complexity={scene_complexity}, actors={num_actors}) - comprehensive views needed"

        # RULE 6: Iteration-based strategy
        if iteration <= 3:
            # Early iterations: exploration
            return 'EXPLORATION', f"Early iteration ({iteration}) - exploration phase"
        elif iteration <= 7:
            # Mid iterations: refinement
            return 'REFINEMENT', f"Mid iteration ({iteration}) - refinement phase"
        else:
            # Late iterations: focused/polishing
            if previous_score is not None and previous_score >= 75:
                return 'FOCUSED', f"Late iteration ({iteration}) with good score ({previous_score:.1f}) - polishing"
            else:
                return 'REFINEMENT', f"Late iteration ({iteration}) but score needs work - continuing refinement"

    def _apply_scene_adjustments(
        self,
        base_set: Dict,
        scene_complexity: str,
        shot_type: str,
        num_actors: int
    ) -> Dict:
        """
        Apply scene-specific adjustments to view set

        Returns:
            Adjusted view set
        """
        adjusted = {
            'rgb': base_set['rgb'].copy(),
            'depth': base_set['depth'].copy(),
            'storyboard_depth': base_set['storyboard_depth']
        }

        # Adjustment 1: Simple scenes - remove redundant views
        if scene_complexity == 'simple' or (num_actors <= 2 and shot_type == 'wide'):
            # Remove back, left, three_quarter for simple scenes
            adjusted['rgb'] = [v for v in adjusted['rgb'] if v not in ['back', 'left', 'three_quarter']]
            unreal.log(f"Simple scene adjustment: Removed redundant views")

        # Adjustment 2: Complex scenes - add back view if not present
        if scene_complexity == 'complex' or num_actors >= 5:
            if 'back' not in adjusted['rgb'] and len(adjusted['rgb']) < 7:
                adjusted['rgb'].append('back')
                unreal.log(f"Complex scene adjustment: Added back view")

        # Adjustment 3: Close-up shots - skip top view (not useful)
        if shot_type == 'close_up':
            adjusted['rgb'] = [v for v in adjusted['rgb'] if v != 'top']
            adjusted['depth'] = [v for v in adjusted['depth'] if v != 'top']
            unreal.log(f"Close-up adjustment: Removed top view")

        # Adjustment 4: Over-shoulder shots - ensure depth is included
        if shot_type == 'over_shoulder':
            if 'hero' not in adjusted['depth']:
                adjusted['depth'].append('hero')
            adjusted['storyboard_depth'] = True
            unreal.log(f"Over-shoulder adjustment: Ensured depth maps")

        return adjusted

    def _should_include_depth(
        self,
        iteration: int,
        score: Optional[float],
        shot_type: str,
        num_actors: int
    ) -> Dict[str, bool]:
        """
        Decide which depth maps to include

        Returns:
            {
                'storyboard': bool,
                'hero': bool,
                'scouts': bool
            }
        """
        result = {
            'storyboard': False,
            'hero': False,
            'scouts': False
        }

        # Rule 1: First 2 iterations always include depth
        if iteration <= 2:
            result['storyboard'] = True
            result['hero'] = True
            result['scouts'] = True
            return result

        # Rule 2: Complex scenes need depth longer
        if num_actors >= 5 or shot_type == 'over_shoulder':
            if iteration <= 5:
                result['hero'] = True
                result['scouts'] = True
            return result

        # Rule 3: Struggling needs depth
        if score is not None and score < 60:
            result['hero'] = True
            result['scouts'] = True
            return result

        # Rule 4: Mid-range scores get hero depth only
        # Extended: Keep hero depth for iterations 6-10 if still improving (score < 80)
        if score is not None and 60 <= score < 80:
            if iteration <= 5:
                result['hero'] = True
                result['scouts'] = True  # Include scout depths for early iterations
            elif iteration <= 10:
                result['hero'] = True  # Hero depth only for mid iterations
            return result

        # Rule 5: High scores skip depth (all False already)
        return result

    def _estimate_cost(self, view_set: Dict) -> Tuple[float, int]:
        """
        Estimate API cost and token count for view set

        Returns:
            (estimated_cost, estimated_tokens)
        """
        # Count images
        num_rgb = len(view_set['rgb'])
        num_depth = len(view_set['depth'])
        has_storyboard_depth = view_set['storyboard_depth']

        # Total images = storyboard + storyboard_depth + rgb + depth
        total_images = 1 + (1 if has_storyboard_depth else 0) + num_rgb + num_depth

        # Cost calculation (assuming high detail for hero/storyboard, low for others)
        high_detail_count = 1 + (1 if has_storyboard_depth else 0) + 1  # storyboard + storyboard_depth + hero
        low_detail_count = total_images - high_detail_count

        estimated_cost = (
            high_detail_count * self.COST_PER_IMAGE['high_detail'] +
            low_detail_count * self.COST_PER_IMAGE['low_detail']
        )

        # Token count (rough estimate)
        estimated_tokens = (
            high_detail_count * 765 +
            low_detail_count * 510
        )

        return estimated_cost, estimated_tokens

    def _log_decision(self, iteration: int, result: ViewSelectionResult):
        """Log the view selection decision"""
        unreal.log("="*70)
        unreal.log(f"VIEW SELECTION - Iteration {iteration}")
        unreal.log("="*70)
        unreal.log(f"Strategy: {result.strategy_name}")
        unreal.log(f"Reasoning: {result.reasoning}")
        unreal.log(f"RGB Views ({len(result.rgb_views)}): {', '.join(result.rgb_views)}")
        unreal.log(f"Depth Views ({len(result.depth_views)}): {', '.join(result.depth_views) if result.depth_views else 'None'}")
        unreal.log(f"Storyboard Depth: {'Yes' if result.include_storyboard_depth else 'No'}")
        unreal.log(f"Estimated Cost: ${result.estimated_cost:.4f}")
        unreal.log(f"Estimated Tokens: {result.estimated_token_count:,}")
        unreal.log("="*70)
    def get_statistics(self) -> Dict:
        """
        Get statistics about view selection across iterations

        Returns:
            Dict with statistics
        """
        if not self.view_history:
            return {
                'total_iterations': 0,
                'average_views_per_iteration': 0,
                'total_estimated_cost': 0,
                'strategy_distribution': {}
            }

        total_views = sum(len(h['views']) + len(h['depth']) for h in self.view_history)
        avg_views = total_views / len(self.view_history)

        # Strategy distribution
        strategy_counts = {}
        for h in self.view_history:
            strategy = h['strategy']
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        # Calculate total estimated cost
        total_cost = 0
        for h in self.view_history:
            view_set = {
                'rgb': h['views'],
                'depth': h['depth'],
                'storyboard_depth': 'storyboard' in h.get('depth', [])
            }
            cost, _ = self._estimate_cost(view_set)
            total_cost += cost

        return {
            'total_iterations': len(self.view_history),
            'average_views_per_iteration': avg_views,
            'total_estimated_cost': total_cost,
            'strategy_distribution': strategy_counts,
            'score_history': self.score_history.copy()
        }

    def reset(self):
        """Reset selector state for new scene"""
        self.score_history = []
        self.view_history = []
        unreal.log("[IntelligentViewSelector] Reset for new scene")

    def detect_oscillation(self, window_size: int = 3) -> bool:
        """
        Detect if scores are oscillating (stuck in local minimum)

        Args:
            window_size: Number of recent scores to analyze

        Returns:
            True if oscillation detected
        """
        if len(self.score_history) < window_size:
            return False

        recent_scores = self.score_history[-window_size:]

        # Calculate variance
        variance = statistics.variance(recent_scores) if len(recent_scores) > 1 else 0

        # High variance = oscillating
        return variance > 100

    def is_converged(self, threshold: float = 85.0) -> bool:
        """
        Check if scene has converged (high score)

        Args:
            threshold: Score threshold for convergence

        Returns:
            True if converged
        """
        if not self.score_history:
            return False

        return self.score_history[-1] >= threshold

    def is_plateau(self, window_size: int = 3, delta_threshold: float = 5.0) -> bool:
        """
        Detect if scores have plateaued (stuck at suboptimal score)

        Args:
            window_size: Number of recent scores to check
            delta_threshold: Maximum delta for plateau detection

        Returns:
            True if plateau detected
        """
        if len(self.score_history) < window_size:
            return False

        recent_scores = self.score_history[-window_size:]

        # Check if all scores within small delta
        max_score = max(recent_scores)
        min_score = min(recent_scores)

        return (max_score - min_score) < delta_threshold


# Convenience function for easy integration
def select_views_for_iteration(
    iteration: int,
    previous_score: Optional[float] = None,
    scene_complexity: str = 'medium',
    shot_type: str = 'medium',
    num_actors: int = 2,
    available_captures: Optional[Dict[str, str]] = None,
    selector: Optional[IntelligentViewSelector] = None
) -> ViewSelectionResult:
    """
    Convenience function to select views without managing selector instance

    Args:
        iteration: Current iteration number
        previous_score: Score from previous iteration (0-100)
        scene_complexity: 'simple', 'medium', or 'complex'
        shot_type: Type of shot
        num_actors: Number of actors in scene
        available_captures: Available captures dict
        selector: Optional existing selector instance

    Returns:
        ViewSelectionResult
    """
    if selector is None:
        selector = IntelligentViewSelector()

    return selector.select_views(
        iteration=iteration,
        previous_score=previous_score,
        scene_complexity=scene_complexity,
        shot_type=shot_type,
        num_actors=num_actors,
        available_captures=available_captures
    )


if __name__ == "__main__":
    # Test the view selector
    unreal.log("\n" + "="*70)
    unreal.log("TESTING INTELLIGENT VIEW SELECTOR")
    unreal.log("="*70)

    selector = IntelligentViewSelector()

    # Simulate 10 iterations with improving scores
    test_scores = [None, 45, 58, 62, 70, 75, 82, 87, 90, 92]

    for i, score in enumerate(test_scores, start=1):
        result = selector.select_views(
            iteration=i,
            previous_score=score,
            scene_complexity='medium',
            shot_type='medium',
            num_actors=3
        )

    # Print statistics
    stats = selector.get_statistics()
    unreal.log("\n" + "="*70)
    unreal.log("STATISTICS")
    unreal.log("="*70)
    unreal.log(f"Total iterations: {stats['total_iterations']}")
    unreal.log(f"Average views per iteration: {stats['average_views_per_iteration']:.1f}")
    unreal.log(f"Total estimated cost: ${stats['total_estimated_cost']:.4f}")
    unreal.log(f"Strategy distribution:")
    for strategy, count in stats['strategy_distribution'].items():
        percentage = (count / stats['total_iterations']) * 100
        unreal.log(f"{strategy}: {count} ({percentage:.1f}%)")
    unreal.log("="*70)
