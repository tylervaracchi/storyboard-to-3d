# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Enhanced Prompt Builder for AI Positioning
Creates context-aware, shot-specific prompts for better positioning accuracy
"""

import unreal
from typing import Dict, List, Optional


class EnhancedPromptBuilder:
    """
    Builds intelligent prompts for AI positioning based on:
    - Shot type (wide, medium, close-up, etc.)
    - Scene context (characters, props, location)
    - Iteration number (explore vs refine)
    - Previous results (learning)
    """

    # Shot-specific composition rules
    SHOT_RULES = {
        'wide': {
            'focus': 'overall composition, spacing, and scene layout',
            'rules': [
                'Characters should be clearly visible',
                'Consider rule of thirds for composition',
                'Maintain appropriate negative space',
                'Ensure all important elements are in frame'
            ],
            'priority': ['spacing', 'layout', 'framing']
        },
        'medium': {
            'focus': 'character positioning and interaction',
            'rules': [
                'Characters should be well-framed',
                'Eye lines and blocking are crucial',
                'Allow room for character movement',
                'Consider character relationships'
            ],
            'priority': ['character_position', 'eye_lines', 'interaction']
        },
        'close_up': {
            'focus': 'precise character framing and face placement',
            'rules': [
                'Character face should dominate frame',
                'Eyes typically on upper third line',
                'Allow appropriate headroom',
                'Consider looking space'
            ],
            'priority': ['face_position', 'headroom', 'eye_level']
        },
        'over_shoulder': {
            'focus': 'foreground and background character relationship',
            'rules': [
                'Foreground shoulder frames the shot',
                'Background character clearly visible',
                'Eye line between characters matters',
                'Depth separation is important'
            ],
            'priority': ['depth', 'eye_lines', 'framing']
        },
        'two_shot': {
            'focus': 'balanced framing of two characters',
            'rules': [
                'Both characters equally important',
                'Symmetry or intentional asymmetry',
                'Consider character spacing',
                'Maintain visual balance'
            ],
            'priority': ['balance', 'spacing', 'symmetry']
        }
    }

    def __init__(self):
        self.iteration_history = []
        unreal.log("[PromptBuilder] Enhanced prompt builder initialized")

    def build_positioning_prompt(
        self,
        shot_type: str = 'medium',
        iteration: int = 1,
        previous_similarity: float = 0.0,
        scene_context: Optional[Dict] = None,
        angle_view: str = 'perspective',
        use_absolute_positioning: bool = True
    ) -> str:
        """
        Build a comprehensive positioning prompt

        Args:
            shot_type: Type of shot (wide, medium, close_up, etc.)
            iteration: Which iteration (1 = explore, 5+ = refine)
            previous_similarity: Similarity from last iteration
            scene_context: Dict with characters, props, etc.
            angle_view: Which camera angle (perspective, front, top, side, wide)
            use_absolute_positioning: If True, AI provides absolute world coordinates

        Returns:
            Detailed prompt string for AI
        """
        # Base instruction
        prompt = self._build_base_instruction(angle_view)

        # Add shot-specific guidance
        prompt += self._build_shot_guidance(shot_type)

        # Add iteration-specific strategy
        prompt += self._build_iteration_strategy(iteration, previous_similarity)

        # Add scene context
        if scene_context:
            prompt += self._build_scene_context(scene_context)

        # Add angle-specific focus
        prompt += self._build_angle_focus(angle_view, shot_type)

        # Add output format (with positioning mode)
        prompt += self._build_output_format(use_absolute_positioning)

        return prompt

    def _build_base_instruction(self, angle_view: str) -> str:
        """Base instruction for positioning"""
        view_descriptions = {
            'perspective': 'a 3/4 perspective view',
            'front': 'a direct front view',
            'top': 'a top-down bird\'s eye view',
            'side': 'a side profile view',
            'wide': 'a wide establishing view'
        }

        view_desc = view_descriptions.get(angle_view, 'the current view')

        return f"""You are an expert cinematographer analyzing {view_desc} of a 3D scene.

TASK: Compare the target storyboard image with the current 3D scene and provide precise movement instructions to match the storyboard composition.

"""

    def _build_shot_guidance(self, shot_type: str) -> str:
        """Add shot-specific composition guidance"""
        shot_info = self.SHOT_RULES.get(shot_type, self.SHOT_RULES['medium'])

        prompt = f"""SHOT TYPE: {shot_type.replace('_', ' ').title()}
FOCUS: {shot_info['focus']}

COMPOSITION RULES FOR THIS SHOT:
"""

        for i, rule in enumerate(shot_info['rules'], 1):
            prompt += f"{i}. {rule}\n"

        prompt += f"\nPRIORITY AREAS: {', '.join(shot_info['priority'])}\n\n"

        return prompt

    def _build_iteration_strategy(self, iteration: int, previous_similarity: float) -> str:
        """Add strategy based on iteration number"""
        if iteration == 1:
            strategy = """STRATEGY: Initial Positioning (Iteration 1)
- Make BOLD movements to get close to target
- Focus on major positioning issues first
- Large adjustments are acceptable (200-400cm)
- Don't worry about fine details yet
"""
        elif iteration <= 3:
            if previous_similarity < 0.5:
                strategy = """STRATEGY: Exploration (Early Iterations, Low Similarity)
- Continue making significant movements
- Try different positioning approaches
- Movement range: 150-300cm
- Focus on getting the overall layout right
"""
            else:
                strategy = """STRATEGY: Refinement (Early Iterations, Improving)
- Good progress - continue with medium adjustments
- Fine-tune character positions
- Movement range: 100-200cm
- Start paying attention to details
"""
        else:
            if previous_similarity >= 0.8:
                strategy = """STRATEGY: Polishing (High Similarity)
- Make SMALL, precise adjustments only
- Focus on fine details and perfection
- Movement range: 25-75cm
- Consider subtle composition improvements
"""
            elif previous_similarity >= 0.6:
                strategy = """STRATEGY: Final Refinement (Good Similarity)
- Medium adjustments to improve further
- Movement range: 75-150cm
- Address remaining composition issues
"""
            else:
                strategy = """STRATEGY: Problem Solving (Later Iteration, Low Similarity)
- Try DIFFERENT approach - previous strategy not working
- Consider alternative positioning
- Movement range: 150-250cm
- Think creatively about the problem
"""

        if previous_similarity > 0:
            strategy += f"\nPREVIOUS SIMILARITY: {previous_similarity:.1%} - "
            if previous_similarity >= 0.85:
                strategy += "Excellent! Small refinements only.\n"
            elif previous_similarity >= 0.7:
                strategy += "Good progress. Continue improvements.\n"
            elif previous_similarity >= 0.5:
                strategy += "Making progress. Keep adjusting.\n"
            else:
                strategy += "Need significant changes.\n"

        return strategy + "\n"

    def _build_scene_context(self, context: Dict) -> str:
        """Add scene context information"""
        prompt = "SCENE CONTEXT:\n"

        if 'characters' in context and context['characters']:
            char_list = ', '.join(context['characters'])
            prompt += f"Characters: {char_list}\n"

        if 'props' in context and context['props']:
            prop_list = ', '.join(context['props'])
            prompt += f"Props: {prop_list}\n"

        if 'location' in context:
            prompt += f"Location: {context['location']}\n"

        prompt += "\n"
        return prompt

    def _build_angle_focus(self, angle_view: str, shot_type: str) -> str:
        """Add angle-specific analysis focus"""
        angle_guidance = {
            'perspective': """PERSPECTIVE VIEW ANALYSIS:
- Evaluate overall composition and framing
- Check character placement relative to frame
- Assess visual balance and spacing
- Consider foreground/background relationships
""",
            'front': """FRONT VIEW ANALYSIS:
- Focus on HORIZONTAL (left/right) positioning
- Check character alignment and spacing
- Evaluate X-axis movements primarily
- Ensure characters are at correct screen positions
""",
            'top': """TOP-DOWN VIEW ANALYSIS:
- Focus on LAYOUT and SPACING from above
- Check depth positioning (forward/backward)
- Evaluate character grouping and floor patterns
- Assess both X and Y positioning
""",
            'side': """SIDE VIEW ANALYSIS:
- Focus on DEPTH (near/far from camera)
- Check Z-axis positioning
- Evaluate foreground/background separation
- Assess character distance from camera
""",
            'wide': """WIDE VIEW ANALYSIS:
- Focus on OVERALL CONTEXT and framing
- Check if all elements are visible
- Evaluate scene composition as a whole
- Assess relationship between all scene elements
"""
        }

        return angle_guidance.get(angle_view, angle_guidance['perspective'])

    def _build_output_format(self, use_absolute_positioning: bool = True) -> str:
        """Specify required output format with positioning mode"""

        if use_absolute_positioning:
            positioning_instruction = """
CRITICAL POSITIONING MODE: ABSOLUTE WORLD COORDINATES

You MUST provide EXACT target positions in world space, NOT relative adjustments!

 CORRECT (Absolute): "move_x": -50.0  (means "position actor at X=-50 in world")
 WRONG (Relative):    "move_x": -50.0  (DON'T interpret as "move 50cm left")

Think of it like GPS coordinates - you're specifying WHERE the actor should BE, not HOW to move them.

WORLD COORDINATE REFERENCE:
- Scene origin (0, 0, 0) is typically at the center of the main location (bench, table, etc.)
- Characters sitting on bench: X ≈ 0, Y ≈ ±30-50cm (side-by-side), Z ≈ 90cm (sitting height)
- Camera position: X ≈ -500 to -800cm (in front of scene), Y ≈ 0 (centered), Z ≈ 140-160cm (eye level)

EXAMPLE ABSOLUTE POSITIONING:
{
    "actor": "Oat",
    "move_x": -30.0,    ← Position Oat AT X=-30 in world (left of center)
    "move_y": 40.0,     ← Position Oat AT Y=40 in world (slightly forward)
    "move_z": 90.0,     ← Position Oat AT Z=90 in world (sitting height)
    "rotate_yaw": 0.0,  ← Face forward (0° = facing +X direction)
    "reason": "Position character on left side of bench at sitting height"
}
"""
        else:
            positioning_instruction = """
POSITIONING MODE: RELATIVE ADJUSTMENTS

Provide movement deltas relative to current position.

EXAMPLE RELATIVE MOVEMENT:
{
    "actor": "Oat",
    "move_x": -50.0,    ← Move 50cm to the LEFT from current position
    "move_y": 100.0,    ← Move 100cm FORWARD from current position
    "move_z": 0.0,      ← No vertical change
    "rotate_yaw": 15.0, ← Rotate 15° clockwise from current rotation
    "reason": "Move character left and forward to better match storyboard"
}
"""

        return f"""
OUTPUT FORMAT:
Provide your analysis as JSON with this structure:
{{
    "analysis": "Brief description of main differences",
    "similarity": 0.75,
    "movements": [
        {{
            "actor": "Character1",
            "move_x": 100.0,
            "move_y": -50.0,
            "move_z": 0.0,
            "rotate_yaw": 15.0,
            "reason": "Positioning reasoning"
        }}
    ],
    "confidence": 0.8,
    "suggestions": "Additional composition notes"
}}

{positioning_instruction}

COORDINATE SYSTEM:
- X: Left (negative) / Right (positive)
- Y: Backward (negative) / Forward (positive)
- Z: Down (negative) / Up (positive)
- Yaw: Counter-clockwise (negative) / Clockwise (positive)

Be specific and precise with all movement values.
Provide clear reasoning for each positioning decision.
"""

    def build_comparison_prompt(
        self,
        storyboard_path: str,
        screenshot_path: str,
        **kwargs
    ) -> str:
        """
        Build a prompt for image comparison

        Args:
            storyboard_path: Path to target storyboard image
            screenshot_path: Path to current 3D scene screenshot
            **kwargs: Additional parameters for build_positioning_prompt

        Returns:
            Complete prompt with image context
        """
        base_prompt = self.build_positioning_prompt(**kwargs)

        # Add image-specific instructions
        image_instruction = f"""
IMAGE COMPARISON:
Image 1 (Target): Storyboard panel - this is what we want to achieve
Image 2 (Current): 3D scene screenshot - this is what we currently have

Compare these images carefully and provide movements to make Image 2 match Image 1.
"""

        return image_instruction + base_prompt

    def record_iteration(self, iteration: int, similarity: float, movements: List[Dict]):
        """Record iteration for learning"""
        self.iteration_history.append({
            'iteration': iteration,
            'similarity': similarity,
            'movements': movements
        })

    def get_iteration_summary(self) -> str:
        """Get summary of iteration history"""
        if not self.iteration_history:
            return "No iterations recorded yet"

        summary = f"Iteration History ({len(self.iteration_history)} iterations):\n"
        for record in self.iteration_history:
            summary += f"  Iter {record['iteration']}: {record['similarity']:.1%} similarity\n"

        return summary


# Convenience function
def build_smart_prompt(
    shot_type: str = 'medium',
    iteration: int = 1,
    previous_similarity: float = 0.0,
    angle_view: str = 'perspective',
    **kwargs
) -> str:
    """
    Quick function to build a smart positioning prompt

    Args:
        shot_type: Type of shot
        iteration: Current iteration number
        previous_similarity: Similarity score from previous iteration
        angle_view: Camera angle perspective
        **kwargs: Additional context

    Returns:
        Enhanced prompt string
    """
    builder = EnhancedPromptBuilder()
    return builder.build_positioning_prompt(
        shot_type=shot_type,
        iteration=iteration,
        previous_similarity=previous_similarity,
        angle_view=angle_view,
        scene_context=kwargs.get('scene_context')
    )


if __name__ == "__main__":
    # Test the prompt builder
    builder = EnhancedPromptBuilder()

    test_prompt = builder.build_positioning_prompt(
        shot_type='close_up',
        iteration=1,
        previous_similarity=0.0,
        angle_view='perspective',
        scene_context={
            'characters': ['Character1', 'Character2'],
            'props': ['Table', 'Chair'],
            'location': 'Interior Office'
        }
    )

    unreal.log("="*80)
    unreal.log("ENHANCED PROMPT EXAMPLE:")
    unreal.log("="*80)
    unreal.log(test_prompt)
    unreal.log("="*80)
