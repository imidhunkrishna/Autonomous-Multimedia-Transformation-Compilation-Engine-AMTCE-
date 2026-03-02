import os
import json
import logging
import random
import re
import google.generativeai as genai
from typing import Dict, List, Optional
from PIL import Image

try:
    from Intelligence_Modules.gemini_status_manager import manager as quota_manager
except ImportError:
    quota_manager = None

from .money_flow_logic import engine as money_engine

logger = logging.getLogger("fashion_scout")

# --- TREND-JACKING PROMPT (MONEY MAXIMIZER) ---
TREND_CONTEXT_PROMPT = """
YOU ARE A HIGH-STAKES FASHION INSIDER & EXCLUSIVE DATA MINER.
Your goal is to "Jack the Trend" by identifying the exact viral aesthetic and providing the "Secret Blueprint."

REAL-TIME LAWS:
1. FOCUS: "Insider Intel", "Leaked Looks", "Restricted Aesthetics".
2. TONE: Suspenseful, Urgent, High-End.
3. TRANSFORMATION: You are not describing; you are revealing the secret construction or "Blueprint" of the look.

OUTPUT FORMAT (STRICT JSON ONLY):
{
  "outfit_description": "<Technical analysis: focus on fabrics/cuts/secrets.>",
  "search_queries": {
    "amazon": "<Viral technical item name e.g. 'Industrial Techwear Windbreaker'>"
  },
  "vibe": "LUXURY|STREETWEAR|MINIMALIST|BOHEMIAN|FORMAL"
}
"""

class FashionScout:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    def scout_outfit(self, image_paths: List[str]) -> Optional[Dict]:
        """
        Analyzes the outfit using 'Insider Intel' persona and integrates Money Flow CTAs.
        """
        if not self.gemini_key or not image_paths:
            return None

        # Try to import money engine
        try:
             from .money_flow_logic import engine as money_engine
        except (ImportError, ValueError):
             try:
                  from Intelligence_Modules.money_flow_logic import engine as money_engine
             except ImportError:
                  money_engine = None

        try:
            # Configure Gemini
            genai.configure(api_key=self.gemini_key)
            
            payload = [TREND_CONTEXT_PROMPT]
            valid_images = 0
            for path in image_paths:
                if os.path.exists(path):
                    try:
                        img = Image.open(path)
                        payload.append(img)
                        valid_images += 1
                    except Exception as ie:
                        logger.warning(f"⚠️ Fashion Scout: Failed to load {path}: {ie}")
            
            if valid_images == 0: return None

            models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
            if quota_manager:
                models = quota_manager.filter_models(models)
                if not models: return None

            for model_name in models:
                try:
                    logger.info(f"👕 Fashion Scout: Jacking Trends with {model_name}...")
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(
                        payload,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.4, # More creative for trend-jacking
                            response_mime_type="application/json"
                        )
                    )

                    if not response or not response.text: continue

                    res_text = response.text.strip()
                    match = re.search(r'(\{.*\})', res_text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        
                        # Apply Money Flow Loophole
                        if money_engine:
                            vibe = data.get("vibe", "GLOBAL")
                            offer = money_engine.get_optimized_offer(vibe)
                            data["imaginative_ctas"] = {
                                "english": money_engine.get_law_bending_cta(offer),
                                "hinglish": f"{offer['hook']} (Complete Verification Step check karo)",
                                "roman_urdu": f"{offer['hook']} (Verification Step complete karein)",
                                "hindi": f"{offer['hook']} (Industrial Verification पूरा करें)"
                            }
                            data["lead_magnet"] = offer['lead_magnet']

                        # Inject Search Links (Trend-Jacking Focus)
                        queries = data.get("search_queries", {})
                        q_encoded = queries.get('amazon', '').replace(' ', '+')
                        data["search_links"] = {
                            "amazon_us": f"https://www.amazon.com/s?k={q_encoded}",
                            "amazon_in": f"https://www.amazon.com/s?k={q_encoded}"
                        }
                        logger.info(f"✅ Fashion Scout: Trend Jacked successfully.")
                        return data
                except Exception as me:
                    err_str = str(me).lower()
                    if any(x in err_str for x in ["429", "quota", "500", "503"]):
                        logger.warning(f"⚠️ Fashion Scout Quota/Issue on {model_name}. Rotating...")
                        if "429" in err_str or "quota" in err_str:
                            if quota_manager: quota_manager.mark_banned(model_name)
                        continue
                    logger.warning(f"⚠️ Fashion Scout fallback on {model_name}: {err_str[:100]}")
                    continue

        except Exception as e:
            logger.error(f"❌ Fashion Scout Fatal Error: {e}")
        
        return None

# Singleton
scout = FashionScout()
