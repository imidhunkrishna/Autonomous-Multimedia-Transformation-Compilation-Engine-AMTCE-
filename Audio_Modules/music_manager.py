
import os
import glob
import random
import logging
import json
from typing import List, Tuple, Dict
import subprocess

logger = logging.getLogger("music_manager")

class ContinuousMusicManager:
    """
    Manages a continuous music timeline for a batch of videos.
    State is specific to an instance (one compilation job).
    """
    def __init__(self, music_dir: str = "music"):
        self.music_dir = music_dir
        self.playlist = self._load_playlist()
        
        # State
        self.current_track_index = 0
        # Per-Track Cursor State (The "Bookmark" for each song)
        # { "music/song1.mp3": 15.0, "music/song2.mp3": 0.0 }
        self.track_offsets = {p: 0.0 for p in self.playlist}
        
        # Shuffle on init to ensure variety per compilation
        if self.playlist:
            random.shuffle(self.playlist)
            # Re-init offsets after shuffle just to be safe (keys match)
            self.track_offsets = {p: 0.0 for p in self.playlist}
        
        self.track_durations = {} # Cache

    def _load_playlist(self) -> List[str]:
        if not os.path.exists(self.music_dir):
            logger.warning(f"⚠️ Music directory not found: {self.music_dir}")
            return []
        files = glob.glob(os.path.join(self.music_dir, "*.mp3")) + \
                glob.glob(os.path.join(self.music_dir, "*.wav"))
        
        # Filter out corrupted or suspiciously small files (< 1KB)
        valid_files = []
        for f in files:
            if os.path.exists(f) and os.path.getsize(f) > 1024:
                valid_files.append(f)
            else:
                logger.warning(f"⚠️ Skipping corrupted or empty track: {os.path.basename(f)} ({os.path.getsize(f) if os.path.exists(f) else 0} bytes)")
        
        # Log loaded tracks to debug source confusion
        if valid_files:
            logger.info(f"🎵 Music Manager loaded {len(valid_files)} tracks from '{self.music_dir}':")
            # Log first 3 to safe space
            for f in valid_files[:3]:
                 logger.info(f"    └─ {os.path.basename(f)}")
            if len(valid_files) > 3: logger.info(f"    └─ ... and {len(valid_files)-3} more.")
        else:
            logger.warning(f"⚠️ No valid music files found in '{self.music_dir}'")
            
        return sorted(valid_files) 

    def get_best_match(self, profile_data: Dict) -> str:
        """
        Intelligent Music Selector.
        Attempts to match video profile with music genres.
        Falls back to Round-Robin allocation if no match found.
        """
        if not self.playlist: return None
        
        try:
            from Audio_Modules.music_intelligence import classify_music
            
            # Simple keyword extraction from profile
            keywords = []
            if profile_data.get('trend_text'): keywords.append(profile_data['trend_text'].lower())
            if profile_data.get('title'): keywords.append(profile_data['title'].lower())
            
            target_genre = "neutral"
            if any(k in " ".join(keywords) for k in ["viral", "phonk", "bass", "gym", "workout"]):
                target_genre = "mass"
            elif any(k in " ".join(keywords) for k in ["lofi", "chill", "relax", "aesthetic"]):
                target_genre = "lofi"
            elif any(k in " ".join(keywords) for k in ["luxury", "slow", "moody", "noir"]):
                target_genre = "romantic"

            # Check all tracks for a match
            for track_path in self.playlist:
                genre, conf = classify_music(track_path)
                if genre == target_genre and conf > 0.6:
                    logger.info(f"🎯 Music Match Found! Genre: {genre} Path: {os.path.basename(track_path)}")
                    # Move cursor to this track for future round-robin consistency if needed
                    # but for now we just return the path as orchestrator expects a string
                    return track_path

        except Exception as e:
            logger.warning(f"⚠️ Music matching intelligence failed: {e}")

        # Fallback to standard round-robin allocation logic
        # Since orchestrator expects just a path string from get_best_match
        # but allocate_music returns a list of dicts, we just use the RR path
        return self.get_next_track_path()

    def get_next_track_path(self) -> str:
        """Returns the path of the next track to be played (for Beat Analysis)."""
        if not self.playlist: return None
        return self.playlist[self.current_track_index % len(self.playlist)]

    def _get_duration(self, path: str) -> float:
        """Get duration with caching"""
        if path in self.track_durations:
            return self.track_durations[path]
            
        try:
             cmd = [
                 "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                 "-of", "default=noprint_wrappers=1:nokey=1", path
             ]
             res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
             dur = float(res.decode().strip())
             self.track_durations[path] = dur
             return dur
        except Exception as e:
            logger.warning(f"Failed to get duration for {os.path.basename(path)}: {e}")
            return 30.0 # Safety default

    def allocate_music(self, needed_duration: float) -> List[Dict]:
        """
        Allocates music in a ROUND-ROBIN fashion with STATE PERSISTENCE.
        Clip 1 -> Track A (0-15s)
        Clip 2 -> Track B (0-15s)
        Clip 3 -> Track A (15-30s) <- Continues where it left off!
        """
        if not self.playlist:
            return []

        # 1. Select Track (Round Robin)
        track_path = self.playlist[self.current_track_index]
        track_path = os.path.abspath(track_path)
        
        # 2. Get Saved State for THIS track
        current_offset = self.track_offsets.get(track_path, 0.0)
        total_track_dur = self._get_duration(track_path)
        
        # 3. Calculate Segment
        # Logic: If needed_dur fits, take it.
        # If not fits (song ends), we loop back to start of SAME song? 
        # Or just take what we can and loop?
        # Simplest consistent implementation: 
        # If (start + needed) > total, we just reset start to 0 for this block.
        # (Avoids complex stitching for now, keeps audio clean).
        
        start_time = current_offset
        if (start_time + needed_duration) > total_track_dur:
            start_time = 0.0 # Reset to beginning of song
            logger.info(f"🔄 Track {os.path.basename(track_path)} looped/reset.")
            
        # 4. Update State for THIS track
        self.track_offsets[track_path] = start_time + needed_duration
        
        # 5. Move Global Cursor to NEXT track (Round Robin)
        self.current_track_index = (self.current_track_index + 1) % len(self.playlist)
        
        logger.info(f"🎵 Allocated [RR]: {os.path.basename(track_path)} ({start_time:.1f}-{start_time+needed_duration:.1f}s)")
        
        return [{
            "path": track_path,
            "start": start_time,
            "duration": needed_duration
        }]
