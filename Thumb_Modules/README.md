# 📸 Thumb Modules (The Click Magnet)

## Use Case
Automatically generates high-CTR (Click-Through Rate) thumbnails for your processed videos.

## What it is good at
1.  **Smart Frame Selection**: It scans to the **50% mark** of the video (the peak of action) to extract the thumbnail frame.
2.  **Contrast Blending**: Overlays high-contrast, professional titles onto the frame to make it "pop" on social discovery pages.

## Step-by-Step Usage

1.  **Run Standalone**:
    ```python
    from generator import generate_thumbnail
    
    # Generates a thumb with the given title
    generate_thumbnail("video.mp4", "IS THIS THE NEW TREND?")
    ```
2.  **Requirement**:
    Requires **FFmpeg** for frame extraction and **PIL** for the graphic blend.
