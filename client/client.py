import sys
import os
import socket
import uuid
import threading
import queue
import asyncio
from datetime import datetime
from functools import partial
import json
import regex
import emoji
from collections import defaultdict
import bluetooth
from pynput import keyboard
from cryptography.fernet import Fernet
import zstandard as zstd
import msgpack
import sounddevice as sd
import soundfile as sf
import numpy as np

# Project imports
try:
    from managers.p2p_manager import P2PManager
    import stun
    from managers.plugin_manager import PluginManager
    from managers.translator import Translator
    from managers.audio_manager import AudioManager
    from managers.webrtc_manager import WebRTCManager
    from managers.hotkey_manager import HotkeyManager
    from managers.config_manager import ConfigManager
    from managers.server_manager import ServerManager
    from managers.bluetooth_manager import BluetoothManager
    from managers.emoji_manager import EmojiManager
    from managers.encryption_manager import EncryptionManager # Добавлен недостающий импорт
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)


class CoreClient:
    """
    Core client application logic without UI dependencies.
    Handles all business logic, networking, and coordination between managers.
    Designed to be UI-agnostic and work with any frontend (Kivy, React, CLI, etc.)
    """
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.tr = Translator(self.config_manager)
        self.encryption_manager = EncryptionManager()
        
        # Core state
        self.p2p_manager = None
        self.server_manager = None
        self.bluetooth_manager = None
        self.username = None
        self.mode = None
        self.server_groups = {}  # {group_id: {name, admin, members}}
        self.active_group_call = None
        self.pending_group_call_punches = set()
        self.current_peer_addr = None
        self.pending_call_target = None
        self.negotiated_rate = None
        self.callback_queue = queue.Queue()
        self.audio_manager = AudioManager(self.config_manager, self.callback_queue)
        self.hotkey_manager = HotkeyManager(self.callback_queue)
        self.is_muted = False
        self.plugin_manager = None
        self.emoji_manager = EmojiManager()
        self.is_recording_audio_message = False
        self.contacts = set()  # Users who have accepted contact requests
        
        # Chat management
        self.chat_history = {'global': []}
        self.initialized = False
        self.active_chat = 'global'  # Can be 'global' or a group_id
        
        # Event handlers for external UI
        self.event_handlers = {
            'message_received': [],
            'status_update': [],
            'user_list_update': [],
            'group_update': [],
            'call_state_change': [],
            'error': []
        }
        
        # Async event loop management. CoreClient now assumes an external loop.
        self.running = False
        self._main_task = None
        self._callback_task = None
    
    def register_event_handler(self, event_type, handler):
        """Register external event handler for UI updates"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)
    
    def emit_event(self, event_type, data):
        """Emit event to all registered handlers"""
        for handler in self.event_handlers.get(event_type, []):
            try:
                handler(data)
            except Exception as e:
                print(f"Error in event handler {event_type}: {e}")
    
    async def async_init(self):
        """Asynchronous initialization for CoreClient.
        This method can be called multiple times safely to re-initialize."""
        if self.initialized:
            print("CoreClient already initialized. Re-initializing...")
            # If already initialized, stop current managers before re-initializing
            await self._stop_managers_async()
            self.initialized = False # Reset for re-initialization

        self.initialized = True
        self.load_client_data() # Load client data
        
        # Initialize and load plugins
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.discover_and_load_plugins()
        
        # Initialize hotkeys
        # HotkeyManager is only initialized here, but its start/stop is managed separately
        self.hotkey_manager = HotkeyManager(self.callback_queue)
        self.init_hotkeys()
        if self.hotkey_manager and not self.hotkey_manager.is_running:
            self.hotkey_manager.start() # Start hotkey listener

        # Apply audio settings from config
        config = self.config_manager.load_config()
        self.apply_audio_settings(config)

        # Initialize user and mode from config if available
        config = self.config_manager.load_config()
        username = config.get('username')
        mode_type = config.get('mode')
        if username and mode_type:
            host = config.get('server_host')
            port = config.get('server_port')
            password = config.get('password')
            # Use the dedicated set_user_and_mode for initial setup
            await self.set_user_and_mode(username, mode_type, host, port, password)
        print("CoreClient initialized successfully")
    
    async def _stop_managers_async(self):
        """Asynchronously stop all active managers."""
        print("Stopping managers asynchronously...")
        if self.p2p_manager:
            self.p2p_manager.stop()
            self.p2p_manager = None
        if self.server_manager:
            self.server_manager.stop()
            self.server_manager = None
        if self.bluetooth_manager:
            self.bluetooth_manager.stop()
            self.bluetooth_manager = None
        if self.webrtc_manager:
            self.webrtc_manager.stop()
            self.webrtc_manager = None # Ensure it's reset
        if self.plugin_manager:
            self.plugin_manager.unload_plugins()
            self.plugin_manager = None
        if self.hotkey_manager and self.hotkey_manager.is_running: # Stop only if running
            self.hotkey_manager.stop()
            # self.hotkey_manager = None # HotkeyManager is re-initialized in async_init, so no need to nullify here
        print("Managers stopped.")
    
    def load_client_data(self):
        """Load client-specific data (username, contacts, chat history) from config"""
        config = self.config_manager.load_config()
        chat_history = self.config_manager.load_chat_history()
        
        # Load username from config
        username = config.get('username')
        if username:
            self.username = username
        
        # Load contacts from config
        contacts = config.get('contacts', [])
        self.contacts = set(contacts)
        
        # Load chat history
        if chat_history:
            self.chat_history = chat_history
        
        print(f"Loaded client data: username={self.username}, contacts={len(self.contacts)}, chat_history_keys={list(self.chat_history.keys())}")

    def save_client_data(self):
        """Save client-specific data (username, contacts, chat history) to config"""
        config = self.config_manager.load_config()
        
        # Save username to config
        if self.username:
            config['username'] = self.username
        
        # Save contacts to config
        config['contacts'] = list(self.contacts)
        
        # Save config
        self.config_manager.save_config(config)
        
        # Save chat history
        self.config_manager.save_chat_history(self.chat_history)
        
        print(f"Saved client data: username={self.username}, contacts={len(self.contacts)}, chat_history_keys={list(self.chat_history.keys())}")

        
    async def set_user_and_mode(self, username: str, mode_type: str, host: str = None, port: int = None, password: str = None):
        """Sets the username and switches the client's operating mode."""
        print(f"Attempting to set user to '{username}' and mode to '{mode_type}'")
        
        # Stop existing managers before switching mode
        await self._stop_managers_async()
        
        self.username = username
        self.mode = mode_type

        if mode_type == 'p2p_local':
            await self._init_p2p_mode(mode_type='local')
        elif mode_type == 'p2p_internet':
            await self._init_p2p_mode(mode_type='internet')
        elif mode_type == 'server':
            if not host or not port:
                self.emit_event('error', {'message': self.tr.get("Host and Port are required for Server mode.")})
                return
            await self._init_server_mode(host, port, password)
        elif mode_type == 'p2p_bluetooth':
            await self._init_bluetooth_mode()
        else:
            self.emit_event('error', {'message': self.tr.get(f"Unknown mode type: {mode_type}")})
            return

        # Save the new user and mode to config
        config = self.config_manager.load_config()
        config['username'] = username
        config['mode'] = mode_type
        if mode_type == 'server':
            config['server_host'] = host
            config['server_port'] = port
            config['password'] = password
        self.config_manager.save_config(config)
        
        self.emit_event('status_update', {'message': self.tr.get(f"User set to '{username}', mode set to '{mode_type}'.")})
        print(f"User set to '{username}', mode set to '{mode_type}'.")

    async def start(self):
        """Starts the CoreClient's main asynchronous operations.
        Assumes an asyncio event loop is already running in the current thread."""
        if self.running:
            print("CoreClient is already running.")
            return

        self.running = True
        print("CoreClient starting asynchronous tasks...")
        
        # Initialize the client fully
        await self.async_init()

        # Start processing callbacks in the background
        # Store tasks to be able to cancel them later
        self._callback_task = asyncio.create_task(self.process_callbacks_async())
        self._main_task = asyncio.create_task(self._main_loop_task())

        print("CoreClient asynchronous tasks started.")
    
    async def _main_loop_task(self):
        """A simple loop to keep the client 'running'."""
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("CoreClient main loop task cancelled.")
        finally:
            print("CoreClient main loop task stopped.")

    async def stop(self):
        """Stops the CoreClient and its managers gracefully."""
        if not self.running:
            return

        print("Stopping CoreClient asynchronous tasks...")
        self.running = False
        self.save_client_data() # Save client data before stopping

        # Cancel main loop task and callback processing task
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass # Expected during cancellation

        if self._callback_task:
            self._callback_task.cancel()
            try:
                await self._callback_task
            except asyncio.CancelledError:
                pass # Expected during cancellation
        
        # Stop all managers asynchronously
        await self._stop_managers_async()
        
        self.initialized = False # Mark as not initialized
        print("CoreClient stopped successfully.")
    
    async def process_callbacks_async(self):
        """Process callbacks from managers asynchronously"""
        try:
            while self.running:
                # Process all available callbacks
                while not self.callback_queue.empty():
                    event = self.callback_queue.get_nowait()
                    await self.handle_callback(event)
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            print("Callback processing task cancelled.")
        except Exception as e:
            print(f"Error in callback processing: {e}")
            await asyncio.sleep(1)
    
    async def handle_callback(self, event):
        """Handle callback events from AudioManager and WebRTCManager."""
        event_type = event[0]
        
        if event_type == 'bt_message_received':
            _, message = event
            self.add_message(message, 'global')
        elif event_type == 'bt_connected':
            _, address = event
            self.emit_event('status_update', f"Bluetooth connected to {address}")
        elif event_type == 'bt_connection_failed':
            _, address = event
            self.emit_event('error', f"Bluetooth connection failed: {address}")
        elif event_type == 'bt_disconnected':
            self.emit_event('status_update', "Bluetooth disconnected")
        elif event_type == 'bt_adapter_error':
            _, error_msg = event
            self.emit_event('error', f"Bluetooth error: {error_msg}")
        elif event_type == 'webrtc_offer_created':
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'offer', event[1]['offer'])
        elif event_type == 'webrtc_answer_created':
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'answer', event[1]['answer'])
        elif event_type == 'mic_level':
            # Handle microphone level updates
            pass
    
    def add_message(self, message_data, chat_id=None):
        """Add message to chat history and notify UI"""
        if chat_id is None:
            chat_id = 'global'
        
        # Ensure message_data is stored in standard format
        if isinstance(message_data, str):
            message_data = {
                'id': str(uuid.uuid4()),
                'sender': 'System',
                'text': message_data,
                'timestamp': datetime.now().isoformat()
            }
        
        self.chat_history.setdefault(chat_id, []).append(message_data)
        
        # Notify UI about new message
        self.emit_event('message_received', {
            'chat_id': chat_id,
            'message': message_data
        })
    
    async def _init_p2p_mode(self, mode_type='internet'):
        """Initialize P2P mode"""
        p2p_mode_type = 'local' if mode_type == 'p2p_local' else 'internet'
        self.p2p_manager = P2PManager(self.username, self.chat_history, mode=p2p_mode_type)
        self.webrtc_manager = WebRTCManager(self.p2p_manager, self.audio_manager, self.callback_queue)
        self.webrtc_manager.start() # Start WebRTC manager now that P2PManager is available
        
        # Register callbacks
        callbacks = {
            'peer_discovered': self.on_peer_discovered,
            'peer_lost': self.on_peer_lost,
            'peer_found': self.on_peer_found,
            'peer_not_found': self.on_peer_not_found,
            'incoming_contact_request': self.on_incoming_contact_request,
            'contact_request_response': self.on_contact_request_response,
            'message_received': self.p2p_message_received,
            'webrtc_signal': self.on_webrtc_signal,
            'secure_channel_established': self.on_secure_channel_established,
            'group_created': self.on_group_created,
            'group_message_received': self.on_group_message_received,
            'history_received': self.on_history_received,
            'incoming_group_invite': self.on_incoming_group_invite,
            'group_joined': self.on_group_joined,
            'group_invite_response': self.on_group_invite_response,
            'incoming_group_call': self.on_incoming_group_call,
            'group_call_response': self.handle_group_call_response,
            'group_call_hang_up': self.handle_group_call_hang_up,
            'user_kicked': self.on_user_kicked,
        }
        
        for event, func in callbacks.items():
            self.p2p_manager.register_callback(event, func)
        
        self.p2p_manager.start()
        
        if not self.p2p_manager.udp_socket:
            self.add_message("Failed to initialize P2P networking. Port might be in use.", 'global')
            return
        
        self.add_message(f"P2P {p2p_mode_type} mode started as '{self.username}'.", 'global')
    
    async def _init_server_mode(self, host: str, port: int, password: str = None):
        """Initialize server mode"""
        self.server_manager = ServerManager(host, port, self.username, password, self.chat_history)
        
        callbacks = {
            'login_failed': lambda p: self.add_message(f"Login failed: {p.get('reason')}", 'global'),
            'connection_failed': lambda e: self.add_message(f"Server connection failed: {e}", 'global'),
            'disconnected': lambda: self.add_message("Disconnected from server.", 'global'),
            'info_received': lambda p: self.add_message(f"Server: {p.get('message')}", 'global'),
            'user_list_update': self.on_user_list_update,
            'group_message_received': self.on_group_message_received,
            'group_created': self.on_group_created,
            'incoming_group_invite': self.on_incoming_group_invite,
            'group_invite_response': self.on_group_invite_response,
            'group_joined': self.on_group_joined,
            'history_received': self.on_history_received,
            'initial_data_received': self.on_initial_data_received,
            'incoming_group_call': self.on_incoming_group_call,
            'user_joined_call': self.on_user_joined_call,
            'user_left_call': self.on_user_left_call,
            'user_kicked': self.on_user_kicked,
        }
        
        for event, func in callbacks.items():
            self.server_manager.register_callback(event, func)
        
        self.server_manager.start()
        self.add_message(f"Connecting to server at {host}:{port} as '{self.username}'...", 'global')
    
    async def _init_bluetooth_mode(self):
        """Initialize Bluetooth mode"""
        self.bluetooth_manager = BluetoothManager(self.username, self.callback_queue)
        self.bluetooth_manager.start()
        self.add_message("Bluetooth mode started", 'global')
    
    def send_message(self, text, chat_id=None):
        """Send message to current or specified chat"""
        if chat_id is None:
            chat_id = self.active_chat
        
        if not text.strip():
            return
        
        message_data = {
            'id': str(uuid.uuid4()),
            'sender': self.username,
            'text': text,
            'timestamp': datetime.now().isoformat(),
            'status': 'sent'
        }
        
        if self.mode.startswith('p2p') and self.p2p_manager:
            is_group = chat_id in self.p2p_manager.groups
            
            if chat_id == 'global':
                if not self.contacts:
                    self.emit_event('error', "You must add a user as a contact before sending messages.")
                    return
                for contact_user in self.contacts:
                    self.p2p_manager.send_private_message(contact_user, message_data)
                self.add_message(message_data, 'global')
            elif is_group:
                self.p2p_manager.send_group_message(chat_id, message_data)
                self.add_message(message_data, chat_id)
            else:
                self.p2p_manager.send_private_message(chat_id, message_data)
                self.add_message(message_data, chat_id)
        
        elif self.mode == 'server' and self.server_manager:
            if chat_id != 'global':
                self.server_manager.send_group_message(chat_id, message_data)
                self.add_message(message_data, chat_id)
            else:
                self.add_message("Cannot send global messages in server mode yet.", 'global')
        
        elif self.mode == 'p2p_bluetooth' and self.bluetooth_manager:
            full_message = f"{self.username}: {text}"
            if self.bluetooth_manager.send_message(full_message):
                self.add_message(full_message, 'global')
            else:
                self.add_message("Bluetooth not connected", 'global')
    
    # --- Callback handlers (adapted from Kivy version) ---
    
    def on_peer_discovered(self, username, address_info):
        """Handle peer discovery"""
        if username == self.username:
            return
        self.emit_event('user_list_update', {'action': 'add', 'user': username})
    
    def on_user_list_update(self, users):
        """Handle user list updates"""
        self.emit_event('user_list_update', {'users': users})
    
    def on_peer_lost(self, username):
        """Handle peer going offline"""
        self.emit_event('user_list_update', {'action': 'remove', 'user': username})
        self.add_message(f"'{username}' went offline.", 'global')
    
    def on_secure_channel_established(self, username):
        """Handle secure connection established"""
        self.add_message(f"Secure connection established with {username}.", 'global')
    
    def on_peer_found(self, username):
        """Handle peer found"""
        self.add_message(f"Found user '{username}'.", 'global')
    
    def on_peer_not_found(self, username):
        """Handle peer not found"""
        self.emit_event('error', f"User '{username}' could not be found.")
    
    def p2p_message_received(self, message_data):
        """Handle incoming P2P message"""
        if message_data.get('sender') != self.username:
            self.add_message(message_data, 'global')
    
    def on_webrtc_signal(self, sender, signal_type, data):
        """Handle WebRTC signals"""
        if signal_type == 'offer':
            self.emit_event('call_state_change', {
                'type': 'incoming_call',
                'peer': sender,
                'offer': data
            })
        elif signal_type == 'answer':
            self.add_message(f"Call with {sender} accepted and connected.", 'global')
            self.webrtc_manager.handle_answer(sender, data)
            self.emit_event('call_state_change', {
                'type': 'call_connected',
                'peer': sender
            })
        elif signal_type == 'hangup':
            self.webrtc_manager.end_call(sender)
            self.add_message(f"Call with {sender} ended.", 'global')
            self.emit_event('call_state_change', {
                'type': 'call_ended',
                'peer': sender
            })
        elif signal_type == 'busy':
            self.add_message(f"Call failed: {sender} is busy.", 'global')
            self.hang_up_call(sender)
    
    def on_incoming_contact_request(self, sender_username, payload):
        """Handle incoming contact request"""
        self.emit_event('status_update', {
            'type': 'contact_request',
            'sender': sender_username,
            'payload': payload
        })
    
    def on_contact_request_response(self, sender_username, accepted):
        """Handle contact request response"""
        if accepted:
            self.contacts.add(sender_username)
            self.emit_event('status_update', f"'{sender_username}' accepted your contact request.")
        else:
            self.emit_event('status_update', f"'{sender_username}' declined your contact request.")
    
    def on_history_received(self, chat_id, history):
        """Handle received chat history"""
        self.add_message(f"Received history for '{chat_id}' ({len(history)} messages).", 'global')
        if len(history) > len(self.chat_history.get(chat_id, [])):
            self.chat_history[chat_id] = history
            self.emit_event('chat_update', {'chat_id': chat_id, 'action': 'history_updated'})
    
    def on_group_created(self, group_id, group_name, admin_username):
        """Handle group creation"""
        # Update internal P2P group state
        if self.mode.startswith('p2p') and self.p2p_manager:
            # Assuming the P2PManager now directly updates its groups state and emits this event
            # so we just need to ensure CoreClient's state reflects it if necessary,
            # or rely on the manager to hold the source of truth for P2P groups.
            # For simplicity, let's assume P2PManager's internal 'groups' is the source.
            pass
        # For server mode, self.server_groups will be updated by on_initial_data_received or explicit server updates.
        # This event usually means *we* created the group, so we add it to our state immediately.
        if self.mode == 'server':
            self.server_groups[group_id] = {'name': group_name, 'admin': admin_username, 'members': {self.username}}
            
        self.add_message(f"You created group '{group_name}'.", 'global')
        self.emit_event('group_update', {
            'action': 'created',
            'group_id': group_id,
            'group_name': group_name,
            'admin': admin_username,
            'members': [self.username] # Initially only creator is a member
        })
    
    def on_group_message_received(self, group_id, message_data):
        """Handle group message"""
        self.add_message(message_data, group_id)
    
    def on_group_joined(self, group_id, username):
        """Handle user joining group"""
        # Update internal P2P group members if in P2P mode
        if self.mode.startswith('p2p') and self.p2p_manager:
            if group_id in self.p2p_manager.groups:
                self.p2p_manager.groups[group_id]['members'].add(username)
        # For server mode, self.server_groups will be updated by on_initial_data_received or explicit server updates.
        
        self.add_message(f"'{username}' has joined the group.", group_id)
        self.emit_event('group_update', {
            'action': 'member_added',
            'group_id': group_id,
            'username': username
        })
    
    def on_incoming_group_invite(self, group_id, group_name, admin_username):
        """Handle incoming group invite"""
        self.emit_event('group_update', {
            'action': 'invite_received',
            'group_id': group_id,
            'group_name': group_name,
            'admin': admin_username
        })
    
    def on_group_invite_response(self, group_id, username, accepted):
        """Handle group invite response"""
        if accepted:
            self.add_message(f"'{username}' accepted the invitation to join.", group_id)
            # For P2P, update the group's member list directly
            if self.mode.startswith('p2p') and self.p2p_manager:
                if group_id in self.p2p_manager.groups:
                    self.p2p_manager.groups[group_id]['members'].add(username)
                    self.emit_event('group_update', {
                        'action': 'member_added',
                        'group_id': group_id,
                        'username': username
                    })
            # For server, the server will send a user_joined_group event
        else:
            self.add_message(f"'{username}' declined the invitation to join.", group_id)
    
    def on_incoming_group_call(self, group_id, admin_username, sample_rate):
        """Handle incoming group call"""
        self.emit_event('call_state_change', {
            'type': 'incoming_group_call',
            'group_id': group_id,
            'admin': admin_username,
            'sample_rate': sample_rate
        })
    
    def handle_group_call_response(self, group_id, username, response):
        """Handle group call response"""
        if group_id != self.active_group_call:
            return
        
        if response == 'accept':
            self.add_message(f"{username} accepted the call. Connecting...", group_id)
            self.pending_group_call_punches.add(username)
            self.p2p_manager.initiate_hole_punch(username)
        else:
            self.add_message(f"{username} declined the call.", group_id)
    
    def handle_group_call_hang_up(self, group_id, username):
        """Handle group call hang up"""
        if group_id == self.active_group_call:
            self.add_message(f"{username} left the call.", group_id)
    
    def on_user_joined_call(self, group_id, username):
        """Handle user joining call"""
        if group_id == self.active_group_call:
            self.add_message(f"{username} joined the call.", group_id)
    
    def on_user_left_call(self, group_id, username):
        """Handle user leaving call"""
        if group_id == self.active_group_call:
            self.add_message(f"{username} left the call.", group_id)
    
    def on_initial_data_received(self, groups, users):
        """Handle initial data from server"""
        self.add_message("Received initial state from server.", 'global')
        self.server_groups.update(groups)
        self.on_user_list_update(users)
        
        for group_id, group_data in groups.items():
            # Update internal server_groups state for tracking
            self.server_groups[group_id] = group_data
            if self.username in group_data.get('members', []):
                self.emit_event('group_update', {
                    'action': 'added',
                    'group_id': group_id,
                    'group_name': group_data['name'],
                    'members': group_data.get('members', [])
                })
    
    def on_user_kicked(self, group_id, kicked_username, admin_username):
        """Handle user being kicked from group"""
        group_info = {}
        if self.mode.startswith('p2p') and self.p2p_manager:
            group_info = self.p2p_manager.groups.get(group_id, {})
        elif self.mode == 'server' and self.server_manager:
            group_info = self.server_groups.get(group_id, {})
            if kicked_username in group_info.get('members', []):
                group_info['members'].remove(kicked_username)
                self.server_groups[group_id] = group_info
        
        group_name = group_info.get('name', 'Unknown Group')
        
        if kicked_username == self.username:
            self.emit_event('error', f"You have been kicked from '{group_name}' by {admin_username}.")
            
            if self.active_chat == group_id:
                self.switch_chat('global')
            
            if group_id in self.chat_history:
                del self.chat_history[group_id]
            
            self.emit_event('group_update', {
                'action': 'removed',
                'group_id': group_id
            })
            # Also remove from local group state if it exists
            if self.mode.startswith('p2p') and self.p2p_manager and group_id in self.p2p_manager.groups:
                del self.p2p_manager.groups[group_id]
            elif self.mode == 'server' and group_id in self.server_groups:
                del self.server_groups[group_id]
        else:
            self.add_message(f"{kicked_username} was kicked by {admin_username}.", group_id)
            # Update UI for member list
            self.emit_event('group_update', {
                'action': 'member_removed',
                'group_id': group_id,
                'username': kicked_username
            })
    
    # --- Audio and call management ---
    
    def initiate_call(self, target_username):
        """Initiate call to user"""
        if self.webrtc_manager.peer_connections:
            self.emit_event('error', "Already in a call.")
            return
        
        if self.mode.startswith('p2p') and target_username not in self.contacts:
            self.request_contact(target_username)
            return
        
        self.add_message(f"Calling {target_username}...", 'global')
        self.webrtc_manager.start_call(target_username)
    
    def hang_up_call(self, peer_username=None):
        """Hang up call"""
        if not peer_username:
            for peer in list(self.webrtc_manager.peer_connections.keys()):
                self.webrtc_manager.end_call(peer)
                if self.p2p_manager:
                    self.p2p_manager.send_webrtc_signal(peer, 'hangup', {})
        else:
            self.webrtc_manager.end_call(peer_username)
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(peer_username, 'hangup', {})
        
        self.add_message("Call ended.", 'global')
        self.emit_event('call_state_change', {'type': 'call_ended'})
    
    def toggle_mute(self):
        """Toggle microphone mute"""
        self.is_muted = not self.is_muted
        self.webrtc_manager.set_mute(self.is_muted)
        
        if self.is_muted:
            self.add_message("Microphone muted.", 'global')
        else:
            self.add_message("Microphone unmuted.", 'global')
        
        self.emit_event('call_state_change', {
            'type': 'mute_toggled',
            'muted': self.is_muted
        })
    
    # --- Group management ---
    
    def create_group(self, group_name):
        """Create new group"""
        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.create_group(group_name)
        elif self.mode == 'server' and self.server_manager:
            self.server_manager.create_group(group_name)
        else:
            self.emit_event('error', "Cannot create groups in current mode.")
    
    def invite_to_group(self, group_id, target_username):
        """Invite user to group"""
        if self.mode.startswith('p2p'):
            self.p2p_manager.send_group_invite(group_id, target_username)
        elif self.mode == 'server':
            self.server_manager.invite_to_group(group_id, target_username)
        
        self.add_message(f"Invitation sent to '{target_username}'.", group_id)
    
    def start_group_call(self, group_id):
        """Start group call"""
        if group_id == 'global' or self.active_group_call or self.webrtc_manager.peer_connections:
            self.emit_event('error', "Cannot start group call.")
            return
        
        config = self.config_manager.load_config()
        supported_rate = config.get('audio_sample_rate', 48000)
        self.active_group_call = group_id
        
        if self.mode.startswith('p2p'):
            self.p2p_manager.start_group_call(group_id, supported_rate)
            self.add_message("Starting P2P group call...", group_id)
            self.join_group_call(group_id) # Creator joins their own call automatically
        elif self.mode == 'server':
            self.server_manager.start_group_call(group_id, supported_rate)
            self.add_message("Requesting server to start group call...", group_id)
            # In server mode, after requesting to start, we also join.
            # The server will then inform us of our public UDP address to use for the call.
            self.join_server_group_call(group_id)
    
    def join_group_call(self, group_id):
        """Join group call (P2P mode) - for server mode, use join_server_group_call"""
        if self.mode.startswith('p2p'):
            self.active_group_call = group_id
            members = self.p2p_manager.groups.get(group_id, {}).get('members', set())
            for member in members:
                if member != self.username:
                    self.pending_group_call_punches.add(member)
                    self.p2p_manager.initiate_hole_punch(member)
        elif self.mode == 'server':
            # This path should ideally not be hit directly for server group calls,
            # as join_server_group_call handles the specific server-side initiation.
            # However, if it is, we can log an error or redirect.
            self.emit_event('error', "Use 'join_server_group_call' for server group calls.")
    
    def join_server_group_call(self, group_id):
        """Join a server-hosted group call, handling the public UDP address.
        This is distinct from P2P group call joining which focuses on direct peer punching."""
        if not self.server_manager:
            self.emit_event('error', "Not connected to a server to join group calls.")
            return
        
        self.active_group_call = group_id
        self.emit_event('call_state_change', {
            'type': 'group_call_started',
            'group_id': group_id,
            'is_admin': False # Assume not admin when joining an existing call
        })
        
        # Get public address for STUN/TURN (placeholder, needs robust implementation)
        public_addr = self.get_public_udp_addr()
        if public_addr[0] == "127.0.0.1": # Fallback means STUN failed or is not implemented
            self.add_message("Warning: Could not determine public UDP address. May affect server call connectivity.", group_id)
        
        self.server_manager.join_group_call(group_id, public_addr)
        self.add_message(f"Attempting to join server group call for '{group_id}'...", group_id)
        # Further UI updates will come from on_user_joined_call callback from server_manager
    
    def leave_group_call(self, group_id):
        """Leave an active group call."""
        if self.active_group_call != group_id:
            self.emit_event('error', "Not in this group call.")
            return

        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.leave_group_call(group_id)
            self.webrtc_manager.end_all_peer_connections() # End all WebRTC connections for the group
        elif self.mode == 'server' and self.server_manager:
            self.server_manager.leave_group_call(group_id)
            self.webrtc_manager.end_all_peer_connections() # For server mode, we still manage local WebRTC
            
        self.active_group_call = None
        self.pending_group_call_punches.clear()
        self.add_message(f"You left the group call for '{group_id}'.", 'global')
        self.emit_event('call_state_change', {
            'type': 'group_call_ended',
            'group_id': group_id
        })
    
    def send_group_invite_response(self, group_id, admin_username, accepted):
        """Send response to a group invite."""
        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.send_group_invite_response(group_id, admin_username, accepted)
        elif self.mode == 'server' and self.server_manager:
            self.server_manager.send_group_invite_response(group_id, admin_username, accepted)
        else:
            self.emit_event('error', "Cannot respond to group invites in current mode.")
    
    def kick_user_from_group(self, group_id, target_username):
        """Kick a user from a group."""
        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.kick_user_from_group(group_id, target_username)
        elif self.mode == 'server' and self.server_manager:
            self.server_manager.kick_user_from_group(group_id, target_username)
        else:
            self.emit_event('error', "Cannot kick users from groups in current mode.")
    
    # --- Utility methods ---
    
    def switch_chat(self, chat_id):
        """Switch to different chat"""
        self.active_chat = chat_id
        self.emit_event('chat_update', {
            'action': 'switched',
            'chat_id': chat_id
        })
    
    def init_hotkeys(self):
        """Initialize hotkeys from config"""
        config = self.config_manager.load_config()
        hotkey_str = config.get('hotkeys', {}).get('mute', 'ctrl+m')
        
        keys = set()
        parts = hotkey_str.split('+')
        for part in parts:
            part = part.strip()
            try:
                keys.add(keyboard.Key[part])
            except KeyError:
                if len(part) == 1:
                    keys.add(keyboard.KeyCode.from_char(part))
        
        if keys:
            self.hotkey_manager.set_hotkey(self.toggle_mute_hotkey, hotkey_str)
        self.hotkey_manager.start()
    
    def toggle_mute_hotkey(self):
        """Hotkey callback for mute toggle"""
        self.toggle_mute()
    
    def apply_audio_settings(self, config):
        """Apply audio settings from config"""
        input_volume = config.get('input_volume', 80)
        output_volume = config.get('output_volume', 80)
        
        input_gain = input_volume / 100.0
        output_gain = output_volume / 100.0
        
        self.audio_manager.set_volume(input_gain, 'input')
        self.audio_manager.set_volume(output_gain, 'output')
    
    def get_public_udp_addr(self):
        """Get public UDP address.
        
        TODO: This is currently a placeholder implementation that attempts a simple external IP check.
        A robust solution for NAT traversal in real-world scenarios requires STUN/TURN servers.
        This method should eventually delegate to a dedicated STUN/TURN client/manager.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            public_ip = s.getsockname()[0]
            s.close()
            return (public_ip, 0) # Port 0 is a placeholder, should be actual public port from STUN
        except Exception as e:
            print(f"Error getting public address: {e}")
            return ("127.0.0.1", 0) # Fallback to loopback
    
    def request_contact(self, target_username):
        """Request contact with user"""
        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.send_contact_request(target_username)
            self.add_message(f"Contact request sent to '{target_username}'.", 'global')
        else:
            self.emit_event('error', "Contact requests not available in current mode.")


# Factory function for creating client instance
def create_client():
    """Create and return a new CoreClient instance"""
    return CoreClient()


# Main entry point for standalone usage
if __name__ == "__main__":
    client = CoreClient()
    client.start() # start() now manages the event loop and handles KeyboardInterrupt