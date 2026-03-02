import os
import sys
import json
import random
import logging
import time

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

# Import Watermark Modules directly
try:
    from Visual_Refinement_Modules import watermark_auto, hybrid_watermark, deps_installer
except ImportError:
    sys.path.append(os.path.join(project_root, "Visual_Refinement_Modules"))
    import watermark_auto, hybrid_watermark, deps_installer

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_watermark")

# Paths
DOWNLOADS_DIR = os.path.join(os.environ['USERPROFILE'], 'Downloads')
TRACKER_FILE = os.path.join(os.path.dirname(__file__), 'processed_videos.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'test_outputs')

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        try:
            with open(TRACKER_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"processed": []}

def save_tracker(data):
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def run_test(use_gemini=False):
    """
    Runs a test on a random video.
    use_gemini: Set to True ONLY if you want to test the full AI detection quota.
    """
    deps_installer.run_setup()
    tracker = load_tracker()
    processed_list = tracker.get("processed", [])

    if not os.path.exists(DOWNLOADS_DIR):
        logger.error("Downloads folder not found.")
        return

    mp4_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.lower().endswith('.mp4') and f not in processed_list]
    if not mp4_files:
        logger.warning("No new videos to test.")
        return

    target = random.choice(mp4_files)
    input_path = os.path.join(DOWNLOADS_DIR, target)
    logger.info(f"🎲 Testing: {target}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"clean_{target}")

    # QUOTA SAVING LOGIC
    if use_gemini:
        logger.info("🔭 Using Gemini Detection (Quota will be used)...")
        json_res = hybrid_watermark.hybrid_detector.process_video(input_path)
        watermarks = json.loads(json_res).get("watermarks", [])
    else:
        logger.info("🧪 MOCK DETECTION: Using fixed test coordinates (Zero Quota)...")
        # Default mock box for testing removal engine logic without AI call
        watermarks = [{"coordinates": {"x": 100, "y": 100, "w": 200, "h": 50}, "text": "test_watermark"}]

    if not watermarks:
        logger.info("No watermarks found/mocked.")
        return

    logger.info("🛡️ Starting Removal Engine...")
    job_dir = os.path.join(OUTPUT_DIR, f"job_{int(time.time())}")
    os.makedirs(job_dir, exist_ok=True)
    
    success, msg = watermark_auto.run_adaptive_watermark_orchestration(
        input_path, watermarks, output_path, job_dir=job_dir, retry_level=1
    )

    if success:
        logger.info(f"✅ Success: {output_path}")
        processed_list.append(target)
        tracker["processed"] = processed_list
        save_tracker(tracker)
    else:
        logger.error(f"❌ Failed: {msg}")

if __name__ == "__main__":
    # Check if user passed --gemini flag
    use_ai = "--gemini" in sys.argv
    run_test(use_gemini=use_ai)
