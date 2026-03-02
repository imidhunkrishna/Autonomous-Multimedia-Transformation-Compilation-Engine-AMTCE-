"""
Health Handlers: Unified Module Portal
--------------------------------------
This module acts as the central gatekeeper for all project modules.
It uses a functional approach to import modules conditionally based on 
system health and CPU/GPU modes configured in .env.
"""

from Health_handlers.necessary_import_gate import *
from Health_handlers.health import check_health, is_system_safe, print_health_summary
from Health_handlers.Heavy_import_gate import HeavyImportGate as ImportGate

class ModuleNamespace:
    """A simple container for modules."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def get_portal():
    """
    Scans the system and environment variables (CPU_MODE, GPU_MODE)
    and returns a portal containing authorized modules.
    """
    # 1. System Health & Capability Scan
    status = check_health()
    from Upscale_Modules.compute_caps import ComputeCaps
    caps = ComputeCaps.get()
    
    # Respect .env via ComputeCaps (already updated)
    allow_ai = caps.get("allow_ai_enhance", False) and status.get("safe", True)
    
    # Create the portal dictionary
    portal_data = {
        "os": os, "sys": sys, "logging": logging, "asyncio": asyncio, 
        "shutil": shutil, "re": re, "time": time, "subprocess": subprocess,
        "csv": csv, "json": json, "io": io, "uuid": uuid, "random": random, 
        "tempfile": tempfile, "glob": glob, "Path": Path, "datetime": datetime,
        "List": List, "Optional": Optional, "Dict": Dict, "Tuple": Tuple, "Any": Any,
        "load_dotenv": load_dotenv, "threading": threading, 
        "contextmanager": contextmanager, "urlparse": urlparse, 
        "ThreadPoolExecutor": ThreadPoolExecutor,
        "check_health": check_health, "is_system_safe": is_system_safe,
        "print_health_summary": print_health_summary,
        "ImportGate": ImportGate,
        "compute_caps": ComputeCaps
    }

    # Add 3rd party core libs if available
    try:
        import cv2
        import numpy as np
        import httpx
        from telegram import Update
        from telegram.ext import ApplicationBuilder, filters, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler
        from telegram.error import NetworkError, TimedOut
        portal_data.update({
            "cv2": cv2, "np": np, "numpy": np, "httpx": httpx,
            "Update": Update, "ApplicationBuilder": ApplicationBuilder, "filters": filters,
            "ContextTypes": ContextTypes, "CommandHandler": CommandHandler, 
            "MessageHandler": MessageHandler, "CallbackQueryHandler": CallbackQueryHandler,
            "NetworkError": NetworkError, "TimedOut": TimedOut
        })
    except ImportError: pass

    # 2. Conditional Project Module Loading
    
    # --- AUDIO ---
    try:
        from Audio_Modules import audio_processing, beat_engine, music_intelligence, music_manager, voiceover
        portal_data.update({
            "audio_processing": audio_processing, "beat_engine": beat_engine,
            "music_intelligence": music_intelligence, "music_manager": music_manager,
            "voiceover": voiceover
        })
    except ImportError: pass

    # --- TEXT & CAPTIONS ---
    try:
        from Text_Modules import gemini_captions, text_overlay, text_region_detector
        portal_data.update({
            "gemini_captions": gemini_captions, "text_overlay": text_overlay,
            "text_region_detector": text_region_detector
        })
    except ImportError: pass

    # --- INTELLIGENCE ---
    try:
        from Intelligence_Modules import (
            analytics_optimizer, decision_engine, deduplication, 
            policy_memory, quality_evaluator, risk_engine, monetization_brain, narrative_brain,
            adaptive_intelligence
        )
        from Monetization_Metrics import fashion_scout
        portal_data.update({
            "analytics_optimizer": analytics_optimizer, "decision_engine": decision_engine,
            "deduplication": deduplication, "policy_memory": policy_memory,
            "quality_evaluator": quality_evaluator, "risk_engine": risk_engine,
            "monetization_brain": monetization_brain, "narrative_brain": narrative_brain,
            "adaptive_intelligence": adaptive_intelligence,
            "fashion_scout": fashion_scout
        })
    except ImportError: pass

    # --- UPSCALE & AI ENGINE (GPU GATED) ---
    if allow_ai:
        try:
            from Upscale_Modules import ai_engine, gpu_utils, router, gemini_enhance_for_upscale, cpu_fast
            portal_data.update({
                "ai_engine": ai_engine, "gpu_utils": gpu_utils,
                "router": router, "gemini_enhance_for_upscale": gemini_enhance_for_upscale,
                "cpu_fast": cpu_fast
            })
        except ImportError: pass
    else:
        from Upscale_Modules import cpu_fast
        portal_data.update({
            "ai_engine": None, "gpu_utils": None,
            "router": None, "gemini_enhance_for_upscale": None,
            "cpu_fast": cpu_fast
        })

    # --- UPLOADER, DOWNLOADER, WATERMARK ---
    # --- DOWNLOADER (CRITICAL) ---
    try:
        from Download_Modules import downloader
        portal_data["downloader"] = downloader
    except ImportError as e:
        # Fallback if specific module fails, but try to keep it isolated
        print(f"CRITICAL: Downloader import failed: {e}")
        pass

    # --- WATERMARK (CRITITAL) ---
    try:
        from Visual_Refinement_Modules import hybrid_watermark, watermark_auto, opencv_watermark, quality_orchestrator
        portal_data.update({
             "hybrid_watermark": hybrid_watermark, 
             "watermark_auto": watermark_auto,
             "opencv_watermark": opencv_watermark,
             "quality_orchestrator": quality_orchestrator
        })
    except ImportError as e:
        print(f"❌ CRITICAL ERROR: Watermark Modules Failed to Load! Reason: {e}")
        # Traceback can be helpful here
        import traceback
        traceback.print_exc()

    # --- UPLOADERS ---
    try:
        from Uploader_Modules import community_promoter, meta_uploader, uploader
        portal_data.update({
            "community_promoter": community_promoter, 
            "meta_uploader": meta_uploader,
            "uploader": uploader
        })
    except ImportError as e:
         print(f"⚠️ Uploader Modules Partial Failure: {e}")

    return ModuleNamespace(**portal_data)
