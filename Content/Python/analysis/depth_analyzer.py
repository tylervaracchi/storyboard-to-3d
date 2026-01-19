# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Depth-Anything-V2 Integration for Storyboard Analysis (Subprocess Client)

This module runs PyTorch in a SEPARATE PROCESS to avoid memory allocator conflicts
and DLL dependency issues with Unreal Engine's embedded Python environment.

Architecture:
- pytorch_server.py: Standalone process running torch/transformers
- depth_analyzer.py: Client that communicates via subprocess JSON IPC
- No direct torch imports in UE's Python environment (stable, no crashes)
"""

import base64
import subprocess
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO
import threading
import queue

# Try importing unreal for logging (will fail outside UE)
try:
    import unreal
    def log(msg):
        unreal.log(msg)
    def log_warning(msg):
        unreal.log_warning(msg)
    def log_error(msg):
        unreal.log_error(msg)
except ImportError:
    def log(msg):
        print(msg)
    def log_warning(msg):
        print(f"WARNING: {msg}")
    def log_error(msg):
        print(f"ERROR: {msg}")

# Optional: NumPy for depth analysis (lightweight, no PyTorch dependency)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    log_warning(" NumPy not available - depth relationship analysis disabled")


class DepthAnalyzer:
    """
    Analyzes depth from storyboard images using Depth-Anything-V2
    Works with line art sketches, not just photorealistic images
    """

    def __init__(self):
        """Initialize depth analyzer by spawning PyTorch server process"""
        self.available = False
        self.process = None
        self.device = "unknown"

        log(" Initializing DepthAnalyzer (subprocess mode)...")

        try:
            # Find pytorch_server.py (same directory as this file)
            server_path = Path(__file__).parent.parent / "pytorch_server.py"

            if not server_path.exists():
                log_error(f" PyTorch server not found at: {server_path}")
                log_error("   Expected: pytorch_server.py in plugin Python directory")
                return

            log(f" Found PyTorch server: {server_path}")
            log(" Starting PyTorch server process...")
            log("   (First run will download ~150MB Depth-Anything-V2 model)")

            # Determine which Python to use
            # UE's sys.executable points to UnrealEditor.exe, not Python!
            # We need to find actual Python interpreters
            python_candidates = []

            # Try to find UE's embedded Python
            if sys.executable:
                ue_dir = Path(sys.executable).parent.parent.parent  # Up from Binaries/Win64
                ue_python = ue_dir / "Binaries" / "ThirdParty" / "Python3" / "Win64" / "python.exe"
                if ue_python.exists():
                    python_candidates.append(str(ue_python))

            # Add user's miniconda (known to have transformers)
            python_candidates.append(r"C:\Users\tyler\miniconda3\python.exe")

            # Add system Python from PATH
            python_candidates.append("python")

            # Find first existing Python
            python_exe = None
            for candidate in python_candidates:
                candidate_path = Path(candidate)
                if candidate_path.exists() and candidate_path.suffix == '.exe':
                    python_exe = str(candidate_path)
                    log(f"   Using Python: {python_exe}")
                    break

            if not python_exe:
                # Fallback to miniconda (hardcoded path known to work)
                python_exe = r"C:\Users\tyler\miniconda3\python.exe"
                log(f"   Fallback to miniconda: {python_exe}")

            # Spawn subprocess with PyTorch server
            self.process = subprocess.Popen(
                [python_exe, str(server_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )

            log("⏳ Waiting for server initialization...")

            # Wait for ready signal (with timeout)
            start_time = time.time()
            max_timeout = 60  # 60 seconds total for model download on first run

            while time.time() - start_time < max_timeout:
                remaining_time = max_timeout - (time.time() - start_time)
                line, timed_out = self._read_line_with_timeout(min(5, remaining_time))

                if timed_out:
                    # Check if process is still alive
                    exit_code = self.process.poll()
                    if exit_code is not None:
                        # Process died
                        log_error(f" PyTorch server crashed during startup (exit code: {exit_code})")
                        try:
                            stderr_output = self.process.stderr.read()
                            if stderr_output:
                                log_error(f"   Stderr output:")
                                for err_line in stderr_output.split('\n')[:20]:  # Limit to 20 lines
                                    if err_line.strip():
                                        log_error(f"      {err_line}")
                        except:
                            pass
                        log_error(f"   Possible causes:")
                        log_error(f"      1. Missing dependencies: pip install torch transformers pillow")
                        log_error(f"      2. Python interpreter issue")
                        log_error(f"      3. Try running manually: python pytorch_server.py")
                        self._cleanup()
                        return
                    # Still running, continue waiting
                    continue

                if not line:
                    # Empty line, process likely died
                    log_error(" PyTorch server process terminated unexpectedly")
                    self._cleanup()
                    return

                try:
                    response = json.loads(line.strip())
                    if response.get('status') == 'ready':
                        self.device = response.get('device', 'unknown')
                        log(f" PyTorch server ready (device: {self.device})")
                        log(f"   Model: {response.get('model', 'Depth-Anything-V2')}")
                        self.available = True
                        return
                    elif response.get('status') == 'error':
                        log_error(f" Server initialization failed: {response.get('message')}")
                        self._cleanup()
                        return
                except json.JSONDecodeError:
                    # Server log message, not JSON response
                    continue

            # Timeout
            log_error(f" PyTorch server startup timeout ({max_timeout}s)")
            log_error("   Possible issues: slow model download, missing dependencies")
            self._cleanup()

        except Exception as e:
            log_error(f" Failed to start PyTorch server: {e}")
            import traceback
            log_error(traceback.format_exc())
            self._cleanup()

    def _read_line_with_timeout(self, timeout_seconds):
        """
        Read a line from subprocess stdout with timeout

        Returns:
            (line, timed_out) tuple
            - line: str or None
            - timed_out: True if timeout occurred
        """
        result_queue = queue.Queue()

        def reader():
            try:
                line = self.process.stdout.readline()
                result_queue.put(('line', line))
            except Exception as e:
                result_queue.put(('error', str(e)))

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        try:
            result_type, result_value = result_queue.get(timeout=timeout_seconds)
            if result_type == 'line':
                return (result_value, False)
            else:
                log_error(f"Error reading from subprocess: {result_value}")
                return (None, True)
        except queue.Empty:
            # Timeout occurred
            return (None, True)

    def _cleanup(self):
        """Clean up subprocess"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.process = None
        self.available = False

    def shutdown(self):
        """
        Gracefully shutdown the depth analyzer subprocess
        Call this to clean up resources
        """
        log(" Shutting down depth analyzer...")
        self._cleanup()
        log(" Depth analyzer shutdown complete")

    def __del__(self):
        """Cleanup on deletion"""
        self._cleanup()

    def generate_depth_map(self, image_b64: str) -> Optional[Dict[str, Any]]:
        """
        Generate depth map from base64 encoded image (via subprocess)

        Args:
            image_b64: Base64 encoded image string

        Returns:
            Dict with:
                - success: bool
                - depth_map_b64: Base64 encoded depth map (grayscale)
                - stats: Dict with min/max depth
                - error: Error message if failed
        """
        if not self.available or not self.process:
            return {
                'success': False,
                'error': 'DepthAnalyzer not available (server not running)'
            }

        try:
            log(f" Sending depth request to subprocess...")
            log(f"   Image size: {len(image_b64)} chars")

            # Send request to subprocess
            request = json.dumps({'image': image_b64}) + '\n'
            self.process.stdin.write(request)
            self.process.stdin.flush()

            # Read response (with timeout)
            log("⏳ Waiting for depth estimation...")
            start_time = time.time()
            max_timeout = 120  # 2 minutes (reduced from 10 min - if it takes longer, something is wrong)

            while time.time() - start_time < max_timeout:
                remaining_time = max_timeout - (time.time() - start_time)
                elapsed = time.time() - start_time

                # Log progress every 15 seconds
                if int(elapsed) % 15 == 0 and int(elapsed) > 0:
                    log(f"   Still waiting... ({int(elapsed)}s elapsed)")

                line, timed_out = self._read_line_with_timeout(min(5, remaining_time))

                if timed_out:
                    # Check if process is still alive
                    exit_code = self.process.poll()
                    if exit_code is not None:
                        # Process died
                        log_error(f" PyTorch server crashed (exit code: {exit_code})")
                        self._cleanup()
                        return {'success': False, 'error': 'Server process died during inference'}
                    # Still running, continue waiting
                    continue

                if not line:
                    # Empty line, process likely died
                    log_error(" PyTorch server process terminated unexpectedly")
                    self._cleanup()
                    return {'success': False, 'error': 'Server process died'}

                try:
                    response = json.loads(line.strip())

                    if response.get('error'):
                        log_error(f" Server error: {response['error']}")
                        return {'success': False, 'error': response['error']}

                    if response.get('success'):
                        elapsed_time = time.time() - start_time
                        log(f" Depth map received from server ({elapsed_time:.1f}s)")
                        log(f"   Depth range: {response.get('min_depth', 0):.2f} - {response.get('max_depth', 0):.2f}")

                        # Return result (depth_array requires NumPy, optional)
                        result = {
                            'success': True,
                            'depth_map_b64': response['depth_map'],
                            'stats': {
                                'min': response.get('min_depth', 0),
                                'max': response.get('max_depth', 0)
                            }
                        }

                        # Optionally decode depth_array if NumPy available
                        if NUMPY_AVAILABLE:
                            try:
                                from PIL import Image
                                depth_data = base64.b64decode(response['depth_map'])
                                depth_image = Image.open(BytesIO(depth_data))
                                result['depth_array'] = np.array(depth_image)
                            except:
                                pass  # depth_array optional

                        return result

                except json.JSONDecodeError:
                    # Server log message, skip
                    continue

            # Timeout - kill the hung subprocess
            log_error(f" Depth estimation timeout ({max_timeout}s)")
            log_error("   Subprocess appears to be hung - terminating it")
            self._cleanup()
            return {'success': False, 'error': f'Request timeout after {max_timeout}s - subprocess hung'}

        except Exception as e:
            log_error(f" Error in depth estimation: {e}")
            import traceback
            log_error(traceback.format_exc())
            return {'success': False, 'error': str(e)}

    def analyze_depth_relationships(self, depth_array: np.ndarray,
                                   character_positions: list) -> Dict[str, Any]:
        """
        Analyze depth relationships between characters

        Args:
            depth_array: NumPy array of depth values (0-255)
            character_positions: List of dicts with {name, x, y, width, height}

        Returns:
            Dict with depth ordering and relative distances
        """
        if not self.available or not NUMPY_AVAILABLE:
            return {'success': False, 'error': 'NumPy required for depth relationship analysis'}

        try:
            log(f" Analyzing depth for {len(character_positions)} characters")

            character_depths = []

            for char in character_positions:
                # Sample depth at character center
                cx = int(char['x'] + char['width'] / 2)
                cy = int(char['y'] + char['height'] / 2)

                # Get depth value (clamp to image bounds)
                cy = max(0, min(cy, depth_array.shape[0] - 1))
                cx = max(0, min(cx, depth_array.shape[1] - 1))
                depth_value = float(depth_array[cy, cx])

                # Sample average depth in character region
                y1, y2 = max(0, char['y']), min(depth_array.shape[0], char['y'] + char['height'])
                x1, x2 = max(0, char['x']), min(depth_array.shape[1], char['x'] + char['width'])
                region_depth = float(depth_array[y1:y2, x1:x2].mean())

                character_depths.append({
                    'name': char['name'],
                    'depth_center': depth_value,
                    'depth_avg': region_depth,
                    'position': (cx, cy)
                })

                log(f"   {char['name']}: depth_center={depth_value:.1f}, depth_avg={region_depth:.1f}")

            # Sort by depth (higher value = closer to camera in Depth-Anything output)
            sorted_chars = sorted(character_depths, key=lambda x: x['depth_avg'], reverse=True)

            depth_order = [char['name'] for char in sorted_chars]
            log(f"   Depth ordering (front to back): {depth_order}")

            return {
                'success': True,
                'character_depths': character_depths,
                'depth_order': depth_order,  # Front to back
                'sorted_characters': sorted_chars
            }

        except Exception as e:
            log_error(f" Error analyzing depth relationships: {e}")
            import traceback
            log_error(traceback.format_exc())
            return {'success': False, 'error': str(e)}


# Module-level test
if __name__ == "__main__":
    print("=" * 80)
    print("Testing DepthAnalyzer")
    print("=" * 80)
    print()

    # Initialize analyzer
    analyzer = DepthAnalyzer()

    if not analyzer.available:
        print("DepthAnalyzer not available")
        print("Ensure pytorch_server.py dependencies are installed:")
        print("pip install torch transformers pillow numpy")
        sys.exit(1)

    print(f"DepthAnalyzer initialized successfully (device: {analyzer.device})")
    print()

    # Create test image (simple geometric shapes at different depths)
    print("Creating test image...")
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("PIL required for test: pip install pillow")
        sys.exit(1)

    test_img = Image.new('RGB', (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(test_img)

    # Draw shapes: larger = closer, smaller = farther
    draw.rectangle([100, 200, 300, 500], fill=(0, 0, 0), outline=(0, 0, 0))  # Large (close)
    draw.rectangle([400, 250, 550, 450], fill=(50, 50, 50), outline=(50, 50, 50))  # Medium
    draw.rectangle([600, 300, 700, 400], fill=(100, 100, 100), outline=(100, 100, 100))  # Small (far)

    # Encode to base64
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    test_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    print(f"Test image created: {len(test_b64)} chars")
    print()

    # Generate depth map
    print("Generating depth map...")
    result = analyzer.generate_depth_map(test_b64)

    if result['success']:
        print("Depth map generated successfully!")
        print(f"Stats: {result['stats']}")
        print()

        # Test depth relationships
        print("Analyzing depth relationships...")
        character_positions = [
            {'name': 'Character_A', 'x': 100, 'y': 200, 'width': 200, 'height': 300},
            {'name': 'Character_B', 'x': 400, 'y': 250, 'width': 150, 'height': 200},
            {'name': 'Character_C', 'x': 600, 'y': 300, 'width': 100, 'height': 100}
        ]

        relationships = analyzer.analyze_depth_relationships(
            result['depth_array'],
            character_positions
        )

        if relationships['success']:
            print("Depth relationships analyzed!")
            print(f"Depth order (front to back): {relationships['depth_order']}")
            print()
        else:
            print(f"Relationship analysis failed: {relationships['error']}")
    else:
        print(f"Depth map generation failed: {result['error']}")

    print("=" * 80)
    print("Test complete!")
    print("=" * 80)
