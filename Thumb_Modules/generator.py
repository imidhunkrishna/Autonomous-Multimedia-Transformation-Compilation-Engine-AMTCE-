
import os
import subprocess
import logging
try:
    from .ai_blender import blender
except (ImportError, ValueError):
    try:
        from ai_blender import blender
    except ImportError:
        try:
            from .ai_blender_local import blender
        except (ImportError, ValueError):
            from ai_blender_local import blender

logger = logging.getLogger("thumb_gen")

FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

def get_video_duration(video_path):
    try:
        cmd = [
            FFPROBE_BIN, 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            video_path
        ]
        result = subprocess.check_output(cmd).decode().strip()
        return float(result)
    except Exception as e:
        logger.error(f"Failed to get duration: {e}")
        return 0

def generate_thumbnail(video_path, title_text, accent_color="yellow", output_path=None):
    """
    Generates a thumbnail for the video by extracting a frame at 50% duration
    and overlaying the title text.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video not found: {video_path}")
        return None

    try:
        # 1. Calculate Timestamp (50% mark)
        duration = get_video_duration(video_path)
        timestamp = max(0, duration / 2)
        
        # 2. Paths
        base_name = os.path.splitext(video_path)[0]
        raw_thumb_path = f"{base_name}_raw_thumb.jpg"
        
        if output_path:
             final_thumb_path = output_path
             # Ensure dir exists
             os.makedirs(os.path.dirname(final_thumb_path), exist_ok=True)
        else:
             final_thumb_path = f"{base_name}_thumb.jpg"
        
        # 3. Extract Frame using FFMPEG
        # ffmpeg -ss <time> -i <video> -vframes 1 -q:v 2 <output>
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            "-update", "1", # Force image mode
            raw_thumb_path
        ]
        
        logger.info(f"📸 Extracting frame at {timestamp:.2f}s...")
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if not os.path.exists(raw_thumb_path):
            logger.error("❌ Frame extraction failed.")
            return None
            
        # 4. Overlay Text using AIBlender
        logger.info(f"🎨 Overlaying title: '{title_text}'")
        success = blender.create_blended_thumbnail(
            image_path=raw_thumb_path, 
            output_path=final_thumb_path, 
            title_text=title_text, 
            accent_color=accent_color
        )
        
        # Cleanup raw frame
        try: os.remove(raw_thumb_path)
        except: pass
        
        if success:
            logger.info(f"✅ Auto-Thumbnail Generated: {final_thumb_path}")
            return final_thumb_path
        else:
            return None

    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
        return None
