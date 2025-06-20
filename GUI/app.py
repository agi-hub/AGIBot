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

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_socketio import SocketIO, emit
import os
import sys
import threading
from datetime import datetime
import shutil
import zipfile
from werkzeug.utils import secure_filename
import multiprocessing
import queue
import re
import signal
import subprocess

# Add parent directory to path to import config_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_loader import get_language, get_gui_default_data_directory

# Check current directory, switch to parent directory if in GUI directory
current_dir = os.getcwd()
current_dir_name = os.path.basename(current_dir)

if current_dir_name == 'GUI':
    parent_dir = os.path.dirname(current_dir)
    os.chdir(parent_dir)
    print(f"🔄 Detected startup in GUI directory, switched to parent directory: {parent_dir}")
else:
    print(f"📁 Current working directory: {current_dir}")

# Add parent directory to path to import main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Application name macro definition
APP_NAME = "AGI Bot"

from main import AGIBotMain

app = Flask(__name__)
app.config['SECRET_KEY'] = f'{APP_NAME.lower().replace(" ", "_")}_gui_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', 
                   ping_timeout=60, ping_interval=25)

# Internationalization text configuration
I18N_TEXTS = {
    'zh': {
        # Page title and basic information
        'page_title': f'{APP_NAME}',
        'app_title': f'{APP_NAME}',
        'app_subtitle': '',
        'chat_title': '执行日志',
        'connected': f'已连接到 {APP_NAME}',
        'reconnect_failed': '重连失败，请刷新页面',
        
        # Button text
        'execute_direct': '直接执行',
        'execute_plan': '计划模式', 
        'new_directory': '新建目录',
        'stop_task': '停止任务',
        'refresh': '刷新',
        'upload': '上传',
        'download': '下载',
        'rename': '重命名',
        'delete': '删除',
        'confirm': '确认',
        'cancel': '取消',
        
        # Button tooltips
        'direct_tooltip': '直接执行 - 不进行任务分解',
        'plan_tooltip': '计划模式 - 先分解任务再执行',
        'new_tooltip': '新建目录 - 创建新的工作目录',
        'refresh_tooltip': '刷新目录列表',
        'upload_tooltip': '上传文件到Workspace',
        'download_tooltip': '下载目录为ZIP（排除workspace_code_index）',
        'rename_tooltip': '重命名目录',
        'delete_tooltip': '删除目录',
        
        # Input boxes and placeholders
        'input_placeholder': '请输入您的需求...',
        'rename_placeholder': '请输入新的目录名称',
        
        # Modal titles
        'upload_title': '上传文件到Workspace',
        'rename_title': '重命名目录',
        'confirm_rename': '确认重命名',
        
        # Status messages
        'task_running': '任务正在运行中...',
        'no_task_running': '当前没有任务在运行',
        'task_stopped': '任务已被用户停止',
        'task_completed': '任务执行完成！',
        'task_completed_with_errors': '任务达到最大轮数，可能未完全完成',
        'task_failed': '任务执行失败',
        'directory_created': '已创建新工作目录',
        'directory_selected': '已选择目录',
        'directory_renamed': '目录重命名成功',
        'directory_deleted': '目录删除成功',
        'files_uploaded': '文件上传成功',
        'refresh_success': '目录列表已刷新',
        
        # Mode information
        'plan_mode_info': '🔄 启用计划模式：将先分解任务再执行',
        'direct_mode_info': '⚡ 直接执行模式：不进行任务分解',
        'new_mode_info': '新建目录模式 - 点击绿色按钮创建新工作目录，或选择现有目录',
        'selected_dir_info': '已选择目录',
        
        # Error messages
        'error_no_requirement': '请提供有效的需求',
        'error_task_running': '已有任务正在运行',
        'error_no_directory': '请先选择目录',
        'error_no_files': '请先选择文件',
        'error_delete_confirm': '确定要删除目录',
        'error_delete_warning': '此操作不可撤销，将永久删除该目录及其所有内容。',
        'error_rename_empty': '新名称不能为空',
        'error_rename_same': '新名称与原名称相同或包含无效字符',
        'error_directory_exists': '目标目录已存在',
        'error_directory_not_found': '目录不存在',
        'error_permission_denied': '权限不足',
        'error_file_too_large': '文件过大无法显示',
        'error_file_not_supported': '不支持预览此文件类型',
        
        # File operations
        'file_size': '文件大小',
        'download_file': '下载文件',
        'office_preview_note': 'Office文档预览',
        'office_download_note': '下载文件: 下载到本地使用Office软件打开',
        
        # Tool execution status
        'tool_running': '执行中',
        'tool_success': '成功',
        'tool_error': '错误',
        'function_calling': '调用中',
        
        # Others
        'deleting': '删除中...',
        'renaming': '重命名中...',
        'uploading': '上传中...',
        'loading': '加载中...',
        'system_message': '系统消息',
        'welcome_message': f'欢迎使用 {APP_NAME}！请在下方输入您的需求，系统将自动为您处理任务。',
        'workspace_title': '工作目录',
        'file_preview': '文件预览',
        'data_directory_info': '数据目录',
        'disconnected': '与服务器断开连接',
        'reconnected': '已重新连接到服务器',
        'drag_files': '拖拽文件到此处或点击选择文件',
        'upload_hint': '支持多文件上传，文件将保存到选定目录的workspace文件夹中',
        'select_files': '选择文件',
        
        # Additional bilingual text
        'new_messages': '条新消息',
        'auto_scroll': '自动滚动',
        'scroll_to_bottom': '滚动到底部',
        'plan_mode_suffix': ' (计划模式)',
        'continue_mode_info': '继续模式 - 将使用上次的工作目录',
        'create_or_select_directory': '请先点击绿色按钮创建新工作目录，或选择右侧的现有目录',
        'select_directory_first': '请先创建或选择一个工作目录',
        'current_name': '当前名称：',
        'new_name': '新名称：',
        'rename_info': '将使用您输入的名称作为目录名',
        'paused': '已暂停',
        'load_directory_failed': '加载目录失败',
        'network_error': '网络错误',
        'upload_network_error': '网络错误，上传失败',
        'rename_failed': '重命名失败',
        'rename_error': '重命名出错',
        'refresh_failed': '刷新失败',
        'attempt': '尝试',
        'create_directory_failed': '创建目录失败',
        'preview': '预览',
        'page_info': '第 {0} 页，共 {1} 页',
        'upload_to': '上传文件到',
        'workspace': '/workspace',
        'select_directory_error': '请先选择目录',
        'uploading_files': '正在上传 {0} 个文件...',
        'upload_progress': '上传进度: {0}%',
        'upload_failed_http': '上传失败: HTTP {0}',
        
        # Directory operations
        'directory_created_with_workspace': '已创建新工作目录: {0} (包含workspace子目录)',
        'directory_list_refreshed': '目录列表已刷新',
        'no_files_selected': '没有选择文件',
        'no_valid_files': '没有选择有效文件',
        'target_directory_not_exist': '目标目录不存在',
        'upload_success': '成功上传 {0} 个文件',
        'new_name_empty': '新名称不能为空',
        
        # Terminal input related
        'terminal_input_placeholder': '输入文本或命令...',
        'send_input': '发送',
        'send_password': '发送密码',
        'send_ctrl_c': 'Ctrl+C',
        'send_ctrl_d': 'Ctrl+D',
        'terminal_input_title': '终端输入',
        'terminal_input_help': '您可以向正在运行的程序发送输入、密码或控制命令',
        'password_mode': '密码模式',
        'text_mode': '文本模式',
    },
    'en': {
        # Page title and basic info
        'page_title': f'{APP_NAME}',
        'app_title': f'{APP_NAME}', 
        'app_subtitle': '',
        'chat_title': 'Execution Log',
        'connected': f'Connected to {APP_NAME}',
        'reconnect_failed': 'Reconnection failed, please refresh the page',
        
        # Button text
        'execute_direct': 'Execute',
        'execute_plan': 'Plan Mode',
        'new_directory': 'New Directory', 
        'stop_task': 'Stop Task',
        'refresh': 'Refresh',
        'upload': 'Upload',
        'download': 'Download',
        'rename': 'Rename',
        'delete': 'Delete',
        'confirm': 'Confirm',
        'cancel': 'Cancel',
        
        # Button tooltips
        'direct_tooltip': 'Direct execution - no task decomposition',
        'plan_tooltip': 'Plan mode - decompose tasks before execution',
        'new_tooltip': 'New directory - create new workspace',
        'refresh_tooltip': 'Refresh directory list',
        'upload_tooltip': 'Upload files to Workspace',
        'download_tooltip': 'Download directory as ZIP (excluding workspace_code_index)',
        'rename_tooltip': 'Rename directory',
        'delete_tooltip': 'Delete directory',
        
        # Input and placeholders
        'input_placeholder': 'Enter your requirements...',
        'rename_placeholder': 'Enter new directory name',
        
        # Modal titles
        'upload_title': 'Upload Files to Workspace',
        'rename_title': 'Rename Directory',
        'confirm_rename': 'Confirm Rename',
        
        # Status messages
        'task_running': 'Task is running...',
        'no_task_running': 'No task is currently running',
        'task_stopped': 'Task stopped by user',
        'task_completed': 'Task completed successfully!',
        'task_completed_with_errors': 'Task reached maximum rounds, may not be fully completed',
        'task_failed': 'Task execution failed',
        'directory_created': 'New workspace directory created',
        'directory_selected': 'Directory selected',
        'directory_renamed': 'Directory renamed successfully',
        'directory_deleted': 'Directory deleted successfully',
        'files_uploaded': 'Files uploaded successfully',
        'refresh_success': 'Directory list refreshed',
        
        # Mode info
        'plan_mode_info': '🔄 Plan mode enabled: Tasks will be decomposed before execution',
        'direct_mode_info': '⚡ Direct execution mode: No task decomposition',
        'new_mode_info': 'New directory mode - Click green button to create new workspace, or select existing directory',
        'selected_dir_info': 'Selected directory',
        
        # Error messages
        'error_no_requirement': 'Please provide a valid requirement',
        'error_task_running': 'A task is already running',
        'error_no_directory': 'Please select a directory first',
        'error_no_files': 'Please select files first',
        'error_delete_confirm': 'Are you sure you want to delete directory',
        'error_delete_warning': 'This operation cannot be undone and will permanently delete the directory and all its contents.',
        'error_rename_empty': 'New name cannot be empty',
        'error_rename_same': 'New name is the same as original or contains invalid characters',
        'error_directory_exists': 'Target directory already exists',
        'error_directory_not_found': 'Directory not found',
        'error_permission_denied': 'Permission denied',
        'error_file_too_large': 'File too large to display',
        'error_file_not_supported': 'File type not supported for preview',
        
        # File operations
        'file_size': 'File Size',
        'download_file': 'Download File',
        'office_preview_note': 'Office Document Preview',
        'office_download_note': 'Download File: Download to local and open with Office software',
        
        # Tool execution status
        'tool_running': 'Running',
        'tool_success': 'Success',
        'tool_error': 'Error',
        'function_calling': 'Calling',
        
        # Others
        'deleting': 'Deleting...',
        'renaming': 'Renaming...',
        'uploading': 'Uploading...',
        'loading': 'Loading...',
        'system_message': 'System Message',
        'welcome_message': f'Welcome to {APP_NAME}! Please enter your requirements below, and the system will automatically process tasks for you.',
        'workspace_title': 'Workspace',
        'file_preview': 'File Preview',
        'data_directory_info': 'Data Directory',
        'disconnected': 'Disconnected from server',
        'reconnected': 'Reconnected to server',
        'drag_files': 'Drag files here or click to select files',
        'upload_hint': 'Supports multiple file upload, files will be saved to the workspace folder of the selected directory',
        'select_files': 'Select Files',
        
        # Additional bilingual text
        'new_messages': 'new messages',
        'auto_scroll': 'Auto Scroll',
        'scroll_to_bottom': 'Scroll to Bottom',
        'plan_mode_suffix': ' (Plan Mode)',
        'continue_mode_info': 'Continue mode - Will use the previous workspace directory',
        'create_or_select_directory': 'Please click the green button to create a new workspace directory, or select an existing directory on the right',
        'select_directory_first': 'Please create or select a workspace directory first',
        'current_name': 'Current Name:',
        'new_name': 'New Name:',
        'rename_info': 'The name you enter will be used as the directory name',
        'paused': 'Paused',
        'load_directory_failed': 'Failed to load directories',
        'network_error': 'Network error',
        'upload_network_error': 'Network error, upload failed',
        'rename_failed': 'Rename failed',
        'rename_error': 'Rename error',
        'refresh_failed': 'Refresh failed',
        'attempt': 'attempt',
        'create_directory_failed': 'Failed to create directory',
        'preview': 'Preview',
        'page_info': 'Page {0} of {1}',
        'upload_to': 'Upload files to',
        'workspace': '/workspace',
        'select_directory_error': 'Please select a directory first',
        'uploading_files': 'Uploading {0} files...',
        'upload_progress': 'Upload progress: {0}%',
        'upload_failed_http': 'Upload failed: HTTP {0}',
        
        # Directory operations
        'directory_created_with_workspace': 'New workspace directory created: {0} (with workspace subdirectory)',
        'directory_list_refreshed': 'Directory list refreshed',
        'no_files_selected': 'No files selected',
        'no_valid_files': 'No valid files selected',
        'target_directory_not_exist': 'Target directory does not exist',
        'upload_success': 'Successfully uploaded {0} files',
        'new_name_empty': 'New name cannot be empty',
        
        # Terminal input related
        'terminal_input_placeholder': 'Enter text or command...',
        'send_input': 'Send',
        'send_password': 'Send Password',
        'send_ctrl_c': 'Ctrl+C',
        'send_ctrl_d': 'Ctrl+D',
        'terminal_input_title': 'Terminal Input',
        'terminal_input_help': 'You can send input, passwords or control commands to the running program',
        'password_mode': 'Password Mode',
        'text_mode': 'Text Mode',
    }
}

def get_i18n_texts():
    """Get internationalization text for current language"""
    current_lang = get_language()
    return I18N_TEXTS.get(current_lang, I18N_TEXTS['en'])

def execute_agibot_task_process_target(user_requirement, output_queue, input_queue, out_dir=None, continue_mode=False, plan_mode=False):
    # Get i18n texts for this process
    i18n = get_i18n_texts()
    """
    This function runs in a separate process.
    It cannot use the `socketio` object directly.
    It communicates back to the main process via the queue.
    """
    try:
        output_queue.put({'event': 'task_started', 'data': {'message': 'Task execution started...'}})
        
        if not out_dir:
            # Get GUI default data directory from config for new directories
            from config_loader import get_gui_default_data_directory
            config_data_dir = get_gui_default_data_directory()
            if config_data_dir:
                base_dir = config_data_dir
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(base_dir, f"output_{timestamp}")
        
        if continue_mode:
            output_queue.put({'event': 'output', 'data': {'message': f"Continuing with existing directory: {out_dir}", 'type': 'info'}})
        else:
            output_queue.put({'event': 'output', 'data': {'message': f"Creating output directory: {out_dir}", 'type': 'info'}})
        
        # Set parameters based on mode
        if plan_mode:
            output_queue.put({'event': 'output', 'data': {'message': f"Plan mode enabled: Using task decomposition (--todo)", 'type': 'info'}})
            single_task_mode = False  # Plan mode uses task decomposition
        else:
            output_queue.put({'event': 'output', 'data': {'message': f"Normal mode: Direct execution (single task)", 'type': 'info'}})
            single_task_mode = True   # Default mode executes directly
        
        agibot = AGIBotMain(
            out_dir=out_dir,
            debug_mode=False,
            detailed_summary=True,
            single_task_mode=single_task_mode,  # Set based on plan_mode
            interactive_mode=False,  # Disable interactive mode
            continue_mode=continue_mode
        )
        
        output_queue.put({'event': 'output', 'data': {'message': f"Initialized {APP_NAME} with output directory: {out_dir}", 'type': 'info'}})
        output_queue.put({'event': 'output', 'data': {'message': f"Starting task execution...", 'type': 'info'}})
        output_queue.put({'event': 'output', 'data': {'message': f"User requirement: {user_requirement}", 'type': 'user'}})
        
        class QueueSocketHandler:
            def __init__(self, q, socket_type='info'):
                self.q = q
                self.socket_type = socket_type
                self.buffer = ""
            
            def write(self, message):
                self.buffer += message
                if '\n' in self.buffer:
                    *lines, self.buffer = self.buffer.split('\n')
                    for line in lines:
                        if line.strip():
                            # Check if it's warning or progress info, if so display as normal info instead of error
                            line_lower = line.lower()
                            if ('warning' in line_lower or 
                                'progress' in line_lower or 
                                'processing files' in line_lower or
                                line.strip().startswith('Processing files:') or
                                'userwarning' in line_lower or
                                'warnings.warn' in line_lower):
                                message_type = 'info'
                            else:
                                message_type = self.socket_type
                            # Display warning and progress info as normal info
                            self.q.put({'event': 'output', 'data': {'message': line.strip(), 'type': message_type}})

            def flush(self):
                pass
            
            def final_flush(self):
                if self.buffer.strip():
                    # Check if it's warning or progress info, if so display as normal info instead of error
                    buffer_lower = self.buffer.lower()
                    if ('warning' in buffer_lower or 
                        'progress' in buffer_lower or 
                        'processing files' in buffer_lower or
                        self.buffer.strip().startswith('Processing files:') or
                        'userwarning' in buffer_lower or
                        'warnings.warn' in buffer_lower):
                        message_type = 'info'
                    else:
                        message_type = self.socket_type
                    # Display warning and progress info as normal info
                    self.q.put({'event': 'output', 'data': {'message': self.buffer.strip(), 'type': message_type}})
                    self.buffer = ""

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        stdout_handler = QueueSocketHandler(output_queue, 'info')
        stderr_handler = QueueSocketHandler(output_queue, 'error')

        try:
            sys.stdout = stdout_handler
            sys.stderr = stderr_handler
            
            success = agibot.run(user_requirement=user_requirement, loops=25)
            
            # Ensure important completion information is displayed
            workspace_dir = os.path.join(out_dir, "workspace")
            output_queue.put({'event': 'output', 'data': {'message': f"📁 All files saved at: {os.path.abspath(out_dir)}", 'type': 'success'}})
            
            # Extract directory name for GUI display (relative to GUI data directory)
            dir_name = os.path.basename(out_dir)
            
            if success:
                output_queue.put({'event': 'task_completed', 'data': {'message': i18n['task_completed'], 'output_dir': dir_name, 'success': True}})
            else:
                output_queue.put({'event': 'task_completed', 'data': {'message': i18n['task_completed_with_errors'], 'output_dir': dir_name, 'success': False}})
        finally:
            stdout_handler.final_flush()
            stderr_handler.final_flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        output_queue.put({'event': 'error', 'data': {'message': f'Task execution failed in process: {str(e)}\\n{tb_str}'}})
    finally:
        output_queue.put({'event': 'STOP'})

class AGIBotGUI:
    def __init__(self):
        self.current_process = None
        self.output_queue = None
        self.input_queue = None  # 新增：用于接收用户输入的队列
        self.current_output_dir = None  # Track current execution output directory
        self.last_output_dir = None     # Track last used output directory
        self.selected_output_dir = None # Track user selected output directory
        
        # Get GUI default data directory from config, fallback to current directory
        config_data_dir = get_gui_default_data_directory()
        if config_data_dir:
            self.output_dir = config_data_dir
            print(f"📁 Using configured GUI data directory: {self.output_dir}")
        else:
            self.output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            print(f"📁 Using default GUI data directory: {self.output_dir}")
        
    def get_output_directories(self):
        """Get all directories containing workspace subdirectory"""
        result = []
        
        try:
            # Traverse all subdirectories in current directory
            for item in os.listdir(self.output_dir):
                item_path = os.path.join(self.output_dir, item)
                
                # Check if it's a directory
                if os.path.isdir(item_path):
                    # Check if it contains workspace subdirectory
                    workspace_path = os.path.join(item_path, 'workspace')
                    if os.path.exists(workspace_path) and os.path.isdir(workspace_path):
                        # Get directory information
                        stat = os.stat(item_path)
                        size = self.get_directory_size(item_path)
                        
                        result.append({
                            'name': item,
                            'path': item_path,
                            'size': self.format_size(size),
                            'modified_time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'files': self.get_directory_structure(item_path),
                            'is_current': item == self.current_output_dir,  # Mark if it's current directory
                            'is_selected': item == self.selected_output_dir,  # Mark if it's selected directory
                            'is_last': item == self.last_output_dir  # Mark if it's last used directory
                        })
        except (OSError, PermissionError) as e:
            print(f"Error reading directories: {e}")
        
        # Sort by modification time
        result.sort(key=lambda x: os.path.getmtime(x['path']), reverse=True)
        return result
    
    def get_directory_size(self, directory):
        """Calculate directory size"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except (OSError, IOError):
            pass
        return total_size
    
    def format_size(self, size_bytes):
        """Format file size"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024.0 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def get_directory_structure(self, directory, max_depth=3, current_depth=0, base_dir=None):
        """Get directory structure"""
        if current_depth > max_depth:
            return []
        
        # If first call, set base_dir to parent directory of current directory
        if base_dir is None:
            base_dir = os.path.dirname(directory)
        
        items = []
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                # Calculate relative path to base_dir
                relative_path = os.path.relpath(item_path, base_dir)
                # Convert Windows path separators to Unix style
                relative_path = relative_path.replace('\\', '/')
                
                if os.path.isdir(item_path):
                    children = self.get_directory_structure(item_path, max_depth, current_depth + 1, base_dir)
                    items.append({
                        'name': item,
                        'type': 'directory',
                        'path': relative_path,
                        'children': children
                    })
                else:
                    items.append({
                        'name': item,
                        'type': 'file',
                        'path': relative_path,
                        'size': self.format_size(os.path.getsize(item_path))
                    })
        except (OSError, PermissionError):
            pass
        
        return sorted(items, key=lambda x: (x['type'] == 'file', x['name']))

gui_instance = AGIBotGUI()

def queue_reader_thread():
    """Reads from the queue and emits messages to the client via SocketIO."""
    print("Queue reader thread started.")
    while True:
        try:
            if gui_instance.current_process and not gui_instance.current_process.is_alive() and gui_instance.output_queue.empty():
                print("Process finished and queue is empty, stopping reader.")
                break

            message = gui_instance.output_queue.get(timeout=1)
            
            if message.get('event') == 'STOP':
                print("Received STOP sentinel.")
                break
            
            # If task completion message, save last used directory and clear current directory mark
            if message.get('event') in ['task_completed', 'error']:
                if gui_instance.current_output_dir:
                    gui_instance.last_output_dir = gui_instance.current_output_dir
                gui_instance.current_output_dir = None
                gui_instance.selected_output_dir = None  # Clear selected directory
            
            socketio.emit(message['event'], message.get('data', {}))
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error in queue_reader_thread: {e}")
            break
    
    print("Queue reader thread finished.")
    if gui_instance.current_process:
        gui_instance.current_process.join(timeout=1)
    gui_instance.current_process = None
    gui_instance.output_queue = None
    gui_instance.input_queue = None  # 清理输入队列
    if gui_instance.current_output_dir:
        gui_instance.last_output_dir = gui_instance.current_output_dir
    gui_instance.current_output_dir = None  # Clear current directory mark

@app.route('/')
def index():
    """Main page"""
    i18n = get_i18n_texts()
    current_lang = get_language()
    return render_template('index.html', i18n=i18n, lang=current_lang)

@app.route('/test_toggle_simple.html')
def test_toggle_simple():
    """Expand/collapse functionality test page"""
    return send_from_directory('.', 'test_toggle_simple.html')

@app.route('/simple_test.html')
def simple_test():
    """Simple test page"""
    return send_from_directory('.', 'simple_test.html')

@app.route('/api/output-dirs')
def get_output_dirs():
    """Get output directory list"""
    try:
        dirs = gui_instance.get_output_directories()
        return jsonify({'success': True, 'directories': dirs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download/<path:dir_name>')
def download_directory(dir_name):
    """Download directory as zip file (excluding workspace_code_index directory)"""
    try:
        dir_path = os.path.join(gui_instance.output_dir, secure_filename(dir_name))
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return jsonify({'success': False, 'error': 'Directory not found'})
        
        # Create temporary zip file
        temp_file = f"/tmp/{dir_name}.zip"
        
        with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dir_path):
                # Exclude workspace_code_index directory
                if 'workspace_code_index' in root:
                    print(f"Excluding directory: {root}")  # Debug info
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    # 计算相对路径
                    arcname = os.path.join(dir_name, os.path.relpath(file_path, dir_path))
                    zipf.write(file_path, arcname)
        
        return send_file(temp_file, as_attachment=True, download_name=f"{dir_name}.zip")
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/file/<path:file_path>')
def get_file_content(file_path):
    """Get file content"""
    try:
        # Use the passed path directly, don't use secure_filename as we need to maintain path structure
        full_path = os.path.join(gui_instance.output_dir, file_path)
        
        # Security check: ensure path is within output directory
        real_output_dir = os.path.realpath(gui_instance.output_dir)
        real_file_path = os.path.realpath(full_path)
        if not real_file_path.startswith(real_output_dir):
            return jsonify({'success': False, 'error': 'Access denied'})
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'success': False, 'error': f'File not found: {file_path}'})
        
        # Check file size to avoid reading oversized files
        file_size = os.path.getsize(full_path)
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'success': False, 'error': 'File too large to display'})
        
        # Get file extension
        _, ext = os.path.splitext(full_path.lower())
        
        # Decide how to handle based on file type
        if ext in ['.html', '.htm']:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return jsonify({
                'success': True, 
                'content': content, 
                'type': 'html',
                'size': gui_instance.format_size(file_size)
            })
        elif ext in ['.md', '.markdown']:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return jsonify({
                'success': True, 
                'content': content, 
                'type': 'markdown',
                'size': gui_instance.format_size(file_size)
            })
        elif ext == '.pdf':
            # PDF文件直接返回文件路径，让前端处理
            return jsonify({
                'success': True, 
                'type': 'pdf',
                'file_path': file_path,
                'size': gui_instance.format_size(file_size)
            })
        elif ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            # Office文档预览
            return jsonify({
                'success': True, 
                'type': 'office',
                'file_path': file_path,
                'file_ext': ext,
                'size': gui_instance.format_size(file_size)
            })
        elif ext in ['.py', '.js', '.jsx', '.ts', '.tsx', '.css', '.json', '.txt', '.log', '.yaml', '.yml', 
                     '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.java', '.go', '.rs', '.php', '.rb', 
                     '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.xml', '.sql', '.r', 
                     '.scala', '.kt', '.swift', '.dart', '.lua', '.perl', '.pl', '.vim', '.dockerfile', 
                     '.makefile', '.cmake', '.gradle', '.properties', '.ini', '.cfg', '.conf', '.toml']:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Language mapping for syntax highlighting
            language_map = {
                '.py': 'python',
                '.js': 'javascript', 
                '.jsx': 'javascript',
                '.ts': 'typescript',
                '.tsx': 'typescript',
                '.css': 'css',
                '.json': 'json',
                '.c': 'c',
                '.cpp': 'cpp',
                '.cc': 'cpp',
                '.cxx': 'cpp',
                '.h': 'c',
                '.hpp': 'cpp',
                '.java': 'java',
                '.go': 'go',
                '.rs': 'rust',
                '.php': 'php',
                '.rb': 'ruby',
                '.sh': 'bash',
                '.bash': 'bash',
                '.zsh': 'bash',
                '.fish': 'bash',
                '.ps1': 'powershell',
                '.bat': 'batch',
                '.cmd': 'batch',
                '.xml': 'xml',
                '.sql': 'sql',
                '.r': 'r',
                '.scala': 'scala',
                '.kt': 'kotlin',
                '.swift': 'swift',
                '.dart': 'dart',
                '.lua': 'lua',
                '.perl': 'perl',
                '.pl': 'perl',
                '.vim': 'vim',
                '.dockerfile': 'dockerfile',
                '.makefile': 'makefile',
                '.cmake': 'cmake',
                '.gradle': 'gradle',
                '.yaml': 'yaml',
                '.yml': 'yaml',
                '.toml': 'toml',
                '.txt': 'text',
                '.log': 'text'
            }
            
            language = language_map.get(ext, ext[1:])  # Default to remove dot
            
            return jsonify({
                'success': True, 
                'content': content, 
                'type': 'code',
                'language': language,
                'size': gui_instance.format_size(file_size)
            })
        elif ext == '.csv':
            # CSV file table preview
            import csv
            import io
            
            try:
                # Read CSV file
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Parse CSV content
                csv_reader = csv.reader(io.StringIO(content))
                rows = list(csv_reader)
                
                if not rows:
                    return jsonify({'success': False, 'error': 'CSV file is empty'})
                
                # Get header (first row)
                headers = rows[0] if rows else []
                data_rows = rows[1:] if len(rows) > 1 else []
                
                # Limit displayed rows to avoid frontend lag
                max_rows = 1000
                if len(data_rows) > max_rows:
                    data_rows = data_rows[:max_rows]
                    truncated = True
                    total_rows = len(rows) - 1  # Subtract header
                else:
                    truncated = False
                    total_rows = len(data_rows)
                
                return jsonify({
                    'success': True,
                    'type': 'csv',
                    'headers': headers,
                    'data': data_rows,
                    'total_rows': total_rows,
                    'displayed_rows': len(data_rows),
                    'truncated': truncated,
                    'size': gui_instance.format_size(file_size)
                })
                
            except UnicodeDecodeError:
                # Try other encodings
                try:
                    with open(full_path, 'r', encoding='gbk', errors='ignore') as f:
                        content = f.read()
                    
                    csv_reader = csv.reader(io.StringIO(content))
                    rows = list(csv_reader)
                    
                    if not rows:
                        return jsonify({'success': False, 'error': 'CSV file is empty'})
                    
                    headers = rows[0] if rows else []
                    data_rows = rows[1:] if len(rows) > 1 else []
                    
                    max_rows = 1000
                    if len(data_rows) > max_rows:
                        data_rows = data_rows[:max_rows]
                        truncated = True
                        total_rows = len(rows) - 1
                    else:
                        truncated = False
                        total_rows = len(data_rows)
                    
                    return jsonify({
                        'success': True,
                        'type': 'csv',
                        'headers': headers,
                        'data': data_rows,
                        'total_rows': total_rows,
                        'displayed_rows': len(data_rows),
                        'truncated': truncated,
                        'encoding': 'gbk',
                        'size': gui_instance.format_size(file_size)
                    })
                except Exception:
                    return jsonify({'success': False, 'error': 'CSV file encoding not supported, please try UTF-8 or GBK encoding'})
            
            except Exception as e:
                return jsonify({'success': False, 'error': f'CSV file parsing failed: {str(e)}'})
        else:
            return jsonify({'success': False, 'error': 'File type not supported for preview'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/pdf/<path:file_path>')
def serve_pdf(file_path):
    """Serve PDF file directly"""
    try:
        # Use the passed path directly, don't use secure_filename as we need to maintain path structure
        full_path = os.path.join(gui_instance.output_dir, file_path)
        
        # Security check: ensure path is within output directory
        real_output_dir = os.path.realpath(gui_instance.output_dir)
        real_file_path = os.path.realpath(full_path)
        if not real_file_path.startswith(real_output_dir):
            return jsonify({'success': False, 'error': 'Access denied'})
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'success': False, 'error': f'File not found: {file_path}'})
        
        # Check if it's a PDF file
        if not full_path.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'Not a PDF file'})
        
        return send_file(full_path, mimetype='application/pdf')
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download-file/<path:file_path>')
def download_file(file_path):
    """Download file directly"""
    try:
        # Use the passed path directly, don't use secure_filename as we need to maintain path structure
        full_path = os.path.join(gui_instance.output_dir, file_path)
        
        # Security check: ensure path is within output directory
        real_output_dir = os.path.realpath(gui_instance.output_dir)
        real_file_path = os.path.realpath(full_path)
        if not real_file_path.startswith(real_output_dir):
            return jsonify({'success': False, 'error': 'Access denied'})
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'success': False, 'error': f'File not found: {file_path}'})
        
        # Get file extension and set appropriate mimetype
        _, ext = os.path.splitext(full_path.lower())
        
        # Define mimetypes for different file types
        mimetype_map = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.zip': 'application/zip',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml'
        }
        
        # Get mimetype or use default
        mimetype = mimetype_map.get(ext, 'application/octet-stream')
        
        # Get filename for download
        filename = os.path.basename(full_path)
        
        return send_file(full_path, 
                        mimetype=mimetype, 
                        as_attachment=True, 
                        download_name=filename)
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload-to-cloud/<path:file_path>')
def upload_to_cloud(file_path):
    """Upload file to cloud storage for preview"""
    try:
        import requests
        
        # Use the passed path directly, don't use secure_filename as we need to maintain path structure
        full_path = os.path.join(gui_instance.output_dir, file_path)
        
        # Security check: ensure path is within output directory
        real_output_dir = os.path.realpath(gui_instance.output_dir)
        real_file_path = os.path.realpath(full_path)
        if not real_file_path.startswith(real_output_dir):
            return jsonify({'success': False, 'error': 'Access denied'})
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return jsonify({'success': False, 'error': f'File not found: {file_path}'})
        
        # Check file size (most free services have limits)
        file_size = os.path.getsize(full_path)
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            return jsonify({'success': False, 'error': 'File too large (max 100MB)'})
        
        filename = os.path.basename(full_path)
        
        # For testing purposes, use local file URL when cloud services fail
        # This allows us to test the preview functionality
        # Can be controlled by environment variable CLOUD_PREVIEW_TEST_MODE
        test_mode = os.environ.get('CLOUD_PREVIEW_TEST_MODE', 'false').lower() == 'true'
        
        # Disable test mode for now to enable real cloud upload
        # if test_mode:
        #     # Return local file URL for testing
        #     local_url = f"{request.host_url}api/download-file/{file_path}"
        #     return jsonify({
        #         'success': True,
        #         'cloud_url': local_url,
        #         'service': 'Local Test',
        #         'expires': 'Session'
        #     })
        
        # Try multiple cloud storage services
        cloud_services = [
            {
                'name': 'transfer.sh',
                'url': 'https://transfer.sh',
                'method': 'transfer'
            },
            {
                'name': '0x0.st',
                'url': 'https://0x0.st',
                'method': '0x0'
            },
            {
                'name': 'File.io',
                'url': 'https://file.io',
                'method': 'fileio'
            }
        ]
        
        for service in cloud_services:
            try:
                if service['method'] == 'transfer':
                    # transfer.sh upload
                    with open(full_path, 'rb') as f:
                        response = requests.put(f"{service['url']}/{filename}", data=f, timeout=30)
                    
                    if response.status_code == 200:
                        cloud_url = response.text.strip()
                        if cloud_url.startswith('http'):
                            return jsonify({
                                'success': True,
                                'cloud_url': cloud_url,
                                'service': service['name'],
                                'expires': '14 days'
                            })
                
                elif service['method'] == 'fileio':
                    # File.io upload
                    with open(full_path, 'rb') as f:
                        files = {'file': (filename, f)}
                        response = requests.post(service['url'], files=files, timeout=30)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            if data.get('success'):
                                return jsonify({
                                    'success': True,
                                    'cloud_url': data['link'],
                                    'service': service['name'],
                                    'expires': '14 days'
                                })
                        except ValueError as e:
                            print(f"File.io JSON parse error: {e}, response: {response.text[:200]}")
                            # File.io might return plain text URL
                            if response.text.startswith('http'):
                                return jsonify({
                                    'success': True,
                                    'cloud_url': response.text.strip(),
                                    'service': service['name'],
                                    'expires': '14 days'
                                })
                
                elif service['method'] == '0x0':
                    # 0x0.st upload
                    with open(full_path, 'rb') as f:
                        files = {'file': (filename, f)}
                        response = requests.post(service['url'], files=files, timeout=30)
                    
                    if response.status_code == 200:
                        cloud_url = response.text.strip()
                        if cloud_url.startswith('http'):
                            return jsonify({
                                'success': True,
                                'cloud_url': cloud_url,
                                'service': service['name'],
                                'expires': '365 days'
                            })
                

                            
            except Exception as e:
                print(f"Failed to upload to {service['name']}: {e}")
                continue
        
        return jsonify({'success': False, 'error': 'All cloud storage services failed'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@socketio.on('connect')
def handle_connect():
    """WebSocket connection processing"""
    i18n = get_i18n_texts()
    emit('status', {'message': i18n['connected']})

@socketio.on('execute_task')
def handle_execute_task(data):
    """Handle task execution request"""
    i18n = get_i18n_texts()
    
    if gui_instance.current_process and gui_instance.current_process.is_alive():
        socketio.emit('error', {'message': i18n['error_task_running']})
        return

    user_requirement = data.get('requirement', '')
    if not user_requirement.strip():
        socketio.emit('error', {'message': i18n['error_no_requirement']})
        return
    
    task_type = data.get('type', 'continue')  # 'new', 'continue', 'selected'
    plan_mode = data.get('plan_mode', False)  # Whether to use plan mode (task decomposition)
    
    if task_type == 'new':
        # New task: create new output directory
        out_dir = None
        continue_mode = False
    elif task_type == 'selected':
        # Use selected directory - convert to absolute path
        if gui_instance.selected_output_dir:
            out_dir = os.path.join(gui_instance.output_dir, gui_instance.selected_output_dir)
        else:
            out_dir = None
        # Check if selected directory is newly created (not in last_output_dir)
        # If it's a new directory, should use continue_mode=False
        if gui_instance.selected_output_dir != gui_instance.last_output_dir:
            continue_mode = False  # New directory, don't continue previous work
        else:
            continue_mode = True   # Existing directory, continue previous work
    else:
        # Continue mode: use last output directory - convert to absolute path
        if gui_instance.last_output_dir:
            out_dir = os.path.join(gui_instance.output_dir, gui_instance.last_output_dir)
        else:
            out_dir = None
        continue_mode = True
        
        # If no last directory, create new one
        if not out_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(gui_instance.output_dir, f"output_{timestamp}")
    
    gui_instance.output_queue = multiprocessing.Queue()
    gui_instance.input_queue = multiprocessing.Queue()  # 新增输入队列
    
    gui_instance.current_process = multiprocessing.Process(
                    target=execute_agibot_task_process_target,
        args=(user_requirement, gui_instance.output_queue, gui_instance.input_queue, out_dir, continue_mode, plan_mode)
    )
    gui_instance.current_process.daemon = True
    gui_instance.current_process.start()
    
    # Set current output directory name (extract from absolute path if needed)
    if out_dir:
        gui_instance.current_output_dir = os.path.basename(out_dir)
    else:
        gui_instance.current_output_dir = None

    threading.Thread(target=queue_reader_thread, daemon=True).start()

@socketio.on('select_directory')
def handle_select_directory(data):
    """Handle directory selection request"""
    dir_name = data.get('dir_name', '')
    if dir_name:
        gui_instance.selected_output_dir = dir_name
        socketio.emit('directory_selected', {'dir_name': dir_name})
    else:
        gui_instance.selected_output_dir = None
        socketio.emit('directory_selected', {'dir_name': None})

@socketio.on('stop_task')
def handle_stop_task():
    """Handle stop task request"""
    i18n = get_i18n_texts()
    
    if gui_instance.current_process and gui_instance.current_process.is_alive():
        print("Received stop request. Terminating process.")
        gui_instance.current_process.terminate()
        gui_instance.current_output_dir = None  # Clear current directory mark
        socketio.emit('task_stopped', {'message': i18n['task_stopped'], 'type': 'error'})
    else:
        socketio.emit('output', {'message': i18n['no_task_running'], 'type': 'info'})

@socketio.on('send_input')
def handle_send_input(data):
    """Handle user input to terminal"""
    i18n = get_i18n_texts()
    
    if not gui_instance.current_process or not gui_instance.current_process.is_alive():
        socketio.emit('output', {'message': i18n['no_task_running'], 'type': 'info'})
        return
    
    user_input = data.get('input', '')
    input_type = data.get('type', 'text')  # 'text', 'password', 'ctrl_c', 'ctrl_d', etc.
    
    if input_type == 'ctrl_c':
        # Send SIGINT to the process
        try:
            gui_instance.current_process.terminate()
            socketio.emit('output', {'message': '🛑 已发送 Ctrl+C 中断信号', 'type': 'info'})
        except Exception as e:
            socketio.emit('output', {'message': f'❌ 发送中断信号失败: {str(e)}', 'type': 'error'})
    elif input_type == 'ctrl_d':
        # Send EOF signal
        try:
            if gui_instance.input_queue:
                gui_instance.input_queue.put({'type': 'eof'})
            socketio.emit('output', {'message': '📤 已发送 Ctrl+D (EOF)', 'type': 'info'})
        except Exception as e:
            socketio.emit('output', {'message': f'❌ 发送EOF信号失败: {str(e)}', 'type': 'error'})
    elif input_type in ['text', 'password']:
        # Send text input
        try:
            if gui_instance.input_queue:
                gui_instance.input_queue.put({'type': input_type, 'data': user_input})
                # Don't echo password input
                if input_type == 'password':
                    socketio.emit('output', {'message': '🔑 已发送密码输入', 'type': 'info'})
                else:
                    socketio.emit('output', {'message': f'📤 用户输入: {user_input}', 'type': 'user_input'})
            else:
                socketio.emit('output', {'message': '❌ 无法发送输入：进程未正确初始化', 'type': 'error'})
        except Exception as e:
            socketio.emit('output', {'message': f'❌ 发送输入失败: {str(e)}', 'type': 'error'})

@socketio.on('create_new_directory')
def handle_create_new_directory():
    """Handle create new directory request"""
    try:
        i18n = get_i18n_texts()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_dir_name = f"output_{timestamp}"
        new_dir_path = os.path.join(gui_instance.output_dir, new_dir_name)
        
        # Create main directory
        os.makedirs(new_dir_path, exist_ok=True)
        
        # Create workspace subdirectory
        workspace_dir = os.path.join(new_dir_path, 'workspace')
        os.makedirs(workspace_dir, exist_ok=True)
        
        # Set as currently selected directory
        gui_instance.selected_output_dir = new_dir_name
        
        socketio.emit('directory_created', {
            'dir_name': new_dir_name,
            'success': True,
            'message': i18n['directory_created_with_workspace'].format(new_dir_name)
        })
        
    except Exception as e:
        socketio.emit('directory_created', {
            'success': False,
            'error': str(e)
        })

@app.route('/api/refresh-dirs', methods=['POST'])
def refresh_directories():
    """Manually refresh directory list"""
    try:
        i18n = get_i18n_texts()
        # Use existing method to get directory list
        directories = gui_instance.get_output_directories()
        return jsonify({
            'success': True,
            'directories': directories,
            'message': i18n['directory_list_refreshed']
        })
    except Exception as e:
        print(f"Failed to refresh directories: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# File upload functionality
@app.route('/api/upload/<path:dir_name>', methods=['POST'])
def upload_files(dir_name):
    """Upload files to workspace of specified directory"""
    try:
        i18n = get_i18n_texts()
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': i18n['no_files_selected']})
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'success': False, 'error': i18n['no_valid_files']})
        
        # Target directory path
        target_dir = os.path.join(gui_instance.output_dir, secure_filename(dir_name))
        if not os.path.exists(target_dir):
            return jsonify({'success': False, 'error': i18n['target_directory_not_exist']})
        
        # workspace directory path
        workspace_dir = os.path.join(target_dir, 'workspace')
        os.makedirs(workspace_dir, exist_ok=True)
        
        uploaded_files = []
        for file in files:
            if file.filename:
                # Custom secure filename handling, preserve Chinese characters
                safe_filename = sanitize_filename(file.filename)
                if not safe_filename:
                    continue
                
                # If file already exists, add timestamp
                if os.path.exists(os.path.join(workspace_dir, safe_filename)):
                    name, ext = os.path.splitext(safe_filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_filename = f"{name}_{timestamp}{ext}"
                
                file_path = os.path.join(workspace_dir, safe_filename)
                
                file.save(file_path)
                uploaded_files.append(safe_filename)
        
        return jsonify({
            'success': True,
            'message': i18n['upload_success'].format(len(uploaded_files)),
            'files': uploaded_files
        })
        
    except Exception as e:
        print(f"File upload failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def sanitize_filename(filename, is_directory=False):
    """
    Custom filename sanitization function, preserve Chinese characters but remove dangerous characters
    """
    if not filename:
        return None
    
    # Remove path separators and other dangerous characters, but preserve Chinese characters
    # Allow: letters, numbers, Chinese characters, dots, underscores, hyphens, spaces, parentheses
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    
    # Remove leading and trailing spaces and dots
    filename = filename.strip(' .')
    
    # If filename is empty, return None
    if not filename:
        return None
    
    # For directory names, allow starting with dots (like .git, etc.)
    # Limit filename length
    if len(filename) > 255:
        filename = filename[:255]
    
    return filename

@app.route('/api/rename-directory/<path:old_name>', methods=['PUT'])
def rename_directory(old_name):
    """Rename output directory"""
    try:
        i18n = get_i18n_texts()
        data = request.get_json()
        new_name = data.get('new_name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': i18n['new_name_empty']})
        
        # Check if it's currently executing directory
        if old_name == gui_instance.current_output_dir:
            return jsonify({'success': False, 'error': 'Cannot rename directory currently in use'})
        
        # Use custom secure filename handling, preserve more characters
        new_name_safe = sanitize_filename(new_name, is_directory=True)
        if not new_name_safe:
            return jsonify({'success': False, 'error': 'Invalid directory name'})
        
        # Build complete path
        old_path = os.path.join(gui_instance.output_dir, secure_filename(old_name))
        new_path = os.path.join(gui_instance.output_dir, new_name_safe)
        
        # Debug info
        print(f"Rename debug info:")
        print(f"  Original old_name: {old_name}")
        print(f"  Original new_name: {new_name}")
        print(f"  Safe old_name: {new_name_safe}")
        print(f"  Old path: {old_path}")
        print(f"  New path: {new_path}")
        print(f"  Paths are same: {old_path == new_path}")
        
        # If processed paths are the same, it means the new name is invalid
        if old_path == new_path:
            return jsonify({'success': False, 'error': 'New name is the same as original or contains invalid characters'})
        
        # Security check: ensure paths are within expected directory
        real_old_path = os.path.realpath(old_path)
        real_new_path = os.path.realpath(new_path)
        expected_parent = os.path.realpath(gui_instance.output_dir)
        
        if not real_old_path.startswith(expected_parent) or not real_new_path.startswith(expected_parent):
            return jsonify({'success': False, 'error': 'Paths are not safe'})
        
        # Check if original directory exists
        if not os.path.exists(old_path):
            return jsonify({'success': False, 'error': 'Original directory does not exist'})
        
        # Check if new directory exists
        if os.path.exists(new_path):
            return jsonify({'success': False, 'error': 'Target directory already exists'})
        
        print(f"Renaming directory: {old_path} -> {new_path}")
        
        # Rename directory
        os.rename(old_path, new_path)
        
        # Update GUI instance related states
        if gui_instance.selected_output_dir == old_name:
            gui_instance.selected_output_dir = new_name_safe
        if gui_instance.last_output_dir == old_name:
            gui_instance.last_output_dir = new_name_safe
        
        print(f"Successfully renamed directory: {old_name} -> {new_name_safe}")
        
        return jsonify({
            'success': True, 
            'message': f'Directory renamed successfully: {old_name} -> {new_name_safe}',
            'old_name': old_name,
            'new_name': new_name_safe
        })
        
    except Exception as e:
        print(f"Failed to rename directory: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-directory/<path:dir_name>', methods=['DELETE'])
def delete_directory(dir_name):
    """Delete specified output directory"""
    try:
        # Security check directory name
        safe_dir_name = secure_filename(dir_name)
        target_dir = os.path.join(gui_instance.output_dir, safe_dir_name)
        
        # Security check: ensure directory is within output directory
        real_output_dir = os.path.realpath(gui_instance.output_dir)
        real_target_dir = os.path.realpath(target_dir)
        if not real_target_dir.startswith(real_output_dir):
            return jsonify({'success': False, 'error': 'Access denied: Invalid directory path'})
        
        # Check if directory exists
        if not os.path.exists(target_dir):
            return jsonify({'success': False, 'error': f'Directory not found: {dir_name}'})
        
        # Check if directory contains workspace subdirectory (ensure it's a workspace directory)
        workspace_path = os.path.join(target_dir, 'workspace')
        if not os.path.exists(workspace_path) or not os.path.isdir(workspace_path):
            return jsonify({'success': False, 'error': 'Only directories with workspace subdirectory can be deleted'})
        
        # Check if it's currently executing directory
        if gui_instance.current_output_dir == dir_name:
            return jsonify({'success': False, 'error': 'Cannot delete currently executing directory'})
        
        print(f"Deleting directory: {target_dir}")
        
        # Delete directory and all its contents
        shutil.rmtree(target_dir)
        
        # Clean GUI instance related states
        if gui_instance.last_output_dir == dir_name:
            gui_instance.last_output_dir = None
        if gui_instance.selected_output_dir == dir_name:
            gui_instance.selected_output_dir = None
        
        print(f"Successfully deleted directory: {dir_name}")
        
        return jsonify({
            'success': True, 
            'message': f'Directory "{dir_name}" has been successfully deleted'
        })
        
    except PermissionError as e:
        print(f"Permission error deleting directory {dir_name}: {str(e)}")
        return jsonify({'success': False, 'error': f'Permission denied: {str(e)}'})
    except Exception as e:
        print(f"Error deleting directory {dir_name}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    socketio.run(app, host='0.0.0.0', port=port, debug=False) 