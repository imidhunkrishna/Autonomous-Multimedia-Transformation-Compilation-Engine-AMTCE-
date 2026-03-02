
"""
Gemini Watermark Detection Module
---------------------------------
Isolated module for forensic watermark detection.
Used by HybridWatermarkDetector.
"""

import os
import cv2
import base64
import logging
import json
import re
import numpy as np
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger("gemini_watermark")

# Try to import Gemini
try:
    import google.generativeai as genai
    from PIL import Image
    HAS_GEMINI = True
    
    try:
        from Intelligence_Modules.gemini_status_manager import manager as quota_manager
    except ImportError:
        quota_manager = None
except ImportError:
    HAS_GEMINI = False
    logger.warning("⚠️ google-generativeai not installed. Gemini watermark detection disabled.")

# Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_FALLBACK_25 = "gemini-2.5-flash"
GEMINI_FALLBACK_LITE = "gemini-2.5-flash-lite"

# Legacy Quota Manager Removed (Superseded by Intelligence_Modules.gemini_status_manager)
gemini_client = None

def init_gemini(api_key: str, model_name: str = None) -> bool:
    global gemini_client, GEMINI_MODEL
    if not HAS_GEMINI or not api_key: return False
    target_model = model_name or GEMINI_MODEL
    try:
        genai.configure(api_key=api_key)
        is_banned = quota_manager.is_banned(target_model) if quota_manager else False
        
        if is_banned:
            logger.warning(f"⚠️ Gemini Watermark: {target_model} is BANNED. Will use fallbacks.")
        else:
            logger.info(f"✅ Gemini Watermark initialized: {target_model}")
            
        gemini_client = genai.GenerativeModel(target_model)
        GEMINI_MODEL = target_model
        return True
    except Exception as e:
        logger.error(f"❌ Gemini init failed: {e}")
        return False

def _safe_gemini_call(contents, generation_config=None, safety_settings=None) -> Optional[Any]:
    global gemini_client, GEMINI_MODEL
    if not gemini_client: return None
    
    # STRICT USER OVERRIDE: Flash & Lite Only
    models = [GEMINI_FALLBACK_25, GEMINI_FALLBACK_LITE]
    
    if quota_manager:
        models = quota_manager.filter_models(models)
        if not models:
            logger.error("❌ All models for Watermark are BANNED. Skipping AI check.")
            return None

    max_retries = len(models) - 1 # Only retry as many times as we have models
    
    for attempt in range(max_retries + 1):
        try:
            current_model_name = models[attempt]
            gemini_client = genai.GenerativeModel(current_model_name)
            
            # 60s hard timeout — watermark detection runs every job, can't stall the pipeline
            response = gemini_client.generate_content(
                contents=contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                request_options={"timeout": 60}
            )

            return response
        except Exception as e:
            err_msg = str(e).lower()
            # IMMEDIATE ROTATION FOR QUOTA/AVAILABILITY ERRORS
            if any(x in err_msg for x in ["429", "quota", "500", "503", "404", "not found"]):
                logger.warning(f"⚠️ Issue with {models[attempt]} ({err_msg}). Rotating model immediately...")
                
                # PERSISTENT BAN FOR QUOTA hits
                if "429" in err_msg or "quota" in err_msg:
                    if quota_manager: quota_manager.mark_banned(models[attempt])
                
                if attempt < max_retries:
                    continue # Try next model NOW
                else:
                    logger.error("❌ Quota/Service exhausted on all available models.")
                    break
            
            # Backoff only for networking/obscure errors
            if attempt < max_retries:
                wait = 2.0
                logger.warning(f"⏳ Gemini attempt {attempt+1} failed ({e}). Rotating in {wait}s...")
                time.sleep(wait)
                continue
                
            logger.error(f"❌ Gemini call failed after {max_retries} retries: {e}")
            return None
    return None

def frame_to_base64(frame: np.ndarray) -> Optional[str]:
    try:
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))
        success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not success: return None
        return base64.b64encode(buffer).decode('utf-8')
    except: return None

def clean_json_response(text: str) -> str:
    try:
        if "```" in text:
            text = re.sub(r"```(json)?", "", text)
            text = text.replace("```", "")
        return text.strip()
    except: return text

def detect_watermark(frames: List[np.ndarray], keywords: str = None, force_width: int = None, force_height: int = None) -> Optional[List[Dict[str, int]]]:
    global gemini_client
    if not gemini_client: init_gemini(os.getenv("GEMINI_API_KEY"))
    if not gemini_client: return None
    
    try:
        if not isinstance(frames, list): frames = [frames]
        b64_contents = []
        for f in frames:
            b64 = frame_to_base64(f)
            if b64: b64_contents.append({'mime_type': 'image/jpeg', 'data': b64})
        if not b64_contents: return None
        
        import math
        prompt = f"""
SYSTEM ROLE:
You are a Professional Output Verification Expert specializing in content safety and clean output validation.
MISSION: Verify if this video frame contains explicit, intrusive third-party watermarks or branding that MUST be removed.

# TARGETS (CONFIRMED VISIBILITY ONLY):
1. LOGOS & ICONS: Distinct Channel icons (TikTok, YouTube Shorts), TV station logos.
2. TEXT OVERLAYS: Explicit social handles (@username), "Link in bio", or watermarks added by video editors.
3. BRANDED TICKERS: Stationary branding.

# NEGATIVE CONSTRAINTS (DO NOT DETECT):
1. SCENE TEXT: Street signs, store names, t-shirt text, posters, or background text. IGNORE ALL natural text.
2. SUBTITLES: Standard movie/anime subtitles at the bottom are NOT watermarks unless they contain a handle.
3. UI ELEMENTS: Video player controls or system UI.
4. AMBIGUOUS NOISE: If you are not 100% sure it is a watermark, DO NOT FLAGG IT.

# PRECISION RULES:
1. BOX FORMAT: [ymin, xmin, ymax, xmax] on a 0-1000 scale.
2. STRICT BOUNDS: Box must tightly enclose the watermark.
3. CONFIDENCE: Only output items you are certain are artificial overlays.

STRICT JSON OUTPUT FORMAT:
{{
  "watermark_present": true,
  "items": [
      {{
          "box_2d": [ymin, xmin, ymax, xmax],
          "type": "logo" | "text" | "social_handle",
          "anchoring": "top_left" | "top_right" | "bottom_left" | "bottom_right" | "floating",
          "text_content": "transcribed text",
          "precision_reasoning": "Explain why this is an artificial overlay and not scene text."
      }}
  ]
}}
"""
        if keywords: prompt += f"\n\nPRIORITY FOCUS: {keywords}"
        
        request_contents = b64_contents + [prompt]
        gen_config = genai.types.GenerationConfig(response_mime_type="application/json")
        
        # Retry loop for empty/malformed responses (Finish Reason 1 but no parts)
        res_txt = None
        for attempt in range(2):
            response = _safe_gemini_call(contents=request_contents, generation_config=gen_config, safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ])
            
            if not response: return None # _safe_gemini_call already handles its own retries/logging
            
            try:
                res_txt = response.text
                break # Success
            except Exception as e:
                logger.warning(f"⚠️ Gemini Detect returned empty Part (Attempt {attempt+1}/2): {e}")
                if attempt < 1: 
                    time.sleep(1)
                    continue
                return None

        data = json.loads(clean_json_response(res_txt))
        
        # Robust handling for varied Gemini response formats (List vs Object)
        if isinstance(data, list):
            items = data
        else:
            if not data.get("watermark_present", False): return []
            items = data.get("items", [])
        
        if not items:
            logger.info(f"raw_response: {res_txt}")
            return []
        results = []
        h_img, w_img = frames[0].shape[:2]
        use_w = force_width if force_width else w_img
        use_h = force_height if force_height else h_img
        
        for item in items:
            box_norm = item.get("box_2d", [])
            if len(box_norm) != 4: continue
            ymin, xmin, ymax, xmax = box_norm
            
            # PRECISE COORDINATE MAPPING
            # We map 0-1000 space to pixel space with sub-pixel encompassing.
            x_start = int(math.floor((xmin / 1000.0) * use_w))
            y_start = int(math.floor((ymin / 1000.0) * use_h))
            
            x_end = int(math.ceil((xmax / 1000.0) * use_w))
            y_end = int(math.ceil((ymax / 1000.0) * use_h))
            
            w_pixel = x_end - x_start
            h_pixel = y_end - y_start
            
            if w_pixel < 2 or h_pixel < 2: continue
            results.append({
                'x': max(0, x_start), 'y': max(0, y_start),
                'w': min(use_w-x_start, w_pixel), 'h': min(use_h-y_start, h_pixel),
                'type': 'HYBRID_CLAMPED',
                'semantic_type': item.get("type", "unknown"),
                'semantic_anchor': item.get("anchoring", "floating"),
                'semantic_hint': item.get("text_content", "")
            })
            logger.info(f"💎 Hybrid Detection: {item.get('type')} at {item.get('anchoring')} -> x={x_start}, y={y_start}, w={w_pixel}, h={h_pixel}")

        return results
    except Exception as e:
        logger.warning(f"⚠️ Gemini Detect failed: {e}")
        return None

def verify_watermark(frame: np.ndarray, candidate_box: Dict[str, int]) -> Optional[bool]:
    global gemini_client
    if not gemini_client: init_gemini(os.getenv("GEMINI_API_KEY"))
    if not gemini_client: init_gemini(os.getenv("GEMINI_API_KEY"))
    
    # Check if Gemini is banned globally (prevent wasted calls)
    if quota_manager and quota_manager.is_banned(GEMINI_MODEL):
         return None
         
    try:
        x, y, w, h = candidate_box['x'], candidate_box['y'], candidate_box['w'], candidate_box['h']
        h_img, w_img = frame.shape[:2]
        pad_x, pad_y = int(w * 3.0), int(h * 3.0)
        x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
        x2, y2 = min(w_img, x + w + pad_x), min(h_img, y + h + pad_y)
        roi = frame[y1:y2, x1:x2]
        b64_frame = frame_to_base64(roi)
        if not b64_frame: return None
        prompt = "Is there ANY text, logo, or watermark visible? JSON ONLY: { 'is_watermark': true/false }"
        # quota_manager.increment("analyze") - Removed (using simple status manager)
        response = _safe_gemini_call(contents=[{'mime_type': 'image/jpeg', 'data': b64_frame}, prompt], generation_config=genai.types.GenerationConfig(response_mime_type="application/json"))
        if not response: return None
        data = json.loads(clean_json_response(response.text))
        return data.get("is_watermark", False)
    except: return None
