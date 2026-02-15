"""
Utility functions for interacting with Ollama.
"""

import subprocess
import json
from typing import Optional


def get_running_ollama_model() -> Optional[str]:
    """
    Detects the currently running Ollama model.
    
    Returns:
        str or None: Name of the running model, or None if no model is running.
    """
    try:
        # Get list of running models
        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            # First data row contains MODEL NAME column
            model_info = lines[1].strip()
            parts = model_info.split()
            if parts:
                return parts[0]  # Return first part as model name
        
        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_available_models() -> list:
    """Get list of available models in Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        models = []
        for line in lines:
            if line.strip():
                model_name = line.split()[0]
                models.append(model_name)
        return models
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# Default fallback model if detection fails
DEFAULT_FALLBACK_MODEL = "qwen:2.5"

