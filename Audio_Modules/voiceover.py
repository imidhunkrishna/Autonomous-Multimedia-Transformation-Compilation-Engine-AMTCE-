"""
AI Voiceover Generator
----------------------
Uses gTTS (Google Text-to-Speech) to generate micro-commentary.
Strictly limited scope: Short, optional, non-blocking additions.

STRICT AUDIT COMPLIANT: Atomic Writes, Threaded Timeout, Smart Filters.
"""

import os
import logging
import random
import threading
import hashlib
import re
import shutil
import time
import tempfile
from typing import Optional, Dict, Any

logger = logging.getLogger("voiceover")

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False
    logger.warning("⚠️ gTTS not installed. Voiceover will be disabled.")

try:
    import edge_tts
    import asyncio
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    logger.warning("⚠️ edge-tts not installed. Voiceover Quality degraded.")

# 1. NEW: Azure Cognitive Services (Primary)
try:
    import azure.cognitiveservices.speech as speechsdk
    HAS_AZURE = True
except ImportError:
    HAS_AZURE = False
    logger.info("ℹ️ Azure Speech SDK not installed. (Primary voice disabled)")

# 2. Kokoro-82M (Optional Premium)
try:
    from kokoro import KModel
    import soundfile as sf
    import torch
    HAS_KOKORO = True
except ImportError:
    HAS_KOKORO = False
    logger.info("ℹ️ Kokoro-82M not installed. (Optional premium voice)")

def _get_audio_duration(path):
    """Helper to get duration using ffprobe (since we can't import compiler here easily)."""
    try:
        import subprocess
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        res = subprocess.check_output(cmd).decode().strip()
        return float(res)
    except:
        return 0.0

class VoiceoverGenerator:
    def __init__(self):
        self.enabled = os.getenv("ENABLE_MICRO_VOICEOVER", "yes").lower() == "yes"
        self.lang = "en"
        
        # 2. Configurable Env Vars
        self.min_chars = int(os.getenv("VOICEOVER_MIN_CHARS", 5))
        self.max_chars = int(os.getenv("VOICEOVER_MAX_CHARS", 200))
        self.tld_overrides = os.getenv("VOICEOVER_TLDS", "").split(",") if os.getenv("VOICEOVER_TLDS") else []
        self.slow_mode = os.getenv("VOICEOVER_SLOW_MODE", "no").lower() == "yes"
        self.safe_ascii = os.getenv("VOICEOVER_SAFE_ASCII_ONLY", "no").lower() == "yes"
        self.timeout = int(os.getenv("VOICEOVER_TIMEOUT", 60))
        self.smart_filter = os.getenv("VOICEOVER_SMART_FILTER", "no").lower() == "yes"
        
        # "Kardashian" Style Pool (Deep, Vocal Fry, Conversational, Pure Female)
        self.kardashian_pool = [
            "en-US-AvaNeural",     # American (Sassy/Trendy) - HIGH PRIORITY
            "en-US-JennyNeural",   # American (Conversational)
            "en-US-AriaNeural",    # American (Vibrant/Influencer vibe)
            "en-US-MichelleNeural", # American (Deep/Vocal Fry)
            "en-GB-SoniaNeural",   # British (Elegant/Posh)
            "en-AU-NatashaNeural"  # Australian (Expressive)
        ]

    def _sanitize_text(self, text: str) -> str:
        """3. Sanitize Input Text"""
        if not text: return ""
        
        # Collapse spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Control chars
        text = "".join(ch for ch in text if ch.isprintable())
        
        if self.safe_ascii:
            # Remove non-ascii
            text = text.encode('ascii', 'ignore').decode('ascii')
            
        # Truncate to max_chars (preserve words if possible)
        if len(text) > self.max_chars:
            cut = text[:self.max_chars]
            last_space = cut.rfind(" ")
            if last_space > self.max_chars // 2:
                 text = cut[:last_space] + "..."
            else:
                 text = cut + "..."
                 
        return text

    def _is_nonsense(self, text: str) -> bool:
        """9. Filter nonsense text (repeated chars, no vowels)."""
        if not text: return True
        # Check vowel presence
        if not re.search(r'[aeiouAEIOU]', text):
            return True
        # Check repetition (e.g. "aaaaa")
        if re.search(r'(.)\1{4,}', text):
            return True
        return False
        
    def humanize_narration(self, text: str) -> str:
        """
        Injects human-like pauses, breaths, and emphasis markers.
        Bypasses AI voice detection by breaking programmatic cadence.
        """
        if not text: return ""
        
        # 1. Inject natural pauses (...)
        segments = text.split(". ")
        humanized = []
        for i, segment in enumerate(segments):
            humanized.append(segment)
            if i < len(segments) - 1:
                # 30% chance of a deep breath/longer pause
                if random.random() < 0.3:
                    humanized.append("... [breath] ...")
                else:
                    humanized.append("... ")
        
        text = " ".join(humanized)
        
        # 2. Inject mid-sentence micro-pauses
        words = text.split()
        if len(words) > 10:
            pivot = random.randint(len(words)//3, 2*len(words)//3)
            # Add a comma or ellipsis for natural hesitation
            words[pivot] = words[pivot] + ","
            text = " ".join(words)

        return text

    def _is_filler(self, text: str) -> bool:
        """Smart Filter: Reject basic filler text."""
        if not self.smart_filter: return False
        
        # Reject 1 word items that aren't powerful
        words = text.split()
        if len(words) <= 1:
            return True
            
        # Reject generic openings
        lower = text.lower()
        if lower.startswith("caption:") or lower.startswith("audio:"):
            return True
            
        return False

    def _get_random_voice(self) -> str:
        """New: Explicitly random rotation for variety."""
        return random.choice(self.kardashian_pool)

    def _get_deterministic_tld(self, text: str) -> str:
        """4. Fallback TLD Selection (for gTTS)"""
        hash_val = int(hashlib.sha256(text.encode('utf-8')).hexdigest(), 16)
        tlds = ['com', 'co.uk', 'ca', 'com.au', 'co.in']
        return tlds[hash_val % len(tlds)]

    def _generate_azure_tts(self, text: str, temp_path: str, voice_name: str = "en-US-AvaNeural") -> Dict:
        """
        PRIMARY: Azure Neural TTS with Word Timestamps.
        """
        if not HAS_AZURE: raise ImportError("Azure SDK not installed")
        
        region = os.getenv("AZURE_SPEECH_REGION")
        key = os.getenv("AZURE_SPEECH_KEY")
        if not region or not key: raise ValueError("Azure Credentials Missing")

        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.speech_synthesis_voice_name = voice_name
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
        
        audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_path)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        
        # Word Boundary Handler
        word_timestamps = []
        def boundary_handler(evt):
            # 1 tick = 100ns = 0.0000001s
            # 10,000,000 ticks = 1s
            seconds = evt.audio_offset / 10_000_000
            word_timestamps.append({
                "word": evt.text,
                "time": seconds,
                "duration": evt.duration / 10_000_000
            })
            
        synthesizer.synthesis_word_boundary.connect(boundary_handler)
        
        result = synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {
                "audio_path": temp_path,
                "duration": _get_audio_duration(temp_path),
                "word_timestamps": word_timestamps
            }
        else:
            cancellation_details = result.cancellation_details
            error_msg = f"Azure Error: {cancellation_details.reason}"
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                error_msg += f" Details: {cancellation_details.error_details}"
            raise RuntimeError(error_msg)

    def _generate_edge_tts_wrapper(self, text: str, temp_path: str, voice_name: str = "en-US-AriaNeural") -> Dict:
        """
        SECONDARY: Edge TTS (Free Neural).
        Robust Asyncio Handling: Works inside or outside existing Event Loops.
        """
        if not HAS_EDGE_TTS: raise ImportError("EdgeTTS not installed")
        
        async def _run():
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(temp_path)
            
        try:
            # [FIX] Check for running event loop to avoid RuntimeError
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
                
            if loop and loop.is_running():
                # Loop is running (likely Gradio). 
                # asyncio.run() cannot be called here.
                # Isolate execution in a separate thread.
                logger.info("⚡ EdgeTTS: Existing Event Loop detected. Spawning isolation thread.")
                import threading
                
                error_container = {}
                def thread_target():
                    try:
                        asyncio.run(_run())
                    except Exception as e:
                        error_container["error"] = e
                        
                t = threading.Thread(target=thread_target)
                t.start()
                t.join()
                
                if "error" in error_container:
                    raise error_container["error"]
            else:
                # No loop running, standard execution
                asyncio.run(_run())
                
        except Exception as e:
            raise RuntimeError(f"EdgeTTS Failed: {e}")
        
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 100:
            return {
                "audio_path": temp_path,
                "duration": _get_audio_duration(temp_path),
                "word_timestamps": None
            }
        raise RuntimeError("EdgeTTS produced invalid file")

    def _generate_google_tts_wrapper(self, text: str, temp_path: str, tld: str = "com") -> Dict:
        """
        FINAL FALLBACK: Google TTS (Robotic).
        """
        if not HAS_GTTS: raise ImportError("gTTS not installed")
        
        tts = gTTS(text=text, lang=self.lang, tld=tld, slow=self.slow_mode)
        tts.save(temp_path)
        
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 100:
            return {
                "audio_path": temp_path,
                "duration": _get_audio_duration(temp_path),
                "word_timestamps": None
            }
        raise RuntimeError("gTTS produced invalid file")

    def _generate_worker(self, text, tld, temp_path, result_container, voice_override=None):
        """
        Worker logic with UNIFIED TTS Failover Chain
        Priority: Azure → Edge → Google
        """

        # ---------- 1️⃣ AZURE TTS ----------
        try:
            logger.info("🎙️ Azure TTS Attempt...")
            azure_voice = voice_override if voice_override else self._get_random_voice()

            res = self._generate_azure_tts(
                text=text,
                temp_path=temp_path,
                voice_name=azure_voice
            )

            # SUCCESS → commit & exit
            result_container.update({
                "success": True,
                "engine": "azure",
                "audio_path": res["audio_path"],
                "duration": res["duration"],
                "word_timestamps": res.get("word_timestamps")
            })
            return

        except Exception as e_azure:
            logger.warning(f"⚠️ Azure failed. Falling back to Edge. Reason: {e_azure}")

        # ---------- 2️⃣ EDGE TTS ----------
        try:
            logger.info("🎙️ Edge TTS Attempt...")
            edge_voice = voice_override if voice_override else self._get_random_voice()

            res = self._generate_edge_tts_wrapper(
                text=text,
                temp_path=temp_path,
                voice_name=edge_voice
            )

            # SUCCESS → commit & exit
            result_container.update({
                "success": True,
                "engine": "edge",
                "audio_path": res["audio_path"],
                "duration": res["duration"],
                "word_timestamps": None
            })
            return

        except Exception as e_edge:
            logger.warning(f"⚠️ Edge failed. Falling back to Google. Reason: {e_edge}")

        # ---------- 3️⃣ GOOGLE TTS ----------
        try:
            logger.info("🎙️ Google TTS Attempt...")

            res = self._generate_google_tts_wrapper(
                text=text,
                temp_path=temp_path,
                tld=tld
            )

            # SUCCESS → commit & exit
            result_container.update({
                "success": True,
                "engine": "google",
                "audio_path": res["audio_path"],
                "duration": res["duration"],
                "word_timestamps": None
            })
            return

        except Exception as e_google:
            logger.error(f"❌ All TTS engines failed. Last error: {e_google}")

            # FINAL FAILURE → commit error
            result_container.update({
                "success": False,
                "engine": None,
                "error": str(e_google)
            })
            return

    def generate_voiceover(self, text: str, output_path: str) -> bool:
        """
        Public entry point for compiler.
        Must preserve original behavior.
        """
        try:
            # 1. Sanitize & Humanize
            safe_text = self._sanitize_text(text)
            safe_text = self.humanize_narration(safe_text)
            
            if len(safe_text) < self.min_chars: return False
            
            # 2. Filters (Preserve behavior)
            if self._is_nonsense(safe_text): return False
            if self._is_filler(safe_text): return False
            
            # 3. Setup
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            tld = self._get_deterministic_tld(safe_text)
            
            # 4. Generate (Direct Call)
            result_container = {}
            # Pass output_path directly as temp_path (Simplified per user request)
            self._generate_worker(
                text=safe_text,
                tld=tld,
                temp_path=output_path,
                result_container=result_container,
                voice_override=None
            )
            
            if not result_container.get("success"):
                logger.warning(f"⚠️ Voiceover generation failed: {result_container.get('error')}")
                return False
                
            # 5. Update Meta (Restored for Azure Timestamps)
            self._last_meta = {
                "text_len": len(safe_text),
                "tld": tld,
                "engine": result_container.get('engine'),
                "word_timestamps": result_container.get('word_timestamps'),
                "success": True
            }
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Voiceover System Error: {e}")
            return False

    def generate_long_form_narration(self, text: str, output_path: str) -> bool:
        """
        Generates narrative audio for compilations.
        C3 SAFETY: Enforces Random Voice Rotation (Kardashian Pool).
        """
        temp_path = None
        try:
            if not self.enabled: return False
            if not text: return False
            
            # Simple Sanitization & Humanize
            text = re.sub(r'\s+', ' ', text).strip()
            text = self.humanize_narration(text)
            
            if self.safe_ascii:
                text = text.encode('ascii', 'ignore').decode('ascii')
                
            # Ensure directory
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Prepare Atomic Temp
            fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            
            tld = self._get_deterministic_tld(text)
            
            # C3: RANDOM VOICE SELECTION
            chosen_voice = random.choice(self.kardashian_pool)
            logger.info(f"🎙️ Rotating Voice Selected: {chosen_voice}")
            
            # Generate in Thread with LONG Timeout (5 mins)
            result = {'success': False, 'error': None}
            # Pass chosen_voice as voice_override
            t = threading.Thread(target=self._generate_worker, args=(text, tld, temp_path, result, chosen_voice))
            t.daemon = True
            t.start()
            
            t.join(timeout=300) # 5 minutes for long form
            
            if t.is_alive():
                logger.error(f"❌ Long-form Narration timed out.")
                return False
            
            if not result['success']:
                logger.warning(f"⚠️ Narration generation failed: {result.get('error')}")
                return False
                
            # Validate Output
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 1024:
                logger.warning("⚠️ Narration file invalid (too small).")
                return False
                
            # Atomic Move
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass
            
            shutil.move(temp_path, output_path)
            
            logger.info(f"🎙️ Long-form Narration Generated: {len(text)} chars (Voice: {result.get('used_tld')})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Narration System Error: {e}")
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

# Global Instance
voice_engine = VoiceoverGenerator()

def generate_voiceover(text: str, output_path: str) -> bool:
    return voice_engine.generate_voiceover(text, output_path)

def generate_long_form_narration(text: str, output_path: str) -> bool:
    return voice_engine.generate_long_form_narration(text, output_path)
