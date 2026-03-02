
import os
import logging
import time
import gc

# Lazy imports
torch = None
HeavyEditor = None

logger = logging.getLogger("gpu_utils")

class ModelManager:
    _instance = None
    _editor = None
    
    @classmethod
    def get_editor(cls):
        global torch, HeavyEditor
        if cls._editor is None:
            from Upscale_Modules.compute_caps import ComputeCaps
            caps = ComputeCaps.get()
            if not caps["allow_ai_enhance"]:
                 logger.warning("⚠️ GPU Access Denied by ComputeCaps (Low VRAM or CPU Mode).")
                 return None
                 
            logger.info("🔄 Initializing Persistent AI Engine...")
            try:
                import torch
                from Upscale_Modules.ai_engine import HeavyEditor
                
                # Load config from env
                scale = 2
                enhancement_level = os.getenv("ENHANCEMENT_LEVEL", "2x").lower().strip()
                
                # Harden ENHANCEMENT_LEVEL parsing
                if "high" in enhancement_level or "4" in enhancement_level:
                    scale = 4
                elif "medium" in enhancement_level or "2" in enhancement_level:
                    scale = 2
                elif "low" in enhancement_level:
                    scale = 2 # Best stable low-tier upscale
                elif enhancement_level == "auto":
                    scale = 2
                else:
                    # Default for invalid or missing
                    scale = 2
                
                face_enhance = os.getenv("ENABLE_FACE_ENHANCE", "yes").lower() == "yes"
                
                cls._editor = HeavyEditor(scale=scale, face_enhance=face_enhance)
                logger.info(f"✅ AI Engine loaded (Scale: {scale}x) and cached.")
            except ImportError as e:
                logger.error(f"❌ AI libraries missing (Torch/RealESRGAN): {e}")
                raise e
            except Exception as e:
                logger.error(f"❌ Failed to load AI Engine: {e}")
                raise e
        return cls._editor

    @classmethod
    def unload(cls):
        if cls._editor:
            del cls._editor
            cls._editor = None
            if torch and torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            logger.info("🗑️ AI Engine unloaded and GPU memory cleared.")

def run_gpu_inference(input_path, output_path, options=None):
    """
    Run GPU inference with retries and memory management.
    """
    options = options or {}
    max_retries = int(os.getenv("FALLBACK_RETRY_COUNT", "2"))
    
    for attempt in range(max_retries + 1):
        try:
            editor = ModelManager.get_editor()
            
            # Update editor settings if needed (hacky, better if editor supported dynamic config)
            # For now we assume persistent settings or reload if critical change needed
            
            success = editor.process_video(input_path, output_path)
            if success:
                return True
            else:
                raise RuntimeError("Editor returned False")
                
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                logger.warning(f"⚠️ GPU OOM detected (Attempt {attempt+1}/{max_retries+1}). Clearing cache...")
                if torch and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Optionally reduce batch size or tile size here if we had access to modify editor config
                # For now, we just retry or fail
            else:
                logger.warning(f"⚠️ GPU Inference failed: {e}")
                
            if attempt == max_retries:
                logger.error("❌ All GPU retries failed.")
                return False
            
            time.sleep(int(os.getenv("FALLBACK_BACKOFF_SECONDS", "5")))
            
    return False
