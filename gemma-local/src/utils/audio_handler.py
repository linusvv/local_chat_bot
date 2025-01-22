import json
import vosk
import pyaudio
from pathlib import Path
import requests
from tqdm import tqdm
import zipfile
import shutil
import os

class AudioHandler:
    VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    
    def __init__(self):
        self._ready = False
        self._listening = False
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Setup Vosk
        model_path = Path(__file__).parent.parent / "models" / "vosk-model-small-en-us-0.15"
        if not model_path.exists():
            print("Downloading Vosk model...")
            self._download_and_extract_model(model_path)
            
        try:
            print("Loading Vosk model...")
            self.model = vosk.Model(str(model_path))
            self.rec = vosk.KaldiRecognizer(self.model, 16000)
            self._ready = True
            print("Vosk model loaded successfully!")
        except Exception as e:
            print(f"Error loading Vosk model: {e}")
            raise

    def _download_and_extract_model(self, model_path):
        try:
            # Create models directory if it doesn't exist
            model_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download with progress bar
            response = requests.get(self.VOSK_MODEL_URL, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            zip_path = model_path.parent / "model.zip"
            with open(zip_path, 'wb') as f, tqdm(
                desc="Downloading",
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as pbar:
                for data in response.iter_content(chunk_size=1024):
                    size = f.write(data)
                    pbar.update(size)
            
            # Extract with progress bar
            print("Extracting model files...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get total size for progress bar
                total_size = sum(file.file_size for file in zip_ref.filelist)
                extracted_size = 0
                
                for file in tqdm(zip_ref.filelist, desc="Extracting"):
                    zip_ref.extract(file, model_path.parent)
                    extracted_size += file.file_size
            
            # Cleanup
            print("Cleaning up temporary files...")
            zip_path.unlink()
            print("Model setup complete!")
            
        except Exception as e:
            print(f"Error downloading/extracting model: {e}")
            if model_path.exists():
                shutil.rmtree(model_path)
            if zip_path.exists():
                zip_path.unlink()
            raise

    @property
    def is_ready(self):
        return self._ready

    def pause_listening(self):
        self._listening = False

    def resume_listening(self):
        self._listening = True

    def listen_continuous(self, callback):
        if not self._ready:
            return

        self._listening = True
        stream = None
        try:
            stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=16000, 
                                   input=True, frames_per_buffer=8000)
            
            while self._listening:
                try:
                    data = stream.read(4000, exception_on_overflow=False)
                    if self.rec.AcceptWaveform(data):
                        result = json.loads(self.rec.Result())
                        if result.get("text"):
                            callback(result["text"].lower())
                except Exception as e:
                    print(f"Error in audio processing: {e}")
                    if not self._listening:  # Break if we're shutting down
                        break
                    continue

        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass

    def listen(self):
        """Single listening instance for basic usage"""
        if not self._ready:
            return None

        stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=16000, 
                               input=True, frames_per_buffer=8000)
        
        try:
            # Listen for up to 5 seconds
            for _ in range(20):  # 5 seconds = 20 * 0.25s chunks
                data = stream.read(4000, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    if result.get("text"):
                        return result["text"].lower()
        finally:
            stream.stop_stream()
            stream.close()
        
        return None

    def __del__(self):
        self._listening = False
        if hasattr(self, 'audio'):
            try:
                self.audio.terminate()
            except:
                pass
