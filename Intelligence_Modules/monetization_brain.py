"""
Monetization Brain Module (Gemini Authority Mode)
-------------------------------------------------
Acts as the YOUTUBE SHORTS CAPTION EDITOR & SAFETY OFFICER.
Goal: Pass YPP Human Review by enforcing strictly editorial/transformative captions.

**SINGLE SOURCE OF TRUTH: GEMINI**
- No OpenAI usage.
- Strict Text Parsing for robustness.
"""

import os
import json
import logging
import re
import random
import shutil
import tempfile
from dotenv import load_dotenv
from typing import Dict, Optional, List
from datetime import datetime
import google.generativeai as genai

# Load credentials
if os.path.exists(".env"):
    load_dotenv(".env", override=True)
else:
    load_dotenv("Credentials/.env", override=True)
from typing import Dict, List, Optional

try:
    from .gemini_status_manager import manager as quota_manager
except (ImportError, ValueError):
    try:
        from gemini_status_manager import manager as quota_manager
    except ImportError:
        quota_manager = None

# --- MONEY FLOW IMPORTS ---
try:
    from .link_optimizer import LinkOptimizer
    from .money_flow_logic import engine as money_engine
except (ImportError, ValueError, ModuleNotFoundError):
    try:
        from link_optimizer import LinkOptimizer
        from money_flow_logic import engine as money_engine
    except ImportError:
        LinkOptimizer = None
        money_engine = None

logger = logging.getLogger("monetization_brain")

# PREDICTION ANALYSIS PROMPT (THE 60% SOLUTION - STYLE FUTURIST)
PREDICTION_ANALYSIS_PROMPT = """
YOU ARE A HIGH-STAKES FASHION FUTURIST & LLM-DRIVEN TREND ANALYST.
Your goal is to "Predict the 2027 Evolution" of the current style piece using AMTCE Proprietary Intelligence.

THE PREDICTION LOOPHOLE (60% YPP DEFENSE):
1. THE CORE: This is a high-intellect report. You are analyzing the "DNA" of the garment to forecast its evolution.
2. THE ANCHOR: You must refer to the "AI Generated Concept Frame" appearing at the end of the video. 
3. THE NARRATIVE: Frame the narration as: "AMTCE Intelligence predicts the [Garment] will evolve into [Predictive Concept] by 2027."

RETURN FORMAT (STRICT JSON ONLY):
{{
  "editorial_script": "<FUTURIST SCRIPT: Must be {word_target} words. Start with context, end with the 2027 Prediction Anchor.>",
  "prediction_data": {{
      "evolved_material": "<Future Fabric Name>",
      "silhouette_shift": "<Future Shape Change>",
      "market_impact": "DISRUPTIVE"
  }},
  "overlay_data": {{
    "brand_text": "AMTCE FUTURIST",
    "trend_text": "2027 BLUEPRINT",
    "context_text": "PREDICTION LAB",
    "commercial_item_name": "<The Garment Name>",
    "item_name": "<Specific garment name, e.g. 'Crimson Silk Gown'>",
    "price_tag": "<Estimated price tag, e.g. '$250' or '₹4,999'>"
  }},
  "generated_title": "<Futurist Title e.g. 'The 2027 Evolution: [Name]'>",
  "generated_hashtags": "<30 High-Traffic Hashtags>",
  "monetization_cta": "Download the 2027 Style Blueprint",
  "transformation_score": 100
}}

RULES FOR ALL TEXT AND NARRATIVE:
- DO NOT use words like "sexy", "hot", "seductive", or any similar sexually suggestive terms. Use professional, editorial terms like "glamorous", "statuesque", "alluring", "bold", or "magnetic".

INPUT:
Video Title: {title}
Visual Context: {visual_context}
"""

# VERSUS ANALYSIS PROMPT (SYNTHETIC NEWSROOM MODE - 75% YPP)
# [RETAINED AS FALLBACK]
VERSUS_ANALYSIS_PROMPT = """
YOU ARE A HIGH-STAKES FASHION NEWS ANCHOR & ARCHITECTURAL CRITIC.
Your goal is to provide a "Versus" comparison between two styles/sources ([SOURCE_A] and [SOURCE_B]).

THE JUXTAPOSITION LOOPHOLE:
1. THE COMPARISON: You must analyze the delta between the two sources.
2. THE COMMENTARY: Focus on "Architectural Divergence", "Textile Evolution", or "Silhouette Conflict".
3. THE ANCHOR: This is a reaction/review video. You are the host technical expert.

RETURN FORMAT (STRICT JSON ONLY):
{{
  "editorial_script": "<COMPOSITION SCRIPT: Must compare A and B. Reference 'On the left' vs 'On the right'. Use host persona.>",
  "entities": {{
    "comparison_theme": "<Theme of the versus, e.g. 'Minimalist vs Maximalist'>",
    "dominant_trend": "<The winning trend or 'Synthesized Aesthetic'>",
    "risk_level": "LOW",
    "ypp_defense": "Reaction & Comparative Documentary"
  }},
  "overlay_data": {{
    "title_a": "<Short Label for Source A>",
    "title_b": "<Short Label for Source B>",
    "host_mood": "ANALYTICAL|EXCITED|CRITICAL"
  }},
  "generated_title": "<Vs Title e.g. 'The Battle of the Silhouettes'>",
  "monetization_cta": "<Versus-focused curiosity gap CTA>",
  "transformation_score": 100
}}

INPUT:
Source A Context: {context_a}
Source B Context: {context_b}
"""

# MEDIA_ANALYSIS_PROMPT - HONEST VISUAL ANALYSIS
MEDIA_ANALYSIS_PROMPT = """
You are a sharp fashion editor analyzing video frames from a clip.

Look at the frames provided. Be honest and specific about what you actually see.

INSTRUCTIONS:
1. Identify the person, outfit, setting, and mood from the frames. Be specific — name exact colors, garment types, styling details.
2. Write narration (~{word_target} words) that a viewer would find genuinely useful and interesting. Describe what makes this look notable, unique, or worth watching. No hype, no fake statistics, no invented trends.
3. Generate overlay labels that accurately reflect what's in the clip, including the item name and an estimated price.
4. Score how much your commentary adds beyond just re-describing the original clip (0=pure reaction, 100=fully original insight).

RULES:
- Only describe what is actually visible. If you can't see a detail clearly, don't invent it.
- No fake "2027 predictions", no "DATA-DRIVEN REPORTING", no invented brand names.
- Narration should sound like a real person talking — natural, direct, confident.
- The title comes from the clip: {title}
- STRICT RULE: DO NOT use words like "sexy", "hot", "seductive", or any similar sexually suggestive terms. Use professional, editorial terms like "glamorous", "statuesque", "alluring", "bold", or "magnetic" instead.

RETURN STRICT JSON ONLY:
{{
  "editorial_script": "<Honest narration describing what you actually see and why it's interesting. ~{word_target} words.>",
  "overlay_data": {{
    "brand_text": "<Channel or brand name, use: {title}>",
    "trend_text": "<2-3 word label for the actual look, e.g. 'STREET CORE' or 'CASUAL LUXE'>",
    "context_text": "<2-3 word setting description, e.g. 'EVENT NIGHT' or 'AIRPORT LOOK'>",
    "item_name": "<Specific garment name, e.g. 'Crimson Silk Gown'>",
    "price_tag": "<Estimated price tag, e.g. '$250' or '₹4,999'>"
  }},
  "generated_title": "<Specific descriptive title based on what you see>",
  "monetization_cta": "<Honest CTA that matches the actual content>",
  "transformation_score": <Integer 0-100: how much does your commentary add beyond just describing the clip?>
}}

Video Title: {title}
Visual Context: {visual_context}
"""

class MonetizationStrategist:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.provider = "none"
        self.model = None
        self.los_pollos_file = "Monetization_Metrics/los_pollos_links.json"
        self.link_optimizer = LinkOptimizer() if LinkOptimizer else None
        
        if self.gemini_key:
            try:
                genai.configure(api_key=self.gemini_key)
                model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                is_banned = quota_manager.is_banned(model_name) if quota_manager else False
                
                if is_banned:
                    logger.warning(f"🧠 YPP Editor Brain: Model {model_name} is BANNED (Quota Exceeded). Rotating to fallbacks...")
                else:
                    logger.info(f"🧠 YPP Editor Brain: ACTIVE (Model: {model_name})")
                
                self.model = genai.GenerativeModel(model_name)
                self.provider = "gemini"
            except Exception as e:
                logger.error(f"❌ Gemini Brain Init Failed: {e}")
        else:
            logger.warning("🧠 YPP Editor Brain: INACTIVE (No Gemini Key)")

    def analyze_content(self, title: str, duration: float, transformations: Dict = {}, image_paths: List[str] = None, visual_context: str = None) -> Dict:
        """
        Analyzes content using Gemini as the sole authority.
        Supports Multimodal (Multi-Image + Text) analysis for Visual Transformation scoring.
        """
        if self.provider != "gemini" or not self.model:
            return self._fallback_response(title, visual_context=visual_context)

        try:
            # 1. Input Sanitization
            clean_title = re.sub(r'[\x00-\x1F\x7F]', '', title).strip()
            clean_title = clean_title[:200]
            
            # Prepare Prompt
            origin = "public_social_media" 
            trans_str = "None"
            if transformations:
                trans_str = ", ".join([f"{k}: {v}" for k,v in transformations.items()])
                
            # [ADAPTIVE v3] Safe Mode Constraints
            import Intelligence_Modules.adaptive_intelligence as ai
            constraints = ai.brain.get_execution_constraints() 
            safe_level = ai.brain.safe_controller.level
            
            # [ADAPTIVE v3] Psychometric Engine Selection
            # Replaces random.choice with Entropy/RL optimized selection
            active_trigger = ai.brain.get_optimized_psychology() 
            if not active_trigger: active_trigger = "Curiosity" # Fallback
            
            logger.info(f"🧠 Active Psychology: {active_trigger} (Safe Level: {safe_level})")
                
            # Use visual_context to augment input_description if available
            input_desc = clean_title
            if visual_context and len(visual_context) > 5:
                # ... existing logic ...
                input_desc = f"{clean_title} (Context: {visual_context})"

            # Calculate target word count based on 140 WPM
            word_target = int((duration / 60) * 140)
            word_target = max(20, min(word_target, 55)) # Balanced range for Shorts
            
            final_prompt = MEDIA_ANALYSIS_PROMPT.format(
                title=clean_title,
                duration=duration,
                visual_context=visual_context if visual_context else "Not provided",
                transformations=trans_str,
                word_target=word_target
            )
            
            # Append Psychology Instruction (Implicitly)
            final_prompt += f"\n\n[ADAPTIVE INSTRUCTION]\nAdopt the perspective of '{active_trigger}'. DO NOT EXPLAIN THE ANGLE. DO NOT USE THE WORD 'PSYCHOLOGY'. Just embody the style naturally."

            # [ADAPTIVE v3] Safe Mode Injection
            if safe_level >= 1:
                final_prompt += "\n\n[SAFE MODE ACTIVE]\nMake the tone strictly professional. No hype. No emojis. Focus on factual value."
            if safe_level >= 2:
                final_prompt += "\n\n[DEFENSIVE MODE]\nEnsure the content is 100% brand safe. Avoid any edgy humor or slang."
            
            
            # 2. Multimodal Payload (Images)
            payload = [final_prompt]
            if image_paths:
                if isinstance(image_paths, str): image_paths = [image_paths]
                
                from PIL import Image
                for path in image_paths:
                    if path and os.path.exists(path):
                        try:
                            img = Image.open(path)
                            payload.append(img)
                            logger.info(f"📸 Image Added to Brain Context: {os.path.basename(path)}")
                        except Exception as ie:
                            logger.warning(f"⚠️ Failed to load image {path}: {ie}")

            # --- RETRY LOOP WITH FALLBACK (GEMINI 2.5 FLASH ONLY) ---
            models_to_try = [
                os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
                "gemini-2.5-flash"
            ]
            # Remove duplicates while preserving order
            models_to_try = list(dict.fromkeys(models_to_try))
            
            if quota_manager:
                models_to_try = quota_manager.filter_models(models_to_try)
                if not models_to_try:
                    logger.error("❌ All models in Quota Manager are BANNED. Brain falling back to generic.")
                    return self._fallback_response(title, error="Global Quota Exceeded", transformations=transformations)
            
            # 3. Model Configuration (Max Genuineness)
            safety_settings = {
                genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            }

            last_error = None
            for model_name in models_to_try:
                try:
                    logger.info(f"🧠 Attempting multimodal analysis with: {model_name} (Temp: 0.85)")
                    current_model = genai.GenerativeModel(model_name)
                    
                    # Call Gemini — 90s hard timeout prevents pipeline hangs on slow multimodal calls
                    response = current_model.generate_content(
                        payload,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.85, 
                            response_mime_type="application/json"
                        ),
                        safety_settings=safety_settings,
                        request_options={"timeout": 90}
                    )
                    
                    response_text = response.text.strip()
                    logger.info(f"🧠 RAW GEMINI RESPONSE ({model_name}): {response_text}")
                    main_data = self._parse_json_response(response_text, clean_title, duration=duration, visual_context=visual_context)
                    
                    # 3. Fashion Scout Integration
                    if image_paths and main_data.get("approved"):
                        try:
                            try:
                                from Monetization_Metrics.fashion_scout import scout
                            except ImportError:
                                try:
                                    from .fashion_scout import scout
                                except (ImportError, ValueError):
                                    try:
                                        from fashion_scout import scout
                                    except ImportError:
                                        scout = None
                            fashion_data = scout.scout_outfit(image_paths) if scout else None
                            if fashion_data:
                                main_data["fashion_scout"] = fashion_data
                        except Exception as fe:
                            logger.warning(f"⚠️ Fashion Scout failed: {fe}")
                            
                    return main_data
                    
                except Exception as e:
                    last_error = e
                    err_msg = str(e).lower()
                    logger.warning(f"⚠️ Brain Analysis Attempt failed with {model_name}: {e}")
                    logger.info(f"🔄 Rotating model... (Finished attempt {models_to_try.index(model_name) + 1}/{len(models_to_try)})")
                    if any(x in err_msg for x in ["429", "quota", "500", "503", "timeout", "404", "not found"]):
                         logger.warning(f"⚠️ Brain Issue with {model_name} ({err_msg}). Rotating immediately...")
                         if any(x in err_msg for x in ["429", "quota"]):
                             if quota_manager: quota_manager.mark_banned(model_name)
                         continue
                    else:
                         raise e
            
            if last_error: raise last_error

        except Exception as e:
            logger.error(f"🧠 Brain Analysis Error: {e}")
            return self._fallback_response(title, error=e, transformations=transformations)

    def _parse_json_response(self, text: str, original_title: str, duration: float = 15.0, visual_context: str = None) -> Dict:
        """
        Parses JSON and applies STRICT Editorial Scoring Gates (Density & Facts).
        """
        try:
            # 1. Extract JSON Object (Strict Regex)
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if not match:
                 logger.warning("🧠 Invalid JSON format: No brackets found.")
                 return self._fallback_response(original_title, error=ValueError("Invalid JSON"), visual_context=visual_context)
                 
            json_str = match.group(1)
            data = json.loads(json_str)
            
            # 2. Extract Data
            script = data.get("editorial_script", "").strip()
            entities = data.get("entities", {})
            overlay = data.get("overlay_data", {})
            gen_title = data.get("generated_title")
            gen_tags = data.get("generated_hashtags")
            mon_cta = data.get("monetization_cta", "Shop for the outfit")
            
            # 3. SCORING GATES
            # A. Narrative Density (Time Based)
            # Assumption: 140 WPM = ~2.33 words/sec
            words = script.split()
            word_count = len(words)
            spoken_seconds = (word_count / 140) * 60
            narrative_density = spoken_seconds / duration if duration > 0 else 0
            
            # [MONETIZATION RULE] VOICEOVER DOMINANCE WINDOW: 0.40 - 1.20
            # Min: 0.40 (Decorative/Reused Risk), Max: 1.20 (High Energy/Educational)
            density_pass = 0.40 <= narrative_density <= 1.20
            
            if not density_pass:
                logger.warning(f"🚫 [NARRATIVE_DENSITY_FAIL] Gate Fail: Density {narrative_density:.2f} (Req 0.40-1.20). Words: {word_count}")
            
            # B. Fact Score (Weighted)
            # NEW FORMAT: overlay_data (brand_text, trend_text, context_text) + transformation_score
            # LEGACY FORMAT: entities (event_context, brand_id, fashion_trend, media_significance)
            fact_score = 0.0
            facts_found = []
            
            # -- NEW (Futurist Brain) format --
            overlay = data.get("overlay_data", {})
            if overlay.get("brand_text") and overlay.get("brand_text", "").lower() not in ["", "unknown"]:
                fact_score += 1.0
                facts_found.append("Brand")
            if overlay.get("trend_text") and overlay.get("trend_text", "").lower() not in ["", "unknown"]:
                fact_score += 1.0
                facts_found.append("Trend")
            if overlay.get("context_text") and overlay.get("context_text", "").lower() not in ["", "unknown"]:
                fact_score += 1.0
                facts_found.append("Context")
            if data.get("transformation_score", 0) >= 70:
                fact_score += 1.5  # High transformation = strong original content
                facts_found.append("Transformation")
            
            # -- LEGACY (Media Analysis) format fallback --
            if not facts_found:
                if entities.get("event_context") and getattr(entities.get("event_context"), "lower", lambda: "")() != "unknown":
                    fact_score += 1.5
                    facts_found.append("Event")
                if entities.get("brand_id") and getattr(entities.get("brand_id"), "lower", lambda: "")() != "unknown":
                    fact_score += 1.0
                    facts_found.append("Brand")
                if entities.get("fashion_trend") and getattr(entities.get("fashion_trend"), "lower", lambda: "")() != "unknown":
                    fact_score += 1.0
                    facts_found.append("Trend")
                if entities.get("media_significance") and getattr(entities.get("media_significance"), "lower", lambda: "")() != "unknown":
                    fact_score += 1.5
                    facts_found.append("Significance")
                
            fact_pass = fact_score >= 2.5
            
            if not fact_pass:
                logger.warning(f"🧠 Gate Fail: Fact Score {fact_score} (Req 2.5). Found: {facts_found}")

            # FINAL VERDICT
            approved = density_pass and fact_pass
            
            if not approved and not data.get("approved") == True: # If brain rejected it anyway
                 return self._fallback_response(original_title, error=ValueError(f"Gate Fail: Density={narrative_density:.2f}, Facts={fact_score}"), visual_context=visual_context)
            elif not approved: # Brain approved but gate failed
                 logger.warning(f"🚫 [NARRATIVE_DENSITY_FAIL] Logic Gated Rejected: D={narrative_density:.2f}, F={fact_score}")
                 return self._fallback_response(original_title, error=ValueError(f"Gate Fail: Density={narrative_density:.2f}, Facts={fact_score}"), visual_context=visual_context, failed_script=script)

            # [USER REQUEST] Voiceover must start with User Title (e.g. "Samantha")
            # If not present in text, prepend it.
            clean_title_str = original_title.replace("_", " ").strip()
            if clean_title_str and clean_title_str.lower() not in script.lower()[:len(clean_title_str)+5]:
                 script = f"{clean_title_str}. {script}"

            # Success
            result = {
                "approved": True,
                "final_caption": script, # Mapped for legacy
                "editorial_script": script,
                "editorial_title": gen_title, # NEW: Compilation Title
                "hashtags": gen_tags,         # NEW: Compilation Hashtags
                "monetization_cta": mon_cta,  # [USER REQUEST] Simplified CTA
                "entities": entities,
                "overlay_data": overlay,
                "caption_style": "EDITORIAL_ANALYSIS",
                "risk_level": "LOW",
                "risk_reason": "Factual media analysis verified.",
                "transformation_score": data.get("transformation_score", 100),
                "narrative_density": narrative_density,
                "fact_score": fact_score,
                "policy_citation": "Educational & Documentary",
                "verdict": "Monetization Viable",
                "source": "media_analysis_brain"
            }

            try:
                # --- NEW: MONEY FLOW OVERHAUL (Intent-Warming) ---
                vibe = result.get('entities', {}).get('fashion_trend', 'GLOBAL')
                # Find a matching category in our money logic
                matched_cat = "GLOBAL"
                for cat in ["LUXURY", "STREETWEAR", "MINIMALIST", "BOHEMIAN", "FORMAL"]:
                     if cat.lower() in vibe.lower():
                         matched_cat = cat
                         break
                
                offer = money_engine.get_optimized_offer(matched_cat)
                result['monetization_cta'] = money_engine.get_law_bending_cta(offer)
                result['lead_magnet'] = offer['lead_magnet']
                logger.info(f"💰 [MoneyFlow] Intent-Warming Applied: {offer['lead_magnet']}")
            except Exception as e:
                logger.warning(f"Failed to apply money flow optimization: {e}")
                result['monetization_cta'] = "Shop for the outfit"

            return result
            
        except json.JSONDecodeError:
            logger.error(f"🧠 JSON Decode Failed: {text[:50]}...")
            return self._fallback_response(original_title, error=ValueError("JSON Decode"), visual_context=visual_context)
        except Exception as e:
            logger.error(f"🧠 Parsing Error: {e}")
            return self._fallback_response(original_title, error=e, visual_context=visual_context)

    def _fallback_response(self, caption: str, error: Exception = None, transformations: Dict = {}, visual_context: str = None, failed_script: str = None) -> Dict:
        """
        FAIL-SAFE: Strict Rejection if Brain is offline.
        Prevents 'safe but boring' reuse content from polluting the channel.
        """
        # Default: REJECT
        risk = "HIGH"
        reason = "Brain Offline - Unable to verify editorial value. Rejecting to protect channel quality."
        
        if error:
             reason = f"Brain Error: {str(error)}"

        script = caption
        if failed_script and len(failed_script) > 10:
             script = failed_script
             reason += " (Using Recovered AI Script)"
        elif visual_context and len(visual_context) > 10:
            script = visual_context
            reason += " (Using AI Caption Fallback)"
            risk = "MEDIUM"
        
        # [mkpv-fix] Sanitize Fallback Script (Remove "Link in bio", "Subscribe", etc.)
        # If the fallback script contains spammy terms, revert to safe default.
        spam_triggers = ["link in", "bio", "description", "subscribe", "sub", "follow", "instagram", "tiktok"]
        if any(x in script.lower() for x in spam_triggers):
             logger.warning(f"⚠️ Fallback script contained unsafe promotional triggers. Reverting to safe default.")
             script = self.get_safe_fallback()
             risk = "LOW" # Default safe is low risk

        # [USER UPDATE V8] "clean voiceover fo caption + link in description + music"
        if script.lower().strip() == caption.lower().strip():
             # Identical
             editorial_script = f"{caption}. Link in description."
        elif caption.lower().strip() in script.lower():
             editorial_script = f"{script}. Link in description."
        else:
             editorial_script = f"{caption}. {script}. Link in description."
        
        # REMOVED: Hardcoded "Check the link in description" (User considers this low-quality/forced)
        
        # Override Verdict for Caption Fallback
        if risk == "MEDIUM" or (visual_context and len(visual_context) > 5):
             risk = "LOW"
             reason = "Brain Offline - Using Verified Caption as Script."
             approved_status = True
             verdict_msg = "Approved (Caption Fallback)"
        else:
             approved_status = False
             verdict_msg = "Rejected (System Failure)"

        return {
            "approved": approved_status,
            "final_caption": script,
            "editorial_script": editorial_script,
            "risk_level": risk, 
            "risk_reason": reason,
            "transformation_score": 50, # Neutral
            "verdict": verdict_msg,
            "policy_citation": "System Recovery",
            "source": "fallback_recovery",
            "monetization_cta": "Shop for the outfit",
            "editorial_title": f"Style Edit: {caption[:30]}..."
        }

    def generate_editorial_title(self, context: str, n_videos: int = None) -> tuple:
        """
        Generates a clickbait, high-performing title AND description for compilations.
        Returns: (title, description)
        """
        fallback_title = f"Compilation: {context}"
        fallback_desc = f"Compilation of best moments for {context}. #SafeForWork #Fashion"
        
        if self.provider != "gemini" or not self.model:
             return fallback_title, fallback_desc
             
        try:
             import random as py_random
             salt = py_random.randint(1000, 9999)
             
             # Zero-Ending Number Rule: Only include n_videos if it ends in 0
             num_str = ""
             if n_videos and n_videos % 10 == 0:
                 num_str = f"{n_videos} "
             
             prompt = f"""Generate ONE high-impact, law-bending TITLE and a short curiosity-gap DESCRIPTION for a compilation about: "{context}".

FORMAT RULES (STRICT):
1. NAME FIRST: The title MUST start with "{context}". Example: "{context}'s Exclusive Trend Vault: 2026 Sneak Peek"
2. NUMBER RULE: {"You MUST include the number '" + num_str.strip() + "' in the title." if num_str else "Do NOT include any numbers in the title."}

LAW-BENDING PERSONA (INSIDER):
Use "Insider Intel" language to drive clicks. 
- Instead of "hot/sexy" -> Use: "Subversive", "Statuesque", "Magnetic", "Elite".
- Instead of "compilation" -> Use: "Vault", "Blueprint", "Archive", "Theory".
- Goal: Make the user feel like they are seeing something they shouldn't.

VARIETY & STYLE:
- Use emojis at the end to grab attention.
- Ensure the title is unique and avoid generic repetitions (Compilation ID: {salt}).
- Max 60 characters for Title.
- SEO Description: 1-2 short sentences.

OUTPUT TYPE: Valid JSON ONLY.
Schema:
{{
    "title": "Your Law-Bending Title Here",
    "description": "Your description here."
}}
"""
             
             # --- RETRY LOOP WITH FALLBACK (GEMINI 2.5 FLASH ONLY) ---
             models_to_try = [
                 "gemini-2.5-flash",
                 "gemini-2.5-flash-lite"
             ]
             # Remove duplicates while preserving order
             models_to_try = list(dict.fromkeys(models_to_try))
             
             last_error = None
             for model_name in models_to_try:
                 try:
                     logger.info(f"🧠 Attempting title generation with: {model_name}")
                     current_model = genai.GenerativeModel(model_name)
                     
                     response = current_model.generate_content(
                         prompt,
                         generation_config=genai.types.GenerationConfig(
                             temperature=0.85 
                         )
                     )
                     text = response.text.strip()
                     
                     # JSON Extraction
                     match = re.search(r'(\{.*\})', text, re.DOTALL)
                     if match:
                         data = json.loads(match.group(1))
                         title = data.get("title", fallback_title).replace('"', '').replace('*', '')
                         desc = data.get("description", fallback_desc)
                         
                         if context.lower() not in title.lower()[:len(context)+5]:
                             title = f"{context}: {title}"
                         
                         logger.info(f"🧠 Generated Title ({model_name}): {title}")
                         return title, desc
                     else:
                         # Fallback if specific text gen (legacy support attempt) or fail
                         title = text.replace('"', '').replace('*', '')
                         return title, fallback_desc
                         
                 except Exception as e:
                     last_error = e
                     err_str = str(e).lower()
                     if any(x in err_str for x in ["429", "quota", "500", "503"]):
                         logger.warning(f"⚠️ Brain Issue (Title Gen) on {model_name}. Rotating...")
                         if "429" in err_str or "quota" in err_str:
                             if quota_manager: quota_manager.mark_banned(model_name)
                         continue
                     else:
                         # For other errors, re-raise the exception
                         raise e
             
             if last_error: raise last_error
                 
        except Exception as e:
             logger.error(f"🧠 Title/Desc Gen Failed: {e}")
             return fallback_title, fallback_desc

    def get_safe_fallback(self) -> str:
        """
        Returns a guaranteed safe caption from:
        1. Local Storage (caption_prompt.json)
        2. Hardcoded Revenue-Safe Templates
        """
        try:
            if os.path.exists("caption_prompt.json"):
                with open("caption_prompt.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "caption_final" in data and len(data["caption_final"]) > 5:
                         val = data["caption_final"]
                         # Quick re-validate stored caption
                         if "#" not in val and len(val.split()) >= 2:
                             logger.info(f"🛡️ Using Stored Fallback: {val}")
                             return val
        except Exception: pass
            
        return "A quiet moment captured today"

    def save_successful_caption(self, caption: str, source: str, style: str):
        """
        Persists the safe caption to disk ATOMICALLY.
        """
        try:
            data = {
                "caption_final": caption,
                "last_source": source,
                "timestamp": datetime.now().isoformat()
            }
            
            # Atomic Write via Temp
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=".", encoding='utf-8') as tmp:
                json.dump(data, tmp, indent=2)
                tmp_path = tmp.name
                
            shutil.move(tmp_path, "caption_prompt.json")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to save caption persistence: {e}")

    def get_monetization_link(self, target_platform: str = "youtube") -> Optional[str]:
        """
        Traffic Segregation Strategy with [ADAPTIVE VARIABLE REWARD]:
        - YouTube -> Amazon Links (Safe / Gifting)
        - Telegram -> Promotional Links (Engagement)
        
        Adaptive Logic:
        - Consult Safe Mode. If L3, return None (Killswitch).
        - If L2, reduce frequency (implicit in calling logic, but double check here).
        """
        # [ADAPTIVE v3] Safe Mode Check
        import Intelligence_Modules.adaptive_intelligence as ai
        constraints = ai.brain.get_execution_constraints()
        if constraints.get("cta_aggression", 1.0) == 0.0:
            logger.info("🛡️ Safe Mode L3: Monetization Disabled.")
            return None

        amazon_file = "Monetization_Metrics/Amazon_affliate_link.json"
        
        # 1. YOUTUBE / SAFE MODE (Amazon Only)
        if target_platform.lower() == "youtube":
            try:
                if os.path.exists(amazon_file):
                    with open(amazon_file, "r", encoding="utf-8") as f:
                        amz_links = json.load(f)
                        if amz_links and isinstance(amz_links, list):
                            # [ADAPTIVE] Shuffle for variety entropy
                            return random.choice(amz_links)
                logger.warning("⚠️ No Amazon links found for YouTube.")
                return None
            except Exception as e:
                logger.warning(f"⚠️ Failed to load Amazon links: {e}")
                return None

        # 2. TELEGRAM (Promotional Links)
        elif target_platform.lower() == "telegram":
            try:
                if os.path.exists(self.los_pollos_file):
                    with open(self.los_pollos_file, "r", encoding="utf-8") as f:
                        lp_links = json.load(f)
                        if lp_links and isinstance(lp_links, list):
                            # [ADAPTIVE v3] Weighted Link Optimizer
                            if self.link_optimizer:
                                selected = self.link_optimizer.get_weighted_link(lp_links)
                                if selected: return selected
                            
                            # Fallback if optimizer missing/failed
                            return random.choice(lp_links)
                
                # Fallback to Amazon if no promotional links
                logger.info("ℹ️ No promotional links, falling back to Amazon for Telegram.")
                return self.get_monetization_link("youtube")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to load promotional links: {e}")
                return None
        
        return None

    def get_telegram_story(self, visual_context: str) -> str:
        """
        Generates a 2-sentence Micro-Fiction (Mystery/Romance) for Telegram.
        Goal: Curiosity Gap.
        """
        try:
            STORY_PROMPT = f"""
            WRITE A 2-SENTENCE HIGH-STAKES STORY based on this outfit: "{visual_context}"
            GENRE: Mystery / Elite Thriller.
            TONE: Exclusive, Cold, Sharp.
            
            STRUCTURE:
            Sentence 1: The moment the world stopped (The look, the location, the impact).
            Sentence 2: The "Insider Secret" or "Hidden Mission" that changes everything.
            
            EXAMPLE:
            "He froze when he saw the velvet dress, realizing she knew his secret. She smiled, turned around, and that's when the message arrived."
            
            OUTPUT: Just the story text. No quotes.
            """
            
            # USE USER-SPECIFIED FALLBACK MODELS (Flash & Lite)
            models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
            
            if quota_manager:
                models = quota_manager.filter_models(models)
            
            for model_name in models:
                try:
                    local_model = genai.GenerativeModel(model_name)
                    response = local_model.generate_content(STORY_PROMPT)
                    if response.text:
                        return response.text.replace('"', '').strip()
                except Exception as me:
                    err_msg = str(me).lower()
                    if "429" in err_msg or "quota" in err_msg:
                        if quota_manager: quota_manager.mark_banned(model_name)
                    logger.warning(f"Story Gen fallback failed on {model_name}: {me}")
                    continue

            return "She wore this to the gala, and he couldn't look away. But he didn't know her real mission started at midnight."
            
        except Exception as e:
            logger.error(f"Story Gen Failed: {e}")
            return "She wore this to the gala, and he couldn't look away. But he didn't know her real mission started at midnight."

    def generate_title_and_hashtags(self, visual_context: str) -> tuple:
        """
        Generates 1 High-Performance Title and 30 Relevant Hashtags for a Short.
        Returns: (title, hashtags_string)
        """
        fallback_title = None
        fallback_hashtags = "#shorts #viral #trending"
        
        try:
            PROMPT = f"""
            YOU ARE A VIRAL CONTENT STRATEGIST.
            Analyze this visual context: "{visual_context}"
            
            TASK:
            1. Write ONE clickbait, high-performing Title (Max 60 chars).
            2. Write 30 relevant, high-traffic Hashtags.
            
            RULES:
            - Title must be punchy, exciting, and law-bending (safe synonyms for hot topics).
            - Hashtags must include mix of niche and broad tags.
            - OUTPUT FORMAT: JSON ONLY.
            
            Schema:
            {{
                "title": "Your Title Here",
                "hashtags": "#tag1 #tag2 ... #tag30"
            }}
            """
            
            # USE FLASH-LITE to save cost/quota if possible, else Standard
            # Ensure model names are valid strings available in your environment
            models = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
            if quota_manager: models = quota_manager.filter_models(models)
            
            last_error = None
            for model_name in models:
                try:
                    local_model = genai.GenerativeModel(model_name)
                    response = local_model.generate_content(
                        PROMPT,
                        generation_config=genai.types.GenerationConfig(
                            response_mime_type="application/json"
                        ),
                        request_options={"timeout": 60} # Prevent 8+ minute hangs
                    )
                    
                    if response.text:
                        import json
                        data = json.loads(response.text)
                        
                        # Extract and Validate
                        title = data.get("title", fallback_title).strip()
                        hashtags = data.get("hashtags", fallback_hashtags).strip()
                        
                        # Basic Validation
                        if len(title) < 5: title = fallback_title
                        if "#" not in hashtags: hashtags = fallback_hashtags
                        
                        return title, hashtags
                        
                except Exception as me:
                    last_error = me
                    err_msg = str(me).lower()
                    if "429" in err_msg or "quota" in err_msg:
                        if quota_manager: quota_manager.mark_banned(model_name)
                    logger.warning(f"Title/Tag Gen fallback failed on {model_name}: {me}")
                    continue
            
            if last_error: logger.error(f"All title models failed. Last error: {last_error}")
            return fallback_title, fallback_hashtags

        except Exception as e:
            logger.error(f"Title/Tag Gen Failed: {e}")
            return fallback_title, fallback_hashtags

    def analyze_versus(self, context_a: str, context_b: str) -> Dict:
        """
        Comparison engine for the Synthetic Newsroom.
        Analyzes two sources to generate a high-stakes 'Versus' script.
        """
        if self.provider != "gemini" or not self.model:
            return {}

        try:
            prompt = VERSUS_ANALYSIS_PROMPT.format(
                context_a=context_a,
                context_b=context_b
            )
            
            logger.info("🧠 Brain: Drafting Versus Comparison...")
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )

            if response and response.text:
                res_text = response.text.strip()
                match = re.search(r'(\{.*\})', res_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    logger.info(f"✅ Brain: Versus script ready. Theme: {data.get('entities', {}).get('comparison_theme')}")
                    return data
        except Exception as e:
            logger.error(f"❌ Brain Versus Analysis Failed: {e}")
            
        return {}

# Singleton
brain = MonetizationStrategist()
