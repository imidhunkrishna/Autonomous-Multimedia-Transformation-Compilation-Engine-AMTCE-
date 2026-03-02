import os
import hashlib
import logging
import shutil

logger = logging.getLogger("audio_deduplicator")

def get_file_hash(filepath: str, block_size: int = 65536) -> str:
    """Calculates MD5 hash of a file's content."""
    md5 = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                md5.update(block)
        return md5.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to hash {filepath}: {e}")
        return ""

def scan_and_clean_duplicates(directory: str):
    """
    Scans the directory for duplicate audio files based on content hash.
    Keeps the oldest file (by modification time) and removes duplicates.
    """
    if not os.path.exists(directory):
        logger.warning(f"Directory not found: {directory}")
        return

    logger.info(f"🎵 Starting Audio Deduplication Scan in: {directory}")
    
    # Store hashes: {hash: [path1, path2]}
    hashes = {}
    
    valid_extensions = ('.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac')
    
    # scan for files
    file_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(valid_extensions):
                file_list.append(os.path.join(root, file))

    if not file_list:
        logger.info("ℹ️ No audio files found to scan.")
        return

    # Calculate hashes
    logger.info(f"🔎 Hashing {len(file_list)} audio files...")
    for file_path in file_list:
        # Check size first? 0 byte files skip?
        if os.path.getsize(file_path) == 0:
            continue
            
        file_hash = get_file_hash(file_path)
        if file_hash:
            if file_hash not in hashes:
                hashes[file_hash] = []
            hashes[file_hash].append(file_path)

    # Process duplicates
    duplicates_found = 0
    bytes_saved = 0
    
    for file_hash, paths in hashes.items():
        if len(paths) > 1:
            # Sort by modification time (Keep the oldest one -> original)
            # mtime: smaller is older
            paths.sort(key=lambda p: os.path.getmtime(p))
            
            original = paths[0]
            duplicates = paths[1:]
            
            for dup in duplicates:
                try:
                    size = os.path.getsize(dup)
                    os.remove(dup)
                    logger.info(f"🗑️ [DEDUPE] Removed duplicate: {os.path.basename(dup)} (Matches {os.path.basename(original)})")
                    bytes_saved += size
                    duplicates_found += 1
                except Exception as e:
                    logger.error(f"❌ Failed to delete duplicate {dup}: {e}")

    if duplicates_found > 0:
        mb_saved = bytes_saved / (1024 * 1024)
        logger.info(f"✅ Audio Deduplication Complete. Removed {duplicates_found} files. Saved {mb_saved:.2f} MB.")
    else:
        logger.info("✅ No duplicates found.")
