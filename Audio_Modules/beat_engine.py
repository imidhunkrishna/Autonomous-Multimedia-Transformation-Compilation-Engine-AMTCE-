"""
Beat Engine
-----------
Zero-dependency Beat Detection for Viral Edits.
Uses FFmpeg to decode audio to raw PCM/WAV, then analyzes amplitude peaks using standard Python libraries.

Usage:
    beats = beat_engine.analyze_beats("music.mp3")
    # beats = [0.54, 1.23, ...] (Seconds)
"""

import os
import logging
import subprocess
import wave
import struct
import math
import tempfile
import shutil
from typing import List

logger = logging.getLogger("beat_engine")

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

class BeatEngine:
    def __init__(self):
        self.sensitivity = 1.3 # Multiplier above local average to count as beat
        self.min_beat_interval = 0.4 # Minimum seconds between beats (prevent rapid fire)
        self.window_size = 0.05 # 50ms window for smoothing

    def analyze_beats(self, audio_path: str) -> List[float]:
        """
        Analyzes an audio file and returns a list of significant beat timestamps.
        """
        if not os.path.exists(audio_path):
            logger.error(f"❌ Audio file not found: {audio_path}")
            return []

        # 0. Size Check
        if os.path.getsize(audio_path) < 1024:
            logger.error(f"❌ Audio file is too small or corrupted: {audio_path} ({os.path.getsize(audio_path)} bytes)")
            return []

        # 1. Convert to temporary WAV (16-bit PCM, Mono, 44.1kHz)
        # We use a temp file
        fd, temp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            cmd = [
                FFMPEG_BIN, "-y", "-i", audio_path,
                "-ac", "1", # Mono
                "-ar", "44100", # 44.1kHz
                "-acodec", "pcm_s16le", # 16-bit raw PCM
                temp_wav
            ]
            
            # Run ffmpeg and capture errors
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True)
            
            # 2. Analyze PCM Data
            return self._process_wav(temp_wav)

        except subprocess.CalledProcessError as e:
            logger.error(f"⚠️ Beat analysis failed (FFmpeg Error): {e.stderr if e.stderr else str(e)}")
            logger.error(f"   └─ Command: {' '.join(cmd)}")
            return []
        except Exception as e:
            logger.error(f"⚠️ Beat analysis failed: {e}")
            return []
        finally:
            if os.path.exists(temp_wav):
                try: os.remove(temp_wav)
                except: pass

    def _process_wav(self, wav_path: str) -> List[float]:
        beats = []
        try:
            with wave.open(wav_path, 'rb') as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                sampwidth = wf.getsampwidth() # Should be 2 (16-bit)
                
                if sampwidth != 2:
                    logger.warning("⚠️ WAV is not 16-bit. Skipping.")
                    return []

                # Read all frames (memory safe for typical 3-5min songs ~30MB)
                raw_data = wf.readframes(nframes)
                
                # Convert to integers
                # 'h' = short (2 bytes)
                count = len(raw_data) // 2
                fmt = f"<{count}h" 
                samples = struct.unpack(fmt, raw_data)
                
                # Calculate Envelope (RMS / Amplitude)
                # We group samples into windows
                window_samples = int(framerate * self.window_size)
                envelopes = []
                
                for i in range(0, len(samples), window_samples):
                    chunk = samples[i:i+window_samples]
                    if not chunk: continue
                    
                    # RMS calculation
                    sum_sq = sum(s*s for s in chunk)
                    rms = math.sqrt(sum_sq / len(chunk))
                    envelopes.append(rms)

                # Peak Detection
                # Calculate local average to determine threshold
                # Simple Moving Average
                local_window = 40 # Look at ~2 seconds context (40 * 50ms)
                
                last_beat_time = -self.min_beat_interval
                
                for i, amp in enumerate(envelopes):
                    # Context window
                    start = max(0, i - local_window // 2)
                    end = min(len(envelopes), i + local_window // 2)
                    context = envelopes[start:end]
                    avg_energy = sum(context) / len(context) if context else 0
                    
                    # Threshold logic
                    threshold = avg_energy * self.sensitivity
                    
                    # Time of this window
                    time_sec = i * self.window_size
                    
                    if amp > threshold and amp > 1000: # Must be somewhat loud
                        # Check debounce
                        if time_sec - last_beat_time >= self.min_beat_interval:
                            beats.append(time_sec)
                            last_beat_time = time_sec
                            
            logger.info(f"🥁 Detected {len(beats)} beats in track.")
            return beats

        except Exception as e:
            logger.error(f"❌ WAV processing failed: {e}")
            return []

# Global Instance
engine = BeatEngine()

def get_beats(path: str) -> List[float]:
    return engine.analyze_beats(path)
