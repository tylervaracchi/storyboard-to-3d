"""
Comprehensive Metrics Tracking for Thesis Evaluation
Tracks all positioning accuracy, iteration counts, convergence, and performance metrics
"""

import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import statistics

# Try to import unreal for logging (may not be available outside Unreal Editor)
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    UNREAL_AVAILABLE = False


class MetricsTracker:
    """
    Tracks comprehensive metrics for thesis evaluation:
    - Positioning accuracy per iteration
    - Convergence analysis
    - Processing times
    - Cost analysis
    - Success rates
    """
    
    def __init__(self, output_dir: Path, scene_id: str, approach: str = "multiview"):
        """
        Initialize metrics tracker
        
        Args:
            output_dir: Directory to save metrics files
            scene_id: Unique identifier for the scene (e.g., "Simple_1", "Medium_2")
            approach: "baseline" (single-view) or "multiview" (your approach)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.scene_id = scene_id
        self.approach = approach
        self.start_time = datetime.now()
        
        # Core metrics
        self.iteration_data: List[Dict[str, Any]] = []
        self.accuracy_by_iteration: List[float] = []  # Match scores 0-100
        self.total_iterations = 0
        self.converged = False
        self.convergence_iteration = None
        
        # Processing metrics
        self.processing_times: Dict[str, float] = {
            'total': 0.0,
            'analysis': 0.0,
            'iteration': 0.0,
            'export': 0.0
        }
        
        # Cost metrics
        self.cost_by_iteration: List[float] = []
        self.total_cost = 0.0
        
        # Additional context
        self.scene_metadata = {
            'scene_id': scene_id,
            'approach': approach,
            'complexity': self._infer_complexity(scene_id),
            'num_characters': 0,
            'num_props': 0,
            'storyboard_file': '',
            'timestamp': self.start_time.isoformat()
        }
        
        # Convergence criteria
        self.convergence_threshold = 80  # Score > 80 = converged
        self.max_iterations = 20
    
    def _infer_complexity(self, scene_id: str) -> str:
        """Infer complexity from scene_id (Simple_X, Medium_X, Complex_X)"""
        scene_lower = scene_id.lower()
        if 'simple' in scene_lower:
            return 'simple'
        elif 'medium' in scene_lower:
            return 'medium'
        elif 'complex' in scene_lower:
            return 'complex'
        else:
            return 'unknown'
    
    def set_scene_context(self, num_characters: int, num_props: int, 
                         storyboard_file: str = '', environment: str = 'indoor'):
        """Set additional scene metadata"""
        self.scene_metadata['num_characters'] = num_characters
        self.scene_metadata['num_props'] = num_props
        self.scene_metadata['storyboard_file'] = storyboard_file
        self.scene_metadata['environment'] = environment
    
    def start_iteration(self, iteration_num: int):
        """Mark the start of an iteration"""
        self.current_iteration_start = datetime.now()
        self.current_iteration_num = iteration_num
    
    def record_iteration(self,
                        iteration_num: int,
                        match_score: float,
                        adjustments_applied: int = 0,
                        camera_adjusted: bool = False,
                        cost: float = 0.0,
                        positioning_mode: str = 'relative',
                        temperature: float = 0.7,
                        analysis_text: str = '',
                        adjustments_data: Optional[List[Dict]] = None,
                        camera_position: Optional[Dict[str, Any]] = None,
                        objective_metrics: Optional[Dict[str, float]] = None,
                        validation_result: Optional[Dict[str, Any]] = None):
        """
        Record comprehensive metrics for a single iteration

        Args:
            iteration_num: Iteration number (0 = initial state, 1+ = after adjustments)
            match_score: AI match score 0-100
            adjustments_applied: Number of actor adjustments made
            camera_adjusted: Whether camera was adjusted
            cost: API cost for this iteration
            positioning_mode: 'relative' or 'absolute'
            temperature: AI temperature used
            analysis_text: AI analysis/reasoning text
            adjustments_data: List of adjustment details
            camera_position: Camera transform {location: {x, y, z}, rotation: {pitch, yaw, roll}}
            objective_metrics: THESIS - Objective perceptual metrics {ssim, psnr, mse, lpips}
            validation_result: THESIS - Validation result {valid, composite_objective_score, discrepancy}
        """
        iteration_time = 0.0
        if hasattr(self, 'current_iteration_start'):
            iteration_time = (datetime.now() - self.current_iteration_start).total_seconds()
        
        # Store iteration data
        iteration_record = {
            'iteration': iteration_num,
            'match_score': match_score,
            'adjustments_applied': adjustments_applied,
            'camera_adjusted': camera_adjusted,
            'cost': cost,
            'positioning_mode': positioning_mode,
            'temperature': temperature,
            'iteration_time_seconds': iteration_time,
            'analysis_text': analysis_text[:500] if analysis_text else '',  # Truncate for storage
            'adjustments_detail': adjustments_data or [],
            'camera_position': camera_position,  # Final camera transform after adjustments
            # THESIS ENHANCEMENT: Objective validation metrics
            'objective_metrics': objective_metrics,  # {ssim, psnr, mse, lpips}
            'validation_result': validation_result   # {valid, composite_objective_score, discrepancy, correlation_strength}
        }
        
        self.iteration_data.append(iteration_record)
        self.accuracy_by_iteration.append(match_score)
        self.cost_by_iteration.append(cost)
        self.total_cost += cost
        self.total_iterations = iteration_num
        
        # Check convergence
        if match_score >= self.convergence_threshold and not self.converged:
            self.converged = True
            self.convergence_iteration = iteration_num
    
    def finalize(self):
        """Calculate final metrics and save all data"""
        end_time = datetime.now()
        self.processing_times['total'] = (end_time - self.start_time).total_seconds()
        
        # Calculate summary statistics
        summary = self._calculate_summary()

        # Save all formats
        self._save_json(summary)
        self._save_csv()
        if summary:
            self._save_summary_text(summary)
        else:
            # No scored iterations (e.g. every AI call failed): the raw
            # JSON/CSV are still saved for forensics, but the summary
            # text assumes at least one score and would KeyError
            print("No scored iterations - summary text skipped")

        return summary
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate comprehensive summary statistics"""
        if not self.accuracy_by_iteration:
            return {}
        
        initial_accuracy = self.accuracy_by_iteration[0] if self.accuracy_by_iteration else 0
        final_accuracy = self.accuracy_by_iteration[-1] if self.accuracy_by_iteration else 0
        improvement = final_accuracy - initial_accuracy
        
        # Calculate statistics
        mean_accuracy = statistics.mean(self.accuracy_by_iteration)
        std_accuracy = statistics.stdev(self.accuracy_by_iteration) if len(self.accuracy_by_iteration) > 1 else 0
        best_accuracy = max(self.accuracy_by_iteration)
        worst_accuracy = min(self.accuracy_by_iteration)
        
        # Convergence analysis
        monotonic_improvement = all(
            self.accuracy_by_iteration[i] >= self.accuracy_by_iteration[i-1]
            for i in range(1, len(self.accuracy_by_iteration))
        ) if len(self.accuracy_by_iteration) > 1 else True
        
        # Check for oscillation
        oscillating = False
        if len(self.accuracy_by_iteration) >= 3:
            changes = [
                self.accuracy_by_iteration[i] - self.accuracy_by_iteration[i-1]
                for i in range(1, len(self.accuracy_by_iteration))
            ]
            oscillating = any(
                changes[i] * changes[i-1] < 0
                for i in range(1, len(changes))
            )
        
        summary = {
            # Scene info
            'scene_id': self.scene_id,
            'approach': self.approach,
            'complexity': self.scene_metadata['complexity'],
            'num_characters': self.scene_metadata['num_characters'],
            'num_props': self.scene_metadata['num_props'],
            'environment': self.scene_metadata.get('environment', 'unknown'),
            
            # Accuracy metrics
            'initial_accuracy': initial_accuracy,
            'final_accuracy': final_accuracy,
            'improvement': improvement,
            'mean_accuracy': mean_accuracy,
            'std_accuracy': std_accuracy,
            'best_accuracy': best_accuracy,
            'worst_accuracy': worst_accuracy,
            
            # Iteration metrics
            'total_iterations': self.total_iterations,
            'converged': self.converged,
            'convergence_iteration': self.convergence_iteration,
            'convergence_threshold': self.convergence_threshold,
            
            # Convergence analysis
            'monotonic_improvement': monotonic_improvement,
            'oscillating': oscillating,
            
            # Performance metrics
            'total_time_seconds': self.processing_times['total'],
            'avg_iteration_time': (
                sum(item.get('iteration_time_seconds', 0) for item in self.iteration_data) /
                len(self.iteration_data) if self.iteration_data else 0
            ),
            
            # Cost metrics
            'total_cost': self.total_cost,
            'avg_cost_per_iteration': (
                self.total_cost / len(self.cost_by_iteration)
                if self.cost_by_iteration else 0
            ),
            'cost_per_point_improvement': (
                self.total_cost / improvement if improvement > 0 else 0
            ),
            
            # Full iteration history
            'accuracy_by_iteration': self.accuracy_by_iteration,
            'cost_by_iteration': self.cost_by_iteration,
            'iteration_details': self.iteration_data,

            # THESIS ENHANCEMENT: Objective validation metrics summary
            'objective_validation': self._calculate_objective_validation_summary(),

            # Metadata
            'timestamp': self.start_time.isoformat(),
            'storyboard_file': self.scene_metadata.get('storyboard_file', '')
        }

        return summary

    def _calculate_objective_validation_summary(self) -> Dict[str, Any]:
        """
        THESIS: Calculate summary statistics for objective metric validation

        Returns statistics on SSIM/PSNR correlation with AI scores
        """
        # Extract objective metrics from iteration data
        iterations_with_metrics = [
            iter_data for iter_data in self.iteration_data
            if iter_data.get('objective_metrics') is not None
        ]

        if not iterations_with_metrics:
            return {
                'available': False,
                'note': 'No objective metrics recorded (install scikit-image for validation)'
            }

        # Calculate averages
        ssim_values = [iter['objective_metrics']['ssim'] for iter in iterations_with_metrics if iter['objective_metrics'].get('ssim')]
        psnr_values = [iter['objective_metrics']['psnr'] for iter in iterations_with_metrics if iter['objective_metrics'].get('psnr')]
        mse_values = [iter['objective_metrics']['mse'] for iter in iterations_with_metrics if iter['objective_metrics'].get('mse')]

        # Count validated vs. invalid
        validated_count = sum(1 for iter in iterations_with_metrics if iter.get('validation_result', {}).get('valid', False))
        total_count = len(iterations_with_metrics)

        # Calculate mean discrepancy
        discrepancies = [
            iter['validation_result']['discrepancy'] * 100
            for iter in iterations_with_metrics
            if iter.get('validation_result')
        ]

        return {
            'available': True,
            'total_iterations_validated': total_count,
            'validated_count': validated_count,
            'validation_rate': (validated_count / total_count * 100) if total_count > 0 else 0,
            'mean_ssim': statistics.mean(ssim_values) if ssim_values else None,
            'mean_psnr': statistics.mean(psnr_values) if psnr_values else None,
            'mean_mse': statistics.mean(mse_values) if mse_values else None,
            'mean_discrepancy_percent': statistics.mean(discrepancies) if discrepancies else None,
            'final_ssim': ssim_values[-1] if ssim_values else None,
            'final_psnr': psnr_values[-1] if psnr_values else None,
            'note': f'{validated_count}/{total_count} iterations validated (AI score within 20% of objective)'
        }
    
    def _save_json(self, summary: Dict[str, Any]):
        """Save complete metrics as JSON"""
        filename = f"{self.scene_id}_{self.approach}_metrics.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)

        if UNREAL_AVAILABLE:
            unreal.log(f"✅ Saved JSON metrics: {filepath}")
        else:
            print(f"✅ Saved JSON metrics: {filepath}")
    
    def _save_csv(self):
        """Save iteration-by-iteration data as CSV"""
        filename = f"{self.scene_id}_{self.approach}_iterations.csv"
        filepath = self.output_dir / filename
        
        if not self.iteration_data:
            return
        
        # CSV headers
        fieldnames = [
            'iteration',
            'match_score',
            'adjustments_applied',
            'camera_adjusted',
            'cost',
            'positioning_mode',
            'temperature',
            'iteration_time_seconds',
            'camera_pos_x',
            'camera_pos_y',
            'camera_pos_z',
            'camera_rot_pitch',
            'camera_rot_yaw',
            'camera_rot_roll',
            # Objective validation metrics (THESIS)
            'ssim',
            'psnr',
            'mse',
            'lpips',
            'validated',
            'discrepancy_percent',
            'objective_composite_score'
        ]
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in self.iteration_data:
                # Extract only the fields we want in CSV
                csv_row = {k: record.get(k, '') for k in fieldnames}
                
                # Add camera position data if available
                cam_pos = record.get('camera_position')
                if cam_pos:
                    loc = cam_pos.get('location', {})
                    rot = cam_pos.get('rotation', {})
                    csv_row['camera_pos_x'] = loc.get('x', '')
                    csv_row['camera_pos_y'] = loc.get('y', '')
                    csv_row['camera_pos_z'] = loc.get('z', '')
                    csv_row['camera_rot_pitch'] = rot.get('pitch', '')
                    csv_row['camera_rot_yaw'] = rot.get('yaw', '')
                    csv_row['camera_rot_roll'] = rot.get('roll', '')

                # Add objective validation metrics if available (THESIS)
                obj_metrics = record.get('objective_metrics')
                if obj_metrics:
                    csv_row['ssim'] = obj_metrics.get('ssim', '')
                    csv_row['psnr'] = obj_metrics.get('psnr', '')
                    csv_row['mse'] = obj_metrics.get('mse', '')
                    csv_row['lpips'] = obj_metrics.get('lpips', '')

                validation = record.get('validation_result')
                if validation:
                    csv_row['validated'] = validation.get('valid', '')
                    csv_row['discrepancy_percent'] = validation.get('discrepancy', 0) * 100 if validation.get('discrepancy') else ''
                    csv_row['objective_composite_score'] = validation.get('composite_objective_score', '')

                writer.writerow(csv_row)

        if UNREAL_AVAILABLE:
            unreal.log(f"✅ Saved CSV data: {filepath}")
        else:
            print(f"✅ Saved CSV data: {filepath}")
    
    def _save_summary_text(self, summary: Dict[str, Any]):
        """Save human-readable summary"""
        filename = f"{self.scene_id}_{self.approach}_summary.txt"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            f.write("="*70 + "\n")
            f.write(f"METRICS SUMMARY: {self.scene_id} ({self.approach})\n")
            f.write("="*70 + "\n\n")
            
            f.write("SCENE INFO:\n")
            f.write(f"  Scene ID: {summary['scene_id']}\n")
            f.write(f"  Approach: {summary['approach']}\n")
            f.write(f"  Complexity: {summary['complexity']}\n")
            f.write(f"  Characters: {summary['num_characters']}\n")
            f.write(f"  Props: {summary['num_props']}\n")
            f.write(f"  Environment: {summary.get('environment', 'unknown')}\n\n")
            
            f.write("ACCURACY METRICS:\n")
            f.write(f"  Initial Accuracy: {summary['initial_accuracy']:.1f}%\n")
            f.write(f"  Final Accuracy: {summary['final_accuracy']:.1f}%\n")
            f.write(f"  Improvement: {summary['improvement']:+.1f} percentage points\n")
            f.write(f"  Mean Accuracy: {summary['mean_accuracy']:.1f}% ± {summary['std_accuracy']:.1f}%\n")
            f.write(f"  Best Accuracy: {summary['best_accuracy']:.1f}%\n")
            f.write(f"  Worst Accuracy: {summary['worst_accuracy']:.1f}%\n\n")
            
            f.write("ITERATION METRICS:\n")
            f.write(f"  Total Iterations: {summary['total_iterations']}\n")
            f.write(f"  Converged: {'Yes' if summary['converged'] else 'No'}\n")
            if summary['converged']:
                f.write(f"  Converged at Iteration: {summary['convergence_iteration']}\n")
            f.write(f"  Convergence Threshold: {summary['convergence_threshold']}%\n\n")
            
            f.write("CONVERGENCE ANALYSIS:\n")
            f.write(f"  Monotonic Improvement: {'Yes' if summary['monotonic_improvement'] else 'No'}\n")
            f.write(f"  Oscillating: {'Yes' if summary['oscillating'] else 'No'}\n\n")
            
            f.write("PERFORMANCE METRICS:\n")
            f.write(f"  Total Time: {summary['total_time_seconds']:.1f} seconds\n")
            f.write(f"  Avg Iteration Time: {summary['avg_iteration_time']:.1f} seconds\n\n")
            
            f.write("COST METRICS:\n")
            f.write(f"  Total Cost: ${summary['total_cost']:.4f}\n")
            f.write(f"  Avg Cost/Iteration: ${summary['avg_cost_per_iteration']:.4f}\n")
            if summary['improvement'] > 0:
                f.write(f"  Cost/Point Improvement: ${summary['cost_per_point_improvement']:.4f}\n")
            f.write("\n")

            # THESIS: Objective validation section
            obj_validation = summary.get('objective_validation', {})
            if obj_validation.get('available'):
                f.write("OBJECTIVE VALIDATION (THESIS):\n")
                f.write(f"  Validation Rate: {obj_validation['validation_rate']:.1f}% ({obj_validation['validated_count']}/{obj_validation['total_iterations_validated']})\n")
                if obj_validation.get('mean_ssim'):
                    f.write(f"  Mean SSIM: {obj_validation['mean_ssim']:.3f}\n")
                if obj_validation.get('mean_psnr'):
                    f.write(f"  Mean PSNR: {obj_validation['mean_psnr']:.2f} dB\n")
                if obj_validation.get('mean_mse'):
                    f.write(f"  Mean MSE: {obj_validation['mean_mse']:.1f}\n")
                if obj_validation.get('mean_discrepancy_percent'):
                    f.write(f"  Mean AI-Objective Discrepancy: {obj_validation['mean_discrepancy_percent']:.1f}%\n")
                if obj_validation.get('final_ssim'):
                    f.write(f"  Final SSIM: {obj_validation['final_ssim']:.3f}\n")
                if obj_validation.get('final_psnr'):
                    f.write(f"  Final PSNR: {obj_validation['final_psnr']:.2f} dB\n")
                f.write(f"  Note: {obj_validation.get('note', '')}\n")
                f.write("\n")

            f.write("ITERATION PROGRESSION:\n")
            for i, score in enumerate(summary['accuracy_by_iteration']):
                delta = ""
                if i > 0:
                    change = score - summary['accuracy_by_iteration'][i-1]
                    delta = f" ({change:+.1f})"
                f.write(f"  Iteration {i}: {score:.1f}%{delta}\n")
            
            f.write("\nCAMERA POSITIONS PER ITERATION:\n")
            for i, record in enumerate(self.iteration_data):
                cam_pos = record.get('camera_position')
                if cam_pos:
                    loc = cam_pos.get('location', {})
                    rot = cam_pos.get('rotation', {})
                    f.write(f"  Iteration {i}:\n")
                    f.write(f"    Position: X={loc.get('x', 0):.1f}, Y={loc.get('y', 0):.1f}, Z={loc.get('z', 0):.1f}\n")
                    f.write(f"    Rotation: Pitch={rot.get('pitch', 0):.1f}, Yaw={rot.get('yaw', 0):.1f}, Roll={rot.get('roll', 0):.1f}\n")
                else:
                    f.write(f"  Iteration {i}: No camera data\n")
            
            f.write("\n" + "="*70 + "\n")

        if UNREAL_AVAILABLE:
            unreal.log(f"✅ Saved summary: {filepath}")
        else:
            print(f"✅ Saved summary: {filepath}")


class MetricsSummaryReport:
    """
    Aggregates metrics from multiple test runs for thesis tables and graphs
    """
    
    def __init__(self, metrics_dir: Path):
        """
        Args:
            metrics_dir: Directory containing all metrics JSON files
        """
        self.metrics_dir = Path(metrics_dir)
        self.all_metrics: List[Dict[str, Any]] = []
        self._load_all_metrics()
    
    def _load_all_metrics(self):
        """Load all metrics JSON files"""
        json_files = list(self.metrics_dir.glob("*_metrics.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    self.all_metrics.append(data)
            except Exception as e:
                print(f"⚠️ Failed to load {json_file}: {e}")
    
    def generate_comparison_table(self, output_file: str = "comparison_table.csv"):
        """
        Generate comparison table (Table 5.1 in thesis)
        Compares baseline vs multiview for each scene
        """
        filepath = self.metrics_dir / output_file
        
        # Group by scene_id
        scenes = {}
        for metric in self.all_metrics:
            scene_id = metric['scene_id']
            approach = metric['approach']
            
            if scene_id not in scenes:
                scenes[scene_id] = {}
            scenes[scene_id][approach] = metric
        
        # Write CSV
        with open(filepath, 'w', newline='') as f:
            fieldnames = [
                'scene_id', 'complexity', 'num_characters', 'environment',
                'baseline_initial_acc', 'baseline_final_acc', 'baseline_iterations',
                'multiview_initial_acc', 'multiview_final_acc', 'multiview_iterations',
                'baseline_time_sec', 'multiview_time_sec',
                'accuracy_gain_pp', 'iteration_reduction', 'time_difference_sec'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for scene_id, approaches in scenes.items():
                baseline = approaches.get('baseline', {})
                multiview = approaches.get('multiview', {})
                
                if not baseline or not multiview:
                    continue  # Skip incomplete comparisons
                
                row = {
                    'scene_id': scene_id,
                    'complexity': baseline.get('complexity', ''),
                    'num_characters': baseline.get('num_characters', 0),
                    'environment': baseline.get('environment', ''),
                    
                    'baseline_initial_acc': baseline.get('initial_accuracy', 0),
                    'baseline_final_acc': baseline.get('final_accuracy', 0),
                    'baseline_iterations': baseline.get('total_iterations', 0),
                    
                    'multiview_initial_acc': multiview.get('initial_accuracy', 0),
                    'multiview_final_acc': multiview.get('final_accuracy', 0),
                    'multiview_iterations': multiview.get('total_iterations', 0),
                    
                    'baseline_time_sec': baseline.get('total_time_seconds', 0),
                    'multiview_time_sec': multiview.get('total_time_seconds', 0),
                    
                    'accuracy_gain_pp': (
                        multiview.get('final_accuracy', 0) - baseline.get('final_accuracy', 0)
                    ),
                    'iteration_reduction': (
                        baseline.get('total_iterations', 0) - multiview.get('total_iterations', 0)
                    ),
                    'time_difference_sec': (
                        baseline.get('total_time_seconds', 0) - multiview.get('total_time_seconds', 0)
                    )
                }
                
                writer.writerow(row)
        
        print(f"✅ Generated comparison table: {filepath}")
        return filepath
    
    def generate_summary_statistics(self, output_file: str = "summary_statistics.txt"):
        """
        Generate summary statistics table (Table 5.2 in thesis)
        """
        filepath = self.metrics_dir / output_file
        
        # Separate baseline and multiview
        baseline_metrics = [m for m in self.all_metrics if m['approach'] == 'baseline']
        multiview_metrics = [m for m in self.all_metrics if m['approach'] == 'multiview']
        
        def calc_stats(metrics_list: List[Dict], key: str) -> Dict:
            values = [m.get(key, 0) for m in metrics_list if m.get(key) is not None]
            if not values:
                return {'mean': 0, 'std': 0, 'min': 0, 'max': 0}
            return {
                'mean': statistics.mean(values),
                'std': statistics.stdev(values) if len(values) > 1 else 0,
                'min': min(values),
                'max': max(values)
            }
        
        with open(filepath, 'w') as f:
            f.write("="*70 + "\n")
            f.write("SUMMARY STATISTICS (Table 5.2)\n")
            f.write("="*70 + "\n\n")
            
            # Accuracy
            baseline_acc = calc_stats(baseline_metrics, 'final_accuracy')
            multiview_acc = calc_stats(multiview_metrics, 'final_accuracy')
            
            f.write("MEAN ACCURACY:\n")
            f.write(f"  Baseline: {baseline_acc['mean']:.1f}% ± {baseline_acc['std']:.1f}%\n")
            f.write(f"  Multiview: {multiview_acc['mean']:.1f}% ± {multiview_acc['std']:.1f}%\n")
            f.write(f"  Improvement: {multiview_acc['mean'] - baseline_acc['mean']:+.1f} pp\n\n")
            
            # Iterations
            baseline_iter = calc_stats(baseline_metrics, 'total_iterations')
            multiview_iter = calc_stats(multiview_metrics, 'total_iterations')
            
            f.write("MEAN ITERATIONS:\n")
            f.write(f"  Baseline: {baseline_iter['mean']:.1f} ± {baseline_iter['std']:.1f}\n")
            f.write(f"  Multiview: {multiview_iter['mean']:.1f} ± {multiview_iter['std']:.1f}\n")
            reduction_pct = ((baseline_iter['mean'] - multiview_iter['mean']) / baseline_iter['mean'] * 100)
            f.write(f"  Reduction: -{reduction_pct:.0f}%\n\n")
            
            # Success rate
            baseline_converged = sum(1 for m in baseline_metrics if m.get('converged', False))
            multiview_converged = sum(1 for m in multiview_metrics if m.get('converged', False))
            
            f.write("SUCCESS RATE (Converged):\n")
            f.write(f"  Baseline: {baseline_converged}/{len(baseline_metrics)} ")
            f.write(f"({baseline_converged/len(baseline_metrics)*100:.0f}%)\n")
            f.write(f"  Multiview: {multiview_converged}/{len(multiview_metrics)} ")
            f.write(f"({multiview_converged/len(multiview_metrics)*100:.0f}%)\n\n")
            
            # Processing time
            baseline_time = calc_stats(baseline_metrics, 'total_time_seconds')
            multiview_time = calc_stats(multiview_metrics, 'total_time_seconds')
            
            f.write("MEAN PROCESSING TIME:\n")
            f.write(f"  Baseline: {baseline_time['mean']:.1f}s ± {baseline_time['std']:.1f}s\n")
            f.write(f"  Multiview: {multiview_time['mean']:.1f}s ± {multiview_time['std']:.1f}s\n\n")
            
            # Cost
            baseline_cost = calc_stats(baseline_metrics, 'total_cost')
            multiview_cost = calc_stats(multiview_metrics, 'total_cost')
            
            f.write("MEAN TOTAL COST:\n")
            f.write(f"  Baseline: ${baseline_cost['mean']:.4f} ± ${baseline_cost['std']:.4f}\n")
            f.write(f"  Multiview: ${multiview_cost['mean']:.4f} ± ${multiview_cost['std']:.4f}\n\n")
            
            f.write("="*70 + "\n")
        
        print(f"✅ Generated summary statistics: {filepath}")
        return filepath
    
    def export_for_plotting(self, output_file: str = "convergence_data.json"):
        """
        Export data formatted for creating convergence graphs (Figure 5.1)
        """
        filepath = self.metrics_dir / output_file
        
        # Calculate mean accuracy at each iteration for baseline and multiview
        baseline_metrics = [m for m in self.all_metrics if m['approach'] == 'baseline']
        multiview_metrics = [m for m in self.all_metrics if m['approach'] == 'multiview']
        
        def calc_mean_by_iteration(metrics_list: List[Dict]) -> List[Dict]:
            """Calculate mean and std at each iteration number"""
            max_iterations = max(len(m.get('accuracy_by_iteration', [])) for m in metrics_list)
            
            result = []
            for iter_num in range(max_iterations):
                scores = [
                    m['accuracy_by_iteration'][iter_num]
                    for m in metrics_list
                    if len(m.get('accuracy_by_iteration', [])) > iter_num
                ]
                
                if scores:
                    result.append({
                        'iteration': iter_num,
                        'mean': statistics.mean(scores),
                        'std': statistics.stdev(scores) if len(scores) > 1 else 0,
                        'count': len(scores)
                    })
            
            return result
        
        plot_data = {
            'baseline': calc_mean_by_iteration(baseline_metrics),
            'multiview': calc_mean_by_iteration(multiview_metrics)
        }
        
        with open(filepath, 'w') as f:
            json.dump(plot_data, f, indent=2)
        
        print(f"✅ Generated plotting data: {filepath}")
        return filepath
