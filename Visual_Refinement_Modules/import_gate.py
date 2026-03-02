try:
    from Health_handlers.Heavy_import_gate import HeavyImportGate
except ImportError:
    try:
        from .Heavy_import_gate import HeavyImportGate
    except (ImportError, ValueError):
        try:
            from Heavy_import_gate import HeavyImportGate
        except ImportError:
            HeavyImportGate = None

class ImportGate:
    """
    Safe wrapper for imports that might be missing in sub-environments.
    """
    @staticmethod
    def check_health():
        try:
             # Try to access the real gate
             from Health_handlers.Heavy_import_gate import HeavyImportGate
             return True
        except ImportError:
             return False

    @staticmethod
    def get(name):
        """
        Retrieves a module by name if available.
        For 'gemini_enhance', we bypass the old gate and import directly from the pinned module.
        """
        if name == "gemini_enhance":
            try:
                # Try package import first (Root Execution)
                from Visual_Refinement_Modules import gemini_enhance_for_watermark as gemini_enhance
                return gemini_enhance
            except ImportError:
                try:
                     # Try direct import (Local Execution)
                    import gemini_enhance_for_watermark as gemini_enhance
                    return gemini_enhance
                except ImportError as e:
                    print(f"❌ ImportGate Error: Could not load gemini_enhance_for_watermark: {e}")
                    return None
        return None
