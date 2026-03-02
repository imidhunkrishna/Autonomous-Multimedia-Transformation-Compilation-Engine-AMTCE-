import logging
import asyncio
import os
from Compiler_Modules import orchestrator

# Compatibility Shim
# This allows main.py to continue importing 'compiler' without breaking.
# We map the old functions to the new Orchestrator.

logger = logging.getLogger("compiler_shim")

async def process_video_pipeline(job_uuid, input_path, output_path, title, description, **kwargs):
    """
    Async wrapper for the new synchronous orchestrator.
    Minimizes change radius in main.py.
    """
    logger.info(f"Using New Compiler Module for: {job_uuid}")
    
    # Offload to thread to keep async loop unblocked
    result = await asyncio.to_thread(
        orchestrator.compile_video,
        job_uuid,
        input_path,
        output_path,
        title,
        description,
        kwargs
    )
    return result

# --- SHIM MAPPINGS ---

from pathlib import Path

# --- SHIM MAPPINGS ---

def compile_batch_with_transitions(file_list, output_file, **kwargs):
    """Shim for batch compilation."""
    logger.info(f"Shim: compile_batch_with_transitions -> orchestrator.compile_batch")
    # Sanitization
    if isinstance(file_list, (str, Path)):
        file_list = [str(file_list)]
    
    # Ensure all items are strings
    file_list = [str(f) for f in file_list]
        
    result_path = orchestrator.compile_batch(file_list, output_file)
    # Batch usually returns just path? Based on main.py line 1563 usage 'merged = ...', yes.
    # But let's check if usage elsewhere expects tuple. 
    # Logic in main.py 1563 assigns to 'merged' (scalar). 
    # But compile_with_transitions usage caused unpack error.
    
    return result_path

import uuid

def compile_with_transitions(file_list, output_file, **kwargs):
    """
    Shim for compilation.
    CRITICAL RESTORATION: This must perform the FULL processing (Overlays, Filters),
    not just a simple batch concatenation.
    """
    logger.info(f"Shim: compile_with_transitions (Full Pipeline)")
    
    # Sanitization
    if isinstance(file_list, (str, Path)):
        file_list = [str(file_list)]
    file_list = [str(f) for f in file_list]
    
    # Extension Safety
    if not os.path.splitext(output_file)[1]:
        output_file = f"{output_file}.mp4"
    
    # CASE 1: Single Video (Standard Flow)
    if len(file_list) == 1:
        input_path = file_list[0]
        logger.info("⚡ Single File detected -> Routing to Orchestrator.compile_video (Smart Render)")
        
        # Generate valid props for the Orchestrator
        job_id = f"job_{uuid.uuid4().hex[:6]}"
        
        # Extract title from filename if not provided in kwargs
        # The main.py usually doesn't pass title here, it expects the compiler to handle it?
        # Or it passed it in kwargs? Check kwargs.
        # If CLI run, we have no metadata.
        
        raw_title = kwargs.get("title", Path(input_path).stem)
        description = kwargs.get("description", "Automated Compilation")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)) or ".", exist_ok=True)

        try:
             # CALL THE BRAIN
             orchestrator.compile_video(
                 uuid_str=job_id,
                 input_path=input_path,
                 output_path=output_file,
                 title=raw_title,
                 description=description,
                 profile_data=kwargs
             )
             return output_file, {"job_id": job_id}
             
        except Exception as e:
            logger.error(f"Smart Render Failed: {e}", exc_info=True)
            return None, {}

    # CASE 2: Multiple Videos (Batch Processing)
    # If we have multiple videos, we should probably process them individually then stitch?
    # Or just stitch. For now, let's keep batch=concat via existing shim,
    # but maybe we should map compile_batch_with_transitions to this logic too?
    # No, 'compile_batch' implies stitching.
    
    # Fallback to concat for actual lists > 1
    return orchestrator.compile_batch(file_list, output_file)

# Alias for safety if names vary
process_batch = compile_batch_with_transitions
