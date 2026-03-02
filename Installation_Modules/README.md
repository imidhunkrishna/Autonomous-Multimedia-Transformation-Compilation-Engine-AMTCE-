# 🛠️ Installation Modules (The Architect)

## Use Case
Handles the automated setup of the environment, especially for complex systems like Google Colab or new Windows environments.

## What it is good at
1.  **Dependency Resolution**: Automatically installs and heals broken dependencies (like Real-ESRGAN or FFmpeg wrappers).
2.  **One-Click Setup**: Provides `install_colab.py` for instant cloud deployment.

## Step-by-Step Usage

1.  **Run in Colab**:
    ```bash
    python install_colab.py
    ```
2.  **Manual Healing**:
    Use this if you find that `pip install -r requirements.txt` is failing for hardware-specific reasons.
