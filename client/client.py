import sys
import os
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

# Kivy imports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay, MediaPlayer, MediaRecorder
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelHeader
from kivy.uix.switch import Switch
from kivy.clock import mainthread, Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.core.text import LabelBase
from kivy.metrics import dp

# --- Set borderless before anything else ---
Window.borderless = False
Window.size = (1000, 600)

# Project imports
try:
    from p2p_manager import P2PManager
    import stun
    from plugin_manager import PluginManager
    from translator import Translator
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# --- Constants ---

# ------------------- Manager Classes -------------------
class BluetoothManager:
        def __init__(self, username, callback_queue):
            self.username = username
            self.callback_queue = callback_queue
            self.server_sock = None
            self.client_sock = None
            self.running = False
            self.server_thread = None
            self.client_thread = None
            self.uuid = "94f39d29-7d6d-437d-973b-fba39e49d4ee" # Unique UUID for this app
    
        def start(self):
            self.running = True
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            print("BluetoothManager server started.")
    
        def stop(self):
            self.running = False
            if self.server_sock:
                self.server_sock.close()
            if self.client_sock:
                self.client_sock.close()
            print("BluetoothManager stopped.")
    
        def discover_devices(self):
            """Scans for nearby Bluetooth devices."""
            print("Scanning for Bluetooth devices...")
            try:
                nearby_devices = bluetooth.discover_devices(duration=8, lookup_names=True, flush_cache=True, lookup_class=False)
                self.callback_queue.put(('bt_devices_discovered', nearby_devices))
                return nearby_devices
            except Exception as e:
                print(f"Error discovering devices: {e}")
                self.callback_queue.put(('bt_discovery_error', str(e)))
                return []
    
        def run_server(self):
            """Listens for incoming Bluetooth connections."""
            try:
                self.server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                self.server_sock.bind(("", bluetooth.PORT_ANY))
                self.server_sock.listen(1)
    
                port = self.server_sock.getsockname()[1]
    
                bluetooth.advertise_service(self.server_sock, "VoiceChatApp",
                                          service_id=self.uuid,
                                          service_classes=[self.uuid, bluetooth.SERIAL_PORT_CLASS],
                                          profiles=[bluetooth.SERIAL_PORT_PROFILE])
                
                print(f"Waiting for connection on RFCOMM channel {port}")
                
                while self.running:
                    try:
                        client_sock, client_info = self.server_sock.accept()
                        self.callback_queue.put(('bt_connection_received', client_info))
                        # Handle the connection in a new thread
                        handler_thread = threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True)
                        handler_thread.start()
                    except bluetooth.btcommon.BluetoothError:
                        # This happens when the socket is closed
                        break
            except OSError as e:
                # This specific error (10040 or similar) can happen if the BT adapter is off
                print(f"Bluetooth server OS error: {e}")
                self.callback_queue.put(('bt_adapter_error', 'Please ensure your Bluetooth adapter is turned on.'))
            except Exception as e:
                print(f"Bluetooth server error: {e}")
                self.callback_queue.put(('bt_server_error', str(e)))
    
        def handle_client(self, sock):
            """Handles an incoming client connection."""
            try:
                while self.running:
                    data = sock.recv(1024)
                    if not data:
                        break
                    message = data.decode('utf-8')
                    self.callback_queue.put(('bt_message_received', message))
            except Exception as e:
                print(f"Error handling BT client: {e}")
            finally:
                sock.close()
    
        def connect_to_device(self, addr):
            """Connects to a specific Bluetooth device."""
            print(f"Connecting to {addr}...")
            try:
                service_matches = bluetooth.find_service(uuid=self.uuid, address=addr)
    
                if len(service_matches) == 0:
                    self.callback_queue.put(('bt_connection_failed', "Service not found."))
                    return
    
                first_match = service_matches[0]
                port = first_match["port"]
                name = first_match["name"]
                host = first_match["host"]
    
                sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                sock.connect((host, port))
                
                self.client_sock = sock
                self.callback_queue.put(('bt_connection_successful', name))
                
                # Start a thread to listen for messages from this connection
                self.client_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
                self.client_thread.start()
    
            except Exception as e:
                print(f"Error connecting to device: {e}")
                self.callback_queue.put(('bt_connection_failed', str(e)))
    
        def listen_for_messages(self):
            """Listens for messages on the client socket."""
            try:
                while self.running and self.client_sock:
                    data = self.client_sock.recv(1024)
                    if not data:
                        break
                    message = data.decode('utf-8')
                    self.callback_queue.put(('bt_message_received', message))
            except Exception as e:
                print(f"Error in client listening thread: {e}")
            finally:
                if self.client_sock:
                    self.client_sock.close()
                    self.client_sock = None
                self.callback_queue.put(('bt_disconnected', None))
    
    
        def send_message(self, message):
            """Sends a message to the connected device."""
            if self.client_sock:
                try:
                    self.client_sock.send(message.encode('utf-8'))
                    return True
                except Exception as e:
                    print(f"Error sending BT message: {e}")
                    return False
            return False
    
class EmojiManager:
    def __init__(self):
        self.categorized_emojis = self._get_windows_emojis()

    def _get_windows_emojis(self):
        """Generates a categorized dictionary of emojis using Windows Unicode ranges."""
        # These are common Unicode blocks for emojis.
        # It's not a perfect categorization, but it's robust and doesn't rely on external libraries.
        categories = {
            'Smileys & People': list(range(0x1F600, 0x1F650)),
            'Symbols & Pictographs': list(range(0x1F300, 0x1F600)),
            'Transport & Map': list(range(0x1F680, 0x1F700)),
            'Dingbats': list(range(0x2700, 0x27C0)),
            'Misc Symbols': list(range(0x2600, 0x2700)),
        }
        
        # Convert integer code points to characters
        char_categories = {}
        for category, code_points in categories.items():
            char_categories[category] = [chr(cp) for cp in code_points]
            
        return char_categories

    def get_categorized_emojis(self):
        """Returns a dictionary of emojis grouped by category."""
        return self.categorized_emojis
    
    
class HotkeyManager(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.hotkey = None
        self.callback = None
        self.running = True
        self.listener = None

    def set_hotkey(self, key_combination):
        """
        Sets the hotkey to listen for.
        key_combination should be a set of pynput.keyboard.Key or pynput.keyboard.KeyCode
        e.g., {keyboard.Key.ctrl, keyboard.KeyCode.from_char('m')}
        """
        self.hotkey = key_combination

    def register_callback(self, func):
        self.callback = func

    def run(self):
        # A set of currently pressed keys
        current_keys = set()

        def on_press(key):
            if self.hotkey and key in self.hotkey:
                current_keys.add(key)
                if all(k in current_keys for k in self.hotkey):
                    if self.callback:
                        self.callback()
            
        def on_release(key):
            try:
                current_keys.remove(key)
            except KeyError:
                pass # Key was not in the set

        # Collect events until released
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            self.listener = listener
            listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()


class WebRTCManager(threading.Thread):
    def __init__(self, callback_queue):
        super().__init__(daemon=True)
        self.callback_queue = callback_queue
        self.loop = None
        self.peer_connections = {} # {peer_username: RTCPeerConnection}
        self.audio_sender = {} # {peer_username: sender_track}
        self.running = True

    def run(self):
        """Runs the asyncio event loop in this dedicated thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    # --- Public methods to be called from other threads ---
    
    async def _create_peer_connection(self, peer_username):
        """Coroutine to create and configure a peer connection."""
        pc = RTCPeerConnection()
        self.peer_connections[peer_username] = pc

        @pc.on("track")
        async def on_track(track):
            print(f"Track {track.kind} received from {peer_username}")
            # Here we would play the audio. This needs a player implementation.
            if track.kind == "audio":
                # Kivy cannot play raw audio frames directly. We need a way to buffer
                # and play this. This is a complex part of the integration.
                self.callback_queue.put(('webrtc_audio_received', {'peer': peer_username, 'track': track}))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {peer_username} is {pc.connectionState}")
            if pc.connectionState == "failed":
                await pc.close()
                del self.peer_connections[peer_username]

        return pc

    def start_call(self, peer_username):
        """Initiates a call to a peer."""
        if not self.loop: return
        future = asyncio.run_coroutine_threadsafe(self._start_call(peer_username), self.loop)
        return future.result()

    async def _start_call(self, peer_username):
        pc = await self._create_peer_connection(peer_username)
        
        # Add local audio track
        # This is a placeholder for getting microphone audio.
        # It will be implemented properly later.
        
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # The offer needs to be sent to the peer via the signaling channel (our P2PManager)
        sdp_offer = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        self.callback_queue.put(('webrtc_offer_created', {'peer': peer_username, 'offer': sdp_offer}))

    def handle_offer(self, peer_username, offer_sdp):
        """Handles an incoming offer from a peer."""
        if not self.loop: return
        future = asyncio.run_coroutine_threadsafe(self._handle_offer(peer_username, offer_sdp), self.loop)
        return future.result()

    async def _handle_offer(self, peer_username, offer_sdp):
        pc = await self._create_peer_connection(peer_username)
        
        offer = RTCSessionDescription(sdp=offer_sdp["sdp"], type=offer_sdp["type"])
        await pc.setRemoteDescription(offer)
        
        # Add local audio track (placeholder)
        
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        sdp_answer = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        self.callback_queue.put(('webrtc_answer_created', {'peer': peer_username, 'answer': sdp_answer}))
        
    def handle_answer(self, peer_username, answer_sdp):
        if not self.loop: return
        asyncio.run_coroutine_threadsafe(self._handle_answer(peer_username, answer_sdp), self.loop)
        
    async def _handle_answer(self, peer_username, answer_sdp):
        pc = self.peer_connections.get(peer_username)
        if pc:
            answer = RTCSessionDescription(sdp=answer_sdp["sdp"], type=answer_sdp["type"])
            await pc.setRemoteDescription(answer)

    async def _close_peer_connection(self, peer_username):
        if peer_username in self.peer_connections:
            pc = self.peer_connections[peer_username]
            await pc.close()
            del self.peer_connections[peer_username]
            
    def end_call(self, peer_username):
        if not self.loop: return
        asyncio.run_coroutine_threadsafe(self._close_peer_connection(peer_username), self.loop)
    
class ConfigManager:
    def __init__(self, key_path='secret.key', config_path='config.dat'):
        self.key_path = key_path
        self.config_path = config_path
        self.key = self.load_or_generate_key()
        self.cipher = Fernet(self.key)

    def load_or_generate_key(self):
        """Загружает ключ шифрования или генерирует новый, если он не найден."""
        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            return key

    def save_config(self, config_data):
        """Шифрует и сохраняет данные конфигурации."""
        try:
            # Сериализуем словарь в JSON-строку, затем в байты
            data_bytes = json.dumps(config_data).encode('utf-8')
            encrypted_data = self.cipher.encrypt(data_bytes)
            with open(self.config_path, 'wb') as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении конфигурации: {e}")
            return False

    def load_config(self):
        """Загружает и расшифровывает данные конфигурации."""
        if not os.path.exists(self.config_path):
            return {}  # Возвращаем пустой словарь, если конфига нет

        try:
            with open(self.config_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data_bytes = self.cipher.decrypt(encrypted_data)
            # Десериализуем из байтов в JSON-строку, затем в словарь
            config_data = json.loads(decrypted_data_bytes.decode('utf-8'))
            return config_data
        except Exception as e:
            print(f"Ошибка при загрузке или расшифровке конфигурации: {e}")
            # Если расшифровка не удалась (например, ключ изменился), возвращаем пустой конфиг
            return {}
    
class ServerManager(threading.Thread):
    def __init__(self, host, port, username, password, chat_history):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.chat_history = chat_history # Reference to the main app's history
        self.sock = None
        self.running = True
        self.callbacks = {}
        self.zstd_c = zstd.ZstdCompressor()
        self.zstd_d = zstd.ZstdDecompressor()

    def register_callback(self, event_name, func):
        self.callbacks[event_name] = func

    def _trigger_callback(self, event_name, *args):
        if event_name in self.callbacks:
            self.callbacks[event_name](*args)

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.login()
            self.listen_for_messages()
        except Exception as e:
            print(f"ServerManager Error: {e}")
            self._trigger_callback('connection_failed', str(e))
        finally:
            if self.sock:
                self.sock.close()

    def listen_for_messages(self):
        unpacker = msgpack.Unpacker(raw=False)
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                
                # Decompress the received chunk immediately
                try:
                    decompressed_data = self.zstd_d.decompress(data)
                    unpacker.feed(decompressed_data)
                    for unpacked in unpacker:
                        self.handle_command(unpacked)
                except zstd.ZstdError:
                    # This might happen if we receive a partial compressed frame.
                    # A more robust solution would buffer compressed chunks.
                    # For now, we assume each recv() gets at least one full message.
                    print("Warning: Could not decompress chunk, might be partial.")
                    continue

            except (ConnectionResetError, ConnectionAbortedError):
                print("Connection to server lost.")
                break
            except Exception as e:
                print(f"Error receiving data from server: {e}")
                break
        self._trigger_callback('disconnected')

    def _send_command(self, command, payload=None):
        if not self.sock:
            return
        try:
            message = {'command': command, 'payload': payload or {}}
            packed_message = msgpack.packb(message, use_bin_type=True)
            compressed_message = self.zstd_c.compress(packed_message)
            self.sock.sendall(compressed_message)
        except Exception as e:
            print(f"Error sending command '{command}': {e}")

    def handle_command(self, message):
        try:
            command = message.get('command')
            payload = message.get('payload')

            if command == 'login_success':
                # We don't really need to do anything here, but it's good to have.
                pass
            elif command == 'login_failed':
                self._trigger_callback('login_failed', payload)
            elif command == 'info':
                self._trigger_callback('info_received', payload)
            elif command == 'user_list_update':
                self._trigger_callback('user_list_update', payload.get('users'))
            elif command == 'group_message':
                self._trigger_callback('group_message_received', payload.get('group_id'), payload.get('message_data'))
            elif command == 'group_created':
                 self._trigger_callback('group_created', payload.get('group_id'), payload.get('group_name'), payload.get('admin'))
            elif command == 'group_invite':
                self._trigger_callback('incoming_group_invite', payload.get('group_id'), payload.get('group_name'), payload.get('admin'))
            elif command == 'group_invite_response':
                 self._trigger_callback('group_invite_response', payload.get('group_id'), payload.get('username'), payload.get('accepted'))
            elif command == 'user_joined_group':
                self._trigger_callback('group_joined', payload.get('group_id'), payload.get('username'))
            elif command == 'history_response':
                self._trigger_callback('history_received', payload.get('chat_id'), payload.get('history'))
            elif command == 'initial_data':
                self._trigger_callback('initial_data_received', payload.get('groups'), payload.get('users'))
            elif command == 'incoming_group_call':
                self._trigger_callback('incoming_group_call', payload.get('group_id'), payload.get('admin'), payload.get('sample_rate'))
            elif command == 'user_joined_call':
                self._trigger_callback('user_joined_call', payload.get('group_id'), payload.get('username'))
            elif command == 'user_left_call':
                self._trigger_callback('user_left_call', payload.get('group_id'), payload.get('username'))
            elif command == 'user_kicked':
                self._trigger_callback('user_kicked', payload.get('group_id'), payload.get('kicked_user'), payload.get('admin'))


        except Exception as e:
            print(f"Error handling server command: {e} - Message: {message}")

    def login(self):
        self._send_command('login', {'username': self.username, 'password': self.password})

    def send_group_message(self, group_id, message_data):
        self._send_command('group_message', {'group_id': group_id, 'message_data': message_data})

    def create_group(self, group_name):
        self._send_command('create_group', {'group_name': group_name})

    def invite_to_group(self, group_id, target_username):
        self._send_command('invite_to_group', {'group_id': group_id, 'username': target_username})

    def send_group_invite_response(self, group_id, accepted):
        self._send_command('group_invite_response', {'group_id': group_id, 'accepted': accepted})
        
    def request_history(self, chat_id):
        self._send_command('request_history', {'chat_id': chat_id})

    def start_group_call(self, group_id, sample_rate):
        self._send_command('start_group_call', {'group_id': group_id, 'sample_rate': sample_rate})

    def join_group_call(self, group_id, udp_addr):
        self._send_command('join_group_call', {'group_id': group_id, 'udp_addr': udp_addr})

    def leave_group_call(self, group_id):
        self._send_command('leave_group_call', {'group_id': group_id})

    def kick_user_from_group(self, group_id, username):
        self._send_command('kick_from_group', {'group_id': group_id, 'username': username})

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except OSError:
                pass
        print("ServerManager stopped.")
    
    
# --- UI-Agnostic Threads ---



# --- Kivy Popups & Widgets ---

class AnimatedPopup(Popup):
    def open(self, *args, **kwargs):
        self.scale = 0.8
        self.opacity = 0
        super().open(*args, **kwargs)
        anim = Animation(scale=1, opacity=1, d=0.2, t='out_quad')
        anim.start(self)

class RootLayout(BoxLayout): pass
class ChatLayout(BoxLayout): pass

class CallPopup(AnimatedPopup):
    def __init__(self, peer_username, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.is_muted = False
        self.title = self.tr.get('call_title', 'Call')
        self.size_hint = (0.6, 0.4)
        self.auto_dismiss = False
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('call_label', peer_username=peer_username)))
        self.mute_button = Button(text=self.tr.get('mute_button'))
        self.mute_button.bind(on_press=self.toggle_mute)
        layout.add_widget(self.mute_button)
        hang_up_button = Button(text=self.tr.get('hang_up_button'))
        hang_up_button.bind(on_press=self.hang_up)
        layout.add_widget(hang_up_button)
        self.content = layout
        self.register_event_type('on_mute_toggle')

    def toggle_mute(self, instance):
        self.is_muted = not self.is_muted
        self.mute_button.text = self.tr.get('unmute_button') if self.is_muted else self.tr.get('mute_button')
        self.dispatch('on_mute_toggle', self.is_muted)

    def hang_up(self, instance):
        self.dismiss()

    def on_mute_toggle(self, is_muted):
        pass

class ContactRequestPopup(AnimatedPopup):
    def __init__(self, username, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('contact_request_title', 'Contact Request')
        self.size_hint = (0.7, 0.4)
        self.auto_dismiss = False

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('contact_request_text', username=username)))
        
        btn_layout = BoxLayout(spacing=10)
        accept_btn = Button(text=self.tr.get('accept_button', 'Accept'))
        decline_btn = Button(text=self.tr.get('decline_button', 'Decline'))
        btn_layout.add_widget(accept_btn)
        btn_layout.add_widget(decline_btn)
        layout.add_widget(btn_layout)
        
        self.content = layout
        
        accept_btn.bind(on_press=self.accept)
        decline_btn.bind(on_press=self.decline)
        
        self.register_event_type('on_response')

    def accept(self, instance):
        self.dispatch('on_response', True)
        self.dismiss()

    def decline(self, instance):
        self.dispatch('on_response', False)
        self.dismiss()

    def on_response(self, accepted):
        pass

# The EmojiPopup class is no longer needed and will be removed.
# The functionality will be integrated into the main app class.

class GroupCallPopup(AnimatedPopup):
    # Placeholder for now
    def __init__(self, group_name, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = f"Group Call - {group_name}"
        self.size_hint = (0.7, 0.6)
        self.auto_dismiss = False
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        self.participants_list = BoxLayout(orientation='vertical')
        layout.add_widget(Label(text="Participants:"))
        layout.add_widget(self.participants_list)
        hang_up_button = Button(text=self.tr.get('hang_up_button'))
        hang_up_button.bind(on_press=self.hang_up)
        layout.add_widget(hang_up_button)
        self.content = layout

    def hang_up(self, instance):
        self.dismiss()


class ManageGroupPopup(AnimatedPopup):
    def __init__(self, translator, members, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('manage_group_title', 'Manage Group')
        self.size_hint = (0.7, 0.8)
        
        layout = BoxLayout(orientation='vertical', spacing=5, padding=10)
        
        scroll_view = ScrollView()
        scroll_content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        scroll_content.bind(minimum_height=scroll_content.setter('height'))
        
        for member in members:
            member_layout = BoxLayout(size_hint_y=None, height=40)
            member_label = Label(text=member)
            kick_button = Button(text='Kick', size_hint_x=None, width=80)
            kick_button.bind(on_press=partial(self.kick_user, member))
            
            member_layout.add_widget(member_label)
            member_layout.add_widget(kick_button)
            scroll_content.add_widget(member_layout)
            
        scroll_view.add_widget(scroll_content)
        layout.add_widget(scroll_view)
        
        close_button = Button(text=self.tr.get('close_button', 'Close'), size_hint_y=None, height=44)
        close_button.bind(on_press=self.dismiss)
        layout.add_widget(close_button)
        
        self.content = layout
        self.register_event_type('on_kick_user')

    def kick_user(self, username, instance):
        self.dispatch('on_kick_user', username)
        self.dismiss()

    def on_kick_user(self, username):
        pass


class AudioMessageWidget(BoxLayout):
    def __init__(self, filepath, sender, **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self.sound = SoundLoader.load(filepath)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 40
        
        self.label = Label(text=f"Audio from {sender}")
        self.play_button = Button(text='▶ Play', size_hint_x=None, width=80)
        self.play_button.bind(on_press=self.toggle_play)
        
        self.add_widget(self.label)
        self.add_widget(self.play_button)

    def toggle_play(self, instance):
        if not self.sound:
            return
        if self.sound.state == 'play':
            self.sound.stop()
            self.play_button.text = '▶ Play'
        else:
            self.sound.play()
            self.play_button.text = '❚❚ Pause'
            self.sound.bind(on_stop=self.on_sound_stop)

    def on_sound_stop(self, instance):
        self.play_button.text = '▶ Play'


class ModeSelectionPopup(AnimatedPopup):
    def __init__(self, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('mode_selection_title')
        self.size_hint = (0.6, 0.5)
        self.auto_dismiss = False
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('mode_selection_label')))
        p2p_internet_button = Button(text=self.tr.get('mode_p2p_internet'))
        p2p_internet_button.bind(on_press=lambda x: self.select_mode('p2p_internet'))
        layout.add_widget(p2p_internet_button)
        p2p_local_button = Button(text=self.tr.get('mode_p2p_local'))
        p2p_local_button.bind(on_press=lambda x: self.select_mode('p2p_local'))
        layout.add_widget(p2p_local_button)
        p2p_bluetooth_button = Button(text=self.tr.get('mode_p2p_bluetooth', 'P2P (Bluetooth)'))
        p2p_bluetooth_button.bind(on_press=lambda x: self.select_mode('p2p_bluetooth'))
        layout.add_widget(p2p_bluetooth_button)
        server_button = Button(text=self.tr.get('mode_client_server'))
        server_button.bind(on_press=lambda x: self.select_mode('server'))
        layout.add_widget(server_button)
        self.content = layout

    def select_mode(self, mode):
        self.mode = mode
        self.dismiss()

class UsernamePopup(AnimatedPopup):
    def __init__(self, translator, current_username, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('username_dialog_title')
        self.size_hint = (0.8, 0.4)
        self.auto_dismiss = False
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('username_dialog_label')))
        self.username_input = TextInput(text=current_username, multiline=False)
        layout.add_widget(self.username_input)
        ok_button = Button(text="OK")
        ok_button.bind(on_press=self.validate_username)
        layout.add_widget(ok_button)
        self.content = layout

    def validate_username(self, instance):
        username = self.username_input.text.strip()
        if username:
            self.username = username
            self.dismiss()

class ServerLoginPopup(AnimatedPopup):
    def __init__(self, translator, config, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('server_login_title', 'Connect to Server')
        self.size_hint = (0.8, 0.6)
        self.auto_dismiss = False
        
        server_config = config.get('server', {})
        
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('server_ip_label', 'Server IP:')))
        self.ip_input = TextInput(text=server_config.get('host', '127.0.0.1'), multiline=False)
        layout.add_widget(self.ip_input)
        
        layout.add_widget(Label(text=self.tr.get('server_port_label', 'Server Port:')))
        self.port_input = TextInput(text=str(server_config.get('port', 12345)), multiline=False)
        layout.add_widget(self.port_input)
        
        layout.add_widget(Label(text=self.tr.get('server_password_label', 'Password (optional):')))
        self.password_input = TextInput(text='', multiline=False, password=True)
        layout.add_widget(self.password_input)
        
        connect_button = Button(text=self.tr.get('connect_button', 'Connect'))
        connect_button.bind(on_press=self.connect)
        layout.add_widget(connect_button)
        
        self.content = layout

    def connect(self, instance):
        self.server_ip = self.ip_input.text.strip()
        self.server_port = self.port_input.text.strip()
        self.password = self.password_input.text
        
        if not self.server_ip or not self.server_port:
            # Maybe show an error label
            return
            
        try:
            self.server_port = int(self.server_port)
            self.dismiss()
        except ValueError:
            # Maybe show an error label
            pass

class SettingsPopup(AnimatedPopup):
    def __init__(self, translator, config, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app # Store the app instance
        self.tr = translator
        self.config = config
        self.title = self.tr.get('settings_title', 'Settings')
        self.size_hint = (0.8, 0.9)
        self.auto_dismiss = False
        self.new_hotkey = set()
        self.recording = False
        self.listener = None
        self.is_testing = False
        self.test_sound = None

        # --- Main Layout ---
        main_layout = BoxLayout(orientation='vertical', spacing=5, padding=10)
        
        # --- Tabbed Panel for Settings ---
        tab_panel = TabbedPanel(do_default_tab=False)
        
        # --- Hotkeys Tab ---
        hotkeys_tab = TabbedPanelHeader(text=self.tr.get('hotkeys_tab', 'Hotkeys'))
        hotkeys_tab.content = self.create_hotkeys_tab()
        tab_panel.add_widget(hotkeys_tab)

        # --- Security Tab ---
        security_tab = TabbedPanelHeader(text=self.tr.get('security_tab', 'Security'))
        security_tab.content = self.create_security_tab()
        tab_panel.add_widget(security_tab)

        # --- Plugins Tab ---
        plugins_tab = TabbedPanelHeader(text=self.tr.get('plugins_tab', 'Plugins'))
        plugins_tab.content = self.create_plugins_tab()
        tab_panel.add_widget(plugins_tab)

        main_layout.add_widget(tab_panel)

        # --- Action Buttons ---
        btn_layout = BoxLayout(size_hint_y=None, height=44, spacing=10)
        save_btn = Button(text=self.tr.get('save_button'))
        save_btn.bind(on_press=self.save_and_dismiss)
        cancel_btn = Button(text=self.tr.get('cancel_button', 'Cancel'))
        cancel_btn.bind(on_press=self.cancel_and_dismiss)
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        main_layout.add_widget(btn_layout)
        
        self.content = main_layout

    def create_hotkeys_tab(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('hotkey_settings_title', 'Mute Hotkey'), font_size='18sp'))
        current_hotkey_str = self.config.get('hotkeys', {}).get('mute', 'ctrl+m')
        layout.add_widget(Label(text=self.tr.get('hotkey_mute_label')))
        self.hotkey_label = Label(text=current_hotkey_str)
        layout.add_widget(self.hotkey_label)
        self.record_button = Button(text=self.tr.get('hotkey_record_button'))
        self.record_button.bind(on_press=self.toggle_record)
        layout.add_widget(self.record_button)
        return layout

    def create_security_tab(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        layout.add_widget(Label(text=self.tr.get('p2p_password_label', 'P2P Connection Password'), font_size='18sp'))
        layout.add_widget(Label(text=self.tr.get('p2p_password_desc', 'Require a password for incoming P2P connections.')))
        self.p2p_password_input = TextInput(
            text=self.config.get('security', {}).get('p2p_password', ''),
            multiline=False,
            password=True
        )
        layout.add_widget(self.p2p_password_input)
        return layout

    def create_plugins_tab(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        scroll_view = ScrollView()
        scroll_content = GridLayout(cols=1, size_hint_y=None, spacing=10)
        scroll_content.bind(minimum_height=scroll_content.setter('height'))

        self.plugin_switches = {} # To hold references to the switches

        if self.app.plugin_manager and self.app.plugin_manager.plugins:
            for plugin in self.app.plugin_manager.plugins:
                plugin_layout = BoxLayout(size_hint_y=None, height=60)
                
                info_layout = BoxLayout(orientation='vertical')
                info_layout.add_widget(Label(text=plugin['name'], font_size='16sp', halign='left', valign='top'))
                info_layout.add_widget(Label(text=plugin['description'], font_size='12sp', color=(0.7,0.7,0.7,1), halign='left', valign='top'))
                
                switch = Switch(active=plugin['enabled'])
                self.plugin_switches[plugin['id']] = switch

                plugin_layout.add_widget(info_layout)
                plugin_layout.add_widget(switch)
                scroll_content.add_widget(plugin_layout)
        else:
            scroll_content.add_widget(Label(text=self.tr.get('no_plugins_found', 'No plugins found.')))

        scroll_view.add_widget(scroll_content)
        layout.add_widget(scroll_view)
        return layout

    def toggle_record(self, instance):
        self.recording = not self.recording
        if self.recording:
            self.new_hotkey = set()
            self.hotkey_label.text = self.tr.get('hotkey_recording_prompt')
            self.record_button.text = self.tr.get('hotkey_stop_record_button')
            self.start_listener()
        else:
            self.record_button.text = self.tr.get('hotkey_record_button')
            self.stop_listener()

    def on_press(self, key):
        if self.recording:
            self.new_hotkey.add(key)
            self.hotkey_label.text = ' + '.join(self.key_to_str(k) for k in self.new_hotkey)

    def on_release(self, key):
        if self.recording:
            self.toggle_record(None)

    def start_listener(self):
        if not self.listener:
            self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
            self.listener.start()

    def stop_listener(self):
        if self.listener:
            self.listener.stop()
            self.listener = None

    def save_and_dismiss(self, instance):
        self.stop_listener()
        self.hotkey = self.new_hotkey
        
        if 'security' not in self.config:
            self.config['security'] = {}
        self.config['security']['p2p_password'] = self.p2p_password_input.text

        # --- Handle Plugin Enable/Disable ---
        restart_required = False
        if hasattr(self, 'plugin_switches'):
            for plugin in self.app.plugin_manager.plugins:
                plugin_id = plugin['id']
                switch = self.plugin_switches.get(plugin_id)
                if switch is None:
                    continue

                is_currently_enabled = plugin['enabled']
                should_be_enabled = switch.active

                if is_currently_enabled != should_be_enabled:
                    restart_required = True
                    py_file_path = os.path.join(plugin['path'], f"{plugin['module_name']}.py")
                    disabled_py_file_path = py_file_path + '.disabled'

                    try:
                        if should_be_enabled and os.path.exists(disabled_py_file_path):
                            os.rename(disabled_py_file_path, py_file_path)
                            print(f"Enabled plugin: {plugin['name']}")
                        elif not should_be_enabled and os.path.exists(py_file_path):
                            os.rename(py_file_path, disabled_py_file_path)
                            print(f"Disabled plugin: {plugin['name']}")
                    except Exception as e:
                        print(f"Error changing plugin state for {plugin['name']}: {e}")

        if restart_required:
            self.app.show_popup(
                self.tr.get('restart_required_title', 'Restart Required'),
                self.tr.get('restart_required_message', 'Plugin changes will take effect after restarting the application.')
            )
        
        self.dismiss()

    def cancel_and_dismiss(self, instance):
        self.stop_listener()
        self.dismiss()

    @staticmethod
    def key_to_str(key):
        if isinstance(key, keyboard.Key):
            return key.name
        elif isinstance(key, keyboard.KeyCode):
            return key.char
        return str(key)



class VoiceChatApp(App):
    def build(self):
        # Register emoji font
        # Let's try to find a suitable emoji font
        font_paths = [
            'C:/Windows/Fonts/seguiemj.ttf',
            '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf', # Linux
            '/System/Library/Fonts/Apple Color Emoji.ttc' # macOS
        ]
        found_font = None
        for font in font_paths:
            if os.path.exists(font):
                found_font = font
                break
        
        if found_font:
            print(f"Emoji font found at: {found_font}")
            LabelBase.register(name='EmojiFont', fn_regular=found_font)
        else:
            print("WARNING: No system emoji font found. Emojis will likely not render.")
            # Using a basic font as a fallback.
            LabelBase.register(name='EmojiFont', fn_regular='Roboto')
        return RootLayout()

    def on_start(self):
        self.config_manager = ConfigManager()
        self.tr = Translator(self.config_manager)
        self.p2p_manager = None
        self.server_manager = None
        self.bluetooth_manager = None
        self.username = None
        self.mode = None
        self.server_groups = {} # {group_id: {name, admin, members}}
        self.active_group_call = None # Stores group_id of the active call
        self.pending_group_call_punches = set()
        self.call_popup = None
        self.group_call_popup = None
        self.current_peer_addr = None
        self.pending_call_target = None
        self.negotiated_rate = None
        self.callback_queue = queue.Queue()
        self.webrtc_manager = WebRTCManager(self.callback_queue)
        self.hotkey_manager = HotkeyManager()
        self.is_muted = False
        self.plugin_manager = None
        self.emoji_manager = None
        self.root.opacity = 0
        self.contacts = set() # Users who have accepted contact requests
        self.search_user_input = None
        self.settings_popup = None
        
        self.chat_history = {'global': []}
        self.initialized = False
        self.active_chat = 'global' # Can be 'global' or a group_id
        
        self.themes = {
            'light': {'bg': [1,1,1,1], 'text': [0,0,0,1], 'panel_bg': [0.9,0.9,0.9,1], 'input_bg': [1,1,1,1], 'button_bg': [0.8,0.8,0.8,1], 'button_text': [0,0,0,1], 'title_bar_bg': [0.7,0.7,0.7,1]},
            'dark': {'bg': [0.1,0.1,0.1,1], 'text': [1,1,1,1], 'panel_bg': [0.15,0.15,0.15,1], 'input_bg': [0.2,0.2,0.2,1], 'button_bg': [0.3,0.3,0.3,1], 'button_text': [1,1,1,1], 'title_bar_bg': [0.25,0.25,0.25,1]}
        }
        self.current_theme = 'light'

        Clock.schedule_interval(self.process_callbacks, 0.1)
        Window.bind(on_request_close=self.on_request_close, on_dropfile=self.on_file_drop)
        self.show_mode_selection_popup()

    def process_callbacks(self, dt):
        while not self.callback_queue.empty():
            try:
                event = self.callback_queue.get_nowait()
                event_type = event[0]
                
                if event_type == 'bt_message_received':
                    _, message = event
                    self.add_message_to_box(message, 'global') # Assuming BT chat is global for now
                elif event_type == 'bt_connected':
                    _, address = event
                    self.add_message_to_box(self.tr.get('bt_connected_to', address=address), 'global')
                elif event_type == 'bt_connection_failed':
                    _, address = event
                    self.add_message_to_box(self.tr.get('bt_connection_failed', address=address), 'global')
                elif event_type == 'bt_disconnected':
                    self.add_message_to_box(self.tr.get('bt_disconnected'), 'global')
                elif event_type == 'bt_adapter_error':
                    _, error_msg = event
                    self.show_popup("Bluetooth Error", error_msg)
                elif event_type == 'webrtc_offer_created':
                    self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'offer', event[1]['offer'])
                elif event_type == 'webrtc_answer_created':
                    self.p2p_manager.send_webrtc_signal(event[1]['peer'], 'answer', event[1]['answer'])

            except queue.Empty:
                break

    def show_mode_selection_popup(self):
        popup = ModeSelectionPopup(translator=self.tr)
        popup.bind(on_dismiss=self.on_mode_selected)
        popup.open()

    def on_mode_selected(self, popup):
        self.mode = getattr(popup, 'mode', None)
        if not self.mode:
            self.stop()
            return
        
        if self.mode == 'server':
            self.show_server_login_popup()
        else:
            self.show_username_popup()

    def show_server_login_popup(self):
        config = self.config_manager.load_config()
        popup = ServerLoginPopup(translator=self.tr, config=config)
        popup.bind(on_dismiss=self.on_server_login_entered)
        popup.open()

    def on_server_login_entered(self, popup):
        self.server_ip = getattr(popup, 'server_ip', None)
        self.server_port = getattr(popup, 'server_port', None)
        self.server_password = getattr(popup, 'password', None)

        if not self.server_ip or not self.server_port:
            self.stop()
            return
        
        # Save the new server config
        config = self.config_manager.load_config()
        if 'server' not in config:
            config['server'] = {}
        config['server']['host'] = self.server_ip
        config['server']['port'] = self.server_port
        self.config_manager.save_config(config)

        self.show_username_popup()

    def show_username_popup(self):
        config = self.config_manager.load_config()
        current_username = config.get('username', '')
        popup = UsernamePopup(translator=self.tr, current_username=current_username)
        popup.bind(on_dismiss=self.on_username_entered)
        popup.open()

    def on_username_entered(self, popup):
        self.username = getattr(popup, 'username', None)
        if not self.username:
            self.stop()
            return
        config = self.config_manager.load_config()
        config['username'] = self.username
        self.config_manager.save_config(config)
        self.initialize_app()

    def initialize_app(self):
        if self.initialized:
            return
        self.initialized = True
        chat_ids = self.root.ids.chat_layout.ids
        
        chat_ids.send_button.bind(on_press=self.send_message)
        chat_ids.theme_button.bind(on_press=self.toggle_theme)
        chat_ids.settings_button.bind(on_press=self.show_settings_popup)
        chat_ids.emoji_button.bind(on_press=self.toggle_emoji_panel)
        chat_ids.msg_entry.bind(on_text_validate=self.send_message)
        
        # Programmatically add Create Group button
        group_actions_layout = chat_ids.group_actions_layout
        
        self.create_group_button = Button(text='+', size_hint_x=None, width=40)
        self.create_group_button.bind(on_press=self.show_create_group_popup)
        group_actions_layout.add_widget(self.create_group_button)

        self.invite_user_button = Button(text='Invite', size_hint_x=None, width=60)
        self.invite_user_button.bind(on_press=self.show_invite_user_popup)
        group_actions_layout.add_widget(self.invite_user_button)
        self.invite_user_button.opacity = 0
        self.invite_user_button.disabled = True

        self.group_call_button = Button(text='Call', size_hint_x=None, width=50)
        self.group_call_button.bind(on_press=self.start_group_call)
        group_actions_layout.add_widget(self.group_call_button)
        self.group_call_button.opacity = 0
        self.group_call_button.disabled = True

        self.manage_group_button = Button(text='Manage', size_hint_x=None, width=70)
        self.manage_group_button.bind(on_press=self.show_manage_group_popup)
        group_actions_layout.add_widget(self.manage_group_button)
        self.manage_group_button.opacity = 0
        self.manage_group_button.disabled = True

        # --- P2P User Search (Internet Mode Only) ---
        if self.mode == 'p2p_internet':
            search_layout = BoxLayout(size_hint_y=None, height=80, spacing=10, padding=(5, 10))
            self.search_user_input = TextInput(
                hint_text=self.tr.get('search_user_hint', 'Find user...'),
                multiline=False,
                font_size='20sp'
            )
            search_button = Button(
                text=self.tr.get('search_button', 'Find'),
                size_hint_x=0.4,
                font_size='20sp'
            )
            search_button.bind(on_press=self.find_p2p_user)
            search_layout.add_widget(self.search_user_input)
            search_layout.add_widget(search_button)
            # Add to the main vertical controls layout, not the group actions one
            chat_ids.users_panel_controls.add_widget(search_layout, index=0) # Add at the top

        if self.mode.startswith('p2p') and self.mode != 'p2p_bluetooth':
            self.init_p2p_mode()
        elif self.mode == 'p2p_bluetooth':
            self.init_bluetooth_mode()
        elif self.mode == 'server':
            self.init_server_mode()
        
        config = self.config_manager.load_config()
        self.init_hotkeys()
        self.apply_theme()
        self.root.opacity = 1
        
        # Initialize and load plugins
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.discover_and_load_plugins()
        self.emoji_manager = EmojiManager()
        self.create_emoji_panel()
        self.webrtc_manager.start()
        
        chat_ids.msg_entry.focus = True
        # The native window is now used, so borderless setup is not required.
        # Clock.schedule_once(self.setup_borderless_window, 0)

    def find_p2p_user(self, instance):
        username = self.search_user_input.text.strip()
        if not username:
            return
        if self.mode == 'p2p_internet' and self.p2p_manager:
            self.add_message_to_box(f"System: Searching for '{username}' in the network...", 'global')
            self.p2p_manager.find_peer(username)
            self.search_user_input.text = ""

    def init_p2p_mode(self):
        p2p_mode_type = 'local' if self.mode == 'p2p_local' else 'internet'
        self.p2p_manager = P2PManager(self.username, self.chat_history, mode=p2p_mode_type)
        callbacks = {
            'peer_discovered': self.add_peer, 'peer_lost': self.remove_peer,
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
            self.add_message_to_box("Failed to initialize P2P networking. Port might be in use.", 'global')
            return
        
        self.udp_socket = self.p2p_manager.udp_socket
        self.add_message_to_box(f"P2P {p2p_mode_type} mode started as '{self.username}'.")

    def init_server_mode(self):
        self.server_manager = ServerManager(self.server_ip, self.server_port, self.username, self.server_password, self.chat_history)
        callbacks = {
            'login_failed': lambda p: self.add_message_to_box(f"Login failed: {p.get('reason')}", 'global'),
            'connection_failed': lambda e: self.add_message_to_box(f"Server connection failed: {e}", 'global'),
            'disconnected': lambda: self.add_message_to_box("Disconnected from server.", 'global'),
            'info_received': lambda p: self.add_message_to_box(f"Server: {p.get('message')}", 'global'),
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
        self.add_message_to_box(f"Connecting to server at {self.server_ip}:{self.server_port} as '{self.username}'...")

    def init_bluetooth_mode(self):
        self.bluetooth_manager = BluetoothManager(self.username, self.callback_queue)
        self.bluetooth_manager.start()
        self.add_message_to_box(self.tr.get('bt_mode_start'), 'global')
        
        # Add a scan button
        self.scan_bt_button = Button(text=self.tr.get('scan_bt_button', 'Scan for Devices'), size_hint_x=1, height=44, size_hint_y=None)
        self.scan_bt_button.bind(on_press=self.scan_for_bt_devices)
        # Add to the main vertical controls layout
        self.root.ids.chat_layout.ids.users_panel_controls.add_widget(self.scan_bt_button)
        self.apply_theme() # To style the new button

    def scan_for_bt_devices(self, instance):
        self.add_message_to_box(self.tr.get('bt_scanning'), 'global')
        # Run discovery in a separate thread to not block the UI
        threading.Thread(target=self.bluetooth_manager.discover_devices, daemon=True).start()



    def toggle_theme(self, instance):
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.apply_theme()

    def _apply_windows_title_bar_theme(self):
        """Applies the selected theme to the native Windows title bar."""
        if sys.platform != 'win32':
            return # This is a Windows-only feature

        try:
            import ctypes
            from kivy.core.window import Window
            
            # Use Window.hwnd, available after the window is created.
            hwnd = Window.hwnd
            if not hwnd:
                print("Could not get window handle (hwnd) for theming.")
                return

            # DWMWA_USE_IMMERSIVE_DARK_MODE attribute for dark title bar
            # Should work for Windows 10 (1903+) and Windows 11
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            
            value = ctypes.c_int(1 if self.current_theme == 'dark' else 0)
            
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
            
            if result != 0:
                print(f"DwmSetWindowAttribute failed with HRESULT: {result}")
        except Exception as e:
            print(f"Failed to set native title bar theme: {e}")

    def apply_theme(self):
        theme = self.themes[self.current_theme]
        chat_ids = self.root.ids.chat_layout.ids
        Window.clearcolor = theme['bg']
        set_bg(self.root, theme['bg'])
        set_bg(chat_ids.chat_panel, theme['panel_bg'])
        set_bg(chat_ids.users_panel, theme['panel_bg'])
        chat_ids.users_list_label.color = theme['text']
        chat_ids.msg_entry.background_color = theme['input_bg']
        chat_ids.msg_entry.foreground_color = theme['text']
        for button_id in ['send_button', 'record_button', 'emoji_button', 'theme_button', 'settings_button']:
            if button_id in chat_ids: # Check if button exists (e.g. attach_button is now in a plugin)
                chat_ids[button_id].background_color = theme['button_bg']
                chat_ids[button_id].color = theme['button_text']
        if hasattr(self, 'scan_bt_button'):
            self.scan_bt_button.background_color = theme['button_bg']
            self.scan_bt_button.color = theme['button_text']
        self.create_group_button.background_color = theme['button_bg']
        self.create_group_button.color = theme['button_text']
        self.invite_user_button.background_color = theme['button_bg']
        self.invite_user_button.color = theme['button_text']
        self.group_call_button.background_color = theme['button_bg']
        self.group_call_button.color = theme['button_text']
        self.manage_group_button.background_color = theme['button_bg']
        self.manage_group_button.color = theme['button_text']
        if hasattr(self, 'search_user_input') and self.search_user_input:
            self.search_user_input.background_color = theme['input_bg']
            self.search_user_input.foreground_color = theme['text']
            if self.search_user_input.parent:
                search_layout = self.search_user_input.parent
                # Find the button, it's not always the first child
                search_button = next((child for child in search_layout.children if isinstance(child, Button)), None)
                if search_button:
                    search_button.background_color = theme['button_bg']
                    search_button.color = theme['button_text']
        for child in chat_ids.chat_box.children:
            if isinstance(child, Label):
                child.color = theme['text']
        for child in chat_ids.users_list.children:
            if isinstance(child, Button):
                child.background_color = theme['button_bg']
                child.color = theme['button_text']
        
        # Apply theme to registered plugin widgets
        if self.plugin_manager:
            for widget in self.plugin_manager.themed_widgets:
                if isinstance(widget, Button):
                    widget.background_color = theme['button_bg']
                    widget.color = theme['button_text']
        
        # Also apply the theme to the native title bar on Windows
        # Schedule the native title bar theme to apply after one frame
        # to ensure the window handle (hwnd) is available.
        Clock.schedule_once(lambda dt: self._apply_windows_title_bar_theme(), 0)

    def send_message(self, instance=None):
        text = self.root.ids.chat_layout.ids.msg_entry.text.strip()
        if not text:
            return
        message_data = {'id': str(uuid.uuid4()), 'sender': self.username, 'text': text, 'timestamp': datetime.now().isoformat()}
        if self.mode.startswith('p2p') and self.p2p_manager:
            if self.active_chat == 'global':
                # In P2P global, we don't broadcast to everyone, but send to contacts.
                # For now, let's assume sending a global message requires a contact request first
                # to the first peer found if no contacts exist. This is complex.
                # A simpler model: you can only message people from your user list (who are contacts).
                # Let's stick to the user's request: to write to someone, they must agree.
                # This implies we can't broadcast to non-contacts.
                # We will modify this to send to all contacts.
                
                # For now, let's just check if we have any contacts.
                if not self.contacts:
                     self.show_popup("Cannot Send", "You must add a user as a contact before sending messages.")
                     return

                for contact in self.contacts:
                     # This is not ideal, broadcast_message sends to all peers.
                     # We need a send_private_message method. Let's add it later.
                     # For now, we will use the existing broadcast and add a check on the receiving end.
                     pass # Placeholder

                self.p2p_manager.broadcast_message(message_data) # This will go to everyone for now
                self.add_message_to_box(message_data, 'global')
            else: # It's a group chat
                self.p2p_manager.send_group_message(self.active_chat, message_data)
                self.add_message_to_box(message_data, self.active_chat)
        elif self.mode == 'server' and self.server_manager:
            if self.active_chat != 'global':
                self.server_manager.send_group_message(self.active_chat, message_data)
                self.add_message_to_box(message_data, self.active_chat)
            else:
                self.add_message_to_box("Cannot send global messages in server mode yet.", 'global')
        elif self.mode == 'p2p_bluetooth' and self.bluetooth_manager:
            full_message = f"{self.username}: {text}"
            if self.bluetooth_manager.send_message(full_message):
                self.add_message_to_box(full_message, 'global')
            else:
                self.add_message_to_box(self.tr.get('bt_not_connected'), 'global')

        self.root.ids.chat_layout.ids.msg_entry.text = ""
        self.root.ids.chat_layout.ids.msg_entry.focus = True

    # --- Call Logic ---
    def initiate_call(self, target_username):
        if self.webrtc_manager.peer_connections:
            self.add_message_to_box("Error: Already in a call.", 'global')
            return

        if self.mode.startswith('p2p') and target_username not in self.contacts:
            self.request_contact(target_username)
            return

        self.add_message_to_box(f"Initiating call to {target_username}...", 'global')
        self.webrtc_manager.start_call(target_username)
        self.show_call_popup(target_username)

    def hang_up_call(self, peer_username=None):
        if not peer_username:
            # If no specific peer, hang up all connections
            for peer in list(self.webrtc_manager.peer_connections.keys()):
                self.webrtc_manager.end_call(peer)
                self.p2p_manager.send_webrtc_signal(peer, 'hangup', {})
        else:
            self.webrtc_manager.end_call(peer_username)
            self.p2p_manager.send_webrtc_signal(peer_username, 'hangup', {})

        if self.call_popup:
            self.call_popup.dismiss()
            self.call_popup = None
        self.add_message_to_box("Call ended.", 'global')

    @mainthread
    def on_webrtc_signal(self, sender, signal_type, data):
        if signal_type == 'offer':
            self.show_incoming_call_popup(sender, data)
        elif signal_type == 'answer':
            self.webrtc_manager.handle_answer(sender, data)
        elif signal_type == 'hangup':
            self.webrtc_manager.end_call(sender)
            if self.call_popup:
                self.call_popup.dismiss()
                self.call_popup = None
            self.add_message_to_box(f"Call with {sender} ended.", 'global')
        elif signal_type == 'busy':
            self.add_message_to_box(f"Call failed: {sender} is busy.", 'global')
            # End our side of the call attempt
            self.hang_up_call(sender)

    @mainthread
    def show_incoming_call_popup(self, peer_username, offer_sdp):
        if self.webrtc_manager.peer_connections:
            # Already in a call, reject automatically
            print(f"Incoming call from {peer_username} while already in another call. Ignoring.")
            # Future: send a 'busy' signal
            self.p2p_manager.send_webrtc_signal(peer_username, 'busy', {})
            return

        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text=self.tr.get('incoming_call_from', peer=peer_username)))
        btn_layout = BoxLayout(spacing=10)
        accept_btn = Button(text=self.tr.get('accept_button'))
        decline_btn = Button(text=self.tr.get('decline_button'))
        btn_layout.add_widget(accept_btn)
        btn_layout.add_widget(decline_btn)
        box.add_widget(btn_layout)
        
        popup = AnimatedPopup(title=self.tr.get('incoming_call_title'), content=box, size_hint=(0.7, 0.4), auto_dismiss=False)

        def accept(instance):
            popup.dismiss()
            self.webrtc_manager.handle_offer(peer_username, offer_sdp)
            self.show_call_popup(peer_username)
            self.add_message_to_box(f"Accepted call from {peer_username}.", 'global')

        def decline(instance):
            popup.dismiss()
            self.p2p_manager.send_webrtc_signal(peer_username, 'hangup', {})
            self.add_message_to_box(f"Declined call from {peer_username}.", 'global')

        accept_btn.bind(on_press=accept)
        decline_btn.bind(on_press=decline)
        popup.open()

    def show_call_popup(self, peer_username):
        if self.call_popup:
            self.call_popup.dismiss()
        
        self.call_popup = CallPopup(peer_username, self.tr)
        
        def on_hang_up(instance):
            self.hang_up_call(peer_username)
        
        def on_mute(instance, is_muted):
            self.is_muted = is_muted
            # TODO: Add actual mute logic for WebRTC here in self.webrtc_manager
            self.add_message_to_box(f"Mute is now {'ON' if is_muted else 'OFF'}", 'global')

        self.call_popup.bind(on_dismiss=on_hang_up)
        self.call_popup.bind(on_mute_toggle=on_mute)
        self.call_popup.open()
    # --- UI Update Callbacks ---
    @mainthread
    def add_message_to_box(self, message_data, chat_id=None):
        if chat_id is None:
            print("WARNING: add_message_to_box called without chat_id. Defaulting to 'global'.")
            chat_id = 'global'
        self.chat_history.setdefault(chat_id, []).append(message_data)
        if self.active_chat != chat_id:
            return # Don't display if not in active chat

        chat_box = self.root.ids.chat_layout.ids.chat_box
        theme = self.themes[self.current_theme]
        
        font_size = '15sp' # Default font size
        label_height = 30 # Default height
        
        if isinstance(message_data, str):
            display_text = message_data
            text_for_analysis = message_data
        elif isinstance(message_data, dict):
            sender = "You" if message_data.get('sender') == self.username else message_data.get('sender', 'Unknown')
            text = message_data.get('text', '')
            text_for_analysis = text
            try:
                time_str = datetime.fromisoformat(message_data.get('timestamp', '')).strftime("%H:%M:%S")
                display_text = f"[{time_str}] {sender}: {text}"
            except:
                display_text = f"{sender}: {text}"
        else:
            return

        # --- Emoji Size Logic ---
        # This regex finds individual emoji characters
        emoji_list = regex.findall(r'\X', text_for_analysis)
        # Check if the message consists ONLY of emojis
        is_all_emoji = all(regex.match(r'\p{So}', char) for char in emoji_list)

        if is_all_emoji and 1 <= len(emoji_list) <= 3:
            if len(emoji_list) == 1:
                font_size = '48sp'
                label_height = 60
            elif len(emoji_list) == 2:
                font_size = '36sp'
                label_height = 50
            elif len(emoji_list) == 3:
                font_size = '28sp'
                label_height = 40
        # --- End Emoji Size Logic ---

        label = Label(text=display_text, size_hint_y=None, height=label_height, halign='left', valign='top', color=theme['text'], opacity=0, font_size=font_size, font_name='EmojiFont')
        label.bind(width=lambda *x: label.setter('text_size')(label, (label.width, None)))
        chat_box.add_widget(label)
        anim = Animation(opacity=1, d=0.3)
        anim.start(label)
        self.root.ids.chat_layout.ids.chat_scroll.scroll_y = 0

    @mainthread
    def p2p_message_received(self, message_data):
        if message_data.get('sender') != self.username:
            self.add_message_to_box(message_data, 'global')

    @mainthread
    def add_peer(self, username, address_info):
        if username == self.username:
            return
        users_list = self.root.ids.chat_layout.ids.users_list
        theme = self.themes[self.current_theme]
        for child in users_list.children:
            if isinstance(child, Button) and child.text.startswith(username):
                return
        user_button = Button(text=username, size_hint_y=None, height=40, background_color=theme['button_bg'], color=theme['button_text'])
        user_button.bind(on_press=lambda x, u=username: self.initiate_call(u))
        users_list.add_widget(user_button)
        self.add_message_to_box(f"System: '{username}' is online.", 'global')

    @mainthread
    def on_user_list_update(self, users):
        users_list = self.root.ids.chat_layout.ids.users_list
        
        # Simple redraw: clear and add all
        # A more efficient implementation would diff the lists
        for child in [c for c in users_list.children if isinstance(c, Button) and not c.text.startswith('[GROUP]')]:
             users_list.remove_widget(child)

        theme = self.themes[self.current_theme]
        for username in users:
            if username == self.username:
                continue
            user_button = Button(text=username, size_hint_y=None, height=40, background_color=theme['button_bg'], color=theme['button_text'])
            # In server mode, clicking a user could open a private chat later
            # user_button.bind(on_press=lambda x, u=username: self.initiate_call(u))
            users_list.add_widget(user_button)

    @mainthread
    def remove_peer(self, username):
        users_list = self.root.ids.chat_layout.ids.users_list
        widget_to_remove = None
        for child in users_list.children:
            if isinstance(child, Button) and child.text.startswith(username):
                widget_to_remove = child
                break
        if widget_to_remove:
            users_list.remove_widget(widget_to_remove)
            self.add_message_to_box(f"System: '{username}' went offline.", 'global')

    @mainthread
    def on_secure_channel_established(self, username):
        self.add_message_to_box(f"System: Secure connection established with {username}.", 'global')
        users_list = self.root.ids.chat_layout.ids.users_list
        for child in users_list.children:
            if isinstance(child, Button) and child.text == username:
                child.text = f"{username} (Secure)"
                break

    @mainthread
    def on_peer_found(self, username):
        self.add_message_to_box(f"System: Found user '{username}'. They have been added to your user list.", 'global')
        # The peer_discovered callback will handle adding the button

    @mainthread
    def on_peer_not_found(self, username):
        self.show_popup("Search Failed", f"User '{username}' could not be found on the network.")

    def request_contact(self, target_username):
        config = self.config_manager.load_config()
        p2p_password = config.get('security', {}).get('p2p_password', '')
        
        # We don't use the password-based encryption for the request itself,
        # just a hash for verification on the other side.
        password_hash = self.p2p_manager.encryption_manager.hash_password(p2p_password) if p2p_password else None
        
        self.p2p_manager.send_contact_request(target_username, password_hash)
        self.add_message_to_box(f"System: Contact request sent to '{target_username}'.", 'global')

    @mainthread
    def on_incoming_contact_request(self, sender_username, password_hash):
        config = self.config_manager.load_config()
        my_password = config.get('security', {}).get('p2p_password', '')

        if my_password:
            my_hash = self.p2p_manager.encryption_manager.hash_password(my_password)
            if my_hash != password_hash:
                print(f"Incoming contact request from {sender_username} with wrong password. Ignoring.")
                return # Silently ignore

        # Password matches or is not required, show popup.
        popup = ContactRequestPopup(sender_username, self.tr)
        def handle_response(instance, accepted):
            self.p2p_manager.send_contact_response(sender_username, accepted)
            if accepted:
                self.contacts.add(sender_username)
                self.add_message_to_box(f"System: You are now contacts with {sender_username}.", 'global')
        popup.bind(on_response=handle_response)
        popup.open()

    @mainthread
    def on_contact_request_response(self, sender_username, accepted):
        if accepted:
            self.contacts.add(sender_username)
            self.show_popup("Contact Added", f"'{sender_username}' accepted your contact request.")
        else:
            self.show_popup("Request Declined", f"'{sender_username}' declined your contact request.")

    # --- History Sync Logic ---
    @mainthread
    def on_history_received(self, chat_id, history):
        self.add_message_to_box(f"System: Received history for '{chat_id}' ({len(history)} messages).", 'global')
        # A simple merge: replace local history with the received one if it's longer.
        # A more sophisticated merge could be implemented later.
        if len(history) > len(self.chat_history.get(chat_id, [])):
            self.chat_history[chat_id] = history
            if self.active_chat == chat_id:
                # Refresh the view
                self.switch_chat(chat_id)

    # --- Group Chat Logic ---
    def show_create_group_popup(self, instance):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text="Enter group name:"))
        self.group_name_input = TextInput(multiline=False)
        box.add_widget(self.group_name_input)
        ok_button = Button(text="Create")
        box.add_widget(ok_button)
        popup = AnimatedPopup(title="Create Group", content=box, size_hint=(0.8, 0.4))
        ok_button.bind(on_press=lambda x: self.create_group(popup))
        popup.open()

    def create_group(self, popup):
        group_name = self.group_name_input.text.strip()
        if not group_name:
            popup.dismiss()
            return
        if self.mode.startswith('p2p'):
            if self.p2p_manager:
                self.p2p_manager.create_group(group_name)
        elif self.mode == 'server':
            if self.server_manager:
                self.server_manager.create_group(group_name)
        popup.dismiss()

    @mainthread
    def on_group_created(self, group_id, group_name, admin_username):
        self.add_message_to_box(f"System: You created group '{group_name}'.", 'global')
        self.add_group_to_list(group_id, group_name)
        self.switch_chat(group_id)

    @mainthread
    def on_group_message_received(self, group_id, message_data):
        self.add_message_to_box(message_data, group_id)

    @mainthread
    def add_group_to_list(self, group_id, group_name):
        users_list = self.root.ids.chat_layout.ids.users_list
        theme = self.themes[self.current_theme]
        group_button = Button(text=f"[GROUP] {group_name}", size_hint_y=None, height=40, background_color=theme['button_bg'], color=theme['button_text'])
        group_button.bind(on_press=lambda x: self.switch_chat(group_id))
        users_list.add_widget(group_button)

    def switch_chat(self, chat_id):
        self.active_chat = chat_id
        chat_box = self.root.ids.chat_layout.ids.chat_box
        chat_box.clear_widgets()
        history = self.chat_history.get(chat_id, [])
        for message_data in history:
            self.add_message_to_box(message_data, chat_id)
        # Update title or some indicator
        if chat_id == 'global':
            Window.title = "Voice Chat"
        else:
            if self.mode.startswith('p2p'):
                group_info = self.p2p_manager.groups.get(chat_id, {})
            else: # server mode
                group_info = self.server_groups.get(chat_id, {})
            
            group_name = group_info.get('name', 'Group')
            Window.title = f"Voice Chat - {group_name}"
            is_admin = group_info.get('admin') == self.username
            
            is_admin = group_info.get('admin') == self.username
            
            self.group_call_button.opacity = 1 if is_admin else 0
            self.group_call_button.disabled = not is_admin

            self.invite_user_button.opacity = 1 if is_admin else 0
            self.invite_user_button.disabled = not is_admin

            self.manage_group_button.opacity = 1 if is_admin else 0
            self.manage_group_button.disabled = not is_admin

    def show_group_call_popup(self):
        group_name = self.p2p_manager.groups.get(self.active_group_call, {}).get('name', '')
        self.group_call_popup = GroupCallPopup(group_name, self.tr)
        self.group_call_popup.bind(on_dismiss=lambda x: self.hang_up_call())
        self.group_call_popup.open()

    @mainthread
    def on_group_joined(self, group_id, username):
        if group_id == self.active_chat:
            self.add_message_to_box(f"System: '{username}' has joined the group.", group_id)

    @mainthread
    def on_incoming_group_invite(self, group_id, group_name, admin_username):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text=f"You are invited to join the group '{group_name}' by {admin_username}."))
        btn_layout = BoxLayout(spacing=10)
        yes_btn = Button(text='Accept')
        no_btn = Button(text='Decline')
        btn_layout.add_widget(yes_btn)
        btn_layout.add_widget(no_btn)
        box.add_widget(btn_layout)
        popup = AnimatedPopup(title="Group Invitation", content=box, size_hint=(0.8, 0.5), auto_dismiss=False)

        def on_yes(inst):
            if self.mode.startswith('p2p'):
                self.p2p_manager.send_group_invite_response(group_id, admin_username, True)
            elif self.mode == 'server':
                self.server_manager.send_group_invite_response(group_id, True)
            
            # The server will confirm our membership, which will trigger adding the group to the list
            # self.add_group_to_list(group_id, group_name)
            # self.switch_chat(group_id)
            popup.dismiss()

        def on_no(inst):
            if self.mode.startswith('p2p'):
                self.p2p_manager.send_group_invite_response(group_id, admin_username, False)
            elif self.mode == 'server':
                self.server_manager.send_group_invite_response(group_id, False)
            popup.dismiss()

        yes_btn.bind(on_press=on_yes)
        no_btn.bind(on_press=on_no)
        popup.open()

    @mainthread
    def on_group_invite_response(self, group_id, username, accepted):
        if not accepted:
            self.add_message_to_box(f"System: '{username}' declined the invitation to join.", group_id)

    def show_invite_user_popup(self, instance):
        if self.mode.startswith('p2p'):
            if not self.p2p_manager or not self.p2p_manager.peers:
                self.add_message_to_box("System: No users online to invite.", self.active_chat)
                return
            current_members = self.p2p_manager.groups.get(self.active_chat, {}).get('members', set())
            available_users = [u for u in self.p2p_manager.peers.keys() if u not in current_members]
        elif self.mode == 'server':
            if not self.server_manager: return
            # Assuming server_manager holds the user list
            all_users = [c.text for c in self.root.ids.chat_layout.ids.users_list.children if isinstance(c, Button) and not c.text.startswith('[GROUP]')]
            current_members = self.server_groups.get(self.active_chat, {}).get('members', [])
            available_users = [u for u in all_users if u not in current_members]
        else:
            return

        if not available_users:
            self.add_message_to_box("System: All available users are already in the group.", self.active_chat)
            return

        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text="Select a user to invite:"))
        popup = AnimatedPopup(title="Invite User", content=box, size_hint=(0.6, 0.8))
        for username in available_users:
            btn = Button(text=username)
            btn.bind(on_press=lambda x, u=username: self.invite_user(u, popup))
            box.add_widget(btn)
        popup.open()

    def invite_user(self, username, popup):
        popup.dismiss()
        if self.active_chat == 'global': return

        if self.mode.startswith('p2p'):
            self.p2p_manager.send_group_invite(self.active_chat, username)
        elif self.mode == 'server':
            self.server_manager.invite_to_group(self.active_chat, username)
        
        self.add_message_to_box(f"System: Invitation sent to '{username}'.", self.active_chat)

    def show_manage_group_popup(self, instance):
        if self.active_chat == 'global':
            return

        if self.mode.startswith('p2p'):
            group_info = self.p2p_manager.groups.get(self.active_chat, {})
            members = group_info.get('members', set())
        elif self.mode == 'server':
            group_info = self.server_groups.get(self.active_chat, {})
            members = group_info.get('members', [])
        else:
            return
        
        # Admin cannot kick themselves
        members_to_manage = [m for m in members if m != self.username]
        
        if not members_to_manage:
            self.add_message_to_box("System: No other members to manage.", self.active_chat)
            return

        popup = ManageGroupPopup(self.tr, members_to_manage)
        popup.bind(on_kick_user=self.on_kick_user_selected)
        popup.open()

    def on_kick_user_selected(self, popup, username):
        # The message will be added via the callback on_user_kicked
        if self.mode.startswith('p2p'):
            self.p2p_manager.kick_user_from_group(self.active_chat, username)
        elif self.mode == 'server':
            self.server_manager.kick_user_from_group(self.active_chat, username)

    # --- Group Call Logic ---
    def start_group_call(self, instance):
        if self.active_chat == 'global' or self.active_group_call or self.webrtc_manager.peer_connections:
            return
        
        config = self.config_manager.load_config()
        
        self.active_group_call = self.active_chat
        
        if self.mode.startswith('p2p'):
            self.p2p_manager.start_group_call(self.active_group_call, supported_rate)
            self.add_message_to_box("Starting P2P group call...", self.active_group_call)
            self.show_group_call_popup()
            # Since we are the admin, we automatically "join"
            self.join_group_call(self.active_group_call)
        elif self.mode == 'server':
            self.server_manager.start_group_call(self.active_group_call, supported_rate)
            self.add_message_to_box("Requesting server to start group call...", self.active_group_call)
            # We will join after getting our public UDP address
            self.join_server_group_call(self.active_group_call)

    def join_group_call(self, group_id):
        if self.mode.startswith('p2p'):
            self.active_group_call = group_id
            self.show_group_call_popup()
            # Initiate hole punch with all other members
            members = self.p2p_manager.groups.get(group_id, {}).get('members', set())
            for member in members:
                if member != self.username:
                    self.pending_group_call_punches.add(member)
                    self.p2p_manager.initiate_hole_punch(member)
        elif self.mode == 'server':
            self.join_server_group_call(group_id)

    @mainthread
    def on_incoming_group_call(self, group_id, admin_username, sample_rate):
        if self.active_group_call or self.webrtc_manager.peer_connections:
            # Decline if already in a call
            # self.p2p_manager.send_group_call_response(group_id, 'reject') # Maybe not needed
            return

        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', '') if self.mode.startswith('p2p') else self.server_groups.get(group_id, {}).get('name', '')
        box.add_widget(Label(text=f"Incoming group call from '{admin_username}' for group '{group_name}'."))
        btn_layout = BoxLayout(spacing=10)
        yes_btn = Button(text='Join')
        no_btn = Button(text='Decline')
        btn_layout.add_widget(yes_btn)
        btn_layout.add_widget(no_btn)
        box.add_widget(btn_layout)
        popup = AnimatedPopup(title="Incoming Group Call", content=box, size_hint=(0.8, 0.5), auto_dismiss=False)

        def on_yes(inst):
            self.negotiated_rate = sample_rate
            if self.mode.startswith('p2p'):
                self.p2p_manager.send_group_call_response(group_id, 'accept')
            # For server mode, joining is the response
            self.join_group_call(group_id)
            popup.dismiss()

        def on_no(inst):
            if self.mode.startswith('p2p'):
                self.p2p_manager.send_group_call_response(group_id, 'reject')
            # No explicit rejection needed for server mode, just don't join.
            popup.dismiss()

        yes_btn.bind(on_press=on_yes)
        no_btn.bind(on_press=on_no)
        popup.open()

    @mainthread
    def handle_group_call_response(self, group_id, username, response):
        if group_id != self.active_group_call:
            return
        
        if response == 'accept':
            self.add_message_to_box(f"System: {username} accepted the call. Connecting...", group_id)
            self.pending_group_call_punches.add(username)
            self.p2p_manager.initiate_hole_punch(username)
        else:
            self.add_message_to_box(f"System: {username} declined the call.", group_id)

    @mainthread
    def handle_group_call_hang_up(self, group_id, username):
        if group_id == self.active_group_call:
            # self.audio_threads was part of the old implementation
            self.add_message_to_box(f"System: {username} left the call.", group_id)
            # Update UI for group calls will need to be implemented with WebRTC logic


    def join_server_group_call(self, group_id):
        self.active_group_call = group_id
        self.show_group_call_popup()
        
        # Get public address and inform server
        public_addr = self.get_public_udp_addr()
        self.server_manager.join_group_call(group_id, public_addr)
        
        # Start audio stream to the server
        config = self.config_manager.load_config()
        server_addr = (self.server_manager.host, self.server_manager.port)
        try:
            # In server mode, we use p2p_audio_thread for the single stream to the server
            self.add_message_to_box("Connected to group call via server.", group_id)
        except Exception as e:
            self.add_message_to_box(f"Error starting server audio stream: {e}", group_id)

    @mainthread
    def on_user_joined_call(self, group_id, username):
        if group_id == self.active_group_call:
            self.add_message_to_box(f"System: {username} joined the call.", group_id)
            # Update UI if needed

    @mainthread
    def on_user_left_call(self, group_id, username):
        if group_id == self.active_group_call:
            self.add_message_to_box(f"System: {username} left the call.", group_id)
            # Update UI if needed

    @mainthread
    def on_initial_data_received(self, groups, users):
        self.add_message_to_box("System: Received initial state from server.", 'global')
        self.server_groups.update(groups) # Use update to be safe
        self.on_user_list_update(users)
        for group_id, group_data in groups.items():
            # Check if user is a member before adding to list
            if self.username in group_data.get('members', []):
                self.add_group_to_list(group_id, group_data['name'])


    @mainthread
    def on_user_kicked(self, group_id, kicked_username, admin_username):
        # Using Clock.schedule_once to avoid modifying UI from a network thread directly
        # Although this callback is already decorated with @mainthread, this is safer
        # in case of complex UI updates.
        
        if kicked_username == self.username:
            # You have been kicked
            self.show_popup("Kicked from Group", f"You have been kicked from the group '{self.p2p_manager.groups.get(group_id, {}).get('name')}' by {admin_username}.")
            
            if self.active_chat == group_id:
                self.switch_chat('global') # Switch to global chat
            
            # Remove the group from the UI list
            button_to_remove = None
            for button in self.root.ids.chat_layout.ids.users_list.children:
                if button.text == f"[GROUP] {self.p2p_manager.groups.get(group_id, {}).get('name')}":
                    button_to_remove = button
                    break
            if button_to_remove:
                self.root.ids.chat_layout.ids.users_list.remove_widget(button_to_remove)

            # Clean up local data
            if group_id in self.chat_history:
                del self.chat_history[group_id]
            if self.mode.startswith('p2p') and group_id in self.p2p_manager.groups:
                group_name = self.p2p_manager.groups[group_id].get('name', '')
                del self.p2p_manager.groups[group_id]
            elif self.mode == 'server' and group_id in self.server_groups:
                group_name = self.server_groups[group_id].get('name', '')
                del self.server_groups[group_id]
            else:
                group_name = "Unknown Group"

            self.show_popup("Kicked from Group", f"You have been kicked from the group '{group_name}' by {admin_username}.")

            if self.active_chat == group_id:
                self.switch_chat('global')

            button_to_remove = None
            for button in self.root.ids.chat_layout.ids.users_list.children:
                if button.text == f"[GROUP] {group_name}":
                    button_to_remove = button
                    break
            if button_to_remove:
                self.root.ids.chat_layout.ids.users_list.remove_widget(button_to_remove)

            if group_id in self.chat_history:
                del self.chat_history[group_id]

        else:
            # Another user was kicked
            message = f"System: {kicked_username} was kicked by {admin_username}."
            self.add_message_to_box(message, group_id)
            # self.update_user_list(group_id) # TODO: Need a way to show group members

    def create_emoji_panel(self):
        emoji_panel = self.root.ids.chat_layout.ids.emoji_panel
        
        # Configure the tabbed panel to prevent text overlap and size tabs appropriately.
        tab_panel = TabbedPanel(
            do_default_tab=False,
            tab_pos='top_left',
            tab_width=150  # Give tabs a fixed width to prevent text overlap
        )
        categorized_emojis = self.emoji_manager.get_categorized_emojis()

        for category, emojis in categorized_emojis.items():
            # Reduce font size on tab headers to ensure text fits
            tab = TabbedPanelHeader(text=category, font_size='12sp')
            scroll_view = ScrollView()
            grid = GridLayout(cols=8, spacing=dp(5), size_hint_y=None)
            grid.bind(minimum_height=grid.setter('height'))
            
            for emoji in emojis:
                btn = Button(
                    text=emoji,
                    font_name='EmojiFont',
                    font_size='24sp',
                    # Use device-independent pixels for consistent button sizing
                    size_hint=(None, None),
                    size=(dp(40), dp(40))
                )
                btn.bind(on_press=self.add_emoji_to_input)
                grid.add_widget(btn)
            
            scroll_view.add_widget(grid)
            tab.content = scroll_view
            tab_panel.add_widget(tab)
            
        emoji_panel.add_widget(tab_panel)

    def toggle_emoji_panel(self, instance):
        chat_layout = self.root.ids.chat_layout
        emoji_panel = chat_layout.ids.emoji_panel
        
        # This approach avoids size_hint by directly manipulating width
        target_width = chat_layout.width * 0.3
        
        if emoji_panel.width > 0: # If panel is visible, hide it
            anim = Animation(width=0, d=0.2, t='out_quad')
            emoji_panel.disabled = True
            emoji_panel.opacity = 0
        else: # If panel is hidden, show it
            anim = Animation(width=target_width, d=0.2, t='out_quad')
            emoji_panel.disabled = False
            emoji_panel.opacity = 1
            
        anim.start(emoji_panel)

    def add_emoji_to_input(self, instance):
        self.root.ids.chat_layout.ids.msg_entry.text += instance.text
        self.root.ids.chat_layout.ids.msg_entry.focus = True

    def show_popup(self, title, message):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text=message))
        ok_button = Button(text="OK", size_hint_y=None, height=44)
        box.add_widget(ok_button)
        popup = AnimatedPopup(title=title, content=box, size_hint=(0.7, 0.4))
        ok_button.bind(on_press=popup.dismiss)
        popup.open()

    def on_request_close(self, *args, **kwargs):
        if self.settings_popup:
            self.settings_popup.dismiss()
            return True
        return False

    def on_stop(self):
        if self.p2p_manager:
            self.p2p_manager.stop()
        if self.server_manager:
            self.server_manager.stop()
        if self.bluetooth_manager:
            self.bluetooth_manager.stop()
        if hasattr(self, 'udp_socket') and self.udp_socket:
            self.udp_socket.close()
        if self.plugin_manager:
            self.plugin_manager.unload_plugins()
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        print("Application stopped.")

    # --- Hotkey Logic ---
    def init_hotkeys(self):
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
            self.hotkey_manager.set_hotkey(keys)
        
        self.hotkey_manager.register_callback(self.toggle_mute_hotkey)
        self.hotkey_manager.start()

    def show_settings_popup(self, instance):
        try:
            config = self.config_manager.load_config()
            # Pass the app instance to the settings popup so it can access the plugin manager
            self.settings_popup = SettingsPopup(self.tr, config, app=self)
            self.settings_popup.bind(on_dismiss=self.on_settings_dismiss)
            self.settings_popup.open()
        except Exception as e:
            import traceback
            error_str = traceback.format_exc()
            print(f"CRASH IN SETTINGS: {error_str}")
            self.show_popup("Error", f"Could not open settings:\n{e}")

    def on_settings_dismiss(self, popup):
        self.settings_popup = None
        config = self.config_manager.load_config()
        
        # Handle hotkey changes
        new_hotkey = getattr(popup, 'hotkey', None)
        if new_hotkey:
            self.hotkey_manager.set_hotkey(new_hotkey)
            if 'hotkeys' not in config:
                config['hotkeys'] = {}
            hotkey_str = ' + '.join(SettingsPopup.key_to_str(k) for k in new_hotkey)
            config['hotkeys']['mute'] = hotkey_str
            self.add_message_to_box(self.tr.get('system_hotkey_set', hotkey=hotkey_str), 'global')

        # Handle audio device changes
        if hasattr(popup, 'config'):
             config['input_device_index'] = popup.config.get('input_device_index')
             config['output_device_index'] = popup.config.get('output_device_index')
             config['input_volume'] = popup.config.get('input_volume')
             config['output_volume'] = popup.config.get('output_volume')
             self.add_message_to_box(self.tr.get('system_audio_settings_saved', 'Audio settings saved.'), 'global')
             self.apply_audio_settings(config)

        self.config_manager.save_config(config)

    @mainthread
    def toggle_mute_hotkey(self):
        self.is_muted = not self.is_muted
        
        # Mute/unmute WebRTC call
        # This needs to be implemented in WebRTCManager by controlling the audio track
        
        # Update UI
        if self.call_popup:
            self.call_popup.is_muted = self.is_muted
            self.call_popup.mute_button.text = self.tr.get('unmute_button') if self.is_muted else self.tr.get('mute_button')
        
        if self.is_muted:
            self.add_message_to_box(self.tr.get('system_audio_muted'), 'global')
        else:
            self.add_message_to_box(self.tr.get('system_audio_unmuted'), 'global')


    def apply_audio_settings(self, config):
        input_device = config.get('input_device_index')
        output_device = config.get('output_device_index')
        input_volume = config.get('input_volume')
        output_volume = config.get('output_volume')

        if input_device is not None and input_volume is not None:
            # It might be better to check if the device is available first
            # but for now, we'll just try to set it.
            self.audio_manager.set_volume(input_device, 'input', input_volume)
        if output_device is not None and output_volume is not None:
            self.audio_manager.set_volume(output_device, 'output', output_volume)

    def on_file_drop(self, window, file_path, x, y):
        """Callback for when a file is dropped onto the window."""
        try:
            filepath_str = file_path.decode('utf-8')
            print(f"File dropped: {filepath_str}")
            if self.plugin_manager:
                # Find the file transfer plugin and call its handler
                ft_plugin = self.plugin_manager.get_plugin_by_id('file_transfer')
                if ft_plugin and ft_plugin['instance']:
                    ft_plugin['instance'].handle_dropped_file(filepath_str)
                else:
                    self.add_message_to_box("System: File transfer plugin not loaded.", 'global')
        except Exception as e:
            print(f"Error handling dropped file: {e}")
            self.add_message_to_box(f"Error handling drop: {e}", 'global')


# Helper for theming
def set_bg(widget, color):
    widget.canvas.before.clear()
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    def update_rect(instance, value):
        rect.pos = instance.pos
        rect.size = instance.size
    widget.bind(pos=update_rect, size=update_rect)

if __name__ == '__main__':
    VoiceChatApp().run()
