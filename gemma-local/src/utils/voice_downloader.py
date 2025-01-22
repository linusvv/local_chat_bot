import os
from pathlib import Path
import urllib.request

def download_voice_model(voice_name="en_US-amy-low"):
    """Download Piper voice model if not present"""
    voice_dir = Path("voices")
    voice_path = voice_dir / f"{voice_name}.onnx"
    
    if not voice_path.exists():
        print(f"Downloading voice model {voice_name}...")
        voice_dir.mkdir(parents=True, exist_ok=True)
        
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low"
        
        # Download model and config
        for ext in [".onnx", ".onnx.json"]:
            url = f"{base_url}/{voice_name}{ext}"
            target = voice_dir / f"{voice_name}{ext}"
            
            try:
                urllib.request.urlretrieve(url, target)
            except Exception as e:
                print(f"Error downloading {url}: {e}")
                return None
    
    return str(voice_path)
