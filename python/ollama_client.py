# python/ollama_client.py
"""
Ollama Client Wrapper for REDACTED Swarm
=========================================
This module provides a Python interface to interact with Ollama's local LLM server.
Supports chat completion, tool calling, and streaming responses.

Dependencies:
- requests (for HTTP communication)
- json (for payload handling)

Configuration:
- Default model: qwen:2.5 (recommended for tool calling)
- Alternative: llama3.2
- Base URL: http://localhost:11434 (Ollama default)
"""

import requests
import json
from typing import Optional, List, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaClient:
    """
    Client for interacting with Ollama's API.
    
    Features:
    - Chat completion with system/user/assistant messages
    - Tool calling support (requires Qwen 2.5 or Llama 3.2)
    - Streaming and non-streaming modes
    - Error handling and retry logic
    - Response parsing and validation
    """
    
    def __init__(
        self,
        model: str = "qwen:2.5",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        max_retries: int = 3
    ):
        """
        Initialize Ollama client.
        
        Args:
            model: Ollama model to use (e.g., "qwen:2.5", "llama3.2")
            base_url: Ollama server URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts on failure
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.generate_endpoint = f"{self.base_url}/api/generate"
        
        # Verify connection on initialization
        self._verify_connection()
    
    def _verify_connection(self) -> bool:
        """Verify Ollama server is running and accessible."""
        try:
            response = requests.get(f"{self.base_url}/api/version", timeout=5)
            if response.status_code == 200:
                logger.info(f"✓ Connected to Ollama server at {self.base_url}")
                logger.info(f"  Model: {self.model}")
                return True
            else:
                logger.warning(f"⚠ Ollama server returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Cannot connect to Ollama server at {self.base_url}")
            logger.error("  Please ensure Ollama is running: 'ollama serve'")
            return False
        except Exception as e:
            logger.error(f"✗ Error verifying connection: {str(e)}")
            return False
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response from Ollama using the chat API.
        
        Args:
            messages: List of message dictionaries (role, content)
            tools: List of tool definitions for function calling
            stream: Whether to stream the response
            options: Additional model options (temperature, top_p, etc.)
        
        Returns:
            Dictionary containing the response data
            
        Example:
            client = OllamaClient()
            response = client.generate(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": "What's the weather like?"}
                ],
                tools=[{"type": "function", "function": {...}}]
            )
        """
        # Build request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        # Add tools if provided
        if tools:
            payload["tools"] = tools
            logger.debug(f"Tools enabled: {len(tools)} functions available")
        
        # Add custom options
        if options:
            payload["options"] = options
        
        # Make request with retry logic
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Sending request to Ollama (attempt {attempt + 1}/{self.max_retries})")
                response = requests.post(
                    self.chat_endpoint,
                    json=payload,
                    timeout=self.timeout,
                    stream=stream
                )
                
                response.raise_for_status()
                
                if stream:
                    return self._handle_stream_response(response)
                else:
                    result = response.json()
                    logger.info(f"✓ Received response (tokens: {result.get('eval_count', 'N/A')})")
                    return result
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {str(e)}")
                if attempt == self.max_retries - 1:
                    raise Exception(f"Failed to get response from Ollama after {self.max_retries} attempts: {str(e)}")
                continue
        
        raise Exception("Unexpected error in generate method")
    
    def _handle_stream_response(self, response) -> Dict[str, Any]:
        """
        Handle streaming response from Ollama.
        
        Args:
            response: Streaming HTTP response object
            
        Returns:
            Aggregated response dictionary
        """
        full_response = {
            "model": self.model,
            "created_at": None,
            "message": {"role": "assistant", "content": ""},
            "done": False,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "eval_count": 0,
            "eval_duration": 0
        }
        
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                
                # Initialize created_at from first chunk
                if not full_response["created_at"]:
                    full_response["created_at"] = chunk.get("created_at")
                
                # Append message content
                if "message" in chunk and "content" in chunk["message"]:
                    full_response["message"]["content"] += chunk["message"]["content"]
                
                # Accumulate statistics
                full_response["total_duration"] += chunk.get("total_duration", 0)
                full_response["load_duration"] += chunk.get("load_duration", 0)
                full_response["eval_count"] += chunk.get("eval_count", 0)
                full_response["eval_duration"] += chunk.get("eval_duration", 0)
                
                # Update done status
                full_response["done"] = chunk.get("done", False)
        
        logger.info(f"✓ Stream complete (tokens: {full_response['eval_count']})")
        return full_response
    
    def list_models(self) -> List[str]:
        """
        List available models on the Ollama server.
        
        Returns:
            List of model names
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama's library.
        
        Args:
            model_name: Name of the model to pull
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Pulling model: {model_name}")
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=None
            )
            
            for line in response.iter_lines():
                if line:
                    status = json.loads(line.decode('utf-8'))
                    if "status" in status:
                        logger.info(f"  {status['status']}")
                    if status.get("done"):
                        logger.info(f"✓ Model {model_name} pulled successfully")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {str(e)}")
            return False
    
    def health_check(self) -> bool:
        """
        Check if Ollama server is healthy and responsive.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except:
            return False
