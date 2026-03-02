# 🔊 Audio Modules (The Mastering Studio)

## Use Case
This module handles the entire auditory transformation of the video. It can generate voiceovers, mix background music, and apply heavy "stadium-grade" EQ and compression.

## What it is good at
1.  **Heavy Remixing**: Applies extreme compression and bass-boost to make audio sound "loud and aggressive" (standard for shorts).
2.  **Voiceover Orchestration**: Uses AI to narrate scripts and automatically ducks (lowers) background music when the narrator speaks.
3.  **Continuous Mixes**: Can create 10-minute seamless music loops for long compilations.

## Step-by-Step Usage

1.  **Requirement**:
    Ensure **FFmpeg** is installed and accessible in your system PATH.
2.  **Run Standalone**:
    ```python
    from audio_processing import heavy_remix
    
    # Transform thin audio into high-energy sound
    heavy_remix("input.mp3", "output_mastered.mp3")
    ```
3.  **Mix Music**:
    ```python
    from audio_processing import mix_background_music
    mix_background_music("video_no_sound.mp4", "final_output.mp4", volume=0.2)
    ```
