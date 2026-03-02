import os
import sys
import logging
import re
import asyncio
import time
import json
import random
import threading
import tempfile
import glob
import csv
import shutil
import traceback
import signal
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import gc

# External Libs (Safe Imports)
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda **kwargs: None # Dummy fallback
    logging.warning("⚠️ 'python-dotenv' not found. Environment variables must be set manually.")

try:
    from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaVideo
    from telegram.ext import (
        ApplicationBuilder, 
        ContextTypes, 
        CommandHandler, 
        MessageHandler, 
        CallbackQueryHandler, 
        filters,
        Application
    )
    from telegram.request import HTTPXRequest
    from telegram.error import NetworkError, TimedOut, BadRequest, Forbidden
    import httpx
except ImportError as e:
    # Critical dependency check
    logging.critical(f"❌ Telegram Bot API not installed: {e}")
    sys.exit(1)

# 1. Immediate Logging Setup (captured before heavy modules)
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from Health_handlers import get_portal

# 2. Initialize authorized modules based on system health and .env modes
portal = get_portal()
globals().update(portal.__dict__)

import compiler
from Audio_Modules import audio_deduplicator
from Intelligence_Modules.deduplication import DedupEngine

# Configurable Constants with Safe Defaults
CLEANUP_POLICY = os.getenv("CLEANUP_POLICY", "delayed") # immediate, on_success, delayed
DEBUG_JSON = int(os.getenv("DEBUG_JSON", "0"))
NET_RETRY_COUNT = int(os.getenv("NET_RETRY_COUNT", "3"))
NET_BACKOFF_BASE = float(os.getenv("NET_BACKOFF_BASE", "2.0"))
LOCK_WAIT_SECS = int(os.getenv("LOCK_WAIT_SECS", "5"))
TELEGRAM_MAX_UPLOAD_MB = int(os.getenv("TELEGRAM_MAX_UPLOAD_MB", "50"))
SESSION_TTL_SECS = int(os.getenv("SESSION_TTL_SECS", "86400"))
# --- REAL-TIME CASH-MAXIMIZER OVERRIDE ---
CASH_MAX_MODE = os.getenv("CASH_MAX_MODE", "no").lower() == "yes"
if CASH_MAX_MODE:
    logger.info("💰 [MONEY PRINTER ACTIVE] CASH_MAX_MODE detected. Locking threads to SEQUENTIAL.")
    THREAD_POOL_SIZE = 1
    COMPILATION_BATCH_SIZE = 3 # Smaller batches for 8GB RAM
else:
    THREAD_POOL_SIZE = int(os.getenv("THREAD_POOL_SIZE", "4"))
    COMPILATION_BATCH_SIZE = int(os.getenv("COMPILATION_BATCH_SIZE", "5"))

ALLOWED_DOMAINS = ["instagram.com", "youtube.com", "youtu.be"]

# Directory Setup
JOB_DIR = "jobs"
COMPILATIONS_DIR = "final_compilations"

os.makedirs(JOB_DIR, exist_ok=True)
os.makedirs(COMPILATIONS_DIR, exist_ok=True)
os.makedirs("downloads", exist_ok=True)
os.makedirs("music", exist_ok=True)
os.makedirs("Original_audio", exist_ok=True)
os.makedirs("remarks", exist_ok=True)
os.makedirs("logo", exist_ok=True)
os.makedirs("models", exist_ok=True)

# --- SETUP VERIFICATION (Runs once on first boot) ---
# Checks DNN model, feature tests, and pipeline health.
# Skips automatically after first passing run (.setup_ok sentinel).
try:
    from setup_modules.setup_runner import run_setup
    run_setup(quick=True)  # quick=True skips full render test at startup
except Exception as _setup_err:
    logger.warning(f"⚠️ Setup verification skipped: {_setup_err}")


# Thread Pool for Heavy Tasks
executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)

# --- ADMIN CONFIGURATION ---
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# --- SMART LOGGING FILTER ---
class PollingFilter(logging.Filter):
    def filter(self, record):
        # Filter out "getUpdates" spam but allow other API calls
        return "getUpdates" not in record.getMessage()

# Apply filter to noisy libraries
# We allow INFO level but filter out the polling spam
for lib in ["httpx", "telegram", "apscheduler"]:
    l = logging.getLogger(lib)
    l.setLevel(logging.INFO)
    l.addFilter(PollingFilter())

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not found in .env! Exiting.")
    sys.exit(1)

# Global Activity State (Smart Idle Tracking)
PROCESSING_LOCK = asyncio.Lock()
QUEUE_SIZE = 0
QS_LOCK = threading.Lock()
background_tasks = set()
UPLOAD_SEMAPHORE = asyncio.Semaphore(1)

# TELEGRAM HOOK POOL (For High-Impact Variety & Trust)
HIGH_VOLTAGE_CTA_HOOKS = [
    "WARNING: This look is fatal. Handle with care. / Sambhal ke, yeh look tabahi hai. / सावधान: यह लुक कहर है।",

    "She didn't just walk, she arrived. Main Character Energy. / Bas entry li aur sab khatam. / उसने बस प्रवेश किया और सब जीत लिया।",

    "Absolutely unlawful levels of perfection. / Yeh look kanuni taur par illegal hona chahiye. / यह स्तर अवैध होना चाहिए।",

    "Obsessed is an understatement. This is art. / Sirf pasand nahi, nasha hai yeh. / यह सिर्फ पसंद नहीं, नशा है।",

    "The definition of 'Iconic' just got updated. / Isey kehte hain asli Icon. / इसे कहते हैं असली आइकन।",

    "Zero competition. She owns the lane. / Koi muqabla hi nahi. / कोई मुकाबला नहीं।",

    "Stop scrolling. Witness greatness. / Ruk jao. Isey dekho. / रुकें। इसे देखें।",

    "This fit is playing mind games. Unreal. / Dimag kharab karne wala look. / दिमाग खराब करने वाला लुक।",

    "Level 1000 Boss Vibes. Respect the drip. / Boss level swag. / बॉस लेवल स्वैग。",
    "Shop this look to master the trend! / Is look ko apnao aur trend set karo! / इस लुक को apnao और ट्रेंड सेट करें!",
    "Shop for the outfit and own the spotlight! / Is outfit ko kharidein aur chha jayein! / इस ऑउटफिट को खरीदें और छा जाएं!"
]


class GlobalState:
    is_busy = False
    last_activity = time.time()
    _lock = threading.Lock()
    
    @classmethod
    def set_busy(cls, busy: bool):
        with cls._lock:
            cls.is_busy = busy
            cls.last_activity = time.time()
    
    @classmethod
    def get_idleness(cls):
        with cls._lock:
            if cls.is_busy: return 0
            return time.time() - cls.last_activity

# Locking Mechanisms
file_locks = {}
fl_lock = threading.Lock()

@contextmanager
def file_lock(path_str):
    """
    Simple in-process file/path locking.
    """
    path_str = str(path_str)
    with fl_lock:
        if path_str not in file_locks:
            file_locks[path_str] = threading.Lock()
        lock = file_locks[path_str]
    
    acquired = lock.acquire(timeout=LOCK_WAIT_SECS)
    try:
        if not acquired:
            logger.warning(f"🔒 Could not acquire lock for {path_str} in {LOCK_WAIT_SECS}s. Proceeding anyway (Split Brain Risk).")
        yield acquired
    finally:
        if acquired:
            lock.release()

def atomic_write(target_path, content, mode="w", encoding="utf-8"):
    """
    Atomic write using tempfile and os.replace.
    Includes robustness for Windows file locking (WinError 5/32).
    """
    target_path = Path(target_path)
    # Write to a temp file in the same directory (to ensure same filesystem for atomic rename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(dir=target_path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, mode, encoding=encoding) as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception: pass # Some systems/pipes don't support fsync
            
        # Atomic Rename with Retry
        max_retries = 3
        last_error = None
        
        for i in range(max_retries):
            try:
                os.replace(temp_path, target_path)
                return # Success
            except OSError as e:
                last_error = e
                # WinError 5: Access denied, WinError 32: Used by process
                # If these occur, we wait and try again or use fallback
                if getattr(e, 'winerror', 0) in [5, 32]:
                    time.sleep(0.5)
                    # Force delete strategy for Windows if standard replace fails
                    try:
                        if os.path.exists(target_path):
                            os.remove(target_path)
                        os.rename(temp_path, target_path)
                        return
                    except Exception:
                        pass # Retry standard loop
                elif i == max_retries - 1:
                    raise e
                    
        # If loop finishes without success
        if last_error: raise last_error
        
    except Exception as e:
        logger.error(f"❌ Atomic write failed: {e}")
        try:
            if os.path.exists(temp_path): os.remove(temp_path)
        except: pass





# Presets Cache
CACHED_PRESETS = None
PRESETS_LOCK = threading.Lock()

def get_presets():
    global CACHED_PRESETS
    with PRESETS_LOCK:
        if CACHED_PRESETS is not None:
            return CACHED_PRESETS
        
        try:
            if os.path.exists("The_json/title_expansion_presets.json"):
                with open("The_json/title_expansion_presets.json", "r", encoding="utf-8") as f:
                    CACHED_PRESETS = json.load(f)
                logger.debug(f"✅ Loaded {len(CACHED_PRESETS)} title expansion presets.")
            else:
                CACHED_PRESETS = {}
        except Exception as e:
            logger.error(f"❌ Failed to load presets: {e}")
            return {}
            
        return CACHED_PRESETS


def sanitize_logs(text):
    """Redact sensitive keys from logs/debug artifacts."""
    if not isinstance(text, str): return text
    pattern = r'(?i)(token|key|secret|password|cookie|auth)\s*[:=]\s*["\']?([^"\',\s]+)["\']?'
    return re.sub(pattern, r'\1=***REDACTED***', text)

# Global State
user_sessions = {}
user_result_locks = {}
g_session_lock = threading.Lock()

def get_session_lock(user_id):
    with g_session_lock:
        if user_id not in user_result_locks:
            user_result_locks[user_id] = threading.RLock()
        return user_result_locks[user_id]

def save_session(user_id):
    """Persist individual session to disk."""
    if user_id in user_sessions:
        try:
            data = json.dumps(user_sessions[user_id], default=str)
            atomic_write(os.path.join(JOB_DIR, f"session_{user_id}.json"), data)
        except Exception as e:
            logger.error(f"Failed to persist session {user_id}: {e}")

def load_sessions():
    """Recover sessions from disk on startup."""
    try:
        now = time.time()
        count = 0
        for f in glob.glob(os.path.join(JOB_DIR, "session_*.json")):
            try:
                # Check age
                mtime = os.path.getmtime(f)
                if now - mtime > SESSION_TTL_SECS:
                    os.remove(f) # Expired
                    continue
                    
                with open(f, 'r') as fp:
                    data = json.load(fp)
                    # Extract user_id from filename
                    fname = os.path.basename(f)
                    uid = int(fname.replace("session_", "").replace(".json", ""))
                    user_sessions[uid] = data
                    count += 1
            except Exception: pass
        logger.info(f"🔄 Restored {count} active sessions from disk.")
    except Exception as e:
        logger.warning(f"Session recovery failed: {e}")

# Global State
COMPILATION_BATCH_SIZE = int(os.getenv("COMPILATION_BATCH_SIZE", "5"))

# ==================== AUTO-INSTALL & SETUP ====================

# ==================== AUTO-INSTALL & SETUP ====================

# Cached Hardware Capabilites
_hardware_cache = None

def detect_hardware_capabilities():
    """
    Detect hardware capabilities (Cached) via ComputeCaps.
    """
    global _hardware_cache
    if _hardware_cache: return _hardware_cache
    
    from Upscale_Modules.compute_caps import ComputeCaps
    caps = ComputeCaps.get()
    
    hardware_info = {
        'has_gpu': caps['has_cuda'] or caps['gpu_fast'], # Logical GPU presence
        'gpu_name': 'NVIDIA GPU' if caps['has_cuda'] else 'CPU',
        'vram_gb': caps['vram_gb'],
        'cuda_available': caps['has_cuda']
    }
    
    if hardware_info['has_gpu']:
         logger.info(f"🎮 GPU Detected via ComputeCaps: {hardware_info['gpu_name']} ({hardware_info['vram_gb']:.1f} GB VRAM)")
    else:
         logger.info("ℹ️ No GPU detected (ComputeCaps).")
         
    _hardware_cache = hardware_info
    return hardware_info

def resolve_compute_mode():
    """
    Resolve the final compute mode.
    Downgrades to CPU if VRAM is too low (< 6GB).
    """
    cpu_mode = os.getenv("CPU_MODE", "auto").lower()
    gpu_mode = os.getenv("GPU_MODE", "auto").lower()
    min_vram = int(os.getenv("MIN_VRAM_GB", "6"))
    
    # 1. Forced Modes
    if cpu_mode == "on":
        return "cpu"
    
    # 2. Hardware Capability Check
    hardware = detect_hardware_capabilities()
    
    # 3. GPU Logic
    if gpu_mode in ["on", "auto"]:
        if hardware['cuda_available']:
            # Check VRAM - Safe threshold for Heavy AI is 6GB
            if hardware['vram_gb'] < min_vram:
                if gpu_mode == "on":
                    logger.warning(f"⚠️ GPU_MODE=ON requested, but VRAM ({hardware['vram_gb']:.1f}GB) is below stable limit ({min_vram}GB).")
                    logger.info("⚡ Downgrading to CPU mode for stability (Heavy modules will be disabled).")
                else:
                    logger.info(f"⚙️ VRAM ({hardware['vram_gb']:.1f}GB) < {min_vram}GB. Selecting CPU mode.")
                return "cpu"
            
            logger.info(f"🤖 {'GPU_MODE=ON' if gpu_mode == 'on' else 'GPU_MODE=auto'}: Sufficient VRAM ({hardware['vram_gb']:.1f}GB). Selecting GPU.")
            return "gpu"
            
    # Default fallback
    return "cpu"

def check_and_update_env():
    """
    Auto-updates .env file with missing keys and smart defaults.
    """
    env_path = "Credentials/.env"
    if not os.path.exists(env_path):
        logger.warning("⚠️ .env file not found. Creating template...")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("""# ==================== CORE SETTINGS ====================
# REQUIRED: Get your bot token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# REQUIRED: Get your API key from https://aistudio.google.com/app/apikey
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

# ==================== PERFORMANCE ====================
# Modes: auto, on, off
CPU_MODE=auto
GPU_MODE=auto
REENCODE_PRESET=fast
REENCODE_CRF=25

# ==================== ENHANCEMENT ====================
ENHANCEMENT_LEVEL=medium
TARGET_RESOLUTION=1080:1920

# ==================== TRANSFORMATIVE FEATURES ====================
ADD_TEXT_OVERLAY=yes
TEXT_OVERLAY_TEXT=swargawasal
TEXT_OVERLAY_POSITION=bottom
TEXT_OVERLAY_STYLE=modern

ADD_COLOR_GRADING=yes
COLOR_FILTER=cinematic
COLOR_INTENSITY=0.5

ADD_SPEED_RAMPING=yes
SPEED_VARIATION=0.15

FORCE_AUDIO_REMIX=yes

# ==================== COMPILATION ====================
COMPILATION_BATCH_SIZE=6
SEND_TO_YOUTUBE=off
DEFAULT_HASHTAGS_SHORTS=#shorts #viral #trending
DEFAULT_HASHTAGS_COMPILATION=#compilation #funny #viral

# ==================== MONETIZATION ====================
LOS_POLLOS_YOUTUBE=no
LOS_POLLOS_TELEGRAM=yes

# ==================== TRANSITIONS ====================
TRANSITION_DURATION=0.5
TRANSITION_INTERVAL=5
GEMINI_TITLE_COMPLICATION=on
""")
        logger.info("✅ Created .env template. Please update TELEGRAM_BOT_TOKEN and GEMINI_API_KEY!")
        
    # Load current env content
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    updates = []
    
    # Define required keys and defaults (HARDENED)
    required_keys = {
        "CPU_MODE": "auto",
        "GPU_MODE": "auto",
        "ENHANCEMENT_LEVEL": "medium",
        "TRANSITION_INTERVAL": "5",
        "TRANSITION_DURATION": "0.5",
        "FORCE_AUDIO_REMIX": "yes",
        "ADD_TEXT_OVERLAY": "yes",
        "ADD_SPEED_RAMPING": "yes",
        "NET_RETRY_COUNT": "3",
        "NET_BACKOFF_BASE": "2.0",
        "LOCK_WAIT_SECS": "5",
        "TELEGRAM_MAX_UPLOAD_MB": "50",
        "SESSION_TTL_SECS": "86400",
        "TELEGRAM_MAX_UPLOAD_MB": "50",
        "GEMINI_TITLE_COMPLICATION": "on",
        "ENABLE_COMMUNITY_POST_COMPILATION": "yes",
        "ENABLE_COMMUNITY_POST_SHORTS": "no",
        "META_COMPILE_UPLOAD": "no",
        "LOS_POLLOS_YOUTUBE": "no",
        "LOS_POLLOS_TELEGRAM": "yes",
        "ENABLE_FASHION_SCOUT": "yes",
    }
    
    for key, default in required_keys.items():
        if key not in os.environ and f"{key}=" not in content:
            logger.info(f"➕ Auto-adding missing key: {key}={default}")
            updates.append(f"\n# Auto-added by Smart Installer\n{key}={default}")
            os.environ[key] = default 
            
    if updates:
        with open(env_path, "a", encoding="utf-8") as f:
            f.writelines(updates)
        logger.info(f"✅ Auto-added {len(updates)} missing keys to .env")
        
    # Expose resolved compute mode
    cm = resolve_compute_mode()
    os.environ["COMPUTE_MODE"] = cm
    logger.info(f"🚀 FINAL COMPUTE MODE: {cm.upper()}")
    
    # 3. Heal JSON State Files
    check_and_heal_json_files()

def check_and_heal_json_files():
    """
    Auto-Heals missing JSON state/config files with intelligent defaults.
    Analyzes user behavior patterns to populate initial data where applicable.
    """
    
    # 1. cleanup_state.json
    # Tracks last cleanup time. Default: Never run checking.
    p_cleanup = "The_json/cleanup_state.json"
    if not os.path.exists(p_cleanup):
        try:
             with open(p_cleanup, 'w') as f:
                 json.dump({"last_run": 0}, f)
             logger.info(f"🩹 Auto-Healed: {p_cleanup}")
        except: pass

    # 2. community_promo_state.json
    # Tracks community post rate limits and hashes.
    p_promo = "The_json/community_promo_state.json"
    if not os.path.exists(p_promo):
        try:
             with open(p_promo, 'w') as f:
                 json.dump({"last_run": 0, "posted_hashes": []}, f)
             logger.info(f"🩹 Auto-Healed: {p_promo}")
        except: pass

    # 3. policy_memory.json
    # Tracks strategy success rates. Default: Empty memory.
    p_policy = "The_json/policy_memory.json"
    if not os.path.exists(p_policy):
        try:
             with open(p_policy, 'w') as f:
                 json.dump({}, f)
             logger.info(f"🩹 Auto-Healed: {p_policy}")
        except: pass

    # 4. caption_prompt.json
    # Stores the "Safe Fallback" caption.
    # We populate this with a high-quality "Transformative" example.
    p_caption = "The_json/caption_prompt.json"
    if not os.path.exists(p_caption):
        try:
             default_data = {
                 "caption_final": "Mixing vintage denim with modern confidence for a timeless look",
                 "last_source": "auto_healer",
                 "timestamp": datetime.now().isoformat()
             }
             with open(p_caption, 'w') as f:
                 json.dump(default_data, f, indent=2)
             logger.info(f"🩹 Auto-Healed: {p_caption}")
        except: pass

    # 5. title_expansion_presets.json
    # Presets for interactive title composition.
    # We populate this with "Viral/Clickbait" patterns tailored for Shorts.
    p_titles = "The_json/title_expansion_presets.json"
    if not os.path.exists(p_titles):
        try:
             presets = {
                 "1": { "label": "Wait for it... 😱", "suffix": " #waitforit" },
                 "2": { "label": "You won't believe this!", "suffix": " #shocking" },
                 "3": { "label": "Satisfying 😌", "suffix": " #satisfying" },
                 "4": { "label": "Viral Moment", "suffix": " #viral" },
                 "5": { "label": "Must Watch", "suffix": " #mustwatch" },
                 "6": { "label": "Relatable 😂", "suffix": " #relatable" }
             }
             with open(p_titles, 'w', encoding='utf-8') as f:
                 json.dump(presets, f, indent=2, ensure_ascii=False)
             logger.info(f"🩹 Auto-Healed: {p_titles}")
        except: pass

# Conditional imports removed for lazy loading
# compute_mode = os.environ.get("COMPUTE_MODE", "cpu") - moved to resolve_compute_mode if needed

# ==================== UTILS ====================

UPLOAD_LOG = "Datasets_and_text_files/upload_log.csv"

def _ensure_log_header():
    if not os.path.exists(UPLOAD_LOG):
        with open(UPLOAD_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "video_id", "caption_style", "ypp_risk", "approved", "user_decision", "channel_name"])

def log_video(file_path: str, yt_link: str, title: str, style: str = "unknown", ypp_risk: str = "unknown", action: str = "approved", channel_name: str = "default_channel"):
    _ensure_log_header()
    # Atomic Append
    video_id = yt_link.split("/")[-1] if yt_link else "upload_failed"
    approved_bool = "true" if action == "approved" else "false"
    
    # Schema: timestamp, video_id, caption_style, ypp_risk, approved, user_decision, channel_name
    row = [datetime.utcnow().isoformat(), video_id, style, ypp_risk, approved_bool, action, channel_name]
    
    with file_lock(UPLOAD_LOG):
        with open(UPLOAD_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
    # Metadata JSON Sidecar
    try:
        final_meta = {
            "unique_id": video_id,
            "source_path": file_path,
            "youtube_link": yt_link,
            "title": title,
            "caption_style": style,
            "ypp_risk": ypp_risk,
            "user_decision": action,
            "channel_name": channel_name,
            "created_at": datetime.utcnow().isoformat(),
            "pipeline_version": "4.0-final-lock"
        }
        meta_path = str(file_path) + ".final.json"
        atomic_write(meta_path, json.dumps(final_meta))
    except Exception: pass

def total_uploads() -> int:
    if not os.path.exists(UPLOAD_LOG):
        return 0
    with open(UPLOAD_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        return max(0, len(rows) - 1)

def last_n_filepaths(n: int) -> list:
    """Get the last N video file paths from the upload log, filtered by recency."""
    if not os.path.exists(UPLOAD_LOG):
        return []
    
    with open(UPLOAD_LOG, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Filter by timestamp - only videos from last 24 hours
    from datetime import datetime, timedelta
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
    recent_rows = []
    for r in rows:
        try:
            timestamp_str = r.get("timestamp", "")
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if timestamp > cutoff_time:
                    recent_rows.append(r)
        except:
            # If timestamp parsing fails, skip this row
            continue
    
    # Get last N from recent rows
    subset = recent_rows[-n:]
    paths = [r.get("file_path") for r in subset if r.get("file_path")]
    
    # Return only paths that exist
    valid_paths = [p for p in paths if p and os.path.exists(p)]
    
    logger.info(f"📊 Found {len(valid_paths)} recent videos for compilation (last 24h)")
    return valid_paths

# Rate Limiting
class RateLimiter:
    def __init__(self, limit=10, period=60):
        self.limit = limit
        self.period = period
        self.users = {}
        self.lock = threading.Lock()
        
    def check(self, user_id):
        with self.lock:
            now = time.time()
            if user_id not in self.users:
                self.users[user_id] = []
            
            # Filter timestamps
            self.users[user_id] = [ts for ts in self.users[user_id] if now - ts < self.period]
            
            if len(self.users[user_id]) >= self.limit:
                return False
                
            self.users[user_id].append(now)
            return True

# Initialize Rate Limiter
user_limiter = RateLimiter(
    limit=int(os.getenv("USER_RATE_LIMIT_PER_MIN", "10")), 
    period=60
)

async def with_retry(func, *args, **kwargs):
    """
    Robust Retry Wrapper for Network Calls.
    """
    last_exception = None
    for attempt in range(NET_RETRY_COUNT):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            # Fail fast on 4xx (Client Error)
            msg = str(e)
            if "40" in msg or "400" in msg or "404" in msg or "403" in msg: 
                # Very rough heuristic, standard http libs usually provide status codes
                logger.error(f"❌ Non-Retriable Error: {e}")
                raise e
                
            wait = NET_BACKOFF_BASE ** attempt
            logger.warning(f"⚠️ Network Op Failed ({attempt+1}/{NET_RETRY_COUNT}): {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)
            
    logger.error(f"❌ Network Op Failed after {NET_RETRY_COUNT} attempts.")
    raise last_exception

async def safe_reply(update: Update, text: str, force: bool = False):
    """
    Robust message sender with improved error handling and force-bypass for rate limits.
    Handles CallbackQuery updates gracefully.
    """
    try:
        user_id = update.effective_user.id
        
        # Rate Limit Check (Unless Forced)
        if not force and not user_limiter.check(user_id):
            logger.warning(f"🛑 Rate limit hit for user {user_id}")
            return
            
        if text and len(text) > 4096:
            logger.warning(f"✂️ Message too long ({len(text)} chars). Truncating to 4096 for user {user_id}")
            text = text[:4093] + "..."

        for attempt in range(1, 4):
            try:
                # Handle CallbackQuery Logic (Where update.message might be None)
                target_msg = update.effective_message
                if not target_msg:
                    # Fallback for weird updates
                    if update.callback_query:
                         target_msg = update.callback_query.message
                
                if target_msg:
                    await target_msg.reply_text(
                        text,
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30
                    )
                else:
                    logger.warning("⚠️ safe_reply: No target message found to reply to.")
                    
                return
            except (NetworkError, TimedOut, httpx.HTTPError) as e:
                logger.warning(f"🛑 Reply failed (Attempt {attempt}/3): {e}. Retrying in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                # Catch BadRequest: "Message is not modified" or "Chat not found"
                # Do NOT retry fatal errors
                logger.warning(f"⚠️ safe_reply fatal error (No Retry): {e}")
                return
                
        logger.error("❌ Failed to send message after retries.")
        
    except Exception as e:
        logger.error(f"❌ safe_reply Crashed: {e}", exc_info=True)

class ProgressFile:
    def __init__(self, filename, logger_func):
        self._f = open(filename, 'rb')
        self._size = os.path.getsize(filename)
        self._seen = 0
        self._last_log = -10
        self._logger = logger_func
        self._path = filename

    def read(self, size=-1):
        chunk = self._f.read(size)
        if chunk:
            self._seen += len(chunk)
            if self._size > 0:
                pct = int((self._seen / self._size) * 100)
                if pct >= self._last_log + 10:
                    if pct < 100:
                        self._logger(f"📤 Uploading: {pct}% ({os.path.basename(self._path)})")
                        self._last_log = pct
        return chunk

    def seek(self, offset, whence=0): return self._f.seek(offset, whence)
    def tell(self): return self._f.tell()
    def close(self): return self._f.close()
    def fileno(self): return self._f.fileno()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

async def safe_video_reply(update: Update, video_path: str, caption: str = None, reply_markup=None):
    """
    Robust video sender with a 3-Tier Multi-Upload Strategy:
    Tier 1: Local API File:// URI (0s Delay)
    Tier 2: Compressed FFmpeg Proxy (~10s Delay)
    Tier 3: Full 46MB Upload (~5m Delay)
    """
    user_id = update.effective_user.id
    if not user_limiter.check(user_id): return

    try:
        f_size = os.path.getsize(video_path)
        if f_size == 0:
            logger.error(f"❌ Critical: Video file is 0 bytes! Cannot send. ({video_path})")
            await safe_reply(update, "❌ Processing Error: Resulting video is empty (0 bytes). Check logs.")
            return

        size_mb = f_size / (1024 * 1024)
        if size_mb > TELEGRAM_MAX_UPLOAD_MB:
             await safe_reply(update, f"⚠️ Video is {size_mb:.1f}MB (Max {TELEGRAM_MAX_UPLOAD_MB}MB). Link/File saved locally.")
             return
             
        # Character Limit Truncation (Telegram Limit: 1024 for captions)
        if caption and len(caption) > 1024:
            logger.warning(f"✂️ Caption too long ({len(caption)} chars). Truncating to 1024.")
            caption = caption[:1021] + "..."

    except Exception as e:
        logger.error(f"Failed size check: {e}")
        pass

    # --- TIER 1: LOCAL API SERVER (FILE:// URI) ---
    local_api = os.getenv("LOCAL_BOT_API_URL")
    if local_api:
        abs_path = f"file://{os.path.abspath(video_path)}"
        logger.info(f"⚡ Tier 1: Attempting Local API Upload (0s Delay) -> {abs_path}")
        try:
            if update.message:
                async with UPLOAD_SEMAPHORE:
                    await update.message.reply_video(
                        video=abs_path,
                        caption=caption,
                        read_timeout=120,
                        write_timeout=120,
                        reply_markup=reply_markup
                    )
            logger.info("✅ Tier 1 (Local API) Success!")
            return
        except Exception as e:
            logger.warning(f"⚠️ Tier 1 Local API Failed (falling back to Tier 2): {e}")
    
    # --- TIER 2: COMPRESSED PROXY GENERATION ---
    logger.info("⏱️ Tier 2: Generating Compressed Telegram Preview (~10s)...")
    import random
    import string
    import subprocess
    proxy_name = f"temp_{''.join(random.choices(string.ascii_letters + string.digits, k=6))}_proxy.mp4"
    proxy_path = os.path.join(os.path.dirname(video_path) or ".", proxy_name)
    
    tier2_success = False
    try:
        # Compress video for Telegram review (720p, veryfast preset, good CRF)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "scale=-2:720", # Scale down to 720p height for legible text
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            proxy_path
        ]
        # Run sync or async
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 0:
            logger.info(f"📤 Tier 2 Proxy Ready ({os.path.getsize(proxy_path)/1024/1024:.2f}MB). Uploading...")
            for attempt in range(1, 4):
                try:
                    if update.message:
                        async with UPLOAD_SEMAPHORE:
                            with open(proxy_path, 'rb') as f:
                                await update.message.reply_video(
                                    video=f, 
                                    caption=caption, 
                                    reply_markup=reply_markup,
                                    read_timeout=300, 
                                    write_timeout=300
                                )
                    tier2_success = True
                    logger.info("✅ Tier 2 Compressed Preview Uploaded!")
                    break
                except Exception as e:
                    logger.warning(f"🛑 Tier 2 Proxy send failed (Attempt {attempt}/3): {e}")
                    await asyncio.sleep(5)
    except Exception as e:
        logger.warning(f"⚠️ Tier 2 Proxy Generation Failed: {e}")
    finally:
        # Cleanup proxy file
        if os.path.exists(proxy_path):
             try: os.remove(proxy_path)
             except: pass
             
    if tier2_success:
        return

    # --- TIER 3: FULL FALLBACK UPLOAD ---
    logger.info(f"🐢 Tier 3: Falling back to FULL standard upload (This may take 5+ mins for {size_mb:.1f}MB)...")
    for attempt in range(1, 6):
        try:
            if update.message:
                async with UPLOAD_SEMAPHORE:
                    with open(video_path, 'rb') as f:
                        await update.message.reply_video(
                            video=f, 
                            caption=caption, 
                            read_timeout=None, 
                            write_timeout=None,
                            connect_timeout=600,
                            pool_timeout=600,
                            reply_markup=reply_markup
                        )
                logger.info(f"✅ Tier 3 Full Upload Success -> {os.path.basename(video_path)}")
            return
        except (NetworkError, TimedOut, httpx.HTTPError) as e:
            logger.warning(f"🛑 Video reply failed (Attempt {attempt}/5): {e}. Retrying in 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"❌ Video reply error: {e}")
            break
            
    logger.error("❌ Failed to send video after retries.")
    await safe_reply(update, "❌ Failed to send video due to network timeout.")

def _validate_url(url: str) -> bool:
    """Detects if a string contains an authorized URL anywhere."""
    if not url: return False
    # Robust URL detection regex
    url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
    matches = re.findall(url_pattern, url)
    if not matches: return False
    
    # Check if any matched URL is from allowed domains
    for m in matches:
        parsed = urlparse(m)
        domain = parsed.netloc.lower()
        if any(allowed in domain for allowed in ALLOWED_DOMAINS):
            return True
    return False

def _sanitize_title(title: str) -> str:
    # Allow spaces but remove other special characters
    clean = re.sub(r'[^\w\s-]', '', title)
    # clean = clean.replace(' ', '_')  <-- REMOVED: Keep spaces for YouTube title
    return clean[:100]  # Increased limit slightly for better titles

def _get_hashtags(text: str) -> str:
    link_count = len(re.findall(r'https?://', text))
    if link_count > 1:
        return os.getenv("DEFAULT_HASHTAGS_COMPILATION", "").strip()
    return os.getenv("DEFAULT_HASHTAGS_SHORTS", "").strip()



    return os.getenv("DEFAULT_HASHTAGS_SHORTS", "").strip()



# Helper for Incremental Filenaming
def _generate_next_filename(directory: str, prefix: str, extension: str = ".mp4") -> str:
    """
    Scans directory for files matching prefix_XX.mp4 and returns the next incremental filename.
    Format: prefix_01.mp4, prefix_02.mp4, etc.
    """
    try:
        if not os.path.exists(directory): return os.path.join(directory, f"{prefix}_01{extension}")
        
        # List all possible matches
        # We look for files starting with prefix
        candidates = glob.glob(os.path.join(directory, f"{prefix}_*{extension}"))
        
        max_idx = 0
        
        # Regex to extract the number at the end
        # We expect: prefix_(\d+).mp4
        # We must be careful not to match prefix_2025... as a huge number if the prefix matches partially.
        # So we ensure the prefix is followed by an UNDERSCORE and then DIGITS only.
        # But wait, our prefix might result in "compile_last_2" and we want "compile_last_2_01".
        # So pattern is: prefix + "_" + digits + extension
        
        pattern = re.compile(rf"^{re.escape(prefix)}_(\d+){re.escape(extension)}$")
        
        for f in candidates:
            fname = os.path.basename(f)
            match = pattern.match(fname)
            if match:
                try:
                    idx = int(match.group(1))
                    if idx > max_idx:
                        max_idx = idx
                except: pass
                
        # If no strict match found (e.g. only timestamped files exist), we start at 01.
        # Timestamped files (prefix_2025...) won't match the regex `_(\d+).mp4` easily 
        # unless user named it `compile_last_2_20251228`. 
        # But timestamp usually has time too: `20251228_123456`. That contains `_`, so `\d+` won't match it fully if strict anchor.
        
        return os.path.join(directory, f"{prefix}_{max_idx+1:02d}{extension}")
        
    except Exception as e:
        logger.error(f"Filename generation error: {e}")
        # Fallback to timestamp if logic fails
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return os.path.join(directory, f"{prefix}_{stamp}{extension}")


async def initiate_compilation_title_flow(update: Update, merged_path: str, n_videos: int, hashtags: str, base_title: str = None):
    """
    New Flow: 
    1. Check GEMINI_TITLE_COMPLICATION
    2. ON -> Try Gemini -> Finish
    3. FAIL/OFF -> Ask User (Mandatory) -> Wait
    """
    user_id = update.effective_user.id
    gemini_mode = os.getenv("GEMINI_TITLE_COMPLICATION", "on").lower()
    
    generated_title = None
    generated_desc = None
    
    # Defaults
    if not base_title:
        base_title = f"Compilation {n_videos} Videos"
    
    # 0. Check Sidecar (Primary: One-Request Strategy)
    json_path = os.path.splitext(merged_path)[0] + ".json"
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                sidecar_data = json.load(f)
                # Check for either editorial_title or brain_analysis[editorial_title]
                title = sidecar_data.get("editorial_title") or sidecar_data.get("brain_analysis", {}).get("editorial_title")
                desc = sidecar_data.get("brain_analysis", {}).get("final_caption")
                if title and len(title) > 5:
                    generated_title = title
                    generated_desc = desc
                    logger.info(f"✨ Using Brain-Generated Title from Sidecar: {generated_title}")
        except: pass
    
    if not generated_title and gemini_mode == "on":
        try:
             # Try smart generation via Brain if valid base context
             from Intelligence_Modules.monetization_brain import brain
             # Construct context for brain from base_title if it looks like a query
             context = base_title.replace("Compilation", "").replace("Videos", "").strip()
             if not context: context = "Influencer Fashion"
             
             logger.info(f"🧠 Generating Compilation Title via Brain: {context} (Clips: {n_videos})")
             smart = brain.generate_editorial_title(context, n_videos=n_videos)
             
             # Smart is now likely a tuple (title, desc) if updated
             if isinstance(smart, tuple):
                 title_cand, desc_cand = smart
             else:
                 title_cand, desc_cand = smart, None
                 
             if title_cand and title_cand != f"Compilation: {context}":
                 generated_title = title_cand
                 generated_desc = desc_cand
                 
        except Exception as e:
             logger.warning(f"Gemini Title Gen Failed: {e}")
    
    if generated_title:
        await safe_reply(update, f"✨ AI Generated Title: {generated_title}")
        await finish_compilation_upload(update, merged_path, generated_title, hashtags, n_videos=n_videos, description=generated_desc)
        return
        
    # --- FALLBACK: ASK USER (MANDATORY) ---
    presets_msg = ""
    try:
        presets = get_presets()
            
        if presets:
            msg_lines = [f"📌 Select title expansion for: '{base_title}' (optional):"]
            # Ensure sorted keys
            for k in sorted(presets.keys(), key=lambda x: int(x) if x.isdigit() else 99):
                v = presets[k]
                msg_lines.append(f"{k}️⃣ {v['label']}")
            msg_lines.append("\nReply with number or /skip")
            presets_msg = "\n".join(msg_lines)
    except Exception as e:
         logger.error(f"Failed to load presets: {e}")
         
    if presets_msg:
        # Save State
        with get_session_lock(user_id):
            user_sessions[user_id] = {
                'state': 'WAITING_FOR_COMPILATION_TITLE',
                'pending_compilation_path': merged_path,
                'pending_n_videos': n_videos,
                'pending_hashtags': hashtags,
                'pending_base_title': base_title 
            }
            save_session(user_id)
            
        await safe_reply(update, presets_msg)
    else:
        # No presets found? Fallback to generic
        await finish_compilation_upload(update, merged_path, base_title, hashtags, n_videos=n_videos)


async def finish_compilation_upload(update: Update, merged_path: str, title: str, hashtags: str, n_videos: int = 10, description: str = None):
    """
    Final step: Upload, Log, Reply.
    """
    # Explicitly log the final location for user clarity
    logger.info(f"💾 Compilation Saved Confirmation: {merged_path}")
    
    # Imports provided via Health_handlers portal
    
    # Check if we should send to YouTube or Telegram
    try:
        send_to_youtube = os.getenv("SEND_TO_YOUTUBE", "off").lower() in ["on", "yes", "true"]
        
        link = None
        yt_status_msg = "🚫 YouTube: Skipped"

        if send_to_youtube:
            await safe_reply(update, f"📤 Uploading compilation: '{title}'...")
            
            try:
                # 1. YouTube Upload
                link = await with_retry(
                    uploader.upload_to_youtube,
                    merged_path, 
                    hashtags=hashtags, 
                    title=title,
                    description=description
                )

                if link:
                    log_video(merged_path, link, title)
                    yt_status_msg = f"✅ YouTube: Uploaded! ({link})"
                    
                    # Reset/Clear user session if strictly compilation (optional, but good hygiene)
                    user_id = update.effective_user.id
                    with get_session_lock(user_id):
                            # Only clear if we were in the waiting state
                            if user_sessions.get(user_id, {}).get('state') == 'WAITING_FOR_COMPILATION_TITLE':
                                user_sessions.pop(user_id, None)
                                save_session(user_id)
                else:
                    yt_status_msg = "❌ YouTube: Failed."
            except Exception as e:
                 logger.error(f"YouTube Upload Failed: {e}")
                 yt_status_msg = f"❌ YouTube Error: {e}"
        else:
             await safe_reply(update, f"✅ Compilation saved locally (YouTube Skipped):\n`{merged_path}`")

        # 2. Meta Upload (Instagram + Facebook)
        # Independent of YouTube failure (as per requirement)
        # Imports provided via Health_handlers portal
        meta_results = {}
        if os.getenv("ENABLE_META_UPLOAD", "no").lower() in ["yes", "true", "on"] and os.getenv("META_COMPILE_UPLOAD", "no").lower() in ["yes", "true", "on"]:
                await safe_reply(update, "📤 Attempting Meta (Instagram/Facebook) Uploads...")
                # Use generated description or title for caption
                # For compilations, maybe use title + hashtags
                meta_caption = f"{title}\n\n{hashtags}"
                if description: meta_caption = f"{title}\n\n{description}\n\n{hashtags}"
                
                # --- FACEBOOK TITLE TRANSFORMATION ---
                fb_caption = meta_caption # Default fallback
                try:
                    # Load Mappings
                    fb_map_file = "The_json/title_expansion_fb.json"
                    presets_file = "The_json/title_expansion_presets.json"
                    
                    if os.path.exists(fb_map_file) and os.path.exists(presets_file):
                        with open(fb_map_file, "r", encoding="utf-8") as f: fb_presets = json.load(f)
                        with open(presets_file, "r", encoding="utf-8") as f: main_presets = json.load(f)
                        
                        # Find which preset was used in the title
                        found_key = None
                        for k, v in main_presets.items():
                            # Check if the Main Preset's Label is in the current title
                            # e.g. Title: "Disha Patani: Red Carpet Event" -> Label: "Red Carpet Event"
                            if v['label'] in title:
                                found_key = k
                                break
                        
                        if found_key and found_key in fb_presets:
                            # Map to FB Title
                            clean_fb_title = fb_presets[found_key]['label']
                            # Re-construct caption for FB: Clean Title + Hashtags (No verbose description)
                            fb_caption = f"{clean_fb_title}\n\n{hashtags}"
                            logger.info(f"📘 Facebook Title Swapped: '{title}' -> '{clean_fb_title}'")
                except Exception as e:
                    logger.warning(f"FB Title Mapping Failed: {e}")

                meta_results = await meta_uploader.AsyncMetaUploader.upload_to_meta(
                    merged_path, 
                    meta_caption,
                    upload_type=os.getenv("META_UPLOAD_TYPE", "Reels"),
                    facebook_caption=fb_caption
                )
        else:
                if os.getenv("ENABLE_META_UPLOAD", "no").lower() in ["yes", "true", "on"]:
                    logger.info("⏩ Meta Compilation Upload skipped (META_COMPILE_UPLOAD is OFF)")
                else:
                    logger.info("🚫 Meta Upload Disabled globally (ENABLE_META_UPLOAD is OFF)")
        
        # 3. Final Report
        report_lines = [f"🎉 Compilation Processing Complete!", ""]
        report_lines.append(yt_status_msg)
        
        if meta_results:
            # Instagram
            ig_res = meta_results.get("instagram", {"status": "skipped"})
            if isinstance(ig_res, str): ig_res = {"status": ig_res}
            ig_status = ig_res.get("status", "skipped")
            ig_link = ig_res.get("link", "")
            icon_ig = "✅" if ig_status == "success" else "❌" if "failed" in ig_status else "⏩"
            line_ig = f"{icon_ig} Instagram: {ig_status}"
            if ig_link: line_ig += f" ({ig_link})"
            report_lines.append(line_ig)
            
            # Facebook
            fb_res = meta_results.get("facebook", {"status": "skipped"})
            if isinstance(fb_res, str): fb_res = {"status": fb_res}
            fb_status = fb_res.get("status", "skipped")
            fb_link = fb_res.get("link", "")
            icon_fb = "✅" if fb_status == "success" else "❌" if "failed" in fb_status else "⏩"
            line_fb = f"{icon_fb} Facebook: {fb_status}"
            if fb_link: line_fb += f" ({fb_link})"
            report_lines.append(line_fb)
            
        await safe_reply(update, "\n".join(report_lines))

            
        # --- COMMUNITY PROMOTION ADD-ON ---
        if link and os.getenv("ENABLE_COMMUNITY_POST_COMPILATION", "yes").lower() == "yes":
            # Just REGISTER the link for future shorts. Do NOT post comment on the compilation itself.
            logger.info("💾 Registering Compilation Link for future cross-promotion...")
            community_promoter.promoter.register_compilation_url(link)
            
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        await safe_reply(update, f"❌ Pipeline failed: {e}")


# ==================== COMPILATION LOGIC ====================

def get_unique_processed_shorts(n=5):
    """
    Robustly find the last N processed videos for compilation.
    Checks 'Processed Shorts' directory.
    Renamed from 'last_n_filepaths' to avoid shadowing the CSV-based helper.
    """
    source_dir = "Processed Shorts"
    if not os.path.exists(source_dir):
        logger.warning(f"get_unique_processed_shorts: {source_dir} does not exist.")
        return []
        
    all_files = glob.glob(os.path.join(source_dir, "*.mp4"))
    # Filter out compilations AND invalid 0-byte files
    valid_files = [f for f in all_files 
                   if "compile" not in os.path.basename(f) 
                   and "compilation" not in os.path.basename(f)
                   and os.path.getsize(f) > 1024]
    
    # Sort by modification time (Newest -> Oldest)
    valid_files.sort(key=os.path.getmtime, reverse=True)
    
    logger.info(f"📊 Found {len(valid_files)} recent videos for compilation")
    return valid_files[:n]


async def maybe_compile_and_upload(update: Update):
    from compiler import compile_batch_with_transitions
    # Explicitly get portal modules to ensure visibility in async scope
    from Health_handlers import get_portal
    portal = get_portal()
    community_promoter = getattr(portal, "community_promoter", None)
    meta_uploader = getattr(portal, "meta_uploader", None)
    count = total_uploads()
    n = COMPILATION_BATCH_SIZE
    if n <= 0 or count == 0 or count % n != 0:
        return

    await safe_reply(update, f"⏳ Creating compilation of last {n} shorts...📦")
    files = get_unique_processed_shorts(n)
    if len(files) < n:
        await safe_reply(update, "⚠️ Not enough local files to compile. Skipping.")
        return

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_name = os.path.join(COMPILATIONS_DIR, f"compilation_{n}_{stamp}.mp4")
    await safe_reply(update, f"🔨 Merging {len(files)} videos now...🛸")

    try:
        await safe_reply(update, "✨ Running full AI pipeline for batch compilation…")

        # --- Single Stage: Batch Compile with Transitions ---
        # This replaces the old 2-stage process (raw merge -> enhance)
        # Now we normalize -> transition -> merge -> remix -> assemble in one go
        
        # Use Output Name directly (contains Path)
        merged = await asyncio.to_thread(
            compile_batch_with_transitions,
            files,
            output_name
        )
        
        if not merged or not os.path.exists(merged):
            await safe_reply(update, "❌ Failed to create compilation.")
            return

        # Prepare Metadata
        count = total_uploads()
        # Default Title (will be overridden by logic likely, but passed as backup or logic param)
        # Actually logic generates title. We just need hashtags.
        
        comp_hashtags = os.getenv("DEFAULT_HASHTAGS_COMPILATION", "").replace("#Shorts", "").replace("#shorts", "").strip()
        
        # Initiate New Flow
        await initiate_compilation_title_flow(update, merged, n, comp_hashtags)

    except Exception as e:
        logger.exception("Compilation/upload failed: %s", e)
        await safe_reply(update, f"❌ Compilation failed: {e}")

async def compile_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global QUEUE_SIZE
    user_id = update.effective_user.id
    
    # --- QUEUE HANDLING ---
    is_queued = False
    with QS_LOCK:
        if PROCESSING_LOCK.locked():
            QUEUE_SIZE += 1
            is_queued = True
            pos = QUEUE_SIZE
    
    if is_queued:
        await safe_reply(update, f"⏳ System Busy. Your compilation request is at position #{pos} in the queue...")

    async with PROCESSING_LOCK:
        if is_queued:
            with QS_LOCK: QUEUE_SIZE = max(0, QUEUE_SIZE - 1)
        
        # Original Logic...
    """
    Compiles the last N downloaded videos from the downloads/ folder.
    Usage: 
      /compile_last <number> (default 6)
      /compile_last <number> <name_prefix> (e.g. /compile_last 6 reem hot)
    """
    try:
        from compiler import compile_batch_with_transitions
        # Imports provided via Health_handlers portal
        # 1. Parse arguments
        n = 6
        name_query = None
        
        if context.args:
            try:
                n = int(context.args[0])
            except ValueError:
                await safe_reply(update, "⚠️ Invalid number. Using default: 6")
            
            if len(context.args) > 1:
                name_query = " ".join(context.args[1:])
        
        if n <= 1:
            await safe_reply(update, "⚠️ Please specify at least 2 videos.")
            return

        # Source from Processed Shorts
        source_dir = "Processed Shorts"
        if not os.path.exists(source_dir):
             await safe_reply(update, f"❌ Directory '{source_dir}' not found.")
             return

        selected_files = []
        
        if name_query:
            # --- NAMED SORT COMPILATION ---
            # User wants specific named clips (e.g. reem_hot_1, reem_hot_2...)
            clean_query = _sanitize_title(name_query) # Use same sanitizer as downloader/main
            clean_query = clean_query.replace(' ', '_') # Ensure underscores if sanitizer kept spaces
            
            logger.info(f"🔍 Searching for clips matching: {clean_query}")
            await safe_reply(update, f"🔍 Searching for {n} clips matching '{clean_query}'...")
            
            # Find all files matching the pattern
            # We look for: base_name.mp4, base_name_1.mp4, base_name_2.mp4...
            # Or just any file starting with base_name
            all_files = glob.glob(os.path.join(source_dir, "*.mp4"))
            
            # Filter by name prefix
            matching_files = []
            for f in all_files:
                fname = os.path.basename(f)
                if fname.startswith(clean_query):
                    matching_files.append(f)
            
            # Sort them naturally (reem_hot.mp4, reem_hot_1.mp4, reem_hot_2.mp4...)
            # We need smart sorting to handle _1, _2, _10 correctly
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
                
            matching_files.sort(key=lambda f: natural_keys(os.path.basename(f)))
            
            if len(matching_files) < n:
                await safe_reply(update, f"⚠️ Not enough clips found matching '{clean_query}'. Found {len(matching_files)}, need {n}. (Debug: Query='{clean_query}')")
                return
                
            # Take the LAST N (Highest Numbers / Newest in Sequence)
            # e.g. If we have 1..45, take 38..45
            selected_files = matching_files[-n:]
            
        else:
            # --- DEFAULT: TIME BASED ---
            all_files = glob.glob(os.path.join(source_dir, "*.mp4"))
            files = [f for f in all_files if not os.path.basename(f).startswith("compile_")]
            
            if not files:
                await safe_reply(update, f"❌ No processed videos found in '{source_dir}' folder.")
                return
    
            # Sort by modification time (newest first)
            files.sort(key=os.path.getmtime, reverse=True)
            
            # Take top N
            selected_files = files[:n]
        
        if len(selected_files) < 2:
            await safe_reply(update, f"⚠️ Found {len(selected_files)} videos, but need at least 2 to compile.")
            return

        # Log selected files for user confirmation
        msg = f"✅ Found {len(selected_files)} videos:\n"
        for f in selected_files:
            msg += f"- {os.path.basename(f)}\n"
        await safe_reply(update, msg)

        # 4. Compile
        if name_query:
            prefix = f"compile_last_{n}_{clean_query}"
        else:
            prefix = f"compile_last_{n}"
            
        output_filename = _generate_next_filename(COMPILATIONS_DIR, prefix, ".mp4")
        
        await safe_reply(update, "🚀 Starting batch compilation with transitions...")
        GlobalState.set_busy(True)
        merged = await asyncio.to_thread(
            compile_batch_with_transitions,
            selected_files,
            output_filename
        )
        GlobalState.set_busy(False)

        if not merged or not os.path.exists(merged):
            await safe_reply(update, "❌ Compilation failed (check logs).")
            return

        # Prepare Hashtags
        comp_hashtags = os.getenv("DEFAULT_HASHTAGS_COMPILATION", "#compilation #viral").replace("#Shorts", "").strip()

        # If user provided a name query, use smart logic
        if name_query:
            # Smart Title Generation via Brain
            # Logic: Try Brain -> If Fail -> Initiate Title Flow (Fallback)
            
            try:
                from Intelligence_Modules.monetization_brain import brain
                logger.info(f"🧠 Generating Smart Title for: {name_query} (Clips: {len(selected_files)})")
                smart_res = brain.generate_editorial_title(name_query, n_videos=len(selected_files))
                
                # Unpack tuple
                if isinstance(smart_res, tuple):
                    smart_title, smart_desc = smart_res
                else:
                    smart_title, smart_desc = smart_res, None
                
                # Check for Failure
                is_fallback = (smart_title == f"Compilation: {name_query}")
                
                if smart_title and not is_fallback and len(smart_title) > 5:
                    final_title = smart_title
                    await finish_compilation_upload(update, merged, final_title, comp_hashtags, description=smart_desc)
                else:
                    # Smart Gen Failed -> Ask User
                    await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags, base_title=name_query)
                    
            except Exception as e:
                logger.warning(f"⚠️ Smart Title Generation Failed: {e}")
                await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags, base_title=name_query)
                
        else:
            # New Flow (No base name provided)
            await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags)

    except Exception as e:
        logger.exception(f"/compile_last failed: {e}")
        await safe_reply(update, f"❌ Error: {e}")

async def register_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manually register a compilation URL for cross-promotion.
    Usage: /register_promo <url>
    """
    try:
        if not context.args:
            await safe_reply(update, "⚠️ Usage: /register_promo <youtube_url>")
            return
            
        url = context.args[0]
        # Explicitly get portal modules
        from Health_handlers import get_portal
        portal = get_portal()
        community_promoter = getattr(portal, "community_promoter", None)
        
        if community_promoter:
            community_promoter.promoter.register_compilation_url(url)
        await safe_reply(update, f"✅ Promotion Link Registered!\nTarget: {url}\nFuture Shorts will link to this.")
        
    except Exception as e:
        logger.error(f"Register Promo Failed: {e}")
        await safe_reply(update, f"❌ Error: {e}")

async def compile_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global QUEUE_SIZE
    user_id = update.effective_user.id
    
    # --- QUEUE HANDLING ---
    is_queued = False
    with QS_LOCK:
        if PROCESSING_LOCK.locked():
            QUEUE_SIZE += 1
            is_queued = True
            pos = QUEUE_SIZE
    
    if is_queued:
        await safe_reply(update, f"⏳ System Busy. Your compilation request is at position #{pos} in the queue...")

    async with PROCESSING_LOCK:
        if is_queued:
            with QS_LOCK: QUEUE_SIZE = max(0, QUEUE_SIZE - 1)
        
        # Original Logic...
    """
    Compiles the FIRST N downloaded videos from the downloads/ folder.
    Usage: 
      /compile_first <number> (default 6)
      /compile_first <number> <name_prefix> (e.g. /compile_first 6 reem hot)
    """
    try:
        from compiler import compile_batch_with_transitions
        # Imports provided via Health_handlers portal
        # 1. Parse arguments
        n = 6
        name_query = None
        
        if context.args:
            try:
                n = int(context.args[0])
            except ValueError:
                await safe_reply(update, "⚠️ Invalid number. Using default: 6")
            
            if len(context.args) > 1:
                name_query = " ".join(context.args[1:])
        
        if n <= 1:
            await safe_reply(update, "⚠️ Please specify at least 2 videos.")
            return

        # Source from Processed Shorts
        source_dir = "Processed Shorts"
        if not os.path.exists(source_dir):
             await safe_reply(update, f"❌ Directory '{source_dir}' not found.")
             return

        selected_files = []
        
        if name_query:
            # --- NAMED SORT COMPILATION ---
            clean_query = _sanitize_title(name_query)
            clean_query = clean_query.replace(' ', '_')
            
            logger.info(f"🔍 Searching for clips matching: {clean_query}")
            await safe_reply(update, f"🔍 Searching for {n} clips matching '{clean_query}'...")
            
            all_files = glob.glob(os.path.join(source_dir, "*.mp4"))
            
            # Filter by name prefix
            matching_files = []
            for f in all_files:
                fname = os.path.basename(f)
                if fname.startswith(clean_query):
                    matching_files.append(f)
            
            # Sort them naturally (1, 2, 3...)
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
                
            matching_files.sort(key=lambda f: natural_keys(os.path.basename(f)))
            
            if len(matching_files) < n:
                await safe_reply(update, f"⚠️ Not enough clips found matching '{clean_query}'. Found {len(matching_files)}, need {n}.")
                return
                
            # Take the FIRST N (1..N)
            selected_files = matching_files[:n]
            
        else:
            # --- DEFAULT: TIME BASED ---
            all_files = glob.glob(os.path.join(source_dir, "*.mp4"))
            files = [f for f in all_files if not os.path.basename(f).startswith("compile_")]
            
            if not files:
                await safe_reply(update, f"❌ No processed videos found in '{source_dir}' folder.")
                return
    
            # Sort by modification time (OLDEST first)
            files.sort(key=os.path.getmtime, reverse=False)
            
            # Take top N (which are now the oldest)
            selected_files = files[:n]
        
        if len(selected_files) < 2:
            await safe_reply(update, f"⚠️ Found {len(selected_files)} videos, but need at least 2 to compile.")
            return

        # Log selected files for user confirmation
        msg = f"✅ Found {len(selected_files)} videos:\n"
        for f in selected_files:
            msg += f"- {os.path.basename(f)}\n"
        await safe_reply(update, msg)

        # 4. Compile
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(COMPILATIONS_DIR, f"compile_first_{n}_{stamp}.mp4")
        if name_query:
            output_filename = os.path.join(COMPILATIONS_DIR, f"compile_{clean_query}_first_{n}_{stamp}.mp4")
        
        await safe_reply(update, "🚀 Starting batch compilation with transitions...")
        GlobalState.set_busy(True)
        merged = await asyncio.to_thread(
            compile_batch_with_transitions,
            selected_files,
            output_filename
        )
        GlobalState.set_busy(False)

        if not merged or not os.path.exists(merged):
            await safe_reply(update, "❌ Compilation failed (check logs).")
            return

        # Prepare Hashtags
        comp_hashtags = os.getenv("DEFAULT_HASHTAGS_COMPILATION", "#compilation #viral").replace("#Shorts", "").strip()

        if name_query:
            # Smart Title Generation via Brain
            # Logic: Try Brain -> If Fail -> Initiate Title Flow (Fallback)
            
            try:
                from Intelligence_Modules.monetization_brain import brain
                logger.info(f"🧠 Generating Smart Title for: {name_query} (Clips: {len(selected_files)})")
                smart_res = brain.generate_editorial_title(name_query, n_videos=len(selected_files))
                
                # Unpack tuple
                if isinstance(smart_res, tuple):
                    smart_title, smart_desc = smart_res
                else:
                    smart_title, smart_desc = smart_res, None
                
                # Check for Failure
                is_fallback = (smart_title == f"Compilation: {name_query}")
                
                if smart_title and not is_fallback and len(smart_title) > 5:
                    final_title = smart_title
                    await finish_compilation_upload(update, merged, final_title, comp_hashtags, description=smart_desc)
                else:
                    # Fail -> Fallback to User
                     await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags, base_title=name_query)
                     
            except Exception as e:
                logger.warning(f"⚠️ Smart Title Generation Failed: {e}")
                await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags, base_title=name_query)
                
        else:
            # New Flow
            await initiate_compilation_title_flow(update, merged, len(selected_files), comp_hashtags)

    except Exception as e:
        logger.exception(f"/compile_first failed: {e}")
        await safe_reply(update, f"❌ Error: {e}")

# ==================== HANDLERS ====================

async def cmd_compile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /compile <EntityName> <Count>
    Generates a Narrative Compilation for the given entity.
    """
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return

    args = context.args
    if len(args) < 2:
        await safe_reply(update, "Usage: /compile <Name> <Count>\nExample: /compile Avneet 5")
        return

    entity_name = args[0]
    try:
        count = int(args[1])
    except ValueError:
        await safe_reply(update, "❌ Count must be a number.")
        return

    # Check Portal Access
    if not hasattr(portal, 'narrative_brain'):
        await safe_reply(update, "❌ Narrative Brain is NOT enabled in Health_handlers.")
        return

    await safe_reply(update, f"🎬 **Director Mode Active**\n\n🔎 Scouting assets for '{entity_name}' (Limit: {count})...")
    # 1. Asset Discovery
    try:
        assets = await asyncio.to_thread(
            portal.narrative_brain.director.find_associated_assets,
            entity_name, 
            limit=count
        )
    except Exception as e:
        await safe_reply(update, f"❌ Discovery Failed: {e}")
        return

    if not assets:
        await safe_reply(update, f"⚠️ No assets found for '{entity_name}'.\nEnsure you have 'Processed Shorts/{entity_name}*.json' and matching thumbnails.")
        return
    
    if len(assets) < 2:
        await safe_reply(update, f"⚠️ Not enough clips found ({len(assets)}). Need at least 2 for a compilation.")
        return

    await safe_reply(update, f"✅ Found {len(assets)} clips. Generating Script & Voiceover... 🎙️")

    # 2. Script & Voiceover
    try:
        # Generate Script (Narrative Brain)
        script = await asyncio.to_thread(
            portal.narrative_brain.director.generate_compilation_script, 
            assets
        )
        
        if not script or len(script) < 50:
             await safe_reply(update, "❌ Script generation failed or too short.")
             return

        # Generate Voiceover
        job_id = int(time.time())
        vo_path = os.path.join("temp", f"narration_{job_id}.mp3")
        
        vo_success = await asyncio.to_thread(
            portal.voiceover.generate_long_form_narration,
            script,
            vo_path
        )
        
        if not vo_success:
             await safe_reply(update, "❌ Voiceover generation failed.")
             return

    except Exception as e:
         await safe_reply(update, f"❌ Narrative/VO Failed: {e}")
         return

    # 3. Assembly
    await safe_reply(update, f"🎞️ Assembling Video (This may take a minute commit to visual/audio sync)...")

    # Pick BGM
    import glob
    import random
    bgm_files = glob.glob("music/*.mp3")
    bgm_path = random.choice(bgm_files) if bgm_files else None
    
    if not bgm_path:
        await safe_reply(update, "⚠️ No BGM found in music/ folder. Video will be silent music.")
        # We can implement a silence fallback or just fail. 
        # assemble_narrated_compilation requires BGM.
        # Let's create a silent mp3? No, fail is better.
        await safe_reply(update, "❌ BGM Missing. Please add mp3s to music/ folder.")
        return

    output_filename = f"Compilation_{entity_name}_{job_id}.mp4"
    output_path = os.path.join(COMPILATIONS_DIR, output_filename)
    
    video_paths = [a['video_path'] for a in assets if os.path.exists(a.get('video_path', ''))]
    
    if len(video_paths) < 2:
         await safe_reply(update, "❌ Video paths missing from metadata assets.")
         return

    success = await asyncio.to_thread(
        compiler.assemble_narrated_compilation,
        video_paths,
        vo_path,
        bgm_path,
        output_path
    )
    
    if success:
         await safe_reply(update, f"✅ **Compilation Ready!**\n\n📂 {output_filename}\n📝 Script Length: {len(script)} chars")
         
         # Send File
         with open(output_path, 'rb') as f:
             await context.bot.send_video(
                 chat_id=update.effective_chat.id,
                 video=f,
                 caption=f"🎬 **{entity_name} Compilation**\n\n✨ {len(assets)} Clips\n🎙️ AI Narration",
                 read_timeout=600, 
                 write_timeout=600,
                 pool_timeout=600
             )
    else:
         await safe_reply(update, "❌ Compilation Assembly Failed.")

async def cmd_versus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /versus <EntityA> <EntityB>
    Generates a high-stakes juxtaposition video between two entities.
    """
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        return

    args = context.args
    if len(args) < 2:
        await safe_reply(update, "Usage: /versus <NameA> <NameB>\nExample: /versus Avneet Disha")
        return

    name_a = args[0]
    name_b = args[1]

    # Check Portal Access for Narrative Brain (Search)
    if not hasattr(portal, 'narrative_brain'):
        await safe_reply(update, "❌ Narrative Brain is NOT enabled.")
        return

    await safe_reply(update, f"⚔️ **Versus Mode Active**\n\n🔎 Scouting assets for '{name_a}' vs '{name_b}'...")

    try:
        # 1. Scouting Clips
        from Intelligence_Modules.narrative_brain import director
        assets_a = await asyncio.to_thread(director.find_associated_assets, name_a, limit=5)
        assets_b = await asyncio.to_thread(director.find_associated_assets, name_b, limit=5)

        if not assets_a or not assets_b:
            await safe_reply(update, f"❌ Could not find enough assets for one or both entities.\nFound {len(assets_a)} for {name_a}, {len(assets_b)} for {name_b}.")
            return

        # Pick representative clips
        clip_a = assets_a[0]["video_path"]
        clip_b = assets_b[0]["video_path"]

        if not os.path.exists(clip_a) or not os.path.exists(clip_b):
            await safe_reply(update, "❌ One of the source videos is missing from disk.")
            return

        # 2. Orchestrate Compilation
        from Compiler_Modules import orchestrator
        job_id = f"vs_{uuid.uuid4().hex[:6]}"
        output_path = os.path.join(COMPILATIONS_DIR, f"versus_{name_a}_{name_b}_{job_id}.mp4")

        await safe_reply(update, "🧠 [Synthetic Newsroom] Comparing styles and rendering juxtaposition...")
        
        success, report = await asyncio.to_thread(
            orchestrator.compile_juxtaposition,
            job_id,
            clip_a,
            clip_b,
            output_path,
            title=f"{name_a} vs {name_b}"
        )

        if success:
            script = report.get("script", "")
            cta = report.get("cta", "")
            caption = f"🏆 {name_a} vs {name_b}\n\n🎙️ {script}\n\n🔗 {cta}\n\n#versus #fashion #amtce"
            
            await safe_video_reply(update, output_path, caption=caption)
        else:
            await safe_reply(update, f"❌ Versus Render Failed: {report.get('error', 'Unknown Error')}")

    except Exception as e:
        logger.error(f"Versus Operation Failed: {e}", exc_info=True)
        await safe_reply(update, f"❌ Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "❓ Please send an Instagram reel or YouTube link to begin.")

async def getbatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, f"Current compilation batch size: {COMPILATION_BATCH_SIZE}")

async def setbatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COMPILATION_BATCH_SIZE
    try:
        if not context.args:
            await safe_reply(update, "Usage: /setbatch <number>")
            return
        n = int(context.args[0])
        if n <= 0:
            await safe_reply(update, "Please provide a positive integer.")
            return
        COMPILATION_BATCH_SIZE = n
        await safe_reply(update, f"✅ Compilation batch size set to {n}.")
    except Exception:
        await safe_reply(update, "Usage: /setbatch <number>")

async def handle_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles direct video file uploads (Video or Document).
    """
    logger.info(f"📨 Handle attachment triggered! Message ID: {update.message.message_id}")
    
    # Re-verify critical imports from portal just in case
    from Health_handlers import get_portal
    portal = get_portal()
    if not portal:
        logger.error("❌ Critical: Portal failed to load in handle_attachment")
        await safe_reply(update, "❌ System Error: Module Portal Failed.")
        return

    load_dotenv(override=True)
    
    user_id = update.effective_user.id
    message = update.message
    
    # Identify attachment
    attachment = message.video or message.document
    if not attachment:
        return # Should be filtered out by handlers but safe check
        
    # Filter non-video documents if needed
    if message.document:
        mime = getattr(attachment, 'mime_type', '')
        if not mime or not mime.startswith('video/'):
            await safe_reply(update, "⚠️ Document is not a recognized video format.")
            return

    file_name = getattr(attachment, 'file_name', None) or f"upload_{int(time.time())}.mp4"
    
    # Check size (Telegram Bot API limit is 20MB for download, Local API is unlimited, MTProto is 2GB)
    file_size = getattr(attachment, 'file_size', None) or 0
    limit_mb = int(os.getenv("TELEGRAM_MAX_UPLOAD_MB", "50"))
    if file_size > limit_mb * 1024 * 1024:
         await safe_reply(update, f"⚠️ File is too large ({file_size/1024/1024:.1f}MB). Max: {limit_mb}MB.")
         return

    await safe_reply(update, "📥 Receiving video file...")
    
    try:
        new_file = await attachment.get_file()
        logger.debug(f"[Step 1] File object retrieved: {new_file.file_id}")
        
        # Sanitize filename
        clean_name = _sanitize_title(file_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join("downloads", f"{clean_name}_{timestamp}.mp4")
        logger.debug(f"[Step 2] Save path generated: {save_path}")

        # [ADAPTIVE] Momentum Throttling Check
        # [ADAPTIVE v3] Safe Mode Constraints & Throttling
        _ai = getattr(portal, 'adaptive_intelligence', None)
        _ai_brain = getattr(_ai, 'brain', None) if _ai else None
        if _ai_brain:
            constraints = _ai_brain.get_execution_constraints()
            # 1. Check if allowed at all
            if constraints.get("upload_delay", 0) > 3000: # Level 3 (3600s)
                # Soft Reject in Survival Mode
                await safe_reply(update, "🛡️ **Bio-Defense Active**\nSystem is in Deep Healing Cycle. Uploads paused for channel protection.\nTry again in ~1 hour.")
                return

            # 2. Check Momentum (using v3 constraint logic)
            # We can still use the helper, but let's respect the dynamic delay
            allowed, wait_time = _ai_brain.check_momentum(user_id)
            if not allowed:
                 # Override wait_time if Safe Level demands higher
                 required_delay = constraints.get("upload_delay", 0)
                 final_wait = max(wait_time, required_delay)
                 await safe_reply(update, f"⏳ **Adaptive Pacing**\nPlease wait {final_wait}s to match current safe levels.")
                 return
        
        # Download
        logger.debug("[Step 3] Starting download...")
        await new_file.download_to_drive(save_path)
        logger.info("[Step 4] Download completed!")

        # [ADAPTIVE] Risk Scoring Check
        if hasattr(portal, 'risk_engine'):
            risk_score, details = portal.risk_engine.RiskEngine.calculate_weighted_risk(save_path)
            if risk_score > 80: # Critical Risk Threshold
                os.remove(save_path)
                await safe_reply(update, f"🚫 **File Rejected (Risk Score: {risk_score})**\nReason: High Entropy/Low Quality.\nDetails: {details}")
                return
            logger.info(f"🛡️ Adaptive Risk Score: {risk_score} (Details: {details})")

        
        # Setup Session for Title Input (Unified Flow)
        logger.info(f"💾 Setting up session for User {user_id} -> WAITING_FOR_TITLE")
        with get_session_lock(user_id):
             user_sessions[user_id] = {
                 'state': 'WAITING_FOR_TITLE',
                 'pending_local_path': str(save_path),
                 'pending_url': None # Explicitly clear URL
             }
             save_session(user_id)
        
        # Ask for Title
        default_hashtags = os.getenv("DEFAULT_HASHTAGS_SHORTS", "#shorts")
        logger.info(f"📤 Sending Title Prompt to User {user_id}")
        await safe_reply(update, f"✅ File Received!\n\n📌 Hashtags:\n{default_hashtags}\n\n✏️ Now send the title to start processing.", force=True)

    except Exception as e:
        logger.error(f"Attachment handler failed: {e}", exc_info=True)
        
        # Smart Error Handling for Large Files
        if "File is too big" in str(e):
             await safe_reply(update, 
                 "⚠️ **Telegram API Limit Reached (20MB)**\n"
                 "Since I am running locally alongside your files, simply **Reply with the File Path** instead!\n\n"
                 "Example:\n"
                 "`D:\\Videos\\my_clip.mp4`"
             )
        else:
             await safe_reply(update, f"❌ Error handling file: {e}")
             
        GlobalState.set_busy(False)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Explicitly get downloader and quality_orchestrator from portal to ensure visibility in async scope
    from Health_handlers import get_portal
    portal = get_portal()
    downloader = getattr(portal, "downloader", None)
    quality_orchestrator = getattr(portal, "quality_orchestrator", None)
    monetization_brain = getattr(portal, "monetization_brain", None)
    narrative_brain = getattr(portal, "narrative_brain", None)
    
    load_dotenv(override=True)
    send_to_youtube = os.getenv("SEND_TO_YOUTUBE", "off").lower() in ["on", "yes", "true"]
    
    text = update.message.text.strip()
    user_id = update.effective_user.id
    with get_session_lock(user_id):
        session = user_sessions.get(user_id, {})
        state = session.get('state')

    # Case 1: New URL
    if _validate_url(text):
        # Store URL and wait for title
        with get_session_lock(user_id):
            user_sessions[user_id] = {
                'state': 'WAITING_FOR_TITLE',
                'pending_url': text
            }
            save_session(user_id)
        
        default_hashtags = os.getenv("DEFAULT_HASHTAGS_SHORTS", "#shorts")
        
        await safe_reply(update, f"✅ Got the link!\n\n📌 Hashtags:\n{default_hashtags}\n\n✏️ Now send the title.")
        return

    # Case 2: Waiting for Title (Prioritize over local file check)
    if state == 'WAITING_FOR_TITLE':
        pending_url = session.get('pending_url')
        pending_local_path = session.get('pending_local_path')
        
        if not pending_url and not pending_local_path:
            await safe_reply(update, "❌ Error: No pending upload found. Please start over.")
            return
            
        # HARDENING: Reject if text is a URL (Reset state for new URL)
        if _validate_url(text) or text.lower().startswith("http"):
             with get_session_lock(user_id):
                 user_sessions[user_id] = {
                     'state': 'WAITING_FOR_TITLE',
                     'pending_url': text,
                     'pending_local_path': None
                 }
                 save_session(user_id)
             await safe_reply(update, "🔄 New link received. Please send the title for THIS one.")
             return

        # Case 1.5: Local File Path (Large File Bypass - Only if NOT already waiting for title)
        # We handle this as a 'Reset' if it looks like a real path, but prioritize title.
        # To avoid title collision (like user sending "my_video" which exists), 
        # we check if it has a video extension.
        possible_path = text.strip('"').strip("'") # Remove quotes if user added them
        looks_like_path = os.path.exists(possible_path) and os.path.isfile(possible_path) and any(possible_path.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.mov', '.avi'])
        
        if looks_like_path:
             # User sent a file path instead of a title - Reset!
             file_name = os.path.basename(possible_path)
             file_size = os.path.getsize(possible_path)
             await safe_reply(update, f"📂 New Local File detected: `{file_name}`. Switching source...")
             
             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
             clean_name = _sanitize_title(file_name)
             save_path = os.path.join("downloads", f"local_{clean_name}_{timestamp}.mp4")
             try:
                 shutil.copy2(possible_path, save_path)
             except Exception as e:
                 await safe_reply(update, f"❌ Failed to copy local file: {e}")
                 return

             with get_session_lock(user_id):
                 user_sessions[user_id] = {
                     'state': 'WAITING_FOR_TITLE',
                     'pending_local_path': str(save_path),
                     'pending_url': None
                 }
                 save_session(user_id)
             await safe_reply(update, f"✅ New File Staged!\n\n✏️ Now send the title to start processing.")
             return

        custom_title = text
        
        # --- SYSTEM HEALTH GUARD ---
        h_verdict = check_health()
        if not h_verdict["safe"]:
             await safe_reply(update, f"⚠️ SYSTEM PROTECTION ACTIVE:\n{h_verdict['summary']}\n\nProcessing paused for safety.")
             return
             
        await safe_reply(update, f"✅ Title set: '{custom_title}'")
        
        # --- QUEUE HANDLING ---
        global QUEUE_SIZE
        is_queued = False
        with QS_LOCK:
            if PROCESSING_LOCK.locked():
                QUEUE_SIZE += 1
                is_queued = True
                pos = QUEUE_SIZE
        
        if is_queued:
            await safe_reply(update, f"⏳ System Busy. Your video (\"{custom_title}\") is at position #{pos} in the queue...")

        async with PROCESSING_LOCK:
            if is_queued:
                with QS_LOCK: QUEUE_SIZE = max(0, QUEUE_SIZE - 1)
            
            await safe_reply(update, "✨ Starting process...")
            # Original Logic...
        
        video_path = None
        unique_filename = None
        url_hash = "local_upload"
        
        import hashlib
        
        # --- PATH A: PRE-DOWNLOADED FILE (Direct Upload) ---
        if pending_local_path:
             if os.path.exists(pending_local_path):
                 video_path = pending_local_path
                 # Generate pseudo-hash for consistency
                 url_hash = hashlib.md5(f"{pending_local_path}_{time.time()}".encode()).hexdigest()[:8]
                 # Rename to include Title for clarity? (Optional, but good for debugging)
                 # We'll stick to the existing path to avoid file errors.
             else:
                 await safe_reply(update, "❌ Error: Uploaded file verification failed. Please try again.")
                 return

        # --- PATH B: URL DOWNLOAD ---
        elif pending_url:
             await safe_reply(update, "📥 Downloading content...")
             
             # Generate Unique ID from URL
             url_hash = hashlib.md5(pending_url.encode()).hexdigest()[:8]
             
             # Sanitize title for filename
             clean_title = "".join([c for c in custom_title if c.isalnum() or c in (' ', '-', '_')]).strip()[:30]
             # unique_filename = f"{clean_title}_{url_hash}.mp4" # REMOVED: Hash Naming
             
             GlobalState.set_busy(True)
             
             # HARDENING: Strict Abort - No Retry
             download_result = await asyncio.to_thread(
                downloader.download_video, 
                pending_url, 
                custom_title=custom_title
             )
             
             # Unpack path and skip flag
             if isinstance(download_result, tuple):
                 video_path, was_skipped = download_result
             else:
                 video_path, was_skipped = download_result, False

             # [USER REQUEST] SMART REUSE LOGIC:
             # If reuse detected, we DO NOT abort processing.
             # But we MUST skip the "Raw Sync Upload" to Telegram group later.
             if was_skipped:
                 logger.info(f"⏳ Processing continues, but Raw Telegram Upload will be skipped.")
                 await safe_reply(update, f"♻️ **Smart Reuse**\nFile exists. Skipping download & group upload, but continuing AI processing...", force=True)

             # Store Reuse Flag in Session
             with get_session_lock(user_id):
                 if user_id not in user_sessions: user_sessions[user_id] = {}
                 user_sessions[user_id]['is_reused'] = was_skipped             
        if not video_path:
             GlobalState.set_busy(False)
             await safe_reply(update, "❌ Download failed (Strict Abort).")
             with get_session_lock(user_id):
                 user_sessions.pop(user_id, None)
                 try: os.remove(os.path.join(JOB_DIR, f"session_{user_id}.json"))
                 except: pass
             return
        
        # --- COMMON PROCESSING ---
        if not video_path: 
             await safe_reply(update, "❌ Critical Error: Video path missing.")
             return

        # DEDUPLICATION CHECK (STEP 2)
        # Check for collision
        col_type, col_msg = DedupEngine.check_collision(url_hash, video_path)
        
        if col_type != "NONE":
            logger.warning(col_msg)
            logger.warning("⚠️ Content Collision Detected: Forcing FRESH processing pipeline.")
            meta_path = str(video_path) + ".json"
            if os.path.exists(meta_path):
                 try: os.remove(meta_path)
                 except: pass
        
        DedupEngine.register_content(url_hash, video_path, source="user_submission")

        # Load metadata (for hashtags etc)
        metadata = {}
        try:
            meta_path = os.path.splitext(video_path)[0] + ".json"
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
            
        # Use user title, but sanitize it for display/files
        title = custom_title
        
        # Combine Metadata Tags + Default Hashtags
        meta_tags = metadata.get('tags', [])
        default_hashtags = os.getenv("DEFAULT_HASHTAGS_SHORTS", "#shorts #viral #trending")
        
        if meta_tags:
             # Take top 5 meta tags
             meta_tag_str = " ".join([f"#{t}" for t in meta_tags[:5]])
             hashtags = f"{default_hashtags} {meta_tag_str}"
        else:
             hashtags = default_hashtags
        
        # Store Downloaded Path for Retries (CRITICAL FOR NUCLEAR RETRY)
        with get_session_lock(user_id):
             if user_id not in user_sessions: user_sessions[user_id] = {}
             user_sessions[user_id]['source_path'] = str(video_path)
             # Bug fix: Ensure retry_count is initialized
             user_sessions[user_id]['retry_count'] = 0
             # Explicitly save title here too just in case
             user_sessions[user_id]['title'] = custom_title
             save_session(user_id)

        # Removed redundant "Downloaded" message here as we sent custom ones above
        
        # Compile/Process
        # Ensure we set busy if it wasn't set (Local Path case)
        GlobalState.set_busy(True)
        await safe_reply(update, "🚀 **Fast-Track Processing Initiated!**\n\n- Mirroring/Cleaning 🔄\n- AI Captioning 🤖\n- Human Safety Check 🛡️\n- Color Grading 🎨\n\n*Hang tight, final polish in progress...*")
        
        # [ADAPTIVE] Start Timer
        process_start = time.time()
        
        # Determine if fresh processing is required (due to collision)
        should_force = (locals().get("col_type") != "NONE")
        
        # Generate a proper output path with extension
        final_dir = "Processed Shorts"
        os.makedirs(final_dir, exist_ok=True)
        # Sanitize title for filename
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        final_target = _generate_next_filename(final_dir, safe_title, ".mp4")

        final_path, wm_context = await asyncio.to_thread(
             compiler.compile_with_transitions, 
             Path(video_path), 
             final_target, 
             title=title,
             force_reprocess=should_force
        )
        
        # [ADAPTIVE] Stop Timer & Log Efficiency
        process_duration = time.time() - process_start
        _ai3 = getattr(portal, 'adaptive_intelligence', None)
        _ai3_brain = getattr(_ai3, 'brain', None) if _ai3 else None
        if _ai3_brain:
            # Estimate video duration (fallback 15s if unknown)
            vid_dur = wm_context.get('duration', 15.0) 
            # Get quality score (transformation score, default 50)
            q_score = wm_context.get('transformation_score', 50)
            
            eff_score = _ai3_brain.compute_efficiency_score(
                duration=vid_dur, 
                time_taken=process_duration, 
                quality_score=q_score
            )
            logger.info(f"⚡ Compute Efficiency: {eff_score} (Time: {process_duration:.2f}s, Q: {q_score})")
        # --- OUTPUT STATE RESOLVER ---
        if not final_path or not os.path.exists(final_path):
             await safe_reply(update, "❌ Compilation failed (Critical Error).processing starts when batch is full (3/3)")
             # Clean session
             with get_session_lock(user_id):
                 user_sessions.pop(user_id, None)
             return

        final_str = str(final_path)

        # Enforce defaults if variables are somehow empty/None
        if not locals().get("wm_context"): wm_context = {}
        
        # Retrieve Sidecar Metadata (Ferrari Audit Fix)
        mon_meta = {}
        pipeline_metrics = {}
        opt_caption = None
        try:
             sidecar_path = os.path.splitext(final_str)[0] + ".json"
             if os.path.exists(sidecar_path):
                 with open(sidecar_path, 'r') as f:
                     sc_data = json.load(f)
                     pipeline_metrics = sc_data.get('pipeline_metrics', {})
                     mon_meta = pipeline_metrics.get('monetization', {})
                     if 'caption_data' in sc_data:
                         opt_caption = sc_data['caption_data'].get('caption')
                     
                     # [FIX] Use Gemini Generated Title if available
                     editorial_title = sc_data.get('editorial_title')
                     if editorial_title and len(editorial_title) > 5 and editorial_title != "None":
                         title = editorial_title
                         logger.info(f"🧠 [MAIN] Upgrading Title to Gemini Editorial: '{title}'")
        except: pass

        # Default Safety Values
        ypp_risk = mon_meta.get('risk_level', 'UNKNOWN')
        is_approved = (ypp_risk in ['LOW', 'MEDIUM'])
        style = "Transformative" # Default
        action = "APPROVE" if is_approved else "REVIEW"
        # Reason Safety (Check both Brain 'risk_reason' and Compiler 'reason')
        reason = mon_meta.get('risk_reason') or mon_meta.get('reason', 'Analysis pending or not performed.')

        # Watermark Status Derivation
        wm_status = wm_context.get('watermark_status', 'NOT_DETECTED')
        
        # Monetization Status Derivation
        monetization_status = "PASSED" if is_approved else "REVIEW"
        if ypp_risk == "HIGH": monetization_status = "BLOCKED"
        
        # Reason Safety (Fallback)
        if not reason: reason = "Transformative edit approved."

        # Dynamic Refinement Message (FINAL UPDATE)
        # Ensure message matches reality of wm_context even if exceptions occurred above
        wm_msg = "(No refinement needed - reply 'no' if missed)"
        final_status = wm_context.get('watermark_status')
        
        if final_status == "DETECTED_AND_REMOVED":
             wm_msg = "(Visual refinement applied - verify result)"
        elif final_status == "DETECTED_BUT_SKIPPED":
             wm_msg = "(Refinement detected but skipped for safety)"
        elif final_status == "DETECTED_BUT_FAILED":
             wm_msg = "(Visual refinement FAILED - verify result)"
        elif final_status == "UNVERIFIED_QUOTA_LIMIT":
             wm_msg = "⚠️ (Refinement Check SKIPPED - Quota Exceeded)"

        # Caption Genuineness (Ensuring we don't just show the title)
        display_caption = opt_caption
        if not display_caption or len(display_caption.split()) < 3:
             # Try pulling from brain reasoning if available (Standardized to 'final_caption')
             brain_cap = mon_meta.get('final_caption') or mon_meta.get('caption')
             display_caption = brain_cap if brain_cap and len(brain_cap.split()) > 3 else title
             
        # If still just the title, mark it clearly
        if display_caption == title:
             display_caption = f"⚠️ Safety Fallback: {title} (AI descriptive check pending)"
        overlay_text = os.getenv('TEXT_OVERLAY_CONTENT', 'swargawasal') # Default from envy

        # [USER REQUEST] AUTO-THUMBNAIL GENERATION
        try:
            from Thumb_Modules.generator import generate_thumbnail
            logger.info("🎨 Generating Auto-Thumbnail...")
            
            # Use sample_thumbs directory to avoid clutter
            sample_dir = "sample_thumbs"
            os.makedirs(sample_dir, exist_ok=True)
            
            # Construct a clean name: basename_thumb.jpg
            base_name = os.path.basename(final_str)
            base_name_no_ext = os.path.splitext(base_name)[0]
            thumb_target = os.path.join(sample_dir, f"{base_name_no_ext}_thumb.jpg")
            
            thumb_path = generate_thumbnail(final_str, title, accent_color="yellow", output_path=thumb_target)
            
            if thumb_path:
                logger.info(f"✅ Thumbnail Ready: {thumb_path}")
            else:
                logger.warning("⚠️ Thumbnail generation returned None.")
        except Exception as e:
            logger.error(f"❌ Thumbnail Generation Failed: {e}")

        # --- PREPARE DATA FOR SESSION & REPORT ---
        enable_lp_tele = os.getenv("LOS_POLLOS_TELEGRAM", "yes").lower() in ["yes", "true", "on"]
        _mon_brain_2 = getattr(getattr(portal, 'monetization_brain', None), 'brain', None)
        mon_link = _mon_brain_2.get_monetization_link(target_platform="telegram") if enable_lp_tele and _mon_brain_2 else None
        cta_text = mon_meta.get('monetization_cta', 'Shop for the outfit')
        
        enable_fashion = os.getenv("ENABLE_FASHION_SCOUT", "yes").lower() in ["yes", "true", "on"]
        fashion = mon_meta.get('fashion_scout') if enable_fashion else None

        # --- REAL-TIME CASH-MAXIMIZER AUTO-APPROVE ---
        if CASH_MAX_MODE:
             logger.info("💰 [AUTO-APPROVE] CASH_MAX_MODE is ACTIVE. Skipping manual review.")
             await safe_reply(update, "🚀 **Auto-Approving for Real-Time Cash flow...**")
             await _perform_upload(update, context)
             gc.collect() # Immediate memory flush
             return
        
        # Update Session with Brain Data
        with get_session_lock(user_id):
            user_sessions[user_id]['monetization_report'] = {
                "risk": ypp_risk,
                "style": style,
                "approved": is_approved,
                "action": action,
                "caption": display_caption,
                "fashion_scout": fashion,
                "monetization_cta": mon_link if mon_link else cta_text # Store actual link if possible
            }
            # Add secondary field for explicit CTA text
            user_sessions[user_id]['monetization_report']['cta_text'] = cta_text
            
            # BUG FIX: Save the Final Video Path to session so /approve can find it
            user_sessions[user_id]['final_path'] = final_str
            user_sessions[user_id]['title'] = title # Update title too if needed
            
            # BUG FIX: Explicitly set state to WAITING_FOR_APPROVAL so commands work
            user_sessions[user_id]['state'] = 'WAITING_FOR_APPROVAL'
            save_session(user_id)
        
        await safe_reply(update, "✅ Video processed! Sending preview...")
        
        # --- REPORT ASSEMBLY (MULTI-PART TO PREVENT TRUNCATION) ---
        # --- REPORT ASSEMBLY (STRICT SPLIT) ---
        
        # 1. Construct Telegram Public Caption (Attraction/Motivation ONLY)
        # User Request: "telegram = attraction message or motivation to find partner message and sponsorship link"
        
        # Consistent 18+ Hook (Using mon_meta text if brain ran, else randomized from pool)
        # Safety net: Only use pool if brain returns empty or very short "filler" (less than 10 words).
        # We want to keep Gemini's new "Detailed Creative" (e.g. Cheetah print teasing).
        raw_cta = mon_meta.get('monetization_cta')
        is_filler = not raw_cta or len(raw_cta.split()) < 10 or any(x in raw_cta.lower() for x in ["check this out", "click here", "more details"])
        
        # Override filler check if it looks like a genuine descriptive teaser (Trust but verify)
        if raw_cta and len(raw_cta.split()) >= 10:
             is_filler = False 

        if is_filler:
            try:
                raw_cta = random.choice(HIGH_VOLTAGE_CTA_HOOKS)
            except NameError:
                 # Fallback if variable rename missed
                 raw_cta = "Warning: This look is fatal. Handle with care."
        
        # --- DUAL FUNNEL LOGIC MOVED FOR SEQUENCING ---
        # User Request: "Verify user upload before channel sync"
        # We prepare the variables here but dispatch later.
        
        # Extract the actual descriptive text from the brain's output (not the non-existent visual_description key)
        # We use editorial_script as it contains the richest visual context generated by the first brain pass.
        vis_desc = mon_meta.get('editorial_script', 'A stunning outfit.')
        _mb = getattr(portal, 'monetization_brain', None)
        _mb_brain = getattr(_mb, 'brain', None) if _mb else None
        mystery_story = _mb_brain.get_telegram_story(vis_desc) if _mb_brain else "Style that speaks for itself."
        
        try:
            amazon_link = _mb_brain.get_monetization_link(target_platform="youtube") if _mb_brain else None
            lp_link = _mb_brain.get_monetization_link(target_platform="telegram") if _mb_brain else None
        except:
            amazon_link = None
            lp_link = None

        raw_caption = f"**{title}**\n\n{mystery_story}\n\n"
        if amazon_link:
            raw_caption += f"👗 Shop the Look: {amazon_link}\n"
        if lp_link:
            raw_caption += f"💋 The Secret: {lp_link}"

        # Define internal helper for later use
        async def _bg_raw_sync_upload(v_path, caption, channel):
            for attempt in range(1, 4): # Reduced retries for sync
                try:
                    async with UPLOAD_SEMAPHORE:
                        with ProgressFile(v_path, logger.info) as vf:
                            await context.bot.send_video(chat_id=channel, video=vf, caption=caption, parse_mode="Markdown", read_timeout=600, write_timeout=600, connect_timeout=60)
                    return
                except: await asyncio.sleep(5)

        # FIXED: Prepend Title here too
        public_caption = f"**{title}**\n\n🔥 Exclusive for VIP Members\n\n{raw_cta}\n"
        
        # A. Motivation / Attraction Link
        if mon_link:
            public_caption += f"👉 {mon_link}\n\n"
            if "example.com" in mon_link:
                await safe_reply(update, "⚠️ WARNING: You are using the default 'example.com' link. Please update 'The_json/los_pollos_links.json'.")
        else:
            public_caption += "\n"

        # B. Hashtags (Optional - keeping them for discovery if user wants, but request said ONLY attraction msg.
        # User said "in one line". Let's keep it strictly to the CTA + Link.)
        
        
        # 2. Construct Admin Debug Report (Stats + Materials for Manual Work)
        # User Request: "🎬 FINAL REVIEW SUMMARY" format
        
        admin_report = (
            "--------------------------------\n"
            "🎬 **FINAL REVIEW SUMMARY**\n"
            "--------------------------------\n\n"
            f"🎯 **Title:**\n{title}\n\n"
            f"📌 **Caption Generated:**\n{display_caption}\n\n"
            f"🖋️ **Text Overlays:**\n{overlay_text}\n\n"
            f"🧠 **Watermark Status:**\n{wm_status}\n\n"
            f"💰 **Monetization Status:**\n{'✅ SAFE' if ypp_risk.upper() == 'LOW' else '⚠️ CHECK REQUIRED'}\n\n"
            f"⚠️ **Risk Level:**\n{ypp_risk.upper()}\n\n"
            f"🎨 **Transformation:**\n{mon_meta.get('transformation_score', '90')}% (Pipeline Certified)\n\n"
            f"📎 **Reason:**\n{reason}\n\n"
        )
        
        if fashion:
            links = fashion.get('search_links', {})
            queries = fashion.get('search_queries', {})
            admin_report += "👗 **FASHION SCOUT (FOR MANUAL SPONSORSHIP METADATA)**\n"
            
            # Show Search Queries 
            if queries.get('amazon'):
                admin_report += f"🔍 Amazon Query: `{queries.get('amazon')}`\n"
            
            # Show Raw Links
            if links.get('amazon_in'):
                admin_report += f"🔗 Amazon IN: {links.get('amazon_in')}\n"
            elif links.get('amazon_us'):
                admin_report += f"🔗 Amazon US: {links.get('amazon_us')}\n"
            
            admin_report += "(Use these to find product -> Create Affiliate Link)\n\n"

        tips = mon_meta.get('improvement_tips', [])
        if tips:
            admin_report += "💡 **Improvement Tips:**\n"
            for t in tips[:2]:
                admin_report += f"• {t}\n"
            admin_report += "\n"

        admin_report += f"📜 **Policy Matched:** \"{mon_meta.get('policy_citation', 'Significant Original Commentary')}\"\n\n"
        admin_report += f"🚀 {wm_msg}\n\n"
        admin_report += "--------------------------------\n"
        admin_report += "**Public Caption Preview:**\n"
        admin_report += f"{public_caption}\n"
        admin_report += "--------------------------------\n\n"
        admin_report += "Reply /approve to upload or /reject."

        # --- BUTTONS (ON VIDEO) ---
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [
            [
                InlineKeyboardButton("✅ Clean (Yes)", callback_data="wm_clean"),
                InlineKeyboardButton("❌ Bad (No)", callback_data="wm_bad")
            ],
            [
                InlineKeyboardButton("🚀 Approve & Post", callback_data="approve_post"),
                InlineKeyboardButton("🗑️ Reject", callback_data="reject_discard")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if os.path.getsize(final_str) < 50 * 1024 * 1024:
                # 1. Unified Preview: Admin Report as Video Caption
                # (Ensures all data is in one place for review)
                combined_caption = admin_report
                if len(combined_caption) > 1024:
                    combined_caption = combined_caption[:1021] + "..."
                
                await safe_video_reply(update, final_str, caption=combined_caption, reply_markup=reply_markup)
            else:
                large_msg = f"⚠️ Video too large for Telegram preview.\n{admin_report}\n\n**Public Caption Preview:**\n{public_caption}"
                await safe_reply(update, large_msg)
                
        except Exception as e:
            logger.error(f"Error: {e}")
            await safe_reply(update, "❌ Error occurred during preview send.")
        return
            
    # Case 3.5: WAITING_FOR_COMPILATION_TITLE (New Mandatory Flow)
    if state == 'WAITING_FOR_COMPILATION_TITLE':
        user_id = update.effective_user.id
        
        # Retrieve context
        with get_session_lock(user_id):
            session = user_sessions.get(user_id, {})
            merged_path = session.get('pending_compilation_path')
            n_videos    = session.get('pending_n_videos')
            hashtags    = session.get('pending_hashtags')
            base_title  = session.get('pending_base_title', "")
            
        if not merged_path or not os.path.exists(merged_path):
             await safe_reply(update, "❌ Compilation file lost. Please try again.")
             with get_session_lock(user_id):
                 user_sessions.pop(user_id, None)
                 save_session(user_id)
             return

        title_choice = text.strip()
        final_title = ""
        
        # SKIP LOGIC
        if title_choice.lower().startswith("/skip"):
            final_title = base_title if base_title else f"Compilation {n_videos} Videos"
            await safe_reply(update, f"⏩ Skipping preset. Using Base Title: {final_title}")
            await finish_compilation_upload(update, merged_path, final_title, hashtags)
            return
            
        # PRESET LOGIC
        try:
            presets = get_presets()
            
            if title_choice in presets:
                item = presets[title_choice]
                suffix = item.get('suffix', '')
                # Logic: Base Title + Suffix (e.g. "Name" + " | Tag | Tag")
                if base_title and base_title != f"Compilation {n_videos} Videos":
                    final_title = f"{base_title}{suffix}"
                else:
                    # If generic base, just use Suffix (stripped of separator) or Label fallback
                    final_title = f"{item['label']} {suffix}"
                
                logger.info(f"DEBUG: Final Title Set To: '{final_title}'")
            else:
                await safe_reply(update, "⚠️ Invalid selection. Please reply with the number (e.g., '1') or /skip.")
                return
        except Exception as e:
            logger.error(f"Preset load error: {e}")
            final_title = base_title or f"Compilation {n_videos} Videos"

        await safe_reply(update, f"✅ Selected Title: {final_title}")
        
        # Proceed to Finish
        await finish_compilation_upload(update, merged_path, final_title, hashtags)
        return

    # Case 3: Title Expansion Selection (OLD - KEPT FOR BACKWARD COMPAT IF NEEDED or REMOVE?)
    # The user said: "ask user for tittle that from title_expansion_presets.json... but not as optional."
    # The old flow was optional after approval.
    # I will KEEP the old flow for single videos if it exists, but the new flow is for compilations.
    # The old flow state is 'WAITING_FOR_TITLE_EXPANSION', new is 'WAITING_FOR_COMPILATION_TITLE'.
    
    if state == 'WAITING_FOR_TITLE_EXPANSION':
        if text.startswith('/skip'):
             await _perform_upload(update, context)
        elif text.isdigit():
            # Load presets
            try:
                presets = get_presets()
                choice = presets.get(text)
                if choice:
                    suffix = choice.get("suffix", "")
                    # Update title in session
                    with get_session_lock(user_id):
                        current_title = user_sessions[user_id].get('title', "")
                        user_sessions[user_id]['title'] = f"{current_title}{suffix}"
                        save_session(user_id)
                    await safe_reply(update, f"✅ Title Updated: {user_sessions[user_id]['title']}")
                    await _perform_upload(update, context)
                else:
                    await safe_reply(update, "⚠️ Invalid selection. Reply number or /skip.")
            except Exception as e:
                logger.error(f"❌ Error applying preset: {e}")
                await _perform_upload(update, context)
        else:
             await safe_reply(update, "⚠️ Reply with a number to apply preset, or /skip.")
        return

    # Case 4: Approval
    if state == 'WAITING_FOR_APPROVAL':
        if text.lower() in ['approve', '/approve']:
            await approve_upload(update, context)
        elif text.lower() in ['yes', 'y']:
            await verify_watermark(update, context, is_positive=True)
        elif text.lower() in ['no', 'n']:
            await verify_watermark(update, context, is_positive=False)
        elif text.lower() in ['reject', '/reject']:
            await reject_upload(update, context)
        else:
            await safe_reply(update, "⚠️ Options:\n• 'yes'/'no' - Verify visual refinement (Training Data)\n• '/approve' - Upload to YouTube\n• '/reject' - Discard Video")
        return

    # Case 5: Initial Local File Path (New Session Fallback)
    possible_path = text.strip('"').strip("'")
    if os.path.exists(possible_path) and os.path.isfile(possible_path):
         file_name = os.path.basename(possible_path)
         file_size = os.path.getsize(possible_path)
         
         await safe_reply(update, f"📂 Found Local File: `{file_name}` ({file_size/1024/1024:.1f}MB)")
         
         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
         clean_name = _sanitize_title(file_name)
         save_path = os.path.join("downloads", f"local_{clean_name}_{timestamp}.mp4")
         try:
             shutil.copy2(possible_path, save_path)
         except Exception as e:
             await safe_reply(update, f"❌ Failed to copy local file: {e}")
             return

         with get_session_lock(user_id):
             user_sessions[user_id] = {
                 'state': 'WAITING_FOR_TITLE',
                 'pending_local_path': str(save_path),
                 'pending_url': None
             }
             save_session(user_id)
         
         default_hashtags = os.getenv("DEFAULT_HASHTAGS_SHORTS", "#shorts")
         await safe_reply(update, f"✅ File Staged!\n\n📌 Hashtags:\n{default_hashtags}\n\n✏️ Now send the title to start processing.")
         return

    # Case 6: Catch-all for regular messages (Help)
    if not text.startswith('/'):
        await safe_reply(update, "🤖 AMTCE Bot Active.\n\nSend me a URL or a Local File Path to start a new job.")

async def approve_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 1 of Approval: Ask for Title Expansion.
    """
    user_id = update.effective_user.id
    logger.info(f"📩 [APPROVE] approve_upload called by User {user_id}")
    
    with get_session_lock(user_id):
        session = user_sessions.get(user_id, {})
        logger.info(f"📊 [APPROVE] Session State: {session.get('state')}")
        if session.get('state') != 'WAITING_FOR_APPROVAL':
            await safe_reply(update, "⚠️ No video waiting for approval.")
            return

    # Load Presets
    presets_msg = ""
    try:
        presets = get_presets()
            
        if presets:
            msg_lines = ["📌 Select title expansion (optional):"]
            for k, v in presets.items():
                msg_lines.append(f"{k}️⃣ {v['label']}")
            msg_lines.append("\nReply with number or /skip")
            presets_msg = "\n".join(msg_lines)
    except Exception: pass

    if presets_msg:
        with get_session_lock(user_id):
            user_sessions[user_id]['state'] = 'WAITING_FOR_TITLE_EXPANSION'
            save_session(user_id)
        # FORCE REPLY to ensure user sees the menu even if they spammed buttons
        await safe_reply(update, presets_msg, force=True)
    else:
        # No presets, direct upload
        await _perform_upload(update, context)

async def _perform_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Imports provided via Health_handlers portal
    from Health_handlers import get_portal
    portal = get_portal()
    monetization_brain = getattr(portal, "monetization_brain", None)
    uploader = getattr(portal, "uploader", None)
    
    user_id = update.effective_user.id
    logger.info(f"📤 [_perform_upload] Starting for User {user_id}")
    
    with get_session_lock(user_id):
        session = user_sessions.get(user_id, {})
        final_path = session.get('final_path')
        title = session.get('title')
        # existing hashtags from session (if any)
        hashtags = session.get('hashtags')
        # Check Reuse Flag
        is_reused_content = session.get('is_reused', False)
    
    logger.info(f"📁 [_perform_upload] Video Path: {final_path}")
    
    if not final_path or not os.path.exists(final_path):
        await safe_reply(update, "❌ Video file found missing during upload phase.")
        return

    # --- CHEETAH LOGIC V2: USE BRAIN HASHTAGS ---
    # Strategy: Brain now returns 'hashtags' directly. No separate call needed.
    mon_report = session.get('monetization_report', {})
    brain_hashtags = mon_report.get('hashtags')
    
    # 2. Resolution Strategy
    if brain_hashtags and isinstance(brain_hashtags, list) and len(brain_hashtags) > 3:
        # Convert list to string if needed, or join
        hashtags = " ".join(brain_hashtags)
        await safe_reply(update, f"🏷️ Used AI Hashtags (Quota Saver): {len(brain_hashtags)} tags")
    else:
        # Fallback to session or default
        if not hashtags:
             hashtags = os.getenv("DEFAULT_HASHTAGS_SHORTS", "#shorts #viral #trending")

    # 3. YouTube Upload (Conditional)
    try:
        send_to_youtube = os.getenv("SEND_TO_YOUTUBE", "on").lower() in ["on", "yes", "true"]
        link = None
        yt_msg = "" # Initialize here to avoid unbound error
        
        if send_to_youtube:
            # Extract caption for rich description
            mon_report = session.get('monetization_report', {})
            caption_text = mon_report.get('caption', '')
            rich_desc = mon_report.get('rich_description')
            
            # Construct Rich Description (Title + Brain Narrative ONLY)
            # Cheetah Logic V2: Use the 3-paragraph humorous/SEO desc if available.
            if rich_desc and len(rich_desc) > 50:
                 description = f"{title}\n\n{rich_desc}\n\n"
            else:
                 # Fallback V1
                 description = f"{title}\n\n{caption_text}\n\n"
            
            # --- TRAFFIC SEGREGATION: FORCE AMAZON LINK ON YOUTUBE ---
            _mb2 = getattr(portal, 'monetization_brain', None)
            _mb2_brain = getattr(_mb2, 'brain', None) if _mb2 else None
            yt_safe_link = _mb2_brain.get_monetization_link(target_platform="youtube") if _mb2_brain else None
            if yt_safe_link:
                 partner_hooks = [
                     "Shop this look for your girlfriend",
                     "Treat your wife to this look",
                     "Get this for your partner",
                     "Surprise her with this fit",
                     "Shop this style for your girl"
                 ]
                 cta_var = random.choice(partner_hooks)
                 description += f"🛍️ {cta_var}: {yt_safe_link}\n\n"
            # ---------------------------------------------------------
            
            # Add Hashtags (if any)
            if hashtags:
                description += f"\n{hashtags}"

            await safe_reply(update, "📤 Uploading to YouTube...", force=True)
            logger.info(f"🚀 Calling uploader for: {final_path}")
            try:
                # HARDENING: Retry Network Call
                link = await with_retry(uploader.upload_to_youtube, final_path, title=title, hashtags=hashtags, description=description)
                
                if link:
                    yt_msg = f"✅ YouTube: Success ({link})"
                    
                    # Log with strict monetization data
                    mon_data = session.get('monetization_report', {})
                    log_video(final_path, link, title, 
                              ypp_risk=mon_data.get('risk', 'unknown'),
                              style=mon_data.get('source', 'unknown'), # Log Source as Style for visibility
                              action="approved") # User clicked approve
                    
                    # [ADAPTIVE v3] Trust Feedback (Success)
                    if getattr(portal, 'adaptive_intelligence', None):
                        # Using 'reward' for RL training (simple proxy: High Trust = Reward?)
                        # Actually we update Trust here. RL reward comes from Views later.
                        # For now, immediate upload success counts as small positive.
                        portal.adaptive_intelligence.brain.register_upload_outcome("success", risk_score=mon_data.get('risk_score', 0))
                        
                        # Trigger minimal RL update for the selected trigger
                        active_trigger = mon_data.get('active_psychology')
                        if active_trigger:
                            portal.adaptive_intelligence.brain.update_cta_reward(active_trigger, 0.1) # Small positive reinforcement for successful pipeline execution
                    
                    # --- COMMUNITY PROMOTION ---
                    # Post a comment on this Video pointing to the last Compilation
                    # SMART ROUTE: Shorts = Text Only (No Link), Long/Comp = Clickable Link
                    if os.getenv("ENABLE_COMMUNITY_POST_COMPILATION", "yes").lower() == "yes":
                         is_short_video = "#shorts" in (hashtags or "").lower()
                         logger.info(f"🚀 Triggering Cross-Promotion (Background Task). Video Type: {'Short' if is_short_video else 'Long/Compilation'}")
                         
                         asyncio.create_task(
                             community_promoter.promoter.promote_on_short_async(
                                 uploader.get_authenticated_service(),
                                 link,
                                 is_short=is_short_video,
                                 custom_text=mon_data.get('monetization_cta'),
                                 fashion_data=mon_data.get('fashion_scout')
                             )
                         )
                else:
                    yt_msg = "❌ YouTube: Failed"
                    # [ADAPTIVE v3] Trust Feedback (Error)
                    if getattr(portal, 'adaptive_intelligence', None):
                        portal.adaptive_intelligence.brain.register_upload_outcome("error", risk_score=mon_data.get('risk_score', 0))

            except Exception as e:
                logger.error(f"YouTube Upload Failed: {e}")
                yt_msg = f"❌ YouTube Error: {e}"
                # [ADAPTIVE v3] Trust Feedback (Error)
                if getattr(portal, 'adaptive_intelligence', None):
                    portal.adaptive_intelligence.brain.register_upload_outcome("error", risk_score=mon_data.get('risk_score', 0))
        else:
            logger.info("🚫 SEND_TO_YOUTUBE is OFF. Skipping YouTube upload.")
            await safe_reply(update, "⏭️ YouTube Upload Skipped (Configured OFF).")
            yt_msg = "⏩ YouTube: Skipped"
            
        # 2. Meta Upload (Runs INDEPENDENTLY of YouTube success/failure/skip)
        # Imports provided via Health_handlers portal
        meta_results = {}
        if os.getenv("ENABLE_META_UPLOAD", "no").lower() in ["yes", "true", "on"]:
             await safe_reply(update, "📤 Attempting Meta (Instagram/Facebook) Uploads...")
             # Construct Caption (Title + Viral Caption + Hashtags)
             mon_report = session.get('monetization_report', {})
             caption_text = mon_report.get('caption', '')
             meta_caption = f"{title}\n\n{caption_text}\n\n{hashtags}" if hashtags else f"{title}\n\n{caption_text}"             
             meta_results = await meta_uploader.AsyncMetaUploader.upload_to_meta(
                 final_path, 
                 meta_caption,
                 upload_type=os.getenv("META_UPLOAD_TYPE", "Reels"),
                 skip_facebook=True # 🛑 RESTRICT FB TO COMPILATIONS ONLY
             )
             
        # 3. Final Report
        report_lines = ["🚀 Upload Summary:", ""]
        report_lines.append(yt_msg)
        
        if meta_results:
            # Instagram
            ig_res = meta_results.get("instagram", {"status": "skipped"})
            if isinstance(ig_res, str): ig_res = {"status": ig_res}
            ig_status = ig_res.get("status", "skipped")
            ig_link = ig_res.get("link", "")
            icon_ig = "✅" if ig_status == "success" else "❌" if "failed" in ig_status else "⏩"
            line_ig = f"{icon_ig} Instagram: {ig_status}"
            if ig_link: line_ig += f" ({ig_link})"
            report_lines.append(line_ig)
            
            # Facebook
            fb_res = meta_results.get("facebook", {"status": "skipped"})
            if isinstance(fb_res, str): fb_res = {"status": fb_res}
            fb_status = fb_res.get("status", "skipped")
            fb_link = fb_res.get("link", "")
            icon_fb = "✅" if fb_status == "success" else "❌" if "failed" in fb_status else "⏩"
            line_fb = f"{icon_fb} Facebook: {fb_status}"
            if fb_link: line_fb += f" ({fb_link})"
            report_lines.append(line_fb)
            
        await safe_reply(update, "\n".join(report_lines))

        # Check for compilation trigger
        if link: # Only trigger compile if at least youtube worked? Or always?
             # Logic: Compilation usually builds from "Processed Shorts".
             # If upload failed, the file is still in Processed Shorts?
             # Yes. So we can trigger it.
             await maybe_compile_and_upload(update)
             
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await safe_reply(update, f"❌ Upload error: {e}")
        
    # Clear session
    with get_session_lock(user_id):
        user_sessions.pop(user_id, None)
        try: os.remove(os.path.join(JOB_DIR, f"session_{user_id}.json"))
        except: pass
        
    # --- CASH-MAXIMIZER MEMORY FLUSH ---
    if CASH_MAX_MODE:
         logger.info("🧹 [MEMORY FLUSH] Real-Time loop finishing. Cleaning RAM.")
         gc.collect()
         # Also try to clear asyncio tasks if too many are lingering
         current_tasks = len(asyncio.all_tasks())
         if current_tasks > 50:
             logger.warning(f"⚠️ High task count detected: {current_tasks}. Clearing RAM aggressively.")
             gc.collect()

async def verify_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE, is_positive: bool = None):
    query = update.callback_query
    
    # Check if called via button (query) or command (arg)
    if query:
        await query.answer()
        user_id = query.from_user.id
        # Use query data mapping if arg is None
        if is_positive is None:
            if query.data == "wm_clean": is_positive = True
            elif query.data == "wm_bad": is_positive = False
            elif query.data == "approve_post":
                await approve_upload(update, context)
                return
            elif query.data == "reject_discard":
                await reject_upload(update, context)
                return
    else:
        # Called via text command
        user_id = update.effective_user.id
    
    if is_positive is None:
        # Should not happen if logic is correct, but safety
        return

    # Imports provided via Health_handlers portal
    
    # Helper for robust editing (Text vs Caption)
    async def smart_edit(text):
        if not query:
            await safe_reply(update, text)
            return
            
        try:
            if query.message.text:
                await query.edit_message_text(text)
            elif query.message.caption is not None: # It's a media message
                await query.edit_message_caption(caption=text)
            else:
                # Fallback for weird cases (stickers? types without caption?)
                await safe_reply(update, text)
        except Exception as e:
            logger.warning(f"⚠️ Smart Edit Failed: {e}")
            await safe_reply(update, text)

    with get_session_lock(user_id):
        session = user_sessions.get(user_id, {})
        # Fallback Logic: handle_message sets 'final_path', retry sets 'pending_video'
        video_path = session.get('pending_video') or session.get('final_path')
        if not video_path:
             msg = "❌ Session expired (Video path lost). Please upload again."
             await smart_edit(msg)
             return
        title = session.get('title', 'video')
        # Retry Tracker
        retry_count = session.get('retry_count', 0)
        
        if is_positive:
            # Positive Feedback
            hybrid_watermark.hybrid_detector.confirm_learning(session.get("wm_context",{}), is_positive=True)
            
            msg = f"✅ Watermark Verification Successful! Proceeding to next step..."
            await smart_edit(msg)
            
            # PROCEED TO APPROVAL FLOW
            try:
                # ensuring state is correct for approve_upload check
                session['state'] = 'WAITING_FOR_APPROVAL'
                save_session(user_id)
                
                await approve_upload(update, context)
            except Exception as e:
                logger.error(f"❌ Error in Approval Flow trigger: {e}", exc_info=True)
                await safe_reply(update, "❌ Error proceeding to upload. Please try /approve manually.", force=True)
            return


        else:
            # Negative Feedback -> RETRY LOOP
            
            # 1. STRICT DELETION (Soft Reset)
            # We must delete the FAILED artifact to prevent pollution.
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    logger.info(f"🗑️ Strict Deletion (Rejected): {video_path}")
                
                # Try to delete associated JSON
                json_path = os.path.splitext(video_path)[0] + ".json"
                if os.path.exists(json_path):
                     os.remove(json_path)
                     logger.info(f"🗑️ Strict Deletion (Meta): {json_path}")
            except Exception as e:
                logger.warning(f"Deletion warning: {e}")

            # 2. Learning
            hybrid_watermark.hybrid_detector.confirm_learning(session.get("wm_context",{}), is_positive=False)
            
            # 3. Increment Level
            retry_count += 1
            session['retry_count'] = retry_count
            save_session(user_id)
            
            if retry_count > 2:
                # Max Retries Reached -> Give Up
                msg = "❌ Maximum retries reached. I'm sorry I couldn't clean it."
                await smart_edit(msg)
                user_sessions.pop(user_id, None)
                GlobalState.set_busy(False)
                return

            # 4. Trigger Retry
            # Level 1: Aggressive Static
            # Level 2: Better Accurate Patch (Static+6) OR Dynamic (if moving)
            
            mode_name = "Aggressive" if retry_count == 1 else "Deep Scan"
            status_msg = f"🔄 Retry {retry_count}/2: Activating {mode_name} Correction...\n(This might take longer)"
            await smart_edit(status_msg)
            
            # --- QUEUE HANDLING FOR RETRY ---
            global QUEUE_SIZE
            is_queued = False
            with QS_LOCK:
                if PROCESSING_LOCK.locked():
                    QUEUE_SIZE += 1
                    is_queued = True
                    pos = QUEUE_SIZE
            
            if is_queued:
                await safe_reply(update, f"⏳ System Busy. Your retry request is at position #{pos} in the queue...")

            async with PROCESSING_LOCK:
                if is_queued:
                    with QS_LOCK: QUEUE_SIZE = max(0, QUEUE_SIZE - 1)
                
                # 5. Re-run Compiler
            # We assume pending_video WAS the input or we still have access to original download?
            # Actually, main.py usually keeps 'pending_url' or original download until finished.
            # But compiler overwrites? No, it makes a NEW file.
            # We need the path to the SOURCE video (downloaded raw).
            # Session usually has 'video_path' populated from download, and 'pending_video' populated from compile?
            # Let's use 'video_path' (downloaded) if available, else 'pending_video' (compiled) would be circular if deleted.
            
            # Wait, `handle_message` download stores path in `video_path` variable, but in SESSION?
            # We need to ensure we have the source.
            # Let's optimistically assume `session['source_path']` exists (I will add it in handle_message next step).
            # Fallback: If not, we might fail.
            
            source_path = session.get('source_path')
            
            # If source path is missing, we try to guess from session state or fail
            if not source_path:
                 await smart_edit("❌ Error: Original source lost. Cannot retry.")
                 return
            
            try:
                import compiler
                retry_out, ctx = await asyncio.to_thread(
                    compiler.compile_with_transitions, 
                    Path(source_path), 
                    title, 
                    retry_level=retry_count
                )
                
                if retry_out:
                    # Update Session
                    session['pending_video'] = str(retry_out)
                    session['wm_context'] = ctx
                    save_session(user_id)
                    
                    # Ask Again
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = [
                        [InlineKeyboardButton("✅ Perfect (Post It)", callback_data="wm_clean")],
                        [InlineKeyboardButton("❌ Still Bad (Retry)", callback_data="wm_bad")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    with ProgressFile(retry_out, logger.info) as vf:
                        await context.bot.send_video(
                            chat_id=user_id,
                            video=vf,
                            caption=f"📝 Retry {retry_count} Result ({mode_name}).\nIs the watermark gone?",
                            reply_markup=reply_markup,
                            read_timeout=600, 
                            write_timeout=600,
                            connect_timeout=60
                        )
                else:
                    await smart_edit("❌ Retry failed to produce output.")
                    
            except Exception as e:
                logger.error(f"Retry Error: {e}")
                await smart_edit("❌ Error during retry.")

async def reject_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("❌ [REJECT] reject_upload triggered")
    
    user_id = update.effective_user.id
    query = update.callback_query
    # Query already answered in verify_watermark
    
    with get_session_lock(user_id):
        session = user_sessions.get(user_id, {})
        logger.debug(f"DEBUG: Session state: {session.get('state')}")
    
        if session.get('state') == 'WAITING_FOR_APPROVAL':
            final_path = session.get('final_path')
            
            # User REJECTED: Permanent Delete
            if final_path and os.path.exists(final_path):
                 try:
                     os.remove(final_path)
                     logger.info(f"🗑️ Deleted rejected file: {final_path}")
                 except Exception as e:
                     logger.error(f"Failed to delete file: {e}")
                 
                 # Also delete sibling JSON if exists
                 json_sibling = os.path.splitext(final_path)[0] + ".json"
                 if os.path.exists(json_sibling):
                      try: os.remove(json_sibling)
                      except Exception: pass
                  
                 # ALSO DELETE SNAPPED THUMBS (assets/snapped_thumbs/)
                 title = session.get('title')
                 if title:
                     try:
                         # Matching compiler.py slug logic for base name
                         safe_base = re.sub(r'[^a-zA-Z0-9_\-]', '', title.replace(" ", "_"))
                         if not safe_base: safe_base = "unnamed_series"
                         
                         snap_dir = "assets/snapped_thumbs"
                         if os.path.exists(snap_dir):
                             # [FIX] Extract Index from Final Path to target SPECIFIC thumb
                             # Final path: .../Avneet_kaur_6.mp4 -> Index 6 -> Avneet_kaur_006.jpg
                             fname = os.path.basename(final_path)
                             name_no_ext = os.path.splitext(fname)[0]
                             
                             # Regex to find trailing number
                             match = re.search(r'_(\d+)$', name_no_ext)
                             if match:
                                 idx = int(match.group(1))
                                 target_thumb = f"{safe_base}_{idx:03d}.jpg"
                                 target_path = os.path.join(snap_dir, target_thumb)
                                 
                                 if os.path.exists(target_path):
                                     os.remove(target_path)
                                     logger.info(f"🗑️ Deleted snapped preview: {target_thumb}")
                                 else:
                                     logger.debug(f"ℹ️ Thumb not found for rejection: {target_thumb}")
                             else:
                                 # Fallback: If no index, standard logic might be safer to SKIP than wildcard.
                                 logger.debug(f"ℹ️ Could not extract index from {fname}, skipping thumb deletion to avoid wildcard error.")
                                 
                     except Exception as se:
                         logger.warning(f"⚠️ Failed to clean snapped thumbs: {se}")
    
                 # CLEANUP: Delete the sample_thumb copy too
                 try:
                     # Logic must match compiler: sample_thumbs/{basename}_thumb.jpg
                     final_name = os.path.basename(final_path) # e.g. text_2.mp4 or Malavika_1.mp4 
                     base_name_no_ext = os.path.splitext(final_name)[0] # e.g. text_2
                     
                     # Check for both possible patterns (with and without _thumb)
                     possible_thumbs = [
                         f"{base_name_no_ext}_thumb.jpg",
                         f"{base_name_no_ext}.jpg"
                     ]
                     
                     sample_dir = "sample_thumbs"
                     if os.path.exists(sample_dir):
                         for pt in possible_thumbs:
                            thumb_path = os.path.join(sample_dir, pt)
                            if os.path.exists(thumb_path):
                                os.remove(thumb_path)
                                logger.info(f"🗑️ Deleted sample thumb: {thumb_path}")
                 except Exception as te:
                     logger.warning(f"⚠️ Failed to clean sample thumb: {te}")
    
                 # AND DELETE THE SPECIFIC THUMBNAIL IN OUTPUT DIR
                 thumb_sibling = os.path.splitext(final_path)[0] + "_thumb.jpg"
                 if os.path.exists(thumb_sibling):
                     try: os.remove(thumb_sibling)
                     except Exception: pass
                      
                 await safe_reply(update, "🗑️ Video permanently deleted.")
            else:
                 await safe_reply(update, "🗑️ Video discarded (File missing).")
                
            logger.info("Clearing session after reject")
            user_sessions.pop(user_id, None)
            # Remove persistence file
            try:
                os.remove(os.path.join(JOB_DIR, f"session_{user_id}.json"))
            except Exception: pass
        else:
            logger.debug("Nothing to reject")
            await safe_reply(update, "⚠️ Nothing to reject.")

import signal
import sys

def signal_handler(sig, frame):
    logger.info("🛑 KeyboardInterrupt received. Force Shutting down...")
    os._exit(0)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Exception while handling an update: {context.error}")
    # traceback.print_exception(None, context.error, context.error.__traceback__) # Optional debug
    
    # Try to notify user if possible
    if isinstance(update, Update) and update.effective_message:
        try:
            await safe_reply(update, "⚠️ A temporary network error occurred. Please try again.")
        except: pass

def main():
    # Register Signal Handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # HARDENED TIMEOUTS (Total patience for slow uploads)
    from telegram.request import HTTPXRequest
    # Setting read/write to None enables infinite timeout for large file streaming
    request_config = HTTPXRequest(
        connect_timeout=600,
        read_timeout=None, 
        write_timeout=None,
        pool_timeout=600,
        connection_pool_size=50  # Fix for "Pool timeout" under load
    )
    
    # Check if Local Bot API is configured
    local_api_url = os.getenv("LOCAL_BOT_API_URL")
    
    app_builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).request(request_config)
    
    if local_api_url:
        logger.info(f"🚀 Using LOCAL_BOT_API_URL: {local_api_url}")
        app_builder = app_builder.base_url(local_api_url).local_mode(True)

    app = app_builder.build()
    
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getbatch", getbatch))
    app.add_handler(CommandHandler("setbatch", setbatch))
    app.add_handler(CommandHandler("compile_last", compile_last))
    app.add_handler(CommandHandler("compile_first", compile_first))
    app.add_handler(CommandHandler("versus", cmd_versus))
    app.add_handler(CommandHandler("approve", approve_upload))
    app.add_handler(CommandHandler("reject", reject_upload))
    app.add_handler(CommandHandler("register_promo", register_promo)) # New Command
    app.add_handler(CommandHandler("compile", cmd_compile))
    app.add_handler(CallbackQueryHandler(verify_watermark)) # FIXED: Register Handler
    
    # Direct Video Upload Handler
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_attachment))
    
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("🤖 Bot is running...")
    
    # Load Sessions
    load_sessions()
    
    # Check Env
    check_and_update_env()
    

    
    # Start AutoCleanup (Checks every 60 minutes, deletes files > 2 days old)
    cleanup = AutoCleanup(interval_minutes=60, age_days=2)
    cleanup.start()
    
    # Run polling
    # stop_signals=None prevents it from overwriting our signal handler (unlikely, but safe)
    # Run resilient polling
    logger.info("🤖 Bot starting polling loop...")
    while True:
        try:
             # stop_signals=None prevents it from overwriting our signal handler
            app.run_polling(stop_signals=None, close_loop=False) # close_loop=False allows restart
        except KeyboardInterrupt:
             logger.info("🛑 Polling stopped by user.")
             break
        except Exception as e:
            logger.error(f"❌ Polling CRASH: {e}")
            if "httpx.ConnectError" in str(e) or "getaddrinfo failed" in str(e):
                logger.warning("⚠️ Network connection lost. Retrying in 10s...")
                time.sleep(10)
            else:
                logger.warning("⚠️ Unexpected crash. Retrying in 5s...")
                time.sleep(5)

    # Safe Shutdown
    logger.info("🛑 Shutting down executor...")
    executor.shutdown(wait=True)
    logger.info("👋 Bot stopped gracefully.")

# ==================== AUTO-TRAINING ====================
# ==================== AUTO-TRAINING ====================


class AutoCleanup(threading.Thread):
    def __init__(self, interval_minutes=60, age_days=2):
        super().__init__()
        self.interval = interval_minutes * 60
        self.age_days = age_days
        self.daemon = True
        self.running = True
        # Expanded Cleanup Targets (Including Telegram Bot API local caches)
        self.target_dirs = ["downloads", "temp", "final_compilations", "Original_audio", "telegram-bot-api", "telegram-bot-api-Windows"]
        self.state_file = "The_json/cleanup_state.json"
        self.last_run = self._load_state()

    def _load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return data.get('last_run', 0)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load cleanup state: {e}")
        return 0

    def _save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump({'last_run': self.last_run}, f)
        except Exception as e:
            logger.error(f"❌ Failed to save cleanup state: {e}")

    def run(self):
        logger.info("🧹 AutoCleanup started (Persistent Mode).")
        
        while self.running:
            # Calculate time since last run
            elapsed = time.time() - self.last_run
            wait_time = max(0, self.interval - elapsed)
            
            if wait_time > 0:
                logger.info(f"⏳ Next cleanup in {int(wait_time/60)} minutes ({int(wait_time)}s)...")
                # Sleep in chunks to allow faster shutdown if needed (though daemon thread handles kill)
                # But for simplicity, simple sleep is fine as it's a daemon thread.
                time.sleep(wait_time)
            
            # Perform cleanup
            self._cleanup()
            
            # Update state
            self.last_run = time.time()
            self._save_state()
            
            # Wait for next interval (full interval now)
            # Actually, the loop logic above handles this naturally:
            # Next iteration: elapsed will be ~0, so wait_time will be ~interval.
            # So we don't need an extra sleep here.

    def _cleanup(self):
        try:
            # 1. RUN AUDIO DEDUPLICATION (Prioritize checking Original_audio)
            audio_deduplicator.scan_and_clean_duplicates("Original_audio")

            cutoff = time.time() - (self.age_days * 86400)
            
            for target_dir in self.target_dirs:
                if not os.path.exists(target_dir):
                    continue

                # Custom Retention Policy per folder
                # Default: self.age_days (2 days)
                # Original_audio: 7 days (Weekly)
                effective_cutoff = cutoff
                if "Original_audio" in target_dir:
                    effective_cutoff = time.time() - (2 * 86400)
                    logger.info("🧹 Cleanup: Applying 2-Day policy to Original_audio")

                for item in os.listdir(target_dir):
                    item_path = os.path.join(target_dir, item)
                    
                    if "Processed Shorts" in item or "keep" in item.lower():
                        continue
                        
                    try:
                        mtime = os.path.getmtime(item_path)
                        if mtime < effective_cutoff:
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                                logger.info(f"🗑️ Cleaned file: {item} in {target_dir}")
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path, ignore_errors=True)
                                logger.info(f"🗑️ Cleaned dir: {item} in {target_dir}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to clean {item}: {e}")
                
        except Exception as e:
            logger.error(f"❌ AutoCleanup Error: {e}")


def run_cli_mode(args):
    """
    Direct CLI Entrypoint.
    Bypasses Telegram Bot and runs the compiler pipeline directly.
    """
    print(f"🚀 CLI Mode Active: Standard Pipeline")
    input_source = args.input
    
    # 1. Handle URL vs File
    video_path = input_source
    if input_source.startswith("http"):
        print(f"📥 Downloading URL: {input_source}")
        # Use portal downloader
        from Download_Modules import downloader
        dl_res = downloader.download_video(input_source)
        if dl_res:
             video_path, is_cached = dl_res
             print(f"✅ Downloaded: {video_path} (Cached: {is_cached})")
        else:
             print(f"❌ Download Failed.")
             return

    if not os.path.exists(video_path):
        print(f"❌ Input file not found: {video_path}")
        return

    # 2. Run Compiler
    print(f"🎬 Compiling: {video_path}")
    output_path = f"cli_output_{int(time.time())}.mp4"
    
    # Simple compilation (No fancy title/description unless provided via args later)
    # We use compile_with_transitions shim
    try:
        # Since it's async in shim technically (wait, shim calls orchestrator directly now in sync?)
        # Let's check shim. 
        # Compiler shim 'compile_with_transitions' calls orchestrator.compile_batch which is sync.
        # But 'process_video_pipeline' is async.
        # Let's use the shim function directly.
        from compiler import compile_with_transitions
        
        # Pass enhance flag from CLI args
        enhance_mode = getattr(args, 'enhance', False)
        print(f"🔬 Enhance Mode: {enhance_mode}")
        
        res_path, meta = compile_with_transitions([video_path], output_path, enhance=enhance_mode)
        
        if res_path and os.path.exists(res_path):
            print(f"✅ SUCCESS! Output: {os.path.abspath(res_path)}")
        else:
            print(f"❌ Compilation Failed.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="AMTCE Bot & CLI")
    parser.add_argument("--input", help="Direct input URL or File Path to process")
    parser.add_argument("--enhance", action="store_true", help="Enable Heavy AI Enhancement/Upscaling")
    args, unknown = parser.parse_known_args()
    
    if args.input:
        run_cli_mode(args)
    else:
        # Run Bot
        main()

