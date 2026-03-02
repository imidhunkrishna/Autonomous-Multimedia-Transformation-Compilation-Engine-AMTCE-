import os
import sys
import logging
import argparse
import json
import shutil
import time
import threading
import asyncio
from dotenv import load_dotenv

# Configure Logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("watermark_main")

# --- AUTO-SETUP ---
try:
    from . import deps_installer
except ImportError:
    import deps_installer
deps_installer.run_setup()

# Ensure root (one level up) is in path for standalone execution
if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import from the Visual_Refinement_Modules package
try:
    from . import hybrid_watermark
    from . import watermark_auto
    from . import opencv_watermark
except ImportError:
    import hybrid_watermark
    import watermark_auto
    import opencv_watermark

# Load Environment
# 1. Try local module-specific env
if os.path.exists("watermark_env.env"):
    load_dotenv("watermark_env.env", override=True)
# 2. Try global credentials env
elif os.path.exists("Credentials/.env"):
    load_dotenv("Credentials/.env", override=True)
# 3. Try one level up (if running from Visual_Refinement_Modules)
elif os.path.exists("../Credentials/.env"):
    load_dotenv("../Credentials/.env", override=True)


# --- GLOBALS ---
gradio_demo = None
# Master switch for LaMa Hybrid (Pro Mode)
USE_LAMA_HYBRID = os.getenv("USE_LAMA_HYBRID", "true").lower() == "true"

# --- CORE FUNCTIONS ---

def detect_watermarks(input_path: str, aggressive: bool = False, keywords: str = None) -> str:
    """Wrapper for detection logic."""
    if not os.path.exists(input_path):
        return json.dumps({"status": "ERROR", "context": {"error": "File not found"}})
    
    # Ensure API Key is loaded
    if not os.getenv("GEMINI_API_KEY"):
        logger.warning("⚠️ GEMINI_API_KEY not found in env. Detection might fail.")

    return hybrid_watermark.hybrid_detector.process_video(
        input_path, 
        aggressive=aggressive, 
        keywords=keywords
    )

def remove_watermark_adaptive(
    input_video: str, 
    retry_level: int = 0,
    watermarks: list = None,
    pro_mode: bool = False
) -> str:
    """Wrapper for removal logic. Returns path to cleaned video."""
    if not input_video or not os.path.exists(input_video):
        logger.warning("⚠️ No input video provided or file not found.")
        return None

    job_dir = os.path.join("temp_watermark", f"job_gradio_{int(time.time())}")
    os.makedirs(job_dir, exist_ok=True)
    
    dir_name = os.path.dirname(input_video)
    name, ext = os.path.splitext(os.path.basename(input_video))
    output_video = os.path.join(dir_name, f"{name}_clean_{int(time.time())}{ext}")

    if watermarks is None:
        logger.info("🕵️ Auto-detecting watermarks...")
        json_res = detect_watermarks(input_video, aggressive=(retry_level > 0))
        logger.info(f"🔍 Raw Detection Result: {json_res[:200]}..." if json_res else "None") # Log first 200 chars
        try:
            res = json.loads(json_res)
            watermarks = res.get("watermarks", [])
            logger.info(f"✅ Parsed {len(watermarks)} watermarks.")
        except Exception as e:
            logger.error(f"❌ JSON Parse Error: {e}")
            watermarks = []

    if not watermarks:
        logger.warning("⚠️ No watermarks found or parsing failed. Returning original.")
        return input_video # Return original if clean

    success = False
    msg = "No process run"
    
    logger.info(f"🔄 Processing Logic Check: ProMode={pro_mode}, GlobalLaMa={USE_LAMA_HYBRID}, WMs={len(watermarks)}")

    # 🛡️ LOGIC GUARD: If Pro requested but not available, force fallback
    if pro_mode and not USE_LAMA_HYBRID:
        logger.warning("⚠️ Pro Mode requested but LaMa Hybrid is disabled globally/env. Falling back to Standard.")
        pro_mode = False

    if pro_mode and USE_LAMA_HYBRID:
        logger.info("💎 Using LaMa-Hybrid Pro Removal (Higher Quality, CPU Stable)...")
        try:
             from Visual_Refinement_Modules import lama_hybrid_main
        except ImportError:
             import lama_hybrid_main
        success, msg = lama_hybrid_main.run_lama_hybrid_removal(
            input_video, watermarks, output_video, job_dir=job_dir
        )
        if not success:
            logger.warning(f"⚠️ LaMa Hybrid failed: {msg}. Falling back to Standard removal.")
            pro_mode = False # Fall through to standard
    
    if not pro_mode:
        logger.info(f"🛡️ Starting Removal Orchestration (Level {retry_level})...")
        success, msg = watermark_auto.run_adaptive_watermark_orchestration(
            input_video,
            watermarks,
            output_video,
            job_dir=job_dir,
            retry_level=retry_level
        )
    
    if success and os.path.exists(output_video):
        return output_video
    return None

# --- GRADIO INTERFACE ---

def run_gradio(blocking=True):
    global gradio_demo
    logger.info("🎨 Starting Gradio Interface...")
    try:
        import gradio as gr
    except ImportError:
        logger.error("❌ Gradio not installed. Run 'pip install gradio'.")
        return

    with gr.Blocks(title="Watermark Manager") as demo:
        gr.Markdown("# 🛡️ Watermark Manager Standalone")
        
        with gr.Tab("Remove Watermark"):
            with gr.Row():
                in_video = gr.Video(label="Input Video")
                out_video = gr.Video(label="Cleaned Video")
            
            with gr.Row():
                level = gr.Slider(0, 2, step=1, label="Aggressive Level (0=Safe, 2=Nuclear)")
                pro_check = gr.Checkbox(label="💎 LaMa Hybrid (Pro Mode - High Quality)", value=USE_LAMA_HYBRID)
                btn_process = gr.Button("Remove Watermark", variant="primary")
            
            btn_process.click(
                fn=remove_watermark_adaptive,
                inputs=[in_video, level, gr.State(None), pro_check],
                outputs=[out_video]
            )

        with gr.Tab("Detect Only"):
            with gr.Row():
                in_detect = gr.Video(label="Input")
                out_json = gr.JSON(label="Detection Results")
            
            btn_detect = gr.Button("Detect")
            
            def gradio_detect(vid):
                res = detect_watermarks(vid)
                return json.loads(res)
                
            btn_detect.click(fn=gradio_detect, inputs=[in_detect], outputs=[out_json])

    gradio_demo = demo
    port = int(os.getenv("GRADIO_PORT", 7860))
    share = os.getenv("GRADIO_SHARE", "false").lower() == "true"
    
    # If we are in a thread, we must not block the thread forever without allow_flag
    demo.launch(server_port=port, share=share, prevent_thread_lock=not blocking)

# --- TELEGRAM BOT ---

def run_telegram():
    logger.info("✈️ Starting Telegram Bot...")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found in env.")
        return

    try:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
    except ImportError:
        logger.error("❌ python-telegram-bot not installed.")
        return

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("I am the Watermark Bot. Send me a video!")

    async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Video received! Processing (This is a simplified standalone demo)...")
        
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    # run_polling() is blocking and handles SIGINT internally
    app.run_polling()

# --- MAIN ENTRY ---

def main():
    parser = argparse.ArgumentParser(description="Watermark Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    detect_parser = subparsers.add_parser("detect", help="CLI Detect")
    detect_parser.add_argument("input", help="Input path")

    run_parser = subparsers.add_parser("run", help="Run Services (Gradio/Telegram)")

    args = parser.parse_args()

    # Default to 'run' if no command provided
    if not args.command:
        args.command = "run"

    if args.command == "detect":
        print(detect_watermarks(args.input))
        return

    # Check Flags
    enable_gradio = os.getenv("ENABLE_GRADIO", "false").lower() == "true"
    enable_telegram = os.getenv("ENABLE_TELEGRAM", "false").lower() == "true"

    try:
        if enable_gradio and not enable_telegram:
            run_gradio(blocking=True)

        elif enable_telegram and not enable_gradio:
            run_telegram()
        
        elif enable_telegram and enable_gradio:
            logger.info("Running BOTH Gradio and Telegram.")
            # Run Gradio in background thread
            t = threading.Thread(target=run_gradio, kwargs={'blocking': False}, daemon=True)
            t.start()
            # Run Telegram in foreground (blocks and handles signals)
            run_telegram()

        else:
            print("No services enabled in .env or CLI command provided.")
            parser.print_help()

    except KeyboardInterrupt:
        logger.info("\n👋 Shutdown requested by user (Ctrl+C).")
    finally:
        if gradio_demo:
            logger.info("🛑 Closing Gradio session...")
            gradio_demo.close()
        logger.info("✅ All services stopped.")

if __name__ == "__main__":
    main()
