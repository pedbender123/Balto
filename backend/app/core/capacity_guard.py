import logging
from datetime import datetime
import os

try:
    import psutil
except ImportError:
    psutil = None

import time
from collections import deque
from app.core import config

class CapacityGuard:
    """
    Protects the server from overload by monitoring:
    1. CPU Usage
    2. RAM Usage
    3. Processing Latency Ratio (Processing Time / Audio Duration)
    """
    
    _latency_ratios = deque(maxlen=20) # Store last 20 processing stats
    
    @classmethod
    def check_availability(cls) -> tuple[bool, str | None]:
        """
        Returns (True, None) if system is healthy.
        Returns (False, Reason) if system is overloaded.
        """
        if psutil is None:
            # If psutil is not available, we cannot check system load.
            # Assume available for now, or return an error if strict.
            # For this context, let's assume it's available if psutil is missing,
            # as the primary concern is latency ratio.
            # Or, more safely, indicate it's unavailable due to missing dependency.
            return False, "System monitoring unavailable (psutil not installed)"

        # 1. Check CPU
        cpu_usage, mem_percent = cls.get_system_load()
        if cpu_usage > config.CAPACITY_MAX_CPU_PERCENT:
             # Check again with small interval to be sure it's not a micro-spike?
             # For real-time audio, immediate rejection is safer.
             return False, f"CPU Overloaded ({cpu_usage:.1f}%)"

        # 2. Check RAM
        if mem_percent > config.CAPACITY_MAX_RAM_PERCENT:
             return False, f"RAM Overloaded ({mem_percent:.1f}%)"

        # 3. Check Latency Ratio (Voortrack)
        # If the average ratio > Threshold (e.g. 3.0), we are too slow.
        if len(cls._latency_ratios) > 5:
            avg_ratio = sum(cls._latency_ratios) / len(cls._latency_ratios)
            if avg_ratio > config.CAPACITY_MAX_LATENCY_RATIO:
                return False, f"High Latency (Ratio: {avg_ratio:.2f}x)"

        return True, None

    @classmethod
    def report_processing_metrics(cls, audio_duration_sec: float, processing_duration_sec: float):
        """
        Updates the internal latency tracker.
        Ratio = Processing Time / Audio Time.
        Ratio > 1.0 means we are slower than real-time.
        Ratio > 3.0 is critical lag.
        """
        if audio_duration_sec <= 0:
            return

        ratio = processing_duration_sec / audio_duration_sec
        cls._latency_ratios.append(ratio)
        
        # Optional debug
        # print(f"[CapacityGuard] Latency Ratio: {ratio:.2f}x")

    @classmethod
    def get_system_load(cls) -> tuple[float, float]:
        """
        Returns (cpu_percent, ram_percent)
        """
        if psutil is None:
            return 0.0, 0.0
            
        cpu = psutil.cpu_percent(interval=None) # Non-blocking immediate
        ram = psutil.virtual_memory().percent
        return cpu, ram
