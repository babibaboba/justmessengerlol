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
import sounddevice as sd
import soundfile as sf
import numpy as np


# Kivy imports
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, AudioStreamTrack
from av import AudioFrame
from kivymd.uix.label import MDLabel
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.dialog import MDDialog
from kivy.uix.scrollview import ScrollView
from kivymd.uix.slider import MDSlider
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.selectioncontrol import MDSwitch, MDCheckbox
from kivy.clock import mainthread, Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.core.audio import SoundLoader
from kivy.core.text import LabelBase
from kivymd.theming import ThemeManager
from kivy.metrics import dp
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.floatlayout import MDFloatLayout
from kivy.utils import rgba

# --- Set borderless before anything else ---
Window.borderless = True
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
            'Animals & Nature': list(range(0x1F400, 0x1F440)),
            'Food & Drink': list(range(0x1F330, 0x1F390)),
            'Symbols & Pictographs': list(range(0x1F300, 0x1F600)),
            'Transport & Map': list(range(0x1F680, 0x1F700)),
            'Objects': list(range(0x1F500, 0x1F540)),
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


class AudioManager:
    """Manages all audio-related functionality like devices, recording, and playback."""
    def __init__(self, app, callback_queue):
        self.app = app
        self.callback_queue = callback_queue
        self.is_recording = False
        self.is_testing_mic = False
        self.recording_stream = None
        self.mic_test_stream = None
        self.recording_file = None
        self.input_volume = 1.0  # Gain factor from 0.0 to 1.0+
        self.output_volume = 1.0

    def resample_and_frame(self, data, sample_rate, block_size):
        pts = int(datetime.utcnow().timestamp() * 1000)
        return AudioFrame(
            channels=1,
            data=data,
            sample_rate=sample_rate,
            sample_width=2, # 16-bit audio
            timestamp=pts,
            time_base='1/1000'
        )

    def get_devices(self):
        """Returns a tuple of (input_devices, output_devices) dictionaries."""
        input_devices = {}
        output_devices = {}
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                display_name = f"{sd.query_hostapis(device['hostapi'])['name']}: {device['name']}"
                if device['max_input_channels'] > 0:
                    input_devices[display_name] = i
                if device['max_output_channels'] > 0:
                    output_devices[display_name] = i
        except Exception as e:
            print(f"Error getting audio devices: {e}")
        return input_devices, output_devices

    def start_recording(self, filename, device_index):
        """Starts recording audio from a specific device to a file."""
        if self.is_recording:
            return False
        
        self.is_recording = True
        
        try:
            samplerate = 44100
            channels = 1
            
            self.recording_file = sf.SoundFile(filename, mode='x', samplerate=samplerate, channels=channels)

            def audio_callback(indata, frames, time, status):
                if status:
                    print(status, file=sys.stderr)
                if self.is_recording and self.recording_file:
                    processed_data = indata * self.input_volume
                    self.recording_file.write(processed_data)

            self.recording_stream = sd.InputStream(
                samplerate=samplerate,
                device=device_index,
                channels=channels,
                callback=audio_callback
            )
            self.recording_stream.start()
            print(f"Recording started to {filename}")
            return True
        except Exception as e:
            print(f"Error starting recording: {e}")
            self.is_recording = False
            if self.recording_file:
                self.recording_file.close()
                self.recording_file = None
            return False

    def stop_recording(self):
        """Stops the current recording."""
        if not self.is_recording:
            return
        
        print("Stopping recording...")
        if self.recording_stream:
            self.recording_stream.stop()
            self.recording_stream.close()
            self.recording_stream = None
        
        if self.recording_file:
            self.recording_file.close()
            self.recording_file = None
            
        self.is_recording = False
        print("Recording stopped.")

    def start_mic_test(self, input_device_index, output_device_index):
        """Starts a microphone test with audio loopback and volume meter."""
        if self.is_testing_mic:
            return

        self.is_testing_mic = True
        try:
            samplerate = 44100
            
            def audio_callback(indata, outdata, frames, time, status):
                if status:
                    print(status, file=sys.stderr)
                
                # Process input volume
                processed_data = indata * self.input_volume
                
                # Loopback audio to output device
                outdata[:] = processed_data
                
                # Update volume meter
                volume_norm = np.linalg.norm(processed_data) * 10
                self.callback_queue.put(('mic_level', min(1.0, volume_norm)))

            self.mic_test_stream = sd.Stream(
                device=(input_device_index, output_device_index),
                samplerate=samplerate,
                channels=1,
                callback=audio_callback
            )
            self.mic_test_stream.start()
            print("Mic loopback test started.")
        except Exception as e:
            print(f"Error starting mic test: {e}")
            self.is_testing_mic = False

    def stop_mic_test(self):
        """Stops the microphone test."""
        if not self.is_testing_mic:
            return
            
        if self.mic_test_stream:
            self.mic_test_stream.stop()
            self.mic_test_stream.close()
            self.mic_test_stream = None
        self.is_testing_mic = False
        print("Mic loopback test stopped.")

    def play_test_sound(self, device_index):
        """Plays a test sound on the specified output device."""
        try:
            samplerate = 44100
            frequency = 440
            duration = 1.0
            t = np.linspace(0., duration, int(samplerate * duration), endpoint=False)
            amplitude = 0.5
            waveform = amplitude * np.sin(2. * np.pi * frequency * t)
            
            # Apply output volume
            processed_waveform = waveform * self.output_volume
            
            print(f"Playing test sound on device {device_index} with volume {self.output_volume}")
            sd.play(processed_waveform, samplerate, device=device_index, blocking=False)
        except Exception as e:
            print(f"Error playing test sound: {e}")

    def set_volume(self, level, vol_type='input'):
        """Sets the input or output volume gain level (0.0 to ...)."""
        if vol_type == 'input':
            self.input_volume = level
            print(f"Set input volume to {level}")
        elif vol_type == 'output':
            self.output_volume = level
            print(f"Set output volume to {level}")

class MicrophoneStreamTrack(AudioStreamTrack):
    def __init__(self, audio_manager, device_index):
        super().__init__()
        self.audio_manager = audio_manager
        self.device_index = device_index
        self.audio_queue = asyncio.Queue()
        self.stream = None
        self.running = False
        self.muted = False

    def set_muted(self, muted):
        """Sets the muted state of the track."""
        self.muted = muted

    def start(self):
        if self.running:
            return
        self.running = True
        
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"MicrophoneStreamTrack status: {status}")
            try:
                self.audio_queue.put_nowait(indata.tobytes())
            except asyncio.QueueFull:
                pass # Drop frames if the queue is full

        self.stream = sd.RawInputStream(
            samplerate=48000,
            blocksize=960, # 20ms of audio at 48kHz
            device=self.device_index,
            channels=1,
            dtype='int16',
            callback=audio_callback
        )
        self.stream.start()
        print("MicrophoneStreamTrack started.")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print("MicrophoneStreamTrack stopped.")

    async def recv(self):
        if not self.running:
            raise MediaStreamError

        if self.muted:
            # When muted, send a frame of silence.
            # 960 samples * 2 bytes/sample (int16) = 1920 bytes
            silent_data = b'\x00' * 1920
            return self.audio_manager.resample_and_frame(silent_data, 48000, 960)

        data = await self.audio_queue.get()
        return self.audio_manager.resample_and_frame(data, 48000, 960)

class AudioTrackPlayer:
    def __init__(self, track, audio_manager, device_index):
        self.track = track
        self.audio_manager = audio_manager
        self.device_index = device_index
        self.stream = None
        self.player_thread = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        
        self.stream = sd.RawOutputStream(
            samplerate=48000,
            blocksize=960,
            device=self.device_index,
            channels=1,
            dtype='int16'
        )
        self.stream.start()
        
        self.player_thread = threading.Thread(target=self.run, daemon=True)
        self.player_thread.start()
        print("AudioTrackPlayer started.")

    def stop(self):
        self.running = False
        if self.player_thread:
            self.player_thread.join()
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print("AudioTrackPlayer stopped.")

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def receive_frames():
            while self.running:
                try:
                    frame = await self.track.recv()
                    self.stream.write(frame.to_ndarray(format='s16', shape=(frame.samples, 1)))
                except MediaStreamError:
                    break
                except Exception as e:
                    print(f"Audio player error: {e}")
                    break
        
        loop.run_until_complete(receive_frames())

class WebRTCManager(threading.Thread):
    def __init__(self, audio_manager, callback_queue):
        super().__init__(daemon=True)
        self.audio_manager = audio_manager
        self.callback_queue = callback_queue
        self.loop = None
        self.peer_connections = {} # {peer_username: RTCPeerConnection}
        self.audio_players = {} # {peer_username: AudioTrackPlayer}
        self.mic_track = None
        self.running = True

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def stop(self):
        self.running = False
        if self.loop:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
            future.result()
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def _shutdown(self):
        if self.mic_track:
            self.mic_track.stop()
        for player in self.audio_players.values():
            player.stop()
        for pc in self.peer_connections.values():
            await pc.close()

    def set_mute(self, is_muted):
        """Toggles mute on the microphone track."""
        if self.mic_track:
            # This is called from the main Kivy thread.
            # The mic_track's muted flag is accessed from the asyncio thread in recv().
            # A simple boolean flag assignment is atomic in Python, so this is thread-safe.
            self.mic_track.set_muted(is_muted)

    async def _create_peer_connection(self, peer_username):
        pc = RTCPeerConnection()
        self.peer_connections[peer_username] = pc

        @pc.on("track")
        async def on_track(track):
            print(f"Track {track.kind} received from {peer_username}")
            if track.kind == "audio":
                config = self.audio_manager.app.config_manager.load_config()
                output_device_name = config.get('output_device_name', 'Default')
                _, output_devices = self.audio_manager.get_devices()
                device_index = output_devices.get(output_device_name, sd.default.device[1])
                
                player = AudioTrackPlayer(track, self.audio_manager, device_index)
                self.audio_players[peer_username] = player
                player.start()

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {peer_username} is {pc.connectionState}")
            if pc.connectionState in ["failed", "closed", "disconnected"]:
                if peer_username in self.audio_players:
                    self.audio_players[peer_username].stop()
                    del self.audio_players[peer_username]
                if pc.connectionState == "failed":
                    await pc.close()
                    if peer_username in self.peer_connections:
                        del self.peer_connections[peer_username]

        return pc

    def _start_mic(self):
        if self.mic_track:
            self.mic_track.stop()
        
        config = self.audio_manager.app.config_manager.load_config()
        input_device_name = config.get('input_device_name', 'Default')
        input_devices, _ = self.audio_manager.get_devices()
        device_index = input_devices.get(input_device_name, sd.default.device[0])
        
        self.mic_track = MicrophoneStreamTrack(self.audio_manager, device_index)
        self.mic_track.start()

    def start_call(self, peer_username):
        if not self.loop: return
        future = asyncio.run_coroutine_threadsafe(self._start_call(peer_username), self.loop)
        return future.result()

    async def _start_call(self, peer_username):
        self._start_mic()
        pc = await self._create_peer_connection(peer_username)
        pc.addTrack(self.mic_track)
        
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        sdp_offer = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        self.callback_queue.put(('webrtc_offer_created', {'peer': peer_username, 'offer': sdp_offer}))

    def handle_offer(self, peer_username, offer_sdp):
        if not self.loop: return
        future = asyncio.run_coroutine_threadsafe(self._handle_offer(peer_username, offer_sdp), self.loop)
        return future.result()

    async def _handle_offer(self, peer_username, offer_sdp):
        self._start_mic()
        pc = await self._create_peer_connection(peer_username)
        
        offer = RTCSessionDescription(sdp=offer_sdp["sdp"], type=offer_sdp["type"])
        await pc.setRemoteDescription(offer)
        
        pc.addTrack(self.mic_track)
        
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


class TitleBar(MDBoxLayout):
    def __init__(self, **kwargs):
        self.app = kwargs.pop('app', None)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(32)
        self.orientation = 'horizontal'
        if self.app:
            self.md_bg_color = self.app.theme_cls.primary_color
        else:
            self.md_bg_color = [0.5, 0, 0.5, 1]  # Default purple if app not available

        # Minimize button
        self.minimize_btn = MDIconButton(
            icon='window-minimize',
            theme_text_color='Custom',
            text_color=[1, 1, 1, 1]
        )
        self.minimize_btn.size_hint = (None, None)
        self.minimize_btn.size = (dp(45), dp(30))
        self.minimize_btn.bind(on_release=self.minimize_window)
        self.add_widget(self.minimize_btn)

        # Maximize button
        self.maximize_btn = MDIconButton(
            icon='window-maximize',
            theme_text_color='Custom',
            text_color=[1, 1, 1, 1]
        )
        self.maximize_btn.size_hint = (None, None)
        self.maximize_btn.size = (dp(45), dp(30))
        self.maximize_btn.bind(on_release=self.maximize_window)
        self.add_widget(self.maximize_btn)

        # Close button
        self.close_btn = MDIconButton(
            icon='window-close',
            theme_text_color='Custom',
            text_color=[1, 1, 1, 1]
        )
        self.close_btn.size_hint = (None, None)
        self.close_btn.size = (dp(45), dp(30))
        self.close_btn.bind(on_release=self.close_window)
        self.add_widget(self.close_btn)

        # Title label - draggable area
        self.title_label = MDLabel(
            text='JustMessenger',
            halign='center',
            valign='center',
            theme_text_color='Custom',
            text_color=[1, 1, 1, 1],
            font_style='H6'
        )
        self.add_widget(self.title_label)

        # Bind touch events for dragging
        self.title_label.bind(on_touch_down=self.on_touch_down_title)
        self.title_label.bind(on_touch_move=self.on_touch_move_title)

    def on_touch_down_title(self, instance, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self.start_pos = touch.pos
            self.start_window_pos = Window.left, Window.top
            return True

    def on_touch_move_title(self, instance, touch):
        if touch.grab_current is self:
            dx = touch.x - self.start_pos[0]
            dy = touch.y - self.start_pos[1]
            Window.left = self.start_window_pos[0] + dx
            Window.top = self.start_window_pos[1] + dy

    def minimize_window(self, instance):
        Window.minimize()

    def maximize_window(self, instance):
        if Window.fullscreen:
            Window.fullscreen = False
        else:
            Window.fullscreen = 'auto'

    def close_window(self, instance):
        if self.app:
            self.app.stop()

class AnimatedPopup(MDDialog):
    pass

class RootLayout(MDBoxLayout): pass
class ChatLayout(MDBoxLayout): pass

# Screen class definitions for Kivy language
class MainScreen(Screen): pass
class ProfileScreen(Screen): pass
class SettingsScreen(Screen): pass
class CallsScreen(Screen): pass

class CallPopup(MDDialog):
    def __init__(self, peer_username, translator, **kwargs):
        self.tr = translator
        self.is_muted = False
        
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))
        
        content_layout.add_widget(MDLabel(text=self.tr.get('call_label', peer_username=peer_username), halign='center'))
        
        self.mute_button = MDRaisedButton(text=self.tr.get('mute_button'))
        self.mute_button.bind(on_press=self.toggle_mute)
        content_layout.add_widget(self.mute_button)
        
        super().__init__(
            title=self.tr.get('call_title', 'Call'),
            type="custom",
            content_cls=content_layout,
            buttons=[
                MDRaisedButton(text=self.tr.get('hang_up_button'), on_release=self.hang_up)
            ],
            auto_dismiss=False,
            **kwargs
        )
        self.register_event_type('on_mute_toggle')

    def toggle_mute(self, instance):
        self.is_muted = not self.is_muted
        self.mute_button.text = self.tr.get('unmute_button') if self.is_muted else self.tr.get('mute_button')
        self.dispatch('on_mute_toggle', self.is_muted)

    def hang_up(self, instance):
        self.dismiss()

    def on_mute_toggle(self, is_muted):
        pass

class ContactRequestPopup(MDDialog):
    def __init__(self, username, translator, **kwargs):
        self.tr = translator
        
        accept_btn = MDRaisedButton(text=self.tr.get('accept_button', 'Accept'))
        decline_btn = MDFlatButton(text=self.tr.get('decline_button', 'Decline'))
        
        super().__init__(
            title=self.tr.get('contact_request_title', 'Contact Request'),
            text=self.tr.get('contact_request_text', username=username),
            buttons=[accept_btn, decline_btn],
            auto_dismiss=False,
            **kwargs
        )
        
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

class PasswordPromptPopup(MDDialog):
    def __init__(self, username, translator, **kwargs):
        self.tr = translator
        
        self.password_input = MDTextField(multiline=False, password=True, hint_text="Password")
        
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        content_layout.add_widget(MDLabel(text=self.tr.get('password_prompt_text', username=username)))
        content_layout.add_widget(self.password_input)
        content_layout.height = "120dp" # Adjust height for content

        ok_btn = MDRaisedButton(text=self.tr.get('ok_button', 'OK'))
        cancel_btn = MDFlatButton(text=self.tr.get('cancel_button', 'Cancel'))

        super().__init__(
            title=self.tr.get('password_prompt_title', 'Password Required'),
            type="custom",
            content_cls=content_layout,
            buttons=[ok_btn, cancel_btn],
            auto_dismiss=False,
            **kwargs
        )
        
        ok_btn.bind(on_press=self.submit)
        cancel_btn.bind(on_press=self.cancel)
        
        self.register_event_type('on_submit')

    def submit(self, instance):
        self.dispatch('on_submit', self.password_input.text)
        self.dismiss()

    def cancel(self, instance):
        self.dispatch('on_submit', None) # Indicate cancellation
        self.dismiss()

    def on_submit(self, password):
        pass

class GroupCallPopup(MDDialog):
    def __init__(self, group_name, translator, **kwargs):
        self.tr = translator
        
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))
        content_layout.add_widget(MDLabel(text=self.tr.get('participants_label', 'Participants:'), halign='center'))
        self.participants_list = MDBoxLayout(orientation='vertical', size_hint_y=None)
        self.participants_list.bind(minimum_height=self.participants_list.setter('height'))
        content_layout.add_widget(self.participants_list)
        
        hang_up_button = MDRaisedButton(text=self.tr.get('hang_up_button'))
        hang_up_button.bind(on_press=self.hang_up)
        
        super().__init__(
            title=self.tr.get('group_call_title', group_name=group_name),
            type="custom",
            content_cls=content_layout,
            buttons=[hang_up_button],
            auto_dismiss=False,
            **kwargs
        )

    def hang_up(self, instance):
        self.dismiss()


class ManageGroupPopup(MDDialog):
    def __init__(self, translator, members, **kwargs):
        self.tr = translator
        self.members = members
        self.register_event_type('on_kick_user')
        self.register_event_type('on_invite_user')

        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))

        scroll_view = ScrollView(size_hint_y=None, height="300dp")
        scroll_content = MDBoxLayout(orientation='vertical', size_hint_y=None, spacing="5dp")
        scroll_content.bind(minimum_height=scroll_content.setter('height'))

        for member in self.members:
            member_layout = MDBoxLayout(size_hint_y=None, height=dp(40))
            member_label = MDLabel(text=member)
            kick_button = MDRaisedButton(text=self.tr.get('kick_button', 'Kick'), size_hint_x=None, width=dp(80))
            kick_button.bind(on_press=partial(self.kick_user, member))
            member_layout.add_widget(member_label)
            member_layout.add_widget(kick_button)
            scroll_content.add_widget(member_layout)

        scroll_view.add_widget(scroll_content)
        content_layout.add_widget(scroll_view)

        invite_button = MDRaisedButton(text=self.tr.get('invite_button', 'Invite'))
        invite_button.bind(on_press=self.invite_user)

        close_button = MDFlatButton(text=self.tr.get('close_button', 'Close'))
        close_button.bind(on_press=lambda x: self.dismiss())

        super().__init__(
            title=self.tr.get('manage_group_title', 'Manage Group'),
            type="custom",
            content_cls=content_layout,
            buttons=[invite_button, close_button],
            **kwargs
        )

    def invite_user(self, instance):
        self.dispatch('on_invite_user')
        self.dismiss()

    def on_invite_user(self):
        pass

    def kick_user(self, username, instance):
        self.dispatch('on_kick_user', username)
        self.dismiss()

    def on_kick_user(self, username):
        pass


class AudioMessageWidget(MDBoxLayout):
    def __init__(self, filepath, sender, tr, **kwargs):
        super().__init__(**kwargs)
        self.tr = tr
        self.filepath = filepath
        self.sound = SoundLoader.load(filepath)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(40)
        
        self.label = MDLabel(text=self.tr.get('audio_from_sender', "Audio from {sender}", sender=sender))
        self.play_button = MDIconButton(icon='play')
        self.play_button.bind(on_press=self.toggle_play)
        
        self.add_widget(self.label)
        self.add_widget(self.play_button)

    def toggle_play(self, instance):
        if not self.sound:
            return
        if self.sound.state == 'play':
            self.sound.stop()
            self.play_button.icon = 'play'
        else:
            self.sound.play()
            self.play_button.icon = 'pause'
            self.sound.bind(on_stop=self.on_sound_stop)

    def on_sound_stop(self, instance):
        self.play_button.icon = 'play'


class ModeSelectionPopup(MDDialog):
    def __init__(self, translator, app=None, **kwargs):
        self.tr = translator
        self.app = app
        self.mode = None

        content_layout = MDBoxLayout(orientation='vertical', spacing="15dp", size_hint_y=None, padding="20dp")
        content_layout.bind(minimum_height=content_layout.setter('height'))
        content_layout.add_widget(MDLabel(text=self.tr.get('mode_selection_label'), halign='center', font_style='H5'))

        modes = {
            'p2p_internet': self.tr.get('mode_p2p_internet'),
            'p2p_local': self.tr.get('mode_p2p_local'),
            'p2p_bluetooth': self.tr.get('mode_p2p_bluetooth', 'P2P (Bluetooth)'),
            'server': self.tr.get('mode_client_server')
        }

        for mode_id, mode_text in modes.items():
            btn = MDRaisedButton(
                text=mode_text,
                size_hint_x=1,
                size_hint_y=None,
                height=dp(60),
                font_style='Body1',
                md_bg_color=self.app.theme_cls.primary_color if self.app else [0.5, 0, 0.5, 1]
            )
            btn.bind(on_press=partial(self.select_mode, mode_id))
            content_layout.add_widget(btn)

        super().__init__(
            title=self.tr.get('mode_selection_title'),
            type="custom",
            content_cls=content_layout,
            auto_dismiss=False,
            size_hint=(0.6, 0.7),
            **kwargs
        )

    def select_mode(self, mode, instance):
        self.mode = mode
        self.dismiss()

class UsernamePopup(MDDialog):
    def __init__(self, translator, current_username, **kwargs):
        self.tr = translator
        self.username_input = MDTextField(text=current_username, multiline=False, hint_text=self.tr.get('username_dialog_label'))
        ok_button = MDRaisedButton(text=self.tr.get('ok_button', 'OK'))
        
        super().__init__(
            title=self.tr.get('username_dialog_title'),
            type="custom",
            content_cls=self.username_input,
            buttons=[ok_button],
            auto_dismiss=False,
            **kwargs
        )
        ok_button.bind(on_press=self.validate_username)

    def validate_username(self, instance):
        username = self.username_input.text.strip()
        if username:
            self.username = username
            self.dismiss()

class ServerLoginPopup(MDDialog):
    def __init__(self, translator, config, **kwargs):
        self.tr = translator
        server_config = config.get('server', {})
        
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None)
        content_layout.height = "200dp"
        
        self.ip_input = MDTextField(text=server_config.get('host', '127.0.0.1'), hint_text=self.tr.get('server_ip_label', 'Server IP:'))
        self.port_input = MDTextField(text=str(server_config.get('port', 12345)), hint_text=self.tr.get('server_port_label', 'Server Port:'))
        self.password_input = MDTextField(text='', password=True, hint_text=self.tr.get('server_password_label', 'Password (optional):'))
        
        content_layout.add_widget(self.ip_input)
        content_layout.add_widget(self.port_input)
        content_layout.add_widget(self.password_input)
        
        connect_button = MDRaisedButton(text=self.tr.get('connect_button', 'Connect'))
        
        super().__init__(
            title=self.tr.get('server_login_title', 'Connect to Server'),
            type="custom",
            content_cls=content_layout,
            buttons=[connect_button],
            auto_dismiss=False,
            **kwargs
        )
        connect_button.bind(on_press=self.connect)

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

class SettingsTab(MDBoxLayout, MDTabsBase):
    pass

class SettingsPopup(MDDialog):
    def __init__(self, translator, config, app, **kwargs):
        self.app = app
        self.tr = translator
        self.config = config
        self.new_hotkey = set()
        self.recording = False
        self.listener = None
        self.is_testing = False
        self.saved = False
        self.language_menu = None
        self.input_device_menu = None
        self.output_device_menu = None
        
        # --- Main Layout ---
        content_layout = MDBoxLayout(orientation='vertical', size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))
        
        tab_panel = MDTabs()
        tab_panel.add_widget(self.create_general_tab())
        tab_panel.add_widget(self.create_hotkeys_tab())
        tab_panel.add_widget(self.create_audio_tab())
        tab_panel.add_widget(self.create_security_tab())
        tab_panel.add_widget(self.create_plugins_tab())
        content_layout.add_widget(tab_panel)

        save_btn = MDRaisedButton(text=self.tr.get('save_button'))
        save_btn.bind(on_press=self.save_and_dismiss)
        cancel_btn = MDFlatButton(text=self.tr.get('cancel_button', 'Cancel'))
        cancel_btn.bind(on_press=self.cancel_and_dismiss)

        super().__init__(
            title=self.tr.get('settings_title', 'Settings'),
            type="custom",
            content_cls=content_layout,
            buttons=[save_btn, cancel_btn],
            auto_dismiss=False,
            **kwargs
        )
        
    def create_general_tab(self):
        layout = MDBoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
        layout.add_widget(MDLabel(text=self.tr.get('language_label', 'Language'), font_style='H6'))

        available_languages = {'en': 'English', 'ru': 'Русский'}
        current_lang_code = self.app.tr.get_language()
        current_lang_name = available_languages.get(current_lang_code, 'English')
        
        self.language_button = MDRaisedButton(text=current_lang_name)
        self.language_button.bind(on_release=self.open_language_menu)
        layout.add_widget(self.language_button)
        
        menu_items = [
            {"text": name, "viewclass": "OneLineListItem", "on_release": lambda x=code: self.set_language(x)}
            for code, name in available_languages.items()
        ]
        self.language_menu = MDDropdownMenu(caller=self.language_button, items=menu_items, width_mult=4)
        self.selected_language = current_lang_code

        layout.add_widget(MDBoxLayout()) # Spacer
        
        return_button = MDRaisedButton(text=self.tr.get('return_to_main_menu_button', 'Return to Main Menu'), size_hint_y=None, height=dp(44))
        return_button.bind(on_press=self.app.return_to_main_menu)
        layout.add_widget(return_button)
        
        return SettingsTab(layout, title=self.tr.get('general_tab', 'General'))

    def open_language_menu(self, button):
        self.language_menu.open()

    def set_language(self, lang_code):
        self.selected_language = lang_code
        self.language_button.text = self.language_menu.items[0]['text'] if lang_code == 'en' else self.language_menu.items[1]['text']
        self.language_menu.dismiss()

    def create_hotkeys_tab(self):
        layout = MDBoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
        layout.add_widget(MDLabel(text=self.tr.get('hotkey_settings_title', 'Mute Hotkey'), font_style='H6'))
        current_hotkey_str = self.config.get('hotkeys', {}).get('mute', 'ctrl+m')
        layout.add_widget(MDLabel(text=self.tr.get('hotkey_mute_label')))
        self.hotkey_label = MDLabel(text=current_hotkey_str)
        layout.add_widget(self.hotkey_label)
        self.record_button = MDRaisedButton(text=self.tr.get('hotkey_record_button'))
        self.record_button.bind(on_press=self.toggle_record)
        layout.add_widget(self.record_button)
        return SettingsTab(layout, title=self.tr.get('hotkeys_tab', 'Hotkeys'))

    def create_audio_tab(self):
        layout = MDBoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
        layout.add_widget(MDLabel(text=self.tr.get('audio_settings_title', 'Audio Settings'), font_style='H6'))

        input_devices, output_devices = self.app.audio_manager.get_devices()
        self.input_device_map = input_devices
        self.output_device_map = output_devices

        layout.add_widget(MDLabel(text=self.tr.get('input_device_label', 'Input Device (Microphone)')))
        self.input_device_button = MDRaisedButton(text=self.config.get('input_device_name', 'Default'))
        self.input_device_button.bind(on_release=self.open_input_device_menu)
        layout.add_widget(self.input_device_button)
        
        input_menu_items = [{"text": name, "viewclass": "OneLineListItem", "on_release": lambda x=name: self.set_input_device(x)} for name in input_devices.keys()]
        self.input_device_menu = MDDropdownMenu(caller=self.input_device_button, items=input_menu_items, width_mult=4)

        layout.add_widget(MDLabel(text=self.tr.get('output_device_label', 'Output Device (Speakers)')))
        self.output_device_button = MDRaisedButton(text=self.config.get('output_device_name', 'Default'))
        self.output_device_button.bind(on_release=self.open_output_device_menu)
        layout.add_widget(self.output_device_button)

        output_menu_items = [{"text": name, "viewclass": "OneLineListItem", "on_release": lambda x=name: self.set_output_device(x)} for name in output_devices.keys()]
        self.output_device_menu = MDDropdownMenu(caller=self.output_device_button, items=output_menu_items, width_mult=4)

        layout.add_widget(MDLabel(text=self.tr.get('input_volume_label', 'Input Volume')))
        self.input_volume_slider = MDSlider(min=0, max=100, value=self.config.get('input_volume', 80))
        layout.add_widget(self.input_volume_slider)

        layout.add_widget(MDLabel(text=self.tr.get('output_volume_label', 'Output Volume')))
        self.output_volume_slider = MDSlider(min=0, max=100, value=self.config.get('output_volume', 80))
        layout.add_widget(self.output_volume_slider)

        test_layout = MDBoxLayout(spacing="10dp", size_hint_y=None, height=dp(44))
        self.mic_test_button = MDRaisedButton(text=self.tr.get('mic_test_button', 'Test Microphone'))
        self.mic_test_button.bind(on_press=self.toggle_mic_test)
        self.mic_level_bar = MDProgressBar(max=1.0, value=0, size_hint_x=1.5)
        test_layout.add_widget(self.mic_test_button)
        test_layout.add_widget(self.mic_level_bar)
        layout.add_widget(test_layout)
        
        speaker_test_button = MDRaisedButton(text=self.tr.get('speaker_test_button', 'Test Speakers'), size_hint_y=None, height=dp(44))
        speaker_test_button.bind(on_press=self.test_speakers)
        layout.add_widget(speaker_test_button)

        return SettingsTab(layout, title=self.tr.get('audio_tab', 'Audio'))

    def open_input_device_menu(self, button):
        self.input_device_menu.open()

    def set_input_device(self, device_name):
        self.input_device_button.text = device_name
        self.input_device_menu.dismiss()
        self.on_device_change()
        
    def open_output_device_menu(self, button):
        self.output_device_menu.open()
        
    def set_output_device(self, device_name):
        self.output_device_button.text = device_name
        self.output_device_menu.dismiss()

    def on_device_change(self):
        if self.is_testing:
            self.app.audio_manager.stop_mic_test()
            input_device_index = self.input_device_map.get(self.input_device_button.text, sd.default.device[0])
            output_device_index = self.output_device_map.get(self.output_device_button.text, sd.default.device[1])
            self.app.audio_manager.start_mic_test(input_device_index, output_device_index)

    def toggle_mic_test(self, instance):
        self.is_testing = not self.is_testing
        if self.is_testing:
            self.mic_test_button.text = self.tr.get('mic_test_stop_button', 'Stop Test')
            input_device_index = self.input_device_map.get(self.input_device_button.text, sd.default.device[0])
            output_device_index = self.output_device_map.get(self.output_device_button.text, sd.default.device[1])
            self.app.audio_manager.start_mic_test(input_device_index, output_device_index)
        else:
            self.mic_test_button.text = self.tr.get('mic_test_button', 'Test Microphone')
            self.app.audio_manager.stop_mic_test()
            self.mic_level_bar.value = 0

    def test_speakers(self, instance):
        device_index = self.output_device_map.get(self.output_device_button.text, sd.default.device[1])
        threading.Thread(target=self.app.audio_manager.play_test_sound, args=(device_index,), daemon=True).start()

    def create_security_tab(self):
        layout = MDBoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
        layout.add_widget(MDLabel(text=self.tr.get('p2p_password_label', 'P2P Connection Password'), font_style='H6'))
        layout.add_widget(MDLabel(text=self.tr.get('p2p_password_desc', 'Require a password for incoming P2P connections.')))
        self.p2p_password_input = MDTextField(
            text=self.config.get('security', {}).get('p2p_password', ''),
            password=True
        )
        layout.add_widget(self.p2p_password_input)
        return SettingsTab(layout, title=self.tr.get('security_tab', 'Security'))

    def create_plugins_tab(self):
        layout = MDBoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
        scroll_view = ScrollView()
        scroll_content = MDGridLayout(cols=1, size_hint_y=None, spacing="10dp")
        scroll_content.bind(minimum_height=scroll_content.setter('height'))

        self.plugin_switches = {}
        if self.app.plugin_manager and self.app.plugin_manager.plugins:
            for plugin in self.app.plugin_manager.plugins:
                plugin_layout = MDBoxLayout(size_hint_y=None, height=dp(60))
                info_layout = MDBoxLayout(orientation='vertical')
                info_layout.add_widget(MDLabel(text=plugin['name'], font_style='Subtitle1'))
                info_layout.add_widget(MDLabel(text=plugin['description'], font_style='Caption', theme_text_color="Secondary"))
                switch = MDCheckbox(active=plugin['enabled'])
                self.plugin_switches[plugin['id']] = switch
                plugin_layout.add_widget(info_layout)
                plugin_layout.add_widget(switch)
                scroll_content.add_widget(plugin_layout)
        else:
            scroll_content.add_widget(MDLabel(text=self.tr.get('no_plugins_found', 'No plugins found.')))

        scroll_view.add_widget(scroll_content)
        layout.add_widget(scroll_view)
        return SettingsTab(layout, title=self.tr.get('plugins_tab', 'Plugins'))

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
        if self.is_testing:
            self.toggle_mic_test(None)
        self.hotkey = self.new_hotkey
        self.saved = True
        
        self.config['language'] = self.selected_language
        self.config['input_device_name'] = self.input_device_button.text
        self.config['output_device_name'] = self.output_device_button.text
        self.config['input_volume'] = self.input_volume_slider.value
        self.config['output_volume'] = self.output_volume_slider.value

        if 'security' not in self.config:
            self.config['security'] = {}
        self.config['security']['p2p_password'] = self.p2p_password_input.text

        restart_required = False
        if hasattr(self, 'plugin_switches'):
            for plugin in self.app.plugin_manager.plugins:
                plugin_id = plugin['id']
                switch = self.plugin_switches.get(plugin_id)
                if switch is None: continue
                if plugin['enabled'] != switch.active:
                    restart_required = True
                    py_file_path = os.path.join(plugin['path'], f"{plugin['module_name']}.py")
                    disabled_py_file_path = py_file_path + '.disabled'
                    try:
                        if switch.active and os.path.exists(disabled_py_file_path):
                            os.rename(disabled_py_file_path, py_file_path)
                        elif not switch.active and os.path.exists(py_file_path):
                            os.rename(py_file_path, disabled_py_file_path)
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
        if isinstance(key, keyboard.Key): return key.name
        elif isinstance(key, keyboard.KeyCode): return key.char
        return str(key)



class VoiceChatApp(MDApp):
    def build(self):
        self.config_manager = ConfigManager()
        self.tr = Translator(self.config_manager)
        self.icon = 'JustMessenger.png'

        # KivyMD Theme Setup with Purple color scheme
        self.theme_cls.theme_style = "Dark" # Dark theme for modern look
        self.theme_cls.primary_palette = "Purple"
        self.theme_cls.primary_hue = "500"  # Use a standard purple shade
        self.theme_cls.accent_palette = "Purple"
        self.theme_cls.accent_hue = "200"

        # Note: primary_color is read-only in newer KivyMD versions
        # Colors will be defined in the .kv file using rgba() function

        # Register custom fonts
        fonts_path = "./fonts/"
        LabelBase.register(
            name="Roboto",
            fn_regular=os.path.join(fonts_path, "Roboto-Regular.ttf"),
            fn_bold=os.path.join(fonts_path, "Roboto-Bold.ttf")
        )
        LabelBase.register(
            name="NotoSans",
            fn_regular=os.path.join(fonts_path, "NotoSans-Regular.ttf")
        )
        LabelBase.register(
            name="EmojiFont",
            fn_regular=os.path.join(fonts_path, "NotoColorEmoji.ttf")
        )

        self.theme_cls.font_styles["Regular"] = [
            "Roboto",
            16,
            False,
            0.15,
        ]

        return RootLayout()

    def on_start(self):
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
        self.audio_manager = AudioManager(self, self.callback_queue)
        self.webrtc_manager = WebRTCManager(self.audio_manager, self.callback_queue)
        self.hotkey_manager = HotkeyManager()
        self.is_muted = False
        self.plugin_manager = None
        self.emoji_manager = None
        self.is_recording_audio_message = False
        self.root.opacity = 0
        self.contacts = set() # Users who have accepted contact requests
        self.search_user_input = None
        self.settings_popup = None
        
        self.chat_history = {'global': []}
        self.initialized = False
        self.active_chat = 'global' # Can be 'global' or a group_id
        

        Clock.schedule_interval(self.process_callbacks, 0.1)
        Window.bind(on_request_close=self.on_request_close, on_dropfile=self.on_file_drop)
        
        # Set window title before showing any popups
        Window.title = self.tr.get('window_title')
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
                elif event_type == 'mic_level':
                    if self.settings_popup and self.settings_popup.is_testing:
                        self.settings_popup.mic_level_bar.value = event[1]

            except queue.Empty:
                break

    def show_mode_selection_popup(self):
        popup = ModeSelectionPopup(translator=self.tr, app=self)
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

    def return_to_main_menu(self, instance=None):
        """Shuts down the current session and returns to the mode selection screen."""
        # Dismiss settings if it's open
        if self.settings_popup:
            # Unbind dismiss to prevent save logic from running
            self.settings_popup.unbind(on_dismiss=self.on_settings_dismiss)
            self.settings_popup.dismiss()

        # 1. Shut down all managers and network activity
        self.on_stop() # Use the existing on_stop logic

        # 2. Reset the UI to a clean state
        try:
            layout = self.root.ids.chat_layout
            layout.ids.chat_box.clear_widgets()
            layout.ids.conversations_list.clear_widgets()
        except (KeyError, AttributeError):
            print("Warning: Could not reset UI layout")


        # 3. Reset internal state variables
        self.p2p_manager = None
        self.server_manager = None
        self.bluetooth_manager = None
        self.username = None
        self.mode = None
        self.server_groups = {}
        self.active_group_call = None
        self.pending_group_call_punches = set()
        self.call_popup = None
        self.group_call_popup = None
        self.current_peer_addr = None
        self.pending_call_target = None
        self.negotiated_rate = None
        self.is_muted = False
        # Don't reset plugin manager, as it's loaded once.
        # self.plugin_manager = None
        self.is_recording_audio_message = False
        self.contacts = set()
        self.search_user_input = None
        self.hotkey_manager = HotkeyManager() # Re-create the manager for the new session
        
        self.chat_history = {'global': []}
        self.initialized = False # Allow re-initialization
        self.active_chat = 'global'
        
        # 4. Show the mode selection popup to start over
        self.show_mode_selection_popup()

    def initialize_app(self):
        if self.initialized:
            return
        self.initialized = True

        # Bind new widget events with the Telegram-style interface
        input_area = None
        try:
            input_area = self.root.ids.input_area
            input_area.ids.send_button.bind(on_press=self.send_message)
            input_area.ids.emoji_button.bind(on_press=self.toggle_emoji_panel)
            input_area.ids.voice_button.bind(on_press=self.toggle_voice_recording)
            input_area.ids.message_input.bind(on_text_validate=self.send_message)
        except AttributeError as e:
            print(f"Warning: Input area binding failed: {e}")

        # Get main layout reference first
        try:
            main_layout = self.root.ids.main_layout
        except AttributeError as e:
            print(f"Warning: Could not access main layout: {e}")
            main_layout = None

        # Bind main layout interactions
        if main_layout:
            try:
                chat_list_panel = main_layout.ids.chat_list_panel

                # Bind toolbar buttons
                toolbar = chat_list_panel.ids.chat_list_toolbar
                toolbar.ids.hamburger_button.bind(on_press=self.toggle_left_menu)
                toolbar.ids.search_button.bind(on_press=self.open_search)
                toolbar.ids.new_chat_button.bind(on_press=self.create_new_chat)

            except AttributeError as e:
                print(f"Warning: Main layout binding failed: {e}")

            # Bind chat view interactions
            try:
                chat_view_panel = main_layout.ids.chat_view_panel
                chat_header = chat_view_panel.ids.chat_header
                chat_header.ids.user_info_area.bind(on_release=self.open_profile_panel)
                chat_header.ids.chat_menu_button.bind(on_release=self.show_chat_menu)
            except AttributeError as e:
                print(f"Warning: Chat view binding failed: {e}")

        # Only proceed with input_area dependent code if it's available
        if input_area and hasattr(input_area.ids, 'message_input'):
            input_area.ids.message_input.focus = True

        if self.mode.startswith('p2p') and self.mode != 'p2p_bluetooth':
            self.init_p2p_mode()
        elif self.mode == 'p2p_bluetooth':
            self.init_bluetooth_mode()
        elif self.mode == 'server':
            self.init_server_mode()

        config = self.config_manager.load_config()
        self.init_hotkeys()
        self.apply_audio_settings(config) # Apply saved audio settings
        self.root.opacity = 1

        # Initialize and load plugins
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.discover_and_load_plugins()
        self.emoji_manager = EmojiManager()
        self.create_emoji_panel()
        self.webrtc_manager.start()


    def find_p2p_user(self, instance):
        try:
            username = self.root.ids.chat_layout.ids.search_field.text.strip()
            if not username:
                return
            if self.mode == 'p2p_internet' and self.p2p_manager:
                self.add_message_to_box(f"System: Searching for '{username}' in the network...", 'global')
                self.p2p_manager.find_peer(username)
                self.root.ids.chat_layout.ids.search_field.text = ""
        except (KeyError, AttributeError):
            print("Warning: Could not access search field")

    def init_p2p_mode(self):
        p2p_mode_type = 'local' if self.mode == 'p2p_local' else 'internet'
        self.p2p_manager = P2PManager(self.username, self.chat_history, mode=p2p_mode_type)
        callbacks = {
            'peer_discovered': self.on_peer_discovered, 'peer_lost': self.on_peer_lost,
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
        self.scan_bt_button = MDRaisedButton(text=self.tr.get('scan_bt_button', 'Scan for Devices'), size_hint_x=1, height=dp(44), size_hint_y=None)
        self.scan_bt_button.bind(on_press=self.scan_for_bt_devices)
        # Add to the conversations list area for now
        self.root.ids.chat_layout.ids.conversations_list.add_widget(self.scan_bt_button)

    def scan_for_bt_devices(self, instance):
        self.add_message_to_box(self.tr.get('bt_scanning'), 'global')
        # Run discovery in a separate thread to not block the UI
        threading.Thread(target=self.bluetooth_manager.discover_devices, daemon=True).start()



    def toggle_theme(self, instance=None):
        """Переключение между светлой и тёмной темой"""
        try:
            current_theme = self.theme_cls.theme_style
            if current_theme == "Dark":
                self.theme_cls.theme_style = "Light"
                self.theme_cls.primary_palette = "Purple"
                self.theme_cls.primary_hue = "200"
            else:
                self.theme_cls.theme_style = "Dark"
                self.theme_cls.primary_palette = "Purple"
                self.theme_cls.primary_hue = "500"

            # Перезагружаем интерфейс для применения темы
            if hasattr(self, 'root') and self.root:
                self.root.canvas.ask_update()
            print(f"Тема изменена на {self.theme_cls.theme_style}")
        except Exception as e:
            print(f"Ошибка при переключении темы: {e}")

    def send_message(self, instance=None):
        try:
            input_area = self.root.ids.input_area
            text = input_area.ids.message_input.text.strip()
            if not text:
                return
        except (KeyError, AttributeError):
            print("Warning: Could not access input area for sending message")
            return
        message_data = {'id': str(uuid.uuid4()), 'sender': self.username, 'text': text, 'timestamp': datetime.now().isoformat(), 'status': 'sent'}
        if self.mode.startswith('p2p') and self.p2p_manager:
            # Determine if the active chat is a group
            is_group = self.active_chat in self.p2p_manager.groups

            if self.active_chat == 'global':
                # Broadcast to all established contacts in 'global' chat
                if not self.contacts:
                    self.show_popup(self.tr.get('cannot_send_title', "Cannot Send"), self.tr.get('must_add_contact_message', "You must add a user as a contact before sending messages."))
                    return
                # We can't broadcast to global, so we will send to all contacts instead
                for contact_user in self.contacts:
                    self.p2p_manager.send_private_message(contact_user, message_data)
                self.add_message_to_box(message_data, 'global') # Show in our own global chat

            elif is_group:
                # Send a message to a specific group
                self.p2p_manager.send_group_message(self.active_chat, message_data)
                self.add_message_to_box(message_data, self.active_chat)

            else:
                # It's a private message to a specific user (self.active_chat holds the username)
                self.p2p_manager.send_private_message(self.active_chat, message_data)
                self.add_message_to_box(message_data, self.active_chat)
        elif self.mode == 'server' and self.server_manager:
            if self.active_chat != 'global':
                self.server_manager.send_group_message(self.active_chat, message_data)
                self.add_message_to_box(message_data, self.active_chat)
            else:
                self.add_message_to_box(self.tr.get('no_global_server_message', "Cannot send global messages in server mode yet."), 'global')
        elif self.mode == 'p2p_bluetooth' and self.bluetooth_manager:
            full_message = f"{self.username}: {text}"
            if self.bluetooth_manager.send_message(full_message):
                self.add_message_to_box(full_message, 'global')
            else:
                self.add_message_to_box(self.tr.get('bt_not_connected'), 'global')

        # Clear input and refocus
        input_area.ids.message_input.text = ""
        Clock.schedule_once(lambda dt: setattr(input_area.ids.message_input, 'focus', True))

    # --- Audio Message Logic ---
    def toggle_audio_message_record(self, instance):
        self.is_recording_audio_message = not self.is_recording_audio_message
        chat_ids = self.root.ids.chat_layout.ids
        
        if self.is_recording_audio_message:
            chat_ids.record_button.icon = "stop"
            config = self.config_manager.load_config()
            device_name = config.get('input_device_name', 'Default')
            input_devices, _ = self.audio_manager.get_devices()
            device_index = input_devices.get(device_name, sd.default.device[0])
            
            # Create a unique filename
            self.audio_message_path = os.path.join("audio_messages", f"{uuid.uuid4()}.wav")
            os.makedirs("audio_messages", exist_ok=True)

            if self.audio_manager.start_recording(self.audio_message_path, device_index):
                self.add_message_to_box("System: Recording audio message...", self.active_chat)
            else:
                self.add_message_to_box("System: Failed to start recording.", self.active_chat)
                self.is_recording_audio_message = False
                chat_ids.record_button.text = "🎤" # Reset button
        else:
            chat_ids.record_button.icon = "microphone"
            self.audio_manager.stop_recording()
            self.add_message_to_box(f"System: Recording saved. Ready to send.", self.active_chat)
            
            # Create the audio widget and add it to the chat
            widget = AudioMessageWidget(self.audio_message_path, self.username, self.tr)
            self.root.ids.chat_layout.ids.chat_box.add_widget(widget)
            
            # Send the recorded audio file to the other users in the chat.
            ft_plugin = self.plugin_manager.get_plugin_by_id('file_transfer')
            if ft_plugin and ft_plugin['instance']:
                recipients = []
                if self.mode.startswith('p2p') and self.p2p_manager and self.active_chat in self.p2p_manager.groups:
                    recipients = self.p2p_manager.groups[self.active_chat].get('members', [])
                elif self.mode == 'server' and self.server_manager and self.active_chat in self.server_groups:
                    recipients = self.server_groups[self.active_chat].get('members', [])

                for user in recipients:
                    if user != self.username:
                        print(f"Sending audio message to {user}")
                        ft_plugin['instance'].send_filepath(self.audio_message_path, user)
            
            # The local audio widget serves as confirmation for the sender.
            # The receiver will get a standard file transfer request.
            message_data = {'id': str(uuid.uuid4()), 'sender': self.username, 'audio_path': self.audio_message_path, 'timestamp': datetime.now().isoformat()}
            self.chat_history.setdefault(self.active_chat, []).append(message_data)


    # --- Call Logic ---
    def initiate_call(self, target_username):
        if self.webrtc_manager.peer_connections:
            self.add_message_to_box("Error: Already in a call.", 'global')
            return

        if self.mode.startswith('p2p') and target_username not in self.contacts:
            self.request_contact(target_username)
            return

        self.add_message_to_box(f"Calling {target_username}...", 'global')
        self.webrtc_manager.start_call(target_username)

    def hang_up_call(self, peer_username=None):
        # Guard against recursive calls from on_dismiss event
        if getattr(self, '_is_hanging_up', False):
            return
        self._is_hanging_up = True

        try:
            if not peer_username:
                # If no specific peer, hang up all connections
                for peer in list(self.webrtc_manager.peer_connections.keys()):
                    self.webrtc_manager.end_call(peer)
                    if self.p2p_manager: self.p2p_manager.send_webrtc_signal(peer, 'hangup', {})
            else:
                self.webrtc_manager.end_call(peer_username)
                if self.p2p_manager: self.p2p_manager.send_webrtc_signal(peer_username, 'hangup', {})

            if self.call_popup:
                # We must dismiss before setting to None, so the guard is necessary
                self.call_popup.dismiss()
                self.call_popup = None
            self.add_message_to_box("Call ended.", 'global')
        finally:
            self._is_hanging_up = False

    @mainthread
    def on_webrtc_signal(self, sender, signal_type, data):
        if signal_type == 'offer':
            self.show_incoming_call_popup(sender, data)
        elif signal_type == 'answer':
            self.add_message_to_box(f"Call with {sender} accepted and connected.", 'global')
            self.webrtc_manager.handle_answer(sender, data)
            self.show_call_popup(sender) # Show call UI for initiator only after answer
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

        accept_btn = MDRaisedButton(text=self.tr.get('accept_button'))
        decline_btn = MDFlatButton(text=self.tr.get('decline_button'))
        
        popup = MDDialog(
            title=self.tr.get('incoming_call_title'),
            text=self.tr.get('incoming_call_from', peer=peer_username),
            buttons=[accept_btn, decline_btn],
            auto_dismiss=False
        )

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
            self.webrtc_manager.set_mute(is_muted)
            self.add_message_to_box(f"Mute is now {'ON' if is_muted else 'OFF'}", 'global')

        self.call_popup.bind(on_dismiss=on_hang_up)
        self.call_popup.bind(on_mute_toggle=on_mute)
        self.call_popup.open()
    # --- UI Update Callbacks ---
    @mainthread
    def add_message_to_box(self, message_data, chat_id=None):
        if chat_id is None:
            chat_id = 'global'

        # Ensure message_data is stored, even if it's a simple string
        if isinstance(message_data, str):
              # Convert system messages to the standard dict format for consistency
              message_data = {'id': str(uuid.uuid4()), 'sender': 'System', 'text': message_data, 'timestamp': datetime.now().isoformat()}

        self.chat_history.setdefault(chat_id, []).append(message_data)

        if self.active_chat != chat_id:
            # Future: show a notification badge on the conversation item
            return

        try:
            if not self.root or not hasattr(self.root, 'ids'):
                print("Warning: UI not ready, cannot add message")
                return
            messages_container = self.root.ids.messages_container
        except (KeyError, AttributeError):
            print("Warning: messages_container not found, cannot add message")
            return

        sender = message_data.get('sender', 'System')
        text = message_data.get('text', '')

        # Determine message type and create appropriate bubble
        is_self = sender == self.username

        if sender == 'System':
            # System message - create a simple centered message
            message_bubble = MDBoxLayout(
                size_hint_y=None,
                height=dp(30),
                padding=dp(10),
                md_bg_color=rgba('#2d1b69')
            )
            label = MDLabel(
                text=text,
                font_style='Caption',
                theme_text_color='Custom',
                text_color=(0.7, 0.7, 0.7, 1),
                halign='center'
            )
            message_bubble.add_widget(label)

        elif 'audio_path' in message_data:
            # Voice message - use VoiceMessageBubble template
            message_bubble = VoiceMessageBubble()
            message_bubble.id = message_data.get('id', '')
            message_bubble.is_own = is_self
            message_bubble.voice_duration.text = "0:30"  # TODO: Calculate from audio file
            message_bubble.voice_time.text = datetime.now().strftime('%H:%M')

            # Set read status
            if hasattr(message_bubble, 'voice_status'):
                status = message_data.get('status', 'sent')
                if status == 'read':
                    message_bubble.voice_status.icon = 'check-all'
                elif status == 'delivered':
                    message_bubble.voice_status.icon = 'check'
                else:
                    message_bubble.voice_status.icon = 'clock'

        else:
            # Regular text message - use MessageBubble template
            message_bubble = MessageBubble()
            message_bubble.id = message_data.get('id', '')
            message_bubble.is_own = is_self
            message_bubble.message_text.text = text
            message_bubble.message_time.text = datetime.now().strftime('%H:%M')

            # Set read status
            if hasattr(message_bubble, 'message_status'):
                status = message_data.get('status', 'sent')
                if status == 'read':
                    message_bubble.message_status.icon = 'check-all'
                elif status == 'delivered':
                    message_bubble.message_status.icon = 'check'
                else:
                    message_bubble.message_status.icon = 'clock'

                # Hide status for received messages
                if not is_self:
                    message_bubble.message_status.opacity = 0

        # Add message bubble to container
        messages_container.add_widget(message_bubble)

        # Auto-scroll to bottom
        if hasattr(messages_container, 'parent') and hasattr(messages_container.parent, 'scroll_to'):
            messages_container.parent.scroll_to(message_bubble)

    @mainthread
    def p2p_message_received(self, message_data):
        if message_data.get('sender') != self.username:
            self.add_message_to_box(message_data, 'global')

    @mainthread
    def on_peer_discovered(self, username, address_info):
        """Callback for when a new P2P peer is discovered on the network."""
        if username == self.username:
            return

        # Avoid adding duplicates
        chat_list = self.root.ids.chat_list
        for child in chat_list.children:
            if hasattr(child, 'user_id') and child.user_id == username:
                return

        # Create a chat list item using the new template
        chat_item = ChatListItem()
        chat_item.user_id = username
        chat_item.chat_name.text = username
        chat_item.chat_preview.text = "Available"
        chat_item.chat_time.text = datetime.now().strftime('%H:%M')
        chat_item.bind(on_release=lambda x, u=username: self.switch_chat(u))

        # Add to chat list
        chat_list.add_widget(chat_item)

    @mainthread
    def on_user_list_update(self, users):
        conversations_list = self.root.ids.chat_layout.ids.conversations_list
        
        # Simple redraw: clear and add all non-group users
        existing_users = {child.user_id for child in conversations_list.children if hasattr(child, 'user_id')}
        
        users_to_add = set(users) - existing_users - {self.username}
        users_to_remove = existing_users - set(users)

        for widget in conversations_list.children[:]:
            if hasattr(widget, 'user_id') and widget.user_id in users_to_remove:
                conversations_list.remove_widget(widget)

        for username in users_to_add:
            # This will be replaced with a proper ConversationItem widget
            user_button = MDRaisedButton(text=username, size_hint_y=None, height=dp(50))
            user_button.user_id = username # custom property to identify it later
            user_button.bind(on_press=lambda x, u=username: self.switch_chat(u))
            conversations_list.add_widget(user_button)

    @mainthread
    def on_peer_lost(self, username):
        """Callback for when a P2P peer goes offline."""
        conversations_list = self.root.ids.chat_layout.ids.conversations_list
        widget_to_remove = None
        for child in conversations_list.children:
            if hasattr(child, 'user_id') and child.user_id == username:
                widget_to_remove = child
                break
        if widget_to_remove:
            conversations_list.remove_widget(widget_to_remove)
            self.add_message_to_box(f"System: '{username}' went offline.", 'global')

    @mainthread
    def on_secure_channel_established(self, username):
        self.add_message_to_box(f"System: Secure connection established with {username}.", 'global')
        conversations_list = self.root.ids.chat_layout.ids.conversations_list
        for child in conversations_list.children:
            if hasattr(child, 'user_id') and child.user_id == username:
                # This will be replaced by a lock icon on the ConversationItem
                child.text = f"{username} (Secure)"
                break

    @mainthread
    def on_peer_found(self, username):
        self.add_message_to_box(f"System: Found user '{username}'. They have been added to your user list.", 'global')
        # The peer_discovered callback will handle adding the button

    @mainthread
    def on_peer_not_found(self, username):
        self.show_popup(self.tr.get('search_failed_title', "Search Failed"), self.tr.get('user_not_found_message', "User '{username}' could not be found on the network.", username=username))

    def request_contact(self, target_username):
        # The password is now handled by the receiver. The sender just sends a plain request.
        self.p2p_manager.send_contact_request(target_username)
        self.add_message_to_box(f"System: Contact request sent to '{target_username}'.", 'global')

    @mainthread
    def on_incoming_contact_request(self, sender_username, payload):
        config = self.config_manager.load_config()
        my_password = config.get('security', {}).get('p2p_password', '')

        if not my_password:
            # No password is set on our end, so show the simple accept/decline popup.
            popup = ContactRequestPopup(sender_username, self.tr)
            def handle_response(instance, accepted):
                self.p2p_manager.send_contact_response(sender_username, accepted)
                if accepted:
                    self.contacts.add(sender_username)
                    self.add_message_to_box(f"System: You are now contacts with {sender_username}.", 'global')
            popup.bind(on_response=handle_response)
            popup.open()
        else:
            # A password is required. Show the password prompt.
            popup = PasswordPromptPopup(sender_username, self.tr)
            def handle_password_submit(instance, entered_password):
                if entered_password is None: # User cancelled
                    self.p2p_manager.send_contact_response(sender_username, False)
                    return

                my_hash = self.p2p_manager.encryption_manager.hash_password(my_password)
                entered_hash = self.p2p_manager.encryption_manager.hash_password(entered_password)

                if my_hash == entered_hash:
                    self.p2p_manager.send_contact_response(sender_username, True)
                    self.contacts.add(sender_username)
                    self.add_message_to_box(f"System: You are now contacts with {sender_username}.", 'global')
                else:
                    self.show_popup("Password Incorrect", "The entered password was incorrect.")
                    self.p2p_manager.send_contact_response(sender_username, False)

            popup.bind(on_submit=handle_password_submit)
            popup.open()

    @mainthread
    def on_contact_request_response(self, sender_username, accepted):
        if accepted:
            self.contacts.add(sender_username)
            self.show_popup(self.tr.get('contact_added_title', "Contact Added"), self.tr.get('contact_request_accepted_message', "'{sender_username}' accepted your contact request.", sender_username=sender_username))
        else:
            self.show_popup(self.tr.get('request_declined_title', "Request Declined"), self.tr.get('contact_request_declined_message', "'{sender_username}' declined your contact request.", sender_username=sender_username))

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
        self.group_name_input = MDTextField(hint_text=self.tr.get('enter_group_name_label', "Enter group name:"))
        
        ok_button = MDRaisedButton(text=self.tr.get('create_button', "Create"))
        cancel_button = MDFlatButton(text=self.tr.get('cancel_button', "Cancel"))

        popup = MDDialog(
            title=self.tr.get('create_group_title', "Create Group"),
            type="custom",
            content_cls=self.group_name_input,
            buttons=[ok_button, cancel_button]
        )
        
        ok_button.bind(on_press=lambda x: self.create_group(popup))
        cancel_button.bind(on_press=popup.dismiss)
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
        conversations_list = self.root.ids.chat_layout.ids.conversations_list
        # This will be replaced with a proper ConversationItem widget
        group_button = MDRaisedButton(text=f"[G] {group_name}", size_hint_y=None, height=dp(50))
        group_button.group_id = group_id # custom property
        group_button.bind(on_press=lambda x: self.switch_chat(group_id))
        conversations_list.add_widget(group_button)

    def switch_chat(self, chat_id):
        # Safety check for UI readiness
        if not self.root or not hasattr(self.root, 'ids'):
            print("Warning: UI not ready for switch_chat")
            return

        self.active_chat = chat_id
        try:
            chat_layout = self.root.ids.chat_layout
            chat_box = chat_layout.ids.chat_box
            chat_header_label = chat_layout.ids.chat_title

            chat_box.clear_widgets()
            history = self.chat_history.get(chat_id, [])
            for message_data in history:
                  # Manually pass the chat_id to add_message_to_box to ensure it renders
                  # even though the active_chat is already set. This is because the check
                  # happens before the widget is added.
                self.add_message_to_box(message_data, self.active_chat)
        except (KeyError, AttributeError):
            print(f"Warning: Could not access chat layout for chat_id: {chat_id}")


        # --- Configure Context Buttons in Chat Header ---
        chat_header_buttons = chat_layout.ids.chat_header_buttons
        chat_header_buttons.clear_widgets()

        # --- Handle different chat contexts ---
        if chat_id == 'global':
            chat_header_label.text = self.tr.get('global_chat_title', "Global Chat")
            return

        is_group = False
        group_info = {}

        if self.mode.startswith('p2p') and self.p2p_manager and chat_id in self.p2p_manager.groups:
            group_info = self.p2p_manager.groups.get(chat_id, {})
            is_group = True
        elif self.mode == 'server' and chat_id in self.server_groups:
            group_info = self.server_groups.get(chat_id, {})
            is_group = True

        if is_group:
            group_name = group_info.get('name', 'Group')
            chat_header_label.text = group_name
            # Group call button removed - now in menu for cleaner interface
            pass

        else: # It's a user chat
            chat_header_label.text = chat_id

            call_button = MDIconButton(icon='phone')
            call_button.bind(on_press=lambda instance: self.initiate_call(chat_id))
            chat_header_buttons.add_widget(call_button)

    def show_group_call_popup(self):
        group_name = self.p2p_manager.groups.get(self.active_group_call, {}).get('name', '')
        self.group_call_popup = GroupCallPopup(group_name, self.tr)
        self.group_call_popup.bind(on_dismiss=lambda x: self.hang_up_call())
        self.group_call_popup.open()
        # Initial population of the participants list
        self.update_group_members_ui(self.active_group_call)

    def update_group_members_ui(self, group_id):
        """Refreshes the displayed list of members for a group call."""
        if not self.group_call_popup or group_id != self.active_group_call:
            return

        if self.mode.startswith('p2p'):
            members = self.p2p_manager.groups.get(group_id, {}).get('members', [])
        elif self.mode == 'server':
            members = self.server_groups.get(group_id, {}).get('members', [])
        else:
            members = []

        # Clear existing member widgets
        self.group_call_popup.participants_list.clear_widgets()
        
        # Add a label for each member
        for member in members:
            self.group_call_popup.participants_list.add_widget(MDLabel(text=member, halign="center"))

    @mainthread
    def on_group_joined(self, group_id, username):
        if group_id == self.active_chat:
            self.add_message_to_box(f"System: '{username}' has joined the group.", group_id)

    @mainthread
    def on_incoming_group_invite(self, group_id, group_name, admin_username):
        box = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        yes_btn = MDRaisedButton(text=self.tr.get('accept_button', 'Accept'))
        no_btn = MDFlatButton(text=self.tr.get('decline_button', 'Decline'))

        popup = MDDialog(
            title=self.tr.get('group_invitation_title', "Group Invitation"),
            text=self.tr.get('group_invite_message', "You are invited to join the group '{group_name}' by {admin_username}.", group_name=group_name, admin_username=admin_username),
            buttons=[yes_btn, no_btn],
            auto_dismiss=False
        )

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
                self.add_message_to_box(self.tr.get('no_users_to_invite_message', "System: No users online to invite."), self.active_chat)
                return
            current_members = self.p2p_manager.groups.get(self.active_chat, {}).get('members', set())
            available_users = [u for u in self.p2p_manager.peers.keys() if u not in current_members]
        elif self.mode == 'server':
            if not self.server_manager: return
            # Assuming server_manager holds the user list
            all_users = [c.text for c in self.root.ids.chat_layout.ids.conversations_list.children if hasattr(c, 'user_id')] # Fetch from conversations list
            current_members = self.server_groups.get(self.active_chat, {}).get('members', [])
            available_users = [u for u in all_users if u not in current_members]
        else:
            return

        if not available_users:
            self.add_message_to_box(self.tr.get('all_users_in_group_message', "System: All available users are already in the group."), self.active_chat)
            return

        box = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(MDLabel(text=self.tr.get('select_user_to_invite_label', "Select a user to invite:")))
        popup = MDDialog(title=self.tr.get('invite_user_title', "Invite User"), type="custom", content_cls=box)
        for username in available_users:
            btn = MDRaisedButton(text=username)
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
        popup.bind(on_invite_user=lambda x: self.show_invite_user_popup(None))
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

        # Get supported sample rate from config, default to 48000 if not found
        supported_rate = config.get('audio_sample_rate', 48000)

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

        box = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        group_name = self.p2p_manager.groups.get(group_id, {}).get('name', '') if self.mode.startswith('p2p') else self.server_groups.get(group_id, {}).get('name', '')
        box.add_widget(MDLabel(text=f"Incoming group call from '{admin_username}' for group '{group_name}'."))
        
        yes_btn = MDRaisedButton(text='Join')
        no_btn = MDFlatButton(text='Decline')

        popup = MDDialog(
            title="Incoming Group Call",
            type="custom",
            content_cls=box,
            buttons=[yes_btn, no_btn],
            auto_dismiss=False
        )

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
            self.update_group_members_ui(group_id)


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
            self.update_group_members_ui(group_id)

    @mainthread
    def on_user_left_call(self, group_id, username):
        if group_id == self.active_group_call:
            self.add_message_to_box(f"System: {username} left the call.", group_id)
            self.update_group_members_ui(group_id)

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
            self.show_popup(self.tr.get('kicked_from_group_title', "Kicked from Group"), self.tr.get('you_were_kicked_message', "You have been kicked from the group '{group_name}' by {admin_username}.", group_name=self.p2p_manager.groups.get(group_id, {}).get('name'), admin_username=admin_username))
            
            if self.active_chat == group_id:
                self.switch_chat('global') # Switch to global chat
            
            # Remove the group from the UI list
            button_to_remove = None
            conversations_list = self.root.ids.chat_layout.ids.conversations_list
            group_name_to_find = self.p2p_manager.groups.get(group_id, {}).get('name')
            
            for button in conversations_list.children:
                if hasattr(button, 'group_id') and button.group_id == group_id:
                    button_to_remove = button
                    break
            if button_to_remove:
                conversations_list.remove_widget(button_to_remove)

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

            self.show_popup(self.tr.get('kicked_from_group_title', "Kicked from Group"), self.tr.get('you_were_kicked_message', "You have been kicked from the group '{group_name}' by {admin_username}.", group_name=group_name, admin_username=admin_username))

            if self.active_chat == group_id:
                self.switch_chat('global')

            button_to_remove = None
            conversations_list = self.root.ids.chat_layout.ids.conversations_list
            for button in conversations_list.children:
                if hasattr(button, 'group_id') and button.group_id == group_id:
                    button_to_remove = button
                    break
            if button_to_remove:
                conversations_list.remove_widget(button_to_remove)

            if group_id in self.chat_history:
                del self.chat_history[group_id]

        else:
            # Another user was kicked
            message = f"System: {kicked_username} was kicked by {admin_username}."
            self.add_message_to_box(message, group_id)
            self.update_group_members_ui(group_id)

    def create_emoji_panel(self):
        # The emoji panel is already defined in the .kv file
        # Just need to populate it with emoji buttons
        try:
            emoji_panel = self.root.ids.emoji_panel
        except KeyError:
            print("Warning: emoji_panel not found in .kv file, skipping emoji panel creation")
            return
        except AttributeError:
            print("Warning: root or ids not available, skipping emoji panel creation")
            return

        if not hasattr(emoji_panel, 'categories_loaded'):
            # Get the categories and create emoji grids
            categorized_emojis = self.emoji_manager.get_categorized_emojis()

            for category, emojis in categorized_emojis.items():
                # Create category tab content
                tab_content = MDBoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))

                # Search bar for the category
                search_field = MDTextField(
                    hint_text='Search emojis...',
                    mode='rectangle',
                    size_hint_y=None,
                    height=dp(40)
                )
                search_field.bind(text=self.on_emoji_search)
                tab_content.add_widget(search_field)

                # Emoji grid
                grid = EmojiGrid()
                tab_content.add_widget(grid)

                # Populate with emoji buttons
                for emoji in emojis[:50]:  # Limit to first 50 for performance
                    emoji_btn = EmojiButton()
                    emoji_btn.emoji_char.text = emoji
                    emoji_btn.bind(on_release=lambda btn, e=emoji: self.on_emoji_selected(e))
                    grid.add_widget(emoji_btn)

                # Store in the panel for switching
                setattr(emoji_panel, f'category_{category.lower().replace(" ", "_")}', tab_content)

            emoji_panel.categories_loaded = True

    def on_emoji_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        """Loads the content of an emoji tab only when it's selected."""
        if not hasattr(instance_tab, 'loaded') or instance_tab.loaded:
            return

        grid = instance_tab.grid
        emojis = instance_tab.emojis
        
        def update_cols(grid_layout, scroll_view_instance, width):
            if width <= 0: return
            new_cols = max(1, int(width / dp(45)))
            grid_layout.cols = new_cols

        scroll_view = grid.parent
        scroll_view.bind(width=partial(update_cols, grid))

        for emoji in emojis:
            btn = MDIconButton(
                icon=emoji,
                font_name='EmojiFont',
                font_size='24sp',
                size_hint=(None, None),
                size=(dp(40), dp(40)),
            )
            btn.emoji_char = emoji
            btn.bind(on_press=self.add_emoji_to_input)
            grid.add_widget(btn)
        
        instance_tab.loaded = True

    def toggle_emoji_panel(self, instance):
        try:
            emoji_panel = self.root.ids.emoji_panel
        except KeyError:
            print("Warning: emoji_panel not found, emoji functionality disabled")
            return

        if emoji_panel.opacity > 0:
            # Hide emoji panel
            emoji_panel.opacity = 0
            emoji_panel.disabled = True
        else:
            # Show emoji panel with animation
            emoji_panel.disabled = False
            Animation(opacity=1, duration=0.2).start(emoji_panel)

    def add_emoji_to_input(self, instance):
        input_area = self.root.ids.input_area
        input_area.ids.message_input.text += instance.emoji_char
        input_area.ids.message_input.focus = True

    def on_emoji_selected(self, emoji):
        """Called when an emoji is selected from the panel"""
        input_area = self.root.ids.input_area
        input_area.ids.message_input.text += emoji
        input_area.ids.message_input.focus = True

    def on_emoji_search(self, instance, value):
        """Filter emojis based on search text"""
        # Implementation for emoji search functionality
        # This would filter the emoji grid based on the search text
        pass

    def show_popup(self, title, message):
        try:
            ok_button = MDRaisedButton(text="OK")
            popup = MDDialog(
                title=title,
                text=message,
                buttons=[ok_button]
            )
            ok_button.bind(on_press=popup.dismiss)
            popup.open()
        except Exception as e:
            print(f"Error showing popup: {e}")
            print(f"Popup title: {title}")
            print(f"Popup message: {message}")

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

    def _menu_callback_wrapper(self, callback, instance=None):
        """Wrapper for menu callbacks to dismiss the menu after selection."""
        if instance is not None:
            callback(instance)
        else:
            callback()
        if hasattr(self, 'main_menu'):
            self.main_menu.dismiss()

    def open_main_menu(self, instance):
        """Opens a dropdown menu with main actions."""
        menu_items = [
            {
                "text": self.tr.get('create_group_title', 'Create Group'),
                "viewclass": "OneLineListItem",
                "on_release": lambda *x: self._menu_callback_wrapper(self.show_create_group_popup)
            },
            {
                "text": self.tr.get('settings_title', 'Settings'),
                "viewclass": "OneLineListItem",
                "on_release": lambda *x: self._menu_callback_wrapper(self.show_settings_popup)
            },
            {
                "text": self.tr.get('toggle_theme_button', 'Toggle Theme'),
                "viewclass": "OneLineListItem",
                "on_release": lambda *x: self._menu_callback_wrapper(self.toggle_theme)
            }
        ]

        # Add group call option only when in a group chat
        if self.active_chat != 'global':
            is_group = False
            if self.mode.startswith('p2p') and self.p2p_manager and self.active_chat in self.p2p_manager.groups:
                is_group = True
            elif self.mode == 'server' and self.active_chat in self.server_groups:
                is_group = True

            if is_group:
                menu_items.insert(1, {
                    "text": self.tr.get('start_group_call_button', 'Start Group Call'),
                    "viewclass": "OneLineListItem",
                    "on_release": lambda *x: self._menu_callback_wrapper(self.start_group_call)
                })

        if not hasattr(self, 'main_menu'):
            self.main_menu = MDDropdownMenu(
                caller=instance,
                items=menu_items,
                width_mult=4
            )
        else:
            self.main_menu.caller = instance
            self.main_menu.items = menu_items

        self.main_menu.open()

    def show_settings_popup(self, instance=None):
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

        # Only apply changes if the user clicked "Save"
        if not getattr(popup, 'saved', False):
            return

        # The popup has already modified this config object in memory.
        # We just need to apply the changes and then save it.
        config = popup.config
        
        # Handle hotkey changes
        new_hotkey = getattr(popup, 'hotkey', None)
        if new_hotkey:
            self.hotkey_manager.set_hotkey(new_hotkey)
            if 'hotkeys' not in config:
                config['hotkeys'] = {}
            hotkey_str = ' + '.join(SettingsPopup.key_to_str(k) for k in new_hotkey)
            config['hotkeys']['mute'] = hotkey_str
            self.add_message_to_box(self.tr.get('system_hotkey_set', hotkey=hotkey_str), 'global')

        # Apply audio settings from the now-updated config
        self.add_message_to_box(self.tr.get('system_audio_settings_saved', 'Audio settings saved.'), 'global')
        self.apply_audio_settings(config)
       
        # Apply language change if it happened
        new_lang = config.get('language', 'en')
        if self.tr.get_language() != new_lang:
            self.tr.set_language(new_lang)
            # We might need to recreate the UI to apply language changes,
            # which is complex. For now, we'll just show a message.
            # A full implementation would require a restart or dynamic UI recreation.
            self.show_popup(self.tr.get('language_changed_title', "Language Changed"), self.tr.get('language_change_restart_message', "The language will fully update on next restart."))
            Window.title = self.tr.get('window_title') # Update title immediately

        self.config_manager.save_config(config)

    @mainthread
    def toggle_mute_hotkey(self):
        self.is_muted = not self.is_muted
        
        # Mute/unmute WebRTC call
        self.webrtc_manager.set_mute(self.is_muted)
        
        # Update UI
        if self.call_popup:
            self.call_popup.is_muted = self.is_muted
            self.call_popup.mute_button.text = self.tr.get('unmute_button') if self.is_muted else self.tr.get('mute_button')
        
        if self.is_muted:
            self.add_message_to_box(self.tr.get('system_audio_muted'), 'global')
        else:
            self.add_message_to_box(self.tr.get('system_audio_unmuted'), 'global')


    def apply_audio_settings(self, config):
        # Applies audio settings from the config to the AudioManager
        input_volume = config.get('input_volume', 80)
        output_volume = config.get('output_volume', 80)

        # Convert slider value [0, 100] to a gain multiplier [0.0, 1.0]
        # Ensure we handle potential None values gracefully, defaulting to 80.
        input_gain = (input_volume or 80) / 100.0
        output_gain = (output_volume or 80) / 100.0
        
        self.audio_manager.set_volume(input_gain, 'input')
        self.audio_manager.set_volume(output_gain, 'output')

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

    # New methods for the Telegram-style interface

    def toggle_left_menu(self):
        """Toggle the left navigation menu"""
        if not self.root or not hasattr(self.root, 'ids'):
            print("Warning: UI not ready for toggle_left_menu")
            return

        try:
            left_menu = self.root.ids.left_menu_overlay
            if left_menu.opacity > 0:
                Animation(opacity=0, duration=0.2, x=left_menu.x - dp(20)).start(left_menu)
                left_menu.disabled = True
            else:
                left_menu.disabled = False
                left_menu.x = -dp(300)  # Start off-screen
                Animation(opacity=1, duration=0.2, x=0).start(left_menu)
        except (KeyError, AttributeError):
            print("Warning: Could not access left menu overlay")

    def open_search(self):
        """Open global search functionality"""
        if not hasattr(self, 'search_popup'):
            content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None, height="200dp")

            self.search_input = MDTextField(
                hint_text="Search messages, users, groups...",
                mode='rectangle',
                size_hint_y=None,
                height=dp(50)
            )
            content_layout.add_widget(self.search_input)

            search_btn = MDRaisedButton(text="Search", size_hint_y=None, height=dp(40))
            search_btn.bind(on_press=self.perform_search)
            content_layout.add_widget(search_btn)

            self.search_popup = MDDialog(
                title="Global Search",
                type="custom",
                content_cls=content_layout,
                auto_dismiss=True,
                size_hint=(0.8, 0.6)
            )

        self.search_popup.open()

    def create_new_chat(self):
        """Create a new chat"""
        if not hasattr(self, 'new_chat_popup'):
            content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None, height="250dp")

            self.new_chat_input = MDTextField(
                hint_text="Enter username or group name",
                mode='rectangle',
                size_hint_y=None,
                height=dp(50)
            )
            content_layout.add_widget(self.new_chat_input)

            # Chat type selection
            self.chat_type = 'private'
            type_layout = MDBoxLayout(spacing="10dp", size_hint_y=None, height=dp(40))

            private_btn = MDRaisedButton(text="Private Chat", size_hint_x=0.5)
            group_btn = MDRaisedButton(text="Group Chat", size_hint_x=0.5)

            def select_private(instance):
                self.chat_type = 'private'
                private_btn.md_bg_color = rgba('#7C4DFF')
                group_btn.md_bg_color = rgba('#4a148c')

            def select_group(instance):
                self.chat_type = 'group'
                group_btn.md_bg_color = rgba('#7C4DFF')
                private_btn.md_bg_color = rgba('#4a148c')

            private_btn.bind(on_press=select_private)
            group_btn.bind(on_press=select_group)
            type_layout.add_widget(private_btn)
            type_layout.add_widget(group_btn)
            content_layout.add_widget(type_layout)

            create_btn = MDRaisedButton(text="Create", size_hint_y=None, height=dp(40))
            create_btn.bind(on_press=self.start_new_chat)
            content_layout.add_widget(create_btn)

            self.new_chat_popup = MDDialog(
                title="New Chat",
                type="custom",
                content_cls=content_layout,
                auto_dismiss=True,
                size_hint=(0.8, 0.7)
            )

        # Set default selection
        self.new_chat_popup.open()

    def search_in_chat(self):
        """Search within current chat"""
        if self.active_chat == 'global':
            self.show_popup("Error", "Cannot search in global chat")
            return

        if not hasattr(self, 'chat_search_popup'):
            content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None, height="200dp")

            self.chat_search_input = MDTextField(
                hint_text="Search in this chat...",
                mode='rectangle',
                size_hint_y=None,
                height=dp(50)
            )
            content_layout.add_widget(self.chat_search_input)

            search_btn = MDRaisedButton(text="Find", size_hint_y=None, height=dp(40))
            search_btn.bind(on_press=self.find_in_chat)
            content_layout.add_widget(search_btn)

            self.chat_search_popup = MDDialog(
                title=f"Search in {self.active_chat}",
                type="custom",
                content_cls=content_layout,
                auto_dismiss=True
            )

        self.chat_search_popup.open()

    def perform_search(self, instance):
        """Perform global search"""
        query = self.chat_search_input.text.strip() if hasattr(self, 'chat_search_input') else ""
        if not query:
            return

        # Search in chat history
        found_messages = []
        for chat_id, messages in self.chat_history.items():
            if chat_id != 'global':
                for msg in messages:
                    if 'text' in msg and query.lower() in msg['text'].lower():
                        found_messages.append((chat_id, msg))

        if found_messages:
            content = f"Found {len(found_messages)} matches for '{query}':\n\n"
            for chat_id, msg in found_messages[:10]:  # Limit to 10 results
                content += f"[{chat_id}] {msg.get('sender', 'Unknown')}: {msg['text'][:50]}...\n"
            if len(found_messages) > 10:
                content += f"\n... and {len(found_messages) - 10} more"
            self.show_popup("Search Results", content)
        else:
            self.show_popup("Search Results", f"No matches found for '{query}'")

    def find_in_chat(self, instance):
        """Find text in current chat"""
        query = self.chat_search_input.text.strip() if hasattr(self, 'chat_search_input') else ""
        if not query:
            return

        if self.active_chat not in self.chat_history:
            self.show_popup("Error", "No messages in this chat")
            return

        found_messages = []
        for msg in self.chat_history[self.active_chat]:
            if 'text' in msg and query.lower() in msg['text'].lower():
                found_messages.append(msg)

        if found_messages:
            content = f"Found {len(found_messages)} matches in {self.active_chat}:\n\n"
            for msg in found_messages[:10]:
                content += f"{msg.get('sender', 'Unknown')}: {msg['text'][:100]}...\n"
            self.show_popup("Search Results", content)
        else:
            self.show_popup("Search Results", f"No matches found for '{query}' in this chat")

    def start_new_chat(self, instance):
        """Start a new chat based on user input"""
        target = self.new_chat_input.text.strip() if hasattr(self, 'new_chat_input') else ""
        if not target:
            return

        if self.chat_type == 'private':
            # Start private chat
            if self.mode.startswith('p2p') and self.p2p_manager:
                self.p2p_manager.find_peer(target)
                self.add_message_to_box(f"System: Searching for user '{target}'...", 'global')
            else:
                self.add_message_to_box(f"System: Private chats not available in {self.mode} mode", 'global')
        else:
            # Create group chat
            if self.mode.startswith('p2p'):
                if self.p2p_manager:
                    self.p2p_manager.create_group(target)
            elif self.mode == 'server' and self.server_manager:
                self.server_manager.create_group(target)

        if hasattr(self, 'new_chat_popup'):
            self.new_chat_popup.dismiss()

    def toggle_voice_recording(self):
        """Toggle voice message recording"""
        voice_button = self.root.ids.input_area.ids.voice_button

        if not self.is_recording_audio_message:
            # Start recording
            voice_button.icon = 'stop'
            voice_button.md_bg_color = rgba('#651FFF')

            config = self.config_manager.load_config()
            device_name = config.get('input_device_name', 'Default')
            input_devices, _ = self.audio_manager.get_devices()
            device_index = input_devices.get(device_name, sd.default.device[0])

            self.audio_message_path = os.path.join("audio_messages", f"{uuid.uuid4()}.wav")
            os.makedirs("audio_messages", exist_ok=True)

            if self.audio_manager.start_recording(self.audio_message_path, device_index):
                self.add_message_to_box("System: Recording voice message...", self.active_chat)
            else:
                self.add_message_to_box("System: Failed to start recording.", self.active_chat)
                voice_button.icon = 'microphone'
        else:
            # Stop recording
            voice_button.icon = 'microphone'
            voice_button.md_bg_color = rgba('#4a148c')

            self.audio_manager.stop_recording()
            self.add_message_to_box(f"System: Voice message saved. Ready to send.", self.active_chat)

            # Here we could implement sending the voice message
            message_data = {
                'id': str(uuid.uuid4()),
                'sender': self.username,
                'audio_path': self.audio_message_path,
                'timestamp': datetime.now().isoformat()
            }
            self.chat_history.setdefault(self.active_chat, []).append(message_data)
            self.add_message_to_box(message_data, self.active_chat)

        self.is_recording_audio_message = not self.is_recording_audio_message

    def show_attachment_menu(self):
        """Show attachment menu with file options"""
        menu_items = [
            {
                "text": "Photo/Gallery",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.attach_file('image')
            },
            {
                "text": "File",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.attach_file('file')
            },
            {
                "text": "Contact",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.attach_contact()
            },
            {
                "text": "Location",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.attach_location()
            }
        ]

        attachment_menu = MDDropdownMenu(
            caller=self.root.ids.input_area.ids.attachment_button,
            items=menu_items,
            width_mult=4
        )
        attachment_menu.open()

    def attach_file(self, file_type):
        """Handle file attachment"""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            self.show_popup("Error", "Tkinter not available for file selection")
            return

        try:
            root = tk.Tk()
            root.withdraw()

            if file_type == 'image':
                file_path = filedialog.askopenfilename(
                    title="Select Image",
                    filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.bmp *.tiff")]
                )
            else:
                file_path = filedialog.askopenfilename(
                    title="Select File",
                    filetypes=[("All files", "*.*")]
                )

            if file_path:
                # Send file using file transfer plugin
                if self.plugin_manager:
                    ft_plugin = self.plugin_manager.get_plugin_by_id('file_transfer')
                    if ft_plugin and ft_plugin['instance']:
                        if self.active_chat and self.active_chat != 'global':
                            ft_plugin['instance'].send_filepath(file_path, self.active_chat)
                            self.add_message_to_box(f"System: File sent: {os.path.basename(file_path)}", self.active_chat)
                        else:
                            self.add_message_to_box("System: Cannot send files in global chat", self.active_chat)
                    else:
                        self.add_message_to_box("System: File transfer plugin not loaded", self.active_chat)
            root.destroy()
        except Exception as e:
            print(f"Error in attach_file: {e}")
            self.show_popup("Error", f"Error selecting file: {str(e)}")

    def attach_contact(self):
        """Handle contact attachment"""
        if not self.contacts:
            self.show_popup("No Contacts", "You don't have any contacts to share")
            return

        # Show contact selection popup
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None, height="300dp")

        for contact in self.contacts:
            btn = MDRaisedButton(text=contact, size_hint_x=1, height=dp(40))
            btn.bind(on_press=lambda x, c=contact: self.send_contact_card(c))
            content_layout.add_widget(btn)

        contact_popup = MDDialog(
            title="Select Contact",
            type="custom",
            content_cls=content_layout,
            auto_dismiss=True
        )
        contact_popup.open()

    def attach_location(self):
        """Handle location attachment"""
        # For now, send a mock location
        import random
        lat = 55.7558 + random.uniform(-1, 1)  # Moscow area
        lon = 37.6176 + random.uniform(-1, 1)

        location_data = {
            'id': str(uuid.uuid4()),
            'sender': self.username,
            'type': 'location',
            'latitude': lat,
            'longitude': lon,
            'timestamp': datetime.now().isoformat()
        }

        if self.active_chat and self.active_chat != 'global':
            if self.mode.startswith('p2p'):
                if self.p2p_manager:
                    self.p2p_manager.send_private_message(self.active_chat, location_data)
            elif self.mode == 'server' and self.server_manager:
                self.server_manager.send_group_message(self.active_chat, location_data)

            self.add_message_to_box(location_data, self.active_chat)
        else:
            self.add_message_to_box("System: Cannot send location in global chat", self.active_chat)

    def send_contact_card(self, contact):
        """Send a contact card"""
        contact_data = {
            'id': str(uuid.uuid4()),
            'sender': self.username,
            'type': 'contact',
            'contact_name': contact,
            'timestamp': datetime.now().isoformat()
        }

        if self.active_chat and self.active_chat != 'global':
            if self.mode.startswith('p2p'):
                if self.p2p_manager:
                    self.p2p_manager.send_private_message(self.active_chat, contact_data)
            elif self.mode == 'server' and self.server_manager:
                self.server_manager.send_group_message(self.active_chat, contact_data)

            self.add_message_to_box(contact_data, self.active_chat)
        else:
            self.add_message_to_box("System: Cannot send contact in global chat", self.active_chat)

    def open_profile_panel(self):
        """Open the profile/info panel"""
        try:
            profile_panel = self.root.ids.profile_panel
            if profile_panel.opacity < 1:
                profile_panel.disabled = False
                Animation(opacity=1, duration=0.2).start(profile_panel)
        except (KeyError, AttributeError):
            print("Warning: Could not access profile panel")

    def close_profile_panel(self):
        """Close the profile/info panel"""
        try:
            profile_panel = self.root.ids.profile_panel
            if profile_panel.opacity > 0:
                Animation(opacity=0, duration=0.2).start(profile_panel)
                profile_panel.disabled = True
        except (KeyError, AttributeError):
            print("Warning: Could not access profile panel")

    def open_settings(self):
        """Open the settings screen"""
        if not self.root or not hasattr(self.root, 'ids'):
            print("Warning: UI not ready for open_settings")
            return

        try:
            self.root.ids.screen_manager.current = 'settings'
        except (KeyError, AttributeError):
            print("Warning: Could not access screen manager")

    def go_back(self):
        """Go back from settings screen"""
        try:
            self.root.ids.screen_manager.current = 'main'
        except (KeyError, AttributeError):
            print("Warning: Could not access screen manager")

    # Settings related methods
    def clear_cache(self):
        """Clear application cache"""
        self.show_popup("Cache Cleared", "Application cache has been cleared successfully.")

    def export_data(self):
        """Export user data"""
        self.show_popup("Data Export", "Data export functionality would be implemented here.")

    def send_feedback(self):
        """Send user feedback"""
        self.show_popup("Feedback", "Feedback form would be implemented here.")

    # Chat menu methods
    def show_chat_menu(self):
        """Show chat options menu"""
        menu_items = [
            {
                "text": "View Profile",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.open_profile_panel()
            },
            {
                "text": "Delete Chat",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.delete_chat()
            },
            {
                "text": "Clear History",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.clear_chat_history()
            },
            {
                "text": "Mute/Unmute",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.toggle_chat_mute()
            },
            {
                "text": "Block/Unblock",
                "viewclass": "OneLineListItem",
                "on_release": lambda x: self.toggle_user_block()
            }
        ]

        chat_header = self.root.ids.chat_header
        chat_menu = MDDropdownMenu(
            caller=chat_header.ids.chat_menu_button,
            items=menu_items,
            width_mult=4
        )
        chat_menu.open()

    def delete_chat(self):
        """Delete current chat"""
        if self.active_chat == 'global':
            self.show_popup("Error", "Cannot delete global chat")
            return

        if self.active_chat in self.chat_history:
            del self.chat_history[self.active_chat]

        # Remove from chat list UI
        chat_list = self.root.ids.chat_list
        for child in chat_list.children:
            if hasattr(child, 'user_id') and child.user_id == self.active_chat:
                chat_list.remove_widget(child)
                break

        # Clean up groups if it's a group
        if self.mode.startswith('p2p') and self.p2p_manager:
            if self.active_chat in self.p2p_manager.groups:
                del self.p2p_manager.groups[self.active_chat]
        elif self.mode == 'server' and self.server_manager:
            if self.active_chat in self.server_groups:
                del self.server_groups[self.active_chat]

        self.show_popup("Chat Deleted", f"Chat '{self.active_chat}' has been deleted")
        self.switch_chat('global')

    def clear_chat_history(self):
        """Clear chat history"""
        if self.active_chat == 'global':
            self.show_popup("Error", "Cannot clear global chat history")
            return

        # Clear messages from UI
        try:
            if not self.root or not hasattr(self.root, 'ids'):
                print("Warning: UI not ready, cannot clear UI messages")
                return
            messages_container = self.root.ids.messages_container
            messages_container.clear_widgets()
        except (KeyError, AttributeError):
            print("Warning: messages_container not found, cannot clear UI messages")

        # Clear from history
        if self.active_chat in self.chat_history:
            self.chat_history[self.active_chat] = []

        self.show_popup("History Cleared", f"Chat history for '{self.active_chat}' has been cleared")

    def toggle_chat_mute(self):
        """Toggle chat mute status"""
        if self.active_chat == 'global':
            self.show_popup("Error", "Cannot mute global chat")
            return

        # Show mute duration options
        content_layout = MDBoxLayout(orientation='vertical', spacing="10dp", size_hint_y=None, height="300dp")

        durations = [
            ("1 hour", 1),
            ("8 hours", 8),
            ("1 day", 24),
            ("1 week", 168),
            ("1 month", 720),
            ("Forever", -1)
        ]

        for text, hours in durations:
            btn = MDRaisedButton(text=text, size_hint_x=1, height=dp(40))
            btn.bind(on_press=lambda x, h=hours: self.mute_chat(h))
            content_layout.add_widget(btn)

        mute_popup = MDDialog(
            title=f"Mute Chat: {self.active_chat}",
            type="custom",
            content_cls=content_layout,
            auto_dismiss=True
        )
        mute_popup.open()

    def toggle_user_block(self):
        """Toggle user block status"""
        if self.active_chat == 'global':
            self.show_popup("Error", "Cannot block users in global chat")
            return

        # Toggle block status
        blocked_users = set()  # This should be loaded from config
        if self.active_chat in blocked_users:
            # Unblock
            blocked_users.remove(self.active_chat)
            self.show_popup("User Unblocked", f"{self.active_chat} has been unblocked")
        else:
            # Block
            blocked_users.add(self.active_chat)
            self.show_popup("User Blocked", f"{self.active_chat} has been blocked")
            self.switch_chat('global')

    def mute_chat(self, hours):
        """Mute chat for specified hours"""
        duration_text = "forever" if hours == -1 else f"{hours} hours"
        self.show_popup("Chat Muted", f"'{self.active_chat}' has been muted for {duration_text}")

        # Here you would save the mute status to config
        # and implement the actual muting logic

    # Profile related methods
    def send_direct_message(self):
        """Send direct message to profile user"""
        self.show_popup("Send Message", "Direct message would be implemented here.")

    def start_call(self):
        """Start call with profile user"""
        if self.active_chat and self.active_chat != 'global':
            self.initiate_call(self.active_chat)

    def delete_contact(self):
        """Delete contact"""
        self.show_popup("Delete Contact", "Contact deletion would be implemented here.")

    def block_user(self):
        """Block user"""
        self.show_popup("Block User", "User blocking would be implemented here.")

    def delete_conversation(self):
        """Delete conversation"""
        self.show_popup("Delete Conversation", "Conversation deletion would be implemented here.")

    def change_profile_picture(self):
        """Change profile picture"""
        self.show_popup("Change Profile Picture", "Profile picture change would be implemented here.")

    # Navigation methods
    def open_my_profile(self):
        """Open user's own profile"""
        self.open_profile_panel()

    def create_group(self):
        """Create a new group"""
        self.show_create_group_popup(None)

    def open_contacts(self):
        """Open contacts list"""
        self.show_popup("Contacts", "Contacts list would be implemented here.")

    def open_calls(self):
        """Open call history"""
        if not self.root or not hasattr(self.root, 'ids'):
            print("Warning: UI not ready for open_calls")
            return

        try:
            self.root.ids.screen_manager.current = 'calls'
        except (KeyError, AttributeError):
            print("Warning: Could not access screen manager for calls")

    def open_personal_chat(self):
        """Open personal chat"""
        self.switch_chat('personal')

    def get_public_udp_addr(self):
        """Get public UDP address for group calls"""
        try:
            # This is a placeholder implementation
            # In a real implementation, you would use STUN/TURN servers
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            public_ip = s.getsockname()[0]
            s.close()
            return (public_ip, 0)  # Return IP and port (port would be determined by server)
        except Exception as e:
            print(f"Error getting public address: {e}")
            return ("127.0.0.1", 0)

    def join_server_group_call(self, group_id):
        """Join server group call (placeholder)"""
        self.active_group_call = group_id
        self.show_group_call_popup()

        # This would need server-side implementation
        self.add_message_to_box("System: Server group calls not fully implemented", group_id)

    def request_contact(self, target_username):
        """Request contact with user"""
        if self.mode.startswith('p2p') and self.p2p_manager:
            self.p2p_manager.send_contact_request(target_username)
            self.add_message_to_box(f"System: Contact request sent to '{target_username}'", 'global')
        else:
            self.show_popup("Error", "Contact requests not available in current mode")



# Import the new widget classes from the .kv file
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior

# Define the new widget classes for the Telegram-style interface
class ChatListItem(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected = False
        self.user_id = None
        self.unread_count = 0

class MessageBubble(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_own = False
        self.message_id = None
        self.status = 'sent'

class ImageMessageBubble(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_own = False
        self.status = 'sent'

class VoiceMessageBubble(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_own = False
        self.status = 'sent'

class EmojiButton(ButtonBehavior, MDLabel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class EmojiGrid(MDGridLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cols = 8
        self.spacing = dp(5)
        self.padding = dp(10)
        self.size_hint_y = None
        self.height = self.minimum_height

if __name__ == '__main__':
    VoiceChatApp().run()
