"""
Multi-Model Comparison Tracker for Thesis
Automatically fills model-specific CSV files based on which AI is running
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


class MultiModelTracker:
    """
    Tracks metrics across 4 different models:
    - GPT-4o (OpenAI)
    - LLaVA 13B (local model)
    - Claude Sonnet 4.5 (Anthropic)
    - Ground Truth (manual positioning)
    
    Each model gets its own CSV with 12 scene slots.
    """
    
    # Model identifiers
    MODELS = {
        'gpt4o': 'GPT-4o',
        'llava': 'LLaVA-13B',
        'sonnet': 'Claude-Sonnet-4.5-Extended-Thinking',
        'groundtruth': 'Ground-Truth-Manual'
    }
    
    # 12 storyboard scenes
    SCENES = [
        'Storyboard_01', 'Storyboard_02', 'Storyboard_03', 'Storyboard_04',
        'Storyboard_05', 'Storyboard_06', 'Storyboard_07', 'Storyboard_08',
        'Storyboard_09', 'Storyboard_10', 'Storyboard_11', 'Storyboard_12'
    ]
    
    def __init__(self, output_dir: Path):
        """
        Initialize multi-model tracker
        
        Args:
            output_dir: Directory to save model comparison CSVs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize all 4 CSV files
        self._initialize_csv_files()
    
    def _initialize_csv_files(self):
        """Create 4 empty CSV files with 12 scene slots each"""
        
        # CSV headers
        headers = [
            'scene_id',
            'initial_accuracy',
            'final_accuracy',
            'improvement',
            'iterations',
            'converged',
            'convergence_iteration',
            'total_time_sec',
            'total_cost',
            'avg_cost_per_iteration',
            'monotonic_improvement',
            'oscillating',
            'timestamp'
        ]
        
        # Create CSV for each model
        for model_key, model_name in self.MODELS.items():
            csv_file = self.output_dir / f"{model_name}_comparison.csv"
            
            # Only create if doesn't exist (preserve existing data)
            if not csv_file.exists():
                with open(csv_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    
                    # Write 12 empty rows (one per storyboard)
                    for scene_id in self.SCENES:
                        row = {h: '' for h in headers}
                        row['scene_id'] = scene_id
                        writer.writerow(row)
                
                print(f"✅ Created: {csv_file.name}")
            else:
                print(f"ℹ️ Already exists: {csv_file.name}")
    
    def detect_current_model(self, ai_client) -> str:
        """
        Auto-detect which AI model is currently running
        
        Args:
            ai_client: The AI client object with model/provider info
            
        Returns:
            Model key: 'gpt4o', 'llava', 'sonnet', or 'groundtruth'
        """
        if not ai_client:
            return 'groundtruth'
        
        # Check provider type
        provider = getattr(ai_client, 'provider', '').lower()
        model_name = getattr(ai_client, 'model', '').lower()
        
        # OpenAI / GPT-4o
        if 'openai' in provider or 'gpt-4o' in model_name or 'gpt4o' in model_name:
            return 'gpt4o'
        
        # Claude / Sonnet (including 3.5, 4, 4.5)
        if 'anthropic' in provider or 'claude' in provider or 'sonnet' in model_name:
            return 'sonnet'
        
        # LLaVA (local model)
        if 'llava' in provider or 'llava' in model_name:
            return 'llava'
        
        # Default to ground truth
        return 'groundtruth'
    
    def get_scene_number_from_panel(self, panel_number: int) -> str:
        """
        Convert panel number to storyboard scene ID
        
        Args:
            panel_number: Panel number (1-12)
            
        Returns:
            Scene ID like 'Storyboard_01'
        """
        if 1 <= panel_number <= 12:
            return f"Storyboard_{panel_number:02d}"
        else:
            # If panel number is outside range, use timestamp
            return f"Storyboard_Extra_{datetime.now().strftime('%H%M%S')}"
    
    def update_model_csv(self, 
                        model_key: str,
                        scene_id: str,
                        metrics: Dict[str, Any]):
        """
        Update a specific model's CSV with metrics for a scene
        
        Args:
            model_key: 'gpt4o', 'llava', 'sonnet', or 'groundtruth'
            scene_id: Scene identifier (e.g., 'Storyboard_01')
            metrics: Dictionary with all metrics
        """
        if model_key not in self.MODELS:
            print(f"⚠️ Unknown model key: {model_key}")
            return
        
        model_name = self.MODELS[model_key]
        csv_file = self.output_dir / f"{model_name}_comparison.csv"
        
        if not csv_file.exists():
            print(f"⚠️ CSV file not found: {csv_file}")
            return
        
        # Read existing CSV
        rows = []
        with open(csv_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Find and update the matching scene row
        scene_found = False
        for row in rows:
            if row['scene_id'] == scene_id:
                # Update with new metrics
                row['initial_accuracy'] = metrics.get('initial_accuracy', '')
                row['final_accuracy'] = metrics.get('final_accuracy', '')
                row['improvement'] = metrics.get('improvement', '')
                row['iterations'] = metrics.get('total_iterations', '')
                row['converged'] = 'Yes' if metrics.get('converged') else 'No'
                row['convergence_iteration'] = metrics.get('convergence_iteration', '')
                row['total_time_sec'] = f"{metrics.get('total_time_seconds', 0):.1f}"
                row['total_cost'] = f"${metrics.get('total_cost', 0):.4f}"
                row['avg_cost_per_iteration'] = f"${metrics.get('avg_cost_per_iteration', 0):.4f}"
                row['monotonic_improvement'] = 'Yes' if metrics.get('monotonic_improvement') else 'No'
                row['oscillating'] = 'Yes' if metrics.get('oscillating') else 'No'
                row['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                scene_found = True
                break
        
        # If scene not found, add as new row
        if not scene_found:
            new_row = {
                'scene_id': scene_id,
                'initial_accuracy': metrics.get('initial_accuracy', ''),
                'final_accuracy': metrics.get('final_accuracy', ''),
                'improvement': metrics.get('improvement', ''),
                'iterations': metrics.get('total_iterations', ''),
                'converged': 'Yes' if metrics.get('converged') else 'No',
                'convergence_iteration': metrics.get('convergence_iteration', ''),
                'total_time_sec': f"{metrics.get('total_time_seconds', 0):.1f}",
                'total_cost': f"${metrics.get('total_cost', 0):.4f}",
                'avg_cost_per_iteration': f"${metrics.get('avg_cost_per_iteration', 0):.4f}",
                'monotonic_improvement': 'Yes' if metrics.get('monotonic_improvement') else 'No',
                'oscillating': 'Yes' if metrics.get('oscillating') else 'No',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            rows.append(new_row)
        
        # Write back to CSV
        with open(csv_file, 'w', newline='') as f:
            fieldnames = [
                'scene_id', 'initial_accuracy', 'final_accuracy', 'improvement',
                'iterations', 'converged', 'convergence_iteration',
                'total_time_sec', 'total_cost', 'avg_cost_per_iteration',
                'monotonic_improvement', 'oscillating', 'timestamp'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✅ Updated: {model_name}_comparison.csv")
        print(f"   Scene: {scene_id}")
        print(f"   Final Accuracy: {metrics.get('final_accuracy', 'N/A')}%")
        print(f"   Iterations: {metrics.get('total_iterations', 'N/A')}")
    
    def get_comparison_summary(self) -> Dict[str, Any]:
        """
        Generate summary comparing all models across all scenes
        
        Returns:
            Dictionary with comparison statistics
        """
        summary = {}
        
        for model_key, model_name in self.MODELS.items():
            csv_file = self.output_dir / f"{model_name}_comparison.csv"
            
            if not csv_file.exists():
                continue
            
            # Read model's CSV
            rows = []
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Calculate statistics (only for filled rows)
            filled_rows = [r for r in rows if r['final_accuracy']]
            
            if filled_rows:
                accuracies = [float(r['final_accuracy']) for r in filled_rows if r['final_accuracy']]
                iterations = [int(r['iterations']) for r in filled_rows if r['iterations']]
                
                summary[model_name] = {
                    'scenes_completed': len(filled_rows),
                    'mean_accuracy': sum(accuracies) / len(accuracies) if accuracies else 0,
                    'mean_iterations': sum(iterations) / len(iterations) if iterations else 0,
                    'best_accuracy': max(accuracies) if accuracies else 0,
                    'worst_accuracy': min(accuracies) if accuracies else 0
                }
        
        return summary
    
    def print_comparison_table(self):
        """Print a formatted comparison table of all models"""
        summary = self.get_comparison_summary()
        
        if not summary:
            print("No data available yet.")
            return
        
        print("\n" + "="*80)
        print("MODEL COMPARISON SUMMARY")
        print("="*80)
        print(f"{'Model':<25} {'Scenes':<10} {'Accuracy':<15} {'Iterations':<12} {'Best':<10}")
        print("-"*80)
        
        for model_name, stats in summary.items():
            scenes = f"{stats['scenes_completed']}/12"
            accuracy = f"{stats['mean_accuracy']:.1f}%"
            iters = f"{stats['mean_iterations']:.1f}"
            best = f"{stats['best_accuracy']:.1f}%"
            
            print(f"{model_name:<25} {scenes:<10} {accuracy:<15} {iters:<12} {best:<10}")
        
        print("="*80 + "\n")
    
    def export_combined_csv(self):
        """Export a single CSV with all models side-by-side for easy comparison"""
        output_file = self.output_dir / "All_Models_Comparison.csv"
        
        # Collect data from all model CSVs
        all_data = {}
        
        for model_key, model_name in self.MODELS.items():
            csv_file = self.output_dir / f"{model_name}_comparison.csv"
            
            if not csv_file.exists():
                continue
            
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    scene_id = row['scene_id']
                    if scene_id not in all_data:
                        all_data[scene_id] = {'scene_id': scene_id}
                    
                    # Add model-specific columns
                    all_data[scene_id][f'{model_name}_accuracy'] = row['final_accuracy']
                    all_data[scene_id][f'{model_name}_iterations'] = row['iterations']
        
        # Write combined CSV
        with open(output_file, 'w', newline='') as f:
            fieldnames = ['scene_id']
            for model_name in self.MODELS.values():
                fieldnames.extend([f'{model_name}_accuracy', f'{model_name}_iterations'])
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Write rows in order
            for scene_id in self.SCENES:
                if scene_id in all_data:
                    writer.writerow(all_data[scene_id])
        
        print(f"✅ Exported combined comparison: {output_file.name}")
        return output_file
