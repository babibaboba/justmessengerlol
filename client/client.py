import sys
import os
import logging
import socket
import uuid
import threading
import queue
from datetime import datetime
from functools import partial
import regex
import json
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

# Flet imports
import flet as ft
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, AudioStreamTrack
from av import AudioFrame

# Create icons mapping for Flet compatibility
class Icons:
    EDIT = "edit"
    MENU = "menu"
    PHONE = "phone"
    MORE_VERT = "more_vert"
    SEND = "send"
    MIC = "mic"
    ATTACH_FILE = "attach_file"
    EMOJI_EMOTIONS = "emoji_emotions"
    SEARCH = "search"
    CLOSE = "close"
    INFO_OUTLINE = "info_outline"
    PERSON = "person"
    NOTIFICATIONS = "notifications"
    GROUP_ADD = "group_add"
    CONTACTS = "contacts"
    SETTINGS = "settings"
    REPLY = "reply"
    COPY = "copy"
    DELETE = "delete"
    KEYBOARD_OUTLINED = "keyboard_outlined"
    AUDIOTRACK_OUTLINED = "audiotrack_outlined"
    PALETTE_OUTLINED = "palette_outlined"
    SECURITY_OUTLINED = "security_outlined"
    EXTENSION_OUTLINED = "extension_outlined"
    ARROW_BACK = "arrow_back"
    MIC_OFF = "mic_off"
    CALL_END = "call_end"
    CALL = "call"
    BROKEN_IMAGE = "broken_image"
    INSERT_DRIVE_FILE = "insert_drive_file"
    PHOTO = "photo"
    LOCATION_ON = "location_on"
    CONTACT = "contacts"
    BLUETOOTH_SEARCHING = "bluetooth_searching"
    SENTIMENT_SATISFIED = "sentiment_satisfied"
    ACCESSIBILITY = "accessibility"
    PETS = "pets"
    EMOJI_FOOD_BEVERAGE = "emoji_food_beverage"
    AIRPLANEMODE_ACTIVE = "airplanemode_active"
    SPORTS_ESPORTS = "sports_esports"
    LIGHTBULB = "lightbulb"
    INFO = "info"
    FLAG = "flag"
    PLUS = "plus"

# Replace ft.icons with our icons class
ft.icons = Icons()

# Create colors mapping for Flet compatibility
class Colors:
    WHITE = "#FFFFFF"
    WHITE70 = "#FFFFFFB2"
    GREY = "#808080"
    GREY_400 = "#BDBDBD"
    GREY_500 = "#9E9E9E"
    BLACK = "#000000"
    RED = "#FF0000"
    PRIMARY = "#1976D2"  # Default primary color
    SURFACE = "#121212"  # Default surface color for dark theme

    # Additional colors from theme
    PRIMARY_GRAY = "#2d2d2d"
    SECONDARY_GRAY = "#424242"
    BACKGROUND = "#1a1a1a"
    SURFACE_VARIANT = "#333333"
    PRIMARY_PURPLE = "#7C4DFF"
    SECONDARY_PURPLE = "#651FFF"
    TERTIARY_PURPLE = "#E1BEE7"
    ERROR = "#FF5252"
    SUCCESS = "#4CAF50"

    @staticmethod
    def with_opacity(opacity, color):
        """Create color with opacity - simplified version"""
        if isinstance(color, str) and color.startswith('#'):
            # Extract RGB and add alpha
            if len(color) == 7:  # #RRGGBB format
                r, g, b = color[1:3], color[3:5], color[5:7]
                alpha = hex(int(255 * opacity))[2:].zfill(2)
                return f"#{r}{g}{b}{alpha}"
        return color

# Replace ft.colors with our colors class
ft.colors = Colors()

# Project imports - reusing all backend logic
try:
    from managers.p2p_manager import P2PManager, stun
    from managers.plugin_manager import PluginManager
    from managers.translator import Translator
    from managers.bluetooth_manager import BluetoothManager
    from managers.emoji_manager import EmojiManager
    from managers.hotkey_manager import HotkeyManager
    from managers.audio_manager import AudioManager, MicrophoneStreamTrack, AudioTrackPlayer
    from managers.webrtc_manager import WebRTCManager
    from managers.config_manager import ConfigManager
    from managers.server_manager import ServerManager
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# Flet-based VoiceChat Application
# Setup basic logging at the top level to ensure it's configured first.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class VoiceChatApp:
    def __init__(self, page: ft.Page):
        self.page = page
        logging.info("VoiceChatApp initializing...")

        # Initialize all the same managers (UI agnostic!)
        self.config_manager = ConfigManager()
        self.tr = Translator(self.config_manager)
        self.callback_queue = queue.Queue()
        self.audio_manager = AudioManager(self.config_manager, self.callback_queue)
        self.webrtc_manager = WebRTCManager(None, self.audio_manager, self.callback_queue) # P2P manager set later
        self.hotkey_manager = HotkeyManager(self.callback_queue)
        self.emoji_manager = EmojiManager(self)

        # Application state
        self.p2p_manager = None
        self.server_manager = None
        self.bluetooth_manager = None
        self.username = "Anonymous" # Default username
        self.mode = "p2p_internet" # Default mode
        self.server_groups = {}
        self.active_group_call = None
        self.call_popup = None
        self.group_call_popup = None
        self.is_muted = False
        self.plugin_manager = None
        self.is_recording_audio_message = False
        self.contacts = set()
        self.chat_history = {'global': []}
        self.initialized = False
        self.active_chat = 'global'
        self.reply_to_message_data = None
        self.edit_message_data = None

        # UI State
        self.left_menu_open = False

        # Setup page properties
        self.page.title = "JustMessenger"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window_width = 1000
        self.page.window_height = 600

        # Lighter dark theme colors from spec and user feedback
        self.primary_gray = "#2d2d2d"
        self.secondary_gray = "#424242"
        self.background_color = "#1a1a1a"
        self.surface_color = "#2d2d2d"
        self.surface_variant_color = "#333333" # Borders and dividers
        self.primary_purple = "#7C4DFF"  # Main accent for buttons, icons
        self.secondary_purple = "#651FFF" # Darker purple
        self.tertiary_purple = "#E1BEE7" # Lighter purple for highlights
        self.error_color = "#FF5252"
        self.success_color = "#4CAF50"

        # Set page background color
        self.page.bgcolor = self.background_color

        # Register fonts
        self.page.fonts = {
            "Roboto": "fonts/Roboto-Regular.ttf",
            "Roboto Bold": "fonts/Roboto-Bold.ttf",
            "NotoSans": "fonts/NotoSans-Regular.ttf",
            "Emoji": "fonts/NotoColorEmoji.ttf"
        }

        # Set a global theme for the app
        self.page.theme = ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=self.primary_purple,
                primary_container=self.secondary_purple,
                background=self.background_color,
                surface=self.surface_color,
                surface_variant=self.surface_variant_color,
                on_primary=ft.colors.WHITE,
                on_background=ft.colors.WHITE,
                on_surface=ft.colors.WHITE,
                error=self.error_color,
            ),
            font_family="Roboto" # Set default font
        )

        # Create navigation drawer (side menu) and assign it to the page
        self.page.drawer = self.create_left_menu_panel()


    def build(self):
        # Create UI components
        self.create_main_layout()
        # The initialization process is now started from main()
        return self.main_layout

    def update(self):
        # In newer Flet versions, update the page directly
        self.page.update()

    def create_main_layout(self):
        # Left Panel (Chat List)
        self.chat_list_panel = self.create_chat_list_panel()

        # Main Chat Area
        self.chat_view_panel = self.create_chat_view_panel()

        # Right Panel (Profile)
        self.profile_panel = self.create_profile_panel()

        # Context menu is now a standalone container, will be added to page.overlay
        self.message_context_menu = ft.Container(
            visible=False, # Visibility controlled by adding/removing from overlay
            bgcolor=self.surface_color,
            border_radius=8,
            border=ft.border.all(1, self.surface_variant_color),
            padding=ft.padding.symmetric(vertical=5),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.colors.with_opacity(0.2, ft.colors.BLACK),
                offset=ft.Offset(2, 2),
            ),
            animate=ft.Animation(100, "ease"),
            width=200,
        )

        # The main layout is now a simple Row, not a complex Stack.
        # This is the core of the architectural fix.
        self.main_layout = ft.Row(
            controls=[
                # Left Panel (Chat List)
                ft.Container(
                    content=self.chat_list_panel,
                    width=300,
                    bgcolor=self.surface_color,
                    border=ft.border.only(right=ft.border.BorderSide(1, self.surface_variant_color))
                ),
                # Main Chat Area
                ft.Container(
                    content=self.chat_view_panel,
                    expand=True,
                    bgcolor=self.background_color
                ),
                # Profile Panel (initially hidden)
                ft.Container(
                    content=self.profile_panel,
                    width=0,  # Hidden initially
                    bgcolor=self.surface_color,
                    border=ft.border.only(left=ft.border.BorderSide(1, self.surface_variant_color)),
                    animate=ft.Animation(300, "ease")
                )
            ],
            expand=True
        )

    def create_chat_list_panel(self):
        # Search field
        self.search_field = ft.TextField(
            hint_text=self.tr.translate("search_chats_hint"),
            border_radius=20,
            filled=True,
            bgcolor=self.surface_variant_color,
            height=40,
            text_size=14,
            content_padding=ft.padding.all(10)
        )

        # Chat list container
        self.chats_container = ft.ListView(expand=True, spacing=5, padding=ft.padding.all(10))

        # New chat and menu buttons
        toolbar = ft.Container(
            content=ft.Row([
                ft.IconButton(
                    icon="menu",
                    icon_color=self.primary_purple,
                    on_click=self.toggle_left_menu
                ),
                ft.Text("JustMessenger", size=18, font_family="Roboto Bold"),
                ft.IconButton(
                    icon=ft.icons.EDIT,
                    icon_color=self.primary_purple,
                    on_click=self.create_new_chat
                )
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            height=50,
            border=ft.border.only(bottom=ft.border.BorderSide(1, self.surface_variant_color))
        )

        return ft.Column([
            toolbar,
            ft.Container(
                content=self.search_field,
                padding=ft.padding.all(10)
            ),
            self.chats_container
        ])

    def create_chat_view_panel(self):
        # Chat header components
        self.chat_avatar = ft.CircleAvatar(
            content=ft.Text("#", color=ft.colors.WHITE),
            bgcolor=self.primary_purple,
            radius=20
        )
        self.chat_title = ft.Text(
            self.tr.translate("global_chat_title"),
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.colors.WHITE
        )
        self.chat_status = ft.Text(
            self.tr.translate("global_chat_status"),
            size=12,
            color=ft.colors.GREY
        )

        # Chat header container
        self.chat_header = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Row([
                            self.chat_avatar,
                            ft.Column([
                                self.chat_title,
                                self.chat_status
                            ])
                        ]),
                        on_click=self.open_profile_panel,
                        expand=True
                    ),
                    ft.Row([
                        ft.IconButton(
                            icon=ft.icons.SEARCH,
                            icon_color=self.primary_purple,
                            tooltip=self.tr.translate("search_in_chat_tooltip"),
                            on_click=self.search_in_chat
                        ),
                        ft.IconButton(
                            icon=ft.icons.PHONE,
                            icon_color=self.primary_purple,
                            on_click=lambda e: self.initiate_call(self.active_chat),
                            tooltip=self.tr.translate("voice_call_tooltip")
                        ),
                        ft.PopupMenuButton(
                           icon=ft.icons.MORE_VERT,
                           items=[
                               ft.PopupMenuItem(text=self.tr.translate("profile_title"), on_click=self.open_profile_panel),
                               ft.PopupMenuItem(),  # divider
                               ft.PopupMenuItem(text=self.tr.translate("clear_history_button"), on_click=self.clear_chat_history),
                               ft.PopupMenuItem(text=self.tr.translate("delete_chat_button"), on_click=self.delete_current_chat),
                           ]
                        )
                    ])
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.all(15),
            height=70,
            border=ft.border.only(bottom=ft.border.BorderSide(1, self.surface_variant_color))
        )

        # Messages container
        self.messages_container = ft.ListView(expand=True, auto_scroll=True, spacing=10)

        # Input area
        self.input_area = self.create_input_area()

        self.emoji_panel = self.create_emoji_panel()

        chat_area = ft.Column([
            self.chat_header,
            ft.Container(
                content=self.messages_container,
                expand=True,
                padding=ft.padding.all(10)
            ),
            self.input_area # Now it's a Column, so it's a direct child
        ])
        
        background_layer = ft.Container(
            bgcolor="#0f0f0f",  # Slightly darker than main background to simulate a background image layer
            expand=True
        )

        return ft.Stack([
            background_layer,
            chat_area,
            ft.Container(
                content=self.emoji_panel,
                right=10,
                bottom=70
            )
        ])

    def create_emoji_panel(self):
        self.emoji_search = ft.TextField(
            hint_text=self.tr.translate("search_emoji_hint"),
            prefix_icon=ft.icons.SEARCH,
            on_change=self.search_emoji,
            height=40,
            border_radius=20,
            filled=True,
            bgcolor=self.background_color
        )

        self.emoji_grid = ft.GridView(
            runs_count=8,
            spacing=5,
            run_spacing=5,
            expand=True
        )

        # Placeholder categories
        categories = {
            "Smileys & Emotion": ft.icons.SENTIMENT_SATISFIED,
            "People & Body": ft.icons.ACCESSIBILITY,
            "Animals & Nature": ft.icons.PETS,
            "Food & Drink": ft.icons.EMOJI_FOOD_BEVERAGE,
            "Travel & Places": ft.icons.AIRPLANEMODE_ACTIVE,
            "Activities": ft.icons.SPORTS_ESPORTS,
            "Objects": ft.icons.LIGHTBULB,
            "Symbols": ft.icons.INFO,
            "Flags": ft.icons.FLAG
        }
        
        category_tabs = [ft.Tab(icon=icon, text=name) for name, icon in categories.items()]
        self.emoji_category_tabs = ft.Tabs(
            tabs=category_tabs,
            on_change=self.load_emojis_for_category,
            selected_index=0
        )
        
        self.load_emojis_for_category(None) # Load initial category

        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=self.emoji_search,
                    padding=ft.padding.all(10)
                ),
                self.emoji_category_tabs,
                ft.Container(
                    content=self.emoji_grid,
                    expand=True,
                    padding=ft.padding.all(10)
                )
            ]),
            width=350,
            height=400,
            bgcolor=self.surface_color,
            border_radius=10,
            border=ft.border.all(1, self.surface_variant_color),
            visible=False
        )

    def create_input_area(self):
        self.edit_info_container = ft.Container(
            visible=False,
            bgcolor=self.surface_variant_color,
            border_radius=ft.border_radius.only(top_left=10, top_right=10),
            padding=ft.padding.symmetric(horizontal=15, vertical=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column([
                        ft.Text(self.tr.translate("edit_message_label"), color=self.primary_purple, weight=ft.FontWeight.BOLD, size=12),
                        ft.Text("", size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, width=self.page.width * 0.5) # Placeholder
                    ]),
                    ft.IconButton(icon=ft.icons.CLOSE, icon_size=16, on_click=self.cancel_edit)
                ]
            )
        )

        self.reply_info_container = ft.Container(
            visible=False,
            bgcolor=self.surface_variant_color,
            border_radius=ft.border_radius.only(top_left=10, top_right=10),
            padding=ft.padding.symmetric(horizontal=15, vertical=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column([
                        ft.Text(self.tr.translate("reply_to_label"), color=self.primary_purple, weight=ft.FontWeight.BOLD, size=12),
                        ft.Text("", size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, width=self.page.width * 0.5) # Placeholder for replied text
                    ]),
                    ft.IconButton(icon=ft.icons.CLOSE, icon_size=16, on_click=self.cancel_reply)
                ]
            )
        )

        self.message_input = ft.TextField(
            hint_text=self.tr.translate("message_hint"),
            border_radius=0, # Will be controlled by the parent container
            filled=True,
            bgcolor=self.surface_color,
            expand=True,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=20, vertical=12),
            on_submit=self.send_message_handler,
            on_change=self.toggle_send_button_visibility, # Add this handler
            shift_enter=True,
            multiline=True,
            min_lines=1,
            max_lines=5
        )

        # Send and Mic buttons that switch
        self.send_button = ft.IconButton(
            icon=ft.icons.SEND,
            icon_color=self.primary_purple,
            on_click=self.send_message_handler,
            tooltip=self.tr.translate("send_button_tooltip")
        )
        self.mic_button = ft.IconButton(
            icon=ft.icons.MIC,
            icon_color=self.primary_purple,
            on_click=self.toggle_voice_recording,
            tooltip=self.tr.translate("record_audio_tooltip")
        )

        self.action_button_switcher = ft.AnimatedSwitcher(
            content=self.mic_button, # Start with mic button
            transition=ft.AnimatedSwitcherTransition.SCALE,
            duration=200,
            reverse_duration=200
        )

        attachment_button = ft.PopupMenuButton(
            icon=ft.icons.ATTACH_FILE,
            tooltip=self.tr.translate("attach_file_tooltip"),
            items=[
                ft.PopupMenuItem(text=self.tr.translate("attach_photo"), icon=ft.icons.PHOTO, on_click=self.attach_photo),
                ft.PopupMenuItem(text=self.tr.translate("attach_file"), icon=ft.icons.INSERT_DRIVE_FILE, on_click=self.attach_file),
                ft.PopupMenuItem(text=self.tr.translate("attach_contact"), icon=ft.icons.CONTACTS, on_click=self.attach_contact),
                ft.PopupMenuItem(text=self.tr.translate("attach_location"), icon=ft.icons.LOCATION_ON, on_click=self.attach_location),
            ]
        )
        # Manually color the icon since PopupMenuButton lacks a direct icon_color property
        # This is a conceptual approach; Flet's direct styling might differ.
        # For now, we rely on the default icon color. A more complex solution would be a custom control.

        input_row = ft.Row([
            attachment_button,
            self.message_input,
            ft.IconButton(
                icon=ft.icons.EMOJI_EMOTIONS,
                icon_color=self.primary_purple,
                on_click=self.toggle_emoji_panel,
                tooltip=self.tr.translate("emoji_tooltip")
            ),
            self.action_button_switcher
        ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.END)

        return ft.Container(
            content=ft.Column(
                [
                    self.edit_info_container,
                    self.reply_info_container,
                    input_row
                ],
                spacing=0
            ),
            border=ft.border.only(top=ft.border.BorderSide(1, self.surface_variant_color)),
            padding=ft.padding.all(10)
        )

    async def update_chat_list(self):
        chat_data = {
            **(self.p2p_manager.peers if self.p2p_manager else {}),
            **(self.p2p_manager.groups if self.p2p_manager else {})
        }
        self.chats_container.controls.clear()

        # Helper to create chat items
        def create_chat_item(chat_id, name, avatar_content, last_message, last_time, unread_count):
            is_selected = self.active_chat == chat_id
            return ft.Container(
                content=ft.ListTile(
                    leading=avatar_content,
                    title=ft.Text(name, weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(last_message, size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                    trailing=ft.Column([
                        ft.Text(last_time, size=10, color=ft.colors.GREY_500),
                        ft.Container(
                            content=ft.Text(str(unread_count), size=10, color=ft.colors.WHITE),
                            bgcolor=self.primary_purple,
                            border_radius=10,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            visible=unread_count > 0
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, horizontal_alignment=ft.CrossAxisAlignment.END, height=40),
                    dense=True
                ),
                bgcolor=self.secondary_gray if is_selected else ft.colors.TRANSPARENT,
                border_radius=8,
                on_click=lambda e, c_id=chat_id: self.switch_chat(c_id),
                padding=ft.padding.symmetric(vertical=5, horizontal=5)
            )

        # Add Global Chat
        global_chat_avatar = ft.CircleAvatar(content=ft.Text("#"), bgcolor=self.primary_purple)
        global_chat_item = create_chat_item('global', self.tr.translate("global_chat_title"), global_chat_avatar, self.tr.translate("global_chat_status"), "", 0)
        self.chats_container.controls.append(global_chat_item)

        # Sort and add other chats
        sorted_chats = sorted(chat_data.values(), key=lambda x: x.get('last_message_time', '1970-01-01'), reverse=True)
        for chat in sorted_chats:
            chat_id = chat['id']
            name = chat['name']
            avatar = ft.CircleAvatar(content=ft.Text(name[0].upper()))
            
            # Get last message info from history
            history = self.chat_history.get(chat_id, [])
            last_message_text = history[-1]['text'] if history else self.tr.translate("no_messages_yet")
            last_message_time_iso = history[-1]['timestamp'] if history else None
            last_message_time = datetime.fromisoformat(last_message_time_iso).strftime('%H:%M') if last_message_time_iso else ""
            
            chat_item = create_chat_item(chat_id, name, avatar, last_message_text, last_message_time, 0) # Unread count is 0 for now
            self.chats_container.controls.append(chat_item)

        if self.page:
            self.update()

    def update_chat_header(self, chat_id):
        if chat_id == 'global':
            chat_name = self.tr.translate("global_chat_title")
            status = self.tr.translate("global_chat_status")
            avatar_char = '#'
        else:
            if not self.p2p_manager: return
            chat_info = self.p2p_manager.peers.get(chat_id) or self.p2p_manager.groups.get(chat_id)
            if not chat_info:
                print(f"Warning: Could not find chat info for {chat_id}")
                return
            chat_name = chat_info['name']
            status = self.tr.translate("status_online") # Placeholder
            avatar_char = chat_name[0].upper()
        
        self.chat_avatar.content.value = avatar_char
        self.chat_title.value = chat_name
        self.chat_status.value = status

    def switch_chat(self, chat_id):
        self.active_chat = chat_id
        self.messages_container.controls.clear()
        
        # Redraw chat list to highlight the new active chat
        self.page.run_task(self.update_chat_list)
        
        history = self.chat_history.get(chat_id, [])
        for msg_data in history:
            self.page.run_task(self.add_message_to_box, msg_data, chat_id)
        
        self.update_chat_header(chat_id)
        # update_chat_list will call update, so this one is for the message box side
        self.update()
        print(f"Switched to chat: {chat_id}")

    def create_profile_panel(self):
        # Определения виджетов, которые будут обновляться
        self.profile_avatar = ft.CircleAvatar(radius=40)
        self.profile_name = ft.Text(self.tr.translate("unknown_user"), size=20, weight=ft.FontWeight.BOLD)
        self.profile_username = ft.Text(self.tr.translate("unknown_username"), size=14, color=ft.colors.GREY)
        self.info_username_subtitle = ft.Text()
        self.info_status_subtitle = ft.Text(self.tr.translate("status_online")) # Placeholder

        # --- Содержимое вкладки "Info" ---
        info_tab_content = ft.Column(
            [
                ft.ListTile(
                    leading=ft.Icon(ft.icons.PERSON, color=self.primary_purple),
                    title=ft.Text(self.tr.translate("username_label")),
                    subtitle=self.info_username_subtitle,
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.INFO_OUTLINE, color=self.primary_purple),
                    title=ft.Text(self.tr.translate("status_label")),
                    subtitle=self.info_status_subtitle,
                ),
                ft.Divider(height=1, color=self.surface_variant_color),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.NOTIFICATIONS, color=self.primary_purple),
                    title=ft.Text(self.tr.translate("notifications_label")),
                    trailing=ft.Switch(value=True),
                    on_click=self.toggle_notifications,
                ),
            ],
            spacing=5
        )

        # --- Содержимое вкладки "Media" ---
        self.profile_media_grid = ft.GridView(
            expand=True,
            runs_count=3,
            max_extent=100,
            child_aspect_ratio=1.0,
            spacing=5,
            run_spacing=5,
            padding=ft.padding.all(10),
        )
        media_tab_content = self.profile_media_grid

        # --- Содержимое вкладки "Files" ---
        self.profile_files_list = ft.ListView(
            expand=True,
            spacing=5,
            padding=ft.padding.all(10),
        )
        files_tab_content = self.profile_files_list

        # Создание вкладок
        profile_tabs = ft.Tabs(
            selected_index=0,
            tabs=[
                ft.Tab(text=self.tr.translate("profile_tab_info"), content=info_tab_content),
                ft.Tab(text=self.tr.translate("profile_tab_media"), content=media_tab_content),
                ft.Tab(text=self.tr.translate("profile_tab_files"), content=files_tab_content),
            ],
            expand=True,
        )

        # Основной макет панели профиля
        return ft.Column(
            controls=[
                # Заголовок с именем и кнопкой закрытия
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(self.tr.translate("profile_title"), size=18, weight=ft.FontWeight.BOLD),
                            ft.IconButton(icon=ft.icons.CLOSE, on_click=self.close_profile_panel, icon_size=20),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    padding=ft.padding.symmetric(horizontal=15, vertical=10),
                    border=ft.border.only(bottom=ft.border.BorderSide(1, self.surface_variant_color))
                ),
                # Секция аватара и имени пользователя
                ft.Container(
                    content=ft.Column(
                        [self.profile_avatar, self.profile_name, self.profile_username],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=5,
                    ),
                    padding=ft.padding.only(top=20, bottom=20),
                ),
                ft.Divider(height=1, color=self.surface_variant_color),
                profile_tabs, # Вкладки занимают оставшееся место
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    async def initialize_app(self):
        """
        Finalizes app initialization after the main UI has been rendered.
        This replaces the old dialog-based startup flow.
        """
        logging.info("Starting initialize_app...")
        
        # Start the callback processing loop in the background
        self.page.run_task(self.process_callbacks_loop)

        config = self.config_manager.load_config()
        # Ensure default username is saved if not present
        if 'username' not in config or not config['username']:
            config['username'] = self.username
        else:
            self.username = config['username'] # Load existing username
        self.config_manager.save_config(config)

        if self.mode.startswith('p2p') and self.mode != 'p2p_bluetooth':
            await self.init_p2p_mode()
        elif self.mode == 'p2p_bluetooth':
            await self.init_bluetooth_mode()
        elif self.mode == 'server':
            await self.init_server_mode()

        await self.apply_audio_settings(config)

        # Apply theme from config
        theme = config.get('theme_mode', 'dark')
        self.page.theme_mode = ft.ThemeMode.DARK if theme == 'dark' else ft.ThemeMode.LIGHT
        
        # Update UI with username
        self.update_username_in_ui()
        self.page.update()

        # Load plugins and complete setup
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.discover_and_load_plugins()
        
        # Update the chat list now that the managers are initialized
        self.page.run_task(self.update_chat_list)
        self.initialized = True
        logging.info("initialize_app finished.")
        # Add a helpful startup message
        await self.add_message_to_box(self.tr.translate("welcome_message_guidance"), 'global')

    def update_username_in_ui(self):
        """Updates all UI elements that display the username."""
        if self.username:
            self.menu_username.value = self.username
            self.menu_avatar.content = ft.Text(self.username[0].upper())
        # Potentially update other places like the profile panel if needed
        self.page.update()

    async def process_callbacks_loop(self):
        """Dedicated loop to process events from the queue."""
        while True:
            try:
                if not self.callback_queue.empty():
                    event = self.callback_queue.get_nowait()
                    await self.process_callback(event)
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in callback processing: {e}")

    async def process_callback(self, event):
        event_type = event[0]

        if event_type == 'bt_message_received':
            _, message = event
            await self.add_message_to_box(message, 'global')
        elif event_type == 'bt_devices_discovered':
            _, devices = event
            await self.show_bt_devices_dialog(devices)
        elif event_type == 'bt_connected':
            _, address = event
            await self.add_message_to_box(f"Bluetooth: Connected to {address}", 'global')
            # Clear scan results and show chat view
            self.chats_container.controls.clear()
            self.chats_container.controls.append(ft.Text(self.tr.translate("bt_chat_active")))
            self.update()
        elif event_type == 'bt_connection_failed':
            _, address = event
            await self.add_message_to_box(f"Bluetooth: Connection to {address} failed", 'global')
        elif event_type == 'bt_disconnected':
            await self.add_message_to_box("Bluetooth: Disconnected", 'global')
            # Show scan button again
            await self.init_bluetooth_mode()
        elif event_type == 'bt_adapter_error':
            _, error_msg = event
            await self.show_popup(self.tr.translate("bt_error_title"), error_msg)
        elif event_type == 'webrtc_offer_created':
            self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'offer', event[1]['offer'])
        elif event_type == 'webrtc_answer_created':
            self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'answer', event[1]['answer'])
        elif event_type == 'mic_level':
            if hasattr(self, 'settings_dialog') and self.settings_dialog.open:
                # Update mic level in settings if open
                pass

    async def show_mode_selection(self):
        # Mode selection dialog
        def on_mode_selected(e, mode):
            self.mode = mode
            self.page.dialog.open = False
            self.page.update()
            self.page.run_task(self.handle_mode_selection)

        modes = [
            {"name": self.tr.translate("mode_p2p_internet"), "mode": "p2p_internet"},
            {"name": self.tr.translate("mode_p2p_local"), "mode": "p2p_local"},
            {"name": self.tr.translate("mode_p2p_bluetooth"), "mode": "p2p_bluetooth"},
            {"name": self.tr.translate("mode_server"), "mode": "server"}
        ]

        mode_buttons = []
        for mode_info in modes:
            mode_buttons.append(
                ft.ElevatedButton(
                    text=mode_info["name"],
                    width=250,
                    height=50,
                    style=ft.ButtonStyle(
                        bgcolor=self.primary_purple,
                        color=ft.colors.WHITE
                    ),
                    on_click=lambda e, m=mode_info["mode"]: on_mode_selected(e, m)
                )
            )

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("select_mode_title"), size=20),
            content=ft.Column(mode_buttons, spacing=10),
            actions_alignment=ft.MainAxisAlignment.CENTER
        )
        self.page.dialog.open = True
        self.page.update()



    async def add_message_to_box(self, message_data, chat_id=None):
        if chat_id is None:
            chat_id = 'global'

        if isinstance(message_data, str):
            message_data = {
                'id': str(uuid.uuid4()),
                'sender': 'System',
                'text': message_data,
                'timestamp': datetime.now().isoformat()
            }

        self.chat_history.setdefault(chat_id, []).append(message_data)

        if self.active_chat != chat_id:
            return

        sender = message_data.get('sender', 'System')
        text = message_data.get('text', '')
        is_self = sender == self.username

        # Create message bubble
        if sender == 'System':
            message_bubble = ft.Container(
                content=ft.Text(
                    text,
                    color=ft.colors.GREY_400,
                    size=12,
                    italic=True
                ),
                alignment=ft.alignment.center,
                padding=ft.padding.all(10)
            )
        else:
            # Telegram-style message bubble
            timestamp = datetime.fromisoformat(message_data.get('timestamp', datetime.now().isoformat()))
            time_text = timestamp.strftime('%H:%M')
            if message_data.get('edited'):
                time_text += " (edited)"

            message_items = []

            # Add reply block if it exists
            if 'reply_to' in message_data and message_data['reply_to']:
                reply_info = message_data['reply_to']
                reply_sender = reply_info.get('sender', 'Unknown')
                reply_text = reply_info.get('text', '')

                reply_display = ft.Container(
                    content=ft.Column([
                        ft.Text(reply_sender, weight=ft.FontWeight.BOLD, color=self.primary_purple, size=12),
                        ft.Text(reply_text, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, size=12, color=ft.colors.WHITE70)
                    ], spacing=2),
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    border=ft.border.only(left=ft.border.BorderSide(2, self.primary_purple)),
                    margin=ft.margin.only(bottom=5)
                )
                message_items.append(reply_display)

            # Add main message text
            message_items.append(ft.Text(text, color=ft.colors.WHITE, size=14))
            
            # Add timestamp
            message_items.append(
                ft.Text(
                    time_text,
                    color=ft.colors.WHITE70,
                    size=10,
                    text_align=ft.TextAlign.RIGHT,
                    margin=ft.margin.only(top=5)
                )
            )

            message_content = ft.Column(message_items, spacing=4, tight=True)

            bubble = ft.Container(
                content=message_content,
                bgcolor=self.primary_purple if is_self else self.surface_color,
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                border_radius=ft.border_radius.only(
                    top_left=18,
                    top_right=18,
                    bottom_left=18 if is_self else 0,
                    bottom_right=0 if is_self else 18
                ),
                max_width=self.page.width * 0.6  # Limit message width
            )

            # Use a Row to align the bubble to the left or right
            # Wrap it in a GestureDetector for the context menu
            message_with_context = ft.GestureDetector(
                content=bubble,
                on_secondary_tap=lambda e, msg=message_data: self.page.run_task(self.show_message_context_menu, e, msg),
            )

            # Use a Row to align the bubble to the left or right
            message_bubble = ft.Row(
                controls=[message_with_context],
                alignment=ft.MainAxisAlignment.END if is_self else ft.MainAxisAlignment.START,
                data=message_data['id'] # Store message ID here for deletion
            )

        # Add to messages container
        self.messages_container.controls.append(message_bubble)
        # With ListView and auto_scroll=True, this is handled automatically
        self.page.update()

    async def send_message_handler(self, e):
        text = self.message_input.value.strip()
        if not text:
            return

        # Handle message editing
        if self.edit_message_data:
            if self.p2p_manager:
                # In a real implementation, a specific message type 'edit' would be sent
                # self.p2p_manager.send_message_edit(self.active_chat, self.edit_message_data['id'], text)
                
                # For now, we simulate it locally
                self.page.run_task(self.handle_local_message_edit, self.active_chat, self.edit_message_data['id'], text)

            self.message_input.value = ""
            self.cancel_edit(None)
            return

        message_data = {
            'id': str(uuid.uuid4()),
            'sender': self.username,
            'text': text,
            'timestamp': datetime.now().isoformat(),
            'status': 'sent'
        }
        
        if self.reply_to_message_data:
            message_data['reply_to'] = {
                'id': self.reply_to_message_data.get('id'),
                'sender': self.reply_to_message_data.get('sender'),
                'text': self.reply_to_message_data.get('text')
            }

        # Handle different communication modes
        if self.mode.startswith('p2p') and self.p2p_manager:
            is_group = self.active_chat in self.p2p_manager.groups

            if self.active_chat == 'global':
                if not self.contacts:
                    await self.show_popup(self.tr.translate("cannot_send_title"), self.tr.translate("add_contact_to_send_message"))
                    return
                for contact_user in self.contacts:
                    self.p2p_manager.send_private_message(contact_user, message_data)
                await self.add_message_to_box(message_data, 'global')

            elif is_group:
                self.p2p_manager.send_group_message(self.active_chat, message_data)
                await self.add_message_to_box(message_data, self.active_chat)

            else:
                self.p2p_manager.send_private_message(self.active_chat, message_data)
                await self.add_message_to_box(message_data, self.active_chat)

        elif self.mode == 'server' and self.server_manager:
            if self.active_chat != 'global':
                self.server_manager.send_group_message(self.active_chat, message_data)
                await self.add_message_to_box(message_data, self.active_chat)
            else:
                await self.add_message_to_box(self.tr.translate("no_global_server_mode"), 'global')

        elif self.mode == 'p2p_bluetooth' and self.bluetooth_manager:
            full_message = f"{self.username}: {text}"
            if self.bluetooth_manager.send_message(full_message):
                await self.add_message_to_box(full_message, 'global')
            else:
                await self.add_message_to_box(self.tr.translate("bt_not_connected"), 'global')

        # Clear input and reset reply state
        self.message_input.value = ""
        if self.reply_to_message_data:
            self.cancel_reply(None) # Pass None as event
        else:
            self.update() # Use async update

        # After sending, toggle button back to mic
        self.page.run_task(self.toggle_send_button_visibility)

    async def toggle_send_button_visibility(self, e=None):
        if self.message_input.value.strip():
            self.action_button_switcher.content = self.send_button
        else:
            self.action_button_switcher.content = self.mic_button
        self.update()

    async def show_popup(self, title, message):
        def on_dismiss(e):
            self.page.dialog.open = False
            self.page.update()

        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, size=18),
            content=ft.Text(message),
            actions=[ft.TextButton(self.tr.translate("ok_button"), on_click=on_dismiss, style=ft.ButtonStyle(color=self.primary_purple))],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=10)
        )
        self.page.dialog.open = True
        self.page.update()

    # Event handlers
    def create_left_menu_panel(self):
        # Placeholder for profile info
        self.menu_avatar = ft.CircleAvatar(content=ft.Text("?"))
        self.menu_username = ft.Text(self.tr.translate("username_label"), weight=ft.FontWeight.BOLD)

        menu_items = ft.Column([
            ft.Container(
                content=ft.ListTile(
                    leading=ft.Icon(ft.icons.GROUP_ADD),
                    title=ft.Text(self.tr.translate("new_group_menu")),
                ),
                on_click=self.create_new_group,
                border_radius=8,
                ink=True
            ),
            ft.Container(
                content=ft.ListTile(
                    leading=ft.Icon(ft.icons.CONTACTS),
                    title=ft.Text(self.tr.translate("contacts_menu")),
                ),
                on_click=self.show_contacts,
                border_radius=8,
                ink=True
            ),
            ft.Container(
                content=ft.ListTile(
                    leading=ft.Icon(ft.icons.SETTINGS),
                    title=ft.Text(self.tr.translate("settings_menu")),
                ),
                on_click=self.open_settings,
                border_radius=8,
                ink=True
            ),
        ])

        return ft.NavigationDrawer(
            controls=[
                ft.Column([
                    ft.Container(
                        content=ft.Column([
                            self.menu_avatar,
                            self.menu_username
                        ]),
                        padding=ft.padding.all(20),
                        bgcolor=self.primary_purple
                    ),
                    menu_items
                ])
            ],
            bgcolor=self.surface_color,
        )

    def close_overlays(self, e=None):
        """Closes any active overlay like the context menu."""
        self.page.overlay.clear()
        if self.message_context_menu:
            self.message_context_menu.visible = False
        self.page.update()

    async def show_message_context_menu(self, e, message_data):
        is_self = message_data.get('sender') == self.username

        # Helper to close the menu and then run the desired action
        async def run_action(action_coro, *args):
            self.close_overlays()
            await action_coro(*args)

        menu_items = [
            ft.ListTile(
                title=ft.Text(self.tr.translate("context_menu_reply")),
                leading=ft.Icon(ft.icons.REPLY),
                dense=True,
                on_click=lambda _e: self.page.run_task(run_action, self.reply_to_message, message_data),
            ),
             ft.ListTile(
                title=ft.Text(self.tr.translate("context_menu_copy")),
                leading=ft.Icon(ft.icons.COPY),
                dense=True,
                on_click=lambda _e: self.page.run_task(run_action, self.copy_message_text, message_data['text']),
            ),
        ]
        if is_self:
            menu_items.append(
                ft.ListTile(
                    title=ft.Text(self.tr.translate("context_menu_edit")),
                    leading=ft.Icon(ft.icons.EDIT),
                    dense=True,
                    on_click=lambda _e: self.page.run_task(run_action, self.edit_message, message_data),
                )
            )
            menu_items.append(ft.ListTile(
                title=ft.Text(self.tr.translate("context_menu_delete"), color=self.error_color),
                leading=ft.Icon(ft.icons.DELETE, color=self.error_color),
                dense=True,
                on_click=lambda _e: self.page.run_task(run_action, self.delete_message, message_data),
            ))

        self.message_context_menu.content = ft.Column(menu_items, spacing=0, tight=True)

        # Position the menu near the cursor
        x = e.global_x
        y = e.global_y
        if x + self.message_context_menu.width > self.page.width - 20:
             x = self.page.width - self.message_context_menu.width - 20
        if y + 100 > self.page.height - 20: # Approximate height
             y = self.page.height - 100 - 20

        self.message_context_menu.left = x
        self.message_context_menu.top = y
        self.message_context_menu.visible = True
        
        # Add a dismissible overlay first, then the menu on top
        self.page.overlay.clear()
        self.page.overlay.append(
            ft.GestureDetector(
                on_tap=self.close_overlays,
                on_secondary_tap=self.close_overlays
            )
        )
        self.page.overlay.append(self.message_context_menu)
        self.page.update()

    async def copy_message_text(self, text):
        self.page.set_clipboard(text)
        await self.show_popup(self.tr.translate("copied_title"), self.tr.translate("copied_message"))

    async def delete_message(self, message_data):
        chat_id = self.active_chat
        message_id = message_data['id']

        # Remove from UI
        control_to_remove = next((c for c in self.messages_container.controls if c.data == message_id), None)
        if control_to_remove:
            self.messages_container.controls.remove(control_to_remove)
            self.update()

        # Remove from history
        if chat_id in self.chat_history:
            self.chat_history[chat_id] = [msg for msg in self.chat_history[chat_id] if msg['id'] != message_id]
        
        # Notify other users (if applicable)
        if self.p2p_manager:
            # This requires a new message type in the P2P protocol, e.g., 'message_delete'
            # self.p2p_manager.broadcast_message_delete(chat_id, message_id)
            pass

    async def reply_to_message(self, message_data):
        self.reply_to_message_data = message_data
        
        reply_text_control = self.reply_info_container.content.controls[0].controls[1]
        reply_text_control.value = message_data['text']
        
        self.reply_info_container.visible = True
        self.update()

    def cancel_reply(self, e):
        self.reply_to_message_data = None
        self.reply_info_container.visible = False
        self.update()

    async def edit_message(self, message_data):
        self.edit_message_data = message_data
        
        edit_text_control = self.edit_info_container.content.controls[0].controls[1]
        edit_text_control.value = message_data['text']
        
        self.message_input.value = message_data['text']
        self.edit_info_container.visible = True
        
        self.message_input.focus()
        self.update()

    def cancel_edit(self, e):
        self.edit_message_data = None
        self.edit_info_container.visible = False
        self.message_input.value = ""
        self.update()

    async def handle_local_message_edit(self, chat_id, message_id, new_text):
        # Find the message control in the UI
        message_control = next((c for c in self.messages_container.controls if c.data == message_id), None)
        if message_control:
            # The structure is Row -> GestureDetector -> Container -> Column -> (ReplyContainer, Text, TimestampText)
            bubble_content_column = message_control.controls[0].content.content
            
            # Find the main text control
            main_text_control = None
            for control in bubble_content_column.controls:
                if isinstance(control, ft.Text) and control.color == ft.colors.WHITE:
                    main_text_control = control
                    break
            
            if main_text_control:
                main_text_control.value = new_text
                # Add (edited) tag - find timestamp and append to it
                timestamp_text_control = bubble_content_column.controls[-1]
                if "(edited)" not in timestamp_text_control.value:
                    timestamp_text_control.value += " (edited)"

        # Update the message in chat history
        if chat_id in self.chat_history:
            for msg in self.chat_history[chat_id]:
                if msg['id'] == message_id:
                    msg['text'] = new_text
                    msg['edited'] = True
                    break
        
        self.update()

    def toggle_left_menu(self, e):
        self.page.drawer.open = not self.page.drawer.open
        self.page.update()

    def open_search(self, e):
        self.page.run_task(self.show_search_dialog)

    async def create_new_chat(self, e):
        await self.show_contact_request_sent_dialog()

    async def show_contact_request_sent_dialog(self):
        def send_request(e):
            username = username_field.value.strip()
            password = password_field.value
            if not username:
                return

            self.page.dialog.open = False
            self.update()

            if self.p2p_manager:
                self.p2p_manager.send_contact_request(username, password)
                self.page.run_task(self.show_popup, self.tr.translate("request_sent_title"), self.tr.translate("contact_request_sent_message").format(username=username))
            else:
                self.page.run_task(self.show_popup, self.tr.translate("error_title"), self.tr.translate("p2p_not_initialized_message"))

        username_field = ft.TextField(label=self.tr.translate("username_label"), width=300)
        password_field = ft.TextField(label=self.tr.translate("password_optional_label"), password=True, can_reveal_password=True, width=300)

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("add_contact_title")),
            content=ft.Column([username_field, password_field]),
            actions=[ft.TextButton(self.tr.translate("send_button"), on_click=send_request), ft.TextButton(self.tr.translate("cancel_button"), on_click=lambda e: self.close_dialog())],
        )
        self.page.dialog.open = True
        self.update()

    async def show_search_dialog(self):
        def on_search(e):
            query = search_field.value.strip()
            if query:
                # Implement search functionality
                self.page.dialog.open = False
                self.update()

        search_field = ft.TextField(
            hint_text=self.tr.translate("global_search_hint"),
            width=400,
            on_submit=on_search
        )

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("global_search_title"), size=20),
            content=search_field,
            actions=[ft.TextButton(self.tr.translate("search_button"), on_click=on_search)],
            actions_alignment=ft.MainAxisAlignment.END
        )
        self.page.dialog.open = True
        self.update()

    async def show_new_chat_dialog(self):
        def on_create(e):
            target = name_field.value.strip()
            chat_type = type_dropdown.value
            if target:
                if self.p2p_manager and chat_type == "Group Chat":
                    self.p2p_manager.create_group(target)
                else:
                    self.page.run_task(self.show_popup, self.tr.translate("not_implemented_title"), self.tr.translate("private_chat_not_implemented_message"))
                self.close_dialog()

        name_field = ft.TextField(
            hint_text=self.tr.translate("enter_username_or_group_hint"),
            width=400
        )

        type_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option(self.tr.translate("private_chat_option")),
                ft.dropdown.Option(self.tr.translate("group_chat_option"))
            ],
            value=self.tr.translate("private_chat_option"),
            width=200
        )

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("new_chat_title"), size=20),
            content=ft.Column([
                type_dropdown,
                name_field
            ]),
            actions=[ft.TextButton(self.tr.translate("create_button"), on_click=on_create)],
            actions_alignment=ft.MainAxisAlignment.END
        )
        self.page.dialog.open = True
        self.update()

    def open_profile_panel(self, e):
        profile_container = self.main_layout.controls[2]
        
        is_opening = profile_container.width == 0
        
        if is_opening:
            self.page.run_task(self.update_profile_panel, self.active_chat)
            profile_container.width = 300
        else:
            profile_container.width = 0
            
        profile_container.animate = ft.Animation(300, "ease")
        self.update()

    async def update_profile_panel(self, chat_id):
        is_group = False
        if chat_id == 'global':
            chat_name = self.tr.translate("global_chat_title")
            username = "#public"
            status = self.tr.translate("global_chat_status")
            avatar_char = "#"
        else:
            if not self.p2p_manager: return
            chat_info = self.p2p_manager.peers.get(chat_id) or self.p2p_manager.groups.get(chat_id)
            if not chat_info: return
            
            is_group = 'members' in chat_info # Простой способ определить, группа ли это
            chat_name = chat_info['name']
            username = f"@{chat_name}"
            
            if is_group:
                member_count = len(chat_info.get('members', []))
                status = f"{member_count} members"
            else:
                 status = self.tr.translate("status_online")  # Placeholder для личных чатов
            avatar_char = chat_name[0].upper()

        # Обновление виджетов
        self.profile_name.value = chat_name
        self.profile_username.value = username
        self.profile_avatar.content = ft.Text(avatar_char, size=30)
        
        # Обновление информации на вкладке "Info"
        self.info_username_subtitle.value = username
        self.info_status_subtitle.value = status
        
        # --- Обновление вкладок "Media" и "Files" ---
        self.profile_media_grid.controls.clear()
        self.profile_files_list.controls.clear()

        history = self.chat_history.get(chat_id, [])
        media_found = False
        files_found = False
        
        # Простой regex для поиска URL изображений
        image_url_pattern = regex.compile(r'https?://\S+\.(?:png|jpg|jpeg|gif|bmp)', regex.IGNORECASE)

        for message in reversed(history): # Показываем новые первыми
            text = message.get('text', '')
            
            # Поиск медиа
            image_urls = image_url_pattern.findall(text)
            if image_urls:
                media_found = True
                for url in image_urls:
                    self.profile_media_grid.controls.append(
                        ft.Image(
                            src=url,
                            fit=ft.ImageFit.COVER,
                            border_radius=ft.border_radius.all(8),
                            error_content=ft.Container(
                                content=ft.Icon(ft.icons.BROKEN_IMAGE, color=ft.colors.GREY),
                                alignment=ft.alignment.center,
                                bgcolor=self.surface_variant_color,
                                border_radius=ft.border_radius.all(8)
                            )
                        )
                    )
            
            # Поиск файлов (логика-заполнитель)
            if "file:" in text.lower():
                files_found = True
                file_name = text.split(' ')[-1] # Простое извлечение
                sender = message.get('sender', 'Unknown')
                timestamp = datetime.fromisoformat(message.get('timestamp')).strftime('%Y-%m-%d')

                self.profile_files_list.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.icons.INSERT_DRIVE_FILE, color=self.primary_purple),
                        title=ft.Text(file_name, size=14, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                        subtitle=ft.Text(f"by {sender} on {timestamp}", size=12),
                        on_click=lambda e, f=file_name: self.page.run_task(self.show_popup, self.tr.translate("download_popup_title"), self.tr.translate("download_popup_message").format(file_name=f))
                    )
                )

        # Добавляем плейсхолдеры, если ничего не найдено
        if not media_found:
            self.profile_media_grid.controls.append(
                ft.Container(content=ft.Text(self.tr.translate("no_media_placeholder"), text_align=ft.TextAlign.CENTER), alignment=ft.alignment.center, expand=True)
            )
        if not files_found:
            self.profile_files_list.controls.append(
                 ft.Container(content=ft.Text(self.tr.translate("no_files_placeholder"), text_align=ft.TextAlign.CENTER), alignment=ft.alignment.center, expand=True)
            )

        self.update()

    def close_profile_panel(self, e):
        profile_container = self.main_layout.controls[2]
        if profile_container.width > 0:
            profile_container.width = 0
            profile_container.animate = ft.Animation(300, "ease")
            self.update()

    def switch_profile_tab(self, e):
        selected_index = e.control.selected_index
        if selected_index == 0:
            self.tab_content.content = self.profile_info_tab
        elif selected_index == 1:
            self.tab_content.content = self.profile_media_tab
        elif selected_index == 2:
            self.tab_content.content = self.profile_files_tab
        self.update()

    def toggle_notifications(self, e):
        # Placeholder for notification toggle logic
        print(f"Toggling notifications for {self.active_chat}")

    def toggle_emoji_panel(self, e):
        if not hasattr(self, 'emoji_panel'):
            print("Emoji panel not initialized yet.")
            return

        is_opening = not self.emoji_panel.visible
        
        if is_opening:
            # Load initial category if not loaded
            if not self.emoji_grid.controls:
                self.load_emojis_for_category(None)
        
        self.emoji_panel.visible = is_opening
        self.emoji_panel.animate = ft.Animation(300, "ease")
        self.emoji_panel.opacity = 1 if is_opening else 0
        
        self.update()

    async def create_new_group(self, e):
        if self.page.drawer.open:
            self.toggle_left_menu(e)
            await asyncio.sleep(0.3)  # Wait for drawer animation
        
        def on_create(e_create):
            group_name = name_field.value.strip()
            if group_name and self.p2p_manager:
                self.p2p_manager.create_group(group_name)
                self.close_dialog()
                self.page.run_task(self.show_popup, self.tr.translate("group_created_title"), self.tr.translate("group_created_message").format(group_name=group_name))

        name_field = ft.TextField(label=self.tr.translate("group_name_label"), width=300)
        
        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("create_new_group_title")),
            content=name_field,
            actions=[
                ft.TextButton(self.tr.translate("cancel_button"), on_click=lambda e_cancel: self.close_dialog()),
                ft.TextButton(self.tr.translate("create_button"), on_click=on_create, style=ft.ButtonStyle(color=self.primary_purple))
            ],
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=10)
        )
        self.page.dialog.open = True
        self.update()

    async def show_contacts(self, e):
        if self.page.drawer.open:
            self.toggle_left_menu(e)
            await asyncio.sleep(0.3)  # Wait for drawer animation

        async def add_contact_click(e_add):
            self.close_dialog()
            await self.show_contact_request_sent_dialog()

        contact_list = ft.ListView(spacing=10, padding=10)
        if self.contacts:
            for contact_name in sorted(list(self.contacts)):
                contact_list.controls.append(
                    ft.ListTile(
                        leading=ft.CircleAvatar(content=ft.Text(contact_name[0].upper())),
                        title=ft.Text(contact_name)
                    )
                )
        else:
            contact_list.controls.append(ft.Text(self.tr.translate("no_contacts_placeholder")))

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("contacts_title")),
            content=ft.Container(
                content=contact_list,
                width=350,
                height=400
            ),
            actions=[
                ft.TextButton(self.tr.translate("add_contact_button"), on_click=add_contact_click, style=ft.ButtonStyle(color=self.primary_purple)),
                ft.TextButton(self.tr.translate("close_button"), on_click=lambda e_close: self.close_dialog())
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=10)
        )
        self.page.dialog.open = True
        self.update()

    def select_emoji(self, e, emoji_char):
        self.message_input.value += emoji_char
        self.update()

    def search_emoji(self, e):
        query = e.data.lower()
        if not query:
            self.load_emojis_for_category(None) # Reset to current category
            return
            
        filtered_emojis = self.emoji_manager.search_emoji(query)
        self.update_emoji_grid(filtered_emojis)
        
    def load_emojis_for_category(self, e):
        category_index = self.emoji_category_tabs.selected_index if e else 0
        category_name = self.emoji_category_tabs.tabs[category_index].text
        
        emojis = self.emoji_manager.get_emojis_by_category(category_name)
        self.update_emoji_grid(emojis)

    def update_emoji_grid(self, emojis):
        self.emoji_grid.controls.clear()
        for emoji_char in emojis[:100]: # Limit for performance
            self.emoji_grid.controls.append(
                ft.Container(
                    content=ft.Text(emoji_char, size=24),
                    on_click=partial(self.select_emoji, emoji_char=emoji_char),
                    border_radius=8,
                    padding=ft.padding.all(5),
                    ink=True
                )
            )
        self.update()

    def toggle_voice_recording(self, e):
        # Implement voice recording toggle
        pass

    def attach_photo(self, e):
        self.page.run_task(self.show_popup, self.tr.translate("not_implemented_title"), self.tr.translate("feature_not_implemented_message"))

    def attach_file(self, e):
        self.page.run_task(self.show_popup, self.tr.translate("not_implemented_title"), self.tr.translate("feature_not_implemented_message"))

    def attach_contact(self, e):
        self.page.run_task(self.show_popup, self.tr.translate("not_implemented_title"), self.tr.translate("feature_not_implemented_message"))

    def attach_location(self, e):
        self.page.run_task(self.show_popup, self.tr.translate("not_implemented_title"), self.tr.translate("feature_not_implemented_message"))

    async def show_feature_pending_dialog(self, feature_name: str):
        """Shows a standardized dialog for features that are not yet implemented."""
        await self.show_popup(
            self.tr.translate("feature_pending_title"),
            self.tr.translate("feature_pending_message").format(feature_name=feature_name)
        )

    def search_in_chat(self, e):
       self.page.run_task(self.show_feature_pending_dialog, self.tr.translate("search_in_chat_tooltip"))

    def clear_chat_history(self, e):
       self.page.run_task(self.show_feature_pending_dialog, self.tr.translate("clear_history_button"))

    def delete_current_chat(self, e):
       self.page.run_task(self.show_feature_pending_dialog, self.tr.translate("delete_chat_button"))

    def initiate_call(self, target_username):
        if not target_username or target_username == 'global':
            self.page.run_task(self.show_popup, self.tr.translate("error_title"), self.tr.translate("no_call_in_global_chat_message"))
            return

        if self.webrtc_manager.peer_connections:
            self.page.run_task(self.show_popup, self.tr.translate("error_title"), self.tr.translate("already_in_call_message"))
            return

        if self.mode.startswith('p2p') and target_username not in self.contacts:
            self.page.run_task(self.show_popup, self.tr.translate("add_contact_title"), self.tr.translate("add_contact_to_call_message").format(username=target_username))
            # In a real app, you might trigger the contact request here.
            return

        self.page.run_task(self.add_message_to_box, f"Calling {target_username}...", 'global')
        self.webrtc_manager.start_call(target_username)

    async def open_settings(self, e):
        if self.page.drawer.open:
            self.toggle_left_menu(e)
            await asyncio.sleep(0.3)  # Wait for drawer animation
        
        self.settings_dialog = self.create_settings_dialog()
        self.page.dialog = self.settings_dialog
        self.settings_dialog.open = True
        self.update()

    def create_settings_dialog(self):
        self.settings_controls = {} # Словарь для хранения всех созданных контролов
        config = self.config_manager.load_config()

        # --- Фабрики для страниц настроек ---

        def create_appearance_settings():
            username_field = ft.TextField(
                label=self.tr.translate("username_label"),
                value=self.username
            )

            theme_mode_switch = ft.Switch(
                label=self.tr.translate("dark_mode_label"),
                value=self.page.theme_mode == ft.ThemeMode.DARK,
                on_change=self.toggle_theme_mode
            )
            
            language_dropdown = ft.Dropdown(
                label=self.tr.translate("language_label"),
                value=config.get('language', 'en'),
                options=[
                    ft.dropdown.Option("en", "English"),
                    ft.dropdown.Option("ru", "Русский"),
                ]
            )

            self.settings_controls['username'] = username_field
            self.settings_controls['theme_mode'] = theme_mode_switch
            self.settings_controls['language'] = language_dropdown
            
            return ft.Column([
                username_field,
                ft.Row([ft.Text(self.tr.translate("theme_label")), theme_mode_switch]),
                language_dropdown
            ])

        def create_audio_settings():
            input_slider = ft.Slider(min=0, max=100, divisions=10, value=config.get('input_volume', 80), label=self.tr.translate("input_volume_slider_label"))
            output_slider = ft.Slider(min=0, max=100, divisions=10, value=config.get('output_volume', 80), label=self.tr.translate("output_volume_slider_label"))
            self.settings_controls['input_volume'] = input_slider
            self.settings_controls['output_volume'] = output_slider
            return ft.Column([
                ft.Text(self.tr.translate("input_volume_label")), input_slider,
                ft.Text(self.tr.translate("output_volume_label")), output_slider
            ])

        def create_hotkey_settings():
            ptt_label = ft.Text(self.tr.translate("ptt_hotkey_label") + f": {config.get('push_to_talk_hotkey', self.tr.translate('hotkey_not_set'))}")
            mute_label = ft.Text(self.tr.translate("mute_hotkey_label") + f": {config.get('mute_hotkey', self.tr.translate('hotkey_not_set'))}")
            self.settings_controls['ptt_hotkey_label'] = ptt_label
            self.settings_controls['mute_hotkey_label'] = mute_label
            return ft.Column([
                ptt_label,
                ft.ElevatedButton(self.tr.translate("set_ptt_hotkey_button"), on_click=lambda e: self.listen_for_hotkey('ptt')),
                mute_label,
                ft.ElevatedButton(self.tr.translate("set_mute_hotkey_button"), on_click=lambda e: self.listen_for_hotkey('mute')),
            ])
            
        def create_security_settings():
            password_field = ft.TextField(label=self.tr.translate("contact_request_password_label"), value=config.get('contact_request_password', ''), password=True, can_reveal_password=True)
            self.settings_controls['contact_password'] = password_field
            return ft.Column([password_field])

        def create_plugin_settings():
            plugin_list = ft.ListView(spacing=5, padding=0)
            if self.plugin_manager and self.plugin_manager.loaded_plugins:
                for name, _ in self.plugin_manager.loaded_plugins.items():
                    plugin_list.controls.append(ft.Text(name))
            else:
                plugin_list.controls.append(ft.Text(self.tr.translate("no_plugins_loaded")))

            def open_plugins_folder(e):
                plugins_path = os.path.join(os.getcwd(), 'plugins')
                if not os.path.exists(plugins_path):
                    os.makedirs(plugins_path)
                os.startfile(plugins_path)

            return ft.Column([
                ft.Container(content=plugin_list, height=150, border=ft.border.all(1, self.surface_variant_color), border_radius=8, padding=10),
                ft.ElevatedButton(self.tr.translate("open_plugins_folder_button"), on_click=open_plugins_folder),
            ])

        # --- Основная логика диалога ---
        
        self.settings_title = ft.Text(self.tr.translate("settings_title"), size=20, weight=ft.FontWeight.BOLD)
        self.settings_content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

        def show_main_menu(e=None):
            self.settings_title.value = self.tr.translate("settings_title")
            self.back_button.visible = False
            self.settings_content.controls.clear()
            self.settings_content.controls.extend([
                ft.Container(
                    content=ft.ListTile(leading=ft.Icon(ft.icons.PALETTE_OUTLINED), title=ft.Text(self.tr.translate("appearance_settings"))),
                    on_click=lambda e: show_page(self.tr.translate("appearance_settings"), create_appearance_settings),
                    border_radius=8,
                    ink=True
                ),
                ft.Container(
                    content=ft.ListTile(leading=ft.Icon(ft.icons.AUDIOTRACK_OUTLINED), title=ft.Text(self.tr.translate("audio_settings"))),
                    on_click=lambda e: show_page(self.tr.translate("audio_settings"), create_audio_settings),
                    border_radius=8,
                    ink=True
                ),
                ft.Container(
                    content=ft.ListTile(leading=ft.Icon(ft.icons.KEYBOARD_OUTLINED), title=ft.Text(self.tr.translate("hotkeys_settings"))),
                    on_click=lambda e: show_page(self.tr.translate("hotkeys_settings"), create_hotkey_settings),
                    border_radius=8,
                    ink=True
                ),
                ft.Container(
                    content=ft.ListTile(leading=ft.Icon(ft.icons.SECURITY_OUTLINED), title=ft.Text(self.tr.translate("security_settings"))),
                    on_click=lambda e: show_page(self.tr.translate("security_settings"), create_security_settings),
                    border_radius=8,
                    ink=True
                ),
                ft.Container(
                    content=ft.ListTile(leading=ft.Icon(ft.icons.EXTENSION_OUTLINED), title=ft.Text(self.tr.translate("plugins_settings"))),
                    on_click=lambda e: show_page(self.tr.translate("plugins_settings"), create_plugin_settings),
                    border_radius=8,
                    ink=True
                ),
            ])
            self.update()

        def show_page(title, content_factory):
            self.settings_title.value = title
            self.back_button.visible = True
            self.settings_content.controls.clear()
            self.settings_content.controls.append(content_factory())
            self.update()

        self.back_button = ft.IconButton(icon=ft.icons.ARROW_BACK, on_click=show_main_menu, visible=False)
        show_main_menu() # Показать главное меню при инициализации

        return ft.AlertDialog(
            modal=True,
            title=ft.Row([self.back_button, self.settings_title]),
            content=ft.Container(
                content=self.settings_content,
                width=400,
                height=350,
                padding=ft.padding.symmetric(vertical=10)
            ),
            actions=[
                ft.TextButton(self.tr.translate("save_button"), on_click=self.save_settings, style=ft.ButtonStyle(color=self.primary_purple)),
                ft.TextButton(self.tr.translate("close_button"), on_click=self.close_settings),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=10),
        )

    def close_settings(self, e):
        self.settings_dialog.open = False
        self.update()

    def save_settings(self, e):
        config = self.config_manager.load_config()
        
        # Собираем значения из словаря self.settings_controls
        if 'input_volume' in self.settings_controls:
            config['input_volume'] = self.settings_controls['input_volume'].value
        if 'output_volume' in self.settings_controls:
            config['output_volume'] = self.settings_controls['output_volume'].value
        if 'contact_password' in self.settings_controls:
            config['contact_request_password'] = self.settings_controls['contact_password'].value
        if 'language' in self.settings_controls:
            config['language'] = self.settings_controls['language'].value
        if 'username' in self.settings_controls:
            new_username = self.settings_controls['username'].value.strip()
            if new_username and new_username != self.username:
                # Username changed, need to handle re-initialization of P2P manager
                logging.info(f"Username changed from {self.username} to {new_username}")
                # For now, we just update it. A real app might need to restart networking.
                self.username = new_username
                config['username'] = new_username
                self.update_username_in_ui()

        self.config_manager.save_config(config)
        
        # Применяем только те настройки, которые могли быть изменены
        self.page.run_task(self.apply_audio_settings, config)
        self.page.run_task(self.apply_language_settings, config)
        self.hotkey_manager.update_hotkeys(config)
        
        self.close_settings(e)

    def listen_for_hotkey(self, key_type):
        popup_content = ft.Text(self.tr.translate("press_any_key_message"))
        self.page.dialog = ft.AlertDialog(title=ft.Text(self.tr.translate("listening_for_hotkey_title")), content=popup_content)
        self.page.dialog.open = True
        self.update()

        def on_press(key):
            try:
                hotkey_str = key.char
            except AttributeError:
                hotkey_str = str(key)

            config = self.config_manager.load_config()
            if key_type == 'ptt':
                config['push_to_talk_hotkey'] = hotkey_str
                self.settings_controls['ptt_hotkey_label'].value = self.tr.translate("ptt_hotkey_label") + f": {hotkey_str}"
            elif key_type == 'mute':
                config['mute_hotkey'] = hotkey_str
                self.settings_controls['mute_hotkey_label'].value = self.tr.translate("mute_hotkey_label") + f": {hotkey_str}"
            
            self.config_manager.save_config(config)
            self.hotkey_manager.update_hotkeys(config)

            # Stop the listener and close the popup
            listener.stop()
            self.page.dialog.open = False
            # Re-open the main settings dialog
            self.open_settings(None)
            self.update()
            return False # Stop the listener

        listener = keyboard.Listener(on_press=on_press)
        listener.start()

    def toggle_theme_mode(self, e):
        self.page.theme_mode = ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT
        # Сохраняем настройку
        config = self.config_manager.load_config()
        config['theme_mode'] = 'dark' if self.page.theme_mode == ft.ThemeMode.DARK else 'light'
        self.config_manager.save_config(config)
        self.update()

    # Manager initialization methods
    async def init_p2p_mode(self):
        p2p_mode_type = 'local' if self.mode == 'p2p_local' else 'internet'
        self.p2p_manager = P2PManager(self.username, self.chat_history, mode=p2p_mode_type)
        self.webrtc_manager.p2p_manager = self.p2p_manager

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
            await self.add_message_to_box(self.tr.translate("p2p_init_failed_message"), 'global')
            return

        await self.add_message_to_box(self.tr.translate("p2p_started_message").format(mode=p2p_mode_type, username=self.username))

    async def init_bluetooth_mode(self):
        if not self.bluetooth_manager:
            self.bluetooth_manager = BluetoothManager(self.username, self.callback_queue)
            self.bluetooth_manager.register_callback('devices_discovered', self.on_bt_devices_discovered)
            self.bluetooth_manager.start()
        
        await self.add_message_to_box(self.tr.translate("bt_started_message"), 'global')
        
        # Clear chat list and add a scan button
        self.chats_container.controls.clear()
        scan_btn = ft.ElevatedButton(
            self.tr.translate("scan_bt_devices_button"),
            icon=ft.icons.BLUETOOTH_SEARCHING,
            on_click=self.scan_for_bt_devices,
            style=ft.ButtonStyle(bgcolor=self.primary_purple)
        )
        self.chats_container.controls.append(
            ft.Container(
                content=scan_btn,
                alignment=ft.alignment.center,
                padding=20
            )
        )
        self.update()

    async def init_server_mode(self):
        # Server login would be implemented here
        await self.add_message_to_box(self.tr.translate("server_mode_init_message"), 'global')

    def scan_for_bt_devices(self, e):
        if self.bluetooth_manager:
            self.page.run_task(self.add_message_to_box, self.tr.translate("bt_scanning_message"), 'global')
            self.bluetooth_manager.discover_devices()

    def on_bt_devices_discovered(self, devices):
        self.page.run_task(self.show_bt_devices_dialog, devices)

    async def show_bt_devices_dialog(self, devices):
        if not devices:
            await self.show_popup(self.tr.translate("no_devices_found_title"), self.tr.translate("no_bt_devices_found_message"))
            return

        def connect_to_device(e, addr, name):
            self.close_dialog()
            self.page.run_task(self.add_message_to_box, f"Connecting to {name} ({addr})...", 'global')
            self.bluetooth_manager.connect_to_device(addr)

        device_list = ft.ListView(spacing=10, padding=20)
        for addr, name in devices:
            device_list.controls.append(
                ft.ListTile(
                    title=ft.Text(name),
                    subtitle=ft.Text(addr),
                    on_click=lambda e, a=addr, n=name: connect_to_device(e, a, n)
                )
            )

        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("nearby_bt_devices_title")),
            content=ft.Container(
                content=device_list,
                width=400,
                height=300
            ),
            actions=[ft.TextButton(self.tr.translate("close_button"), on_click=lambda e: self.close_dialog())]
        )
        self.page.dialog.open = True
        self.update()

    # All the callback methods from the original kivy_client.py
    # These callbacks are now updated to work with the Flet UI
    def on_peer_discovered(self, username, address_info):
        print(f"Peer discovered: {username}")
        self.page.run_task(self.update_chat_list)

    def on_peer_lost(self, username):
        print(f"Peer lost: {username}")
        self.page.run_task(self.update_chat_list)

    def on_peer_found(self, username):
        print(f"Peer found: {username}")

    def on_peer_not_found(self, username):
        self.page.run_task(self.show_popup, self.tr.translate("search_failed_title"), self.tr.translate("user_not_found_message").format(username=username))

    def p2p_message_received(self, message_data):
        sender = message_data.get('sender')
        if sender and sender != self.username:
            # For P2P messages, the sender's username is the chat ID
            self.page.run_task(self.add_message_to_box, message_data, sender)

    def on_webrtc_signal(self, sender, signal_type, data):
        if signal_type == 'offer':
            self.page.run_task(self.show_incoming_call_dialog, sender, data)
        elif signal_type == 'answer':
            self.page.run_task(self.add_message_to_box, f"Call with {sender} accepted and connected.", 'global')
            self.webrtc_manager.handle_answer(sender, data)
            # The initiator shows the call dialog only after the peer answers.
            self.page.run_task(self.show_call_dialog, sender)
        elif signal_type == 'hangup':
            self.webrtc_manager.end_call(sender)
            if self.call_popup:
                self.call_popup.open = False
                self.update()
            self.page.run_task(self.add_message_to_box, f"Call with {sender} ended.", 'global')
        elif signal_type == 'busy':
            self.page.run_task(self.add_message_to_box, f"Call failed: {sender} is busy.", 'global')
            self.page.run_task(self.hang_up_call, sender)

    def on_secure_channel_established(self, username):
        self.page.run_task(self.add_message_to_box, f"Secure connection with {username} established.", 'global')

    def on_group_created(self, group_id, group_name, admin_username):
        self.page.run_task(self.add_message_to_box, f"Group '{group_name}' created.", 'global')
        self.page.run_task(self.update_chat_list)

    def on_group_message_received(self, group_id, message_data):
        self.page.run_task(self.add_message_to_box, message_data, group_id)

    def on_history_received(self, chat_id, history):
        self.page.run_task(self.add_message_to_box, f"Received history for '{chat_id}'", 'global')

    def on_incoming_group_invite(self, group_id, group_name, admin_username):
        self.page.run_task(self.show_group_invite_dialog, group_id, group_name, admin_username)

    def on_group_joined(self, group_id, username):
        self.page.run_task(self.add_message_to_box, f"'{username}' joined group", group_id)
        self.page.run_task(self.update_chat_list)

    def on_group_invite_response(self, group_id, username, accepted):
        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', 'the group')
        if accepted:
            message = f"{username} accepted your invitation to join {group_name}."
        else:
            message = f"{username} declined your invitation to join {group_name}."
        self.page.run_task(self.show_popup, self.tr.translate("invitation_response_title"), message)

    def on_incoming_group_call(self, group_id, admin_username, sample_rate):
        self.page.run_task(self.show_incoming_group_call_dialog, group_id, admin_username)

    def handle_group_call_response(self, group_id, username, response):
        if self.active_group_call == group_id:
            status = 'joined' if response else 'declined'
            message = f"{username} has {status} the call."
            self.page.run_task(self.add_message_to_box, message, group_id)

    def handle_group_call_hang_up(self, group_id, username):
        if self.active_group_call == group_id:
            self.page.run_task(self.add_message_to_box, f"{username} left the call.", group_id)
        if username == self.username:
            self.active_group_call = None
            if self.group_call_popup:
                self.group_call_popup.open = False
                self.update()

    def on_user_kicked(self, group_id, kicked_username, admin_username):
        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', 'a group')
        if kicked_username == self.username:
            message = f"You have been kicked from '{group_name}' by {admin_username}."
            self.page.run_task(self.show_popup, self.tr.translate("kicked_from_group_title"), message)
            if self.active_chat == group_id:
                self.switch_chat('global')
        else:
            message = f"{kicked_username} was kicked from '{group_name}' by {admin_username}."
            self.page.run_task(self.add_message_to_box, message, group_id)
        
        self.page.run_task(self.update_chat_list)

    def on_incoming_contact_request(self, sender_username, payload):
        self.page.run_task(self.show_incoming_contact_request_dialog, sender_username, payload)

    def on_contact_request_response(self, sender_username, accepted):
        if accepted:
            self.contacts.add(sender_username)
            self.page.run_task(self.show_popup, self.tr.translate("contact_added_title"), self.tr.translate("contact_request_accepted_message").format(username=sender_username))
            self.page.run_task(self.update_chat_list)
        else:
            self.page.run_task(self.show_popup, self.tr.translate("request_declined_title"), self.tr.translate("contact_request_declined_message").format(username=sender_username))

    def on_user_list_update(self, users):
        # User list update handling
        pass

    def on_initial_data_received(self, groups, users):
        # Initial data handling
        pass

    def on_user_joined_call(self, group_id, username):
        # User joined call handling
        pass

    def on_user_left_call(self, group_id, username):
        # User left call handling
        pass

    async def apply_audio_settings(self, config):
        input_volume = config.get('input_volume', 80)
        output_volume = config.get('output_volume', 80)

        input_gain = (input_volume or 80) / 100.0
        output_gain = (output_volume or 80) / 100.0

        self.audio_manager.set_volume(input_gain, 'input')
        self.audio_manager.set_volume(output_gain, 'output')

        await self.add_message_to_box(self.tr.translate("audio_settings_applied_message"), 'global')

    # --- Language and Theme Settings ---
    async def apply_language_settings(self, config):
        lang = config.get('language', 'en')
        if self.tr.get_language() != lang:
            self.tr.set_language(lang)
            await self.rebuild_ui_with_translation()
            await self.show_popup(
                self.tr.translate("language_changed_title"),
                self.tr.translate("language_change_restart_message")
            )

    async def rebuild_ui_with_translation(self):
        """
        This method updates the text of all UI components after a language change.
        It's crucial to update every visible text element here.
        """
        print("Rebuilding UI with new translations...")

        # Page Title
        self.page.title = self.tr.get("app_title")

        # Left Panel (Chat List)
        self.search_field.hint_text = self.tr.translate("search_chats_hint")
        # The main title "JustMessenger" is also in the toolbar
        if isinstance(self.chat_list_panel.controls[0].content.controls[1], ft.Text):
            self.chat_list_panel.controls[0].content.controls[1].value = self.tr.translate("app_title")

        # Left Menu (Hamburger Menu)
        self.menu_username.value = self.username if self.username else self.tr.translate("username_label")
        # Drawer contains a Column, which contains the header Container and the menu_items Column
        if self.page.drawer and self.page.drawer.controls:
            menu_items_column = self.page.drawer.controls[0].controls[1]
            menu_items_column.controls[0].title.value = self.tr.translate("new_group_menu")
            menu_items_column.controls[1].title.value = self.tr.translate("contacts_menu")
            menu_items_column.controls[2].title.value = self.tr.translate("settings_menu")

        # Center Panel (Chat View)
        self.update_chat_header(self.active_chat) # This handles chat title and status
        self.chat_header.content.controls[1].controls[0].tooltip = self.tr.translate("search_in_chat_tooltip")
        self.chat_header.content.controls[1].controls[1].tooltip = self.tr.translate("voice_call_tooltip")

        # Input Area
        self.message_input.hint_text = self.tr.translate("message_hint")
        self.input_area.content.controls[0].content.controls[0].controls[0].value = self.tr.translate("edit_message_label") # Edit message title
        self.input_area.content.controls[1].content.controls[0].controls[0].value = self.tr.translate("reply_to_label") # Reply to title
        self.input_area.content.controls[2].controls[0].tooltip = self.tr.translate("attach_file_tooltip") # Attach file button

        # Emoji Panel
        self.emoji_search.hint_text = self.tr.translate("search_emoji_hint")
        
        # Right Panel (Profile)
        profile_header = self.profile_panel.controls[0].content
        profile_header.controls[0].value = self.tr.translate("profile_title")
        
        info_tab_list = self.profile_panel.controls[3].tabs[0].content.controls
        info_tab_list[0].title.value = self.tr.translate("username_label")
        info_tab_list[1].title.value = self.tr.translate("status_label")
        info_tab_list[3].title.value = self.tr.translate("notifications_label")

        profile_tabs_bar = self.profile_panel.controls[3]
        profile_tabs_bar.tabs[0].text = self.tr.translate("profile_tab_info")
        profile_tabs_bar.tabs[1].text = self.tr.translate("profile_tab_media")
        profile_tabs_bar.tabs[2].text = self.tr.translate("profile_tab_files")
        
        # Update currently visible profile data
        await self.update_profile_panel(self.active_chat)
        
        # Update chat list (it has its own logic with chat names etc)
        await self.update_chat_list()

        # Update any open dialogs if necessary (e.g., settings)
        if self.page.dialog and hasattr(self, 'settings_dialog') and self.page.dialog == self.settings_dialog:
             # Re-create and show the settings dialog to reflect language changes
            current_title = self.settings_title.value
            self.close_settings(None)
            self.open_settings(None)
            # Try to restore the subpage if it was open
            # This is complex, for now, just reopening is enough to show the main menu translated

        self.update()
        print("UI rebuild complete.")

    # --- Call Management ---

    async def hang_up_call(self, peer_username=None):
        """Hangs up a specific call or all active calls."""
        if not self.webrtc_manager.peer_connections:
            return

        peers_to_hangup = list(self.webrtc_manager.peer_connections.keys())
        if peer_username:
            if peer_username in peers_to_hangup:
                peers_to_hangup = [peer_username]
            else:
                return # Not in a call with this user

        for peer in peers_to_hangup:
            self.webrtc_manager.end_call(peer)
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(peer, 'hangup', {})

        if self.call_popup:
            self.call_popup.open = False
            self.call_popup = None

        await self.add_message_to_box(self.tr.translate("call_ended_message"), 'global')
        self.update()


    async def show_incoming_call_dialog(self, peer_username, offer_sdp):
        if self.webrtc_manager.peer_connections:
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(peer_username, 'busy', {})
            return

        async def accept_call(e):
            self.page.dialog.open = False
            self.update()
            self.webrtc_manager.handle_offer(peer_username, offer_sdp)
            await self.show_call_dialog(peer_username)
            await self.add_message_to_box(self.tr.translate("call_accepted_message").format(username=peer_username), 'global')

        async def decline_call(e):
            self.page.dialog.open = False
            self.update()
            if self.p2p_manager:
                self.p2p_manager.send_webrtc_signal(peer_username, 'hangup', {})
            await self.add_message_to_box(self.tr.translate("call_declined_message").format(username=peer_username), 'global')

        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("incoming_call_title"), text_align=ft.TextAlign.CENTER),
            content=ft.Column([
                ft.CircleAvatar(content=ft.Text(peer_username[0].upper()), radius=30),
                ft.Text(peer_username, size=18, weight=ft.FontWeight.BOLD)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            actions=[
                ft.IconButton(icon=ft.icons.CALL_END, bgcolor=self.error_color, icon_color=ft.colors.WHITE, on_click=decline_call, tooltip=self.tr.translate("decline_button")),
                ft.IconButton(icon=ft.icons.CALL, bgcolor=self.success_color, icon_color=ft.colors.WHITE, on_click=accept_call, tooltip=self.tr.translate("accept_button")),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=20),
            content_padding=ft.padding.all(25)
        )
        self.page.dialog.open = True
        self.update()


    async def show_call_dialog(self, peer_username):
        if self.call_popup:
            self.call_popup.open = False

        def toggle_mute(e):
            self.is_muted = not self.is_muted
            self.webrtc_manager.set_mute(self.is_muted)
            mute_button.icon = ft.icons.MIC_OFF if self.is_muted else ft.icons.MIC
            mute_button.bgcolor = self.primary_purple if self.is_muted else self.secondary_gray
            mute_status = 'ON' if self.is_muted else 'OFF'
            self.page.run_task(self.add_message_to_box, self.tr.translate("mute_status_message").format(status=mute_status), 'global')
            self.update()

        async def hang_up(e):
            await self.hang_up_call(peer_username)

        mute_button = ft.IconButton(
            icon=ft.icons.MIC_OFF if self.is_muted else ft.icons.MIC,
            on_click=toggle_mute,
            tooltip=self.tr.translate("mute_unmute_tooltip"),
            icon_size=30,
            bgcolor=self.secondary_gray,
            icon_color=ft.colors.WHITE
        )

        self.call_popup = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("call_in_progress_title"), text_align=ft.TextAlign.CENTER),
            content=ft.Column([
                ft.CircleAvatar(content=ft.Text(peer_username[0].upper()), radius=30),
                ft.Text(peer_username, size=18, weight=ft.FontWeight.BOLD),
                ft.Text("00:00", size=14) # Placeholder for call timer
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            actions=[
                mute_button,
                ft.IconButton(icon=ft.icons.CALL_END, bgcolor=self.error_color, icon_color=ft.colors.WHITE, on_click=hang_up, tooltip=self.tr.translate("hang_up_button"), icon_size=30),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            actions_vertical_alignment=ft.CrossAxisAlignment.CENTER,
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=20),
            content_padding=ft.padding.all(25)
        )
        self.page.dialog = self.call_popup
        self.call_popup.open = True
        self.update()

    def close_dialog(self):
        if self.page.dialog:
            self.page.dialog.open = False
            self.update()

    async def show_incoming_contact_request_dialog(self, sender_username, payload):
        password_required = payload.get('password_protected', False)
        password_field = ft.TextField(label=self.tr.translate("password_label"), password=True, can_reveal_password=True, visible=password_required)

        def respond(e, accepted):
            password = password_field.value if password_required else None
            self.close_dialog()

            if self.p2p_manager:
                self.p2p_manager.send_contact_request_response(sender_username, accepted, password)
            if accepted and not password_required: # If password required, acceptance is confirmed on successful channel establishment
                self.contacts.add(sender_username)
                self.page.run_task(self.update_chat_list)


        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("contact_request_title")),
            content=ft.Column([
                ft.Text(self.tr.translate("incoming_contact_request_message").format(username=sender_username)),
                password_field
            ]),
            actions=[
                ft.TextButton(self.tr.translate("decline_button"), on_click=lambda e: respond(e, False)),
                ft.TextButton(self.tr.translate("accept_button"), on_click=lambda e: respond(e, True), style=ft.ButtonStyle(color=self.primary_purple)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=self.surface_color,
            shape=ft.RoundedRectangleBorder(radius=10)
        )
        self.page.dialog.open = True
        self.update()

    # --- Group Management Dialogs ---

    async def show_invite_to_group_dialog(self):
        def send_invite(e):
            username = username_field.value.strip()
            if not username:
                return
            
            self.close_dialog()
            if self.p2p_manager and self.active_chat in self.p2p_manager.groups:
                self.p2p_manager.invite_to_group(self.active_chat, username)
                self.page.run_task(self.show_popup, self.tr.translate("invitation_sent_title"), self.tr.translate("group_invitation_sent_message").format(group_name=self.p2p_manager.groups[self.active_chat]['name'], username=username))
            else:
                self.page.run_task(self.show_popup, self.tr.translate("error_title"), self.tr.translate("group_invitation_error_message"))

        username_field = ft.TextField(label=self.tr.translate("username_to_invite_label"), width=300)
        
        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("invite_to_group_title")),
            content=username_field,
            actions=[
                ft.TextButton(self.tr.translate("send_invite_button"), on_click=send_invite),
                ft.TextButton(self.tr.translate("cancel_button"), on_click=lambda e: self.close_dialog()),
            ],
        )
        self.page.dialog.open = True
        self.update()

    async def show_group_invite_dialog(self, group_id, group_name, admin_username):
        def respond(e, accepted):
            self.close_dialog()
            if self.p2p_manager:
                self.p2p_manager.respond_to_group_invite(group_id, admin_username, accepted)
            if accepted:
                self.page.run_task(self.add_message_to_box, self.tr.translate("joined_group_message").format(group_name=group_name), 'global')

        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("group_invitation_title")),
            content=ft.Text(self.tr.translate("incoming_group_invitation_message").format(group_name=group_name, username=admin_username)),
            actions=[
                ft.TextButton(self.tr.translate("accept_button"), on_click=lambda e: respond(e, True)),
                ft.TextButton(self.tr.translate("decline_button"), on_click=lambda e: respond(e, False)),
            ],
        )
        self.page.dialog.open = True
        self.update()

    async def show_incoming_group_call_dialog(self, group_id, admin_username):
        if self.active_group_call or self.webrtc_manager.peer_connections:
            # Auto-reject if already in any call
            if self.p2p_manager:
                self.p2p_manager.respond_to_group_call(group_id, False)
            return

        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', 'a group')

        async def respond(e, accepted):
            self.close_dialog()
            if self.p2p_manager:
                self.p2p_manager.respond_to_group_call(group_id, accepted)
            if accepted:
                self.active_group_call = group_id
                await self.show_group_call_dialog(group_id)

        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("incoming_group_call_title")),
            content=ft.Text(self.tr.translate("incoming_group_call_message").format(username=admin_username, group_name=group_name)),
            actions=[
                ft.TextButton(self.tr.translate("join_button"), on_click=lambda e: respond(e, True)),
                ft.TextButton(self.tr.translate("decline_button"), on_click=lambda e: respond(e, False)),
            ],
        )
        self.page.dialog.open = True
        self.update()

    async def show_group_call_dialog(self, group_id):
        if self.group_call_popup:
            self.group_call_popup.open = False
        
        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', 'Group Call')

        def toggle_mute_group(e):
            self.is_muted = not self.is_muted
            # Group call mute logic would go in audio manager
            mute_button.icon = ft.icons.MIC_OFF if self.is_muted else ft.icons.MIC
            self.update()

        async def hang_up_group(e):
            if self.p2p_manager:
                self.p2p_manager.hang_up_group_call(group_id)
            self.active_group_call = None
            self.group_call_popup.open = False
            self.update()

        mute_button = ft.IconButton(icon=ft.icons.MIC, on_click=toggle_mute_group)
        
        self.group_call_popup = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.tr.translate("in_call_title").format(group_name=group_name)),
            content=ft.Row([mute_button], alignment=ft.MainAxisAlignment.CENTER),
            actions=[ft.TextButton(self.tr.translate("leave_call_button"), on_click=hang_up_group, style=ft.ButtonStyle(color=ft.colors.RED))],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        self.page.dialog = self.group_call_popup
        self.group_call_popup.open = True
        self.update()

    def leave_group(self, e):
        if self.p2p_manager and self.active_chat in self.p2p_manager.groups:
            group_id = self.active_chat
            self.p2p_manager.leave_group(group_id)
            self.switch_chat('global')
            self.page.run_task(self.update_chat_list)
            self.page.run_task(self.show_popup, self.tr.translate("group_left_title"), self.tr.translate("group_left_message"))

    async def show_kick_user_dialog(self):
        def kick_user(e):
            username = username_field.value.strip()
            if not username:
                return
            
            self.close_dialog()
            if self.p2p_manager and self.active_chat in self.p2p_manager.groups:
                self.p2p_manager.kick_user_from_group(self.active_chat, username)

        username_field = ft.TextField(label=self.tr.translate("username_to_kick_label"), width=300)
        
        self.page.dialog = ft.AlertDialog(
            title=ft.Text(self.tr.translate("kick_user_from_group_title")),
            content=username_field,
            actions=[
                ft.TextButton(self.tr.translate("kick_button"), on_click=kick_user),
                ft.TextButton(self.tr.translate("cancel_button"), on_click=lambda e: self.close_dialog()),
            ],
        )
        self.page.dialog.open = True
        self.update()


async def main(page: ft.Page):
    logging.info("Main function started.")
    app = VoiceChatApp(page)
    
    logging.info("Building main layout...")
    page.add(app.build())
    
    logging.info("Performing initial page update.")
    page.update()
    
    logging.info("Initializing application...")
    # The app logic will now be kicked off after the UI is built
    await app.initialize_app()

if __name__ == '__main__':
    ft.app(target=main)

