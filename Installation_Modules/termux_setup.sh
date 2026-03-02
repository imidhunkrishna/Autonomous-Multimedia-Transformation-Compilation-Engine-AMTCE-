#!/bin/bash

echo "🤖 Termux Auto-Setup for Transformative Bot (Venv Edition)"
echo "=========================================================="

echo "📦 Updating repositories..."
pkg update -y && pkg upgrade -y

echo "📦 Installing System Dependencies & Python..."
# Core build tools, python, git, and media libraries
# Note: User strictly requires Python 3.10 for compatibility.
pkg install -y tur-repo x11-repo science-repo
pkg update -y # Update after adding new repos
pkg install -y python3.10 git clang make binutils pkg-config

# Critical compile fix for Termux (fixes -lgcc errors)
pkg install -y libandroid-spawn

# Try to install system OpenCV (often includes bindings in Termux)
# Enabling x11-repo/science-repo usually makes 'opencv' available
# Try 'python-opencv' specifically (often in tur-repo) as it definitely has bindings
pkg install -y python-opencv || pkg install -y opencv || echo "⚠️ 'pkg install' failed. proceeding..."

# Build tools for compiling python packages (Numpy, Pillow, OpenCV fallback)
pkg install -y cmake ninja rust libffi libjpeg-turbo libpng freetype libxml2 libxslt zlib openjpeg libwebp libtiff ffmpeg

echo "🛠️ Creating Virtual Environment (venv)..."

# 1. Locate Python 3.10 (System)
# If running inside venv, 'command -v' might return the venv python. We need the SYSTEM one.
if [ -n "$VIRTUAL_ENV" ]; then
    echo "⚠️ Deactivating current venv to avoid conflicts..."
    deactivate 2>/dev/null || true
fi

# Explicitly check Termux system path first
if [ -f "/data/data/com.termux/files/usr/bin/python3.10" ]; then
    PY_BIN="/data/data/com.termux/files/usr/bin/python3.10"
else
    # Fallback to path search, but ignore venv directories
    PY_BIN=$(command -v python3.10)
fi

if [ -z "$PY_BIN" ]; then
    echo "⚠️ Python 3.10 not found in strict locations. Searching..."
    pkg install -y python3.10
    PY_BIN="/data/data/com.termux/files/usr/bin/python3.10"
fi

if [ ! -f "$PY_BIN" ]; then
    echo "❌ FATAL: Could not locate 'python3.10'."
    exit 1
fi

echo "   > Using System Python at: $PY_BIN"

# 2. Try Standard Venv with system packages (allows using pkg installed opencv)
# Force recreation if we don't have system-site-packages enabled or venv is broken
if [ -d "venv" ]; then
    if ! grep -q "include-system-site-packages = true" venv/pyvenv.cfg; then
        echo "   ⚠️ Existing 'venv' does not use system packages. Deleting to recreate..."
        rm -rf venv
    fi
fi

if [ ! -d "venv" ]; then
    echo "   > Attempting standard 'venv' creation (with system site-packages)..."
    "$PY_BIN" -m venv --system-site-packages venv
    
    if [ ! -d "venv" ]; then
        echo "   ⚠️ Standard 'venv' failed. Falling back to 'virtualenv'..."
        "$PY_BIN" -m pip install virtualenv
        "$PY_BIN" -m virtualenv --system-site-packages venv
    fi
    
    if [ ! -d "venv" ]; then
        echo "❌ FATAL: Failed to create 'venv'. Check permissions?"
        exit 1
    fi
    echo "   └─ Created 'venv' successfully."
else
    echo "   └─ 'venv' already exists and uses system-site-packages."
fi

echo "🔌 Activating venv..."
source venv/bin/activate || . venv/bin/activate
if [ $? -ne 0 ]; then
    echo "❌ ERROR: Failed to activate venv."
    exit 1
fi

echo "📦 Upgrading pip (inside venv)..."
pip install --upgrade pip setuptools wheel --only-binary=:all:

echo "📦 Installing Python Dependencies (inside venv)..."
# Flag to force compile if wheels missing
export CFLAGS="-Wno-error=incompatible-function-pointer-types -O3 -Wno-implicit-function-declaration"
export MATHLIB="m"
export LDFLAGS="-L/data/data/com.termux/files/usr/lib/"

# Check if system OpenCV is usable
# We need numpy allowed/installed for cv2 to import, so we install it first
echo "📦 Pre-installing numpy to enable cv2 check..."
# Try using system numpy if available (fastest)
pkg install -y python-numpy || true
# Ensure it's in the venv (system-site-packages should pick it up, or we install it)
pip install numpy --only-binary=:all:

echo "🔍 Checking for System OpenCV..."
# Debug: Where is cv2?
echo "   Listing 'opencv' package files (looking for cv2.so)..."
pkg files opencv | grep "cv2.so" || echo "   ❌ No cv2.so found in opencv package."

CV2_PATH=$(find /data/data/com.termux/files/usr/lib/ -name "cv2*.so" | head -n 1)
if [ -n "$CV2_PATH" ]; then
    echo "   Found cv2.so at: $CV2_PATH"
    CV2_DIR=$(dirname "$CV2_PATH")
    echo "   Append to PYTHONPATH: $CV2_DIR"
    export PYTHONPATH="$PYTHONPATH:$CV2_DIR"
else
    echo "   ❌ Could not find cv2.so in /usr/lib/"
fi

if python -c "import cv2; print(f'Successfully imported cv2 version: {cv2.__version__}')" 2> cv2_err.log; then
    # Success path
    echo "✅ System OpenCV detected. Skipping 'opencv-python-headless' from requirements..."
    grep -v "opencv-python-headless" requirements.txt > requirements_filtered.txt
    pip install --only-binary=:all: -r requirements_filtered.txt
    rm requirements_filtered.txt
else
    # Failure path: System OpenCV missing
    echo "⚠️ System OpenCV NOT detected."
    
    echo "⚠️ Falling back to PIP 'Wheel Hunt'..."
    grep -v "opencv-python-headless" requirements.txt > requirements_filtered.txt
    
    # Install other deps first - STRICTLY BINARY ONLY
    echo "📦 Installing other dependencies (Binary Only)..."
    pip install --only-binary=:all: -r requirements_filtered.txt
    rm requirements_filtered.txt

    # 1. Try generic binary wheel (Primary Attempt)
    echo "   1/2 Trying opencv-python-headless (binary only)..."
    if pip install opencv-python-headless --only-binary=:all:; then
        echo "   ✅ Success with opencv-python-headless wheel!"
    else
        echo "   ❌ No headless wheel found."
        
        # 2. FINAL RESORT: Single-Core Compilation
        echo "   ⚠️ LAST RESORT: Compiling Source Code."
        echo "   ❗ THIS WILL TAKE 20-40 MINUTES. DO NOT CANCEL."
        echo "   ❗ Running in single-core mode to prevent crashes."
        
        export CMAKE_BUILD_PARALLEL_LEVEL=1
        export MAX_JOBS=1
        export MAKEFLAGS="-j1"
        
        # FIX: Force install older numpy first to avoid 2.x build errors
        echo "   🔧 Pre-installing stable Numpy 1.x for build compatibility..."
        pip install "numpy<2.0" --only-binary=:all: || pip install "numpy<2.0" --no-binary=:all:

        if pip install opencv-python-headless --no-binary=opencv-python-headless; then
             echo "   ✅ Success! OpenCV Compiled from source."
        else
             echo "❌ FATAL: Compilation failed."
             echo "   Your device might simply be unable to build this."
             exit 1
        fi
    fi
    rm cv2_err.log
fi

echo "=========================================================="
echo "✅ Setup Complete!"
echo ""
echo "❗ IMPORTANT ❗"
echo "To run the bot, you must activate the environment first:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "Or run in one line:"
echo "   ./venv/bin/python main.py"
