# 🎨 Text Modules (The Graphic Designer)

## Use Case
This module is the graphic overlay system. It renders professional captions, branding watermarks, and informational text onto the video frames.

## What it is good at
1.  **Collision Avoidance**: It mathematically calculates "lanes" for text so that captions don't collide with branding or UI elements.
2.  **Font Healing**: Automatically downloads and installs missing fonts from the project assets to ensure consistent branding.
3.  **High-Visibility Rendering**: Uses professional shadowing and outlining to ensure text is readable over any background.

## Step-by-Step Usage

1.  **Requirement**:
    Needs **OpenCV** and **PIL (Pillow)**.
2.  **Integrate**:
    This module is usually called via `compiler.py`, but you can use `text_overlay.py` to slap text on static frames for testing layouts.
