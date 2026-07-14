"""
Metric Validation Module for Thesis
====================================

Addresses Critical Issue #1: Match Score Validation
- Implements objective perceptual metrics (SSIM, PSNR, MSE)
- Validates AI-generated subjective scores
- Provides multi-metric composite scoring
- Supports human evaluation protocol

Author: [Your Name]
Date: October 31, 2025
Purpose: Drexel University Digital Media Master's Thesis
"""

import unreal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image
import json

try:
    from skimage.metrics import structural_similarity as ssim
    from skimage.metrics import peak_signal_noise_ratio as psnr
    from skimage.metrics import mean_squared_error as mse
    SKIMAGE_AVAILABLE = True
except ImportError:
    unreal.log_warning("[MetricValidation] scikit-image not available - install with: pip install scikit-image")
    SKIMAGE_AVAILABLE = False

try:
    import torch
    import lpips
    LPIPS_AVAILABLE = True
except ImportError:
    unreal.log_warning("[MetricValidation] LPIPS not available - install with: pip install lpips")
    LPIPS_AVAILABLE = False

# Force disable LPIPS - causes crashes in UE environment (Nov 4, 2025)
LPIPS_AVAILABLE = False
unreal.log(f"[MetricValidation] Module loaded - LPIPS_AVAILABLE = {LPIPS_AVAILABLE}")


class MetricValidator:
    """
    Validates match scores using objective perceptual metrics

    Addresses thesis committee concern:
    "How do you know AI-generated scores correlate with actual visual similarity?"
    """

    def __init__(self):
        self.lpips_model = None
        if LPIPS_AVAILABLE:
            try:
                self.lpips_model = lpips.LPIPS(net='alex')  # AlexNet-based perceptual loss
                unreal.log("[MetricValidation] LPIPS model loaded successfully")
            except Exception as e:
                unreal.log_warning(f"[MetricValidation] Could not load LPIPS: {e}")

        # Validation statistics
        self.validation_history = []

    def calculate_objective_metrics(self,
                                    reference_path: str,
                                    test_path: str) -> Dict[str, float]:
        """
        Calculate all objective perceptual metrics

        Args:
            reference_path: Path to storyboard reference image
            test_path: Path to generated 3D screenshot

        Returns:
            Dictionary with all metric scores:
            - ssim: Structural Similarity Index (0-1, higher better)
            - psnr: Peak Signal-to-Noise Ratio (dB, higher better)
            - mse: Mean Squared Error (lower better)
            - lpips: Learned Perceptual Image Patch Similarity (0-1, lower better)
        """
        if not SKIMAGE_AVAILABLE:
            unreal.log_error("[MetricValidation] Cannot calculate metrics - scikit-image not installed")
            return {}

        try:
            # Load images
            ref_img = Image.open(reference_path).convert('RGB')
            test_img = Image.open(test_path).convert('RGB')

            # Resize to same dimensions if needed
            if ref_img.size != test_img.size:
                test_img = test_img.resize(ref_img.size, Image.Resampling.LANCZOS)

            # Convert to numpy arrays
            ref_array = np.array(ref_img)
            test_array = np.array(test_img)

            # Calculate metrics
            metrics = {}

            # SSIM: Structural Similarity (0-1, 1 = identical)
            metrics['ssim'] = ssim(ref_array, test_array,
                                  channel_axis=2,  # RGB channels
                                  data_range=255)

            # PSNR: Peak Signal-to-Noise Ratio (dB, higher = better)
            metrics['psnr'] = psnr(ref_array, test_array, data_range=255)

            # MSE: Mean Squared Error (lower = better)
            metrics['mse'] = mse(ref_array, test_array)

            # LPIPS: Learned Perceptual metric (0-1, 0 = identical)
            if LPIPS_AVAILABLE and self.lpips_model is not None:
                try:
                    # Normalize to [-1, 1] and convert to torch tensors
                    ref_tensor = torch.from_numpy(ref_array).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1.0
                    test_tensor = torch.from_numpy(test_array).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1.0

                    with torch.no_grad():
                        lpips_score = self.lpips_model(ref_tensor, test_tensor).item()

                    metrics['lpips'] = lpips_score
                except Exception as e:
                    unreal.log_warning(f"[MetricValidation] LPIPS calculation failed: {e}")
                    metrics['lpips'] = None
            else:
                metrics['lpips'] = None

            unreal.log(f"[MetricValidation] Calculated metrics:")
            unreal.log(f"   SSIM: {metrics['ssim']:.4f} (0-1, higher better)")
            unreal.log(f"   PSNR: {metrics['psnr']:.2f} dB (higher better)")
            unreal.log(f"   MSE: {metrics['mse']:.2f} (lower better)")
            if metrics['lpips'] is not None:
                unreal.log(f"   LPIPS: {metrics['lpips']:.4f} (0-1, lower better)")

            return metrics

        except Exception as e:
            unreal.log_error(f"[MetricValidation] Error calculating metrics: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return {}

    def validate_ai_score(self,
                         ai_subjective_score: float,
                         objective_metrics: Dict[str, float]) -> Dict[str, any]:
        """
        Validate AI's subjective score against objective metrics

        Args:
            ai_subjective_score: AI-reported match score (0-100)
            objective_metrics: Dict from calculate_objective_metrics()

        Returns:
            Validation results with correlation analysis
        """
        if not objective_metrics:
            return {'valid': False, 'reason': 'No objective metrics available'}

        # Convert AI score to 0-1 scale
        ai_score_normalized = ai_subjective_score / 100.0

        # Calculate composite objective score
        composite_objective = self._calculate_composite_score(objective_metrics)

        # Calculate discrepancy
        discrepancy = abs(ai_score_normalized - composite_objective)

        # Determine validity (threshold: 0.2 = 20% difference)
        # Convert to native Python bool (numpy booleans are not JSON serializable)
        is_valid = bool(discrepancy < 0.2)

        validation_result = {
            'valid': is_valid,
            'ai_score_normalized': float(ai_score_normalized),  # Ensure native Python float
            'composite_objective_score': float(composite_objective),
            'discrepancy': float(discrepancy),
            'correlation_strength': float(1.0 - discrepancy),  # Inverse of discrepancy
            'metrics_breakdown': {k: float(v) if v is not None else None for k, v in objective_metrics.items()},
            'validation_threshold': 0.2
        }

        # Store for longitudinal analysis
        self.validation_history.append({
            'ai_score': ai_subjective_score,
            'objective_score': composite_objective * 100,
            'discrepancy': discrepancy
        })

        if not is_valid:
            unreal.log_warning(f"[MetricValidation] AI score ({ai_subjective_score:.1f}%) differs from objective ({composite_objective*100:.1f}%) by {discrepancy*100:.1f}%")
        else:
            unreal.log(f"[MetricValidation] ✓ AI score validated (discrepancy: {discrepancy*100:.1f}%)")

        return validation_result

    def _calculate_composite_score(self, metrics: Dict[str, float]) -> float:
        """
        Calculate weighted composite score from multiple metrics

        Weighting based on perceptual importance:
        - SSIM: 40% (structural similarity most important)
        - LPIPS: 30% (learned perceptual features)
        - PSNR: 20% (signal quality)
        - MSE: 10% (pixel-level accuracy)

        Returns:
            Composite score 0-1 (higher = better match)
        """
        weights = {
            'ssim': 0.40,
            'lpips': 0.30,
            'psnr': 0.20,
            'mse': 0.10
        }

        # Normalize metrics to 0-1 scale (higher = better)
        normalized = {}

        # SSIM already 0-1, higher better
        normalized['ssim'] = metrics.get('ssim', 0.5)

        # LPIPS: 0-1, lower better → invert
        if metrics.get('lpips') is not None:
            normalized['lpips'] = 1.0 - min(1.0, metrics['lpips'])
        else:
            # If LPIPS unavailable, redistribute weight to SSIM
            weights['ssim'] += weights['lpips']
            weights['lpips'] = 0
            normalized['lpips'] = 0

        # PSNR: typically 20-50 dB, normalize to 0-1
        psnr_val = metrics.get('psnr', 25)
        normalized['psnr'] = np.clip((psnr_val - 20) / 30, 0, 1)  # 20-50 dB range

        # MSE: lower better, normalize inverse
        mse_val = metrics.get('mse', 5000)
        normalized['mse'] = np.clip(1.0 - (mse_val / 10000), 0, 1)  # 0-10000 range

        # Calculate weighted sum
        composite = sum(normalized[key] * weights[key] for key in weights.keys())

        return composite

    def calculate_correlation_statistics(self) -> Dict[str, float]:
        """
        Calculate correlation between AI scores and objective metrics
        across all validation history

        Returns:
            Pearson correlation coefficient and p-value
        """
        if len(self.validation_history) < 3:
            return {'correlation': None, 'p_value': None, 'n': len(self.validation_history)}

        try:
            from scipy import stats

            ai_scores = [v['ai_score'] for v in self.validation_history]
            obj_scores = [v['objective_score'] for v in self.validation_history]

            correlation, p_value = stats.pearsonr(ai_scores, obj_scores)

            return {
                'correlation': correlation,
                'p_value': p_value,
                'n': len(self.validation_history),
                'interpretation': self._interpret_correlation(correlation, p_value)
            }
        except Exception as e:
            unreal.log_error(f"[MetricValidation] Error calculating correlation: {e}")
            return {'correlation': None, 'p_value': None, 'n': len(self.validation_history)}

    def _interpret_correlation(self, r: float, p: float) -> str:
        """Interpret correlation coefficient"""
        if p > 0.05:
            return f"Not statistically significant (p={p:.3f})"

        if abs(r) < 0.3:
            return f"Weak correlation (r={r:.3f}, p={p:.3f})"
        elif abs(r) < 0.7:
            return f"Moderate correlation (r={r:.3f}, p={p:.3f})"
        else:
            return f"Strong correlation (r={r:.3f}, p={p:.3f})"

    def save_validation_report(self, output_path: str):
        """
        Save validation report for thesis documentation

        Includes:
        - All validation history
        - Correlation statistics
        - Metric reliability assessment
        """
        report = {
            'validation_history': self.validation_history,
            'correlation_stats': self.calculate_correlation_statistics(),
            'total_validations': len(self.validation_history),
            'avg_discrepancy': np.mean([v['discrepancy'] for v in self.validation_history]) if self.validation_history else 0,
            'metrics_used': ['SSIM', 'PSNR', 'MSE'] + (['LPIPS'] if LPIPS_AVAILABLE else [])
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        unreal.log(f"[MetricValidation] Validation report saved to: {output_path}")


class HumanEvaluationProtocol:
    """
    Protocol for collecting human evaluation data

    Addresses committee question:
    "What validates that AI scores match human perception?"
    """

    def __init__(self):
        self.ratings = []

    def collect_rating(self,
                      scene_id: str,
                      storyboard_path: str,
                      screenshot_path: str,
                      rater_id: str) -> Dict:
        """
        Collect human rating for a scene result

        Protocol:
        1. Show rater storyboard and 3D result side-by-side
        2. Ask: "On a scale of 1-10, how well does the 3D scene match the storyboard?"
        3. Ask: "What are the main differences?"
        4. Record rating and comments

        Args:
            scene_id: Identifier for test scene
            storyboard_path: Reference image
            screenshot_path: AI-generated result
            rater_id: Identifier for rater (e.g., "Rater1", "Rater2")

        Returns:
            Rating data dictionary
        """
        unreal.log(f"\n{'='*70}")
        unreal.log(f"HUMAN EVALUATION PROTOCOL")
        unreal.log(f"{'='*70}")
        unreal.log(f"Scene: {scene_id}")
        unreal.log(f"Rater: {rater_id}")
        unreal.log(f"\nPlease view:")
        unreal.log(f"  Storyboard: {storyboard_path}")
        unreal.log(f"  3D Result:  {screenshot_path}")
        unreal.log(f"\n[MANUAL INPUT REQUIRED]")
        unreal.log(f"After viewing both images, record:")
        unreal.log(f"1. Match quality (1-10 scale, 10 = perfect match)")
        unreal.log(f"2. Main differences observed")
        unreal.log(f"3. Confidence in rating (1-5, 5 = very confident)")

        # In production, this would prompt GUI input
        # For thesis, record manually and call add_rating()

        return {
            'scene_id': scene_id,
            'rater_id': rater_id,
            'storyboard_path': storyboard_path,
            'screenshot_path': screenshot_path,
            'timestamp': str(Path(screenshot_path).stat().st_mtime),
            'instructions_displayed': True
        }

    def add_rating(self,
                  scene_id: str,
                  rater_id: str,
                  match_quality: int,
                  differences: str,
                  confidence: int):
        """
        Add a completed human rating

        Args:
            scene_id: Scene identifier
            rater_id: Rater identifier
            match_quality: 1-10 scale (10 = perfect)
            differences: Text description of differences
            confidence: 1-5 scale (5 = very confident)
        """
        rating = {
            'scene_id': scene_id,
            'rater_id': rater_id,
            'match_quality': match_quality,
            'match_quality_normalized': match_quality / 10.0,  # Convert to 0-1
            'differences': differences,
            'confidence': confidence
        }

        self.ratings.append(rating)
        unreal.log(f"[HumanEval] Rating recorded: {scene_id} by {rater_id} = {match_quality}/10")

    def calculate_inter_rater_reliability(self, scene_id: str) -> Dict:
        """
        Calculate inter-rater reliability (Cohen's Kappa or ICC)

        Requires at least 2 raters for same scene

        Args:
            scene_id: Scene to analyze

        Returns:
            IRR statistics
        """
        scene_ratings = [r for r in self.ratings if r['scene_id'] == scene_id]

        if len(scene_ratings) < 2:
            return {'error': 'Need at least 2 raters', 'n_raters': len(scene_ratings)}

        # Get ratings as array
        ratings_array = [r['match_quality'] for r in scene_ratings]

        # Calculate statistics
        mean_rating = np.mean(ratings_array)
        std_rating = np.std(ratings_array)

        # Simple agreement percentage
        if len(set(ratings_array)) == 1:
            agreement = 1.0
        else:
            # Calculate how close ratings are (within ±1 point = agreement)
            agreements = 0
            total_pairs = 0
            for i in range(len(ratings_array)):
                for j in range(i+1, len(ratings_array)):
                    if abs(ratings_array[i] - ratings_array[j]) <= 1:
                        agreements += 1
                    total_pairs += 1
            agreement = agreements / total_pairs if total_pairs > 0 else 0

        return {
            'scene_id': scene_id,
            'n_raters': len(scene_ratings),
            'mean_rating': mean_rating,
            'std_rating': std_rating,
            'agreement_within_1pt': agreement,
            'ratings': ratings_array
        }

    def calculate_ai_human_correlation(self, ai_scores: Dict[str, float]) -> Dict:
        """
        Correlate AI scores with human ratings

        Args:
            ai_scores: Dict mapping scene_id -> AI match score (0-100)

        Returns:
            Correlation statistics
        """
        if len(self.ratings) == 0:
            return {'error': 'No human ratings available'}

        # Calculate mean human rating per scene
        human_means = {}
        for rating in self.ratings:
            scene_id = rating['scene_id']
            if scene_id not in human_means:
                human_means[scene_id] = []
            human_means[scene_id].append(rating['match_quality'] * 10)  # Convert to 0-100 scale

        # Average across raters
        for scene_id in human_means:
            human_means[scene_id] = np.mean(human_means[scene_id])

        # Match with AI scores
        matched_scenes = [s for s in human_means.keys() if s in ai_scores]

        if len(matched_scenes) < 3:
            return {'error': 'Need at least 3 scenes with both AI and human ratings', 'n': len(matched_scenes)}

        human_scores = [human_means[s] for s in matched_scenes]
        ai_scores_list = [ai_scores[s] for s in matched_scenes]

        try:
            from scipy import stats
            correlation, p_value = stats.pearsonr(human_scores, ai_scores_list)

            return {
                'correlation': correlation,
                'p_value': p_value,
                'n_scenes': len(matched_scenes),
                'interpretation': 'Strong' if abs(correlation) > 0.7 else 'Moderate' if abs(correlation) > 0.4 else 'Weak'
            }
        except Exception as e:
            unreal.log_error(f"[HumanEval] Error calculating correlation: {e}")
            return {'error': str(e)}

    def save_human_evaluation_data(self, output_path: str):
        """Save all human evaluation data for thesis"""
        data = {
            'ratings': self.ratings,
            'total_ratings': len(self.ratings),
            'unique_scenes': len(set(r['scene_id'] for r in self.ratings)),
            'unique_raters': len(set(r['rater_id'] for r in self.ratings))
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        unreal.log(f"[HumanEval] Data saved to: {output_path}")


# Example usage for thesis
if __name__ == "__main__":
    unreal.log("="*70)
    unreal.log("METRIC VALIDATION MODULE - THESIS INTEGRATION")
    unreal.log("="*70)

    # Initialize validator
    validator = MetricValidator()

    # Example: Validate a single result
    reference = "D:/PythonStoryboardToUE/Content/StoryboardTo3D/Shows/oat/Episodes/Episode1/testpanel_008.png"
    result = "D:/PythonStoryboardToUE/Saved/Screenshots/WindowsEditor/test_hero.png"

    if Path(reference).exists() and Path(result).exists():
        # Calculate objective metrics
        metrics = validator.calculate_objective_metrics(reference, result)

        # Validate AI's score (example: AI said 70%)
        ai_score = 70.0
        validation = validator.validate_ai_score(ai_score, metrics)

        unreal.log(f"\nValidation Result:")
        unreal.log(f"  AI Score: {ai_score}%")
        unreal.log(f"  Objective Score: {validation['composite_objective_score']*100:.1f}%")
        unreal.log(f"  Valid: {validation['valid']}")
        unreal.log(f"  Discrepancy: {validation['discrepancy']*100:.1f}%")
    else:
        unreal.log("Example files not found - install scikit-image to enable metrics")
        unreal.log("  pip install scikit-image")
        unreal.log("  pip install lpips  (optional, for advanced perceptual metrics)")
