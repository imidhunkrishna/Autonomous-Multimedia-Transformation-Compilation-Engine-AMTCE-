import os

SRC = r'd:\Autonomous Multimedia Transformation & Compilation Engine (AMTCE)'

SKIP_DIRS = {
    '__pycache__', '.git', 'venv', 'scripts', 'Processed Shorts',
    'Processed_Cache', 'Original_audio', 'The_json',
    'Datasets_and_text_files', 'Credentials', 'Monetization_Metrics',
    '.gradio', 'models', 'node_modules', 'site-packages',
    'Hunter_Modules', 'Installation_Modules', 'Health_handlers',
    'Watermark_Colab.ipynb', 'Download_Modules', 'Uploader_Modules'
}

# Only look inside our project module dirs
PROJECT_MODULE_DIRS = [
    'Compiler_Modules',
    'Intelligence_Modules',
    'Audio_Modules',
    'Text_Modules',
    'Visual_Refinement_Modules',
    'Upscale_Modules',
]

# Collect all .py modules
all_modules = []
for mod_dir in PROJECT_MODULE_DIRS:
    dir_path = os.path.join(SRC, mod_dir)
    if not os.path.isdir(dir_path):
        continue
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if (f.endswith('.py') and f != '__init__.py'):
                rel = os.path.relpath(os.path.join(root, f), SRC)
                all_modules.append(rel)

# Also check root-level py files
for f in os.listdir(SRC):
    if f.endswith('.py') and f not in ('__init__.py', 'orphan_check.py'):
        all_modules.append(f)

# Read all main pipeline entry-point files
PIPELINE_FILES = [
    'Compiler_Modules/orchestrator.py',
    'Compiler_Modules/video_pipeline.py',
    'Compiler_Modules/audio_pipeline.py',
    'Compiler_Modules/overlay_engine.py',
    'compiler.py',
    'main.py',
]
pipeline_src = ''
for pf in PIPELINE_FILES:
    fp = os.path.join(SRC, pf.replace('/', os.sep))
    try:
        pipeline_src += open(fp, encoding='utf-8').read()
    except Exception:
        pass

wired = []
orphans = []
for m in sorted(all_modules):
    base = os.path.splitext(os.path.basename(m))[0]
    if base in pipeline_src:
        wired.append(m)
    else:
        orphans.append(m)

print("=== WIRED (referenced in pipeline) ===")
for m in wired:
    print("  OK    " + m)

print("\n=== ORPHANS (NOT referenced anywhere in pipeline) ===")
for m in orphans:
    print("  !!!!  " + m)

print(f"\n  Total: {len(wired)} wired, {len(orphans)} orphans, {len(all_modules)} total")
