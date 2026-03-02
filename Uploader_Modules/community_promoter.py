import os
import json
import time
import hashlib
import random
import logging
import asyncio
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger("community_promoter")
logger.setLevel(logging.INFO)

STATE_FILE = "The_json/community_promo_state.json"
LOS_POLLOS_FILE = "The_json/los_pollos_links.json"

class CommunityPromoter:
    """
    Handles 'Community Post' promotion via Channel Comments (commentThreads).
    - Rate Limited (6h)
    - Deterministic Content (No Gemini)
    - Silent Failures
    """
    
    def __init__(self):
        self.state = self._load_state()
        
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Migration: Single URL -> Pool
                    if "last_compilation_url" in data and "promo_pool" not in data:
                        data["promo_pool"] = [
                            {"url": data["last_compilation_url"], "ts": data.get("last_compilation_time", time.time())}
                        ]
                        
                    return data
            except Exception:
                pass
        return {"last_run": 0, "posted_hashes": [], "promo_pool": [], "last_rotation_idx": -1}

    def _save_state(self):
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"❌ Failed to save promoter state: {e}")

    def _get_telegram_link(self) -> str:
        """Reads the Telegram link from config."""
        try:
            with open("Credentials/telegram_config.json", "r") as f:
                data = json.load(f)
                return data.get("telegram_link", "")
        except:
            return ""

    def _get_template(self, clip_count: int, promo_url: str, is_short: bool = True, custom_text: Optional[str] = None, fashion_data: Optional[Dict] = None) -> str:
        """
        Unified Funnel Strategy:
        1. Fashion Hook (If available) - TOP.
        2. Psychological Partner Bridge - MIDDLE.
        3. Elite Telegram Conversion - BOTTOM.
        """
        final_parts = []
        
        # --- SECTION 1: FASHION HOOK (BUY FOR HER) ---
        if fashion_data:
            ctas = fashion_data.get("imaginative_ctas", {})
            # User Request: "don't put he amazon link as commusnity post instead say link in description"
            # So we use the hook text but NOT the link.
            
            options = []
            # User Request: English, Hinglish, Pure Hindi (Devanagari)
            for lang in ["english", "hinglish", "hindi"]:
                if ctas.get(lang): options.append(ctas[lang])
            
            if options:
                # User Request: Put all 3 languages in one go (Concatenate them)
                combined_cta = ""
                for opt in options:
                    clean_opt = opt.replace("[Link]", "").strip()
                    combined_cta += f"{clean_opt}\n"
                
                # Add directive
                fashion_part = f"{combined_cta.strip()}\n✨ Get the look: (Link in Description) 👇"
                final_parts.append(fashion_part)

        # --- SECTION 2: EGO & MYSTERY TEASER (FEMALE GAZE) ---
        tg_link = self._get_telegram_link()
        clean_handle = tg_link.replace("https://t.me/", "@") if tg_link else "@swargawasal_official"
        
        enable_lp_yt = os.getenv("LOS_POLLOS_YOUTUBE", "no").lower() in ["yes", "true", "on"]
        mon_link = self._get_next_los_pollos_link() if enable_lp_yt else None
        mon_part = f"\n🔥 Exclusive Link: {mon_link}" if mon_link else ""

        # Motivation Logic: If we already have fashion data, we bridge it.
        has_fashion = len(final_parts) > 0
        
        if is_short:
            if has_fashion:
                # BRIDGE TEMPLATES (Fashion -> Ego/Status)
                teasers = [
                    f"💖 Warning: This fit causes extreme jealousy. Not everyone can handle the attention. 💅\n🚀 Join the High-Value Circle (VIP Access) 👇\n👉 Telegram: {clean_handle}{mon_part}",
                    f"🥂 They will stare. Make it worth their while. Only 1% of women have this specific taste. 🌟\n✨ Unlock the Secret Collection 👇\n🔥 Telegram: {clean_handle}{mon_part}"
                ]
            else:
                # STANDALONE TEASERS (Direct Ego Hook)
                teasers = [
                    f"🔥 Confidence isn't bought, but this vibe helps. \n\n✨ See why he can't look away... 👇\n🚀 Join the Elite Circle: {clean_handle}{mon_part}",
                    f"🔥 He will regret losing you when you wear this.\n\n🌟 Unlock the 'Fatal' Collection here... 👇\n✨ Join Telegram VIP: {clean_handle}{mon_part}"
                ]
            final_parts.append(random.choice(teasers))
        else:
            # COMPILATION / LONG FORM
            teaser = f"🔥 Watch UNEDITED raw clips & find high-quality connections in our private circle! 👇\n✨ Join the Elite Community: {tg_link or clean_handle}"
            final_parts.append(teaser)

        # Final Assembly
        return "\n\n".join(final_parts)

    def _get_next_los_pollos_link(self) -> Optional[str]:
        """
        Loads links from los_pollos_links.json and rotates through them.
        """
        try:
            if not os.path.exists(LOS_POLLOS_FILE):
                return None
                
            with open(LOS_POLLOS_FILE, "r", encoding="utf-8") as f:
                links = json.load(f)
                
            if not links or not isinstance(links, list):
                return None
                
            idx = self.state.get("last_rotation_idx", -1)
            next_idx = (idx + 1) % len(links)
            
            self.state["last_rotation_idx"] = next_idx
            self._save_state()
            
            return links[next_idx]
        except Exception as e:
            logger.error(f"❌ Failed to rotate Los Pollos links: {e}")
            return None

    def register_compilation_url(self, url: str):
        """
        Adds compilation URL to the rotating pool (Max 10).
        """
        pool = self.state.get("promo_pool", [])
        
        # Deduplicate
        pool = [x for x in pool if x["url"] != url]
        
        # Add new
        pool.append({"url": url, "ts": time.time()})
        
        # Cap size (Keep recent 10)
        if len(pool) > 10:
            pool = pool[-10:]
            
        self.state["promo_pool"] = pool
        self._save_state()
        logger.info(f"💾 Registered Compilation URL to Pool (Total: {len(pool)}): {url}")

    def _get_rotation_url(self) -> Optional[str]:
        """
        Picks a URL from the pool (Random Rotation).
        """
        pool = self.state.get("promo_pool", [])
        if not pool:
            return None
        return random.choice(pool)["url"]

    def _can_run(self, content_hash: str) -> bool:
        """
        Checks rate limit (1m) and duplication.
        """
        now = time.time()
        
        # 1. Rate Limit (1 Minute Safe Guard)
        last_run = self.state.get("last_run", 0)
        
        if now - last_run < 60: 
            logger.info(f"⏳ Community Promotion skipped (Rate Limit: {int(60 - (now-last_run))}s remaining)")
            return False
            
        # 2. Duplicate Guard
        if content_hash in self.state.get("posted_hashes", []):
            logger.info("♻️ Community Promotion skipped (Duplicate content)")
            return False
            
        return True

    def _register_success(self, content_hash: str):
        self.state["last_run"] = time.time()
        
        # Keep hash history manageable (last 50)
        hashes = self.state.get("posted_hashes", [])
        hashes.append(content_hash)
        if len(hashes) > 50:
            hashes = hashes[-50:]
        self.state["posted_hashes"] = hashes
        
        self._save_state()

    async def promote_on_short_async(self, service, short_video_url: str, is_short: bool = True, delay_seconds: int = 20, custom_text: Optional[str] = None, fashion_data: Optional[Dict] = None):
        """
        Promotes a ROTATING Compilation on the provided Video (Short or Long).
        """
        comp_url = self._get_rotation_url()
        
        if not comp_url:
            logger.warning("⚠️ No Compilation URL in Pool. Skipping promotion.")
            return

        logger.info(f"⏲️ Scheduling Community Promotion in {delay_seconds}s (Link: {short_video_url})...")
        await asyncio.sleep(delay_seconds)
        
        # We need to run the blocking API call in a thread
        clip_count = 10 
        await asyncio.to_thread(self._promote_sync, service, short_video_url, comp_url, clip_count, is_short, custom_text, fashion_data)

    def _extract_video_id(self, url: str) -> Optional[str]:
        try:
            if "youtu.be" in url:
                return url.split("/")[-1].split("?")[0]
            if "v=" in url:
                return url.split("v=")[-1].split("&")[0]
            if "shorts" in url:
                 return url.split("shorts/")[-1].split("?")[0]
        except:
            pass
        return None

    def _promote_sync(self, service, target_video_url: str, promo_link: str, clip_count: int, is_short: bool = True, custom_text: Optional[str] = None, fashion_data: Optional[Dict] = None):
        try:
            # 1. Extract Video ID (Target Short) - Required for Unique Hashing
            video_id = self._extract_video_id(target_video_url)
            if not video_id:
                logger.warning(f"⚠️ Could not extract Video ID from {target_video_url}. Skipping.")
                return

            # 2. Generate Content
            text = self._get_template(clip_count, promo_link, is_short=is_short, custom_text=custom_text, fashion_data=fashion_data)
            
            # UNIQUE HASH: Include video_id so we can post the same text on DIFFERENT videos
            content_hash = hashlib.md5(f"{video_id}:{text}".encode()).hexdigest()
            
            # 3. Guard Checks
            if not self._can_run(content_hash):
                return

            # 4. Get Channel ID (Required for commentThreads)
            try:
                channels_response = service.channels().list(mine=True, part="id").execute()
                if not channels_response.get("items"):
                    logger.warning("⚠️ Could not resolve Channel ID. Skipping.")
                    return
                channel_id = channels_response["items"][0]["id"]
            except Exception as e:
                 logger.warning(f"⚠️ Channel ID fetch failed: {e}")
                 return

            # 4. Execute API Call (Best Effort)
            # Posting a TOP LEVEL COMMENT on the TARGET VIDEO
            body = {
                "snippet": {
                    "channelId": channel_id,
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": text
                        }
                    }
                }
            }
            
            service.commentThreads().insert(
                part="snippet",
                body=body
            ).execute()
            
            # 5. Success
            logger.info(f"📣 Community Promotion Posted on Short ({video_id}) -> Linking to Compilation!")
            self._register_success(content_hash)
            
        except Exception as e:
            # SILENT FAILURE
            logger.warning(f"ℹ️ Community Promotion skipped: {e}")

# Global Instance
promoter = CommunityPromoter()

if __name__ == "__main__":
    # Manual Test Mode
    logging.basicConfig(level=logging.INFO)
    print("📢 Community Promoter Manual Mode")
    
    try:
        from Uploader_Modules.uploader import get_authenticated_service
        service = get_authenticated_service()
        if not service:
            print("❌ Auth failed.")
            exit(1)
            
        url = input("Enter Video URL: ").strip()
        count = int(input("Enter Clip Count: ").strip())
        
        print("🚀 Promoting...")
        promoter._promote_sync(service, url, count)
        
    except ImportError:
        import traceback
        traceback.print_exc()
        print("❌ Could not import 'uploader.get_authenticated_service'. Check traceback above.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error: {e}")
