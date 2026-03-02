# gemini_captions.py - AI-Powered Caption Generator using Gemini Vision API
import os
import logging
import random
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv("Credentials/.env", override=True)

logger = logging.getLogger("gemini_captions")

# Try to import Gemini
try:
    import google.generativeai as genai
    from PIL import Image
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("⚠️ google-generativeai not installed. Run: pip install google-generativeai")

try:
    from assets.system_prompts import GEMINI_SYSTEM_ROLE, STYLE_TEMPLATES
except ImportError:
    # Fallback if file not found locally (dev mode)
    GEMINI_SYSTEM_ROLE = "You are a caption generator. Output short editorial fashion commentary."
    STYLE_TEMPLATES = {"viral": "Focus on elegance."}
    logger.warning("⚠️ assets/system_prompts.py not found. Using minimal fallback.")

try:
    from Intelligence_Modules.gemini_status_manager import manager as quota_manager
except ImportError:
    quota_manager = None
    logger.warning("⚠️ Intelligence_Modules/gemini_status_manager.py not found. Quota management disabled.")

# --- FALLBACK SYSTEM ---
# Global index to ensure rotation even across different generator instances
_fallback_index = 0

FALLBACK_CAPTIONS = [
  "A confident moment captured effortlessly",
  "A graceful take on modern glamour",
  "Elegant movement with a timeless appeal",
  "Soft tones paired with refined style",
  "Red carpet elegance done right",
  "Active style with a polished touch",
  "A poised presence on the red carpet",
  "Confidence reflected in every step",
  "Subtle shine with a refined finish",
  "A statement look with classic charm",
  "Naturally elegant and composed",
  "Understated glamour at its best",
  "A warm smile with effortless style",
  "Simple styling, elevated presence",
  "Graceful glamour without trying too hard",
  "Timeless elegance in motion",
  "A balanced blend of confidence and style",
  "Poised and naturally radiant",
  "A refined take on classic red",
  "Clean styling with modern aesthetics",
  "A polished look with visual appeal",
  "Contemporary style with calm confidence",
  "A thoughtfully styled appearance",
  "A confident fashion moment",
  "Cool tones with modern elegance",
  "Soft hues paired with subtle sparkle",
  "Minimal glamour with strong presence",
  "A composed and stylish appearance",
  "Fashion-forward with a calm attitude",
  "Clean lines and confident energy",
  "A well-balanced modern aesthetic",
  "Simple styling done right",
  "A confident and composed look",
  "Denim styled with elegance",
  "Casual fashion with refined detail",
  "Soft reflections with modern charm",
  "A thoughtfully styled appearance",
  "Balanced fashion with visual clarity",
  "A calm and confident presence",
  "A refined take on modern fashion",
  "Style that feels natural and composed",
  "Clean, modern styling",
  "Poised red carpet appearance",
  "Festive style with subtle elegance",
  "A composed look for a special event",
  "Confidence reflected through styling",
  "Evening elegance made effortless",
  "Light seasonal styling with grace",
  "Modern fashion with a confident stance",
  "Relaxed glamour with refined detail"
]

class GeminiCaptionGenerator:
    """
    AI-powered caption generator using Google Gemini Vision API.
    Analyzes video frames and generates engaging, context-aware captions.
    """
    
    def __init__(self):
        if not GEMINI_AVAILABLE:
            raise ImportError("google-generativeai package not installed")
        
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env file")
        
        if "YOUR_" in api_key or len(api_key) < 20:
            raise ValueError("GEMINI_API_KEY not configured properly. Get one from https://aistudio.google.com/app/apikey")
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Use Gemini 2.5 Flash FIRST, then Lite
        self.models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        
        # Remove duplicates while preserving order
        self.models = list(dict.fromkeys(self.models))

        if quota_manager:
            is_def_banned = quota_manager.is_banned(self.models[0])
            self.models = quota_manager.filter_models(self.models)
            if not self.models:
                logger.error("❌ gemini_captions: All models are BANNED globally.")
                self.models = ["gemini-2.5-flash-lite"] 
            
            if is_def_banned:
                logger.warning(f"🏷️ gemini_captions: Primary model is BANNED. Using available: {self.models[0]}")
            else:
                logger.info(f"🏷️ gemini_captions: ACTIVE (Model: {self.models[0]})")
        
        self.current_model_idx = 0
        self.model = genai.GenerativeModel(self.models[self.current_model_idx])
        
        # Define safety settings to prevent blocking (List format for compatibility)
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Initialize Caption Cache
        self.cache_file = "The_json/captions_cache.json"
        self.caption_cache = self._load_cache()

        # Initialize Persistent State (Fallback Index)
        self.state_file = "The_json/caption_state.json"
        self.fallback_index = self._load_state()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                import json
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"💾 Loaded {len(data)} captions from cache.")
                return data
        except Exception:
            pass
        return []

    def _save_cache(self):
        try:
            import json
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.caption_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_state(self) -> int:
        """Loads the persistent fallback index."""
        try:
            if os.path.exists(self.state_file):
                import json
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return data.get("fallback_index", 0)
        except Exception: pass
        return 0

    def _save_state(self):
        """Saves the persistent fallback index."""
        try:
            import json
            with open(self.state_file, 'w') as f:
                json.dump({"fallback_index": self.fallback_index}, f)
        except Exception: pass

    def _get_style_prompt(self, style: str, strict_mode: bool = False) -> str:
        """
        Returns the optimized system prompt for the given style using centralized templates.
        """
        # Inject "Micro-Commentary" variety
        template_key = random.choice(list(STYLE_TEMPLATES.keys()))
        style_instruction = STYLE_TEMPLATES.get(template_key, "")
        
        # If strict style requested override random
        if style in ["question", "motivational", "clickbait"]:
             # Custom overrides for specific functional styles
             if style == "question": style_instruction = "Ask a short rhetorical question about the style."
             if style == "motivational": style_instruction = "Focus on confidence and power."
        
        full_prompt = (
            f"{GEMINI_SYSTEM_ROLE}\n\n"
            f"CURRENT TASK:\n"
            f"Style Strategy: {template_key.upper()} - {style_instruction}\n\n"
            f"GENUINENESS RULE: DO NOT return the name of the model alone. DO NOT say 'Saiee' or 'Model'.\n"
            f"Instead, describe the specific fabric (silk, velvet), the lighting (warm, studio), or the vibe (high-status, red-carpet).\n"
            f"CRITICAL: Always apply the LAW-BENDING DICTIONARY rules for monetization safety.\n"
        )
        
        if strict_mode:
            full_prompt += "\nSTRICT MODE UPDATE: Your previous attempt was too short or generic. YOU MUST BE DESCRIPTIVE."
            
        full_prompt += "\n\nOUTPUT ONLY THE EXPERT CAPTION."
            
        return full_prompt
    
    def _validate_caption(self, text: str) -> bool:
        """
        STRICT VALIDATION GATE (Updated for Micro-Commentary).
        Returns True if caption is safe to use, False otherwise.
        """
        if not text: return False
        
        words = text.split()
        word_count = len(words)
        
        # 1. Strict Word Count (8-15 preferrred, 25 max absolute)
        if word_count < 5: # Too short (label)
             logger.warning(f"⚠️ Validation Fail: Too Short ({word_count} words) - '{text}'")
             return False
        if word_count > 25: # Too long (essay)
             logger.warning(f"⚠️ Validation Fail: Too Long ({word_count} words) - '{text}'")
             return False
             
        # 2. Line Length Check (Approx 2 lines max)
        # Average char per word ~5 + space = 6. 25 words = 150 chars.
        # But we want visual fit. 22 chars per line x 2 lines = 44 chars ideal?
        # User said "No line should exceed ~22 characters". That is very short.
        # We will check absolute char length.
        if len(text) > 160: 
             logger.warning(f"⚠️ Validation Fail: Too Long Chars ({len(text)})")
             return False

        text_lower = text.lower()
        
        # 3. Banned Phrases (Analytical/Meta)
        # Relaxed "features" if it makes sense contextually, but "caption:" is hard ban.
        hard_banned = [
            "caption:", "here is", "this is a video", "output:", 
            "analyze:", "assessment:", "image shows"
        ]
        
        for b in hard_banned:
            if b in text_lower:
                 return False
                 
        return True

    def generate_caption(self, image_path: str, style: str = "viral") -> str:
        """
        Generate AI caption from video frame (DIRECT MODE ONLY).
        """
        # global _fallback_index # Removed in favor of self.fallback_index
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image not found: {image_path}")
                
            logger.info(f"🤖 Generating caption (Direct Mode)...")
            
            # Retry Loop (Exponential Backoff)
            import time
            import random
            
            max_retries = 5 # Increased from 3
            last_error = None
            generated_text = None
            
            for attempt in range(max_retries):
                is_strict = attempt > 0
                prompt = self._get_style_prompt(style, strict_mode=is_strict)
                
                try:
                    with Image.open(image_path) as img:
                        # Add transport timeout check if possible, mostly implied by library
                        response = self.model.generate_content([prompt, img], safety_settings=self.safety_settings)
                        text = response.text.strip()
                        
                        # Clean
                        text = text.replace('"', '').replace("'", "").replace('\n', ' ').strip()
                        if ":" in text and len(text.split(":")[0]) < 15: 
                            text = text.split(":")[-1].strip() # Remove "Analysis: ..."
                        
                        if self._validate_caption(text):
                            # UNIQUENESS CHECK
                            if text in self.caption_cache:
                                logger.warning(f"⚠️ Duplicate Caption: '{text}'. Retrying...")
                                time.sleep(1)
                                continue
                                
                            generated_text = text
                            logger.info(f"📝 Caption generated in attempt {attempt+1}/{max_retries} ({getattr(self.model, 'model_name', 'default')}).")
                            break
                        else:
                            logger.warning(f"⚠️ Validation Failed: '{text}'. Retrying...")
                            
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    
                    # QUOTA / AVAILABILITY FALLBACK LOGIC
                    if any(x in err_str for x in ["429", "quota", "500", "404", "not found"]):
                        if self.current_model_idx < len(self.models) - 1:
                             old_model = self.models[self.current_model_idx]
                             
                             # GLOBAL BAN
                             if ("429" in err_str or "quota" in err_str) and quota_manager:
                                 quota_manager.mark_banned(old_model)
                                 
                             self.current_model_idx += 1
                             new_model = self.models[self.current_model_idx]
                             logger.warning(f"⚠️ Quota Hit on {old_model}. Switching to {new_model}...")
                             self.model = genai.GenerativeModel(new_model)
                             continue # IMMEDIATE RETRY
                        else:
                             logger.error(f"❌ Quota exceeded on all available models ({self.models}).")
                             break

                    # Backoff Strategy
                    wait_time = (2 ** attempt) + random.uniform(0.1, 1.0)
                    if "503" in err_str or "timeout" in err_str:
                         logger.warning(f"⚠️ Network/Server Error ({e}). Retrying in {wait_time:.1f}s...")
                    else:
                         logger.warning(f"⚠️ Attempt {attempt+1} failed: {e}. Retrying in {wait_time:.1f}s...")
                         
                    time.sleep(wait_time)
            
            # --- HARD FALLBACK WITH PERSISTENT ROTATION & PRUNING ---
            if not generated_text:
                logger.error("❌ Caption Generation Failed. Using Hard Fallback.")
                
                # Load Usage Data
                usage_file = "The_json/captions_usage.json"
                usage_data = {}
                try:
                    if os.path.exists(usage_file):
                        import json
                        with open(usage_file, 'r', encoding='utf-8') as f: usage_data = json.load(f)
                except: pass

                # PRIMARY: Use User's Cache (Full History)
                if self.caption_cache and len(self.caption_cache) > 0:
                     # Sort candidates by usage count (ascending) to pick freshest
                     candidates = sorted(self.caption_cache, key=lambda x: usage_data.get(x, 0))
                     
                     # Pick the winner (least used)
                     generated_text = candidates[0]
                     
                     # Increment Usage
                     new_count = usage_data.get(generated_text, 0) + 1
                     usage_data[generated_text] = new_count
                     
                     # PRUNING LOGIC (User Request: Delete if used > 2 times)
                     if new_count > 2:
                         logger.info(f"✂️ Caption '{generated_text}' used {new_count} times. DELETING from cache.")
                         if generated_text in self.caption_cache:
                             self.caption_cache.remove(generated_text)
                             self._save_cache() # Save updated cache
                         if generated_text in usage_data:
                             del usage_data[generated_text]
                     
                     # Save Usage
                     try:
                         with open(usage_file, 'w', encoding='utf-8') as f: 
                             json.dump(usage_data, f, indent=2)
                     except: pass
                     
                     if new_count <= 2:
                        logger.info(f"🔄 Used Cache Fallback: '{generated_text}' (Usage: {new_count}/2)")
                else:
                     # SECONDARY: Use Hardcoded List (Persistent Index)
                     generated_text = FALLBACK_CAPTIONS[self.fallback_index % len(FALLBACK_CAPTIONS)]
                     logger.info(f"🔄 Used Static Fallback #{self.fallback_index}: '{generated_text}'")
                
                # Increment & Save Persistent Index
                self.fallback_index += 1
                self._save_state()
                    
            # Cache Success (If new generated text)
            if generated_text and generated_text not in self.caption_cache and generated_text not in FALLBACK_CAPTIONS:
                self.caption_cache.append(generated_text)
                self._save_cache()
                
            return generated_text

        except Exception as e:
            logger.error(f"❌ Critical Caption Error: {e}")
            
            # Use a descriptive fallback, NOT the title
            fallback = FALLBACK_CAPTIONS[random.randint(0, len(FALLBACK_CAPTIONS)-1)]
            return fallback

    
    def generate_hashtags(self, image_path: str, count: int = 5) -> str:
        """
        Generate relevant hashtags based on video content.
        """
        prompt = (
            f"Analyze this image and generate {count} relevant, popular hashtags "
            f"that would work well on YouTube Shorts or Instagram Reels. "
            f"Return ONLY the hashtags separated by spaces, starting with #. "
            f"Focus on trending, viral topics."
        )
        
        try:
            img = Image.open(image_path)
            response = self.model.generate_content([prompt, img], safety_settings=self.safety_settings)
            hashtags = response.text.strip()
            
            # Clean up
            hashtags = ' '.join([tag for tag in hashtags.split() if tag.startswith('#')])
            
            logger.info(f"✨ Generated hashtags: {hashtags}")
            return hashtags
            
        except Exception as e:
            logger.error(f"❌ Hashtag generation failed: {e}")
            return "#viral #trending #shorts"
    
    def generate_title(self, image_path: str) -> str:
        """
        Generate a YouTube-ready title based on video content.
        """
        prompt = (
            "Generate a CATCHY and LAW-BENDING YouTube title (max 60 characters) for this video. "
            "Target high search intent by using professional synonyms for suggestive terms: "
            "Replace 'hot' with Bold/Stunning, 'sexy' with Sizzling/Alluring, 'naked' with Unseen/Raw. "
            "Make it clickable, engaging, and optimized for YouTube algorithm. "
            "Use capitalization strategically. Be creative!"
        )
        try:
            img = Image.open(image_path)
            response = self.model.generate_content([prompt, img], safety_settings=self.safety_settings)
            title = response.text.strip().replace('"', '').replace("'", '')
            
            if len(title) > 60:
                title = title[:60].rsplit(' ', 1)[0]
            
            logger.info(f"✨ Generated title: '{title}'")
            return title
            
        except Exception as e:
            logger.error(f"❌ Title generation failed: {e}")
            return "Amazing Video You Need To See!"



    def generate_compilation_title(self, n_videos: int, style: str = "compilation_intro", context: str = None) -> str:
        """
        Generate a catchy title for a compilation.
        """
        # Zero-Ending Number Rule
        num_str = ""
        if n_videos and n_videos % 10 == 0:
            num_str = f"{n_videos} "
            
        context_str = f" about: \"{context}\"" if context else ""
        name_rule = f"1. NAME FIRST: The title MUST start with '{context}'.\n" if context else ""
        
        prompt = (
            f"Generate a HIGHLY CLICKABLE, VIRAL, and LAW-BENDING title for a video compilation containing {n_videos} clips{context_str}. "
            "LAW-BENDING DICTIONARY: Always swap 'hot' -> Bold/Stunning, 'sexy' -> Sizzling/Alluring, 'boobs' -> Silhouette/Physique. "
            "\nFORMAT RULES (STRICT):\n"
            f"{name_rule}"
            f"2. NUMBER RULE: {'You MUST include the number ' + num_str.strip() + ' in the title.' if num_str else 'Do NOT include any numbers like 11 or 12 in the title.'}\n"
            "Use emotional triggers, curiosity gaps, and strong adjectives. "
            "CRITICAL: Must be ADVERTISER FRIENDLY. NO profanity, NO 'WTF', NO NSFW terms. "
            "Make it sound like a 'Must Watch'. Use emojis at the end to grab attention. "
            "Max 60 characters. "
            f"Example: '{context if context else 'Avneet Kaur'}: Her Most {num_str}Stunning Style Transformations! 🔥'"
            "\n\nRETURN ONLY THE TITLE TEXT."
        )
        
        try:
            # Retry logic for Quota limits (429) & Network
            import time
            import random
            import os
            import google.generativeai as genai
            
            primary_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
            fallback_model = "gemini-2.5-flash"
            safety_model = "gemini-2.5-flash-lite"
            
            # Using a dynamic chain for 5 attempts
            models_chain = [primary_model, primary_model, fallback_model, fallback_model, safety_model]
            
            for attempt in range(5):
                try:
                    current_model_name = models_chain[attempt]
                    model = genai.GenerativeModel(current_model_name)
                    
                    response = model.generate_content([prompt], safety_settings=self.safety_settings)
                    
                    title = response.text.strip().replace('"', '').replace("'", "").replace("\n", " ")
                    if len(title) > 60:
                        title = title[:60].rsplit(' ', 1)[0]
                        
                    # Final safety check for Name First
                    if context and context.lower() not in title.lower()[:len(context)+5]:
                        title = f"{context}: {title}"
                        
                    logger.info(f"✨ Generated compilation title ({current_model_name}): '{title}'")
                    return title
                    
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str:
                        logger.warning(f"⚠️ Quota hit (Attempt {attempt+1}). Retrying with fallback logic...")
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    # Original error handling for other exceptions
                    wait = (2 ** attempt) + random.uniform(0.1, 1.0)
                    logger.warning(f"⚠️ Gemini Title Error ({e}). Retrying in {wait:.1f}s...")
                    time.sleep(wait)
            
        except Exception as e:
            logger.error(f"❌ Compilation title generation failed: {e}")
            return None


# Convenience function for quick caption generation
def generate_caption_from_video(video_path: str, style: str = "viral", timestamp: str = "00:00:01") -> Optional[str]:
    """
    Extract frame from video and generate caption.
    """
    import subprocess
    import tempfile
    
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            frame_path = tmp.name
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", timestamp,
            "-vframes", "1",
            frame_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        generator = GeminiCaptionGenerator()
        caption = generator.generate_caption(frame_path, style)
        
        return caption
        
    except Exception as e:
        logger.error(f"❌ Failed to generate caption from video: {e}")
        return None
    finally:
        if 'frame_path' in locals() and os.path.exists(frame_path):
             try: os.remove(frame_path)
             except: pass

def generate_hashtags_from_video(video_path: str, count: int = 5) -> Optional[str]:
    import subprocess
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            frame_path = tmp.name
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", "00:00:01",
            "-vframes", "1",
            frame_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        generator = GeminiCaptionGenerator()
        tags = generator.generate_hashtags(frame_path, count)
        
        return tags
    except Exception as e:
        logger.error(f"❌ Failed to generate hashtags from video: {e}")
        return None
    finally:
        if 'frame_path' in locals() and os.path.exists(frame_path):
             try: os.remove(frame_path)
             except: pass

# Wrapper for compiler.py compatibility
def generate_caption_direct(video_path: str) -> Optional[str]:
    """
    Direct wrapper for compiler compatibility.
    """
    return generate_caption_from_video(video_path, style="viral")


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 Gemini Caption Generator Test")
    
    if not GEMINI_AVAILABLE:
        print("❌ google-generativeai not installed")
        exit(1)
    
    try:
        generator = GeminiCaptionGenerator()
        print("✅ Gemini initialized successfully!")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")

# Standalone wrapper
def generate_compilation_title(n_videos: int, context: str = None) -> str:
    try:
        generator = GeminiCaptionGenerator()
        return generator.generate_compilation_title(n_videos, context=context)
    except Exception as e:
        logger.error(f"❌ Wrapper failed: {e}")
        return f"{context + ': ' if context else ''}Best {n_videos} Viral Moments Compilation"
