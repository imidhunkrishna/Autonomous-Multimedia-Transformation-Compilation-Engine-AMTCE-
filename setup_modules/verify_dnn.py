
import logging
import sys
import os

# Setup Logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("--- TESTING DNN LOAD ---")
try:
    from .quality_orchestrator import human_guard
except ImportError:
    try:
        from quality_orchestrator import human_guard
        if human_guard.face_net:
            print("✅ SUCCESS: human_guard.face_net IS LOADED.")
            print(f"   Model Object: {human_guard.face_net}")
            
            # Test Inference with Dummy Frame
            import numpy as np
            import cv2
            dummy = np.zeros((500, 500, 3), dtype=np.uint8)
            faces = human_guard.detect_faces(dummy)
            print(f"✅ INFERENCE TEST: Ran successfully (Faces found: {len(faces)})")
        else:
            print("❌ FAILURE: human_guard.face_net is None.")
    except Exception as nested_e:
        print(f"❌ NESTED IMPORT/EVAL ERROR: {nested_e}")
except Exception as e:
    print(f"❌ CRITICAL ERROR: {e}")
