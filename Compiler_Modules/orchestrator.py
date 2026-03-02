import os
import logging
import json
import shutil
import uuid
import subprocess
import re
from datetime import datetime
from dotenv import load_dotenv # Fix: Load Env
from . import video_pipeline, audio_pipeline
from Text_Modules import text_overlay # Use Legacy Module

# Load Env from Credentials
env_path = os.path.join("Credentials", ".env")
load_dotenv(env_path)

try:
    from Audio_Modules import voiceover
    VOICEOVER_AVAILABLE = True
except ImportError:
    VOICEOVER_AVAILABLE = False

try:
    from Visual_Refinement_Modules import watermark_auto
    WATERMARK_AVAILABLE = True
except ImportError:
    WATERMARK_AVAILABLE = False

try:
    from Intelligence_Modules.monetization_brain import MonetizationStrategist
    BRAIN_AVAILABLE = True
except ImportError:
    BRAIN_AVAILABLE = False

# NOTE: Intelligence_Modules.generator is not yet wired into single-clip pipeline.
# It is used externally for compilation prediction. Left for future integration.
GENERATOR_AVAILABLE = False  # Set True when generator module is ready


try:
    from Text_Modules.gemini_captions import GeminiCaptionGenerator
    GEMINI_CAPTIONS_AVAILABLE = True
except ImportError:
    GEMINI_CAPTIONS_AVAILABLE = False

try:
    from Intelligence_Modules.quality_evaluator import QualityEvaluator
    QUALITY_EVAL_AVAILABLE = True
except ImportError:
    QUALITY_EVAL_AVAILABLE = False

try:
    from Audio_Modules.audio_processing import heavy_remix
    HEAVY_REMIX_AVAILABLE = True
except ImportError:
    HEAVY_REMIX_AVAILABLE = False

# --- AI ENHANCEMENT (GATED) ---
try:
    from Upscale_Modules import ai_engine
    HEAVY_AI_AVAILABLE = True
except ImportError:
    HEAVY_AI_AVAILABLE = False

# --- ANALYTICS OPTIMIZER (Upload Timing) ---
try:
    from Intelligence_Modules.analytics_optimizer import AnalyticsOptimizer
    _analytics_optimizer = AnalyticsOptimizer()
    ANALYTICS_AVAILABLE = True
except Exception:
    _analytics_optimizer = None
    ANALYTICS_AVAILABLE = False

# --- MUSIC MANAGER (Round-Robin with Bookmarks) ---
try:
    from Audio_Modules.music_manager import ContinuousMusicManager
    MUSIC_MANAGER_AVAILABLE = True
except Exception:
    MUSIC_MANAGER_AVAILABLE = False

# --- BEAT ENGINE (Zero-dep Beat Detection) ---
try:
    from Audio_Modules.beat_engine import BeatEngine
    _beat_engine = BeatEngine()
    BEAT_ENGINE_AVAILABLE = True
except Exception:
    _beat_engine = None
    BEAT_ENGINE_AVAILABLE = False

# --- SMART PRICE TAG ---
try:
    from Text_Modules.smart_price_tag import SmartPriceTag
    _price_tag_engine = SmartPriceTag()
    PRICE_TAG_AVAILABLE = True
except Exception:
    _price_tag_engine = None
    PRICE_TAG_AVAILABLE = False

# --- NARRATIVE BRAIN (Single-Clip Kardashian-style scripts) ---
try:
    from Intelligence_Modules.narrative_brain import NarrativeDirector
    NARRATIVE_BRAIN_AVAILABLE = True
except Exception:
    NARRATIVE_BRAIN_AVAILABLE = False

# --- OVERLAY ENGINE (Advanced Timed Stack Layout) ---
try:
    from Compiler_Modules.overlay_engine import OverlayEngine
    _overlay_engine = OverlayEngine()
    OVERLAY_ENGINE_AVAILABLE = True
except Exception:
    _overlay_engine = None
    OVERLAY_ENGINE_AVAILABLE = False

try:
    from Intelligence_Modules.adaptive_intelligence import AdaptiveBrain
    _adaptive_brain = AdaptiveBrain()  # Singleton — loads state from disk
    ADAPTIVE_BRAIN_AVAILABLE = True
except Exception:
    _adaptive_brain = None
    ADAPTIVE_BRAIN_AVAILABLE = False

# --- POLICY MEMORY (Stage Success Tracking) ---
try:
    from Intelligence_Modules.policy_memory import PolicyMemory
    _policy_db = PolicyMemory()  # Singleton
    POLICY_MEMORY_AVAILABLE = True
except Exception:
    _policy_db = None
    POLICY_MEMORY_AVAILABLE = False

# --- DECISION ENGINE (EV-Based Action Gating) ---
try:
    from Intelligence_Modules.decision_engine import DecisionEngine
    DECISION_ENGINE_AVAILABLE = True
except Exception:
    DECISION_ENGINE_AVAILABLE = False

logger = logging.getLogger("orchestrator")

def compile_video(
    uuid_str, 
    input_path, 
    output_path, 
    title, 
    description,
    profile_data={}
):
    """
    Main Orchestrator Function.
    Replaces the old 'compiler.py' monolithic logic.
    """
    # --- ADAPTIVE BRAIN: Get Execution Constraints for this job ---
    safe_mode_level = 0
    exec_constraints = {}
    psych_trigger = "viral"  # default caption style
    if ADAPTIVE_BRAIN_AVAILABLE and _adaptive_brain:
        try:
            exec_constraints = _adaptive_brain.get_execution_constraints()
            safe_mode_level = exec_constraints.get("safe_mode_level", 0)
            psych_trigger = _adaptive_brain.get_optimized_psychology() or "viral"
            logger.info(f"🧐 AdaptiveBrain: SafeMode={safe_mode_level} | Psychology='{psych_trigger}'")
        except Exception as _ab_e:
            logger.warning(f"⚠️ AdaptiveBrain init error: {_ab_e}")
    job_dir = os.path.join("temp", uuid_str)
    os.makedirs(job_dir, exist_ok=True)
    
    current_video_source = input_path
    
    # --- STEP 1: WATERMARK REMOVAL ---
    _wm_policy_ok = (not POLICY_MEMORY_AVAILABLE) or (not _policy_db) or _policy_db.is_enabled("watermark_removal")
    if WATERMARK_AVAILABLE and profile_data.get('remove_watermark', True) and _wm_policy_ok:
        logger.info(f"🛡️ [Step 1] Initiating Watermark Scan...")
        clean_path = os.path.join(job_dir, "clean_source.mp4")
        _wm_success = False
        try:
            # DecisionEngine: Gate inpainting action with EV logic
            _wm_confidence = 0.75  # Default assumption
            _proceed_inpaint = True
            if DECISION_ENGINE_AVAILABLE:
                _proceed_inpaint = DecisionEngine.should_proceed(_wm_confidence, "inpaint", threshold=0.0)
            
            if _proceed_inpaint:
                _rl = int(profile_data.get('retry_level', 0))
                wm_result = watermark_auto.process_video_with_watermark(input_path, clean_path, retry_mode=(_rl > 0), retry_level=_rl)
                if wm_result.get("success"):
                    logger.info(f"✅ Watermark Processing Complete. Using clean source.")
                    
                    # Capture exact coordinates of the removed watermark for the Smart Price Tag to use as camouflage
                    if "bbox" in wm_result and wm_result["bbox"]:
                        profile_data['watermark_bbox'] = wm_result["bbox"]
                        logger.info(f"🎯 Watermark Location Captured for Tag Camouflage: {wm_result['bbox']}")
                    # Quality gate: verify watermark removal didn't degrade video
                    if QUALITY_EVAL_AVAILABLE:
                        try:
                            qr = QualityEvaluator.evaluate_quality(input_path, clean_path)
                            if qr.get("status") == "HARD_FAIL":
                                logger.warning(f"⚠️ Quality Gate HARD_FAIL post-watermark ({qr.get('reasons')}) — User preference: Keeping clean source despite blur.")
                            
                            current_video_source = clean_path
                            _wm_success = True
                            logger.info(f"✅ Quality Gate Result (Score: {qr.get('score', '?')})")
                        except Exception as _qe:
                            logger.warning(f"⚠️ Quality eval error: {_qe}. Using clean source anyway.")
                            current_video_source = clean_path
                            _wm_success = True
                    else:
                        current_video_source = clean_path
                        _wm_success = True
                else:
                    logger.warning(f"⚠️ Watermark Check skipped/failed. Using original.")
            else:
                logger.warning("⛔ DecisionEngine blocked watermark inpainting (EV too low)")
        except Exception as e:
             logger.error(f"❌ Watermark Module Error: {e}")
        
        # Record outcome in PolicyMemory
        if POLICY_MEMORY_AVAILABLE and _policy_db:
            _policy_db.update_policy("watermark_removal", success=_wm_success)
    elif not _wm_policy_ok:
        logger.warning("🚫 PolicyMemory: 'watermark_removal' is DISABLED (low success rate). Skipping watermark step.")

    # --- STEP 1.4: AUDIO REMIX (Source Audio Enhancement) ---
    # heavy_remix is audio-only (-vn flag). We remix to a temp .aac, then mux it
    # back with the original video stream to produce a proper video+audio MP4.
    _remix_policy_ok = (not POLICY_MEMORY_AVAILABLE) or (not _policy_db) or _policy_db.is_enabled("heavy_remix")
    if HEAVY_REMIX_AVAILABLE and _remix_policy_ok:
        _remix_ok = False
        try:
            ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
            remixed_audio  = os.path.join(job_dir, "remixed_audio.aac")   # audio-only temp
            remixed_muxed  = os.path.join(job_dir, "remixed_source.mp4")  # final video+audio
            # Step A: Process audio (heavy_remix writes audio-only file)
            heavy_remix(current_video_source, remixed_audio, original_volume=1.1)
            # Step B: Mux remixed audio back with original video (no re-encode of video)
            if os.path.exists(remixed_audio) and os.path.getsize(remixed_audio) > 1000:
                mux_cmd = [
                    ffmpeg_bin, "-y",
                    "-i", current_video_source,   # original (for video stream)
                    "-i", remixed_audio,           # enhanced audio
                    "-map", "0:v:0",               # video from original
                    "-map", "1:a:0",               # audio from remix
                    "-c:v", "copy",                # no video re-encode (fast)
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    remixed_muxed
                ]
                import subprocess as _sp
                _mux = _sp.run(mux_cmd, capture_output=True, timeout=60)
                if _mux.returncode == 0 and os.path.exists(remixed_muxed):
                    # Validate the muxed file has a real video stream
                    _vprobe = video_pipeline.get_video_info(remixed_muxed)
                    if _vprobe.get("width") and _vprobe.get("height"):
                        current_video_source = remixed_muxed
                        _remix_ok = True
                        logger.info("🎚️ Source Audio Enhanced: bass/treble/compression applied")
                    else:
                        logger.warning("⚠️ Muxed remix has no video stream — keeping original")
                else:
                    err = _mux.stderr.decode(errors="replace")[:200] if _mux.stderr else ""
                    logger.warning(f"⚠️ Audio mux failed: {err}")
        except Exception as _re:
            logger.warning(f"⚠️ Heavy Remix failed (non-critical): {_re}")
        if POLICY_MEMORY_AVAILABLE and _policy_db:
            _policy_db.update_policy("heavy_remix", success=_remix_ok)


    # --- STEP 1.5: AI ENHANCEMENT (Restored "Heavy" Editor) ---
    # Only if profile requests it or env var FORCE_HEAVY is set
    should_enhance = profile_data.get('enhance', False) or os.getenv("FORCE_HEAVY_MODE", "no").lower() == "yes"
    
    logger.info(f"DEBUG: HeavyAvail={HEAVY_AI_AVAILABLE}, EnhanceReq={should_enhance}")

    if HEAVY_AI_AVAILABLE and should_enhance:
         logger.info(f"✨ [Step 1.5] AI Enhancement & Upscaling Initiated...")
         enhanced_path = os.path.join(job_dir, "enhanced_source.mp4")
         try:
             # Use Upscale Router (Gemini/GPU/CPU auto-dispatch) instead of ai_engine directly
             try:
                 from Upscale_Modules.router import run_enhancement as _route_enhance
                 _route_success = _route_enhance(current_video_source, enhanced_path)
                 logger.info("🛣️ Upscale Router dispatched (Gemini/GPU/CPU)")
             except Exception as _router_e:
                 logger.warning(f"⚠️ Upscale Router unavailable ({_router_e}), falling back to ai_engine")
                 editor = ai_engine.HeavyEditor()
                 _route_success = editor.process_video(current_video_source, enhanced_path)

             if _route_success and os.path.exists(enhanced_path):
                 logger.info(f"✅ AI Enhancement Success. Input switched to enhanced version.")
                 current_video_source = enhanced_path
             else:
                 logger.warning(f"⚠️ AI Enhancement failed or produced no output. Skipping.")
         except Exception as e:
             logger.error(f"❌ AI Engine Crash: {e}")

    # --- STEP 1.6: EDGE CROP (5% - Remove Edge Noise/Logos) ---
    try:
        logger.info("✂️ Applying Edge Crop (Factor: 0.05)...")
        crop_path = os.path.join(job_dir, "cropped_source.mp4")
        ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
        crop_cmd = [
            ffmpeg_bin, "-y", "-i", current_video_source,
            "-vf", "crop=in_w*0.95:in_h*0.95:(in_w-in_w*0.95)/2:(in_h-in_h*0.95)/2,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "copy",
            crop_path
        ]
        subprocess.run(crop_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)

        # Validate crop output has a real video stream before promoting it
        crop_ok = False
        if os.path.exists(crop_path) and os.path.getsize(crop_path) > 10_000:
            _probe = video_pipeline.get_video_info(crop_path)
            if _probe.get("width") and _probe.get("height"):
                crop_ok = True

        if crop_ok:
            current_video_source = crop_path
            logger.info(f"✅ Edge Crop OK: {_probe['width']}×{_probe['height']}")
        else:
            logger.warning("⚠️ Edge Crop output invalid — keeping original source")
    except subprocess.TimeoutExpired:
        logger.warning("⚠️ Edge Crop timed out — keeping original source")
    except Exception as _ce:
        logger.warning(f"⚠️ Edge Crop failed (non-critical): {_ce}")


    # --- STEP 2: BRAIN ANALYSIS (Restored) ---
    # Only run if we don't have explicit overlay data yet
    # We check if profile_data has 'brand_text' etc.
    if BRAIN_AVAILABLE and not profile_data.get('brand_text'):
        logger.info(f"🧠 [Step 2] Invoking Monetization Brain...")
        try:
            # We need duration check
            try:
                # We haven't imported get_video_info here yet, it's in video_pipeline
                vid_info = video_pipeline.get_video_info(current_video_source)
                duration = vid_info.get("duration", 15.0)
            except: duration = 15.0 
            
            brain = MonetizationStrategist()
            
            # Extract 3 frames from the actual video so Brain can SEE the clip
            frame_paths = []
            try:
                import cv2
                _cap = cv2.VideoCapture(current_video_source)
                _total = int(_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                _fps = _cap.get(cv2.CAP_PROP_FPS) or 30
                # Sample at 20%, 50%, 80% of the video
                for _pct in [0.20, 0.50, 0.80]:
                    _cap.set(cv2.CAP_PROP_POS_FRAMES, int(_total * _pct))
                    _ok, _fr = _cap.read()
                    if _ok:
                        _fp = os.path.join(job_dir, f"brain_frame_{int(_pct*100)}.jpg")
                        cv2.imwrite(_fp, _fr)
                        frame_paths.append(_fp)
                _cap.release()
                logger.info(f"📸 Brain Frames Extracted: {len(frame_paths)} frames")
            except Exception as _fe:
                logger.warning(f"⚠️ Frame extraction for brain failed: {_fe}")

            # Analyze — pass real frames so Brain actually sees the clip
            analysis = brain.analyze_content(title, duration=duration, image_paths=frame_paths if frame_paths else None)
            
            if analysis:
                logger.info(f"🧠 Brain Result: {analysis.get('verdict')} (Risk: {analysis.get('risk_level')})")
                
                # Merge Brain Data into Profile
                profile_data['raw_analysis'] = analysis
                brain_overlays = analysis.get('overlay_data', {})
                profile_data['brand_text'] = brain_overlays.get('brand_text', 'Style Analysis')
                profile_data['trend_text'] = brain_overlays.get('trend_text', 'Viral Trend')
                profile_data['item_name'] = brain_overlays.get('item_name') or brain_overlays.get('commercial_item_name')
                profile_data['price_tag'] = brain_overlays.get('price_tag')
                
                # Use context_text from overlay_data first, then fallback
                desc_ctx = brain_overlays.get('context_text') or analysis.get('entities', {}).get('event_context') or description[:20]
                profile_data['context_text'] = desc_ctx
                
                # Also set the caption/voiceover script if needed
                if not profile_data.get('editorial_script'):
                    profile_data['editorial_script'] = analysis.get('editorial_script')
                    
                # Extract Bounding Box for Smart Price Tag tracking
                _entities = analysis.get('entities', {})
                _bbox = _entities.get('subject_bbox') or _entities.get('item_bbox')
                if _bbox and len(_bbox) == 4:
                    profile_data['human_bbox'] = _bbox
                    logger.info(f"🎯 Vision Tracker: Bounding Box Acquired {_bbox}")
                    
        except Exception as e:
            logger.error(f"❌ Brain Analysis Failed: {e}")
            profile_data['brand_text'] = "Style Analysis"
            profile_data['context_text'] = "Fashion Edit"

    # --- STEP 2.5: GENERATIVE PREDICTION ANCHOR (THE 60% DEFENSE) ---
    prediction_frame = None
    if GENERATOR_AVAILABLE and profile_data.get('editorial_script'):
        logger.info(f"🔮 [Step 2.5] Synthesizing Prediction Anchor (60% YPP)...")
        try:
            pred_path = os.path.join(job_dir, "prediction_anchor.jpg")
            # Run async generator in a thread
            import asyncio
            async def run_gen():
                return await generator.engine.generate_future_concept(profile_data['editorial_script'], pred_path)
            
            prediction_frame = asyncio.run(run_gen())
            if prediction_frame:
                logger.info(f"✅ Prediction Anchor Synthesized: {prediction_frame}")
        except Exception as e:
            logger.error(f"❌ Prediction Synthesis Failed: {e}")
    
    try:
        # --- ANALYTICS OPTIMIZER: Log optimal upload window ---
        if ANALYTICS_AVAILABLE and _analytics_optimizer:
            try:
                _opt_time = _analytics_optimizer.get_optimal_upload_time()
                if _opt_time:
                    logger.info(f"📈 AnalyticsOptimizer: Best upload window → {_opt_time}")
            except Exception as _aoe:
                logger.warning(f"⚠️ AnalyticsOptimizer failed: {_aoe}")

        logger.info(f"🚀 Starting Compilation Job: {uuid_str}")
        
        # 1. Pipeline Config
        # Use profile data (Brain) or fallbacks
        full_script = profile_data.get('editorial_script') or ""
        
        # --- NARRATIVE BRAIN FALLBACK ---
        # If brain didn't produce a script, use NarrativeDirector for rich single-clip narration
        if NARRATIVE_BRAIN_AVAILABLE and (not full_script or len(full_script) < 30):
            try:
                _nd = NarrativeDirector()
                _asset = [{"title": title, "description": description, "path": input_path}]
                _narr = _nd.generate_compilation_script(_asset)
                if _narr and isinstance(_narr, dict):
                    _narr_script = _narr.get("script") or _narr.get("narration") or ""
                    if _narr_script and len(_narr_script) > 30:
                        full_script = _narr_script
                        logger.info(f"🎬 NarrativeBrain Script: '{full_script[:80]}...'")
            except Exception as _nbe:
                logger.warning(f"⚠️ NarrativeBrain failed: {_nbe}")

        # Smart Caption Decision (Editorial Enhancement)
        # We skip the first sentence if it's just the title to avoid redundant text on screen.
        if full_script and len(full_script.strip()) > 10:
             _sentences = [s.strip() for s in full_script.replace('!', '.').replace('?', '.').split('.') if s.strip()]
             _title_clean = re.sub(r'[^\w\s]', '', title).strip().lower()
             
             candidate = ""
             if _sentences:
                  # If first sentence is just the name/title (ignoring punctuation), skip to the actual insight
                  first_sent_clean = re.sub(r'[^\w\s]', '', _sentences[0]).strip().lower()
                  
                  if (first_sent_clean == _title_clean or _title_clean in first_sent_clean) and len(_sentences) > 1:
                       candidate = " ".join(_sentences[1:3])
                       logger.info(f"📝 Caption Decision: Skipping redundant first sentence ('{_sentences[0]}')")
                  else:
                       candidate = " ".join(_sentences[0:2])
             else:
                  candidate = full_script
                  
             # Final validation: don't show if still redundant or too short
             if candidate.strip().lower() == _title_clean or len(candidate) < 5:
                  has_caption = False
                  final_caption = ""
                  logger.info("📝 Caption Decision: HIDE | Reason: Redundant or empty")
             else:
                  final_caption = candidate[:120].strip()
                  has_caption = True
                  logger.info(f"📝 Caption Decision: SHOW ('{final_caption[:40]}...')")
        else:
             has_caption = False
             final_caption = ""
             logger.info("📝 Caption Decision: HIDE | Reason: No valid script")
        # Voiceover uses the FULL script (trimmed to 500 chars max for TTS speed)
        vo_full_text = full_script[:500] if full_script else title
        
        # 3. Gather All Visual Elements for Single-Pass Rendition
        mirror = profile_data.get('mirror', False) or os.getenv("MIRROR_VIDEO", "no").lower() == "yes"
        logger.info(f"🎨 Visuals: cinematic | Mirror: {mirror}")
        
        # A. Smart Trim (Cut 1s from start and end)
        vid_dur = video_pipeline.get_video_info(current_video_source).get("duration", 0)
        trim_dur = None
        if vid_dur > 4:
             trim_dur = vid_dur - 2.0
             logger.info(f"✂️ Smart Trim Queued: {trim_dur:.1f}s")
             
        # B. Smart Price Tag (Generate PNG overlay)
        _item_name = profile_data.get("item_name") or profile_data.get("clothing_category", "")
        _price_text = profile_data.get("price_estimate") or profile_data.get("price_tag", "")
        price_tag_image = None
        
        # 1. Prioritize Watermark Location (Camouflage Strategy)
        # 2. Fallback to Brain's Entity Detection (Human/Product)
        _human_box = profile_data.get("watermark_bbox") or profile_data.get("human_bbox")
        _location_hint = "unknown" if profile_data.get("watermark_bbox") else "torso"
        
        _vid_w2 = video_pipeline.get_video_info(current_video_source).get("width", 1080)
        _vid_h2 = video_pipeline.get_video_info(current_video_source).get("height", 1920)
        
        # Fallback to center-right if no AI bounding box was detected
        if not _human_box:
              _human_box = [int(_vid_w2*0.3), int(_vid_h2*0.2), int(_vid_w2*0.4), int(_vid_h2*0.6)]
        
        # Check if the user globally enabled the price tag in .env (defaults to 'yes')
        _tag_enabled = os.getenv("ENABLE_PRICE_TAG", "yes").strip().lower() == "yes"
        
        if _tag_enabled and PRICE_TAG_AVAILABLE and _price_tag_engine and _item_name and _price_text:
             try:
                 _probe2 = video_pipeline.get_video_info(current_video_source)
                 _vid_w2 = _probe2.get("width", 1080)
                 _vid_h2 = _probe2.get("height", 1920)
                 price_tag_image = _price_tag_engine.generate(
                     width=_vid_w2, height=_vid_h2,
                     human_box=_human_box,
                     item_name=_item_name,
                     price_text=str(_price_text),
                     location_hint=_location_hint # dynamic hint based on anchor type
                 )
                 if price_tag_image:
                     logger.info(f"💰 Global Monetization Tag Queued: {_item_name} | {_price_text}")
             except Exception as _pte:
                 logger.warning(f"⚠️ Smart Price Tag failed: {_pte}")

        # C. Text Overlays
        final_filters = []
        try:
             # Initialize Local Text Engine
             txt_engine = text_overlay.TextOverlay()
             from Text_Modules.text_overlay import get_timed_overlay_filter
             
             # Title (Timed: 0.75s -> 3.25s)
             if title and len(title) > 2:
                 title_f = get_timed_overlay_filter(title, lane="top", start=0.75, duration=2.5, size=65)
                 if title_f: final_filters.append(title_f)
             
             # Branding (Permanent)
             brand_val = os.getenv("BRAND_NAME") or os.getenv("TEXT_OVERLAY_CONTENT") or "@FashionScout"
             if brand_val and "Unknown" not in brand_val:
                 brand_f = get_timed_overlay_filter(brand_val, lane="fixed", start=0.75, duration=999, size=45)
                 if brand_f: final_filters.append(brand_f)

             # Captions (Real AI caption, Permanent)
             if has_caption and final_caption:
                 cap_f = get_timed_overlay_filter(final_caption, lane="caption", start=0.75, duration=999, size=55, color="yellow")
                 if cap_f: final_filters.append(cap_f)
        except Exception as e:
             logger.warning(f"⚠️ Text Overlay Fault: {e}")

        # 4. EXECUTE ALL VISUALS IN SINGLE-PASS FILTERGRAPH
        final_video_visuals = os.path.join(job_dir, "video_visuals_done.mp4")
        success = video_pipeline.render_pipeline(
            input_path=current_video_source,
            output_path=final_video_visuals,
            filters=final_filters,
            speed_factor=1.0,
            color_intensity=0.5,
            filter_type="cinematic",
            mirror_mode=mirror,
            trim_duration=trim_dur,
            price_tag_image=price_tag_image
        )
        
        if not success: 
            raise Exception("Video Render Failed")
            
        current_stage_video = final_video_visuals
        logger.info("✅ Single-Pass Visual Rendering Complete!")
             
        # 5. Audio Mix (Audio Pipeline)
        # ---------------------------------------------------------
        # A. Voiceover Generation (independent of caption overlay)
        voiceover_path = None
        has_voiceover = bool(vo_full_text and len(vo_full_text) > 10)
        if has_voiceover:
            vo_text = vo_full_text  # Full editorial script (up to 500 chars)
            # Use job_dir for temp audio
            vo_temp = os.path.join(job_dir, "voiceover.mp3")
            if voiceover.generate_voiceover(vo_text, vo_temp):
                voiceover_path = vo_temp
                logger.info(f"🎙️ Voiceover Generated: {len(vo_text)} chars")
            else:
                logger.warning("🎙️ Voiceover generation skipped.")

        # B. Music Selection & Mixing (ContinuousMusicManager — Round-Robin)
        music_path = None
        try:
            # Check music dir
            _music_dirs = ["Original_audio", "music", os.path.join("assets", "music")]
            _music_dir_found = next((d for d in _music_dirs if os.path.exists(d) and
                                     any(f.lower().endswith((".mp3",".wav")) for f in os.listdir(d))), None)
            
            # Intelligent Music Selector (Metadata driven)
            if MUSIC_MANAGER_AVAILABLE and _music_dir_found:
                _mm = ContinuousMusicManager(music_dir=_music_dir_found)
                music_path = _mm.get_best_match(profile_data)
                if music_path:
                    logger.info(f"🎵 MusicIntelligence: Selected '{os.path.basename(music_path)}'")
                    # Genre-specific filters
                    try:
                        from Audio_Modules.music_intelligence import classify_music, get_filter_graph
                        _vid_dur = video_pipeline.get_video_info(current_stage_video).get("duration", 30.0)
                        _genre, _confidence = classify_music(music_path)
                        _music_filter = get_filter_graph(_genre, _vid_dur)
                        logger.info(f"🎙️ MusicIntelligence: Genre='{_genre}' (conf={_confidence:.2f}) | EQ='{_music_filter[:50]}...'")
                    except Exception as _mi_e:
                        _music_filter = None
                        logger.warning(f"⚠️ MusicIntelligence failed: {_mi_e}")

                    # Beat analysis on selected track
                    if BEAT_ENGINE_AVAILABLE and _beat_engine:
                        try:
                            _beats = _beat_engine.analyze_beats(music_path)
                            if _beats:
                                logger.info(f"🥁 BeatEngine: {len(_beats)} beats detected | First: {_beats[0]:.2f}s | Avg interval: {(_beats[-1]-_beats[0])/max(1,len(_beats)-1):.2f}s")
                        except Exception as _be:
                            logger.warning(f"⚠️ BeatEngine failed: {_be}")
            elif _music_dir_found:
                # Fallback: simple random pick
                import random
                _files = [f for f in os.listdir(_music_dir_found) if f.lower().endswith((".mp3",".wav"))]
                if _files:
                    music_path = os.path.join(_music_dir_found, random.choice(_files))
                    logger.info(f"🎵 Music (fallback pick): {os.path.basename(music_path)}")
        except Exception as e:
            logger.warning(f"⚠️ Music Selection Failed: {e}")

        final_video = output_path
        
        mix_success = audio_pipeline.mix_audio(
            video_path=current_stage_video, 
            output_path=final_video,
            voiceover_path=voiceover_path,
            music_path=music_path, 
            vo_vol=2.5,    # Narration: clear and dominant (slightly lowered to prevent clipping)
            music_vol=0.15 # Background music: 15% (subtle and non-competing)
        )
        
        if not mix_success:
            logger.warning("⚠️ Audio Mix failed. Copying video only.")
            final_audio_path = current_stage_video
        else:
            logger.info("✅ Audio Mix Complete.")
            final_audio_path = final_video

        # --- STEP 6: INJECT PREDICTION ANCHOR (Final Concat) ---
        if prediction_frame and os.path.exists(prediction_frame):
            logger.info(f"🎞️ [Step 6] Appending Prediction Anchor...")
            try:
                # Convert image to 3s video clip
                anchor_clip = os.path.join(job_dir, "anchor_clip.mp4")
                # Simple ffmpeg image to video command
                cmd = [
                    os.getenv("FFMPEG_BIN", "ffmpeg"), "-y", "-loop", "1", 
                    "-i", prediction_frame, "-t", "3", 
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920",
                    anchor_clip
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                
                # Concat the two pieces
                # We reuse compile_batch logic here but just for these two
                final_combined = os.path.join(job_dir, "combined_final.mp4")
                compile_batch([final_audio_path, anchor_clip], final_combined)
                
                if os.path.exists(final_combined):
                    if os.path.abspath(final_combined) != os.path.abspath(output_path):
                        shutil.copy(final_combined, output_path)
                    logger.info("✅ High-Probability Prediction Video Ready.")
                else:
                    if os.path.abspath(final_audio_path) != os.path.abspath(output_path):
                        shutil.copy(final_audio_path, output_path)
            except Exception as e:
                logger.error(f"❌ Anchor Injection Failed: {e}")
                if os.path.abspath(final_audio_path) != os.path.abspath(output_path):
                    shutil.copy(final_audio_path, output_path)
        else:
            if os.path.abspath(final_audio_path) != os.path.abspath(output_path):
                shutil.copy(final_audio_path, output_path)

        # 7. Cleanup
        shutil.rmtree(job_dir, ignore_errors=True)
        
        # --- ADAPTIVE BRAIN: Record Success ---
        if ADAPTIVE_BRAIN_AVAILABLE and _adaptive_brain:
            try:
                _brain_risk = profile_data.get("risk_score", 0.0) if isinstance(profile_data, dict) else 0.0
                _adaptive_brain.register_upload_outcome("success", risk_score=float(_brain_risk))
                logger.info("✅ AdaptiveBrain: Job success recorded. Trust updated.")
            except Exception as _ab_e:
                logger.warning(f"⚠️ AdaptiveBrain outcome update failed: {_ab_e}")
                
        # --- WRITE JSON SIDECAR ---
        try:
            sidecar_path = os.path.splitext(output_path)[0] + ".json"
            sidecar_data = {
                "caption_data": {
                    "caption": final_caption
                },
                "pipeline_metrics": {
                    "monetization": profile_data.get('raw_analysis', {})
                },
                "editorial_title": title,
                "last_processed": datetime.now().isoformat()
            }
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(sidecar_data, f, indent=2)
            logger.info(f"💾 JSON Sidecar saved: {sidecar_path}")
        except Exception as sidecar_err:
            logger.warning(f"⚠️ Failed to write sidecar JSON: {sidecar_err}")
        
        return True, {"status": "success", "uuid": uuid_str}

    except Exception as e:
        logger.error(f"Compilation Failed: {e}", exc_info=True)
        # --- ADAPTIVE BRAIN: Record Failure ---
        if ADAPTIVE_BRAIN_AVAILABLE and _adaptive_brain:
            try:
                _adaptive_brain.register_upload_outcome("error", risk_score=0.0)
            except Exception:
                pass
        return False, {"error": str(e)}


def compile_batch(
    video_paths,
    output_path,
    transition_type="fade",
    transition_duration=0.5
):
    """
    Compiles a batch of videos into a single sequence.
    """
    if not video_paths: return False
    
    unique_id = f"batch_{uuid.uuid4().hex[:6]}"
    job_dir = os.path.join("temp", unique_id)
    os.makedirs(job_dir, exist_ok=True)
    
    try:
        logger.info(f"📦 Starting Batch Compilation: {len(video_paths)} videos")
        
        # Auto-Correction: Ensure extension exists
        if not output_path.lower().endswith(".mp4"):
             output_path += ".mp4"
        
        # Simple Concat via Demuxer (Fastest, no re-encode if same codec)
        # Create list file
        list_file = os.path.join(job_dir, "input.txt")
        with open(list_file, "w") as f:
            for v in video_paths:
                f.write(f"file '{os.path.abspath(v)}'\n")
        
        # Concat Command
        cmd = [
            os.getenv("FFMPEG_BIN", "ffmpeg"), "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_path
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # Cleanup
        shutil.rmtree(job_dir, ignore_errors=True)
        return output_path

    except Exception as e:
        logger.error(f"Batch Compilation Failed: {e}")
        return None
def compile_juxtaposition(
    uuid_str,
    input_a,
    input_b,
    output_path,
    title,
    profile_data={}
):
    """
    The Synthetic Newsroom Pipeline (75% YPP).
    Renders a side-by-side comparison with a Virtual Host reacting to the delta.
    """
    job_dir = os.path.join("temp", uuid_str)
    os.makedirs(job_dir, exist_ok=True)
    
    clean_a = input_a
    clean_b = input_b
    
    # --- STEP 1: CLEAN SOURCES ---
    if WATERMARK_AVAILABLE:
        try:
            res_a = watermark_auto.process_video_with_watermark(input_a, os.path.join(job_dir, "clean_a.mp4"))
            if res_a.get("success"): clean_a = os.path.join(job_dir, "clean_a.mp4")
            
            res_b = watermark_auto.process_video_with_watermark(input_b, os.path.join(job_dir, "clean_b.mp4"))
            if res_b.get("success"): clean_b = os.path.join(job_dir, "clean_b.mp4")
        except: pass

    # --- STEP 2: COMPARISON BRAIN ---
    script = "Look A versus Look B. Comparison underway."
    cta = "Access the Blueprint..."
    if BRAIN_AVAILABLE:
        logger.info("🧠 [Synthetic Newsroom] Comparing sources...")
        brain_inst = MonetizationStrategist()
        # Mocking context for now, in a real run we'd use fashion_scout results
        analysis = brain_inst.analyze_versus(context_a=title, context_b=title)
        if analysis:
            script = analysis.get("editorial_script", script)
            cta = analysis.get("monetization_cta", cta)
            profile_data.update(analysis)

    # --- STEP 3: RENDER JUXTAPOSITION ---
    temp_juxta = os.path.join(job_dir, "juxtaposition.mp4")
    from .anchors import engine as anchor_engine
    anchor_path = anchor_engine.get_anchor_path()
    
    success = video_pipeline.render_juxtaposition(
        clean_a, clean_b, temp_juxta, 
        anchor_path=anchor_path,
        layout="vertical"
    )
    
    if not success: return False, {"error": "Juxtaposition failed"}

    # --- STEP 4: OVERLAYS & AUDIO (Simplified for Prototype) ---
    final_output = output_path
    shutil.copy(temp_juxta, final_output)
    
    logger.info(f"✅ Synthetic Newsroom Render Complete: {uuid_str}")
    return True, {"status": "success", "script": script, "cta": cta}
