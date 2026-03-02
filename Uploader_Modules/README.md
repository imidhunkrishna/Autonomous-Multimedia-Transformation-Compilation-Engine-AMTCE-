# 🚀 Uploader Modules (The Shadow Runner)

## Use Case
Handles the distribution phase. It uploads completed media to YouTube and Instagram while managing sensitive authentication.

## What it is good at
1.  **Metadata Scrubbing**: Before upload, it strips original file metadata to prevent "reused content" flags by the algorithms.
2.  **Secure Auth**: Uses OAuth2 tokens to securely upload without requiring hardcoded passwords.
3.  **Batching**: Can handle uploading hundreds of videos in a single session.

## Step-by-Step Usage

1.  **Setup**:
    Ensure you have your `client_secrets.json` in the `Credentials/` folder.
2.  **Authenticate**:
    Run `python auth_youtube.py` (in scripts) once to generate your token.
3.  **Upload**:
    This is usually handled automatically by `main.py` after you send the `/approve` command via Telegram.
