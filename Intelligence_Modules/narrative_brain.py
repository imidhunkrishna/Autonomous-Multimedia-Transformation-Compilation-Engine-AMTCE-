"""
Narrative Brain Module (Multimodal Director)
--------------------------------------------
Orchestrates the creation of cohesive, documentary-style narratives for compilations.
Uses Gemini Pro Vision (Multimodal) to "see" the thumbnails and "read" the metadata.

Key Features:
1. Asset Matching: Pairs Processed Shorts/{Name}_X.json with assets/snapped_thumbs/{Name}_00X.jpg.
2. Batch Process: Sends clips in batches (e.g., 10) to Gemini to maintain context.
3. Continuity: Passes context between batches to ensure a smooth story.
"""

import os
import json
import logging
import re
import glob
from typing import List, Dict, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image

# Load credentials
load_dotenv("Credentials/.env", override=True)

logger = logging.getLogger("narrative_brain")

# NARRATIVE PROMPT (Multimodal - Kardashian Style Audit)
NARRATIVE_PROMPT = """
STRICT VIBE: "The Fashion Genius Socialite".
- PERSONA: You are a Kardashian-style influencer, but with a degree in Textile Engineering. You are an INSIDER who knows the technical secrets.
- LANGUAGE STYLE: Use Kardashian-style slang ("literally", "it's giving", "biblical") but mix it with high-end technical terms from the metadata.
- MIRROR TECH: Hook them with the drama, anchor them with the "Fashion Science".

NARRATIVE RULES:
1. THE HOOK: Start with a dramatic socialite opening ("Okay guys, we need to talk about the technical mastery of this look...").
2. THE ANCHOR: Use a technical fact from the "Journalist Notes" or "Fashion Scout" metadata to explain WHY it's iconic.
3. FLOW: Transition using high-stakes language. "This isn't just a dress, it's a structural manifesto, period."
4. LENGTH: ~2 sentences per clip. One for the vibe, one for the technical "secret".

PREVIOUS CONTEXT (If any):
{prev_context}

OUTPUT FORMAT (JSON):
{{
  "script": "Full Kardashian-style narration text here...",
  "mood": "Iconic/Dramatic/Influencer",
  "title_suggestion": "The Ultimate Style Evolution"
}}
"""

class NarrativeDirector:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        
        if self.gemini_key:
            try:
                genai.configure(api_key=self.gemini_key)
                # Use Gemini Model from Env (Default: gemini-2.5-flash)
                model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                self.model = genai.GenerativeModel(model_name)
                logger.info(f"🎬 Narrative Director: ACTIVE ({model_name})")
            except Exception as e:
                logger.error(f"❌ Narrative Brain Init Failed: {e}")

    def find_associated_assets(self, entity_name: str, limit: int = 10) -> List[Dict]:
        """
        Scans filesystem to pair JSON Metadata with Thumbnail Images.
        Matches Processed Shorts/{Name}_X.json <-> assets/snapped_thumbs/{Name}_00X.jpg
        """
        assets = []
        
        # 1. Normalize Name for Regex
        # "Avneet Kaur" -> "Avneet_kaur" (loosely)
        base_pattern = entity_name.replace(" ", "_").lower()
        
        json_dir = "Processed Shorts"
        thumb_dir = "assets/snapped_thumbs"
        
        # Scan JSONs first (Source of Truth)
        all_jsons = glob.glob(os.path.join(json_dir, "*.json"))
        
        candidates = []
        
        for j_path in all_jsons:
            fname = os.path.basename(j_path)
            # Filter by entity name (case insensitive partial match)
            if base_pattern in fname.lower() and not fname.endswith(".final.json"):
                # Extract Numeric ID
                # regex: .*_(\d+).json
                match = re.search(r'_(\d+)\.json$', fname)
                if match:
                    seq_id = int(match.group(1))
                    candidates.append({
                        "id": seq_id,
                        "json_path": j_path,
                        "base_name": fname.replace(f"_{match.group(1)}.json", "")
                    })
        
        # Sort by ID
        candidates.sort(key=lambda x: x["id"])
        
        # Apply Limit
        candidates = candidates[:limit]
        
        # 2. Find Matching Thumbnails
        final_pairs = []
        for item in candidates:
            # Expected Thumb: {base_name}_{seq_id:03d}.jpg
            # e.g. Avneet_kaur_001.jpg
            thumb_name = f"{item['base_name']}_{item['id']:03d}.jpg"
            thumb_path = os.path.join(thumb_dir, thumb_name)
            
            # Load Metadata (Always required)
            meta = {}
            try:
                with open(item['json_path'], 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Failed to read metadata for {item['base_name']}: {e}")
                continue # Cannot proceed without metadata

            # Check Thumbnail
            final_thumb_path = thumb_path if os.path.exists(thumb_path) else None
            
            if not final_thumb_path:
                logger.warning(f"⚠️ Missing thumbnail for ID {item['id']}: {thumb_path} (Using Metadata Only)")

            final_pairs.append({
                "id": item["id"],
                "json": meta,
                "image_path": final_thumb_path, # Logic handles None
                "video_path": meta.get("video_path", "")
            })
                
        logger.info(f"✅ Found {len(final_pairs)} matched assets for '{entity_name}'")
        return final_pairs

    def generate_compilation_script(self, assets: List[Dict]) -> str:
        """
        Generates a continuous script from a list of assets.
        Handles batching if list is long.
        """
        if not assets: return ""
        if not self.model: return "Narrative generation unavailable (No AI)."
        
        full_script = []
        batch_size = 10
        prev_context = "Start of compilation."
        
        for i in range(0, len(assets), batch_size):
            batch = assets[i : i + batch_size]
            logger.info(f"🧠 Processing Batch {i//batch_size + 1} ({len(batch)} clips)...")
            
            # Prepare Multimodal Payload
            payload = []
            
            # 1. System Prompt (Text)
            prompt_text = NARRATIVE_PROMPT.format(
                count=len(batch),
                prev_context=prev_context
            )
            payload.append(prompt_text)
            
            # 2. Add Images & Metadata (Interleaved)
            for file_idx, item in enumerate(batch):
                # Image
                try:
                    img = Image.open(item['image_path'])
                    payload.append(f"--- CLIP {file_idx+1} ---")
                    payload.append(img) # The actual PIL Image
                except:
                    payload.append(f"[Missing Image for Clip {file_idx+1}]")
                
                # Metadata Summary
                meta = item.get("json", {})
                fashion = meta.get("brain_analysis", {}).get("fashion_scout", {}).get("outfit_description", "Fashion details unavailable")
                facts = meta.get("brain_analysis", {}).get("visual_facts", [])
                caption = meta.get("caption", "No caption available")
                
                # [JOURNALIST CONTEXT] - Injecting the "Ghost" Script
                journalist_notes = meta.get("brain_analysis", {}).get("editorial_script", "")
                if journalist_notes:
                    logger.info(f"📰 Injecting Journalist Context ({len(journalist_notes)} chars) for Clip {file_idx+1}")
                
                meta_text = f"""
                METADATA (Clip {file_idx+1}):
                - Outfit: {fashion[:300]}...
                - Key Facts: {', '.join(facts[:3])}
                - Journalist Notes: {journalist_notes[:500]} 
                - Original Caption: {caption[:200]}
                """
                payload.append(meta_text)
            
            # 3. Call Gemini — 120s timeout (heavy multimodal: up to 10 images per batch)
            try:
                response = self.model.generate_content(
                    payload,
                    request_options={"timeout": 120}
                )

                resp_text = response.text.strip()
                
                # Extract JSON
                match = re.search(r'(\{.*\})', resp_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    script_part = data.get("script", "")
                    full_script.append(script_part)
                    
                    # Update context for next batch
                    prev_context = f"Previous batch ended with: {script_part[-100:]}"
                else:
                    logger.warning("⚠️ Narrative Brain returned raw text (no JSON). Using raw.")
                    full_script.append(resp_text)
                    
            except Exception as e:
                logger.error(f"❌ Batch Generation Failed: {e}")
                full_script.append(f"[Narrative gap for clips {i}-{i+len(batch)}]")
                
        final_narrative = " ".join(full_script)
        return final_narrative

# Sentinel
director = NarrativeDirector()
