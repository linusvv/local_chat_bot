import edge_tts
import asyncio
import sounddevice as sd
import soundfile as sf
from pathlib import Path
import tempfile
import time
import re
from collections import deque
from typing import List, Tuple

class TTSHandler:
    FALLBACK_VOICES = [
        "en-US-ChristopherNeural",
        "en-US-EricNeural",
        "en-US-GuyNeural",
        "en-GB-RyanNeural"
    ]

    def __init__(self):
        self.voice = "en-GB-RyanNeural"  # Start with default voice
        self.temp_dir = Path(tempfile.gettempdir())
        self._ready = True
        self.tts_timeout = 10
        self._current_voice_index = 0

    def split_into_chunks(self, text: str) -> List[str]:
        """Split text into chunks at sentence boundaries"""
        # Split at sentence endings or commas for natural pauses
        chunks = re.split(r'(?<=[.!?])\s+', text)
        # Filter out empty chunks and ensure reasonable length
        return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 0]

    async def _try_voice(self, text: str, voice: str, temp_file: Path) -> bool:
        """Try to generate speech with a specific voice"""
        try:
            communicate = edge_tts.Communicate(text, voice)
            await asyncio.wait_for(
                communicate.save(str(temp_file)), 
                timeout=self.tts_timeout
            )
            return True
        except:
            return False

    async def prepare_speech(self, text: str) -> tuple[str, bytes, int]:
        """Prepare speech audio data asynchronously"""
        temp_file = self.temp_dir / f"temp_speech_{hash(text)}.wav"
        
        # Try current voice first, then fallbacks
        success = await self._try_voice(text, self.voice, temp_file)
        if not success:
            for voice in self.FALLBACK_VOICES:
                if voice != self.voice and await self._try_voice(text, voice, temp_file):
                    self.voice = voice
                    success = True
                    break
        
        if not success:
            raise Exception("All voices failed to generate speech")
            
        # Read audio data
        data, samplerate = sf.read(temp_file)
        temp_file.unlink(missing_ok=True)
        
        return text, data, samplerate

    async def prepare_speech_chunks(self, text: str) -> List[Tuple[bytes, int]]:
        """Prepare multiple chunks of speech in parallel"""
        chunks = self.split_into_chunks(text)
        tasks = []
        
        for chunk in chunks:
            if len(chunk) > 0:
                tasks.append(self.prepare_speech(chunk))
        
        try:
            results = await asyncio.gather(*tasks)
            # Extract just the audio data and samplerate
            return [(audio, rate) for _, audio, rate in results]
        except Exception as e:
            print(f"Error preparing speech chunks: {e}")
            raise

    def play_audio(self, audio_data, samplerate, on_complete=None):
        """Play audio data with proper cleanup"""
        try:
            sd.play(audio_data, samplerate)
            duration = len(audio_data) / samplerate
            time.sleep(duration + 0.5)  # Add small buffer
            sd.stop()
            
            if on_complete:
                on_complete()
            return True
        except Exception as e:
            print(f"Error playing audio: {e}")
            if on_complete:
                on_complete()
            return False

    def play_audio_chunks(self, chunks: List[Tuple[bytes, int]], on_complete=None):
        """Play multiple audio chunks sequentially"""
        try:
            for audio_data, samplerate in chunks:
                sd.play(audio_data, samplerate)
                duration = len(audio_data) / samplerate
                time.sleep(duration + 0.1)  # Small pause between chunks
                sd.stop()
            
            if on_complete:
                on_complete()
            return True
        except Exception as e:
            print(f"Error playing audio chunks: {e}")
            if on_complete:
                on_complete()
            return False

    @property
    def is_ready(self):
        return self._ready

    def speak(self, text: str, on_complete=None):
        """Enhanced speak method with chunk processing"""
        if not self._ready:
            return False

        try:
            # Prepare all chunks in parallel
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            chunks = loop.run_until_complete(self.prepare_speech_chunks(text))
            loop.close()
            
            # Play chunks sequentially
            self.play_audio_chunks(chunks, on_complete)
            return True
            
        except Exception as e:
            print(f"Error in TTS: {e}")
            if on_complete:
                on_complete()
            return False

    def __del__(self):
        try:
            sd.stop()
            for temp_file in self.temp_dir.glob("temp_speech*.wav"):
                temp_file.unlink(missing_ok=True)
        except:
            pass
