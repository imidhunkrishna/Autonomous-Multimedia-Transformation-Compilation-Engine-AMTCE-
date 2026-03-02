# 📥 Download Modules (The Harvester)

## Use Case
This module is the "front line" of the pipeline. It is responsible for fetching high-quality video content from URLs (Instagram, TikTok, YouTube, etc.) while ensuring that duplicate content is never processed twice.

## What it is good at
1.  **Duplicate Detection**: Uses internal fingerprinting to recognize videos even if the URL or filename changes.
2.  **Platform Agnostic**: Uses `yt-dlp` under the hood to support a massive range of social media platforms.
3.  **Atomic Operations**: Ensures that downloads are completed fully (renaming `.part` files only after success) to prevent corrupt media from entering the pipeline.

## Supported Platforms
The Harvester is powered by `yt-dlp` and supports 1000+ sites, including:
- **Instagram**: Reels, Posts, Stories, IGTV.
- **Facebook**: Reels, Watch, Public Videos.
- **TikTok**: Videos (no-watermark usually handled by yt-dlp).
- **YouTube**: Shorts, Regular Videos.
- **Twitter/X**, **Pinterest**, **Snapchat**, and more.

## Step-by-Step Usage

1.  **Installation**:
    Ensure you have dependencies installed:
    ```bash
    pip install yt-dlp opencv-python numpy gradio
    ```

2.  **Web Interface (Gradio)**:
    Run the user-friendly web UI:
    ```bash
    python gradio_downloader.py
    ```
    Then open `http://localhost:7860` in your browser.

3.  **Command Line (CLI)**:
    ```bash
    python downloader.py --input "https://www.instagram.com/p/example/"
    ```

4.  **Python API**:
    ```python
    from downloader import download_video
    file_path = download_video("https://www.instagram.com/p/example/")
    ```

## Manual Cleanup
If you want to reset the database of downloaded videos, delete the `download_index.json` (if present in the data folder).
