"""
UTILITY: Hardware Capability Checker (check_hw.py)
------------------------------------------------
Purpose: 
- Quickly verifies if PyTorch can see your NVIDIA GPU.
- Checks CUDA availability and device memory capability.
- Verifies if TensorRT is correctly installed for faster inference.

When to run: 
- Run this manually if you suspect the 'Heavy AI' (Upscaling/Visual Refinement) is slow.
- Useful for debugging why a machine is defaulting to 'CPU Mode'.

Auto-run:
- This is NOT auto-run by the main bot. The bot uses its own 'ComputeCaps' logic.
- Use this as a standalone diagnostic tool.
"""

import torch
import sys

def check():
    print(f"Python Version: {sys.version}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device Name: {torch.cuda.get_device_name(0)}")
        cap = torch.cuda.get_device_capability()
        print(f"Capability: {cap}")
        print(f"FP16 Supported: {cap[0] >= 7}")
    
    try:
        import tensorrt
        print(f"TensorRT Version: {tensorrt.__version__}")
    except ImportError:
        print("TensorRT: missing")

if __name__ == "__main__":
    check()
