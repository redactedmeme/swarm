#!/usr/bin/env python3

"""
REDACTED Swarm - Ollama Runner
===============================
Main entry point for running the REDACTED AI Swarm using Ollama as the LLM provider.

Features:
- Loads agent definitions from .character.json files
- Provides interactive terminal interface
- Supports multiple agents and contexts
- Handles tool execution and function calling
- Maintains conversation history

Usage:
    python python/run_with_ollama.py
    python python/run_with_ollama.py --agent agents/default.character.json
    python python/run_with_ollama.py --model llama3.2
"""

import json
import os
import sys
import argparse
from typing import Optional, Dict, List, Any
import logging
from datetime import datetime

# Import Ollama client
from ollama_client import OllamaClient

# Import Ollama utilities for auto-detection
from utils.ollama_utils import get_running_ollama_model, DEFAULT_OLLAMA_MODEL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_AGENT_FILE = "agents/default.character.json"
DEFAULT_HISTORY_FILE = ".swarm_history.json"

class SwarmRunner:
    """
    Main runner for the REDACTED Swarm with Ollama integration.
    
    Manages:
    - Agent loading and configuration
    - Conversation history
    - Tool/function execution
    - User interaction loop
    """
    
    def __init__(
        self,
        agent_file: str = DEFAULT_AGENT_FILE,
        model: str = DEFAULT_OLLAMA_MODEL,
        load_history: bool = True,
        save_history: bool = True
    ):
        """
        Initialize the swarm runner.
        
        Args:
            agent_file: Path to the .character.json agent definition
            model: Ollama model to use
            load_history: Whether to load previous conversation history
            save_history: Whether to save conversation history
        """
        self.agent_file = agent_file
        self.model = model
        self.load_history = load_history
        self.save_history = save_history
        
        # Initialize Ollama client
        self.client = OllamaClient(model=self.model)
        
        # Load agent configuration
        self.agent_config = self._load_agent_config()
        
        # Initialize conversation history
        self.conversation_history = []
        if self.load_history:
            self._load_history()
        
        # Tool registry (for function calling)
        self.tool_registry = {}
        self._register_tools()
        
        logger.info(f"✓ Swarm initialized with agent: {self.agent_config.get('name', 'Unknown')}")
    
    def _load_agent_config(self) -> Dict[str, Any]:
        """
        Load agent configuration from .character.json file.
        
        Returns:
            Dictionary containing agent configuration
        """
        try:
            if not os.path.exists(self.agent_file):
                logger.warning(f"Agent file not found: {self.agent_file}")
                logger.info("Creating default agent configuration...")
                return self._create_default_agent()
            
            with open(self.agent_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"✓ Loaded agent: {config.get('name', 'Unnamed')}")
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in agent file: {str(e)}")
            return self._create_default_agent()
        except Exception as e:
            logger.error(f"Failed to load agent configuration: {str(e)}")
            return self._create_default_agent()
    
    def _create_default_agent(self) -> Dict[str, Any]:
        """
        Create a default agent configuration if none exists.
        
        Returns:
            Default agent configuration dictionary
        """
        default_config = {
            "name": "REDACTED Terminal",
            "model": self.model,
            "provider": "ollama",
            "system_prompt": """You are the REDACTED Terminal — an autonomous AI agent operating within the Pattern Blue framework.

NERV-inspired interface. Minimalist aesthetic. Maximum efficiency.

Capabilities:
- Analyze market conditions
- Execute autonomous operations
- Coordinate with other agents
- Maintain operational security

Guidelines:
- Be concise and direct
- Use technical terminology when appropriate
- Maintain professional demeanor
- Prioritize mission objectives

Current context: Interactive terminal session""",
            "tools": [],
            "temperature": 0.7,
            "max_tokens": 2048
        }
        
        # Create agents directory if it doesn't exist
        os.makedirs(os.path.dirname(self.agent_file), exist_ok=True)
        
        # Save default configuration
        with open(self.agent_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        
        logger.info(f"✓ Created default agent configuration at {self.agent_file}")
        return default_config
    
    def _register_tools(self):
        """
        Register available tools/functions for the agent.
        
        This is where you would define custom functions that the agent can call.
        Example tools might include:
        - File operations
        - Web requests
        - Data analysis
        - System commands
        """
        # Example tool registration (customize as needed)
        self.tool_registry = {
            # "get_weather": self._tool_get_weather,
            # "search_web": self._tool_search_web,
            # "read_file": self._tool_read_file,
        }
        
        # Register tools from agent config if available
        agent_tools = self.agent_config.get("tools", [])
        for tool in agent_tools:
            tool_name = tool.get("function", {}).get("name")
            if tool_name:
                logger.debug(f"Registered tool: {tool_name}")
    
    def _tool_get_weather(self, location: str) -> str:
        """Example tool: Get weather information."""
        return f"Weather tool called for {location} (implement actual API call)"
    
    def _load_history(self):
        """Load conversation history from file."""
        try:
            if os.path.exists(DEFAULT_HISTORY_FILE):
                with open(DEFAULT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.conversation_history = json.load(f)
                logger.info(f"✓ Loaded {len(self.conversation_history)} previous messages")
        except Exception as e:
            logger.warning(f"Could not load history: {str(e)}")
    
    def _save_history(self):
        """Save conversation history to file."""
        if not self.save_history:
            return
        
        try:
            with open(DEFAULT_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f, indent=2)
            logger.debug(f"✓ Saved conversation history ({len(self.conversation_history)} messages)")
        except Exception as e:
            logger.warning(f"Could not save history: {str(e)}")
    
    def _format_message_history(self) -> List[Dict[str, str]]:
        """
        Format conversation history for Ollama API.
        
        Returns:
            List of message dictionaries with role and content
        """
        messages = []
        
        # Add system prompt if not already in history
        system_prompt = self.agent_config.get("system_prompt", "")
        if system_prompt and (not self.conversation_history or self.conversation_history[0]["role"] != "system"):
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        messages.extend(self.conversation_history)
        
        return messages
    
    def process_tool_calls(self, response: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Process tool/function calls from the model response.
        
        Args:
            response: Ollama API response containing potential tool calls
            
        Returns:
            List of tool response messages if tools were called, None otherwise
        """
        try:
            # Check if response contains tool calls
            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])
            
            if not tool_calls:
                return None
            
            logger.info(f"🔧 Processing {len(tool_calls)} tool call(s)")
            
            # Process each tool call
            tool_responses = []
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                tool_name = function.get("name")
                arguments = json.loads(function.get("arguments", "{}"))
                
                if tool_name in self.tool_registry:
                    try:
                        # Execute the tool
                        tool_result = self.tool_registry[tool_name](**arguments)
                        
                        # Format tool response
                        tool_response = {
                            "role": "tool",
                            "name": tool_name,
                            "content": str(tool_result)
                        }
                        tool_responses.append(tool_response)
                        
                        logger.info(f"  ✓ Executed {tool_name}: {str(tool_result)[:100]}...")
                    except Exception as e:
                        logger.error(f"  ✗ Error executing {tool_name}: {str(e)}")
                        tool_responses.append({
                            "role": "tool",
                            "name": tool_name,
                            "content": f"Error: {str(e)}"
                        })
                else:
                    logger.warning(f"  ⚠ Unknown tool: {tool_name}")
                    tool_responses.append({
                        "role": "tool",
                        "name": tool_name,
                        "content": "Error: Tool not found"
                    })
            
            return tool_responses
            
        except Exception as e:
            logger.error(f"Error processing tool calls: {str(e)}")
            return None
    
    def run(self):
        """
        Start the interactive swarm session.
        
        This is the main loop that handles user input and agent responses.
        """
        # Display welcome message
        print("\n" + "="*60)
        print(f"  REDACTED SWARM - Ollama Edition")
        print(f"  Agent: {self.agent_config.get('name', 'Unknown')}")
        print(f"  Model: {self.model}")
        print(f"  Type 'exit', 'quit', or 'Ctrl+C' to terminate")
        print("="*60 + "\n")
        
        try:
            while True:
                # Get user input
                try:
                    user_input = input("REDACTED> ").strip()
                except KeyboardInterrupt:
                    print("\n\nSession terminated by user.")
                    break
                
                # Check for exit commands
                if user_input.lower() in ['exit', 'quit', 'bye', 'stop']:
                    print("\nTerminating session...")
                    break
                
                if not user_input:
                    continue
                
                # Add user message to history
                self.conversation_history.append({
                    "role": "user",
                    "content": user_input
                })
                
                # Get model options
                options = {
                    "temperature": self.agent_config.get("temperature", 0.7),
                    "top_p": self.agent_config.get("top_p", 0.9),
                    "num_predict": self.agent_config.get("max_tokens", 2048)
                }
                
                # Generate response
                try:
                    logger.info("Generating response...")
                    response = self.client.generate(
                        messages=self._format_message_history(),
                        tools=self.agent_config.get("tools", []),
                        options=options
                    )
                    
                    # Process tool calls if any
                    tool_responses = self.process_tool_calls(response)
                    
                    if tool_responses:
                        # Add tool responses to history and get final response
                        self.conversation_history.extend(tool_responses)
                        
                        # Get response to tool results
                        final_response = self.client.generate(
                            messages=self._format_message_history(),
                            options=options
                        )
                        assistant_message = final_response.get("message", {}).get("content", "")
                    else:
                        # No tool calls, use direct response
                        assistant_message = response.get("message", {}).get("content", "")
                    
                    # Add assistant response to history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_message
                    })
                    
                    # Display response
                    print(f"\n{assistant_message}\n")
                    
                    # Save history after each exchange
                    self._save_history()
                    
                except Exception as e:
                    logger.error(f"Error generating response: {str(e)}")
                    print(f"\n✗ Error: {str(e)}\n")
        
        except KeyboardInterrupt:
            print("\n\nSession terminated by user.")
        
        finally:
            # Cleanup
            self._save_history()
            print("\n" + "="*60)
            print("Session ended. History saved.")
            print("="*60 + "\n")

def parse_arguments():
    """
    Parse command-line arguments.
    
    Returns:
        argparse.Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="REDACTED Swarm - Run autonomous agents with Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python python/run_with_ollama.py
  python python/run_with_ollama.py --agent agents/trader.character.json
  python python/run_with_ollama.py --model llama3.2 --temperature 0.5
  python python/run_with_ollama.py --no-history
        """
    )
    
    parser.add_argument(
        "--agent",
        type=str,
        default=DEFAULT_AGENT_FILE,
        help=f"Path to agent configuration file (default: {DEFAULT_AGENT_FILE})"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_OLLAMA_MODEL})"
    )
    
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature (0.0 to 1.0)"
    )
    
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Don't load or save conversation history"
    )
    
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Ollama models and exit"
    )
    
    parser.add_argument(
        "--pull-model",
        type=str,
        help="Pull a model from Ollama library and exit"
    )
    
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Handle special commands
    if args.list_models:
        client = OllamaClient(model=args.model)
        models = client.list_models()
        print("\nAvailable Ollama Models:")
        print("-" * 40)
        for model in models:
            print(f"  • {model}")
        print()
        return
    
    if args.pull_model:
        client = OllamaClient(model=args.pull_model)
        success = client.pull_model(args.pull_model)
        if success:
            print(f"\n✓ Model {args.pull_model} pulled successfully\n")
        else:
            print(f"\n✗ Failed to pull model {args.pull_model}\n")
        return
    
    # AUTOMATIC MODEL DETECTION LOGIC
    # Only auto-detect if user didn't explicitly specify a model
    if args.model == DEFAULT_OLLAMA_MODEL and '--model' not in sys.argv:
        detected_model = get_running_ollama_model()
        if detected_model:
            args.model = detected_model
            logger.info(f"✓ Auto-detected running model: {args.model}")
        else:
            logger.warning(f"No running model detected, using fallback: {DEFAULT_OLLAMA_MODEL}")
    else:
        logger.info(f"Using specified model: {args.model}")
    
    # Create and run swarm
    runner = SwarmRunner(
        agent_file=args.agent,
        model=args.model,
        load_history=not args.no_history,
        save_history=not args.no_history
    )
    
    # Update temperature if specified
    if args.temperature != 0.7:
        runner.agent_config["temperature"] = args.temperature
        logger.info(f"Temperature set to: {args.temperature}")
    
    # Run the swarm
    runner.run()

if __name__ == "__main__":
    main()
