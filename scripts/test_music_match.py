import sys
import os
import logging

# Path hack to import modules from root
sys.path.append(os.getcwd())

from Audio_Modules.music_manager import ContinuousMusicManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_music")

def test_music_selection():
    # Ensure music dir exists and has some files
    if not os.path.exists("music"):
        os.makedirs("music", exist_ok=True)
        # Create dummy files if empty
        with open("music/test_lofi.mp3", "wb") as f: f.write(b"0"*2000)
        with open("music/test_heavy.mp3", "wb") as f: f.write(b"0"*2000)

    mm = ContinuousMusicManager(music_dir="music")
    
    # Test cases
    profiles = [
        {"title": "Relaxing Vlog", "trend_text": "Aesthetic Vibes"},
        {"title": "Heavy Workout", "trend_text": "Sigma Phonk"},
        {"title": "Standard Clip", "trend_text": "Viral"}
    ]
    
    for p in profiles:
        match = mm.get_best_match(p)
        logger.info(f"Test case: {p['title']} -> Selected: {os.path.basename(match) if match else 'None'}")

if __name__ == "__main__":
    test_music_selection()
