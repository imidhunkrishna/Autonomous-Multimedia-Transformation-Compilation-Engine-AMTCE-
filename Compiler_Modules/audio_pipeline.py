import os
import logging
import subprocess
import random
import glob

logger = logging.getLogger("audio_pipeline")

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

def mix_audio(
    video_path: str,
    output_path: str,
    voiceover_path: str = None,
    music_path: str = None,
    music_vol: float = 0.2,
    vo_vol: float = 1.5
) -> bool:
    """
    Mixes Voiceover + Background Music + Original Audio
    """
    inputs = []
    filter_complex = ""
    
    # 0. Video (Stream 0)
    inputs.extend(["-i", video_path])
    
    # 1. Voiceover (Stream 1)
    has_vo = False
    if voiceover_path and os.path.exists(voiceover_path):
        inputs.extend(["-i", voiceover_path])
        has_vo = True
        
    # 2. Music (Stream 2)
    has_music = False
    if music_path and os.path.exists(music_path):
        inputs.extend(["-i", music_path])
        has_music = True
        
    # Map Logic
    # [0:a] volume=1.0 [orig]
    # [1:a] volume=vo_vol [vo]
    # [2:a] volume=music_vol, aloop=loop=-1:size=2e+09 [mus] (Loop music)
    
    if not has_vo and not has_music:
        # Just copy
        return False # No mixing needed
        
    steps = []
    
    # Define intermediate streams
    # [0:a] Original video audio (Lowered to background level)
    # [1:a] Voiceover (Narrator)
    # [2:a] Music (Background)
    
    # 1. Prepare Original Audio
    # [a_orig_raw] might be missing if video has no audio. We use anullsrc if needed.
    # But for now, we assume [0:a] exists or it will error (which is handled by mix_success check).
    steps.append("[0:a]volume=0.2[a_orig]")
    
    if has_vo and has_music:
        # 2. Sidechain Compression (Ducking)
        # We need to split VO because it's used as BOTH a trigger and a mix input
        steps.append(f"[1:a]volume={vo_vol},asplit=2[a_vo_trig][a_vo_mix]")
        steps.append(f"[2:a]volume={music_vol}[a_mus_pre]")
        # threshold=0.1, ratio=4.0, release=700
        steps.append("[a_mus_pre][a_vo_trig]sidechaincompress=threshold=0.1:ratio=4:attack=20:release=700[a_mus_duck]")
        # 3. Final Mix (Order: [a_orig] first to control duration)
        steps.append("[a_orig][a_vo_mix][a_mus_duck]amix=inputs=3:duration=first:dropout_transition=2[a_mixed]")
    elif has_vo:
        steps.append(f"[1:a]volume={vo_vol}[a_vo]")
        steps.append("[a_orig][a_vo]amix=inputs=2:duration=first[a_mixed]")
    elif has_music:
        # Logic fix: If no VO, music is input [1:a]
        steps.append(f"[1:a]volume={music_vol}[a_mus]")
        steps.append("[a_orig][a_mus]amix=inputs=2:duration=first[a_mixed]")
    else:
        return False

    # 4. Professional Loudness Normalization (EBU R128)
    steps.append("[a_mixed]loudnorm=I=-16:TP=-1.5:LRA=11[outa]")
    
    filter_complex = ";".join(steps)
    
    cmd = [
        FFMPEG_BIN, "-y",
    ]
    
    # Construct Inputs
    cmd.extend(["-i", video_path])
    if has_vo: cmd.extend(["-i", voiceover_path])
    if has_music: cmd.extend(["-stream_loop", "-1", "-i", music_path])
    
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[outa]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path
    ])
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio Mix Failed: {e.stderr.decode()}")
        return False
