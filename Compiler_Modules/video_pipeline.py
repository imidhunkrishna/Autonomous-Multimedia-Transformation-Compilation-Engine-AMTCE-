import os
import logging
import subprocess
import shutil
import json
import uuid
import re

logger = logging.getLogger("video_pipeline")

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

# --- DYNAMIC RENDER SETTINGS ---
RENDER_TARGET = os.getenv("RENDER_TARGET", "quality").strip().lower()

if RENDER_TARGET == "speed":
    logger.info("⚡ RENDER_TARGET = speed. Using `-crf 26` and `-preset fast` for faster uploads.")
    REENCODE_PRESET = "fast"
    REENCODE_CRF = "26" 
else:
    logger.info("🎥 RENDER_TARGET = quality. Using `-crf 20` and `-preset medium` for maximum detail.")
    REENCODE_PRESET = "medium"
    REENCODE_CRF = "20"  # High quality (Default)

def get_video_info(path):
    """Probe video metadata."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,r_frame_rate",
            "-of", "json", path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            logger.warning(f"Probe: no video stream found in '{path}' — returning empty info")
            return {}
        stream = streams[0]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "duration": float(stream.get("duration", 0)),
            "fps": eval(stream.get("r_frame_rate", "30/1"))
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Probe timed out for '{path}'")
        return {}
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        return {}


def render_pipeline(
    input_path: str,
    output_path: str,
    filters: list = [],
    speed_factor: float = 1.0,
    color_intensity: float = 0.0,
    filter_type: str = "cinematic",
    mirror_mode: bool = False,
    trim_duration: float = None,
    price_tag_image: str = None
) -> bool:
    """
    Core Rendering Pipeline (The "Ferrari Engine")
    executes ALL visual transformations (Trim, Crop, Color, Text, Image Overlays) in ONE PASS.
    """
    if not os.path.exists(input_path):
        logger.error(f"Input not found: {input_path}")
        return False

    # 1. Inputs Construction
    inputs = ["-i", input_path]
    if price_tag_image and os.path.exists(price_tag_image):
        inputs.extend(["-i", price_tag_image])

    # 2. Build Filter Graph
    # We use stream labels to pass the video through multiple independent stages
    current_stream = "[0:v]"
    filter_commands = []
    
    # Stage A: Trim (Start at 1s, duration=trim_duration) & Reset Timestamps
    if trim_duration and trim_duration > 0:
        filter_commands.append(f"{current_stream}trim=start=1:duration={trim_duration},setpts=PTS-STARTPTS[v_trim]")
        current_stream = "[v_trim]"
        
    # Stage B: Core Visuals (Mirror, Speed, Scale/Pad, Color)
    core_vf = []
    if mirror_mode:
        core_vf.append("hflip")
        
    if abs(speed_factor - 1.0) > 0.05:
        core_vf.append(f"setpts={1/speed_factor}*PTS")
        
    core_vf.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1")
    
    if color_intensity > 0:
        if filter_type == "cinematic":
             c = 1.0 + (0.1 * color_intensity)
             s = 1.0 + (0.3 * color_intensity)
             core_vf.append(f"eq=contrast={c}:saturation={s}")
        elif filter_type == "noir":
             core_vf.append("hue=s=0,eq=contrast=1.2")
        elif filter_type == "vibrant":
             core_vf.append("eq=saturation=1.5:brightness=0.05")
             
    if core_vf:
        filter_commands.append(f"{current_stream}{','.join(core_vf)}[v_core]")
        current_stream = "[v_core]"
        
    # Stage C: Text Overlays
    if filters:
        if isinstance(filters, list):
             text_chain = ",".join(filters)
        else:
             text_chain = filters
        filter_commands.append(f"{current_stream}{text_chain}[v_text]")
        current_stream = "[v_text]"

    # Stage D: Image Overlay (Price Tag)
    if price_tag_image and os.path.exists(price_tag_image):
        # Professional Timing: Show tag from 0.75s to 5.75s (5 seconds total)
        filter_commands.append(f"{current_stream}[1:v]overlay=0:0:enable='between(t,0.75,5.75)'[v_out]")
        current_stream = "[v_out]"
    else:
        # If no image overlay, we just map the last stream to output
        filter_commands.append(f"{current_stream}copy[v_out]")
        current_stream = "[v_out]"

    # Compile the final graph string
    filter_complex = ";".join(filter_commands)
    
    # 3. Render Command
    cmd = [
        FFMPEG_BIN, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", current_stream,
        "-map", "0:a?", # Map audio if it exists, otherwise ignore
        "-c:v", "libx264", 
        "-preset", REENCODE_PRESET, 
        "-crf", REENCODE_CRF,
        "-c:a", "copy",
        output_path
    ]
    
    # Only trim audio if we trimmed video to maintain sync
    if trim_duration and trim_duration > 0:
         cmd.extend(["-t", str(trim_duration)])
    
    logger.info(f"🏎️ Single-Pass Pipeline Engine: {len(filter_commands)} stages | Tag: {bool(price_tag_image)}")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Single-Pass Render Failed. Command: {' '.join(cmd)}")
        logger.error(f"FFmpeg Error: {e.stderr.decode()}")
        return False
def render_juxtaposition(
    input_a: str,
    input_b: str,
    output_path: str,
    anchor_path: str = None,
    layout: str = "vertical" # or "horizontal"
) -> bool:
    """
    Renders two videos in a side-by-side or top-bottom juxtaposition.
    The 'Law-Bending' core of the Synthetic Newsroom.
    """
    if not os.path.exists(input_a) or not os.path.exists(input_b):
        logger.error(f"Juxtaposition failed: Inputs not found.")
        return False

    # Filter logic:
    # 1. Scale both to 1080x960 (if vertical)
    # 2. Stack them
    # 3. Overlay anchor if provided
    
    if layout == "vertical":
        # Split 1080x1920 into two 1080x960 sections
        filter_str = (
            "[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[v0];"
            "[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[v1];"
            "[v0][v1]vstack=inputs=2[base]"
        )
    else:
        # Side-by-side (Square-ish for each)
        filter_str = (
            "[0:v]scale=540:1920:force_original_aspect_ratio=increase,crop=540:1920[v0];"
            "[1:v]scale=540:1920:force_original_aspect_ratio=increase,crop=540:1920[v1];"
            "[v0][v1]hstack=inputs=2[base]"
        )

    inputs = ["-i", input_a, "-i", input_b]
    
    if anchor_path and os.path.exists(anchor_path):
        from .anchors import engine as anchor_engine
        inputs.extend(["-i", anchor_path])
        # Add anchor overlay to the chain
        # [base] is the stacked videos, [2:v] is the anchor
        host_filter = anchor_engine.get_overlay_filter()
        # Transform host filter to use common 'base' input
        host_filter = host_filter.replace("[0:v]", "[base]")
        filter_str += f";{host_filter}"
    else:
        filter_str += ";[base]null[out]"
        filter_str = filter_str.replace("[out]", "") # Clean up if no anchor

    cmd = [
        FFMPEG_BIN, "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-c:v", "libx264", "-preset", REENCODE_PRESET, "-crf", REENCODE_CRF,
        "-c:a", "copy",
        output_path
    ]

    logger.info(f"🚀 Rendering Juxtaposition ({layout})...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Juxtaposition Render Failed: {e.stderr.decode()}")
        return False
