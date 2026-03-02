"""
Import Gate Authority
---------------------
Centralized gatekeeper for heavy imports (Torch, Diffusers, etc.).
Consults ComputeCaps to allow or block modules based on VRAM availability.

Usage:
    from Health_handlers.Heavy_import_gate import HeavyImportGate
    
    # Safe Import
    torch = HeavyImportGate.get("torch") # Returns module or None
    
    if torch:
        # Use GPU code
    else:
        # Fallback to CPU/OpenCV
"""

import sys
import logging
import importlib
try:
    from Upscale_Modules.compute_caps import ComputeCaps
except ImportError:
    try:
        from .compute_caps import ComputeCaps
    except (ImportError, ValueError):
        from compute_caps import ComputeCaps

logger = logging.getLogger("Heavy_import_gate")

class HeavyImportGate:
    _loaded_modules = {}
    
    # Modules classified as "HEAVY" (Require GPU_ENHANCED_MODE)
    _heavy_registry = {
        "torch": "Per-frame AI / Tensors",
        "diffusers": "Texture Synthesis / Stable Diffusion",
        "transformers": "Advanced NLP/Vision",
        "basicsr": "Super Resolution",
        "gfpgan": "Face Restoration",
        "realesrgan": "Upscaling"
    }

    @staticmethod
    def get(module_name: str):
        """
        Attempts to import a module respecting Compute Caps.
        Returns: Module object if allowed/successful, else None.
        """
        # 0. Check Cache
        if module_name in HeavyImportGate._loaded_modules:
            return HeavyImportGate._loaded_modules[module_name]

        # 1. Check Compute Caps AND System Health
        try:
            from Health_handlers import health
        except ImportError:
            try:
                from . import health
            except (ImportError, ValueError):
                import health
        caps = ComputeCaps.get()
        h_status = health.check_health()
        
        allow_ai = caps.get("allow_ai_enhance", False) and h_status.get("safe", True)
        
        # 2. Check Registry
        if module_name in HeavyImportGate._heavy_registry:
            if not allow_ai:
                # BLOCKED
                reason = "CPU Safe Mode" if not caps.get("allow_ai_enhance") else "System Unsafe (Health)"
                logger.info(f"🚫 HeavyImportGate: Blocking '{module_name}' ({reason}).")
                logger.debug(f"   └─ Reason: {HeavyImportGate._heavy_registry[module_name]}")
                return None
            else:
                # ALLOWED: But log it
                logger.info(f"⚡ HeavyImportGate: Allowing '{module_name}' (Health & Compute Safe).")

        # 3. Attempt Import
        try:
            mod = importlib.import_module(module_name)
            HeavyImportGate._loaded_modules[module_name] = mod
            return mod
        except ImportError as e:
            logger.warning(f"⚠️ HeavyImportGate: Failed to import '{module_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"❌ HeavyImportGate: Unexpected error importing '{module_name}': {e}")
            return None

    @staticmethod
    def is_active(module_name: str) -> bool:
        """Returns True if module is successfully loaded and active."""
        return module_name in sys.modules and HeavyImportGate.get(module_name) is not None
