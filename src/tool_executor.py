#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 AGI Bot Research Group.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import json
import re
import argparse
import sys
import datetime
import platform
import subprocess
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path
import requests
import hashlib
from openai import OpenAI
from tools import Tools
from tools.print_system import print_system, print_manager, set_agent_id, print_current, streaming_context
from tools.debug_system import track_operation, finish_operation
from tools.cli_mcp_wrapper import get_cli_mcp_wrapper, initialize_cli_mcp_wrapper, safe_cleanup_cli_mcp_wrapper
from tools.mcp_client import get_mcp_client, initialize_mcp_client, safe_cleanup_mcp_client
from config_loader import get_api_key, get_api_base, get_model, get_max_tokens, get_streaming, get_language, get_truncation_length, get_web_content_truncation_length, get_summary_history, get_summary_max_length, get_summary_trigger_length, get_simplified_search_output, get_web_search_summary, get_multi_agent, get_tool_calling_format
import base64
import mimetypes
import threading

# Note: JSON parsing utilities now imported below with other utils

# Import get_info utilities
from utils.get_info import (
    get_ip_location_info,
    get_system_environment_info,
    get_workspace_info,
    format_file_size,
    get_file_language,
)

# Import cache efficiency utilities
from utils.cacheeff import (
    analyze_cache_potential,
    estimate_token_count,
)

# Import parse utilities
from utils.parse import (
    fix_json_escapes,
    smart_escape_quotes_in_json_values,
    rebuild_json_structure,
    fix_long_json_with_code,
    parse_python_params_manually,
    convert_parameter_value,
    generate_tools_prompt_from_json,
)

# Note: test_api_connection imported dynamically to avoid circular imports

# Check if the API base uses Anthropic format
def is_anthropic_api(api_base: str) -> bool:
    """Check if the API base URL uses Anthropic format"""
    return api_base.lower().endswith('/anthropic') if api_base else False


# Backward compatibility function (deprecated)
def is_claude_model(model: str) -> bool:
    """
    Deprecated: Check if the model name is a Claude model
    This function is kept for backward compatibility only.
    Use is_anthropic_api(api_base) instead to check API format.
    """
    return model.lower().startswith('claude')


def should_use_chat_based_tools(model: str) -> bool:
    """
    Determine if a model should use chat-based tool calling based on the configuration.
    
    Args:
        model: The model name
        
    Returns:
        Boolean indicating whether to use chat-based tool calling
    """
            # Load tool calling format configuration from config/config.txt
    # True = standard tool calling, False = chat-based tool calling
    tool_calling_format = get_tool_calling_format()
    
    # Return the inverse of tool_calling_format
    # use_chat_based_tools is the inverse of tool_calling_format
    return not tool_calling_format


# Dynamically import Anthropic
def get_anthropic_client():
    """Dynamically import and return Anthropic client class"""
    try:
        from anthropic import Anthropic
        return Anthropic
    except ImportError:
        print_current("❌ Anthropic library not installed, please run: pip install anthropic")
        raise ImportError("Anthropic library not installed")



class ToolExecutor:
    def __init__(self, api_key: Optional[str] = None, 
                 model: Optional[str] = None, 
                 api_base: Optional[str] = None, 
                 workspace_dir: Optional[str] = None,
                 debug_mode: bool = False,
                 logs_dir: str = "logs",
                 session_timestamp: Optional[str] = None,
                 streaming: Optional[bool] = None,
                 interactive_mode: bool = False,
                 MCP_config_file: Optional[str] = None,
                 prompts_folder: Optional[str] = None):
        """
        Initialize the ToolExecutor
        
        Args:
            api_key: API key for LLM service
            model: Model name to use
            api_base: Base URL for the API service
            workspace_dir: Directory for workspace files
            debug_mode: Whether to enable debug logging
            logs_dir: Directory for log files
            session_timestamp: Timestamp for this session (used for log organization)
            streaming: Whether to use streaming output (None to use config.txt)
            interactive_mode: Whether to enable interactive mode
            MCP_config_file: Custom MCP configuration file path (optional, defaults to 'config/mcp_servers.json')
            prompts_folder: Custom prompts folder path (optional, defaults to 'prompts')
        """
        # Load API key from config/config.txt if not provided
        if api_key is None:
            api_key = get_api_key()
            if api_key is None:
                raise ValueError("API key not found. Please provide api_key parameter or set it in config/config.txt")
        self.api_key = api_key
        
        # Load model from config/config.txt if not provided
        if model is None:
            model = get_model()
            if model is None:
                raise ValueError("Model not found. Please provide model parameter or set it in config/config.txt")
        self.model = model
        
        # Load API base from config/config.txt if not provided
        if api_base is None:
            api_base = get_api_base()
            if api_base is None:
                raise ValueError("API base URL not found. Please provide api_base parameter or set it in config/config.txt")
        
        # Load streaming configuration from config/config.txt if not provided
        if streaming is None:
            streaming = get_streaming()
        self.streaming = streaming
        
        # Load language configuration from config/config.txt
        self.language = get_language()
        
        # Load history summarization configuration from config/config.txt
        self.summary_history = get_summary_history()
        self.summary_max_length = get_summary_max_length()
        self.summary_trigger_length = get_summary_trigger_length()
        
        # Load simplified search output configuration from config/config.txt
        self.simplified_search_output = get_simplified_search_output()
        
        # Load multi-agent mode configuration from config/config.txt
        self.multi_agent = get_multi_agent()
        
        self.workspace_dir = workspace_dir or os.getcwd()
        self.debug_mode = debug_mode
        self.logs_dir = logs_dir
        self.session_timestamp = session_timestamp
        self.interactive_mode = interactive_mode
        
        # Store custom file paths
        self.MCP_config_file = MCP_config_file or "config/mcp_servers.json"
        self.prompts_folder = prompts_folder or "prompts"
        
        # Set api_base first
        self.api_base = api_base
        
        # Check if using Anthropic API based on api_base
        self.is_claude = is_anthropic_api(self.api_base)
        
        # Load tool calling format configuration from config/config.txt
        # True = standard tool calling, False = chat-based tool calling
        tool_calling_format = get_tool_calling_format()
        
        # Set use_chat_based_tools based on configuration
        # Note: use_chat_based_tools is the inverse of tool_calling_format
        self.use_chat_based_tools = not tool_calling_format
        
        # Print system is ready to use
        
        # Display tool calling method
        if self.use_chat_based_tools:
            print_system(f"🔧 Tool calling method: Chat-based (tools described in messages)")
        else:
            print_system(f"🔧 Tool calling method: Standard API tool calling")
        
        # History summarization cache
        self.history_summary_cache = {}
        self.last_summarized_history_length = 0
        
        # print_system(f"🤖 LLM Configuration:")  # Commented out to reduce terminal noise
        # print_system(f"   Model: {self.model}")  # Commented out to reduce terminal noise
        # print_system(f"   API Base: {self.api_base}")  # Commented out to reduce terminal noise
        # print_system(f"   API Key: {self.api_key[:20]}...{self.api_key[-10:]}")  # Commented out to reduce terminal noise
        # print_system(f"   Workspace: {self.workspace_dir}")  # Commented out to reduce terminal noise
        # print_system(f"   Language: {'中文' if self.language == 'zh' else 'English'} ({self.language})")  # Commented out to reduce terminal noise
        # print_system(f"   Streaming: {'✅ Enabled' if self.streaming else '❌ Disabled (Batch mode)'}")  # Commented out to reduce terminal noise
        # print_system(f"   Cache Optimization: ✅ Enabled (All rounds use combined prompts for maximum cache hits)")  # Commented out to reduce terminal noise
        # print_system(f"   History Summarization: {'✅ Enabled' if self.summary_history else '❌ Disabled'} (Trigger: {self.summary_trigger_length} chars, Max: {self.summary_max_length} chars)")  # Commented out to reduce terminal noise
        # print_system(f"   Simplified Search Output: {'✅ Enabled' if self.simplified_search_output else '❌ Disabled'} (Affects codebase_search and web_search terminal display)")  # Commented out to reduce terminal noise
        # if debug_mode:
        #     print_system(f"   Debug Mode: Enabled (Log directory: {logs_dir})")  # Commented out to reduce terminal noise
        
        # Set up LLM client
        self._setup_llm_client()
        
        # Initialize tools with LLM configuration for web search filtering
        from tools import Tools
        
        # Get the parent directory of workspace (typically the output directory)
        out_dir = os.path.dirname(self.workspace_dir) if self.workspace_dir else os.getcwd()
        
        # Store the project root directory for image path processing
        self.project_root_dir = out_dir
        
        self.tools = Tools(
            workspace_root=self.workspace_dir,
            llm_api_key=self.api_key,
            llm_model=self.model,
            llm_api_base=self.api_base,
            enable_llm_filtering=False,  # Disable LLM filtering by default for faster responses
            enable_summary=get_web_search_summary(),  # Load web search summary setting from config
            out_dir=out_dir
        )
        
        # Initialize long-term memory system
        try:
            from tools.long_term_memory import LongTermMemoryTools
            # 长期记忆现在存储在项目根目录，不再需要workspace_root参数
            # 配置文件会自动从项目根目录加载
            self.long_term_memory = LongTermMemoryTools(
                workspace_root=self.workspace_dir  # 仅用于兼容性，实际存储在项目根目录
            )
            #print_current("✅ Long-term memory system initialized successfully (global shared storage)")
        except ImportError as e:
            print_current(f"⚠️ 长期记忆模块导入失败: {e}")
            self.long_term_memory = None
        except Exception as e:
            print_current(f"⚠️ 长期记忆系统初始化失败: {e}")
            self.long_term_memory = None
        
        # Initialize history optimizer for image data optimization
        try:
            from tools.history_optimizer import HistoryOptimizer
            self.history_optimizer = HistoryOptimizer(workspace_root=self.workspace_dir)
            # print_current("✅ History optimizer initialized for image data optimization")
        except ImportError as e:
            print_current(f"⚠️ Failed to import HistoryOptimizer: {e}")
            self.history_optimizer = None
        
        # Initialize multi-agent tools directly if enabled
        if self.multi_agent:
            from tools.multiagents import MultiAgentTools
            # 🔧 修复：传递debug_mode参数给MultiAgentTools
            self.multi_agent_tools = MultiAgentTools(self.workspace_dir, debug_mode=self.debug_mode)
        else:
            self.multi_agent_tools = None
        
        # Store current round's image data for next round vision API
        self.current_round_images = []
        
        # Store previous messages for cache analysis
        self.previous_messages = []
        
        # Initialize summary generator for conversation history summarization
        if self.summary_history:
            try:
                from multi_round_executor.summary_generator import SummaryGenerator
                self.conversation_summarizer = SummaryGenerator(self, detailed_summary=True)
                # print_current(f"✅ Conversation history summarizer initialized")
            except ImportError as e:
                print_system(f"⚠️ Failed to import SummaryGenerator: {e}, history summarization disabled")
                self.conversation_summarizer = None
                self.summary_history = False  # Disable summarization if import fails
        else:
            self.conversation_summarizer = None
        
        # Helper function for disabled multi-agent tools
        def _multi_agent_disabled_error(*args, **kwargs):
            return {"status": "error", "message": "Multi-agent functionality is disabled. Enable it in config/config.txt by setting multi_agent=True"}
        
        # Map of tool names to their implementation methods
        self.tool_map = {
            "codebase_search": self.tools.codebase_search,
            "read_file": self.tools.read_file,
            "run_terminal_cmd": self.tools.run_terminal_cmd,
            "list_dir": self.tools.list_dir,
            "grep_search": self.tools.grep_search,
            "edit_file": self.tools.edit_file,
            "file_search": self.tools.file_search,
            "web_search": self.tools.web_search,
            "search_img": self.tools.search_img,  # Add image search tool
            "tool_help": self.enhanced_tool_help,  # Use enhanced version that supports MCP tools
            "fetch_webpage_content": self.tools.fetch_webpage_content,
            "get_background_update_status": self.tools.get_background_update_status,
            "talk_to_user": self.tools.talk_to_user,
            "idle": self.tools.idle,
            "get_sensor_data": self.tools.get_sensor_data,
            "todo_update": self.tools.todo_update,  # Add todo task status update tool
        }
        
        # Add long-term memory tools if available
        if self.long_term_memory:
            self.tool_map.update({
                "recall_memories": self.long_term_memory.recall_memories,
                "recall_memories_by_time": self.long_term_memory.recall_memories_by_time,
                "get_memory_summary": self.long_term_memory.get_memory_summary,
            })
            print_current("🧠 Long-term memory tools registered")
        else:
            # Add error handlers for disabled memory tools
            def _memory_disabled_error(*args, **kwargs):
                return {"status": "error", "message": "长期记忆功能未启用或初始化失败"}
            
            self.tool_map.update({
                "recall_memories": _memory_disabled_error,
                "recall_memories_by_time": _memory_disabled_error,
                "get_memory_summary": _memory_disabled_error,
            })
        
        # Add multi-agent tools if enabled, otherwise add error handlers
        if self.multi_agent_tools:
            self.tool_map.update({
                "spawn_agibot": self.multi_agent_tools.spawn_agibot,
                "send_message_to_agent_or_manager": self.multi_agent_tools.send_message_to_agent_or_manager,
                "get_agent_messages": self.multi_agent_tools.get_agent_messages,
                "send_status_update_to_manager": self.multi_agent_tools.send_status_update_to_manager,
                "broadcast_message_to_agents": self.multi_agent_tools.broadcast_message_to_agents,
                "get_agent_session_info": self.multi_agent_tools.get_agent_session_info,
                "terminate_agibot": self.multi_agent_tools.terminate_agibot
            })
        else:
            # Add error handlers for disabled multi-agent tools
            self.tool_map.update({
                "spawn_agibot": _multi_agent_disabled_error,
                "send_message_to_agent_or_manager": _multi_agent_disabled_error,
                "get_agent_messages": _multi_agent_disabled_error,
                "send_status_update_to_manager": _multi_agent_disabled_error,
                "broadcast_message_to_agents": _multi_agent_disabled_error,
                "get_agent_session_info": _multi_agent_disabled_error,
                "terminate_agibot": _multi_agent_disabled_error,
            })
        
        # Add plugin tools if available
        if hasattr(self.tools, 'kb_search'):
            self.tool_map.update({
                "kb_search": self.tools.kb_search,
                "kb_content": self.tools.kb_content,
                "kb_body": self.tools.kb_body
            })
            # print_current("🔌 Plugin tools registered: kb_search, kb_content, kb_body")
        
        # Initialize MCP clients - support both cli-mcp and direct MCP implementation
        self.cli_mcp_client = get_cli_mcp_wrapper(self.MCP_config_file)
        # Create direct MCP client with specific config file instead of using global singleton
        from tools.mcp_client import MCPClient
        self.direct_mcp_client = MCPClient(self.MCP_config_file if self.MCP_config_file else "config/mcp_servers.json")
        self.cli_mcp_initialized = False
        self.direct_mcp_initialized = False
        
        # Try to initialize both MCP clients synchronously if possible
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, use thread pool for initialization
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Initialize cli-mcp client
                    try:
                        future_cli = executor.submit(asyncio.run, initialize_cli_mcp_wrapper(self.MCP_config_file))
                        self.cli_mcp_initialized = future_cli.result(timeout=10)
                        if self.cli_mcp_initialized:
                            print_current(f"✅ cli-mcp client initialized during startup with config: {self.MCP_config_file}")
                    except Exception as e:
                        print_current(f"⚠️ cli-mcp client startup initialization failed: {e}")
                        self.cli_mcp_initialized = False
                    
                    # Initialize direct MCP client
                    try:
                        future_direct = executor.submit(asyncio.run, self.direct_mcp_client.initialize())
                        self.direct_mcp_initialized = future_direct.result(timeout=10)
                        if self.direct_mcp_initialized:
                            print_current(f"✅ SSE MCP client initialized during startup with config: {self.MCP_config_file}")
                    except Exception as e:
                        print_current(f"⚠️ SSE MCP client startup initialization failed: {e}")
                        self.direct_mcp_initialized = False
            else:
                # Safe to run async initialization directly
                try:
                    self.cli_mcp_initialized = asyncio.run(initialize_cli_mcp_wrapper(self.MCP_config_file))
                    if self.cli_mcp_initialized:
                        print_current(f"✅ cli-mcp client initialized during startup with config: {self.MCP_config_file}")
                except Exception as e:
                    print_current(f"⚠️ cli-mcp client startup initialization failed: {e}")
                    self.cli_mcp_initialized = False
                
                try:
                    self.direct_mcp_initialized = asyncio.run(self.direct_mcp_client.initialize())
                    if self.direct_mcp_initialized:
                        print_current(f"✅ SSE MCP client initialized during startup with config: {self.MCP_config_file}")
                except Exception as e:
                    print_current(f"⚠️ SSE MCP client startup initialization failed: {e}")
                    self.direct_mcp_initialized = False
        except RuntimeError:
            # No event loop, safe to create one
            try:
                self.cli_mcp_initialized = asyncio.run(initialize_cli_mcp_wrapper(self.MCP_config_file))
                if self.cli_mcp_initialized:
                    print_current(f"✅ cli-mcp client initialized during startup with config: {self.MCP_config_file}")
            except Exception as e:
                print_current(f"⚠️ cli-mcp client startup initialization failed: {e}")
                self.cli_mcp_initialized = False
            
            try:
                self.direct_mcp_initialized = asyncio.run(self.direct_mcp_client.initialize())
                if self.direct_mcp_initialized:
                    print_current(f"✅ SSE MCP client initialized during startup with config: {self.MCP_config_file}")
            except Exception as e:
                print_current(f"⚠️ SSE MCP client startup initialization failed: {e}")
                self.direct_mcp_initialized = False
        
        # Add MCP tools to tool_map after successful initialization
        if self.cli_mcp_initialized or self.direct_mcp_initialized:
            self._add_mcp_tools_to_map()
            #print_current(f"🔧 MCP tools loaded successfully during startup")
        
        # Log related settings
        # Simplified logs directory path construction - always use simple "logs" structure
        if workspace_dir:
            # Get the parent directory of workspace (typically the output directory)
            parent_dir = os.path.dirname(workspace_dir) if workspace_dir else os.getcwd()
            self.logs_dir = os.path.join(parent_dir, "logs")  # Simplified: directly use "logs"
        else:
            self.logs_dir = os.path.join(os.getcwd(), "logs")  # Simplified: directly use "logs"
        
        self.llm_logs_dir = self.logs_dir  # LLM call logs directory
        self.llm_call_counter = 0  # LLM call counter
        
        # Ensure log directory exists
        os.makedirs(self.llm_logs_dir, exist_ok=True)
        
        # If DEBUG mode is enabled, initialize CSV logger
        if self.debug_mode:
            # print_current(f"🐛 DEBUG mode enabled, LLM call records will be saved to: {self.llm_logs_dir}/llmcall.csv")
            pass
    
    async def _initialize_mcp_async(self):
        """Initialize both MCP clients asynchronously"""
        try:
            # Initialize cli-mcp wrapper
            if not self.cli_mcp_initialized:
                self.cli_mcp_initialized = await initialize_cli_mcp_wrapper(self.MCP_config_file)
                if self.cli_mcp_initialized:
                    print_current("✅ cli-mcp client initialized successfully")
                else:
                    print_current("⚠️ cli-mcp client initialization failed")
            
            # Initialize direct MCP client
            if not self.direct_mcp_initialized:
                self.direct_mcp_initialized = await self.direct_mcp_client.initialize()
                if self.direct_mcp_initialized:
                    print_current("✅ Direct MCP client initialized successfully")
                else:
                    print_current("⚠️ Direct MCP client initialization failed")
            
            # Add MCP tools to tool_map after initialization
            if self.cli_mcp_initialized or self.direct_mcp_initialized:
                self._add_mcp_tools_to_map()
                
        except Exception as e:
            print_current(f"⚠️ MCP client async initialization failed: {e}")
    
    def _add_mcp_tools_to_map(self):
        """Add MCP tools to the tool mapping"""
        # Create tool source mapping table
        if not hasattr(self, 'tool_source_map'):
            self.tool_source_map = {}
        
        # Add cli-mcp tools (NPX/NPM format) - NO prefix
        if self.cli_mcp_initialized and self.cli_mcp_client:
            try:
                # Get available MCP tools from cli-mcp wrapper
                cli_mcp_tools = self.cli_mcp_client.get_available_tools()
                
                if cli_mcp_tools:
                    for tool_name in cli_mcp_tools:
                        # Create a wrapper function for each cli-mcp tool
                        def create_cli_mcp_tool_wrapper(tool_name=tool_name):
                            def sync_cli_mcp_tool_wrapper(**kwargs):
                                import asyncio
                                try:
                                    # Call the cli-mcp wrapper
                                    return asyncio.run(self.cli_mcp_client.call_tool(tool_name, kwargs))
                                except Exception as e:
                                    return {"error": f"cli-mcp tool {tool_name} call failed: {e}"}
                            
                            return sync_cli_mcp_tool_wrapper
                        
                        # Add to tool mapping WITHOUT prefix
                        self.tool_map[tool_name] = create_cli_mcp_tool_wrapper()
                        self.tool_source_map[tool_name] = 'cli_mcp'
                    
                    print_current(f"✅ Added {len(cli_mcp_tools)} cli-mcp tools to mapping: {', '.join(cli_mcp_tools)}")
            except Exception as e:
                print_current(f"⚠️ Failed to add cli-mcp tools to mapping: {e}")
                self.cli_mcp_initialized = False
        
        # Add direct MCP client tools (SSE format) - NO prefix for SSE tools
        if self.direct_mcp_initialized and self.direct_mcp_client:
            try:
                # Get available MCP tools from direct MCP client
                direct_mcp_tools = self.direct_mcp_client.get_available_tools()
                
                if direct_mcp_tools:
                    for tool_name in direct_mcp_tools:
                        # Create a wrapper function for each direct MCP tool
                        def create_direct_mcp_tool_wrapper(tool_name=tool_name):
                            def sync_direct_mcp_tool_wrapper(**kwargs):
                                import asyncio
                                try:
                                    # Call the direct MCP client
                                    return asyncio.run(self.direct_mcp_client.call_tool(tool_name, kwargs))
                                except Exception as e:
                                    return {"error": f"Direct MCP tool {tool_name} call failed: {e}"}
                            
                            return sync_direct_mcp_tool_wrapper
                        
                        # Add to tool mapping WITHOUT prefix for SSE tools
                        self.tool_map[tool_name] = create_direct_mcp_tool_wrapper()
                        self.tool_source_map[tool_name] = 'direct_mcp'
                    
                    print_current(f"✅ Added {len(direct_mcp_tools)} SSE MCP tools to mapping: {', '.join(direct_mcp_tools)}")
            except Exception as e:
                print_current(f"⚠️ Failed to add direct MCP tools to mapping: {e}")
                self.direct_mcp_initialized = False
    
    def cleanup(self):
        """Clean up all resources and threads"""
        try:
            
            # Cleanup cli-mcp client
            if hasattr(self, 'cli_mcp_client') and self.cli_mcp_client:
                try:
                    safe_cleanup_cli_mcp_wrapper()
                    # print_current("🔌 cli-mcp client cleanup completed")
                except Exception as e:
                    print_current(f"⚠️ cli-mcp client cleanup failed: {e}")
            
            # Cleanup direct MCP client
            if hasattr(self, 'direct_mcp_client') and self.direct_mcp_client:
                try:
                    safe_cleanup_mcp_client()
                    # print_current("🔌 Direct MCP client cleanup completed")
                except Exception as e:
                    print_current(f"⚠️ Direct MCP client cleanup failed: {e}")
            
            # Cleanup long-term memory
            if hasattr(self, 'long_term_memory') and self.long_term_memory:
                try:
                    self.long_term_memory.cleanup()
                    # print_current("🧠 Long-term memory cleanup completed")
                except Exception as e:
                    print_current(f"⚠️ Long-term memory cleanup failed: {e}")
            
            # Cleanup tools
            if hasattr(self, 'tools') and self.tools:
                try:
                    self.tools.cleanup()
                except Exception as e:
                    print_current(f"⚠️ Tools cleanup failed: {e}")
            
            # Close LLM client connections if needed
            if hasattr(self, 'client'):
                try:
                    if hasattr(self.client, 'close'):
                        self.client.close()
                except:
                    pass
            
            # print_system(f"✅ ToolExecutor cleanup completed")
            
        except Exception as e:
            print_system(f"⚠️ Error during ToolExecutor cleanup: {e}")
    
    def _store_task_completion_memory(self, task_prompt: str, task_result: str, metadata: Dict[str, Any] = None):
        """
        Store task completion in long-term memory
        
        Args:
            task_prompt: The original task prompt
            task_result: The task execution result
            metadata: Additional metadata about the execution
        """
        try:
            if not hasattr(self, 'long_term_memory') or not self.long_term_memory:
                # Long-term memory not available, skip silently
                return
            
            # Store the memory
            result = self.long_term_memory.memory_manager.store_task_memory(
                task_prompt=task_prompt,
                task_result=task_result,
                execution_metadata=metadata
            )
            
            if result.get("success", False):
                action = result.get("action", "stored")
                memory_id = result.get("memory_id", "unknown")
                # Only print for new memories, not updates
                if action == "added":
                    print_current(f"🧠 任务记忆已存储 (ID: {memory_id})")
                elif action == "updated":
                    print_current(f"🧠 任务记忆已更新 (ID: {memory_id})")
            else:
                # Only print errors in debug mode to avoid cluttering output
                if self.debug_mode:
                    print_current(f"⚠️ 任务记忆存储失败: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            # Only print errors in debug mode
            if self.debug_mode:
                print_current(f"⚠️ 存储任务记忆时发生异常: {e}")
    
    def _setup_llm_client(self):
        """
        Set up the LLM client based on the API base URL.
        """
        if self.is_claude:
            # print_current(f"🧠 Detected Anthropic API, using Anthropic protocol")
            # print_current(f" Anthropic API Base: {self.api_base}")
            
            # Initialize Anthropic client
            Anthropic = get_anthropic_client()
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=self.api_base
            )
        else:
            # print_current(f"🤖 Using OpenAI protocol")
            # Initialize OpenAI client
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
    
    def _get_max_tokens_for_model(self, model: str) -> int:
        """
        Get the appropriate max_tokens for the given model.
        First tries to read from config.txt, then falls back to model defaults.
        
        Args:
            model: Model name
            
        Returns:
            Max tokens for the model
        """
        # First try to get max_tokens from configuration file
        config_max_tokens = get_max_tokens()
        if config_max_tokens is not None:
            # print_current(f"🔧 Using max_tokens from config: {config_max_tokens}")
            return config_max_tokens
        
        # Fallback to model-specific defaults
        model_limits = {
            # Claude models
            'claude-3-haiku-20240307': 4096,
            'claude-3-5-haiku-20241022': 8192,
            'claude-3-sonnet-20240229': 4096,
            'claude-3-5-sonnet-20240620': 8192,
            'claude-3-5-sonnet-20241022': 8192,
            'claude-3-opus-20240229': 4096,
            'claude-3-7-sonnet-latest': 8192,
            # OpenAI models (generally have higher limits)
            'gpt-4': 8192,
            'gpt-4o': 16384,
            'gpt-4o-mini': 16384,
            'gpt-3.5-turbo': 4096,
            # Qwen models (SiliconFlow)
            'Qwen/Qwen2.5-7B-Instruct': 8192,
            'Qwen/Qwen3-32B': 8192,
            'Qwen/Qwen3-30B-A3B': 8192,
        }
        
        # Get model-specific limit or default to 8192 for unknown models
        max_tokens = model_limits.get(model, 8192)
        
        # Extra safety check for Claude models
        if 'claude' in model.lower() and 'haiku' in model.lower():
            max_tokens = min(max_tokens, 4096)
        elif 'claude' in model.lower():
            max_tokens = min(max_tokens, 8192)
        
        print_current(f"🔧 Using default max_tokens for model {model}: {max_tokens}")
        return max_tokens
    

    
    def load_system_prompt(self, prompt_file: str = "prompts.txt") -> str:
        """
        Load only the core system prompt (system_prompt.txt).
        Other prompt files are loaded separately for user message construction.
        
        Args:
            prompt_file: Path to the prompt file (legacy support)
            
        Returns:
            The core system prompt text from system_prompt.txt
        """
        try:
            # Try to load system_prompt.txt first from custom prompts folder
            system_prompt_file = os.path.join(self.prompts_folder, "system_prompt.txt")
            
            if os.path.exists(system_prompt_file):
                with open(system_prompt_file, 'r', encoding='utf-8') as f:
                    system_prompt = f.read().strip()
                return system_prompt
            else:
                # Fall back to single file approach
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    system_prompt = f.read()
                return system_prompt
                
        except Exception as e:
            print_current(f"Error loading system prompt: {e}")
            return "You are a helpful AI assistant that can use tools to accomplish tasks."
    
    def load_user_prompt_components(self) -> Dict[str, str]:
        """
        Load all prompt components that go into the user message.
        
        Returns:
            Dictionary containing different prompt components
        """
        components = {
            'rules_and_tools': '',
            'system_environment': '',
            'workspace_info': '',
        }
        
        try:
            # For chat-based tools, generate tool descriptions from JSON instead of loading files
            if self.use_chat_based_tools:
                # Generate tools prompt from JSON definitions
                tool_definitions = self._load_tool_definitions_from_file()
                json_tools_prompt = generate_tools_prompt_from_json(tool_definitions, self.language)
                
                # Load only rules and plugin prompts (excluding deprecated tool files)
                rules_tool_files = [
                    os.path.join(self.prompts_folder, "rules_prompt.txt"), 
                    os.path.join(self.prompts_folder, "plugin_tool_prompts.txt"),
                    os.path.join(self.prompts_folder, "user_rules.txt")
                ]
                
                rules_parts = []
                if json_tools_prompt:
                    rules_parts.append(json_tools_prompt)
                
                loaded_files = []
                
                for file_path in rules_tool_files:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read().strip()
                                if content:
                                    rules_parts.append(content)
                                    loaded_files.append(file_path)
                        except Exception as e:
                            print_current(f"Warning: Could not load file {file_path}: {e}")
                
                if rules_parts:
                    components['rules_and_tools'] = "\n\n".join(rules_parts)
                
                # Log the approach used
                if json_tools_prompt:
                    print_current("✅ Using JSON-generated tool descriptions for chat-based model")
                else:
                    print_current("⚠️  Failed to generate JSON tool descriptions, falling back to file-based approach")
                    
            else:
                # For standard tool calling, load only rules (no tool descriptions needed)
                rules_tool_files = [
                    os.path.join(self.prompts_folder, "rules_prompt.txt"), 
                    os.path.join(self.prompts_folder, "plugin_tool_prompts.txt"),
                    os.path.join(self.prompts_folder, "user_rules.txt")
                ]
                
                rules_parts = []
                loaded_files = []
                
                for file_path in rules_tool_files:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read().strip()
                                if content:
                                    rules_parts.append(content)
                                    loaded_files.append(file_path)
                        except Exception as e:
                            print_current(f"Warning: Could not load file {file_path}: {e}")
                
                if rules_parts:
                    components['rules_and_tools'] = "\n\n".join(rules_parts)
                
                print_current("✅ Using standard tool calling (tool descriptions provided via API)")
                
            # Note: Removed loading of deprecated files:
            # - prompts/tool_prompt.txt
            # - prompts/tool_prompt_for_chat.txt  
            # - prompts/multiagent_prompt.txt
            # These are now replaced by JSON-generated tool descriptions
            
            # Load system environment information
            components['system_environment'] = get_system_environment_info(
                language=self.language, 
                model=self.model, 
                api_base=self.api_base
            )
            
            # Load workspace information
            components['workspace_info'] = get_workspace_info(self.workspace_dir)
            
        except Exception as e:
            print_current(f"Warning: Error loading user prompt components: {e}")
        
        return components
    
    
    def _add_full_history_to_message(self, message_parts: List[str], task_history: List[Dict[str, Any]]) -> None:
        """
        Add full task history to message parts with standardized formatting for better cache hits.
        
        Args:
            message_parts: List to append history content to
            task_history: Previous task execution history
        """
        message_parts.append("## Previous Round Context:")
        message_parts.append("Below is the context from previous tasks in this session:")
        message_parts.append("")
        
        for i, record in enumerate(task_history, 1):
            if record.get("role") == "system":
                continue
            elif "prompt" in record and "result" in record:
                # Add clear separator line for each round
                message_parts.append(f"### Previous round {i}:")
                message_parts.append("")
                
                # Format user request with consistent line breaks
                user_request = record['prompt'].strip()
                message_parts.append(f"**User Request:**")
                message_parts.append(user_request)
                message_parts.append("")
                
                # Format assistant response with consistent line breaks and standardized tool result formatting
                assistant_response = record['result'].strip()
                
                # Check if response contains tool calls and/or execution results
                tool_calls_section = ""
                tool_results_section = ""
                main_content = assistant_response
                
                # Extract tool calls section if present
                if "--- Tool Calls ---" in assistant_response:
                    parts = assistant_response.split("--- Tool Calls ---", 1)
                    main_content = parts[0].strip()
                    remaining_content = parts[1] if len(parts) > 1 else ""
                    
                    # Check if there are also tool execution results after tool calls
                    if "--- Tool Execution Results ---" in remaining_content:
                        tool_parts = remaining_content.split("--- Tool Execution Results ---", 1)
                        tool_calls_section = tool_parts[0].strip()
                        tool_results_section = tool_parts[1].strip() if len(tool_parts) > 1 else ""
                    else:
                        tool_calls_section = remaining_content.strip()
                
                # If no tool calls section but has tool execution results
                elif "--- Tool Execution Results ---" in assistant_response:
                    parts = assistant_response.split("--- Tool Execution Results ---", 1)
                    main_content = parts[0].strip()
                    tool_results_section = parts[1].strip() if len(parts) > 1 else ""
                    
                # Display the main assistant response
                message_parts.append(f"**Assistant Response:**")
                message_parts.append(main_content)
                message_parts.append("")
                
                # Display tool calls if present
                if tool_calls_section:
                    message_parts.append("**Tool Calls:**")
                    message_parts.append(tool_calls_section)
                    message_parts.append("")
                
                # Display tool execution results if present
                if tool_results_section:
                    message_parts.append("**Tool Execution Results:**")
                    # Standardize tool results format for better cache consistency
                    tool_results_section = self._standardize_tool_results_format(tool_results_section)
                    message_parts.append(tool_results_section)
                    message_parts.append("")
                
                message_parts.append("")  # Extra space after separator
    
    def _standardize_tool_results_format(self, tool_results: str) -> str:
        """
        Standardize tool results format for better cache consistency.
        
        Args:
            tool_results: Raw tool results string
            
        Returns:
            Standardized tool results string
        """
        lines = tool_results.split('\n')
        standardized_lines = []
        
        for line in lines:
            # Remove trailing whitespace from each line
            line = line.rstrip()
            
            # Skip empty lines at the beginning
            if not standardized_lines and not line:
                continue
                
            # Standardize tool execution markers
            if line.startswith('<tool_execute'):
                # Extract tool name and number, standardize format
                import re
                match = re.search(r'tool_name="([^"]+)".*tool_number="(\d+)"', line)
                if match:
                    tool_name, tool_number = match.groups()
                    standardized_lines.append(f'<tool_execute tool_name="{tool_name}" tool_number="{tool_number}">')
                else:
                    standardized_lines.append(line)
            elif line.startswith('</tool_execute>'):
                standardized_lines.append('</tool_execute>')
            elif line.startswith('Executing tool:'):
                # Standardize executing tool message format
                parts = line.split(' with params: ')
                if len(parts) == 2:
                    tool_info = parts[0].replace('Executing tool: ', '')
                    params_info = parts[1]
                    standardized_lines.append(f'Executing tool: {tool_info} with params: {params_info}')
                else:
                    standardized_lines.append(line)
            else:
                standardized_lines.append(line)
        
        # Join lines and ensure consistent line ending
        result = '\n'.join(standardized_lines)
        
        # Remove trailing newlines and add a single one
        result = result.rstrip() + '\n' if result.strip() else ''
        
        return result
    

    
    def _get_recent_history_subset(self, task_history: List[Dict[str, Any]], max_length: int) -> List[Dict[str, Any]]:
        """
        Get a subset of recent history that doesn't exceed the maximum length.
        
        Args:
            task_history: Full task history
            max_length: Maximum allowed character length
            
        Returns:
            Subset of recent history records
        """
        if not task_history:
            return []
        
        # Start from the most recent records and work backwards
        recent_history = []
        current_length = 0
        
        for record in reversed(task_history):
            # Calculate the length of this record
            record_length = len(str(record.get("content", ""))) + len(str(record.get("result", ""))) + len(str(record.get("prompt", "")))
            
            # Check if adding this record would exceed the limit
            if current_length + record_length > max_length and recent_history:
                break
            
            recent_history.insert(0, record)
            current_length += record_length
        
        return recent_history

    def _compute_history_hash(self, task_history: List[Dict[str, Any]]) -> str:
        """
        Compute a hash for the task history to enable caching.
        
        Args:
            task_history: Task history to hash
            
        Returns:
            Hash string for the history
        """
        import hashlib
        
        # Create a string representation of the history
        history_str = ""
        for record in task_history:
            history_str += str(record.get("prompt", "")) + str(record.get("result", "")) + str(record.get("content", ""))
        
        # Create SHA256 hash
        return hashlib.sha256(history_str.encode('utf-8')).hexdigest()

    def get_history_summary_cache_info(self) -> Dict[str, Any]:
        """
        Get information about the history summary cache.
        
        Returns:
            Dictionary containing cache information
        """
        cache_size = len(self.history_summary_cache) if hasattr(self, 'history_summary_cache') else 0
        last_length = getattr(self, 'last_summarized_history_length', 0)
        
        return {
            'cache_size': cache_size,
            'last_summarized_length': last_length,
            'cache_keys': list(self.history_summary_cache.keys()) if hasattr(self, 'history_summary_cache') else []
        }

    def clear_history_summary_cache(self) -> None:
        """
        Clear the history summary cache.
        """
        if hasattr(self, 'history_summary_cache'):
            self.history_summary_cache.clear()
        if hasattr(self, 'last_summarized_history_length'):
            self.last_summarized_history_length = 0

    def execute_subtask(self, prompt: str, prompts_file: str = "", 
                       task_history: Optional[List[Dict[str, Any]]] = None, 
                       execution_round: int = 1) -> Union[str, Tuple[str, List[Dict[str, Any]]]]:
        """
        Execute a subtask with potential multiple rounds (if tools need to be called)
        
        Args:
            prompt: User prompt
            prompts_file: Prompt file to load (currently not used, loads default system prompt)
            task_history: Historical messages from previous rounds (to maintain conversation context)
            execution_round: Current execution round number
            
        Returns:
            Execution result (str) or tuple (result, optimized_task_history) if history was optimized
        """
        track_operation(f"executing task (prompt length: {len(prompt)})")
        
        # Initialize task history if not provided
        if task_history is None:
            task_history = []
        
        original_history_id = id(task_history)  # Track if we modify the history
        history_was_optimized = False
        
        max_rounds = 10  # Maximum number of rounds to prevent infinite loops
        round_counter = 1
        
        # 🔧 Initialize current_round_images if not exists
        if not hasattr(self, 'current_round_images'):
            self.current_round_images = []
        
        # �� NEW: Track if get_sensor_data was called in current round
        current_round_has_sensor_data = False
        
        while round_counter <= max_rounds:
            try:
                # Enhancement: Check for terminate messages before each tool call in every round
                terminate_signal = self._check_terminate_messages()
                if terminate_signal:
                    return terminate_signal
                
                # Load system prompt (only core system_prompt.txt content)
                system_prompt = self.load_system_prompt()
                
                # Build user message with new architecture
                user_message = self._build_new_user_message(prompt, task_history, round_counter)
                
                # Prepare messages for the LLM with proper system/user separation
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
                
                # Save debug log for this call's input (before LLM call)
                if self.debug_mode:
                    try:
                        initial_call_info = {
                            "is_single_call": True,
                            "call_type": "standard_tools_execution",
                            "user_prompt": prompt
                        }
                    except Exception as e:
                        print_current(f"⚠️ Debug preparation failed: {e}")
                
                # Execute LLM call with standard tools
                content, tool_calls = self._call_llm_with_standard_tools(messages, user_message, system_prompt)
                
                # 🔧 DEBUG: Check current_round_images status
                #print_current(f"🔍 DEBUG: After LLM call, current_round_images status: {len(self.current_round_images) if self.current_round_images else 0} images")
                
                # After vision analysis is complete, immediately optimize the history to remove any analyzed base64 image data
                print_current(f"🔍 Checking optimization conditions: task_history={len(task_history) if task_history else 0}, history_optimizer={hasattr(self, 'history_optimizer') and self.history_optimizer is not None}")
                if task_history and hasattr(self, 'history_optimizer') and self.history_optimizer:
                    try:
                        # Immediately optimize the history, removing all image data (keep_recent_images=0)
                        # Since the vision API has already provided a text description, the original image data is no longer needed
                        #print_current(f"🔍 Starting optimization with {len(task_history)} history records...")
                        optimized_history = self.history_optimizer.optimize_history_for_context(
                            task_history, keep_recent_images=0
                        )
                        # Update the history reference to ensure subsequent rounds use the optimized history
                        original_count = len(task_history)
                        task_history.clear()
                        task_history.extend(optimized_history)
                        history_was_optimized = True
                        #print_current(f"✅ History optimization complete: {original_count} → {len(optimized_history)} records")
                    except Exception as e:
                        print_current(f"❌ History optimization failed: {e}")
                else:
                    print_current("⚠️ Skipping history optimization - conditions not met")
                # Show raw model response for debugging
                if self.debug_mode and content:
                    print_current("🤖 Raw model response:")
                    print_current(content)
                
                # Calculate and display token and character statistics
                self._display_llm_statistics(messages, content, tool_calls)
                
                # Store current messages for next round cache analysis
                self.previous_messages = messages.copy()
                
                # Check for TASK_COMPLETED flag and detect conflicts
                has_task_completed = "TASK_COMPLETED:" in content
                has_tool_calls = len(tool_calls) > 0
                
                # Check for TASK_COMPLETED flag and detect conflicts
                has_task_completed = "TASK_COMPLETED:" in content
                has_tool_calls = len(tool_calls) > 0
                
                # CONFLICT DETECTION: Both tool calls and TASK_COMPLETED present
                conflict_detected = has_tool_calls and has_task_completed
                if conflict_detected:
                    print_current(f"⚠️ CONFLICT DETECTED: Both tool calls and TASK_COMPLETED flag found, removing TASK_COMPLETED flag")
                    # Remove the TASK_COMPLETED flag from the content to ensure tool execution proceeds
                    content = re.sub(r'TASK_COMPLETED:.*', '', content).strip()
                    has_task_completed = False # Ensure the flag is updated after removal
                
                # If TASK_COMPLETED but no tool calls, complete the task
                if has_task_completed and not has_tool_calls:
                    print_current(f"🎉 TASK_COMPLETED flag detected in content, task completed!")
                    # Extract the completion message
                    task_completed_match = re.search(r'TASK_COMPLETED:\s*(.+)', content)
                    if task_completed_match:
                        completion_message = task_completed_match.group(1).strip()
                    
                    # Save final debug log
                    if self.debug_mode:
                        try:
                            completion_info = {
                                "has_tool_calls": False,
                                "task_completed": True,
                                "completion_detected": True,
                                "execution_result": "task_completed_flag"
                            }
                            
                            self._save_llm_call_debug_log(messages, f"Task completed with TASK_COMPLETED flag", 1, completion_info)
                        except Exception as log_error:
                            print_current(f"❌ Completion debug log save failed: {log_error}")
                    
                    # Store task completion in long-term memory
                    self._store_task_completion_memory(prompt, content, {
                        "task_completed": True,
                        "completion_method": "TASK_COMPLETED_flag",
                        "execution_round": round_counter,
                        "model_used": self.model
                    })
                    
                    finish_operation(f"executing task (round {round_counter})")
                    # Return optimized history if available
                    if history_was_optimized:
                        return (content, task_history)
                    return content
                
                # Execute tools if present
                if tool_calls:
                    print_current(f"🔧 Model decided to call {len(tool_calls)} tools:")
                    print_current("=" * 50)
                    
                    # Print tool calls for terminal display with better formatting
                    tool_calls_formatted = self._format_tool_calls_for_history(tool_calls)
                    if tool_calls_formatted:
                        # Remove the "**Tool Calls:**" header since we already printed our own
                        display_content = tool_calls_formatted.replace("**Tool Calls:**\n", "").strip()
                        print_current(display_content)
                    
                    print_current("=" * 50)
                    print_current("🚀 Starting tool execution...")
                    print_current("")
                    
                    # Execute all tool calls and collect results
                    all_tool_results = []
                    successful_executions = 0
                    
                    for i, tool_call in enumerate(tool_calls, 1):
                        # Handle standard format tool calls (both OpenAI and Anthropic)
                        tool_name = self._get_tool_name_from_call(tool_call)
                        tool_params = self._get_tool_params_from_call(tool_call)
                        
                        # 🔧 NEW: Track if get_sensor_data was called in current round
                        if tool_name == 'get_sensor_data':
                            current_round_has_sensor_data = True
                        
                        # Print tool execution start with clear formatting
                        print_current(f"🔧 Executing tool {i}: {tool_name}")
                        print_current(f"   Parameters: {tool_params}")
                        print_current(f"   Results:")
                        
                        try:
                            # Convert to standard format for execute_tool
                            standard_tool_call = {
                                "name": tool_name,
                                "arguments": tool_params
                            }
                            tool_result = self.execute_tool(standard_tool_call)
                            
                            all_tool_results.append({
                                'tool_name': tool_name,
                                'tool_params': tool_params,
                                'tool_result': tool_result
                            })
                            successful_executions += 1
                            
                            # Real-time print of each tool's execution result with proper indentation
                            if isinstance(tool_result, dict):
                                # Use simplified formatting for search tools if enabled in config
                                if (self.simplified_search_output and 
                                    tool_name in ['codebase_search', 'web_search']):
                                    formatted_result = self._format_search_result_for_terminal(tool_result, tool_name)
                                else:
                                    formatted_result = self._format_dict_as_text(tool_result, for_terminal_display=True)
                                # Add indentation to each line
                                indented_result = "\n".join(f"   {line}" for line in formatted_result.split("\n"))
                                print_current(indented_result)
                            else:
                                # Add indentation to the result
                                result_str = str(tool_result)
                                indented_result = "\n".join(f"   {line}" for line in result_str.split("\n"))
                                print_current(indented_result)
                            
                        except Exception as e:
                            error_msg = f"Tool {tool_name} execution failed: {str(e)}"
                            print_current(f"   ❌ {error_msg}")
                            all_tool_results.append({
                                'tool_name': tool_name,
                                'tool_params': tool_params,
                                'tool_result': f"Error: {error_msg}"
                            })
                        
                        # Add separator between tools
                        if i < len(tool_calls):
                            print_current("-" * 30)
                    

                    
                    # 🔧 MODIFIED: Store image data but don't use vision API
                    self._extract_current_round_images(all_tool_results)
                    
                    # 🔧 NEW: Format tool results with base64 data detection
                    tool_results_message = self._format_tool_results_for_llm(all_tool_results, include_base64_info=current_round_has_sensor_data)
                    
                    # Save debug log with tool execution info
                    if self.debug_mode:
                        try:
                            tool_execution_info = {
                                "has_tool_calls": True,
                                "parsed_tool_calls": tool_calls,
                                "tool_results": all_tool_results,
                                "formatted_tool_results": tool_results_message,
                                "successful_executions": successful_executions,
                                "total_tool_calls": len(tool_calls),
                                "conflict_detected": conflict_detected
                            }
                            
                            self._save_llm_call_debug_log(messages, f"Single execution with {len(tool_calls)} tool calls", 1, tool_execution_info)
                        except Exception as log_error:
                            print_current(f"❌ Debug log save failed: {log_error}")
                    
                    # Return combined response with tool calls and tool results
                    result_parts = [content]
                    if tool_calls_formatted:
                        result_parts.append("\n\n--- Tool Calls ---\n" + tool_calls_formatted)
                    result_parts.append("\n\n--- Tool Execution Results ---\n" + tool_results_message)
                    
                    # Store task completion in long-term memory
                    combined_result = "".join(result_parts)
                    self._store_task_completion_memory(prompt, combined_result, {
                        "task_completed": True,
                        "completion_method": "tool_execution",
                        "execution_round": round_counter,
                        "tool_calls_count": len(tool_calls),
                        "successful_executions": successful_executions,
                        "model_used": self.model
                    })
                    
                    finish_operation(f"executing task (round {round_counter})")
                    # Return optimized history if available, even with tool calls
                    if history_was_optimized:
                        return (combined_result, task_history)
                    return combined_result
                
                else:
                    # No tool calls, return LLM response directly
                    print_current("📝 No tool calls found, returning LLM response")
                    
                    # 🔧 NEW: Add base64 data status information when no tools are called
                    base64_status_info = "\n\n## Base64 Data Status\n❌ No base64 encoded image data acquired in this round (no get_sensor_data tool called)."
                    content = content + base64_status_info
                    
                    # Save debug log for response without tools
                    if self.debug_mode:
                        try:
                            no_tools_info = {
                                "has_tool_calls": False,
                                "task_completed": has_task_completed,
                                "execution_result": "llm_response_only"
                            }
                            
                            self._save_llm_call_debug_log(messages, f"Single execution, no tool calls", 1, no_tools_info)
                        except Exception as log_error:
                            print_current(f"❌ Final debug log save failed: {log_error}")
                    
                    # Store task completion in long-term memory
                    self._store_task_completion_memory(prompt, content, {
                        "task_completed": True,
                        "completion_method": "llm_response_only",
                        "execution_round": round_counter,
                        "model_used": self.model
                    })
                    
                    finish_operation(f"executing task (round {round_counter})")
                    # Return optimized history if available
                    if history_was_optimized:
                        return (content, task_history)
                    return content
                
            except json.JSONDecodeError as e:
                error_msg = f"❌ JSON parsing error in tool call: {str(e)}"
                print_current(error_msg)
                print_current(f"📄 This usually means the model generated invalid JSON in tool arguments")
                print_current(f"💡 Try regenerating the response or check the model's tool calling format")
                finish_operation(f"executing task (round {round_counter})")
                return error_msg
            except Exception as e:
                error_msg = f"❌ Error executing subtask: {str(e)}"
                print_current(error_msg)
                
                # Add more specific error information for common issues
                if "Expecting ',' delimiter" in str(e):
                    print_current(f"💡 This is likely a JSON formatting issue in tool arguments")
                    print_current(f"🔧 The model may have generated malformed JSON - try regenerating")
                elif "json.loads" in str(e) or "JSONDecodeError" in str(e):
                    print_current(f"💡 JSON parsing error detected - check tool argument formatting")
                
                finish_operation(f"executing task (round {round_counter})")
                return error_msg
            
            # Add current result to accumulated results
            accumulated_results += content
            
            # Add tool calls to conversation history
            conversation_history.append({"role": "assistant", "content": content})
            
            # Add tool calls to tool_calls list
            tool_calls_list.extend(tool_calls)
            
            round_counter += 1
        
        # If we reach here, it means we've completed all tool calls
        print_current("🎉 All tool calls completed successfully!")
        
        # Return final accumulated results
        return accumulated_results
    
    def _check_terminate_messages(self) -> Optional[str]:
        """
        检查agent是否收到terminate信号
        
        Returns:
            如果收到terminate信号返回终止消息，否则返回None
        """
        try:
            # 只有在多智能体模式下才检查
            if not self.multi_agent_tools:
                return None
            
            # 🔧 修复：直接从mailbox获取未读消息，不自动标记为已读
            from tools.message_system import get_message_router
            from tools.print_system import get_agent_id
            
            current_agent_id = get_agent_id()
            if not current_agent_id:
                return None
                
            try:
                router = get_message_router(self.multi_agent_tools.workspace_root, cleanup_on_init=False)
                mailbox = router.get_mailbox(current_agent_id)
                
                if not mailbox:
                    return None
                
                # 直接获取未读消息，不自动标记为已读
                unread_messages = mailbox.get_unread_messages()
                
                # 检查是否有terminate信号
                for message in unread_messages:
                    if hasattr(message, 'message_type') and hasattr(message, 'content'):
                        message_type = message.message_type
                        content = message.content
                        
                        # 检查是否是系统消息且包含terminate信号
                        if (message_type.value == "system" and 
                            isinstance(content, dict) and 
                            content.get("signal") == "terminate"):
                            
                            reason = content.get("reason", "Terminated by request")
                            sender = content.get("sender", "unknown")
                            
                            terminate_msg = f"AGENT_TERMINATED: Agent {current_agent_id} received terminate signal from {sender}. Reason: {reason}"
                            print_current(f"🛑 {terminate_msg}")
                            
                            # 只有在确认terminate信号后才标记消息为已读
                            try:
                                mailbox.mark_as_read(message.message_id)
                            except Exception as e:
                                print_current(f"⚠️ Warning: Could not mark terminate message as read: {e}")
                            
                            return terminate_msg
                            
                return None
                
            except Exception as e:
                if self.debug_mode:
                    print_current(f"⚠️ Warning: Error accessing mailbox directly: {e}")
                return None
            
        except Exception as e:
            # 如果检查terminate消息失败，不应该中断正常执行
            if self.debug_mode:
                print_current(f"⚠️ Warning: Failed to check terminate messages: {e}")
            return None
    
    def parse_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse multiple tool calls from the model's response.
        
        Args:
            content: The model's response text
            
        Returns:
            List of dictionaries with tool name and parameters
        """
        
        # Debug mode, save raw content for analysis
        if self.debug_mode:
            # Check for common tool call format markers
            has_function_calls = '<function_calls>' in content
            has_invoke = '<invoke' in content
            has_function_call = '<function_call>' in content
            has_json_block = '```json' in content
            has_tool_calls_json = '"tool_calls"' in content
        
        all_tool_calls = []
        

        openai_json_pattern = r'```json\s*\{\s*"tool_calls"\s*:\s*\[(.*?)\]\s*\}\s*```'
        openai_json_match = re.search(openai_json_pattern, content, re.DOTALL)
        if openai_json_match:
            try:
                # Extract the full JSON structure
                json_start = content.find('```json')
                json_end = content.find('```', json_start + 7) + 3
                if json_start != -1 and json_end > json_start:
                    json_block = content[json_start + 7:json_end - 3].strip()
                    
                    # Handle common escape issues in JSON strings
                    # Replace single backslashes with double backslashes to make valid JSON
                    # But be careful not to double-escape already valid escapes
                    json_block = fix_json_escapes(json_block)
                    
                    tool_calls_data = json.loads(json_block)
                    
                    if isinstance(tool_calls_data, dict) and 'tool_calls' in tool_calls_data:
                        for i, tool_call in enumerate(tool_calls_data['tool_calls']):
                            if isinstance(tool_call, dict) and 'function' in tool_call:
                                function_data = tool_call['function']
                                if 'name' in function_data and 'arguments' in function_data:
                                    arguments = function_data['arguments']
                                    # If arguments is a string (JSON), parse it
                                    if isinstance(arguments, str):
                                        try:
                                            arguments = json.loads(arguments)
                                        except json.JSONDecodeError:
                                            pass
                                    
                                    all_tool_calls.append({
                                        "name": function_data['name'],
                                        "arguments": arguments
                                    })
                        
                        # If we found OpenAI-style tool calls, return them
                        if all_tool_calls:
                            return all_tool_calls
            except json.JSONDecodeError as e:
                if self.debug_mode:
                    print_current(f"Failed to parse OpenAI-style JSON tool calls: {e}")
        
        # Also try to parse direct JSON tool calls without ```json wrapper
        direct_json_pattern = r'\{\s*"tool_calls"\s*:\s*\[(.*?)\]\s*\}'
        direct_json_match = re.search(direct_json_pattern, content, re.DOTALL)
        if direct_json_match and not all_tool_calls:
            try:
                json_str = direct_json_match.group(0)
                json_str = fix_json_escapes(json_str)
                tool_calls_data = json.loads(json_str)
                if isinstance(tool_calls_data, dict) and 'tool_calls' in tool_calls_data:
                    for tool_call in tool_calls_data['tool_calls']:
                        if isinstance(tool_call, dict) and 'function' in tool_call:
                            function_data = tool_call['function']
                            if 'name' in function_data and 'arguments' in function_data:
                                arguments = function_data['arguments']
                                # If arguments is a string (JSON), parse it
                                if isinstance(arguments, str):
                                    try:
                                        arguments = json.loads(arguments)
                                    except json.JSONDecodeError:
                                        pass
                                
                                all_tool_calls.append({
                                    "name": function_data['name'],
                                    "arguments": arguments
                                })
                    
                    # If we found direct JSON tool calls, return them
                    if all_tool_calls:
                        return all_tool_calls
            except json.JSONDecodeError as e:
                if self.debug_mode:
                    print_current(f"Failed to parse direct JSON tool calls: {e}")
        
        # Continue with existing XML parsing logic...
        # Try to parse individual <function_call> tags (single format)
        function_call_pattern = r'<function_call>\s*\{(.*?)\}\s*</function_call>'
        function_call_matches = re.findall(function_call_pattern, content, re.DOTALL)
        if function_call_matches:
            for match in function_call_matches:
                try:
                    # Parse the JSON content inside function_call tags
                    json_str = '{' + match + '}'
                    tool_data = json.loads(json_str)
                    
                    if isinstance(tool_data, dict):
                        # Handle different JSON structures
                        if 'name' in tool_data and 'parameters' in tool_data:
                            all_tool_calls.append({
                                "name": tool_data["name"],
                                "arguments": tool_data["parameters"]
                            })
                        elif 'name' in tool_data and 'content' in tool_data:
                            all_tool_calls.append({
                                "name": tool_data["name"],
                                "arguments": tool_data["content"]
                            })
                except json.JSONDecodeError as e:
                    continue
            
            # If we found function_call format tool calls, return them
            if all_tool_calls:
                return all_tool_calls
        
        # Try to parse XML format with function_calls wrapper
        function_calls_matches = re.findall(r'<function_calls>(.*?)</function_calls>', content, re.DOTALL)
        if function_calls_matches:
            for i, function_calls_text in enumerate(function_calls_matches, 1):
                # Parse the function calls in this block
                function_calls = self.parse_function_calls(function_calls_text)
                if function_calls:
                    all_tool_calls.extend(function_calls)
            
            # If we found function_calls wrapper tool calls, return directly, avoid duplicate parsing
            if all_tool_calls:
                return all_tool_calls
        
        # Only try to parse individual invoke tags if no function_calls wrapper was found
        invoke_pattern = r'<invoke name="([^"]+)">(.*?)</invoke>'
        invoke_matches = re.findall(invoke_pattern, content, re.DOTALL)
        if invoke_matches:
            for tool_name, args_text in invoke_matches:
                args = self.parse_arguments(args_text)
                all_tool_calls.append({"name": tool_name, "arguments": args})
        
        # If we found tool calls through XML parsing, return them
        if all_tool_calls:
            return all_tool_calls
        
        # Fallback: try to parse Python function call format
        python_tool_calls = self.parse_python_function_calls(content)
        if python_tool_calls:
            all_tool_calls.extend(python_tool_calls)
            return all_tool_calls
        
        # NEW: Support for multiple independent JSON tool calls (like our new format)
        # Look for multiple ```json blocks with tool_name format
        multiple_json_pattern = r'```json\s*(.*?)\s*```'
        multiple_json_matches = re.findall(multiple_json_pattern, content, re.DOTALL)
        if multiple_json_matches:
            for json_str in multiple_json_matches:
                try:
                    json_str = json_str.strip()
                    tool_data = json.loads(json_str)
                    
                    if isinstance(tool_data, dict):
                        # Check if it's our new tool_name format
                        if 'tool_name' in tool_data and 'parameters' in tool_data:
                            all_tool_calls.append({
                                "name": tool_data["tool_name"],
                                "arguments": tool_data["parameters"]
                            })
                        # Check if it's the old name format (backward compatibility)
                        elif 'name' in tool_data and 'parameters' in tool_data:
                            all_tool_calls.append({
                                "name": tool_data["name"],
                                "arguments": tool_data["parameters"]
                            })
                        # Check if it's content format
                        elif 'name' in tool_data and 'content' in tool_data:
                            all_tool_calls.append({
                                "name": tool_data["name"],
                                "arguments": tool_data["content"]
                            })
                except json.JSONDecodeError:
                    continue
            
            # If we found any tool calls through multiple JSON blocks, return them
            if all_tool_calls:
                return all_tool_calls
        
        # Fallback: try to parse single JSON format with nested content structure (like in the logs)
        json_pattern = r'```json\s*(.*?)\s*```'
        json_match = re.search(json_pattern, content, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                tool_data = json.loads(json_str)
                
                # Handle nested structure like {"name": "edit_file", "content": {...}}
                if isinstance(tool_data, dict):
                    if 'name' in tool_data and 'content' in tool_data:
                        return [{
                            "name": tool_data["name"],
                            "arguments": tool_data["content"]
                        }]
                    # Check if it's a valid tool call format with tool_name and parameters (新的JSON格式)
                    elif 'tool_name' in tool_data and 'parameters' in tool_data:
                        return [{
                            "name": tool_data["tool_name"],
                            "arguments": tool_data["parameters"]
                        }]
                    # Check if it's a valid tool call format with name and parameters (兼容旧格式)
                    elif 'name' in tool_data and 'parameters' in tool_data:
                        return [{
                            "name": tool_data["name"],
                            "arguments": tool_data["parameters"]
                        }]
                    # Check if it's a direct parameter format, try to infer tool name from context
                    else:
                        # Look for tool name mentioned in the text before JSON
                        text_before_json = content[:content.find('```json')]
                        
                        # Common tool names to look for
                        tool_names = list(self.tool_map.keys())
                        inferred_tool = None
                        
                        for tool_name in tool_names:
                            if tool_name in text_before_json.lower() or tool_name.replace('_', ' ') in text_before_json.lower():
                                inferred_tool = tool_name
                                break
                        
                        # If no tool found in text, try to infer from parameters
                        if not inferred_tool:
                            if 'target_file' in tool_data and ('should_read_entire_file' in tool_data or 'start_line' in tool_data):
                                inferred_tool = 'read_file'
                            elif 'relative_workspace_path' in tool_data:
                                inferred_tool = 'list_dir'
                            elif 'query' in tool_data and 'target_directories' in tool_data:
                                inferred_tool = 'codebase_search'
                            elif 'query' in tool_data and ('include_pattern' in tool_data or 'exclude_pattern' in tool_data):
                                inferred_tool = 'grep_search'
                            elif 'command' in tool_data and 'is_background' in tool_data:
                                inferred_tool = 'run_terminal_cmd'
                            elif 'target_file' in tool_data and ('instructions' in tool_data or 'code_edit' in tool_data):
                                inferred_tool = 'edit_file'
                        
                        if inferred_tool:
                            return [{
                                "name": inferred_tool,
                                "arguments": tool_data
                            }]
            except json.JSONDecodeError as e:
                pass
        
        # Try to parse JSON array format (AGIBot's chat-based tool calls)
        try:
            # Look for JSON array structure in the content
            array_start = content.find('[')
            array_end = content.rfind(']') + 1
            if array_start != -1 and array_end > array_start:
                json_str = content[array_start:array_end]
                tool_array = json.loads(json_str)
                
                # Handle JSON array of tool calls
                if isinstance(tool_array, list):
                    parsed_tools = []
                    for tool_item in tool_array:
                        if isinstance(tool_item, dict):
                            if 'tool_name' in tool_item and 'parameters' in tool_item:
                                parsed_tools.append({
                                    "name": tool_item["tool_name"],
                                    "arguments": tool_item["parameters"]
                                })
                            elif 'name' in tool_item and 'parameters' in tool_item:
                                parsed_tools.append({
                                    "name": tool_item["name"],
                                    "arguments": tool_item["parameters"]
                                })
                    
                    if parsed_tools:
                        return parsed_tools
        except json.JSONDecodeError:
            pass

        # Try to parse plain JSON without code blocks
        try:
            # Look for JSON-like structure in the content
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                tool_data = json.loads(json_str)
                
                # Handle nested structure
                if isinstance(tool_data, dict):
                    if 'name' in tool_data and 'content' in tool_data:
                        return [{
                            "name": tool_data["name"],
                            "arguments": tool_data["content"]
                        }]
                    elif 'name' in tool_data and 'parameters' in tool_data:
                        return [{
                            "name": tool_data["name"],
                            "arguments": tool_data["parameters"]
                        }]
                    # Support for AGIBot's chat-based tool calling format
                    elif 'tool_name' in tool_data and 'parameters' in tool_data:
                        return [{
                            "name": tool_data["tool_name"],
                            "arguments": tool_data["parameters"]
                        }]
        except json.JSONDecodeError:
            pass
    
        return []


    def parse_tool_call(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single tool call from the model's response (backward compatibility).
        
        Args:
            content: The model's response text
            
        Returns:
            Dictionary with tool name and parameters, or None if no tool call found
        """
        tool_calls = self.parse_tool_calls(content)
        return tool_calls[0] if tool_calls else None


    
    def parse_python_function_calls(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse Python-style function calls from the model's response.
        This serves as a fallback for when the model doesn't use the correct XML format.
        
        Args:
            content: The model's response text
            
        Returns:
            List of dictionaries, each representing a function call
        """

        
        function_calls = []
        
        # Pattern to match function calls like: tool_name({"param": "value", ...})
        # Updated pattern to better handle multiline strings and nested braces
        python_pattern = r'(\w+)\s*\(\s*(\{(?:[^{}]|(?:\{[^{}]*\}))*\})\s*\)'
        
        matches = re.findall(python_pattern, content, re.DOTALL)
        
        for tool_name, params_str in matches:
            # Check if this is a valid tool name
            if tool_name in self.tool_map:
                try:
                    # Try to parse the parameters as JSON directly
                    # Fix common JSON issues
                    params_json = params_str.replace("'", '"')  # Replace single quotes with double quotes
                    
                    params = json.loads(params_json)
                    
                    function_calls.append({
                        "name": tool_name,
                        "arguments": params
                    })
                    
                except json.JSONDecodeError as e:
                    # Try to extract individual parameters manually
                    try:
                        params = parse_python_params_manually(params_str)
                        if params:
                            function_calls.append({
                                "name": tool_name,
                                "arguments": params
                            })
                    except Exception as e2:
                        continue
        
        return function_calls
    

    
    def parse_function_calls(self, function_calls_text: str) -> List[Dict[str, Any]]:
        """
        Parse function calls from the given text.
        
        Args:
            function_calls_text: Text containing function calls
            
        Returns:
            List of dictionaries, each representing a function call
        """
        function_calls = []
        # Look for individual function calls
        invoke_pattern = r'<invoke name="([^"]+)">(.*?)</invoke>'
        invokes = re.findall(invoke_pattern, function_calls_text, re.DOTALL)
        for name, args_text in invokes:
            # Parse the arguments
            args = self.parse_arguments(args_text)
            function_calls.append({"name": name, "arguments": args})
        return function_calls
    
    def parse_arguments(self, args_text: str) -> Dict[str, Any]:
        """
        Parse arguments from the given text.
        
        Args:
            args_text: Text containing arguments
            
        Returns:
            Dictionary of argument names and values
        """
        args = {}
        
        # Method 1: Try the traditional <parameter name="...">value</parameter> format
        arg_pattern = r'<parameter name="([^"]+)">(.*?)</parameter>'
        arg_matches = re.findall(arg_pattern, args_text, re.DOTALL)
        for name, value in arg_matches:
            value = value.strip()
            args[name] = convert_parameter_value(value)
        
        # Method 2: Try the direct tag format <tag_name>value</tag_name>
        # This supports the more intuitive XML format that models often generate
        if not args:  # Only try this if the traditional format didn't work
            # Find all XML tags and their content
            direct_tag_pattern = r'<([^/][^>]*?)>(.*?)</\1>'
            direct_matches = re.findall(direct_tag_pattern, args_text, re.DOTALL)
            
            for tag_name, value in direct_matches:
                # Clean up the tag name (remove any attributes)
                tag_name = tag_name.split()[0]
                value = value.strip()
                
                # Handle special cases for array-like structures
                if tag_name == 'target_directories':
                    # Handle <target_directories><item>value1</item><item>value2</item></target_directories>
                    item_pattern = r'<item[^>]*>(.*?)</item>'
                    items = re.findall(item_pattern, value, re.DOTALL)
                    if items:
                        args[tag_name] = [item.strip() for item in items]
                    else:
                        args[tag_name] = convert_parameter_value(value)
                else:
                    args[tag_name] = convert_parameter_value(value)
        
        return args
    

    
    def execute_tool(self, tool_call: Dict[str, Any]) -> Any:
        """
        Execute a tool with the given parameters.
        
        Args:
            tool_call: Dictionary containing tool name and parameters
            
        Returns:
            Result of executing the tool
        """
        tool_name = tool_call["name"]
        params = tool_call["arguments"]
        
        # 🔧 Error handling: If the large model calls the send_message_to_manager tool, correct it to send_message_to_agent_or_manager
        if tool_name == "send_message_to_manager":
            print_current(f"🔧 Auto-correcting tool call: {tool_name} -> send_message_to_agent_or_manager")
            tool_name = "send_message_to_agent_or_manager"
            
            # If receiver_id parameter is missing, set it to manager
            if "receiver_id" not in params:
                params["receiver_id"] = "manager"
                print_current(f"🔧 Added missing receiver_id parameter: manager")
            
            # Update tool_call object to reflect the correction
            tool_call["name"] = tool_name
        # Check tool source from mapping table
        tool_source = getattr(self, 'tool_source_map', {}).get(tool_name, 'regular')
        
        # Handle cli-mcp tools
        if tool_source == 'cli_mcp':
            # Enhanced multi-thread initialization for cli-mcp client
            current_thread = threading.current_thread().name
            
            # First check: instance-level initialization status
            if not self.cli_mcp_initialized:
                print_current(f"🔄 [Thread: {current_thread}] cli-mcp client not initialized, attempting initialization for tool {tool_name}...")
                
                # Second check: global cli-mcp wrapper status
                from tools.cli_mcp_wrapper import get_cli_mcp_status, is_cli_mcp_initialized, initialize_cli_mcp_wrapper
                
                global_status = get_cli_mcp_status(self.MCP_config_file)
                print_current(f"🔍 [Thread: {current_thread}] Global cli-mcp status: {global_status}")
                
                # If globally initialized but not locally, sync the status
                if global_status.get("initialized", False) and not self.cli_mcp_initialized:
                    print_current(f"🔄 [Thread: {current_thread}] Global cli-mcp is initialized, syncing local status...")
                    self.cli_mcp_initialized = True
                    self._add_mcp_tools_to_map()
                    print_current(f"✅ [Thread: {current_thread}] Local cli-mcp status synced successfully")
                
                # If still not initialized, attempt initialization with enhanced retry
                if not self.cli_mcp_initialized:
                    retry_count = 0
                    max_retries = 3
                    
                    while retry_count < max_retries and not self.cli_mcp_initialized:
                        try:
                            retry_count += 1
                            print_current(f"🔄 [Thread: {current_thread}] cli-mcp initialization attempt {retry_count}/{max_retries}")
                            
                            import asyncio
                            
                            # Enhanced async handling for different thread contexts
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    # We're in an async context, use thread pool for initialization
                                    import concurrent.futures
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(asyncio.run, initialize_cli_mcp_wrapper(self.MCP_config_file))
                                        init_result = future.result(timeout=20)  # Increased timeout
                                        self.cli_mcp_initialized = init_result
                                else:
                                    # We can run the async function directly
                                    self.cli_mcp_initialized = asyncio.run(initialize_cli_mcp_wrapper(self.MCP_config_file))
                            except RuntimeError as re:
                                # No event loop or other runtime issues
                                print_current(f"⚠️ [Thread: {current_thread}] Runtime error during async init: {re}")
                                # Try creating new event loop
                                try:
                                    new_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(new_loop)
                                    self.cli_mcp_initialized = new_loop.run_until_complete(initialize_cli_mcp_wrapper(self.MCP_config_file))
                                    new_loop.close()
                                except Exception as loop_e:
                                    print_current(f"❌ [Thread: {current_thread}] Failed to create new event loop: {loop_e}")
                                    self.cli_mcp_initialized = False
                            
                            # Verify initialization and add tools to mapping
                            if self.cli_mcp_initialized:
                                self._add_mcp_tools_to_map()
                                print_current(f"✅ [Thread: {current_thread}] cli-mcp client initialized successfully with config: {self.MCP_config_file}")
                                
                                # Double-check the tool mapping
                                if tool_name in self.tool_map:
                                    print_current(f"✅ [Thread: {current_thread}] Tool {tool_name} found in tool mapping")
                                else:
                                    print_current(f"⚠️ [Thread: {current_thread}] Tool {tool_name} NOT found in tool mapping after initialization")
                                break
                            else:
                                print_current(f"⚠️ [Thread: {current_thread}] cli-mcp initialization attempt {retry_count} failed")
                                if retry_count < max_retries:
                                    import time
                                    time.sleep(3)  # Wait 3 seconds before retry
                                    
                        except Exception as e:
                            print_current(f"⚠️ [Thread: {current_thread}] cli-mcp client initialization attempt {retry_count} failed: {e}")
                            if retry_count < max_retries:
                                import time
                                time.sleep(3)  # Wait 3 seconds before retry
                            else:
                                error_msg = f"cli-mcp client initialization failed after {max_retries} attempts in thread {current_thread}: {e}"
                                print_current(f"❌ {error_msg}")
                                return {"error": error_msg}
                    
                    # Final check
                    if not self.cli_mcp_initialized:
                        error_msg = f"cli-mcp client failed to initialize after all attempts in thread {current_thread}"
                        print_current(f"❌ {error_msg}")
                        return {"error": error_msg}
            
            # Call cli-mcp tool with enhanced error handling
            try:
                print_current(f"🔧 [Thread: {current_thread}] Calling cli-mcp tool: {tool_name}")
                
                import asyncio
                
                # Enhanced async execution handling
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're in an async context, use thread pool for execution
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            # Remove prefix from tool name if present
                            actual_tool_name = tool_name.replace("cli_mcp_", "")
                            print_current(f"🎯 [Thread: {current_thread}] Calling actual tool: {actual_tool_name} with params: {params}")
                            future = executor.submit(asyncio.run, self.cli_mcp_client.call_tool(actual_tool_name, params))
                            result = future.result(timeout=35)  # Increased timeout
                            print_current(f"✅ [Thread: {current_thread}] cli-mcp tool call completed successfully")
                            return result
                except RuntimeError:
                    # No event loop, safe to run asyncio.run
                    pass
                
                # Synchronous execution
                actual_tool_name = tool_name.replace("cli_mcp_", "")
                print_current(f"🎯 [Thread: {current_thread}] Calling actual tool (sync): {actual_tool_name} with params: {params}")
                result = asyncio.run(self.cli_mcp_client.call_tool(actual_tool_name, params))
                print_current(f"✅ [Thread: {current_thread}] cli-mcp tool call completed successfully (sync)")
                return result
                
            except Exception as e:
                error_msg = f"cli-mcp工具调用失败 in thread {current_thread}: {e}"
                print_current(f"❌ {error_msg}")
                return {"error": error_msg}
        
        # Handle direct MCP tools (SSE)
        elif tool_source == 'direct_mcp':
            # Ensure direct MCP client is initialized
            if not self.direct_mcp_initialized:
                print_current(f"🔄 Attempting to initialize direct MCP client for tool {tool_name}...")
                import asyncio
                
                retry_count = 0
                max_retries = 3
                
                while retry_count < max_retries and not self.direct_mcp_initialized:
                    try:
                        retry_count += 1
                        print_current(f"🔄 Direct MCP initialization attempt {retry_count}/{max_retries}")
                        
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # We're in an async context, use thread pool for initialization
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(asyncio.run, self.direct_mcp_client.initialize())
                                self.direct_mcp_initialized = future.result(timeout=15)  # 增加超时时间
                        else:
                            # We can run the async function directly
                            self.direct_mcp_initialized = asyncio.run(self.direct_mcp_client.initialize())
                        
                        # Add MCP tools to tool_map after successful initialization
                        if self.direct_mcp_initialized:
                            self._add_mcp_tools_to_map()
                            print_current(f"✅ Direct MCP client initialized with config: {self.MCP_config_file}")
                            break
                        else:
                            print_current(f"⚠️ Direct MCP initialization attempt {retry_count} failed")
                            if retry_count < max_retries:
                                import time
                                time.sleep(2)  # 等待2秒后重试
                                
                    except Exception as e:
                        print_current(f"⚠️ Direct MCP client initialization attempt {retry_count} failed: {e}")
                        if retry_count < max_retries:
                            import time
                            time.sleep(2)  # 等待2秒后重试
                        else:
                            return {"error": f"Direct MCP client initialization failed after {max_retries} attempts: {e}"}
            
            # Call direct MCP tool
            try:
                import asyncio
                
                # 检查是否在异步环境中
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 在异步环境中，使用线程池执行
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            # Use tool name directly (no prefix removal needed for SSE tools)
                            future = executor.submit(asyncio.run, self.direct_mcp_client.call_tool(tool_name, params))
                            result = future.result(timeout=30)  # 30秒超时
                            return result
                except RuntimeError:
                    # 没有事件循环，可以安全地运行asyncio.run
                    pass
                
                # 在同步环境中运行异步函数
                result = asyncio.run(self.direct_mcp_client.call_tool(tool_name, params))
                return result
                
            except Exception as e:
                print_current(f"❌ SSE MCP工具调用失败: {e}")
                return {"error": f"SSE MCP工具调用失败: {e}"}
        
        # Handle regular tools
        if tool_name in self.tool_map:
            tool_func = self.tool_map[tool_name]
            try:
                # Filter out None values and empty strings for optional parameters
                filtered_params = {k: v for k, v in params.items() if v is not None and v != ""}
                
                # Special handling for read_file to map end_line_one_indexed to end_line_one_indexed_inclusive
                if tool_name == "read_file" and "end_line_one_indexed" in filtered_params:
                    # Map end_line_one_indexed to end_line_one_indexed_inclusive
                    filtered_params["end_line_one_indexed_inclusive"] = filtered_params.pop("end_line_one_indexed")
                    print_current("Mapped end_line_one_indexed parameter to end_line_one_indexed_inclusive")
                
                # Robustness handling: auto-correct wrong parameter names for edit_file and read_file
                if tool_name in ["edit_file", "read_file"]:
                    # Map relative_workspace_path to target_file
                    if "relative_workspace_path" in filtered_params:
                        filtered_params["target_file"] = filtered_params.pop("relative_workspace_path")
                        print_current(f"🔧 Auto-corrected parameter: relative_workspace_path -> target_file for {tool_name}")
                    # Map file_path to target_file
                    if "file_path" in filtered_params:
                        filtered_params["target_file"] = filtered_params.pop("file_path")
                        print_current(f"🔧 Auto-corrected parameter: file_path -> target_file for {tool_name}")
                    # Map filename to target_file (for edit_file)
                    if "filename" in filtered_params:
                        filtered_params["target_file"] = filtered_params.pop("filename")
                        print_current(f"🔧 Auto-corrected parameter: filename -> target_file for {tool_name}")
                
                # Robustness handling for edit_file: auto-correct content to code_edit
                if tool_name == "edit_file" and "content" in filtered_params:
                    # Map content to code_edit
                    filtered_params["code_edit"] = filtered_params.pop("content")
                    print_current(f"🔧 Auto-corrected parameter: content -> code_edit for {tool_name}")
                
                # Robustness handling for codebase_search: auto-correct search_term to query
                if tool_name == "codebase_search" and "search_term" in filtered_params:
                    # Map search_term to query
                    filtered_params["query"] = filtered_params.pop("search_term")
                    print_current(f"🔧 Auto-corrected parameter: search_term -> query for {tool_name}")
                
                # 🔧 Robustness handling for multi-agent messaging tools: auto-add missing content parameter
                if tool_name in ["send_message_to_agent_or_manager", "broadcast_message_to_agents"]:
                    if "content" not in filtered_params:
                        # Provide default content based on message context
                        if tool_name == "send_message_to_agent_or_manager":
                            receiver_id = filtered_params.get("receiver_id", "unknown")
                            message_type = filtered_params.get("message_type", "status_update")
                            filtered_params["content"] = {
                                "message": f"Automated message to {receiver_id}",
                                "type": message_type,
                                "status": "active"
                            }
                        elif tool_name == "broadcast_message_to_agents":
                            message_type = filtered_params.get("message_type", "broadcast")
                            filtered_params["content"] = {
                                "message": "Broadcast message to all agents",
                                "type": message_type,
                                "status": "active"
                            }
                        print_current(f"🔧 Auto-added missing content parameter for {tool_name}: {filtered_params['content']}")
                
                # No special handling needed for run_terminal_cmd anymore
                
                result = tool_func(**filtered_params)
                
                # Enhanced error handling for edit_file and other tools
                if isinstance(result, dict) and result.get('status') == 'error':
                    # For terminal commands, preserve stdout and stderr information
                    if tool_name == 'run_terminal_cmd':
                        # Keep the original result with all details for terminal commands
                        return result
                    else:
                        # Return detailed error information for other failed tool executions
                        error_msg = result.get('error', result.get('message', 'Unknown error occurred'))
                        return {
                            'tool': tool_name,
                            'status': 'error', 
                            'error': error_msg,
                            'parameters': filtered_params,
                            'details': result  # Include original result for debugging
                        }
                
                return result
            except TypeError as e:
                # Handle parameter mismatch with helpful guidance
                error_msg = f"Parameter mismatch: {str(e)}"
                
                # Add specific guidance for common parameter issues
                if tool_name == 'edit_file' and 'code_edit' in str(e):
                    error_msg += "\n💡 HINT: edit_file requires 'code_edit' parameter. Example: \"code_edit\": \"your code content here\""
                elif tool_name == 'edit_file' and any(param in str(e) for param in ['start_line', 'end_line']):
                    error_msg += "\n💡 HINT: edit_file replace_lines mode requires 'start_line_one_indexed' and 'end_line_one_indexed_inclusive' parameters"
                elif tool_name == 'read_file' and any(param in str(e) for param in ['start_line', 'end_line', 'should_read']):
                    error_msg += "\n💡 HINT: read_file requires 'target_file' and 'should_read_entire_file'. Line parameters are optional when should_read_entire_file=true"
                elif tool_name == 'run_terminal_cmd' and 'is_background' in str(e):
                    error_msg += "\n💡 HINT: run_terminal_cmd requires 'command' and 'is_background' parameters"
                
                error_result = {
                    'tool': tool_name,
                    'status': 'error',
                    'error': error_msg,
                    'parameters': params
                }
                print_current(f"❌ Tool execution failed: {error_result}")
                return error_result
            except Exception as e:
                # General exception handling
                error_result = {
                    'tool': tool_name,
                    'status': 'error', 
                    'error': f"Execution failed: {str(e)}",
                    'parameters': params
                }
                print_current(f"❌ Tool execution failed: {error_result}")
                return error_result
        else:
            # Unknown tool - provide list of available tools with brief usage info
            available_tools_list = list(self.tool_map.keys())
            tools_help_summary = []
            
            # Get brief help for each available tool
            for available_tool in available_tools_list[:5]:  # Limit to first 5 tools to avoid overwhelming output
                try:
                    help_info = self.tools.tool_help(available_tool)
                    if 'description' in help_info and 'error' not in help_info:
                        # Get first sentence of description
                        desc = help_info['description'].split('.')[0].split('\n')[0][:100]
                        tools_help_summary.append(f"- {available_tool}: {desc}")
                    else:
                        tools_help_summary.append(f"- {available_tool}")
                except:
                    tools_help_summary.append(f"- {available_tool}")
            
            if len(available_tools_list) > 5:
                tools_help_summary.append(f"... and {len(available_tools_list) - 5} more tools")
            
            available_tools_help = "\n".join(tools_help_summary)
            
            error_result = {
                'tool': tool_name,
                'status': 'error',
                'error': f"Unknown tool: {tool_name}",
                'available_tools': available_tools_list,
                'available_tools_help': f"Available tools:\n{available_tools_help}\n\nUse tool_help('<tool_name>') to get detailed usage for any specific tool."
            }
            print_current(f"❌ Tool execution failed: {error_result}")
            return error_result
    
    def _format_dict_as_text(self, data: Dict[str, Any], for_terminal_display: bool = False) -> str:
        """
        Format a dictionary result as readable text.
        
        Args:
            data: Dictionary to format
            for_terminal_display: If True, skip stdout/stderr for terminal commands to avoid duplication
            
        Returns:
            Formatted text string
        """
        if not isinstance(data, dict):
            return str(data)
        
        lines = []
        
        # Handle common result patterns
        if 'error' in data:
            error_msg = f"Error: {data['error']}"
            if 'tool' in data:
                error_msg = f"Tool '{data['tool']}' failed: {data['error']}"
            if 'parameters' in data:
                error_msg += f"\nParameters used: {data['parameters']}"
            if 'available_tools' in data:
                error_msg += f"\nAvailable tools: {', '.join(data['available_tools'])}"
            if 'available_tools_help' in data:
                error_msg += f"\n\n{data['available_tools_help']}"

            return error_msg
        
        if 'status' in data:
            lines.append(f"Status: {data['status']}")
        
        if 'file' in data:
            lines.append(f"File: {data['file']}")
        
        # Special handling for read_file results with truncation information
        if 'content' in data:
            # Check if this is a read_file result with truncation info
            if 'total_lines' in data:
                total_lines = data['total_lines']
                
                # Handle truncated entire file read
                if data.get('truncated', False) and 'lines_shown' in data:
                    lines_shown = data['lines_shown']
                    lines.append(f"📄 **FILE TRUNCATED**: Showing lines 1-{lines_shown} of {total_lines} total lines")
                    lines.append(f"⚠️  **IMPORTANT**: The file has {total_lines - lines_shown} additional lines that are not shown.")
                    lines.append(f"Content (first {lines_shown} lines):")
                    lines.append(f"{data['content']}")
                    if 'after_summary' in data:
                        lines.append(f"\n{data['after_summary']}")
                # Handle partial file read
                elif 'start_line' in data and 'end_line' in data:
                    start_line = data['start_line']
                    end_line = data['end_line']
                    lines.append(f"📄 **PARTIAL FILE READ**: Showing lines {start_line}-{end_line} of {total_lines} total lines")
                    if 'before_summary' in data and data['before_summary']:
                        lines.append(f"⚠️  **BEFORE**: {data['before_summary']}")
                    lines.append(f"Content (lines {start_line}-{end_line}):")
                    lines.append(f"{data['content']}")
                    if 'after_summary' in data and data['after_summary']:
                        lines.append(f"⚠️  **AFTER**: {data['after_summary']}")
                # Handle complete file read (no truncation)
                else:
                    lines.append(f"📄 **COMPLETE FILE**: Showing all {total_lines} lines")
                    lines.append(f"Content:")
                    lines.append(f"{data['content']}")
            else:
                # Fallback for content without line info
                lines.append(f"Content:\n{data['content']}")
        
        # Special handling for web search results
        if 'search_term' in data and 'results' in data:
            lines.append(f"Search Term: {data['search_term']}")
            if 'timestamp' in data:
                lines.append(f"Search Time: {data['timestamp']}")
            
            results = data['results']
            if isinstance(results, list):
                lines.append(f"\nSearch Results ({len(results)} items):")
                for i, result in enumerate(results[:10], 1):  # Limit to first 10
                    if isinstance(result, dict):
                        lines.append(f"\n{i}. {result.get('title', 'No Title')}")
                        
                        # URL field removed from display to reduce clutter
                        
                        # Handle content with priority: full_content > content > content_summary > snippet
                        content_shown = False
                        if result.get('full_content'):
                            content = result['full_content']
                            if len(content) > get_truncation_length():
                                lines.append(f"   Content: {content[:get_truncation_length()]}...\n   [Content truncated - showing first {get_truncation_length()} characters]")
                            else:
                                lines.append(f"   Content: {content}")
                            content_shown = True
                        elif result.get('content'):
                            content = result['content']
                            if len(content) > get_truncation_length():
                                lines.append(f"   Content: {content[:get_truncation_length()]}...\n   [Content truncated - showing first {get_truncation_length()} characters]")
                            else:
                                lines.append(f"   Content: {content}")
                            content_shown = True
                        elif result.get('content_summary'):
                            lines.append(f"   Content Summary: {result['content_summary']}")
                            content_shown = True
                        
                        # If no content, show snippet
                        if not content_shown and result.get('snippet'):
                            lines.append(f"   Summary: {result['snippet'][:get_truncation_length()]}...")
                        
                        # Show source
                        if result.get('source'):
                            lines.append(f"   Source: {result['source']}")
                        
                        # Show content status for results without content
                        if result.get('content_status'):
                            lines.append(f"   Content Status: {result['content_status']}")
            
            # Add additional web search metadata
            if 'content_fetched' in data:
                lines.append(f"\nContent Fetched: {data['content_fetched']}")
            if 'total_results' in data:
                lines.append(f"Total Results: {data['total_results']}")
            if 'results_with_content' in data:
                lines.append(f"Results with Content: {data['results_with_content']}")
            
            return '\n'.join(lines)
        
        # Handle agent messages results from get_agent_messages
        if 'messages' in data and 'agent_id' in data and 'message_count' in data:
            agent_id = data.get('agent_id', 'unknown')
            message_count = data.get('message_count', 0)
            messages = data.get('messages', [])
            
            lines.append(f"📬 Agent {agent_id} Messages: {message_count} messages")
            
            if message_count > 0:
                lines.append("")
                # Show each message with a summary format
                for i, msg in enumerate(messages[:10], 1):  # Limit to first 10 messages
                    if isinstance(msg, dict):
                        msg_id = msg.get('message_id', f'msg_{i}')
                        sender = msg.get('sender_id', 'unknown')
                        msg_type = msg.get('message_type', 'unknown')
                        timestamp = msg.get('timestamp', 'unknown')
                        read_status = "✓ read" if msg.get('read', False) else "unread"
                        
                        lines.append(f"  {i}. {msg_id} from {sender}")
                        lines.append(f"     Type: {msg_type} | Time: {timestamp} | Status: {read_status}")
                        
                        # Show content preview
                        content = msg.get('content', {})
                        if isinstance(content, dict):
                            # Special handling for different message types
                            if content.get('message'):
                                preview = str(content['message'])[:100]
                                if len(str(content['message'])) > 100:
                                    preview += "..."
                                lines.append(f"     Content: {preview}")
                            elif content.get('llm_response_preview'):
                                preview = str(content['llm_response_preview'])[:100]
                                if len(str(content['llm_response_preview'])) > 100:
                                    preview += "..."
                                lines.append(f"     Response: {preview}")
                            elif content.get('current_task_description'):
                                preview = str(content['current_task_description'])[:100]
                                if len(str(content['current_task_description'])) > 100:
                                    preview += "..."
                                lines.append(f"     Task: {preview}")
                            else:
                                # Generic content preview
                                content_str = json.dumps(content, ensure_ascii=False)[:150]
                                if len(json.dumps(content, ensure_ascii=False)) > 150:
                                    content_str += "..."
                                lines.append(f"     Content: {content_str}")
                        else:
                            content_str = str(content)[:100]
                            if len(str(content)) > 100:
                                content_str += "..."
                            lines.append(f"     Content: {content_str}")
                        
                        lines.append("")  # Empty line between messages
                
                if message_count > 10:
                    lines.append(f"  ... and {message_count - 10} more messages")
            
            # Add mailbox statistics if available
            if 'mailbox_stats' in data:
                stats = data['mailbox_stats']
                lines.append("")
                lines.append(f"📊 Mailbox Stats:")
                for key, value in stats.items():
                    lines.append(f"   {key}: {value}")
            
            # Add workspace info
            if 'found_in_workspace' in data:
                lines.append(f"📁 Workspace: {data['found_in_workspace']}")
            
            return '\n'.join(lines)

        # Handle other types of results
        if 'results' in data:
            results = data['results']
            if isinstance(results, list):
                lines.append(f"Results ({len(results)} items):")
                for i, result in enumerate(results[:10]):  # Limit to first 10
                    if isinstance(result, dict):
                        if 'file' in result and 'line_number' in result:
                            lines.append(f"  {i+1}. {result['file']}:{result['line_number']} - {result.get('line', '')}")
                        elif 'file' in result and 'snippet' in result:
                            lines.append(f"  {i+1}. {result['file']} - {result['snippet'][:get_truncation_length()]}...")
                        else:
                            lines.append(f"  {i+1}. {str(result)[:get_truncation_length()]}...")
                    else:
                        lines.append(f"  {i+1}. {str(result)}")
        
        if 'output' in data:
            lines.append(f"Output:\n{data['output']}")
        
        # Handle stdout/stderr based on context
        if for_terminal_display and ('command' in data and 'working_directory' in data):
            # For terminal display of terminal commands, skip stdout/stderr to avoid duplication
            # (they were already shown in real-time)
            pass
        else:
            # For LLM context or non-terminal commands, always include stdout/stderr
            if 'stdout' in data and data['stdout']:
                lines.append(f"Output:\n{data['stdout']}")
            
            if 'stderr' in data and data['stderr']:
                lines.append(f"Error Output:\n{data['stderr']}")
        
        # If no specific formatting applied, show all key-value pairs
        if not lines:
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    # Avoid serializing very large lists/dicts that could cause display issues
                    if isinstance(value, list) and len(value) > 20:
                        lines.append(f"{key}: [Large list with {len(value)} items - use specific tools to inspect]")
                    elif isinstance(value, dict) and len(json.dumps(value, ensure_ascii=False)) > 5000:
                        lines.append(f"{key}: [Large dict with {len(value)} keys - use specific tools to inspect]")
                    else:
                        lines.append(f"{key}: {json.dumps(value, indent=2, ensure_ascii=False)}")
                else:
                    # Special handling for base64 data field - truncate to 50 characters for terminal display
                    if key == 'data' and isinstance(value, str) and len(value) > 1000:
                        # Check if this looks like base64 data (long string with base64 characters)
                        import re
                        if re.match(r'^[A-Za-z0-9+/\[\]_:\-\.]+={0,2}$', value[:100]):
                            # Show only first 50 characters for terminal display
                            truncated_value = value[:50] + f"... [Total length: {len(value)} characters]"
                            lines.append(f"{key}: {truncated_value}")
                        else:
                            lines.append(f"{key}: {value}")
                    else:
                        lines.append(f"{key}: {value}")
        
        return '\n'.join(lines)




    def _save_llm_call_debug_log(self, messages: List[Dict[str, Any]], content: str, tool_call_round: int = 0, tool_calls_info: Optional[Dict[str, Any]] = None) -> None:
        """
        Save detailed debug log for LLM call.
        
        Args:
            messages: Complete messages sent to LLM
            content: LLM response content
            tool_call_round: Current tool call round number
            tool_calls_info: Additional tool call information for better logging
        """
        try:
            # Increment call counter
            self.llm_call_counter += 1
            
            # Create timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # microseconds to milliseconds
            
            # 🔧 获取当前agent ID并添加到文件名中
            from tools.print_system import get_agent_id
            current_agent_id = get_agent_id()
            if current_agent_id:
                log_filename = f"llm_call_{current_agent_id}_{self.llm_call_counter:03d}_{timestamp}.json"
            else:
                log_filename = f"llm_call_{self.llm_call_counter:03d}_{timestamp}.json"
            log_path = os.path.join(self.llm_logs_dir, log_filename)
            
            # 🔧 Apply message optimization to remove base64 data from logs
            optimized_messages = self._optimize_messages_for_logging(messages)
            
            # Prepare debug data - including detailed tool call information
            debug_data = {
                "call_info": {
                    "call_number": self.llm_call_counter,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "model": self.model,
                    "tool_call_round": tool_call_round  # Track which tool call round this is
                },
                "messages": optimized_messages,
                "response_content": content
            }
            
            # Add tool call information if available
            if tool_calls_info:
                debug_data["tool_calls_info"] = tool_calls_info
                
                # Add detailed breakdown for better debugging
                if "parsed_tool_calls" in tool_calls_info:
                    debug_data["call_info"]["tool_calls_count"] = len(tool_calls_info["parsed_tool_calls"])
                    debug_data["call_info"]["tool_names"] = [tc.get("name", "unknown") for tc in tool_calls_info["parsed_tool_calls"]]
                
                if "tool_results" in tool_calls_info:
                    debug_data["call_info"]["tool_results_count"] = len(tool_calls_info["tool_results"])
                    
                if "formatted_tool_results" in tool_calls_info:
                    debug_data["call_info"]["formatted_results_length"] = len(tool_calls_info["formatted_tool_results"])
            
            # Save to JSON file
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            
            
        except Exception as e:
            print_current(f"⚠️ Debug log save failed: {e}")

    def _optimize_messages_for_logging(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Optimize messages by replacing base64 data with references for logging purposes.
        
        Args:
            messages: Original messages list
            
        Returns:
            Optimized messages list with base64 data replaced by references
        """
        if not hasattr(self, 'history_optimizer') or not self.history_optimizer:
            return messages
        
        optimized_messages = []
        
        for message in messages:
            optimized_message = message.copy()
            
            # Check and optimize content field
            if 'content' in message and isinstance(message['content'], str):
                optimized_content = self._optimize_text_for_logging(message['content'])
                optimized_message['content'] = optimized_content
            
            optimized_messages.append(optimized_message)
        
        return optimized_messages
    
    def _optimize_text_for_logging(self, text: str) -> str:
        """
        Optimize text content by replacing base64 data with lightweight references for logging.
        
        Args:
            text: Original text content
            
        Returns:
            Optimized text with base64 data replaced by references
        """
        if not text or not isinstance(text, str):
            return text
        
        import re
        import hashlib
        
        # Detect base64 image data patterns
        base64_pattern = r'[A-Za-z0-9+/]{500,}={0,2}'
        matches = list(re.finditer(base64_pattern, text))
        
        if not matches:
            return text
        
        optimized_text = text
        offset = 0
        
        for match in matches:
            base64_data = match.group()
            
            # Calculate image hash for reference
            image_hash = hashlib.md5(base64_data.encode()).hexdigest()[:16]
            
            # Extract file path info if present
            file_marker_pattern = r'\[FILE_(?:SOURCE|SAVED):([^\]]+)\]'
            file_match = re.search(file_marker_pattern, base64_data)
            file_info = f"|{file_match.group(1)}" if file_match else ""
            
            # Estimate size
            estimated_size_kb = len(base64_data) * 3 // 4 // 1024
            
            # Create compact reference
            reference_text = f"[IMAGE_DATA_REF:{image_hash}|{estimated_size_kb}KB{file_info}]"
            
            # Calculate position in adjusted text
            start_pos = match.start() + offset
            end_pos = match.end() + offset
            
            # Replace base64 data with reference
            optimized_text = (optimized_text[:start_pos] + 
                            reference_text + 
                            optimized_text[end_pos:])
            
            # Update offset
            offset += len(reference_text) - len(base64_data)
        
        return optimized_text

    def _display_llm_statistics(self, messages: List[Dict[str, Any]], response_content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Display LLM input/output statistics including token count and character count.
        
        Args:
            messages: Input messages sent to LLM
            response_content: Response content from LLM
            tool_calls: Tool calls from LLM response (optional)
        """
        try:
            # Calculate input statistics
            input_text = ""
            for message in messages:
                role = message.get("role", "")
                content = message.get("content", "")
                input_text += f"[{role}] {content}\n"
            
            # Detect if input contains images (base64 data)
            import re
            has_images = bool(re.search(r'[A-Za-z0-9+/]{100,}={0,2}', input_text))
            
            # Estimate token counts for response content, including image tokens
            input_tokens_est = estimate_token_count(input_text, has_images=has_images, model=self.model)
            output_tokens_est = estimate_token_count(response_content, has_images=False, model=self.model)
            
            # Estimate token counts for tool calls if present
            tool_calls_tokens = 0
            if tool_calls:
                tool_calls_text = self._format_tool_calls_for_token_estimation(tool_calls)
                tool_calls_tokens = estimate_token_count(tool_calls_text)
            
            # Total output tokens including tool calls
            total_output_tokens = output_tokens_est + tool_calls_tokens
            
            # Calculate cache-related statistics
            cache_stats = analyze_cache_potential(messages, self.previous_messages)
            
            # Display simplified statistics in one line
            cached_tokens = cache_stats['estimated_cache_tokens']
            new_input_tokens = cache_stats['new_tokens']
            
            print_current("")
            if tool_calls_tokens > 0:
                print_current(f"📊 Input history (cached) tokens: {cached_tokens:,}, Input new tokens: {new_input_tokens:,}, Output tokens: {total_output_tokens:,} (content: {output_tokens_est:,}, tool calls: {tool_calls_tokens:,})")
            else:
                print_current(f"📊 Input history (cached) tokens: {cached_tokens:,}, Input new tokens: {new_input_tokens:,}, Output tokens: {total_output_tokens:,}")
            
        except Exception as e:
            print_current(f"⚠️ Statistics calculation failed: {e}")

    def _format_tool_calls_for_token_estimation(self, tool_calls: List[Dict[str, Any]]) -> str:
        """
        Format tool calls into text for token estimation.
        
        Args:
            tool_calls: List of tool calls
            
        Returns:
            Formatted text representation of tool calls
        """
        if not tool_calls:
            return ""
        
        formatted_parts = []
        for tool_call in tool_calls:
            # Handle different tool call formats
            if isinstance(tool_call, dict):
                # Extract tool name
                tool_name = ""
                if "name" in tool_call:
                    tool_name = tool_call["name"]
                elif "function" in tool_call and isinstance(tool_call["function"], dict):
                    tool_name = tool_call["function"].get("name", "")
                
                # Extract parameters/arguments
                params = {}
                if "arguments" in tool_call:
                    params = tool_call["arguments"]
                elif "input" in tool_call:
                    params = tool_call["input"]
                elif "function" in tool_call and isinstance(tool_call["function"], dict):
                    if "arguments" in tool_call["function"]:
                        try:
                            import json
                            params = json.loads(tool_call["function"]["arguments"]) if isinstance(tool_call["function"]["arguments"], str) else tool_call["function"]["arguments"]
                        except:
                            params = tool_call["function"]["arguments"]
                
                # Format tool call as text
                tool_text = f"Tool: {tool_name}\n"
                if params:
                    import json
                    try:
                        params_text = json.dumps(params, ensure_ascii=False)
                        tool_text += f"Parameters: {params_text}\n"
                    except:
                        tool_text += f"Parameters: {str(params)}\n"
                
                formatted_parts.append(tool_text)
        
        return "\n".join(formatted_parts)
    
    # Cache analysis functions moved to utils/cacheeff.py
    


    def _format_tool_results_for_llm(self, tool_results: List[Dict[str, Any]], include_base64_info: bool = False) -> str:
        """
        Format tool execution results for the LLM to understand.
        
        Args:
            tool_results: List of tool execution results
            
        Returns:
            Formatted message string for the LLM
        """
        if not tool_results:
            return "No tool results to report."
        
       
        truncation_length = get_truncation_length()
        
        message_parts = ["Tool execution results:\n"]
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get('tool_name', 'unknown')
            tool_params = result.get('tool_params', {})
            tool_result = result.get('tool_result', '')
            
            # Format the tool result section
            message_parts.append(f"## Tool {i}: {tool_name}")
            
            # Add parameters if meaningful
            if tool_params:
                key_params = []
                for key, value in tool_params.items():
                    if key in ['target_file', 'query', 'command', 'relative_workspace_path', 'search_term', 'instructions']:
                        # Truncate long values for readability
                        if isinstance(value, str) and len(value) > truncation_length:
                            value = value[:truncation_length] + "..."
                        key_params.append(f"{key}={value}")
                if key_params:
                    message_parts.append(f"**Parameters:** {', '.join(key_params)}")
            
            # Check if this is a read_file operation with should_read_entire_file=true
            is_read_entire_file = (tool_name == 'read_file' and 
                                 tool_params.get('should_read_entire_file', False) is True)
            
            # Check if this is a get_sensor_data operation (should not truncate image data)
            is_sensor_data = (tool_name == 'get_sensor_data')
            
            # Format the result
            message_parts.append("**Result:**")
            if isinstance(tool_result, dict):
                if tool_result.get('success') is not None:
                    # Structured result format
                    status = "✅ Success" if tool_result.get('success') else "❌ Failed"
                    message_parts.append(status)
                    
                    for key, value in tool_result.items():
                        if key not in ['status', 'command', 'working_directory']:
                            # For read_entire_file operations, don't truncate content but show truncation info
                            if is_read_entire_file and key == 'content':
                                # Check if the file was truncated
                                if tool_result.get('truncated', False):
                                    total_lines = tool_result.get('total_lines', 'unknown')
                                    lines_shown = tool_result.get('lines_shown', 'unknown')
                                    message_parts.append(f"- 📄 **FILE TRUNCATED**: Showing lines 1-{lines_shown} of {total_lines} total lines")
                                    message_parts.append(f"- ⚠️  **IMPORTANT**: The file has {total_lines - lines_shown if isinstance(total_lines, int) and isinstance(lines_shown, int) else 'additional'} lines that are not shown.")
                                    message_parts.append(f"- {key} (first {lines_shown} lines): {value}")
                                    if tool_result.get('after_summary'):
                                        message_parts.append(f"- **Truncation note**: {tool_result.get('after_summary')}")
                                else:
                                    # Complete file
                                    total_lines = tool_result.get('total_lines', 'unknown')
                                    message_parts.append(f"- 📄 **COMPLETE FILE**: Showing all {total_lines} lines")
                                    message_parts.append(f"- {key}: {value}")
                                print_current(f"📄 Full file content passed to LLM, length: {len(value) if isinstance(value, str) else 'N/A'} characters")
                            # For get_sensor_data operations, show a summary instead of full base64 to avoid overwhelming LLM
                            elif is_sensor_data and key == 'data':
                                if isinstance(value, str) and len(value) > 1000:
                                    # Show base64 data summary (only first 50 characters for terminal display)
                                    data_preview = value[:50] + "..." if len(value) > 50 else value
                                    message_parts.append(f"- {key}: [BASE64_DATA] {data_preview} [Total length: {len(value)} characters]")
                                    print_current(f"📸 Base64 data summary passed to LLM, original length: {len(value)} characters")
                                else:
                                    message_parts.append(f"- {key}: {value}")
                                    print_current(f"📸 Full sensor data passed to LLM, length: {len(value) if isinstance(value, str) else 'N/A'} characters")
                            elif isinstance(value, str) and len(value) > truncation_length:
                                # Truncate very long content for other operations
                                value = value[:truncation_length] + f"... [Content truncated, total length: {len(value)} characters]"
                                message_parts.append(f"- {key}: {value}")
                            else:
                                message_parts.append(f"- {key}: {value}")
                else:
                    # Fallback formatting
                    formatted_result = self._format_dict_as_text(tool_result)
                    # For read_entire_file and get_sensor_data operations, don't truncate
                    if is_read_entire_file or is_sensor_data:
                        message_parts.append(formatted_result)
                        if is_read_entire_file:
                            print_current(f"📄 Full file content formatted and passed to LLM")
                        else:
                            print_current(f"📸 Full sensor data formatted and passed to LLM")
                    elif len(formatted_result) > truncation_length:
                        formatted_result = formatted_result[:truncation_length] + "... [Content truncated]"
                        message_parts.append(formatted_result)
                    else:
                        message_parts.append(formatted_result)
            else:
                # Handle non-dict results
                result_str = str(tool_result)
                # For read_entire_file and get_sensor_data operations, don't truncate
                if is_read_entire_file or is_sensor_data:
                    message_parts.append(result_str)
                    if is_sensor_data:
                        print_current(f"📸 Full sensor data (non-dict) passed to LLM, length: {len(result_str)} characters")
                elif len(result_str) > truncation_length:
                    result_str = result_str[:truncation_length] + "... [Content truncated]"
                    message_parts.append(result_str)
                else:
                    message_parts.append(result_str)
            
            # Add separator between tools
            if i < len(tool_results):
                message_parts.append("")  # Empty line for separation
        
        # 🔧 NEW: Add base64 data detection information
        if include_base64_info:
            message_parts.append("")
            message_parts.append("## Base64 Data Status")
            message_parts.append("✅ Base64 encoded image data has been successfully acquired in this round.")
        
        return '\n'.join(message_parts)
    
    def _format_tool_results_with_vision(self, tool_results: List[Dict[str, Any]], vision_images: List[Dict[str, Any]]) -> Any:
        """
        Format tool results that contain vision data for LLM.
        Returns the proper format for vision-capable models.
        
        Args:
            tool_results: List of tool execution results
            vision_images: List of vision image data
            
        Returns:
            Properly formatted content for vision models (content array format)
        """
        truncation_length = get_truncation_length()
        
        # Build text content first
        message_parts = ["Tool execution results:\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get('tool_name', 'unknown')
            tool_params = result.get('tool_params', {})
            tool_result = result.get('tool_result', '')
            
            # Format the tool result section
            message_parts.append(f"## Tool {i}: {tool_name}")
            
            # Add parameters if meaningful
            if tool_params:
                key_params = []
                for key, value in tool_params.items():
                    if key in ['target_file', 'query', 'command', 'relative_workspace_path', 'search_term', 'instructions']:
                        # Truncate long values for readability
                        if isinstance(value, str) and len(value) > truncation_length:
                            value = value[:truncation_length] + "..."
                        key_params.append(f"{key}={value}")
                if key_params:
                    message_parts.append(f"**Parameters:** {', '.join(key_params)}")
            
            # Format the result
            message_parts.append("**Result:**")
            if isinstance(tool_result, dict):
                if tool_result.get('success') is not None:
                    # Structured result format
                    status = "✅ Success" if tool_result.get('success') else "❌ Failed"
                    message_parts.append(status)
                    
                    for key, value in tool_result.items():
                        # For image data in get_sensor_data, show metadata but reference image below
                        if (tool_name == 'get_sensor_data' and key == 'data' and 
                            any(img['tool_index'] == i for img in vision_images)):
                            message_parts.append(f"- {key}: [IMAGE DATA - See image below]")
                            print_current(f"📸 Image data formatted for vision API, tool {i}")
                        elif key not in ['status', 'command', 'working_directory']:
                            if isinstance(value, str) and len(value) > truncation_length:
                                # Truncate very long content for other operations
                                value = value[:truncation_length] + f"... [Content truncated, total length: {len(value)} characters]"
                                message_parts.append(f"- {key}: {value}")
                            else:
                                message_parts.append(f"- {key}: {value}")
            
            # Add separator between tools
            if i < len(tool_results):
                message_parts.append("")  # Empty line for separation
        
        # Build content array with text and images
        text_content = '\n'.join(message_parts)
        
        # Create content array format for vision models
        content_parts = []
        
        # Add text part
        content_parts.append({
            "type": "text",
            "text": text_content
        })
        
        # Add image parts
        for img_data in vision_images:
            if self.is_claude:
                # Claude format
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img_data['mime_type'],
                        "data": img_data['data']
                    }
                })
            else:
                # OpenAI format
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img_data['mime_type']};base64,{img_data['data']}"
                    }
                })
        
        print_current(f"🖼️ Formatted {len(vision_images)} images for vision API ({self.model})")
        return content_parts


    

    









    

    

    

    




    def _format_search_result_for_terminal(self, data: Dict[str, Any], tool_name: str) -> str:
        """
        Format search results (codebase_search and web_search) for simplified terminal display.
        Only shows brief summary with limited characters to reduce terminal clutter.
        
        Args:
            data: Dictionary result from search tools
            tool_name: Name of the tool that generated this result
            
        Returns:
            Simplified formatted text string for terminal display
        """
        if not isinstance(data, dict):
            return str(data)
        
        lines = []
        
        # Handle error cases first
        if 'error' in data:
            return f"❌ {tool_name} failed: {data['error']}"
        
        # Handle codebase_search results
        if tool_name == 'codebase_search':
            query = data.get('query', 'unknown')
            results = data.get('results', [])
            total_results = len(results)
            
            lines.append(f"🔍 Code search for '{query}': Found {total_results} results")
            
            # Show all results (up to 10) with brief info
            for i, result in enumerate(results[:10], 1):
                if isinstance(result, dict):
                    file_path = result.get('file', 'unknown')
                    start_line = result.get('start_line', '')
                    # Show only first 100 characters of snippet
                    snippet = result.get('snippet', '')[:100].replace('\n', ' ').strip()
                    if len(result.get('snippet', '')) > 100:
                        snippet += "..."
                    
                    lines.append(f"  {i}. {file_path}:{start_line} - {snippet}")
            
            if total_results > 10:
                lines.append(f"  ... and {total_results - 10} more results")
            
            # Add repository stats briefly
            stats = data.get('repository_stats', {})
            if stats:
                lines.append(f"📊 Repository: {stats.get('total_files', 0)} files, {stats.get('total_segments', 0)} segments")
        
        # Handle web_search results
        elif tool_name == 'web_search':
            search_term = data.get('search_term', 'unknown')
            results = data.get('results', [])
            
            # Get total results count from various possible fields
            total_results = data.get('total_results')  # First try the direct field
            if total_results is None:
                # Handle cases where results were replaced with summary
                if data.get('detailed_results_replaced_with_summary'):
                    total_results = data.get('total_results_processed', 0)
                    simplified_results = data.get('simplified_results', [])
                    # Use simplified results for display if original results were removed
                    if not results and simplified_results:
                        results = simplified_results
                else:
                    total_results = len(results)
            
            lines.append(f"🌐 Web search for '{search_term}': Found {total_results} results")
            
            # Show only first 3 results with very brief info
            for i, result in enumerate(results[:3], 1):
                if isinstance(result, dict):
                    title = result.get('title', 'No Title')[:80]  # Limit title length
                    if len(result.get('title', '')) > 80:
                        title += "..."
                    
                    # Show brief snippet or content summary
                    content_preview = ""
                    if result.get('snippet'):
                        content_preview = result['snippet'][:100].replace('\n', ' ').strip()
                    elif result.get('content_summary'):
                        content_preview = result['content_summary'][:100].replace('\n', ' ').strip()
                    elif result.get('content'):
                        content_preview = result['content'][:100].replace('\n', ' ').strip()
                    
                    if content_preview and len(content_preview) >= 100:
                        content_preview += "..."
                    
                    lines.append(f"  {i}. {title}")
                    if content_preview:
                        lines.append(f"     {content_preview}")
            
            if total_results > 3:
                lines.append(f"  ... and {total_results - 3} more results")
            
            # Add metadata briefly
            if data.get('content_fetched'):
                lines.append(f"📄 Content fetched: {data['content_fetched']}")
        
        # For other tools or unrecognized search results, fall back to original formatting
        else:
            return self._format_dict_as_text(data, for_terminal_display=True)
        
        return '\n'.join(lines)



    def _convert_tools_to_standard_format(self, provider="openai"):
        """
        Convert current tool_map to standard tool calling format.
        
        Args:
            provider: "openai" or "anthropic"
            
        Returns:
            List of tools in standard format
        """
        standard_tools = []
        
        # Load tool definitions from JSON file
        tool_definitions = self._load_tool_definitions_from_file()
        
        # Get tool source mapping
        tool_source_map = getattr(self, 'tool_source_map', {})
        
        # Convert to standard format based on provider
        for tool_name in self.tool_map.keys():
            tool_source = tool_source_map.get(tool_name, 'regular')
            
            # Handle cli-mcp tools
            if tool_source == 'cli_mcp':
                if self.cli_mcp_client and self.cli_mcp_initialized:
                    try:
                        # Use tool name directly (no prefix for cli-mcp tools now)
                        cli_mcp_tool_def = self.cli_mcp_client.get_tool_definition(tool_name)
                        if cli_mcp_tool_def:
                            if provider == "openai":
                                # OpenAI format for cli-mcp tools
                                standard_tool = {
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,  # Use original name (no prefix)
                                        "description": cli_mcp_tool_def.get("description", f"cli-mcp工具: {tool_name}"),
                                        "parameters": cli_mcp_tool_def.get("input_schema", {
                                            "type": "object",
                                            "properties": {},
                                            "required": []
                                        })
                                    }
                                }
                            elif provider == "anthropic":
                                # Anthropic format for cli-mcp tools
                                standard_tool = {
                                    "name": tool_name,  # Use original name (no prefix)
                                    "description": cli_mcp_tool_def.get("description", f"cli-mcp工具: {tool_name}"),
                                    "input_schema": cli_mcp_tool_def.get("input_schema", {
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    })
                                }
                            
                            standard_tools.append(standard_tool)
                    except Exception as e:
                        print_current(f"⚠️ 无法获取cli-mcp工具 {tool_name} 的定义: {e}")
            
            # Handle direct MCP tools (SSE)
            elif tool_source == 'direct_mcp':
                if self.direct_mcp_client and self.direct_mcp_initialized:
                    try:
                        # Use tool name directly (no prefix for SSE tools)
                        direct_mcp_tool_def = self.direct_mcp_client.get_tool_definition(tool_name)
                        if direct_mcp_tool_def:
                            if provider == "openai":
                                # OpenAI format for direct MCP tools
                                standard_tool = {
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,  # No prefix for SSE tools
                                        "description": direct_mcp_tool_def.get("description", f"SSE MCP tools: {tool_name}"),
                                        "parameters": direct_mcp_tool_def.get("inputSchema", direct_mcp_tool_def.get("input_schema", {
                                            "type": "object",
                                            "properties": {},
                                            "required": []
                                        }))
                                    }
                                }
                            elif provider == "anthropic":
                                # Anthropic format for direct MCP tools
                                standard_tool = {
                                    "name": tool_name,  # No prefix for SSE tools
                                    "description": direct_mcp_tool_def.get("description", f"SSE MCP tools: {tool_name}"),
                                    "input_schema": direct_mcp_tool_def.get("inputSchema", direct_mcp_tool_def.get("input_schema", {
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    }))
                                }
                            
                            standard_tools.append(standard_tool)
                    except Exception as e:
                        print_current(f"⚠️ Failed to get SSE MCP tool {tool_name} definition: {e}")
            
            # Handle regular tools from JSON definitions
            elif tool_name in tool_definitions:
                tool_def = tool_definitions[tool_name]
                
                if provider == "openai":
                    # OpenAI format
                    standard_tool = {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": tool_def["description"],
                            "parameters": tool_def["parameters"]
                        }
                    }
                elif provider == "anthropic":
                    # Anthropic format (uses input_schema instead of parameters)
                    standard_tool = {
                        "name": tool_name,
                        "description": tool_def["description"],
                        "input_schema": tool_def["parameters"]
                    }
                
                standard_tools.append(standard_tool)
 
        
        return standard_tools

    def _call_llm_with_standard_tools(self, messages, user_message, system_message):
        """
        Call LLM with either standard tool calling format or chat-based tool calling.
        
        Args:
            messages: Message history for the LLM
            user_message: Current user message
            system_message: System message
            
        Returns:
            Tuple of (content, tool_calls)
        """
        if self.use_chat_based_tools:
            return self._call_llm_with_chat_based_tools(messages, user_message, system_message)
        elif self.is_claude:
            return self._call_claude_with_standard_tools(messages, user_message, system_message)
        else:
            return self._call_openai_with_standard_tools(messages, user_message, system_message)

    def _call_llm_with_chat_based_tools(self, messages, user_message, system_message):
        """
        Call LLM with chat-based tool calling (no standard tool calling format).
        Tools are described in the message and responses are parsed from content.
        
        Args:
            messages: Message history for the LLM
            user_message: Current user message
            system_message: System message
            
        Returns:
            Tuple of (content, tool_calls)
        """
        # Retry logic for retryable errors
        max_retries = 3
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (4 total attempts)
            try:
                if self.is_claude:
                    # Use Anthropic Claude API for chat-based tool calling
                    claude_messages = [{"role": "user", "content": user_message}]
                    
                    if self.streaming:
                        with streaming_context(show_start_message=True) as printer:
                            with self.client.messages.stream(
                                model=self.model,
                                max_tokens=self._get_max_tokens_for_model(self.model),
                                system=system_message,
                                messages=claude_messages,
                                temperature=0.7
                            ) as stream:
                                content = ""
                                for text in stream.text_stream:
                                    printer.write(text)
                                    content += text
                    else:
                        # print_current("🔄 LLM is thinking:")
                        response = self.client.messages.create(
                            model=self.model,
                            max_tokens=self._get_max_tokens_for_model(self.model),
                            system=system_message,
                            messages=claude_messages,
                            temperature=0.7
                        )
                        
                        content = ""
                        for content_block in response.content:
                            if content_block.type == "text":
                                content += content_block.text
                else:
                    # Use OpenAI API for chat-based tool calling
                    api_messages = [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ]
                    
                    if self.streaming:
                        with streaming_context(show_start_message=True) as printer:
                            response = self.client.chat.completions.create(
                                model=self.model,
                                messages=api_messages,
                                max_tokens=self._get_max_tokens_for_model(self.model),
                                temperature=0.7,
                                top_p=0.8,
                                stream=True
                            )
                            
                            content = ""
                            for chunk in response:
                                if chunk.choices and len(chunk.choices) > 0:
                                    delta = chunk.choices[0].delta
                                    if delta.content is not None:
                                        printer.write(delta.content)
                                        content += delta.content
                        
                    else:
                        # print_current("🔄 LLM is thinking:")
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=api_messages,
                            max_tokens=self._get_max_tokens_for_model(self.model),
                            temperature=0.7,
                            top_p=0.8
                        )
                        
                        content = response.choices[0].message.content or ""
                
                # Parse tool calls from the response content
                tool_calls = self.parse_tool_calls(content)
                
                # Convert tool calls to standard format for compatibility
                standardized_tool_calls = []
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict) and "name" in tool_call and "arguments" in tool_call:
                        standardized_tool_calls.append({
                            "name": tool_call["name"],
                            "input": tool_call["arguments"]  # Use "input" format like Anthropic
                        })
                
                return content, standardized_tool_calls
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a retryable error
                retryable_errors = [
                    'overloaded', 'rate limit', 'too many requests', 
                    'service unavailable', 'timeout', 'temporary failure',
                    'server error', '429', '503', '502', '500'
                ]
                
                # Find which error keyword matched
                matched_error_keyword = None
                for error_keyword in retryable_errors:
                    if error_keyword in error_str:
                        matched_error_keyword = error_keyword
                        break
                
                is_retryable = matched_error_keyword is not None
                
                if is_retryable and attempt < max_retries:
                    # Calculate retry delay with exponential backoff
                    retry_delay = min(2 ** attempt, 10)  # 1, 2, 4 seconds, max 10
                    
                    api_type = "Claude API" if self.is_claude else "OpenAI API"
                    print_current(f"⚠️ {api_type} {matched_error_keyword} error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    print_current(f"💡 Consider switching to a different model or trying again later")
                    print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    print_current(f"🔄 Retrying in {retry_delay} seconds...")
                    
                    # Wait before retry
                    import time
                    time.sleep(retry_delay)
                    continue  # Retry the loop
                    
                else:
                    # Non-retryable error or max retries exceeded
                    api_type = "Claude API" if self.is_claude else "OpenAI API"
                    if is_retryable:
                        print_current(f"❌ {api_type} {matched_error_keyword} error: Maximum retries ({max_retries}) exceeded")
                        print_current(f"💡 Consider switching to a different model or trying again later")
                        print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    else:
                        print_current(f"❌ Chat-based LLM API call failed: {e}")
                    
                    raise e

    def _call_openai_with_standard_tools(self, messages, user_message, system_message):
        """
        Call OpenAI with standard tool calling format.
        """
        # Get standard tools for OpenAI
        tools = self._convert_tools_to_standard_format("openai")
        
        # Check if we have stored image data for vision API
        if hasattr(self, 'current_round_images') and self.current_round_images:
            print_current(f"🖼️ Using vision API with {len(self.current_round_images)} stored images")
            # Build vision message with stored images
            vision_user_message = self._build_vision_message(user_message if isinstance(user_message, str) else user_message.get("text", ""))
            api_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": vision_user_message}
            ]
            # Clear image data after using it for vision API to prevent reuse in subsequent rounds
            print_current("🧹 Clearing image data after vision API usage")
            self.current_round_images = []
        else:
            # Prepare messages - user_message can be string or content array
            api_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
        
        # Retry logic for retryable errors
        max_retries = 3
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (4 total attempts)
            try:
                if self.streaming:
                    with streaming_context(show_start_message=False) as printer:
                        # print_current("🔄 Starting streaming generation with standard tools...")
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=api_messages,
                            tools=tools,
                            max_tokens=self._get_max_tokens_for_model(self.model),
                            temperature=0.7,
                            top_p=0.8,
                            stream=True
                        )
                        
                        content = ""
                        tool_calls = []
                        current_tool_call = None
                        
                        for chunk in response:
                            if chunk.choices and len(chunk.choices) > 0:
                                delta = chunk.choices[0].delta
                                
                                # Handle content
                                if delta.content is not None:
                                    printer.write(delta.content)
                                    content += delta.content
                            
                            # Handle tool calls
                            if delta.tool_calls:
                                for tool_call_delta in delta.tool_calls:
                                    if tool_call_delta.index is not None:
                                        # Ensure we have enough tool calls in our list
                                        while len(tool_calls) <= tool_call_delta.index:
                                            tool_calls.append({
                                                "id": "",
                                                "type": "function",
                                                "function": {"name": "", "arguments": ""}
                                            })
                                        
                                        current_tool_call = tool_calls[tool_call_delta.index]
                                        
                                        if tool_call_delta.id:
                                            current_tool_call["id"] = tool_call_delta.id
                                        
                                        if tool_call_delta.function:
                                            if tool_call_delta.function.name:
                                                current_tool_call["function"]["name"] = tool_call_delta.function.name
                                            if tool_call_delta.function.arguments:
                                                current_tool_call["function"]["arguments"] += tool_call_delta.function.arguments
                    
                    # print_current("\n✅ Streaming completed")
                    return content, tool_calls
                else:
                    # print_current("🔄 Starting batch generation with standard tools...")
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=api_messages,
                        tools=tools,
                        max_tokens=self._get_max_tokens_for_model(self.model),
                        temperature=0.7,
                        top_p=0.8
                    )
                    
                    content = response.choices[0].message.content or ""
                    raw_tool_calls = response.choices[0].message.tool_calls or []
                    
                    # Convert OpenAI tool_calls objects to dictionary format
                    tool_calls = []
                    for tool_call in raw_tool_calls:
                        tool_calls.append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                    
                    # print_current("✅ Generation completed")
                    return content, tool_calls
                    
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a retryable error
                retryable_errors = [
                    'overloaded', 'rate limit', 'too many requests', 
                    'service unavailable', 'timeout', 'temporary failure',
                    'server error', '429', '503', '502', '500'
                ]
                
                # Find which error keyword matched
                matched_error_keyword = None
                for error_keyword in retryable_errors:
                    if error_keyword in error_str:
                        matched_error_keyword = error_keyword
                        break
                
                is_retryable = matched_error_keyword is not None
                
                if is_retryable and attempt < max_retries:
                    # Calculate retry delay with exponential backoff
                    retry_delay = min(2 ** attempt, 10)  # 1, 2, 4 seconds, max 10
                    
                    print_current(f"⚠️ OpenAI API {matched_error_keyword} error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    print_current(f"💡 Consider switching to a different model or trying again later")
                    print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    print_current(f"🔄 Retrying in {retry_delay} seconds...")
                    
                    # Wait before retry
                    import time
                    time.sleep(retry_delay)
                    continue  # Retry the loop
                    
                else:
                    # Non-retryable error or max retries exceeded
                    if is_retryable:
                        print_current(f"❌ OpenAI API {matched_error_keyword} error: Maximum retries ({max_retries}) exceeded")
                        print_current(f"💡 Consider switching to a different model or trying again later")
                        print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    else:
                        print_current(f"❌ OpenAI API call failed: {e}")
                    
                    raise e

    def _call_claude_with_standard_tools(self, messages, user_message, system_message):
        """
        Call Claude with standard tool calling format.
        """
        # Get standard tools for Anthropic
        tools = self._convert_tools_to_standard_format("anthropic")
        
        # Check if we have stored image data for vision API
        if hasattr(self, 'current_round_images') and self.current_round_images:
            print_current(f"🖼️ Using vision API with {len(self.current_round_images)} stored images")
            # Build vision message with stored images
            vision_user_message = self._build_vision_message(user_message if isinstance(user_message, str) else user_message.get("text", ""))
            claude_messages = [{"role": "user", "content": vision_user_message}]
            # Clear image data after using it for vision API to prevent reuse in subsequent rounds
            print_current("🧹 Clearing image data after vision API usage")
            self.current_round_images = []
        else:
            # Prepare messages for Claude - user_message can be string or content array
            claude_messages = [{"role": "user", "content": user_message}]
        
        # Retry logic for retryable errors
        max_retries = 3
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (4 total attempts)
            try:
                if self.streaming:
                    with streaming_context(show_start_message=True) as printer:
                        with self.client.messages.stream(
                            model=self.model,
                            max_tokens=self._get_max_tokens_for_model(self.model),
                            system=system_message,
                            messages=claude_messages,
                            tools=tools,
                            temperature=0.7
                        ) as stream:
                            content = ""
                            tool_calls = []
                            
                            for text in stream.text_stream:
                                printer.write(text)
                                content += text
                        
                        # Get final message to extract tool use blocks
                        final_message = stream.get_final_message()
                        
                        # Extract tool use blocks
                        for content_block in final_message.content:
                            if content_block.type == "tool_use":
                                tool_calls.append({
                                    "id": content_block.id,
                                    "name": content_block.name,
                                    "input": content_block.input
                                })
                    
                    return content, tool_calls
                else:
                    # print_current("🔄 LLM is thinking: ")
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=self._get_max_tokens_for_model(self.model),
                        system=system_message,
                        messages=claude_messages,
                        tools=tools,
                        temperature=0.7
                    )
                    
                    content = ""
                    tool_calls = []
                    
                    # Extract content and tool use blocks
                    for content_block in response.content:
                        if content_block.type == "text":
                            content += content_block.text
                        elif content_block.type == "tool_use":
                            tool_calls.append({
                                "id": content_block.id,
                                "name": content_block.name,
                                "input": content_block.input
                            })
                    
                    return content, tool_calls
                    
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a retryable error
                retryable_errors = [
                    'overloaded', 'rate limit', 'too many requests', 
                    'service unavailable', 'timeout', 'temporary failure',
                    'server error', '429', '503', '502', '500'
                ]
                
                # Find which error keyword matched
                matched_error_keyword = None
                for error_keyword in retryable_errors:
                    if error_keyword in error_str:
                        matched_error_keyword = error_keyword
                        break
                
                is_retryable = matched_error_keyword is not None
                
                if is_retryable and attempt < max_retries:
                    # Calculate retry delay with exponential backoff
                    retry_delay = min(2 ** attempt, 10)  # 1, 2, 4 seconds, max 10
                    
                    print_current(f"⚠️ Claude API {matched_error_keyword} error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    print_current(f"💡 Consider switching to a different model or trying again later")
                    print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    print_current(f"🔄 Retrying in {retry_delay} seconds...")
                    
                    # Wait before retry
                    import time
                    time.sleep(retry_delay)
                    continue  # Retry the loop
                    
                else:
                    # Non-retryable error or max retries exceeded
                    if is_retryable:
                        print_current(f"❌ Claude API {matched_error_keyword} error: Maximum retries ({max_retries}) exceeded")
                        print_current(f"💡 Consider switching to a different model or trying again later")
                        print_current(f"🔄 You can change the model in config.txt and restart AGIBot")
                    else:
                        print_current(f"❌ Claude API call failed: {e}")
                    
                    raise e

    def _get_tool_name_from_call(self, tool_call):
        """
        Extract tool name from different tool call formats.
        
        Args:
            tool_call: Tool call in various formats (OpenAI, Anthropic, or chat-based)
            
        Returns:
            Tool name string
        """
        if isinstance(tool_call, dict):
            # OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
            if "function" in tool_call and isinstance(tool_call["function"], dict):
                return tool_call["function"]["name"]
            # Anthropic/Chat-based format: {"id": "...", "name": "...", "input": {...}}
            elif "name" in tool_call:
                return tool_call["name"]
        else:
            # Handle OpenAI API raw object format as fallback
            if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name'):
                return tool_call.function.name
            elif hasattr(tool_call, 'name'):
                return tool_call.name
        
        raise ValueError(f"Unknown tool call format: {tool_call}")

    def _get_tool_params_from_call(self, tool_call):
        """
        Extract tool parameters from different tool call formats.
        
        Args:
            tool_call: Tool call in various formats (OpenAI, Anthropic, or chat-based)
            
        Returns:
            Tool parameters dictionary
        """
        if isinstance(tool_call, dict):
            # OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
            if "function" in tool_call and isinstance(tool_call["function"], dict):
                arguments = tool_call["function"]["arguments"]
                if isinstance(arguments, str):
                    import json
                    try:
                        return json.loads(arguments)
                    except json.JSONDecodeError as e:
                        # Try to fix common JSON issues
                        try:
                            fixed_arguments = fix_json_escapes(arguments)
                            parsed_result = json.loads(fixed_arguments)
                            return parsed_result
                        except json.JSONDecodeError as e2:
                            return {}
                return arguments
            # Anthropic/Chat-based format: {"id": "...", "name": "...", "input": {...}}
            elif "input" in tool_call:
                return tool_call["input"]
            # Legacy/Chat-based format: {"name": "...", "arguments": {...}}
            elif "arguments" in tool_call:
                return tool_call["arguments"]
        else:
            # Handle OpenAI API raw object format as fallback
            if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'arguments'):
                arguments = tool_call.function.arguments
                if isinstance(arguments, str):
                    import json
                    try:
                        return json.loads(arguments)
                    except json.JSONDecodeError as e:
                        # Try to fix common JSON issues
                        try:
                            fixed_arguments = fix_json_escapes(arguments)
                            parsed_result = json.loads(fixed_arguments)
                            return parsed_result
                        except json.JSONDecodeError as e2:
                            return {}
                return arguments
            elif hasattr(tool_call, 'input'):
                return tool_call.input
            elif hasattr(tool_call, 'arguments'):
                return tool_call.arguments
        
        raise ValueError(f"Unknown tool call format: {tool_call}")

    def _format_tool_calls_for_history(self, tool_calls: List[Dict[str, Any]]) -> str:
        """
        Format tool calls for inclusion in history records.
        
        Args:
            tool_calls: List of tool calls in standard format
            
        Returns:
            Formatted string representation of tool calls
        """
        if not tool_calls:
            return ""
        
        formatted_calls = []
        formatted_calls.append("**Tool Calls:**")
        
        for i, tool_call in enumerate(tool_calls, 1):
            tool_name = self._get_tool_name_from_call(tool_call)
            tool_params = self._get_tool_params_from_call(tool_call)
            
            formatted_calls.append(f"")
            formatted_calls.append(f"Tool {i}: {tool_name}")
            
            # Format parameters in a readable way
            if tool_params:
                formatted_calls.append("Parameters:")
                for key, value in tool_params.items():
                    # Show complete tool calls without truncation for better debugging
                    display_value = value
                    formatted_calls.append(f"  - {key}: {display_value}")
            else:
                formatted_calls.append("Parameters: None")
        
        return "\n".join(formatted_calls)

    def _load_tool_definitions_from_file(self, json_file_path: str = None) -> Dict[str, Any]:
        """
        Load tool definitions from JSON file.
        
        Args:
            json_file_path: Path to the JSON file containing tool definitions
            
        Returns:
            Dictionary containing tool definitions
        """
        try:
            import json
            
            # Load basic tool definitions
            tool_definitions = {}
            
            # Use default path if none provided
            if json_file_path is None:
                json_file_path = os.path.join(self.prompts_folder, "tool_prompt.json")
            
            # Try to load from the provided path
            if os.path.exists(json_file_path):
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    tool_definitions = json.load(f)
                    # print_current(f"✅ Loaded basic tool definitions from {json_file_path}")
            else:
                # print_current(f"⚠️  Tool definitions file not found: {json_file_path}")
                # No fallback definitions available
                tool_definitions = {}
            
            # Load memory tool definitions
            memory_tools_file = os.path.join(self.prompts_folder, "memory_tools.json")
            if os.path.exists(memory_tools_file):
                try:
                    with open(memory_tools_file, 'r', encoding='utf-8') as f:
                        memory_tools = json.load(f)
                        tool_definitions.update(memory_tools)
                        # print_current(f"✅ Loaded memory tool definitions from {memory_tools_file}")
                except Exception as e:
                    print_current(f"⚠️ Error loading memory tools: {e}")
            else:
                # print_current(f"⚠️ Memory tools file not found: {memory_tools_file}")
                pass
            
            # Check if multi-agent mode is enabled
            multi_agent_enabled = self._is_multi_agent_enabled()
            
            if multi_agent_enabled:
                # Load multi-agent tool definitions from custom prompts folder
                multiagent_file_path = os.path.join(self.prompts_folder, "multiagent_tool_prompt.json")
                if os.path.exists(multiagent_file_path):
                    with open(multiagent_file_path, 'r', encoding='utf-8') as f:
                        multiagent_tools = json.load(f)
                        tool_definitions.update(multiagent_tools)
                        # print_current(f"✅ Loaded multi-agent tool definitions from {multiagent_file_path}")
                else:
                    # print_current(f"⚠️  Multi-agent tool definitions file not found: {multiagent_file_path}")
                    pass
            else:
                # print_current("🔒 Multi-agent mode disabled - skipping multi-agent tool definitions")
                pass
            
            return tool_definitions
                
        except json.JSONDecodeError as e:
            print_current(f"❌ Error parsing JSON in {json_file_path}: {e}")
        except Exception as e:
            print_current(f"❌ Error loading tool definitions from {json_file_path}: {e}")
        
        # Return empty definitions if file loading fails
        # print_current("🔄 No fallback tool definitions available")
        return {}
    
    def _is_multi_agent_enabled(self) -> bool:
        """
        Check if multi-agent mode is enabled from configuration.
        
        Returns:
            True if multi-agent mode is enabled, False otherwise
        """
        try:
            from config_loader import get_config_value
            multi_agent_config = get_config_value("multi_agent", "True")
            
            # Handle different possible values
            if isinstance(multi_agent_config, str):
                return multi_agent_config.lower() in ["true", "1", "yes", "on"]
            elif isinstance(multi_agent_config, bool):
                return multi_agent_config
            else:
                return bool(multi_agent_config)
                
        except Exception as e:
            print_current(f"⚠️  Error checking multi-agent configuration: {e}")
            # Default to True if configuration cannot be read
            return True
    
    # Tool prompt generation function moved to utils/parse.py
    
    def _parse_image_tags(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Parse image tags in user input [img=path_to_image_file]
        
        Args:
            text: User input text
            
        Returns:
            Tuple of (processed_text, image_data_list)
            - processed_text: Text with image tags removed
            - image_data_list: List of image data, each containing {'path': str, 'data': str, 'mime_type': str}
        """
        # Regular expression to match image tags
        image_pattern = r'\[img=([^\]]+)\]'
        matches = re.findall(image_pattern, text)
        
        if not matches:
            return text, []
        
        # Process each image file
        image_data_list = []
        for image_path in matches:
            try:
                # Normalize path
                if not os.path.isabs(image_path):
                    # Relative path, relative to project root directory
                    full_path = os.path.join(self.project_root_dir, image_path)
                else:
                    full_path = image_path
                
                # Check if file exists
                if not os.path.exists(full_path):
                    print_current(f"⚠️ Image file does not exist: {full_path}")
                    continue
                
                # Read image file and encode as base64
                with open(full_path, 'rb') as f:
                    image_data = f.read()
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                
                # Get MIME type
                mime_type, _ = mimetypes.guess_type(full_path)
                if not mime_type or not mime_type.startswith('image/'):
                    print_current(f"⚠️ Unsupported image format: {full_path}")
                    continue
                
                image_data_list.append({
                    'path': image_path,
                    'full_path': full_path,
                    'data': base64_data,
                    'mime_type': mime_type
                })
                
                print_current(f"📸 Successfully loaded image: {image_path} ({mime_type})")
                
            except Exception as e:
                print_current(f"❌ Failed to load image {image_path}: {e}")
                continue
        
        # Remove image tags from text
        processed_text = re.sub(image_pattern, '', text).strip()
        
        return processed_text, image_data_list
    
    def _build_message_with_images(self, text_content: str, image_data_list: List[Dict[str, Any]], is_claude: bool = False) -> Any:
        """
        Build message content with images
        
        Args:
            text_content: Text content
            image_data_list: List of image data
            is_claude: Whether using Claude model
            
        Returns:
            Message content built according to model type
        """
        if not image_data_list:
            return text_content
        
        if is_claude:
            # Claude format: using content array
            content_parts = []
            
            # Add text part
            if text_content.strip():
                content_parts.append({
                    "type": "text",
                    "text": text_content
                })
            
            # Add image parts
            for image_data in image_data_list:
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_data['mime_type'],
                        "data": image_data['data']
                    }
                })
            
            return content_parts
        else:
            # OpenAI format: using content array
            content_parts = []
            
            # Add text part
            if text_content.strip():
                content_parts.append({
                    "type": "text",
                    "text": text_content
                })
            
            # Add image parts
            for image_data in image_data_list:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_data['mime_type']};base64,{image_data['data']}"
                    }
                })
            
            return content_parts
    
    def _build_new_user_message(self, user_prompt: str, task_history: List[Dict[str, Any]] = None, execution_round: int = 1) -> Any:
        """
        Build user message with new architecture:
        1. Pure user requirement (first)
        2. Rules and tools prompts  
        3. System environment info
        4. Workspace info
        5. History context (with intelligent summarization)
        6. Execution instructions (last)
        
        Args:
            user_prompt: Current user prompt (pure requirement)
            task_history: Previous task execution history
            execution_round: Current execution round number
            
        Returns:
            Structured user message (string or content array with images)
        """
        # Check and process image tags in first iteration
        processed_prompt = user_prompt
        image_data_list = []
        
        if execution_round == 1:
            processed_prompt, image_data_list = self._parse_image_tags(user_prompt)
        
        message_parts = []
        
        # 1. Pure user requirement (first)
        message_parts.append(processed_prompt)
        message_parts.append("")  # Empty line for separation
        
        # 2. Load and add rules and tools prompts
        prompt_components = self.load_user_prompt_components()
        
        if prompt_components['rules_and_tools']:
            message_parts.append("---")
            message_parts.append("")
            message_parts.append(prompt_components['rules_and_tools'])
            message_parts.append("")
        
        # 3. System environment information
        if prompt_components['system_environment']:
            message_parts.append("---")
            message_parts.append("")
            message_parts.append(prompt_components['system_environment'])
            message_parts.append("")
        
        # 4. Workspace information
        if prompt_components['workspace_info']:
            message_parts.append("---")
            message_parts.append("")
            message_parts.append(prompt_components['workspace_info'])
            message_parts.append("")
        
        # 5. Add task history context if provided
        if task_history:
            message_parts.append("---")
            message_parts.append("")
            
            # Use task_history directly since image optimization is now handled after vision API analysis
            processed_history = task_history
            
            # Calculate total history length (consistent with upstream calculation)
            total_history_length = sum(len(str(record.get("prompt", ""))) + len(str(record.get("result", ""))) for record in processed_history)
            
            # Check if we need to summarize the history (simplified logic since summarization is now handled upstream)
            if hasattr(self, 'summary_history') and self.summary_history and hasattr(self, 'summary_trigger_length') and total_history_length > self.summary_trigger_length:
                print_system(f"📊 History length ({total_history_length} chars) exceeds trigger length ({self.summary_trigger_length} chars)")
                print_system("⚠️ History is very long. Using recent history subset to keep context manageable.")
                
                # Use recent history subset as fallback when history is still too long
                recent_history = self._get_recent_history_subset(processed_history, max_length=self.summary_trigger_length // 2)
                self._add_full_history_to_message(message_parts, recent_history)
                print_system(f"📋 Using recent history subset: {len(recent_history)} records instead of {len(processed_history)} records")
            else:
                # History is manageable, use processed history
                self._add_full_history_to_message(message_parts, processed_history)
        
        # 6. Execution instructions (last)
        message_parts.append("---")
        message_parts.append("")
        message_parts.append("## Execution Instructions:")
        message_parts.append(f"This is round {execution_round} of task execution. Please continue with the task based on the above context and requirements.")
        
        # Build final message
        combined_message = "\n".join(message_parts)
        
        # If there is image data, build message format with images
        if image_data_list:
            final_message = self._build_message_with_images(combined_message, image_data_list, self.is_claude)
            print_current(f"📸 First iteration contains {len(image_data_list)} images")
        else:
            final_message = combined_message
        
        if self.debug_mode:
            if task_history:
                pass
        
        return final_message

    def enhanced_tool_help(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Enhanced tool_help that supports both built-in tools and MCP tools.
        
        Args:
            tool_name: The tool name to get help for
            
        Returns:
            Dictionary containing comprehensive tool usage information
        """
        # Ignore additional parameters
        if kwargs:
            print_current(f"⚠️ Ignoring additional parameters: {list(kwargs.keys())}")
        
        # First check if it's a built-in tool
        try:
            builtin_help = self.tools.tool_help(tool_name)
            if 'error' not in builtin_help:
                builtin_help['tool_type'] = 'built-in'
                return builtin_help
        except Exception as e:
            print_current(f"⚠️ Error getting built-in tool help: {e}")
        
        # Check if it's an MCP tool
        mcp_tool_def = self._get_mcp_tool_definition(tool_name)
        if mcp_tool_def:
            help_info = {
                "tool_name": tool_name,
                "tool_type": mcp_tool_def.get("tool_type", "mcp"),
                "description": mcp_tool_def["description"],
                "parameters": mcp_tool_def["parameters"],
                "usage_example": self._generate_mcp_usage_example(tool_name, mcp_tool_def),
                "parameter_template": self._generate_parameter_template(mcp_tool_def["parameters"]),
                "notes": mcp_tool_def.get("notes", "This is an MCP (Model Context Protocol) tool."),
                "mcp_format_warning": "⚠️ MCP tools typically use camelCase parameter format (e.g. entityType) rather than snake_case (e.g. entity_type). Please refer to the usage_example for the correct format."
            }
            
            return help_info
        
        # Tool not found - get all available tools including MCP tools
        all_tools = self._get_all_available_tools()
        available_tools = list(all_tools.keys())
        
        return {
            "error": f"Tool '{tool_name}' not found",
            "available_tools": available_tools,
            "all_tools_with_descriptions": all_tools,
            "message": f"Available tools are: {', '.join(available_tools)}",
            "suggestion": "Use list_available_tools() to see all available tools with descriptions"
        }

    def _get_mcp_tool_definition(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get MCP tool definition from MCP clients"""
        try:
            # Check if it's a cli-mcp tool
            if hasattr(self, 'cli_mcp_client') and self.cli_mcp_client and self.cli_mcp_initialized:
                cli_mcp_tools = self.cli_mcp_client.get_available_tools()
                if tool_name in cli_mcp_tools:
                    tool_def = self.cli_mcp_client.get_tool_definition(tool_name)
                    if tool_def:
                        return {
                            "description": tool_def.get("description", f"cli-mcp tool: {tool_name}"),
                            "parameters": tool_def.get("input_schema", {}),
                            "notes": f"MCP工具 (cli-mcp): {tool_name}. 请注意使用正确的参数格式（通常为camelCase）。",
                            "tool_type": "cli-mcp"
                        }
            
            # Check if it's a direct MCP tool
            if hasattr(self, 'direct_mcp_client') and self.direct_mcp_client and self.direct_mcp_initialized:
                direct_mcp_tools = self.direct_mcp_client.get_available_tools()
                if tool_name in direct_mcp_tools:
                    tool_def = self.direct_mcp_client.get_tool_definition(tool_name)
                    if tool_def:
                        return {
                            "description": tool_def.get("description", f"SSE MCP tool: {tool_name}"),
                            "parameters": tool_def.get("inputSchema", tool_def.get("input_schema", {})),
                            "notes": f"MCP tool (SSE): {tool_name}. This is an MCP tool connected via SSE protocol.",
                            "tool_type": "direct-mcp"
                        }
            
        except Exception as e:
            print_current(f"⚠️ Error getting MCP tool definition: {e}")
        
        return None

    def _get_all_available_tools(self) -> Dict[str, str]:
        """Get all available tools including MCP tools"""
        all_tools = {}
        
        # Add built-in tools
        for tool_name in self.tool_map.keys():
            # Skip MCP tools here, we'll add them separately
            tool_source = getattr(self, 'tool_source_map', {}).get(tool_name, 'regular')
            if tool_source == 'regular':
                try:
                    help_info = self.tools.tool_help(tool_name)
                    if 'error' not in help_info:
                        description = help_info["description"]
                        first_sentence = description.split(".")[0] + "." if "." in description else description
                        if len(first_sentence) > 100:
                            first_sentence = first_sentence[:97] + "..."
                        all_tools[tool_name] = f"[Built-in] {first_sentence}"
                    else:
                        all_tools[tool_name] = f"[Built-in] {tool_name}"
                except:
                    all_tools[tool_name] = f"[Built-in] {tool_name}"
        
        # Add MCP tools
        try:
            # Add cli-mcp tools
            if hasattr(self, 'cli_mcp_client') and self.cli_mcp_client and self.cli_mcp_initialized:
                cli_mcp_tools = self.cli_mcp_client.get_available_tools()
                for tool_name in cli_mcp_tools:
                    try:
                        tool_def = self.cli_mcp_client.get_tool_definition(tool_name)
                        description = tool_def.get("description", f"cli-mcp tool: {tool_name}") if tool_def else f"cli-mcp tool: {tool_name}"
                        first_sentence = description.split(".")[0] + "." if "." in description else description
                        if len(first_sentence) > 100:
                            first_sentence = first_sentence[:97] + "..."
                        all_tools[tool_name] = f"[MCP/CLI] {first_sentence}"
                    except Exception as e:
                        all_tools[tool_name] = f"[MCP/CLI] {tool_name} (error getting definition)"
            
            # Add direct MCP tools
            if hasattr(self, 'direct_mcp_client') and self.direct_mcp_client and self.direct_mcp_initialized:
                direct_mcp_tools = self.direct_mcp_client.get_available_tools()
                for tool_name in direct_mcp_tools:
                    try:
                        tool_def = self.direct_mcp_client.get_tool_definition(tool_name)
                        description = tool_def.get("description", f"SSE MCP tool: {tool_name}") if tool_def else f"SSE MCP tool: {tool_name}"
                        first_sentence = description.split(".")[0] + "." if "." in description else description
                        if len(first_sentence) > 100:
                            first_sentence = first_sentence[:97] + "..."
                        all_tools[tool_name] = f"[MCP/SSE] {first_sentence}"
                    except Exception as e:
                        all_tools[tool_name] = f"[MCP/SSE] {tool_name} (error getting definition)"
        
        except Exception as e:
            print_current(f"⚠️ Error getting MCP tool list: {e}")
        
        return all_tools

    def _generate_mcp_usage_example(self, tool_name: str, tool_def: Dict[str, Any]) -> str:
        """Generate usage example for MCP tools"""
        parameters = tool_def.get("parameters", {})
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])
        
        # Build example arguments
        example_args = {}
        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "string")
            
            # Generate appropriate example values
            if param_type == "array":
                if "entities" in param_name.lower():
                    example_args[param_name] = [{
                        "name": "Example Entity",
                        "entityType": "Person", 
                        "observations": ["Relevant observation info"]
                    }]
                else:
                    example_args[param_name] = ["example1", "example2"]
            elif param_type == "boolean":
                example_args[param_name] = True
            elif param_type == "integer":
                example_args[param_name] = 1
            elif param_type == "object":
                if "parameters" in param_name.lower():
                    example_args[param_name] = {"query": "search keywords"}
                else:
                    example_args[param_name] = {"key": "value"}
            else:
                # String type
                if "query" in param_name.lower():
                    example_args[param_name] = "search keywords"
                elif "path" in param_name.lower() or "file" in param_name.lower():
                    example_args[param_name] = "/path/to/file.txt"
                elif "content" in param_name.lower():
                    example_args[param_name] = "file content"
                elif "name" in param_name.lower():
                    example_args[param_name] = "example name"
                elif "type" in param_name.lower():
                    example_args[param_name] = "Person"
                else:
                    example_args[param_name] = "example value"
        
        # Special handling for known MCP tools
        if tool_name == "create_entities":
            example_args = {
                "entities": [{
                    "name": "user",
                    "entityType": "Person",
                    "observations": ["likes eating ice pops"]
                }]
            }
        elif tool_name == "write_file" or "write" in tool_name.lower():
            example_args = {
                "path": "/home/user/example.txt",
                "content": "This is example file content\nwith multiple lines"
            }
        elif tool_name == "read_file" or "read" in tool_name.lower():
            example_args = {
                "path": "/home/user/example.txt"
            }
        elif "search" in tool_name.lower():
            example_args = {
                "query": "search keywords",
                "language": "en",
                "num_results": 10
            }
        
        import json
        example_json = json.dumps(example_args, ensure_ascii=False, indent=2)
        
        return f'''{{
  "name": "{tool_name}",
  "arguments": {example_json}
}}

📝 MCP Tool Call Format Notes:
- Parameter names typically use camelCase format (e.g. entityType, numResults)
- Avoid using snake_case format (e.g. entity_type, num_results)
- Ensure parameter types match the tool definition correctly'''

    def _generate_parameter_template(self, parameters: Dict[str, Any]) -> str:
        """Generate a parameter template showing how to call the tool."""
        template_lines = []
        properties = parameters.get("properties", {})
        required_params = parameters.get("required", [])
        
        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "string")
            description = param_info.get("description", "")
            is_required = param_name in required_params
            
            # Generate appropriate example values
            if param_type == "array":
                example_value = '["example1", "example2"]'
            elif param_type == "boolean":
                example_value = "true"
            elif param_type == "integer":
                example_value = "1"
            else:
                if "path" in param_name.lower() or "file" in param_name.lower():
                    example_value = "path/to/file.py"
                elif "command" in param_name.lower():
                    example_value = "ls -la"
                elif "query" in param_name.lower() or "search" in param_name.lower():
                    example_value = "search query"
                elif "url" in param_name.lower():
                    example_value = "https://example.com"
                elif "edit_mode" in param_name.lower():
                    example_value = '"replace_lines"'
                elif "start_line" in param_name.lower():
                    example_value = "10"
                elif "end_line" in param_name.lower():
                    example_value = "15"
                elif "position" in param_name.lower():
                    example_value = "15"
                else:
                    example_value = "value"
            
            required_marker = " (REQUIRED)" if is_required else " (OPTIONAL)"
            template_lines.append(f'"{param_name}": {example_value}  // {description}{required_marker}')
        
        return "{\n  " + ",\n  ".join(template_lines) + "\n}"

    def _extract_current_round_images(self, tool_results: List[Dict[str, Any]]) -> None:
        """
        Extract image data from current round tool results for next round vision API.
        
        Args:
            tool_results: List of tool execution results
        """
        # Only clear if we actually have new image data to process
        new_images = []
        
        for result in tool_results:
            tool_name = result.get('tool_name', '')
            tool_result = result.get('tool_result', {})
            
            # Check if this is get_sensor_data with image data
            if tool_name == 'get_sensor_data' and isinstance(tool_result, dict):
                data_field = tool_result.get('data', '')
                dataformat = tool_result.get('dataformat', '')
                
                # Check if it's image data
                if (isinstance(data_field, str) and 
                    len(data_field) > 1000 and  # Likely base64 data
                    'base64 encoded image/' in dataformat):
                    
                    # Clean the base64 data (remove any file markers)
                    import re
                    clean_base64 = re.sub(r'\[FILE_(?:SOURCE|SAVED):[^\]]+\]', '', data_field)
                    
                    # Extract MIME type from dataformat
                    if 'image/jpeg' in dataformat:
                        mime_type = 'image/jpeg'
                    elif 'image/png' in dataformat:
                        mime_type = 'image/png'
                    else:
                        mime_type = 'image/jpeg'  # default
                    
                    # Store image data for next round
                    new_images.append({
                        'data': clean_base64,
                        'mime_type': mime_type
                    })
                    
                    print_current(f"🖼️ Stored image data for next round vision API (MIME: {mime_type}, size: {len(clean_base64)} chars)")
        
        # Only update the array if we found new images
        if new_images:
            self.current_round_images = new_images
    
    def _build_vision_message(self, text_content: str) -> List[Dict[str, Any]]:
        """
        Build vision message content array from text and stored images.
        
        Args:
            text_content: Text content to include
            
        Returns:
            Content array for vision API
        """
        content_parts = []
        
        # Add text part
        content_parts.append({
            "type": "text",
            "text": text_content
        })
        
        # Add image parts
        for img_data in self.current_round_images:
            if self.is_claude:
                # Claude format
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img_data['mime_type'],
                        "data": img_data['data']
                    }
                })
            else:
                # OpenAI format
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img_data['mime_type']};base64,{img_data['data']}"
                    }
                })
        
        return content_parts
    
    def _perform_vision_analysis(self, vision_content: List[Dict[str, Any]], original_content: str) -> str:
        """
        Perform immediate vision analysis using the vision-capable model.
        
        Args:
            vision_content: Content array with text and images for vision API
            original_content: Original LLM response content
            
        Returns:
            Vision analysis result as string
        """
        try:
            # Prepare system prompt for vision analysis
            vision_system_prompt = "You are an AI assistant with vision capabilities. Analyze the images provided and give detailed descriptions of what you see."
            
            # Prepare messages for vision analysis
            vision_messages = [
                {"role": "system", "content": vision_system_prompt},
                {"role": "user", "content": vision_content}
            ]
            
            print_current("🔍 Performing vision analysis...")
            
            # Call LLM with vision data
            if self.is_claude:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self._get_max_tokens_for_model(self.model),
                    system=vision_system_prompt,
                    messages=[{"role": "user", "content": vision_content}],
                    temperature=0.7
                )
                
                vision_analysis = ""
                for content_block in response.content:
                    if content_block.type == "text":
                        vision_analysis += content_block.text
                        
            else:
                # OpenAI format
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=vision_messages,
                    max_tokens=self._get_max_tokens_for_model(self.model),
                    temperature=0.7,
                    top_p=0.8
                )
                
                vision_analysis = response.choices[0].message.content or ""
            
            print_current(f"✅ Vision analysis completed: {len(vision_analysis)} characters")
            return f"## Vision Analysis Results:\n\n{vision_analysis}"
            
        except Exception as e:
            print_current(f"❌ Vision analysis failed: {e}")
            # Fall back to text description
            text_content = ""
            for item in vision_content:
                if item.get("type") == "text":
                    text_content = item.get("text", "")
                    break
            return f"## Tool Results (Vision analysis failed):\n\n{text_content}"


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description='Execute a subtask using LLM with tools')
    parser.add_argument('prompt', nargs='?', help='The prompt for the subtask')
    parser.add_argument('--api-key', '-k', help='API key for the LLM service')
    parser.add_argument('--model', '-m', default="Qwen/Qwen3-30B-A3B", help='Model to use')
    parser.add_argument('--system-prompt', '-s', default="prompts.txt", help='System prompt file')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with detailed logging')
    parser.add_argument('--logs-dir', default="logs", help='Directory for saving debug logs')
    parser.add_argument('--workspace-dir', help='Working directory for code files and project output')
    parser.add_argument('--streaming', action='store_true', help='Enable streaming output mode')
    parser.add_argument('--no-streaming', action='store_true', help='Disable streaming output mode (force batch)')


    
    args = parser.parse_args()
    
    # Handle streaming configuration
    streaming = None
    if args.streaming and args.no_streaming:
        print_current("Warning: Both --streaming and --no-streaming specified, using config.txt default")
    elif args.streaming:
        streaming = True
    elif args.no_streaming:
        streaming = False
    # If neither specified, streaming=None will use config.txt value
    
    # Check if prompt is provided for normal execution
    if not args.prompt:
        parser.error("prompt is required")
    
    # Create executor
    executor = ToolExecutor(
        api_key=args.api_key, 
        model=args.model,
        workspace_dir=args.workspace_dir,
        debug_mode=args.debug,
        logs_dir=args.logs_dir,
        streaming=streaming
    )
    
    # Execute subtask
    result = executor.execute_subtask(args.prompt, args.system_prompt)
    
    print(result)

if __name__ == "__main__":
    main()