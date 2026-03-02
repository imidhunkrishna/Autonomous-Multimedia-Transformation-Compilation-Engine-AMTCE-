# 🤖 AMTCE: Autonomous Multimedia Transformation & Compilation Engine

Welcome! AMTCE is an end-to-end automated multimedia processing pipeline designed for systematic content transformation, curation, and delivery. 

It orchestrates advanced video and AI technologies to achieve this:
1. **Intelligent Content Refinement**: Employs exact OpenCV/Numpy masking algorithms for programmatic visual editing and regional processing.
2. **Audio Processing Pipeline**: Programmatically normalizes and remixes audio layers (using FFmpeg) to create distinct, high-quality audio profiles.
3. **Automated Media Transformation**: Dynamically applies spatial upscaling, smart cropping, and cinematic color grading to raw footage.
4. **LLM Integration (Google Gemini)**: Analyzes video frames in real-time to extract metadata, deduce context, and autonomously generate SEO-optimized captions.
5. **Asynchronous Delivery via Bot API**: Packages the fully transformed assets and routes them through a Telegram Bot interface for human-in-the-loop review and approval.

This project demonstrates scalable system architecture, integrating asynchronous Python processes (`ThreadPoolExecutor`), multi-modal LLMs, and heavy A/V processing to automate curation workflows.

---

## 🎯 Core Use Cases & Adaptability

Out of the box, this engine features a robust prompt-engineering framework ("Brain Modules") that uses Google Gemini to dynamically parse visual content. By adapting its prompts, the engine handles highly varied data extraction and rendering tasks.

### Highlighted Processing Pipelines:
1. **Tech & Hardware Summarization:** Ingests unboxing or review footage, programmatically extracts the "Device Name" and "Specifications", and automatically overlays synchronized, lower-third informational graphics.
2. **Real Estate & Property Tours:** Processes raw residential walkthroughs. Instructs the vision model to identify "Location" and "Property Value", standardizing the output with smooth background audio and branded aesthetic tags.
3. **Fitness & Activity Tracking:** Analyzes workout routines to extract the "Exercise Name" and "Target Muscle Group", automatically generating dynamic rep-counter captions and high-BPM audio overlays.
4. **Culinary Process Standardization:** Processes recipe videos by extracting the "Dish Name" and "Preparation Time", applying consistent, stylish typography for ingredients over the original footage.
5. **Podcast & Long-Form Highlights:** Ingests long-form conversational content, leverages the AI to identify and summarize the most engaging 30-second segments, and overlays cinematic text filters with normalized audio.

*To adapt the engine's extraction targets, developers can modify the system prompts located in `Brain_Modules/monetization_brain.py` and `Brain_Modules/caption_brain.py`.*

---

## 🛠️ Step-by-Step Setup Guide (For Beginners)

Even if you have only basic computer knowledge, you can set this up by following these steps carefully.

### Step 1: Install Required Software
1. **Install Python**: You need Python installed on your computer. 
   > [!WARNING]
   > **Python Version**: You MUST install Python **3.11 or 3.12**. Python 3.10 is reaching end-of-life for Google AI services soon, and Python 3.8/3.9 will cause the engine to crash.
   - Go to [python.org/downloads](https://www.python.org/downloads/) and install it.
   - **Crucial for Windows Users**: During installation, make sure to check the box at the bottom that says **"Add Python to PATH"**.
2. **Install FFmpeg**: This is a powerful hidden tool that processes video and audio.
   - Keep it simple: search YouTube for "How to install FFmpeg on Windows" (or Mac) and follow a 2-minute video. It involves downloading a folder and telling your computer where to find it.

### Step 2: Get Your Secret Keys (Passwords for the AI and Bot)
To make the AI work and your bot communicate, you need two secret keys:
1. **Telegram Bot Token**: 
   - Open your Telegram app and search for `@BotFather`.
   - Send the message `/newbot`, follow the instructions to give your bot a name, and copy the long `HTTP API Token` it gives you.
2. **Gemini API Key**: 
   - Go to [Google AI Studio](https://aistudio.google.com/app/apikey), sign in with your Google account, and click the "Create API key" button. Copy this key.

### Step 3: Prepare the Project on your Computer
1. Open your computer's terminal or command prompt inside this project folder.
2. Create an isolated workspace (virtual environment) so we don't mess up your computer:
   - Type this command and hit enter: `python -m venv venv`
3. Activate the workspace:
   - **On Windows**: type `venv\Scripts\activate` and hit enter.
   - **On Mac/Linux**: type `source venv/bin/activate` and hit enter.
4. Install everything the bot needs to run:
   > [!IMPORTANT]
   > The watermark removal module heavily relies on exact mathematical formulas. It REQUIRES a specific old version of numpy (`numpy==1.26.1`) to communicate with OpenCV. If you upgrade numpy randomly, the watermark remover **will break**.
   - Type: `pip install -r requirements.txt` and hit enter. Let it finish.

### Step 4: Add Your Secret Keys to the Project
1. Open the project folder on your computer and go inside the `Credentials/` folder.
2. Find the file named `.env.example`. Make a copy of it and rename the copy to `.env` (just a dot and the word env).
3. Open this `.env` file in any text editor (like Notepad).
4. Replace `YOUR_BOT_TOKEN_HERE` with your Telegram token from earlier.
5. Replace `YOUR_GEMINI_API_KEY_HERE` with your Gemini key from earlier.
6. Save and close the file.

### Step 5: Start the Engine!
1. Go back to your command prompt (make sure `(venv)` is showing on the left side, indicating your workspace is active).
2. Type `python main.py` and hit enter.
3. The engine is now running!
4. Open your Telegram app, find the bot you created, and say hello! Send it a video link (like a YouTube shorts link) and it will start downloading, transforming, and sending the fresh result back to you.

---

## ☕ Support the Project

If you find this codebase useful for educational purposes, or if you simply want to support the extensive mathematical and operational engineering that went into building this autonomous engine, consider buying me a coffee! Your support fuels future updates and advanced AI integrations.

**Support via:**
* **PayPal**: `@Midhunkrishnapv`
* **UPI ID**: `midhunv424@naviaxis`
* **Bitcoin (BTC)**: `bc1qt70u2sacxgk69y3jz7jncmryx7pdru8upu9k6d`
* **Pi Wallet**: `GBOH5VYHMBTAJNISPVVSUDACFQAFU2WWHNBK2D3S57NY2WVL6LCROM4M`
