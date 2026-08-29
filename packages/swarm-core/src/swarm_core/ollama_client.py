"""
Enhanced Ollama Client for REDACTED Swarm
========================================
Advanced client for interacting with Ollama API with streaming, 
retry logic, health checks, and improved tool calling.

Features:
- Streaming responses for real-time output
- Automatic retry with exponential backoff
- Connection health checks
- Enhanced tool calling support
- Model capability detection
"""

import json
import requests
import time
from typing import Dict, List, Optional, Generator, Any
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import logging

# Configure logging
logger = logging.getLogger(__name__)

class OllamaClient:
    """
    Enhanced client for interacting with Ollama API.
    
    Provides robust communication with Ollama service including:
    - Streaming responses
    - Automatic retries
    - Health checks
    - Tool calling support
    """
    
    def __init__(self, model: str = "qwen:2.5", base_url: str = "http://localhost:11434"):
        """
        Initialize the Ollama client.
        
        Args:
            model: Default model to use for completions
            base_url: Base URL for Ollama API
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Test connection on initialization
        if not self.health_check():
            logger.warning("⚠ Ollama service not responding. Please ensure Ollama is running.")
    
    def health_check(self) -> bool:
        """
        Check if Ollama service is running and healthy.
        
        Returns:
            bool: True if service is healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {str(e)}")
            return False
    
    def list_models(self) -> List[str]:
        """
        List all available models in Ollama.
        
        Returns:
            List of model names
        """
        try:
            response = self.session.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            return [model["name"] for model in models]
        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama library.
        
        Args:
            model_name: Name of the model to pull
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True
            )
            response.raise_for_status()
            
            # Process streaming response
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        logger.info(f"Pull status: {data['status']}")
                    if "error" in data:
                        logger.error(f"Pull error: {data['error']}")
                        return False
            
            logger.info(f"Successfully pulled model: {model_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {str(e)}")
            return False
    
    def get_model_info(self, model_name: str = None) -> Dict[str, Any]:
        """
        Get detailed information about a model.
        
        Args:
            model_name: Name of the model (defaults to current model)
            
        Returns:
            Dictionary with model information
        """
        model_name = model_name or self.model
        try:
            response = self.session.post(
                f"{self.base_url}/api/show",
                json={"name": model_name}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get model info for {model_name}: {str(e)}")
            return {}
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict]] = None,
        options: Optional[Dict] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a chat completion using Ollama.
        
        Args:
            messages: List of message dictionaries with role/content
            tools: Optional list of tool definitions
            options: Model options (temperature, etc.)
            stream: Whether to stream the response
            
        Returns:
            Dictionary with response data
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if tools:
            payload["tools"] = tools
            
        if options:
            payload["options"] = options
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Chat completion failed: {str(e)}")
            raise
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        options: Optional[Dict] = None,
        stream: bool = False
    ) -> Dict[str, Any] | Generator[Dict[str, Any], None, None]:
        """
        Generate a completion with enhanced features.
        
        Args:
            messages: List of message dictionaries with role/content
            tools: Optional list of tool definitions
            options: Model options (temperature, etc.)
            stream: Whether to stream the response
            
        Returns:
            Response dictionary or generator for streaming
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if tools:
            payload["tools"] = tools
            
        if options:
            payload["options"] = options
        
        try:
            if stream:
                return self._stream_generate(payload)
            else:
                response = self.session.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise
    
    def _stream_generate(self, payload: Dict) -> Generator[Dict[str, Any], None, None]:
        """
        Internal method to handle streaming responses.
        
        Args:
            payload: Request payload
            
        Yields:
            Response chunks as dictionaries
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        yield chunk
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode streaming chunk: {line}")
        except Exception as e:
            logger.error(f"Streaming generation failed: {str(e)}")
            raise
    
    def embedding(self, prompt: str) -> List[float]:
        """
        Generate embeddings for a prompt.
        
        Args:
            prompt: Text to generate embeddings for
            
        Returns:
            List of embedding values
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": prompt
                }
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise
    
    def model_capabilities(self, model_name: str = None) -> Dict[str, Any]:
        """
        Get capabilities of a model.
        
        Args:
            model_name: Name of the model (defaults to current model)
            
        Returns:
            Dictionary with model capabilities
        """
        model_name = model_name or self.model
        info = self.get_model_info(model_name)
        
        # Extract capabilities from model info
        capabilities = {
            "tool_calling": False,
            "streaming": True,  # Ollama generally supports streaming
            "embedding": False,
            "context_length": None,
            "family": None
        }
        
        # Try to determine capabilities from model info
        if info:
            # Check for tool calling capability
            if "template" in info and "tools" in str(info["template"]).lower():
                capabilities["tool_calling"] = True
            
            # Extract model family if available
            if "details" in info:
                capabilities["family"] = info["details"].get("family")
                capabilities["context_length"] = info["details"].get("context_length")
            
            # Check for embedding capability
            if "embed" in info.get("details", {}):
                capabilities["embedding"] = True
        
        return capabilities
    
    def benchmark_model(self, model_name: str = None, prompt: str = None) -> Dict[str, Any]:
        """
        Benchmark a model's performance.
        
        Args:
            model_name: Name of the model to benchmark (defaults to current)
            prompt: Test prompt (defaults to standard benchmark)
            
        Returns:
            Dictionary with benchmark results
        """
        model_name = model_name or self.model
        prompt = prompt or "Explain the importance of low latency in AI systems."
        
        start_time = time.time()
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False
                }
            )
            response.raise_for_status()
            
            end_time = time.time()
            duration = end_time - start_time
            
            result = response.json()
            tokens = result.get("eval_count", 0)
            throughput = tokens / duration if duration > 0 else 0
            
            return {
                "model": model_name,
                "response_time": duration,
                "tokens_generated": tokens,
                "tokens_per_second": throughput,
                "successful": True
            }
        except Exception as e:
            logger.error(f"Benchmark failed for {model_name}: {str(e)}")
            return {
                "model": model_name,
                "successful": False,
                "error": str(e)
            }

# Convenience functions for common operations
def create_client(model: str = "qwen:2.5") -> OllamaClient:
    """
    Create an OllamaClient instance with health checking.
    
    Args:
        model: Model name to use
        
    Returns:
        Configured OllamaClient instance
    """
    client = OllamaClient(model=model)
    return client

def get_available_models(client: OllamaClient = None) -> List[str]:
    """
    Get list of available models.
    
    Args:
        client: OllamaClient instance (creates default if None)
        
    Returns:
        List of model names
    """
    if client is None:
        client = create_client()
    return client.list_models()

def test_connection(base_url: str = "http://localhost:11434") -> bool:
    """
    Test if Ollama service is accessible.
    
    Args:
        base_url: Base URL for Ollama API
        
    Returns:
        True if service is accessible, False otherwise
    """
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False
