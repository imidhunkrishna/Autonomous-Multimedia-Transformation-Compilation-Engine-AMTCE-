
"""
Gemini Video Enhancement & Upscale Module
------------------------------------------
Analyzes video quality and builds FFmpeg instruction chains.
Used by the main compiler for high-quality production.
"""

import os
import cv2
import base64
import logging
import json
import re
import numpy as np
import subprocess
import time
from typing import Optional, Dict, Any, List
from Intelligence_Modules.decision_engine import DecisionEngine
from Intelligence_Modules.quality_evaluator import QualityEvaluator

logger = logging.getLogger("gemini_upscale")

# Try to import Gemini
try:
    import google.generativeai as genai
    from PIL import Image
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logger.warning("⚠️ google-generativeai not installed. Gemini upscale disabled.")

# Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

class GeminiQuotaManager:
    """
    Strictly manages Gemini API quota usage per video.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GeminiQuotaManager, cls).__new__(cls)
            cls._instance.calls = {"analyze": 0}
            cls._instance.limits = {
                "analyze": int(os.getenv("GEMINI_ANALYZE_LIMIT", "5"))
            }
        return cls._instance
        
    def can_call(self, purpose: str = "analyze") -> bool:
        current = self.calls.get(purpose, 0)
        limit = self.limits.get(purpose, 5)
        if current >= limit: return False
        return True
        
    def increment(self, purpose: str = "analyze"):
        if purpose in self.calls:
            self.calls[purpose] += 1
            logger.info(f"📊 Gemini Quota ({purpose}): {self.calls[purpose]}/{self.limits.get(purpose, '?')}")
        
    def reset(self):
        self.calls = {"analyze": 0}
        logger.info("🔄 Gemini Quota Reset for new video.")

# Global Quota Manager
quota_manager = GeminiQuotaManager()
gemini_client = None

def init_gemini(api_key: str, model_name: str = None) -> bool:
    global gemini_client, GEMINI_MODEL
    if not HAS_GEMINI or not api_key: return False
    target_model = model_name or GEMINI_MODEL
    try:
        genai.configure(api_key=api_key)
        gemini_client = genai.GenerativeModel(target_model)
        GEMINI_MODEL = target_model
        logger.info(f"✅ Gemini Upscale initialized: {GEMINI_MODEL}")
        return True
    except: return False

def _safe_gemini_call(contents, generation_config=None) -> Optional[Any]:
    global gemini_client, GEMINI_MODEL
    if not gemini_client: return None
    models = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    for attempt in range(2):
        try:
            return gemini_client.generate_content(contents=contents, generation_config=generation_config)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg:
                try: current_idx = models.index(GEMINI_MODEL)
                except ValueError: current_idx = 0
                if current_idx < len(models) - 1:
                    GEMINI_MODEL = models[current_idx + 1]
                    gemini_client = genai.GenerativeModel(GEMINI_MODEL)
                    continue
            return None
    return None

def frame_to_base64(frame: np.ndarray) -> Optional[str]:
    try:
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))
        success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return base64.b64encode(buffer).decode('utf-8') if success else None
    except: return None

def get_hybrid_prompt(n_frames: int = 1) -> str:
    return f"""
Analyze these {n_frames} video frames and generate a JSON recipe for FFmpeg enhancement.
{{
  "results": [
      {{
          "enhance": true,
          "sharpness": 0.0 to 1.0,
          "denoise": 0.0 to 1.0,
          "contrast": 0.5 to 2.0,
          "brightness": -0.2 to 0.2,
          "saturation": 0.5 to 2.0,
          "upscale": "1x" or "2x"
      }},
      ...
  ]
}}
"""

def analyze_frames_batch(frames: List[np.ndarray]) -> List[Dict[str, Any]]:
    global gemini_client
    if not gemini_client: return []
    if not quota_manager.can_call("analyze"): return []
    try:
        request_contents = []
        for f in frames:
            b64 = frame_to_base64(f)
            if b64: request_contents.append({'mime_type': 'image/jpeg', 'data': b64})
        if not request_contents: return []
        request_contents.append(get_hybrid_prompt(len(request_contents)))
        quota_manager.increment("analyze")
        gen_config = genai.types.GenerationConfig(temperature=0.2, response_mime_type="application/json")
        response = _safe_gemini_call(contents=request_contents, generation_config=gen_config)
        if not response: return []
        data = json.loads(re.sub(r"```(json)?", "", response.text).strip())
        return data.get("results", [])
    except: return []

def run(input_video: str, output_video: str) -> str:
    if not gemini_client: init_gemini(os.getenv("GEMINI_API_KEY"))
    try:
        cap = cv2.VideoCapture(input_video)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0: return "GEMINI_FAIL"
        frames = []
        for idx in [int(total*0.1), int(total*0.5), int(total*0.9)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, f = cap.read()
            if ret: frames.append(f)
        cap.release()
        results = analyze_frames_batch(frames)
        if not results: return "GEMINI_FAIL"
        
        sharp = np.median([float(r.get("sharpness", 0)) for r in results])
        denoise = max([float(r.get("denoise", 0)) for r in results])
        filters = []
        if sharp > 0: filters.append(f"unsharp=5:5:{sharp*1.5:.2f}:5:5:0.0")
        if denoise > 0: filters.append(f"hqdn3d={denoise*10:.1f}:{denoise*10:.1f}:6:6")
        filters.append("scale=1080:1920:flags=lanczos:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2")
        
        cmd = ["ffmpeg", "-y", "-i", input_video, "-vf", ",".join(filters), "-c:v", "libx264", "-crf", "23", output_video]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "SUCCESS"
    except: return "GEMINI_FAIL"
