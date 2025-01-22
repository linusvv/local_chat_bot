import signal
import sys
from models.gemma_client import GemmaClient
from utils.audio_handler import AudioHandler
from utils.tts_handler import TTSHandler
import time
import threading
import asyncio
import os
import sounddevice as sd  # Add this import

def main():
    print("Starting Gemma service...")
    client = GemmaClient()
    
    # Initialize components and flags
    audio_handler = None
    tts_handler = None
    timeout_thread = None
    running = True
    cleanup_in_progress = False

    def force_exit():
        print("\nForcing exit...")
        if client:
            client.shutdown()
        os._exit(1)

    def signal_handler(signum, frame):
        nonlocal running, cleanup_in_progress
        if cleanup_in_progress:  # If cleanup is stuck, force exit
            force_exit()
            return
            
        if not running:  # Prevent multiple shutdown attempts
            return
            
        print("\nReceived shutdown signal. Cleaning up...")
        running = False
        cleanup_in_progress = True
        
        if client:
            client.shutdown()
        if audio_handler:
            audio_handler.pause_listening()
            
        # Set a timeout for cleanup
        threading.Timer(5.0, force_exit).start()
            
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        audio_handler = AudioHandler()
        tts_handler = TTSHandler()
        
        if not audio_handler.is_ready or not tts_handler.is_ready:
            raise Exception("Audio systems not initialized properly")
        
        # Use a threading event for cleaner shutdown
        shutdown_event = threading.Event()
        state_lock = threading.Lock()
        conversation_state = {
            'in_conversation': False,
            'last_interaction': time.time(),
            'processing': False
        }
        
        print("\nReady! Listening for wake word 'Hey Gemma'...")
        
        def update_last_interaction():
            with state_lock:
                conversation_state['last_interaction'] = time.time()
        
        def handle_speech(text):
            with state_lock:
                if conversation_state.get('processing', False):
                    print("Still processing previous request...")
                    return

                conversation_state['processing'] = True
                try:
                    if not conversation_state['in_conversation']:
                        if "hey gemma" in text:
                            print("\nWake word detected!")
                            audio_handler.pause_listening()
                            conversation_state['in_conversation'] = True
                            conversation_state['last_interaction'] = time.time()
                            
                            tts_handler.speak(
                                "Hi! How can I help you?",
                                on_complete=lambda: audio_handler.resume_listening()
                            )
                    else:
                        if "thanks and goodbye" in text:
                            print("\nEnding conversation...")
                            audio_handler.pause_listening()
                            conversation_state['in_conversation'] = False
                            tts_handler.speak(
                                "Goodbye! Let me know if you need anything else.",
                                on_complete=lambda: audio_handler.resume_listening()
                            )
                            print("\nListening for wake word 'Hey Gemma'...")
                        elif time.time() - conversation_state['last_interaction'] > 20:
                            print("\nConversation timed out")
                            audio_handler.pause_listening()
                            conversation_state['in_conversation'] = False
                            tts_handler.speak(
                                "Goodbye! Let me know if you need anything else.",
                                on_complete=lambda: audio_handler.resume_listening()
                            )
                            print("\nListening for wake word 'Hey Gemma'...")
                        else:
                            print(f"\nYou: {text}")
                            audio_handler.pause_listening()
                            try:
                                # Generate response
                                response = client.generate_response(text)
                                print("Gemma:", response)
                                
                                # Update interaction time before TTS starts
                                conversation_state['last_interaction'] = time.time()
                                
                                # Use async TTS
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                _, audio_data, samplerate = loop.run_until_complete(
                                    tts_handler.prepare_speech(response)
                                )
                                loop.close()
                                
                                # Calculate speech duration
                                duration = len(audio_data) / samplerate
                                
                                # Update interaction time to account for speech duration
                                conversation_state['last_interaction'] = time.time() + duration + 1
                                
                                # Play the prepared audio using TTS handler
                                tts_handler.play_audio(audio_data, samplerate, 
                                    on_complete=lambda: audio_handler.resume_listening()
                                )
                                
                            except Exception as e:
                                print(f"Error processing response: {e}")
                                tts_handler.speak(
                                    "I'm sorry, I had trouble processing that. Could you try again?",
                                    on_complete=lambda: audio_handler.resume_listening()
                                )
                finally:
                    conversation_state['processing'] = False
        
        # Start monitoring thread for conversation timeout
        def check_timeout():
            while not shutdown_event.is_set():
                try:
                    time.sleep(1)
                    with state_lock:
                        current_time = time.time()
                        if (conversation_state['in_conversation'] and 
                            not conversation_state.get('processing', False) and
                            current_time - conversation_state['last_interaction'] > 20):
                                print("\nDebug: Time since last interaction:", 
                                      current_time - conversation_state['last_interaction'])
                                # Reset conversation state before handling timeout
                                conversation_state['in_conversation'] = False
                                audio_handler.pause_listening()
                                tts_handler.speak(
                                    "Shush! I'm going to take a nap now. Let me know if you need anything.",
                                    on_complete=lambda: audio_handler.resume_listening()
                                )
                                print("\nListening for wake word 'Hey Gemma'...")
                except Exception as e:
                    print(f"Error in timeout thread: {e}")

        timeout_thread = threading.Thread(target=check_timeout, daemon=True)
        timeout_thread.start()
        
        # Start main listening loop
        while running:
            try:
                if not audio_handler.is_ready:
                    print("Audio handler lost connection. Attempting to restart...")
                    time.sleep(1)
                    continue
                    
                audio_handler.listen_continuous(handle_speech)
            except Exception as e:
                if running:  # Only show error if not shutting down
                    print(f"\nError in main loop: {e}")
                    print("Attempting to restart listening...")
                    time.sleep(1)
                continue
    
    except Exception as e:
        print(f"Fatal error: {e}")
    
    finally:
        if not cleanup_in_progress:  # Only cleanup if not already in progress
            print("\nCleaning up...")
            running = False
            cleanup_in_progress = True
            
            try:
                # Shutdown all components in order
                client.shutdown()
                if audio_handler:
                    audio_handler.pause_listening()
                if timeout_thread and timeout_thread.is_alive():
                    shutdown_event.set()
                    timeout_thread.join(timeout=1)
                    
                # Close executor in GemmaClient
                if hasattr(client, 'executor'):
                    client.executor.shutdown(wait=False)
                    
            except Exception as e:
                print(f"Error during cleanup: {e}")
            finally:
                print("Goodbye!")
                sys.exit(0)

if __name__ == "__main__":
    main()