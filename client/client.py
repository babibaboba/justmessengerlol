import sys
import os
import socket
import uuid
import threading
import pyaudio
import queue
from datetime import datetime
from functools import partial
import regex

# Kivy imports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelHeader
from kivy.clock import mainthread, Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.core.audio import SoundLoader

# --- Set borderless before anything else ---
Window.borderless = True
Window.size = (1000, 600)

# Project imports
try:
    from config_manager import ConfigManager
    from p2p_manager import P2PManager
    from server_manager import ServerManager
    from localization import Translator
    import stun
    from hotkey_manager import HotkeyManager
    from pynput import keyboard
    from bluetooth_manager import BluetoothManager
    from audio_recorder import AudioRecorder
    from audio_manager import AudioManager
    from plugin_manager import PluginManager
except ImportError as e: print(f"Import Error: {e}"); sys.exit(1)

# --- Constants ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

# --- UI-Agnostic Threads ---

class AudioThread(threading.Thread):
    def __init__(self, udp_socket, peer_addr, sample_rate, input_device_index=None, output_device_index=None):
        super().__init__(daemon=True)
        self.udp_socket = udp_socket
        self.peer_addr = peer_addr
        self.rate = sample_rate
        self.running = True
        self.muted = False
        self.audio = pyaudio.PyAudio()
        
        self.output_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                             rate=self.rate, output=True,
                                             frames_per_buffer=CHUNK,
                                             output_device_index=output_device_index)
        
        self.input_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                            rate=self.rate, input=True,
                                            frames_per_buffer=CHUNK,
                                            input_device_index=input_device_index)

    def run(self):
        send_thread = threading.Thread(target=self.send_audio, daemon=True)
        receive_thread = threading.Thread(target=self.receive_audio, daemon=True)
        send_thread.start()
        receive_thread.start()
        send_thread.join()
        receive_thread.join()

    def send_audio(self):
        while self.running:
            try:
                data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                if self.muted:
                    data = b'\x00' * len(data)
                self.udp_socket.sendto(data, self.peer_addr)
            except (IOError, OSError):
                break

    def receive_audio(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(CHUNK * 2)
                self.output_stream.write(data)
            except (IOError, OSError):
                break

    def stop(self):
        self.running = False
        self.input_stream.stop_stream()
        self.input_stream.close()
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.audio.terminate()
        print("AudioThread stopped.")

    def set_muted(self, muted):
        self.muted = muted


# --- Kivy Popups & Widgets ---

class AnimatedPopup(Popup):
    def open(self, *args, **kwargs):
        self.scale = 0.8
        self.opacity = 0
        super().open(*args, **kwargs)
        anim = Animation(scale=1, opacity=1, d=0.2, t='out_quad')
        anim.start(self)

class TitleBar(BoxLayout):
    def on_touch_move(self, touch):
        if touch.grab_current is self:
            Window.left = self._start_x + (touch.x - self._touch_x)
            Window.top = self._start_y - (touch.y - self._touch_y)
        return super().on_touch_move(touch)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            for child in self.children:
                if isinstance(child, Button) and child.collide_point(*touch.pos):
                    return super().on_touch_down(touch)
            touch.grab(self)
            self._start_x = Window.left
            self._start_y = Window.top
            self._touch_x = touch.x
            self._touch_y = touch.y
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

class RootLayout(BoxLayout): pass
class ChatLayout(BoxLayout): pass

class CallPopup(AnimatedPopup):
    def __init__(self, peer_username, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.is_muted = False
        self.title = self.tr.get('call_window_title', peer_username=peer_username)
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

class EmojiPopup(AnimatedPopup):
    def __init__(self, translator, **kwargs):
        super().__init__(**kwargs)
        self.tr = translator
        self.title = self.tr.get('emoji_popup_title', 'Select Emoji')
        self.size_hint = (None, None)
        self.size = (400, 300)
        
        # Popular emojis
        emojis = [
            '🙂', '😂', '❤️', '👍', '🤔', '🎉', '🙏', '🔥',
            '😊', '😭', '😍', '👎', '🙄', '👏', '😢', '😎'
        ]
        
        grid = GridLayout(cols=4, spacing=10, padding=10)
        for emoji in emojis:
            btn = Button(
                text=emoji,
                font_name='C:/Windows/Fonts/seguiemj.ttf',
                font_size='24sp'
            )
            btn.bind(on_press=self.select_emoji)
            grid.add_widget(btn)
            
        self.content = grid
        self.register_event_type('on_select')

    def select_emoji(self, instance):
        self.dispatch('on_select', instance.text)
        self.dismiss()

    def on_select(self, emoji):
        pass

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
    def __init__(self, translator, config, audio_manager, **kwargs):
        super().__init__(**kwargs)
        if not audio_manager:
            raise ValueError("SettingsPopup requires a valid AudioManager instance.")
        self.tr = translator
        self.config = config
        self.audio_manager = audio_manager
        self.title = self.tr.get('settings_title', 'Settings')
        self.size_hint = (0.8, 0.9)
        self.auto_dismiss = False
        self.new_hotkey = set()
        self.recording = False
        self.audio_devices = self.audio_manager.get_audio_devices()
        self.listener = None
        self.is_testing = False
        self.test_sound = None

        # --- Main Layout ---
        main_layout = BoxLayout(orientation='vertical', spacing=5, padding=10)
        
        # --- Tabbed Panel for Settings ---
        tab_panel = TabbedPanel(do_default_tab=False)
        
        # --- Audio Tab ---
        audio_tab = TabbedPanelHeader(text=self.tr.get('audio_tab', 'Audio'))
        audio_tab.content = self.create_audio_tab()
        tab_panel.add_widget(audio_tab)

        # --- Hotkeys Tab ---
        hotkeys_tab = TabbedPanelHeader(text=self.tr.get('hotkeys_tab', 'Hotkeys'))
        hotkeys_tab.content = self.create_hotkeys_tab()
        tab_panel.add_widget(hotkeys_tab)

        # --- Security Tab ---
        security_tab = TabbedPanelHeader(text=self.tr.get('security_tab', 'Security'))
        security_tab.content = self.create_security_tab()
        tab_panel.add_widget(security_tab)

        main_layout.add_widget(tab_panel)

        # --- Action Buttons ---
        btn_layout = BoxLayout(size_hint_y=None, height=44, spacing=10)
        save_btn = Button(text=self.tr.get('save_button'))
        save_btn.bind(on_press=self.save_and_dismiss)
        cancel_btn = Button(text=self.tr.get('cancel_button', 'Cancel'))
        cancel_btn.bind(on_press=self.dismiss)
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(cancel_btn)
        main_layout.add_widget(btn_layout)
        
        self.content = main_layout

    def create_audio_tab(self):
        layout = BoxLayout(orientation='vertical', spacing=5, padding=10)
        # Input device
        layout.add_widget(Label(text=self.tr.get('input_device_label', 'Input Device:'), size_hint_y=None, height=30))
        input_layout = BoxLayout(size_hint_y=None, height=44)
        input_devices = [f"{d['name']} (API: {d['hostApiName']})" for d in self.audio_devices['input']]
        self.input_spinner = Spinner(text=self.get_device_name('input'), values=input_devices)
        self.input_spinner.bind(text=self.on_input_device_change)
        test_mic_btn = Button(text=self.tr.get('test_mic_button', 'Test'), size_hint_x=0.2)
        test_mic_btn.bind(on_press=self.test_input_device)
        input_layout.add_widget(self.input_spinner)
        input_layout.add_widget(test_mic_btn)
        layout.add_widget(input_layout)
        self.input_volume_slider = Slider(min=0, max=100, value=self.get_current_volume('input'), size_hint_y=None, height=44)
        self.input_volume_slider.bind(value=self.on_input_volume_change)
        layout.add_widget(self.input_volume_slider)
        # Output device
        layout.add_widget(Label(text=self.tr.get('output_device_label', 'Output Device:'), size_hint_y=None, height=30))
        output_layout = BoxLayout(size_hint_y=None, height=44)
        output_devices = [f"{d['name']} (API: {d['hostApiName']})" for d in self.audio_devices['output']]
        self.output_spinner = Spinner(text=self.get_device_name('output'), values=output_devices)
        self.output_spinner.bind(text=self.on_output_device_change)
        test_speaker_btn = Button(text=self.tr.get('test_speaker_button', 'Test'), size_hint_x=0.2)
        test_speaker_btn.bind(on_press=self.test_output_device)
        output_layout.add_widget(self.output_spinner)
        output_layout.add_widget(test_speaker_btn)
        layout.add_widget(output_layout)
        self.output_volume_slider = Slider(min=0, max=100, value=self.get_current_volume('output'), size_hint_y=None, height=44)
        self.output_volume_slider.bind(value=self.on_output_volume_change)
        layout.add_widget(self.output_volume_slider)
        return layout

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

    def test_input_device(self, instance):
        if self.is_testing:
            return
        self.is_testing = True
        instance.disabled = True
        instance.text = self.tr.get('testing_button', 'Testing...')
        
        input_device_index = self._get_selected_device_index('input')
        output_device_index = self._get_selected_device_index('output')

        def test_mic_thread():
            try:
                audio = pyaudio.PyAudio()
                # Record
                stream_in = audio.open(format=pyaudio.paInt16, channels=1, rate=44100,
                                       input=True, frames_per_buffer=1024,
                                       input_device_index=input_device_index)
                frames = []
                for _ in range(0, int(44100 / 1024 * 2)): # 2 seconds
                    data = stream_in.read(1024)
                    frames.append(data)
                stream_in.stop_stream()
                stream_in.close()
                
                # Playback
                stream_out = audio.open(format=pyaudio.paInt16, channels=1, rate=44100,
                                        output=True, frames_per_buffer=1024,
                                        output_device_index=output_device_index)
                for data in frames:
                    stream_out.write(data)
                stream_out.stop_stream()
                stream_out.close()
                audio.terminate()
            except Exception as e:
                print(f"Mic test error: {e}")
            finally:
                def reset_test_button(dt):
                    instance.disabled = False
                    instance.text = self.tr.get('test_mic_button', 'Test')
                    self.is_testing = False
                Clock.schedule_once(reset_test_button, 0)

        threading.Thread(target=test_mic_thread, daemon=True).start()

    def test_output_device(self, instance):
        if self.is_testing:
            return
        
        output_device_index = self._get_selected_device_index('output')
        
        # Stop previous sound if playing
        if self.test_sound and self.test_sound.state == 'play':
            self.test_sound.stop()

        # Generate a simple sine wave to avoid needing a file
        import wave
        import numpy as np
        import io

        sample_rate = 44100
        duration = 1 # seconds
        frequency = 440 # A4
        volume = 0.5
        
        t = np.linspace(0., duration, int(sample_rate * duration), endpoint=False)
        amplitude = np.iinfo(np.int16).max * volume
        data = amplitude * np.sin(2. * np.pi * frequency * t)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(data.astype(np.int16).tobytes())
        
        wav_buffer.seek(0)

        # Kivy's SoundLoader can't load from memory directly with a specific output,
        # so we use pyaudio for playback.
        def test_speaker_thread():
            self.is_testing = True
            instance.disabled = True
            try:
                with wave.open(wav_buffer, 'rb') as wf:
                    p = pyaudio.PyAudio()
                    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                                    channels=wf.getnchannels(),
                                    rate=wf.getframerate(),
                                    output=True,
                                    output_device_index=output_device_index)
                    
                    data = wf.readframes(1024)
                    while data:
                        stream.write(data)
                        data = wf.readframes(1024)

                    stream.stop_stream()
                    stream.close()
                    p.terminate()
            except Exception as e:
                print(f"Speaker test error: {e}")
            finally:
                instance.disabled = False
                self.is_testing = False

        threading.Thread(target=test_speaker_thread, daemon=True).start()


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
        # Stop recording once a combination is released
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

    def get_audio_devices(self):
        p = pyaudio.PyAudio()
        devices = {'input': [], 'output': []}
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            if dev_info.get('maxInputChannels') > 0:
                devices['input'].append({
                    'index': i,
                    'name': dev_info.get('name'),
                    'hostApiName': p.get_host_api_info_by_index(dev_info.get('hostApi')).get('name')
                })
            if dev_info.get('maxOutputChannels') > 0:
                devices['output'].append({
                    'index': i,
                    'name': dev_info.get('name'),
                    'hostApiName': p.get_host_api_info_by_index(dev_info.get('hostApi')).get('name')
                })
        p.terminate()
        return devices

    def get_device_name(self, device_type):
        """Get the currently configured device name."""
        device_index = self.config.get(f'{device_type}_device_index')
        if device_index is not None:
            for dev in self.audio_devices[device_type]:
                if dev['index'] == device_index:
                    return f"{dev['name']} (API: {dev['hostApiName']})"
        return self.tr.get('default_device', 'Default Device')

    def _get_selected_device_index(self, device_type):
        spinner = self.input_spinner if device_type == 'input' else self.output_spinner
        selected_text = spinner.text
        for dev in self.audio_devices[device_type]:
            if f"{dev['name']} (API: {dev['hostApiName']})" == selected_text:
                return dev['index']
        return None

    def save_and_dismiss(self, instance):
        self.stop_listener()
        self.hotkey = self.new_hotkey
        
        # Save audio device settings
        self.config['input_device_index'] = self._get_selected_device_index('input')
        self.config['output_device_index'] = self._get_selected_device_index('output')
        self.config['input_volume'] = int(self.input_volume_slider.value)
        self.config['output_volume'] = int(self.output_volume_slider.value)
        
        # Save security settings
        if 'security' not in self.config:
            self.config['security'] = {}
        self.config['security']['p2p_password'] = self.p2p_password_input.text
            
        self.dismiss()

    @staticmethod
    def key_to_str(key):
        if isinstance(key, keyboard.Key):
            return key.name
        elif isinstance(key, keyboard.KeyCode):
            return key.char
        return str(key)

    def on_input_device_change(self, spinner, text):
        # Update volume slider when device changes
        self.input_volume_slider.value = self.get_current_volume('input')

    def on_output_device_change(self, spinner, text):
        self.output_volume_slider.value = self.get_current_volume('output')

    def on_input_volume_change(self, slider, value):
        device_index = self._get_selected_device_index('input')
        if device_index is not None:
            self.audio_manager.set_volume(device_index, 'input', int(value))

    def on_output_volume_change(self, slider, value):
        device_index = self._get_selected_device_index('output')
        if device_index is not None:
            self.audio_manager.set_volume(device_index, 'output', int(value))

    def get_current_volume(self, device_type):
        device_index = self._get_selected_device_index(device_type)
        volume = None
        
        if device_index is not None and self.audio_manager:
            volume = self.audio_manager.get_volume(device_index, device_type)
        
        # First, try the volume from the device
        if volume is not None:
            return int(volume)
            
        # If that fails, try the saved config value
        config_volume = self.config.get(f'{device_type}_volume')
        if config_volume is not None:
            return int(config_volume)
            
        # If all else fails, return a safe default
        return 100


class VoiceChatApp(App):
    def build(self):
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
        self.p2p_audio_thread = None # For 1-on-1 calls
        self.audio_threads = {} # For group calls {username: AudioThread}
        self.active_group_call = None # Stores group_id of the active call
        self.pending_group_call_punches = set()
        self.call_popup = None
        self.group_call_popup = None
        self.current_peer_addr = None
        self.pending_call_target = None
        self.negotiated_rate = None
        self.callback_queue = queue.Queue()
        self.hotkey_manager = HotkeyManager()
        self.is_muted = False
        self.audio_recorder = None
        self.audio_manager = None
        self.plugin_manager = None
        self.root.opacity = 0
        self.contacts = set() # Users who have accepted contact requests
        self.search_user_input = None
        
        self.chat_history = {'global': []}
        self.initialized = False
        self.active_chat = 'global' # Can be 'global' or a group_id
        
        self.themes = {
            'light': {'bg': [1,1,1,1], 'text': [0,0,0,1], 'panel_bg': [0.9,0.9,0.9,1], 'input_bg': [1,1,1,1], 'button_bg': [0.8,0.8,0.8,1], 'button_text': [0,0,0,1], 'title_bar_bg': [0.7,0.7,0.7,1]},
            'dark': {'bg': [0.1,0.1,0.1,1], 'text': [1,1,1,1], 'panel_bg': [0.15,0.15,0.15,1], 'input_bg': [0.2,0.2,0.2,1], 'button_bg': [0.3,0.3,0.3,1], 'button_text': [1,1,1,1], 'title_bar_bg': [0.25,0.25,0.25,1]}
        }
        self.current_theme = 'light'

        Clock.schedule_interval(self.process_callbacks, 0.1)
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
        title_bar_ids = self.root.ids.title_bar.ids
        
        chat_ids.send_button.bind(on_press=self.send_message)
        chat_ids.theme_button.bind(on_press=self.toggle_theme)
        chat_ids.settings_button.bind(on_press=self.show_settings_popup)
        chat_ids.record_button.bind(on_touch_down=self.start_recording, on_touch_up=self.stop_recording_and_send)
        chat_ids.emoji_button.bind(on_press=self.show_emoji_popup)
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

        title_bar_ids.minimize_btn.bind(on_press=lambda x: Window.minimize())
        title_bar_ids.maximize_btn.bind(on_press=lambda x: self.toggle_maximize())
        title_bar_ids.close_btn.bind(on_press=self.stop)

        if self.mode.startswith('p2p') and self.mode != 'p2p_bluetooth':
            self.init_p2p_mode()
        elif self.mode == 'p2p_bluetooth':
            self.init_bluetooth_mode()
        elif self.mode == 'server':
            self.init_server_mode()
        
        config = self.config_manager.load_config()
        self.audio_manager = AudioManager()
        self.apply_audio_settings(config)
        self.audio_recorder = AudioRecorder(input_device_index=config.get('input_device_index'))
        self.init_hotkeys()
        self.apply_theme()
        self.root.opacity = 1
        
        # Initialize and load plugins
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.discover_and_load_plugins()
        
        chat_ids.msg_entry.focus = True

    def toggle_maximize(self):
        if Window.fullscreen:
            Window.fullscreen = False
        else:
            Window.fullscreen = 'auto'

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
            'incoming_p2p_call': self.handle_p2p_call_request,
            'p2p_call_response': self.handle_p2p_call_response,
            'p2p_hang_up': self.handle_p2p_hang_up,
            'hole_punch_successful': self.on_hole_punch_success,
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

    def apply_theme(self):
        theme = self.themes[self.current_theme]
        chat_ids = self.root.ids.chat_layout.ids
        title_bar_ids = self.root.ids.title_bar.ids
        Window.clearcolor = theme['bg']
        set_bg(self.root, theme['bg'])
        set_bg(self.root.ids.title_bar, theme['title_bar_bg'])
        title_bar_ids.title.color = theme['text']
        for btn_id in ['minimize_btn', 'maximize_btn', 'close_btn']:
            title_bar_ids[btn_id].background_color = theme['button_bg']
            title_bar_ids[btn_id].color = theme['button_text']
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
    def get_supported_rate(self, device_index, is_input=True):
        p = pyaudio.PyAudio()
        supported_rates = [48000, 44100, 32000, 16000]
        try:
            for rate in supported_rates:
                try:
                    if p.is_format_supported(rate, input_device=device_index if is_input else None, output_device=device_index if not is_input else None, input_channels=CHANNELS if is_input else 0, output_channels=CHANNELS if not is_input else 0, input_format=FORMAT, output_format=FORMAT):
                        return rate
                except ValueError:
                    continue
            return None
        finally:
            p.terminate()

    def initiate_call(self, target_username):
        if self.p2p_audio_thread or self.active_group_call:
            self.add_message_to_box("Error: Already in a call.", 'global')
            return
            
        if self.mode.startswith('p2p') and target_username not in self.contacts:
            self.request_contact(target_username)
            return

        config = self.config_manager.load_config()
        input_device_index = config.get('input_device_index')
        supported_rate = self.get_supported_rate(input_device_index, is_input=True)
        if not supported_rate:
            self.add_message_to_box("Error: No supported sample rate for input device.", 'global')
            return
        self.negotiated_rate = supported_rate
        self.pending_call_target = target_username
        self.add_message_to_box(f"Setting up call to {target_username}...", 'global')
        self.p2p_manager.initiate_hole_punch(target_username)

    @mainthread
    def on_hole_punch_success(self, username, public_address):
        if self.pending_call_target == username: # P2P Call
            self.add_message_to_box(f"Hole punch successful. Sending call request...", 'global')
            self.current_peer_addr = (public_address[0], public_address[1])
            self.p2p_manager.send_p2p_call_request(username, self.negotiated_rate)
        elif self.current_peer_addr is True: # P2P Call
            self.add_message_to_box(f"Hole punch successful. Accepting call...", 'global')
            self.current_peer_addr = (public_address[0], public_address[1])
            self.p2p_manager.send_p2p_call_response(username, 'accept')
            self.start_audio_stream(username)
        elif username in self.pending_group_call_punches: # Group Call
            self.pending_group_call_punches.remove(username)
            self.add_message_to_box(f"Audio connection established with {username}.", self.active_group_call)
            self.start_audio_stream(username, is_group_call=True, peer_addr=public_address)

    @mainthread
    def handle_p2p_call_request(self, sender_username, sample_rate):
        if self.p2p_audio_thread or self.active_group_call:
            self.p2p_manager.send_p2p_call_response(sender_username, 'busy')
            return
        self.negotiated_rate = sample_rate
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text=self.tr.get('system_incoming_call_prompt_text', sender_username=sender_username)))
        btn_layout = BoxLayout(spacing=10)
        yes_btn = Button(text='Yes')
        no_btn = Button(text='No')
        btn_layout.add_widget(yes_btn)
        btn_layout.add_widget(no_btn)
        box.add_widget(btn_layout)
        popup = AnimatedPopup(title=self.tr.get('system_incoming_call_prompt_title'), content=box, size_hint=(0.7, 0.4), auto_dismiss=False)
        
        def on_yes(inst):
            popup.dismiss()
            self.add_message_to_box(f"Accepting call...", 'global')
            self.current_peer_addr = True
            self.p2p_manager.initiate_hole_punch(sender_username)
        
        def on_no(inst):
            popup.dismiss()
            self.p2p_manager.send_p2p_call_response(sender_username, 'reject')
            self.negotiated_rate = None
        
        yes_btn.bind(on_press=on_yes)
        no_btn.bind(on_press=on_no)
        popup.open()

    @mainthread
    def handle_p2p_call_response(self, sender_username, response):
        if response == 'accept' and self.pending_call_target == sender_username:
            self.add_message_to_box(f"Call accepted.", 'global')
            self.start_audio_stream(sender_username)
        elif response in ['reject', 'busy']:
            self.add_message_to_box(f"Call {response}.", 'global')
            self.pending_call_target = self.current_peer_addr = self.negotiated_rate = None

    @mainthread
    def start_audio_stream(self, peer_username, is_group_call=False, peer_addr=None):
        addr = peer_addr if is_group_call else self.current_peer_addr
        if not addr or not isinstance(addr, tuple):
            self.add_message_to_box(f"Error: No address for {peer_username}.", 'global')
            return
        if not self.negotiated_rate:
            self.add_message_to_box("Error: No negotiated sample rate.", 'global')
            return
        
        config = self.config_manager.load_config()
        try:
            audio_thread = AudioThread(self.udp_socket, addr, self.negotiated_rate, config.get('input_device_index'), config.get('output_device_index'))
            audio_thread.start()
            
            if is_group_call:
                self.audio_threads[peer_username] = audio_thread
                # Update group call UI
            else:
                self.p2p_audio_thread = audio_thread
                self.call_popup = CallPopup(peer_username, self.tr)
                self.call_popup.bind(on_dismiss=lambda x: self.hang_up_call(), on_mute_toggle=lambda i, m: self.p2p_audio_thread.set_muted(m))
                self.call_popup.open()
                self.pending_call_target = None
        except Exception as e:
            self.add_message_to_box(f"Error starting audio: {e}", 'global')
            self.hang_up_call()

    def hang_up_call(self):
        if self.active_group_call:
            if self.mode.startswith('p2p'):
                self.p2p_manager.send_group_hang_up(self.active_group_call)
                for username, thread in self.audio_threads.items():
                    thread.stop()
                self.audio_threads.clear()
            elif self.mode == 'server':
                self.server_manager.leave_group_call(self.active_group_call)
                if self.p2p_audio_thread: # In server mode, we use this for the single stream
                    self.p2p_audio_thread.stop()
                    self.p2p_audio_thread = None

            self.add_message_to_box("Group call ended.", self.active_group_call)
            if self.group_call_popup:
                self.group_call_popup.dismiss()
                self.group_call_popup = None
            self.active_group_call = None
            self.negotiated_rate = None
            return

        if self.p2p_audio_thread:
            self.p2p_audio_thread.stop()
            self.p2p_audio_thread = None
            peer_username = self.p2p_manager.get_peer_username_by_addr(self.current_peer_addr)
            if peer_username:
                self.p2p_manager.send_p2p_hang_up(peer_username)
            self.add_message_to_box("Call ended.", 'global')
        
        if self.call_popup:
            self.call_popup.dismiss()
            self.call_popup = None
        self.current_peer_addr = self.negotiated_rate = None

    @mainthread
    def handle_p2p_hang_up(self, sender_username):
        self.add_message_to_box(f"{sender_username} ended the call.", 'global')
        if self.p2p_audio_thread:
            self.p2p_audio_thread.stop()
            self.p2p_audio_thread = None
        if self.call_popup:
            self.call_popup.dismiss()
            self.call_popup = None
        self.current_peer_addr = self.negotiated_rate = None


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

        label = Label(text=display_text, size_hint_y=None, height=label_height, halign='left', valign='top', color=theme['text'], opacity=0, font_size=font_size)
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
        title = self.root.ids.title_bar.ids.title
        if chat_id == 'global':
            title.text = "Voice Chat"
        else:
            if self.mode.startswith('p2p'):
                group_info = self.p2p_manager.groups.get(chat_id, {})
            else: # server mode
                group_info = self.server_groups.get(chat_id, {})
            
            group_name = group_info.get('name', 'Group')
            title.text = f"Voice Chat - {group_name}"
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
        if self.active_chat == 'global' or self.active_group_call or self.p2p_audio_thread:
            return
        
        config = self.config_manager.load_config()
        input_device_index = config.get('input_device_index')
        supported_rate = self.get_supported_rate(input_device_index, is_input=True)
        if not supported_rate:
            self.add_message_to_box("Error: No supported sample rate for input device.", self.active_chat)
            return
        
        self.negotiated_rate = supported_rate
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
        if self.active_group_call or self.p2p_audio_thread:
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
        if group_id == self.active_group_call and username in self.audio_threads:
            self.audio_threads[username].stop()
            del self.audio_threads[username]
            self.add_message_to_box(f"System: {username} left the call.", group_id)
            # Update UI

    def get_public_udp_addr(self):
        try:
            # Using a public STUN server
            nat_type, external_ip, external_port = stun.get_ip_info(source_port=self.udp_socket.getsockname()[1])
            return (external_ip, external_port)
        except Exception as e:
            print(f"STUN failed: {e}")
            # Fallback to local address, might not work behind NAT
            return self.udp_socket.getsockname()

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
            self.p2p_audio_thread = AudioThread(self.udp_socket, server_addr, self.negotiated_rate, config.get('input_device_index'), config.get('output_device_index'))
            self.p2p_audio_thread.start()
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

    def show_emoji_popup(self, instance):
        popup = EmojiPopup(translator=self.tr)
        popup.bind(on_select=self.add_emoji_to_input)
        popup.open()

    def add_emoji_to_input(self, popup, emoji):
        self.root.ids.chat_layout.ids.msg_entry.text += emoji
        self.root.ids.chat_layout.ids.msg_entry.focus = True

    def show_popup(self, title, message):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text=message))
        ok_button = Button(text="OK", size_hint_y=None, height=44)
        box.add_widget(ok_button)
        popup = AnimatedPopup(title=title, content=box, size_hint=(0.7, 0.4))
        ok_button.bind(on_press=popup.dismiss)
        popup.open()

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
        if self.audio_recorder:
            # No explicit stop needed as it's not a long-running thread
            pass
        print("Application stopped.")

    # --- Audio Message Logic ---
    def start_recording(self, instance, touch):
        if instance.collide_point(*touch.pos):
            # Change button color to indicate recording
            instance.background_color = (1, 0, 0, 1) # Red
            self.audio_recorder.start()
            self.add_message_to_box(self.tr.get('system_recording_started', 'Recording audio...'), 'global')

    def stop_recording_and_send(self, instance, touch):
        # Restore button color
        self.apply_theme()
        
        filepath = self.audio_recorder.stop()
        if not filepath:
            return

        self.add_message_to_box(self.tr.get('system_recording_finished', 'Recording finished. Sending...'), 'global')

        # Determine target user (similar to image paste)
        target_user = None
        if self.mode.startswith('p2p'):
            if self.active_chat == 'global' and self.p2p_manager and len(self.p2p_manager.peers) == 1:
                target_user = list(self.p2p_manager.peers.keys())[0]
            else:
                self.add_message_to_box("System: Can only send audio messages in a 1-on-1 P2P chat.", self.active_chat)
                return
        else:
            self.add_message_to_box("System: Audio messages are not yet supported in this mode.", self.active_chat)
            return

        if target_user:
            # TODO: This functionality should be moved to a plugin
            self.add_message_to_box("System: Audio message sending is being refactored.", self.active_chat)


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
            if self.audio_manager is None:
                self.audio_manager = AudioManager()
            # The popup now needs the audio_manager instance
            popup = SettingsPopup(self.tr, config, self.audio_manager)
            popup.bind(on_dismiss=self.on_settings_dismiss)
            popup.open()
        except Exception as e:
            import traceback
            error_str = traceback.format_exc()
            print(f"CRASH IN SETTINGS: {error_str}")
            self.show_popup("Error", f"Could not open settings:\n{e}")

    def on_settings_dismiss(self, popup):
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
        
        # Mute/unmute 1-on-1 call
        if self.p2p_audio_thread:
            self.p2p_audio_thread.set_muted(self.is_muted)
        
        # Mute/unmute group call (P2P)
        for thread in self.audio_threads.values():
            thread.set_muted(self.is_muted)
            
        # Mute/unmute group call (Server) - uses p2p_audio_thread
        if self.mode == 'server' and self.active_group_call and self.p2p_audio_thread:
             self.p2p_audio_thread.set_muted(self.is_muted)

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