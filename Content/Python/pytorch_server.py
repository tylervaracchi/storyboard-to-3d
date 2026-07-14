"""
PyTorch Depth Estimation Server - Runs in Separate Process

This server runs OUTSIDE Unreal Engine's embedded Python to avoid
memory allocator conflicts and DLL dependency issues between PyTorch
and UE's embedded environment.

Communication: JSON over stdin/stdout
Model: Depth-Anything-V2-Small-hf
"""

import sys
import json
import base64
from io import BytesIO
import traceback

def log(message):
    """Log to stderr (stdout is used for JSON responses)"""
    print(f"[PyTorch Server] {message}", file=sys.stderr, flush=True)

def initialize_model():
    """Initialize Depth-Anything-V2 model"""
    try:
        log("Initializing PyTorch and transformers...")
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        from PIL import Image
        import numpy as np
        
        log("Loading Depth-Anything-V2-Small model...")
        processor = AutoImageProcessor.from_pretrained(
            "depth-anything/Depth-Anything-V2-Small-hf"
        )
        model = AutoModelForDepthEstimation.from_pretrained(
            "depth-anything/Depth-Anything-V2-Small-hf"
        )
        
        # Device selection
        if torch.cuda.is_available():
            device = "cuda"
            log(f"✅ Using CUDA: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            log("✅ Using CPU")
        
        model.to(device)
        model.eval()
        
        log("✅ Model loaded successfully")
        return processor, model, device, torch, Image, np
    
    except Exception as e:
        log(f"❌ Failed to initialize model: {e}")
        traceback.print_exc(file=sys.stderr)
        return None

def process_depth_request(request, processor, model, device, torch, Image, np):
    """Process a single depth estimation request"""
    try:
        # Decode base64 image
        image_b64 = request.get('image')
        if not image_b64:
            return {'error': 'No image provided'}
        
        image_data = base64.b64decode(image_b64)
        image = Image.open(BytesIO(image_data)).convert('RGB')
        
        # Preprocess
        inputs = processor(images=image, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            outputs = model(**inputs)
            predicted_depth = outputs.predicted_depth
        
        # Post-process
        prediction = torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=image.size[::-1],
            mode="bicubic",
            align_corners=False,
        )
        
        # Convert to numpy and normalize
        depth = prediction.squeeze().cpu().numpy()
        depth_normalized = (depth - depth.min()) / (depth.max() - depth.min())
        
        # Apply colormap for better visualization (like Hugging Face demos)
        # Using Turbo colormap: blue=far, red=near (perceptually uniform)
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            
            # Apply colormap (turbo is perceptually better than jet)
            depth_colored = plt.cm.turbo(depth_normalized)  # Returns RGBA
            depth_rgb = (depth_colored[:, :, :3] * 255).astype(np.uint8)  # Convert to RGB
            
            # Convert to PIL Image and encode
            depth_image = Image.fromarray(depth_rgb, mode='RGB')
            buffer = BytesIO()
            depth_image.save(buffer, format='PNG')
            depth_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            log("✅ Applied Turbo colormap (RGB depth visualization)")
            
        except ImportError as e:
            # Fallback to grayscale if matplotlib not available
            log(f"⚠️ Matplotlib not available ({e}), using grayscale depth")
            depth_uint8 = (depth_normalized * 255).astype(np.uint8)
            depth_image = Image.fromarray(depth_uint8, mode='L')
            buffer = BytesIO()
            depth_image.save(buffer, format='PNG')
            depth_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            # Catch any other colormap errors
            log(f"⚠️ Colormap failed ({e}), using grayscale depth")
            depth_uint8 = (depth_normalized * 255).astype(np.uint8)
            depth_image = Image.fromarray(depth_uint8, mode='L')
            buffer = BytesIO()
            depth_image.save(buffer, format='PNG')
            depth_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            'success': True,
            'depth_map': depth_b64,
            'min_depth': float(depth.min()),
            'max_depth': float(depth.max()),
            'shape': list(depth.shape)
        }
    
    except Exception as e:
        log(f"❌ Error processing request: {e}")
        traceback.print_exc(file=sys.stderr)
        return {'error': str(e)}

def main():
    """Main server loop"""
    log("="*60)
    log("PyTorch Depth Estimation Server Starting...")
    log("="*60)
    
    # Initialize model
    init_result = initialize_model()
    if init_result is None:
        # Send initialization failure
        response = {
            'status': 'error',
            'message': 'Failed to initialize model'
        }
        print(json.dumps(response), flush=True)
        sys.exit(1)
    
    processor, model, device, torch, Image, np = init_result
    
    # Send ready signal
    ready_response = {
        'status': 'ready',
        'device': device,
        'model': 'Depth-Anything-V2-Small-hf'
    }
    print(json.dumps(ready_response), flush=True)
    
    log("Server ready, waiting for requests...")
    log("="*60)
    
    # Request processing loop
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                log("EOF received, shutting down...")
                break
            
            line = line.strip()
            if not line:
                continue
            
            # Parse request
            request = json.loads(line)
            
            # Handle shutdown
            if request.get('command') == 'shutdown':
                log("Shutdown command received")
                response = {'status': 'shutdown'}
                print(json.dumps(response), flush=True)
                break
            
            # Handle ping
            if request.get('command') == 'ping':
                response = {'status': 'pong'}
                print(json.dumps(response), flush=True)
                continue
            
            # Process depth estimation
            result = process_depth_request(request, processor, model, device, torch, Image, np)
            print(json.dumps(result), flush=True)
        
        except json.JSONDecodeError as e:
            log(f"Invalid JSON: {e}")
            error_response = {'error': f'Invalid JSON: {str(e)}'}
            print(json.dumps(error_response), flush=True)
        
        except Exception as e:
            log(f"Unexpected error: {e}")
            traceback.print_exc(file=sys.stderr)
            error_response = {'error': f'Server error: {str(e)}'}
            print(json.dumps(error_response), flush=True)
    
    log("Server shutdown complete")

if __name__ == '__main__':
    main()
