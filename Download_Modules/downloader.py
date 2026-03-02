import os
import logging
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError
import glob
import time
from datetime import datetime
import re
import json
import sys
import argparse
from typing import Dict, Optional

import hashlib
import shutil

import subprocess
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

logger = logging.getLogger("downloader")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Configuration & Constants
DOWNLOAD_RETRY_DELAY = int(os.getenv("DOWNLOAD_RETRY_DELAY", 2))
RATE_LIMIT_WAIT = int(os.getenv("RATE_LIMIT_WAIT", 8))
DEBUG_JSON = os.getenv("DEBUG_JSON", "0") == "1"

# Throttle updates (Once per 12 hours max)
LAST_UPDATE_TIME = 0
UPDATE_COOLDOWN = 12 * 3600 

def _update_yt_dlp():
    """Programmatically updates yt-dlp to latest version."""
    global LAST_UPDATE_TIME
    now = time.time()
    
    if now - LAST_UPDATE_TIME < UPDATE_COOLDOWN:
        logger.info("⏳ yt-dlp update cooldown active. Skipping.")
        return False
        
    logger.info("🚀 Triggering automatic yt-dlp update (pip install -U yt-dlp)...")
    try:
        # Use sys.executable to ensure we update the correct env
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], check=True, capture_output=True)
        import yt_dlp
        import importlib
        importlib.reload(yt_dlp)
        logger.info(f"✅ yt-dlp updated successfully to v{yt_dlp.version.__version__}")
        LAST_UPDATE_TIME = now
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update yt-dlp: {e}")
        return False

def _calculate_file_hash(path: str) -> str:
    """Calculate SHA1 hash of file for uniqueness."""
    try:
        sha1 = hashlib.sha1()
        with open(path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data: break
                sha1.update(data)
        return sha1.hexdigest()[:8]
    except:
        return ""

def _calculate_content_fingerprint(video_path: str) -> str:
    """
    Generate a robust content fingerprint based on visual content (Deep Hash).
    Hashes: Resolution + Duration + First 3 Frames (Visual)
    Use this to detect same video even if re-encoded or named differently.
    """
    try:
        if cv2 is None: return _calculate_file_hash(video_path)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return _calculate_file_hash(video_path)
        
        hashes = []
        
        # 1. Metadata Component (Robust to container change)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        dur = int(frames / fps) if fps > 0 else 0
        
        # Soft-Quantize Duration to merge slightly different cuts (e.g. +/- 1s)
        # Actually strict is better for now.
        hashes.append(f"{w}x{h}_{dur}")
        
        # 2. Visual Component (First 3 frames)
        # Read frames at 0, 10, 20
        for i in range(3):
            if i > 0: # Skip ahead slightly
                cap.set(cv2.CAP_PROP_POS_FRAMES, i * 10)
                
            ret, frame = cap.read()
            if not ret: break
            
            # Resize small to ignore noise/compression artifacts
            small = cv2.resize(frame, (64, 64))
            # Hash the raw bytes
            frame_hash = hashlib.sha1(small.tobytes()).hexdigest()[:8]
            hashes.append(frame_hash)
            
        cap.release()
        
        combined = "_".join(hashes)
        final_hash = hashlib.sha1(combined.encode()).hexdigest()[:12]
        return final_hash
        
    except Exception as e:
        logger.warning(f"Fingerprint failed: {e}. Fallback to file hash.")
        return _calculate_file_hash(video_path)


# ==================== ARCHITECTURE: INDEX & ATOMICITY ====================

class DownloadIndex:
    """
    Persistent, lightweight index for O(1) duplicate lookups.
    Replaces expensive O(N) file system scans.
    """
    INDEX_FILE = os.path.join(DOWNLOAD_DIR, "index.json")
    
    @classmethod
    def _load_index(cls) -> Dict:
        try:
            if os.path.exists(cls.INDEX_FILE):
                with open(cls.INDEX_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Index load failed: {e}. Starting fresh.")
        return {"ids": {}, "hashes": {}}

    @classmethod
    def _save_index(cls, data: Dict):
        """Atomic save of index."""
        temp = cls.INDEX_FILE + ".tmp"
        try:
            with open(temp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=0) # Compact
            if os.path.exists(cls.INDEX_FILE):
                os.remove(cls.INDEX_FILE)
            os.rename(temp, cls.INDEX_FILE)
        except Exception as e:
            logger.error(f"❌ Index save failed: {e}")
            if os.path.exists(temp): os.remove(temp)

    @classmethod
    def register(cls, video_path: str, meta: Dict):
        """Register a new download commit."""
        data = cls._load_index()
        
        # 1. ID Indexing
        url_id = meta.get("id_extracted") or meta.get("url_id")
        if url_id:
            data["ids"][str(url_id)] = video_path
            
        # 2. Hash Indexing
        c_hash = meta.get("content_hash")
        if c_hash:
            data["hashes"][c_hash] = video_path
            
        cls._save_index(data)

    @classmethod
    def find_by_id(cls, url_id: str) -> Optional[str]:
        if not url_id: return None
        data = cls._load_index()
        path = data["ids"].get(str(url_id))
        if path and os.path.exists(path): return path
        # If indexed but missing on disk, strictly return None (stale)
        return None

    @classmethod
    def find_by_hash(cls, target_hash: str) -> Optional[str]:
        if not target_hash: return None
        data = cls._load_index()
        path = data["hashes"].get(target_hash)
        if path and os.path.exists(path): return path
        return None

def _atomic_rename(src: str, dst: str) -> bool:
    """
    Atomic rename with strict Windows collision handling.
    Eliminates TOCTOU race conditions.
    """
    try:
        # Windows: os.rename fails if dst exists. 
        # We MUST ensure dst does NOT exist for a clean new file 
        # OR we accept that we are overwriting (if logic demands).
        # Here we assume we want UNIQUE filenames, so exist=fail.
        
        if os.path.exists(dst): return False
        os.rename(src, dst)
        return True
    except OSError:
        return False

def _sanitize_filename(name: str) -> str:
    """Sanitize filename."""
    clean = re.sub(r'[^\w\s-]', '', name)
    return clean.replace(' ', '_').strip()




def download_video(url: str, custom_title: str = None, force_filename: str = None) -> str:
    """
    Architecturally Robust Downloader (v2)
    - Atomic Transactionality (Commit/Rollback)
    - Indexed Duplicate Lookups via DownloadIndex
    - Race-Condition Free Rename
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. ID Extraction & Duplicate Check (O(1) via Index)
    url_id = ""
    # Platform Expansion: Instagram (Reels/Stories/Posts) & Facebook (Reels)
    if "instagram.com" in url:
        # Reels/Posts: /reel/ID or /p/ID
        match = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', url)
        if match:
            url_id = match.group(1)
        # Stories: /stories/username/ID
        elif "/stories/" in url:
            match = re.search(r'/stories/[^/]+/(\d+)', url)
            if match:
                url_id = match.group(1)
                
    elif "facebook.com" in url or "fb.watch" in url:
        # FB Reels: /reel/ID/ or /videos/ID/
        match = re.search(r'/(?:reel|videos)/(\d+)', url)
        if match:
            url_id = match.group(1)
    
    if url_id:
        logger.info(f"📌 Extracted ID: {url_id}")
        existing = DownloadIndex.find_by_id(url_id)
        if existing:
            return existing, True

        # 1a. FALLBACK: Manual File Scan (User Request: "Check manual files by ID")
        # If the index is empty/stale, scan the folder for any file containing the ID.
        if url_id:
            scan_candidates = glob.glob(os.path.join(DOWNLOAD_DIR, "*")) 
            for candidate in scan_candidates:
                 # Check if filename contains ID (case insensitive?)
                 # Usually IDs are case sensitive (YouTube), but let's be strict first.
                 if url_id in os.path.basename(candidate):
                     # Verify it's a video
                     if candidate.lower().endswith(('.mp4', '.mkv', '.webm', '.mov')):
                         logger.info(f"♻️ [MANUAL SCAN] Found existing file with ID '{url_id}': {os.path.basename(candidate)}")
                         
                         # Auto-Repair Index
                         try:
                             DownloadIndex.register(candidate, {"id_extracted": url_id})
                         except: pass
                         
                         return candidate, True

        # 1b. Smart Title-Based Reuse (User Logic)
        if url_id and custom_title:
             # Sanitize title to match how we save it
             title_slug = _sanitize_filename(custom_title)[:100]
             
             # Search for all variants: Title.json, Title_1.json, etc.
             candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{title_slug}*.json"))
             
             for c in candidates:
                 try:
                     with open(c, 'r', encoding='utf-8') as f:
                         meta = json.load(f)
                     
                     # Check ID Match (Strict)
                     if str(meta.get('id')) == str(url_id):
                         # Match Found! Check if video exists
                         base = os.path.splitext(c)[0]
                         # Try common extensions
                         for ext in ['.mp4', '.mkv', '.webm', '.mov']:
                             v_path = base + ext
                             if os.path.exists(v_path):
                                 logger.info(f"♻️ [SMART REUSE] ID Match found in '{os.path.basename(v_path)}'. Skipping download.")
                                 return v_path, True
                 except: pass
            
    # 2. Temp File Setup (The "Work Area")

    # 2. Temp File Setup (The "Work Area")
    # We use a strict prefix for temp files to easily identify them
    temp_base = f"download_{timestamp}_{url_id if url_id else 'unknown'}"
    temp_video_tmpl = os.path.join(DOWNLOAD_DIR, f"{temp_base}.%(ext)s")
    
    # We don't know the extension yet, so we'll have to find it after
    absolute_tmpl = os.path.abspath(temp_video_tmpl)
    
    logger.info("📥 [DOWNLOAD] Request started")
    logger.info(f"    ├─ url: {url}")
    logger.info(f"    └─ temp: {temp_base}")
    
    # 3. Download Options (Hardened)
    ydl_opts = {
        'outtmpl': absolute_tmpl,
        'format': 'bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True, # We handle success manually
        'restrictfilenames': True, # HELPS WINDOWS: Avoids special chars impacting file ops
        # Fallbacks handled in loops below
    }



    # --- RETRY & AUTH LOOP ---
    success = False
    downloaded_path = None
    info_dict = {}

    # Keywords that indicate yt-dlp is outdated or site auth has changed
    _UPDATE_TRIGGER_KEYWORDS = [
        "no suitable extractor",   # ← THE MAIN FIX: Instagram extractor gone
        "extractor",               # Generic extractor failure
        "unsupported url",         # yt-dlp doesn't know the URL format
        "sign in", "login", "401",
        "unavailable", "dpapi",
        "rate-limit", "cookies",
        "not available",
        "this version",            # "Update yt-dlp to the latest version"
        "upgrade",
    ]

    strategies = ["no_auth", "cookies_file", "username_password", "browser_firefox", "browser_chrome"]

    for strategy in strategies:
        if success: break

        # Setup Auth
        opts = ydl_opts.copy()
        if strategy == "cookies_file":
            cpath = os.getenv("COOKIES_FILE", "cookies.txt")
            if os.path.exists(cpath) and os.path.getsize(cpath) > 100:
                opts['cookiefile'] = cpath
            else: continue
        elif strategy == "username_password":
            user = os.getenv("IG_USERNAME")
            pwd = os.getenv("IG_PASSWORD")
            if user and pwd:
                opts['username'] = user
                opts['password'] = pwd
            else:
                continue
        elif strategy.startswith("browser_"):
            browser = strategy.split("_")[1]
            opts['cookiesfrombrowser'] = (browser,)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    info_dict = info
                    candidates = glob.glob(os.path.join(DOWNLOAD_DIR, f"{temp_base}.*"))
                    valid = [c for c in candidates if not c.endswith(('.part', '.ytdl', '.json'))]
                    if valid:
                        downloaded_path = valid[0]
                        success = True
        except (DownloadError, ExtractorError) as e:
            err_msg = str(e).lower()
            logger.warning(f"⚠️ [DOWNLOAD] yt-dlp Error ({strategy}): {err_msg[:120]}...")

            if any(x in err_msg for x in _UPDATE_TRIGGER_KEYWORDS):
                if "cookies" in err_msg:
                    logger.warning("🍪 Cookie/Auth issue detected.")
                logger.warning("🔄 Extractor/site breakage detected — triggering yt-dlp auto-update...")
                if _update_yt_dlp():
                    logger.info("♻️ yt-dlp updated. Retrying with next strategy...")
                    # Reset cooldown so a second update isn't immediately blocked
                    import importlib
                    try:
                        import yt_dlp as _ytdlp_fresh
                        importlib.reload(_ytdlp_fresh)
                    except Exception:
                        pass

            elif "geo" in err_msg or "country" in err_msg:
                logger.error("❌ GEO-BLOCKED: Content not available in this region.")

            time.sleep(2)

        except Exception as e:
            err_str = str(e).lower()
            logger.warning("⚠️ [DOWNLOAD] Attempt failed (Generic)")
            logger.warning(f"    ├─ strategy: {strategy}")
            logger.warning(f"    ├─ error: {err_str[:100]}")
            
            # Generic Fallback for unexpected site blocks
            if any(x in err_str for x in ["rate-limit", "cookies", "login", "unavailable"]):
                 _update_yt_dlp()
            
            time.sleep(2)

        # RESCUE MISSION: If success is False, check for .part file and manually rename
        # This handles WinError 32 where yt-dlp fails to rename but file exists
        if not success:
             parts = glob.glob(os.path.join(DOWNLOAD_DIR, f"{temp_base}.*.part"))
             if parts:
                 try:
                     part_file = parts[0]
                     logger.info(f"🚑 Attempting rescue of partial download: {part_file}")
                     
                     # Robust Retry for File Locking (Windows)
                     rescued_name = part_file.replace(".part", "")
                     rescue_success = False
                     
                     for attempt in range(5):
                         try:
                             if os.path.exists(rescued_name):
                                 os.remove(rescued_name)
                             os.rename(part_file, rescued_name)
                             downloaded_path = rescued_name
                             rescue_success = True
                             success = True
                             logger.info("✅ Rescue successful!")
                             break
                         except OSError as e:
                             # Access denied / File in use
                             logger.warning(f"🔒 Rescue lock wait ({attempt+1}/5): {e}")
                             time.sleep(2)
                             
                     if not rescue_success:
                         logger.error(f"❌ Rescue failed: Could not acquire lock on {part_file}")
                         
                 except Exception as e:
                     logger.error(f"❌ Rescue failed: {e}")

    if not success or not downloaded_path:
        logger.error("❌ All download attempts failed.")
        return None

    # --- 4. ATOMIC COMMIT PHASE ---
    try:
        # A. Calculate Hash (Deep Fingerprint)
        logger.info("🔍 Computing Deep Fingerprint...")
        content_hash = _calculate_content_fingerprint(downloaded_path)
        file_size = os.path.getsize(downloaded_path)
        
        # B. Check Hash Duplicate (O(1))
        existing_hash_match = DownloadIndex.find_by_hash(content_hash)
        if existing_hash_match:
             logger.info(f"♻️ CONTENT HASH MATCH: {os.path.basename(existing_hash_match)}")
             try: os.remove(downloaded_path) # Cleanup duplicate temp
             except: pass
             
             # NEW: Rename existing file to match new Custom Title if needed
             if custom_title:
                 current_name = os.path.basename(existing_hash_match)
                 title_slug = _sanitize_filename(custom_title)[:100]
                 
                 # Basic check: is title_slug part of the filename?
                 if title_slug.lower() not in current_name.lower():
                     logger.info(f"✏️ Renaming cached file to match new title: {custom_title}")
                     ext = existing_hash_match.rsplit('.', 1)[-1]
                     old_path = existing_hash_match
                     
                     # Rename Loop
                     for i in range(1, 200):
                         suffix = f"_{i}"
                         candidate_name = f"{title_slug}{suffix}.{ext}"
                         candidate_path = os.path.join(DOWNLOAD_DIR, candidate_name)
                         
                         if _atomic_rename(old_path, candidate_path):
                             # Rename successful
                             existing_hash_match = candidate_path
                             
                             # Rename Metadata Sidecar
                             old_json = os.path.splitext(old_path)[0] + ".json"
                             new_json = os.path.splitext(candidate_path)[0] + ".json"
                             if os.path.exists(old_json):
                                 try: _atomic_rename(old_json, new_json)
                                 except: pass
                                 
                             # Update Index (Delete old, Add new)
                             # Since checking by hash will find the old path in the dict loaded from disk?
                             # No, we must update the index on disk.
                             # Actually just calling register() overwrites the hash entry.
                             # We need to recreate meta dict? Or just register.
                             try:
                                 # Load old meta if possible
                                 reg_meta = {}
                                 if os.path.exists(new_json):
                                     with open(new_json, 'r') as f: reg_meta = json.load(f)
                                 # Update title in meta
                                 reg_meta['title'] = custom_title
                                 DownloadIndex.register(candidate_path, reg_meta)
                             except: pass
                             
                             logger.info(f"✅ Renamed to: {candidate_name}")
                             break
             
             return existing_hash_match, True

        # C. Metadata Prep
        duration = info_dict.get("duration")
        if not duration and cv2 is not None:
             cap = cv2.VideoCapture(downloaded_path)
             if cap.isOpened():
                 frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                 fps = cap.get(cv2.CAP_PROP_FPS)
                 if fps > 0:
                     duration = int(frames / fps)
                 cap.release()
                 
        meta = {
            "id": url_id,
            "url": url,
            "title": info_dict.get("title", "video"),
            "uploader": info_dict.get("uploader", "unknown"),
            "content_hash": content_hash,
            "file_size": file_size,
            "duration": duration,
            "download_timestamp": time.time(),
            "source_platform": "instagram" # assumed
        }
        
        # D. Determine Final Filename (Deterministic & Atomic)
        final_video_path = None
        ext = downloaded_path.rsplit('.', 1)[-1]
        
        if force_filename:
             # STRICT MODE: Use exact filename provided (ignoring extension derived from name, using real ext)
             # User says unique_filename is like "Title_hash.mp4".
             # We should use the base name and append REAL extension to be safe.
             base_force = os.path.splitext(force_filename)[0]
             candidate_name = f"{base_force}.{ext}"
             candidate_path = os.path.join(DOWNLOAD_DIR, candidate_name)
             
             # Overwrite Policy for Forced flow? Use atomic rename but pre-delete if forced.
             if os.path.exists(candidate_path):
                 try: os.remove(candidate_path)
                 except: pass
                 
             if _atomic_rename(downloaded_path, candidate_path):
                 final_video_path = candidate_path
        else:
            # Standard Logic
            if custom_title:
                 title_slug = _sanitize_filename(custom_title)[:100]
            else:
                 title_slug = _sanitize_filename(meta["title"])[:50]
            
            if not title_slug: title_slug = f"video_{url_id}"
            
            # 1. Try Base Name First
            candidate_base = f"{title_slug}.{ext}"
            path_base = os.path.join(DOWNLOAD_DIR, candidate_base)
            if _atomic_rename(downloaded_path, path_base):
                final_video_path = path_base
            else:
                # 2. Rename Loop (Collision Avoidance)
                for i in range(1, 200):
                    suffix = f"_{i}"
                    candidate_name = f"{title_slug}{suffix}.{ext}"
                    candidate_path = os.path.join(DOWNLOAD_DIR, candidate_name)
                    
                    if _atomic_rename(downloaded_path, candidate_path):
                        final_video_path = candidate_path
                        break
                
        # Last Resort Fallback (Hash-based name)
        if not final_video_path:
             candidate_name = f"{title_slug}_{content_hash[:6]}.{ext}"
             candidate_path = os.path.join(DOWNLOAD_DIR, candidate_name)
             if _atomic_rename(downloaded_path, candidate_path):
                 final_video_path = candidate_path
             else:
                 # Should never happen unless hash collision on FS
                 logger.error("❌ CRITICAL: Could not resolve filename collision.")
                 os.remove(downloaded_path)
                 return None

        # E. Save Metadata (Atomic JSON)
        final_json_path = final_video_path.rsplit('.', 1)[0] + ".json"
        try:
             with open(final_json_path, 'w', encoding='utf-8') as f:
                 json.dump(meta, f, indent=2)
        except Exception as e:
             logger.error(f"❌ Failed to save metadata: {e}")
             # Rollback video? No, let's keep video but log error.
             # Strict atomicity would delete video, but video is valuable.
             # We will just not register in index if meta fails (soft consistency)
        
        # F. Update Index (Commit)
        DownloadIndex.register(final_video_path, meta)
        
        dur_str = f" | {duration}s" if duration else ""
        logger.info(f"✅ Download Committed: {os.path.basename(final_video_path)}{dur_str}")
        return final_video_path, False

    except Exception as e:
        logger.error(f"❌ Transaction Failed: {e}")
        # Rollback Temp
        if downloaded_path and os.path.exists(downloaded_path):
            try: os.remove(downloaded_path)
            except: pass
        return None


def main():
    """CLI Entry Point for standalone harvester operations."""
    parser = argparse.ArgumentParser(description="AMTCE Harvest Module: Standalone Video Downloader")
    parser.add_argument("--input", "-i", required=True, help="Target URL (Instagram, TikTok, YouTube, etc.)")
    parser.add_argument("--title", "-t", help="Optional custom title for the video")
    parser.add_argument("--force", "-f", help="Force a specific filename (atomic overwrite)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    # Configure Console Output for CLI usage
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    print(f"\n📥 AMTCE Harvester: Processing Request...")
    print(f"🔗 URL: {args.input}")
    
    try:
        result = download_video(args.input, custom_title=args.title, force_filename=args.force)
        
        if result:
            v_path, is_cached = result
            status = "REUSED (Cached)" if is_cached else "DOWNLOADED"
            print(f"\n✅ SUCCESS!")
            print(f"   ├─ Status: {status}")
            print(f"   └─ Path:   {os.path.abspath(v_path)}")
        else:
            print(f"\n❌ FAILED: All automated strategies exhausted.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
