import os
import sys
import logging
import asyncio
import shutil
import re
import time
import subprocess
import csv
import json
import io
import uuid
import random
import tempfile
import glob
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Any
from dotenv import load_dotenv
from contextlib import contextmanager
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# Configure logging for the gate itself
logger = logging.getLogger("necessary_import_gate")

class NecessaryImportGate:
    """
    Necessary Import Gate
    ---------------------
    Centralized gatekeeper for standard, non-heavy imports.
    Ensures critical dependencies are available before execution.
    """
    _loaded_modules = {}
    
    # Standard modules required for operation
    # These are for the 'get' method if we want to dynamically load
    _registry = {
        "cv2": "OpenCV for video processing",
        "numpy": "Numerical operations",
        "PIL": "Image processing (Pillow)",
        "psutil": "System health monitoring",
        "tqdm": "Progress bars",
        "dotenv": "Environment variable management"
    }

    @staticmethod
    def get(module_name: str):
        """
        Attempts to import a standard module dynamically.
        """
        if module_name in NecessaryImportGate._loaded_modules:
            return NecessaryImportGate._loaded_modules[module_name]

        try:
            import importlib
            mod = importlib.import_module(module_name)
            NecessaryImportGate._loaded_modules[module_name] = mod
            return mod
        except ImportError as e:
            logger.error(f"❌ NecessaryImportGate: Critical dependency '{module_name}' missing: {e}")
            return None

# Export common modules for easy access via 'from necessary_import_gate import ...'
# This satisfies the "remove headache" requirement.
__all__ = [
    'os', 'sys', 'logging', 'asyncio', 'shutil', 're', 'time', 'subprocess',
    'csv', 'json', 'io', 'uuid', 'random', 'tempfile', 'glob', 'Path',
    'datetime', 'List', 'Optional', 'Dict', 'Tuple', 'Any', 'load_dotenv',
    'threading', 'contextmanager', 'urlparse', 'ThreadPoolExecutor'
]
