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

import datetime
from typing import Dict, Any

from .base_tools import BaseTools
from .code_search_tools import CodeSearchTools
from .file_system_tools import FileSystemTools
from .terminal_tools import TerminalTools
from .web_search_tools import WebSearchTools
from .help_tools import HelpTools

# Import plugin tools
try:
    import sys
    import os
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent_dir)
    from tools_plugin import PluginTools
    PLUGIN_TOOLS_AVAILABLE = True
    # print("🔌 Plugin tools loaded successfully")  # Moved warning display to main.py
except ImportError as e:
    PLUGIN_TOOLS_AVAILABLE = False
    # print(f"⚠️ Plugin tools not available: {e}")  # Moved warning display to main.py


if PLUGIN_TOOLS_AVAILABLE:
    class Tools(
        BaseTools,
        CodeSearchTools,
        FileSystemTools,
        TerminalTools,
        WebSearchTools,
        HelpTools,
        PluginTools
    ):
        def __init__(self, workspace_root: str = None, llm_api_key: str = None, llm_model: str = None, llm_api_base: str = None, enable_llm_filtering: bool = False, enable_summary: bool = True, out_dir: str = None):
            # Initialize all parent classes with workspace_root parameter
            BaseTools.__init__(self, workspace_root)
            CodeSearchTools.__init__(self)
            FileSystemTools.__init__(self)
            TerminalTools.__init__(self, workspace_root)  # Pass workspace_root to TerminalTools
            WebSearchTools.__init__(self, llm_api_key, llm_model, llm_api_base, enable_llm_filtering, enable_summary, out_dir)
            HelpTools.__init__(self)
            PluginTools.__init__(self, workspace_root)
else:
    class Tools(
        BaseTools,
        CodeSearchTools,
        FileSystemTools,
        TerminalTools,
        WebSearchTools,
        HelpTools
    ):
        def __init__(self, workspace_root: str = None, llm_api_key: str = None, llm_model: str = None, llm_api_base: str = None, enable_llm_filtering: bool = False, enable_summary: bool = True, out_dir: str = None):
            # Initialize all parent classes with workspace_root parameter
            BaseTools.__init__(self, workspace_root)
            CodeSearchTools.__init__(self)
            FileSystemTools.__init__(self)
            TerminalTools.__init__(self, workspace_root)  # Pass workspace_root to TerminalTools
            WebSearchTools.__init__(self, llm_api_key, llm_model, llm_api_base, enable_llm_filtering, enable_summary, out_dir)
            HelpTools.__init__(self)




if __name__ == "__main__":
    tools = Tools()
    print("Tool implementations ready. This module provides Python implementations for the tools mentioned in prompts.txt.")