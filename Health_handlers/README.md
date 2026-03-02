# 🏥 Health Handlers (The Life Support)

## Use Case
Monitors the system resource levels (CPU, RAM, GPU, Disk) to ensure the engine doesn't crash the machine during heavy processing.

## What it is good at
1.  **Safety Gates**: Prevents "Heavy Imports" (like Torch) if the system is low on RAM or VRAM, forcing a safe CPU-only fallback.
2.  **Real-Time Monitoring**: Provides a structured health status that the `main.py` uses to pause processing if the machine gets too hot or full.

## Step-by-Step Usage

1.  **Check Health**:
    ```python
    from health import check_health
    status = check_health()
    print(f"Is system safe to run AI? {status['safe']}")
    ```
2.  **Standalone Diagnostic**:
    You can run `python health.py` directly to see a full system health report in the console.
