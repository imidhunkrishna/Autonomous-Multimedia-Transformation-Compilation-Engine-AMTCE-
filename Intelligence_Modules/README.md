# 🏎️ Intelligence Modules (The Editorial Brain)

## Use Case
This is the "Decision Maker" of the AMTCE engine. It uses Google Gemini 1.5/2.0 to analyze video content, ensure it meets YouTube Monetization (YPP) requirements, and generate viral scripts.

## What it is good at
1.  **YPP Compliance**: It acts as a strict "safety officer," rejecting videos that it deems too low-quality or "untransformative."
2.  **Viral Narrative**: Automatically generates titles, hashtags, and spoken script commentary that adds educational/critical value to the video.
3.  **Multimodal Analysis**: It doesn't just read code; it "looks" at video frames to understand the context.

## Step-by-Step Usage

1.  **Installation**:
    ```bash
    pip install google-generativeai python-dotenv
    ```
2.  **Configuration**:
    Ensure your `GEMINI_API_KEY` is set in the `.env` file within this folder (or root).
3.  **Run Standalone**:
    ```python
    from monetization_brain import brain
    
    # Analyze a video's narrative potential
    analysis = brain.analyze_content(
        title="Fashion Look", 
        duration=15.0, 
        image_paths=["frame_debug.jpg"]
    )
    
    if analysis.get("approved"):
        print(f"Script: {analysis['script']}")
    else:
        print("Video rejected for low transformative value.")
    ```
