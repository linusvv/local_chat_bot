import requests
from requests.exceptions import Timeout
from config.settings import (
    OLLAMA_BASE_URL, 
    GEMMA_MODEL_NAME, 
    MAX_TOKENS, 
    TEMPERATURE,
    SYSTEM_PROMPT
)

class GemmaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = GEMMA_MODEL_NAME
        self.context = []
        self.timeout = 10  # 10 seconds timeout for requests
        self._shutdown = False

    def shutdown(self):
        """Clean shutdown of client resources"""
        self._shutdown = True

    def generate_response(self, prompt: str) -> str:
        """Generate a single response"""
        if self._shutdown:
            return ""
            
        url = f"{self.base_url}/api/generate"
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {prompt}\nAssistant:"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "context": self.context
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            response_data = response.json()
            
            if 'context' in response_data:
                self.context = response_data['context']
                
            return response_data['response']
        except Timeout:
            print("Response generation timed out")
            return "I'm sorry, I'm taking too long to respond. Could you try again?"
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I apologize, but I had trouble generating a response."
