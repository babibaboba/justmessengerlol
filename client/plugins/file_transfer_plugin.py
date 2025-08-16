import os
import socket
import threading
import uuid
from functools import partial

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.clock import mainthread

# Assuming plugin_manager and its BasePlugin are discoverable
# This might require adjusting sys.path, which the PluginManager does.
from plugin_manager import BasePlugin
# We also need the custom popup from the main app
from client import AnimatedPopup


# --- THREADS (Copied from client.py) ---

class FileSenderThread(threading.Thread):
    def __init__(self, filepath, server_socket, transfer_id, callback_queue):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.server_socket = server_socket
        self.transfer_id = transfer_id
        self.callback_queue = callback_queue
        self.running = True

    def run(self):
        try:
            self.server_socket.settimeout(30)
            conn, addr = self.server_socket.accept()
            filesize = os.path.getsize(self.filepath)
            with open(self.filepath, 'rb') as f:
                sent_bytes = 0
                while self.running:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    conn.sendall(chunk)
                    sent_bytes += len(chunk)
                    self.callback_queue.put(('progress', self.transfer_id, int((sent_bytes / filesize) * 100)))
            if self.running:
                self.callback_queue.put(('finished', self.transfer_id, f"File '{os.path.basename(self.filepath)}' sent."))
        except socket.timeout:
            self.callback_queue.put(('error', self.transfer_id, "Receiver did not connect."))
        except Exception as e:
            self.callback_queue.put(('error', self.transfer_id, f"Error: {e}"))
        finally:
            if 'conn' in locals():
                conn.close()
            try:
                self.server_socket.close()
            except:
                pass

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except:
            pass

class FileReceiverThread(threading.Thread):
    def __init__(self, target_ip, target_port, filename, filesize, save_path, transfer_id, callback_queue):
        super().__init__(daemon=True)
        self.target_ip = target_ip
        self.target_port = target_port
        self.filename = filename
        self.filesize = filesize
        self.save_path = save_path
        self.transfer_id = transfer_id
        self.callback_queue = callback_queue
        self.running = True

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.target_ip, self.target_port))
            with open(self.save_path, 'wb') as f:
                received_bytes = 0
                while self.running and received_bytes < self.filesize:
                    chunk = sock.recv(4096)
                    if not chunk:
                        if received_bytes < self.filesize:
                            raise ConnectionAbortedError("Connection closed prematurely.")
                        break
                    f.write(chunk)
                    received_bytes += len(chunk)
                    self.callback_queue.put(('progress', self.transfer_id, int((received_bytes / self.filesize) * 100)))
            if self.running:
                self.callback_queue.put(('finished', self.transfer_id, f"File '{self.filename}' received."))
        except Exception as e:
            self.callback_queue.put(('error', self.transfer_id, f"Error receiving file: {e}"))
        finally:
            sock.close()

    def stop(self):
        self.running = False

# --- WIDGETS (Copied from client.py) ---

class FileSelectPopup(AnimatedPopup):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "Select a File to Send"
        self.size_hint = (0.9, 0.9)
        layout = BoxLayout(orientation='vertical')
        self.file_chooser = FileChooserListView()
        try:
            user_dir = os.path.expanduser('~')
            if os.path.isdir(user_dir):
                self.file_chooser.path = user_dir
        except Exception:
            pass
        layout.add_widget(self.file_chooser)
        btn_layout = BoxLayout(size_hint_y=None, height=44)
        ok_btn = Button(text='Send')
        ok_btn.bind(on_press=self.send_file)
        cancel_btn = Button(text='Cancel')
        cancel_btn.bind(on_press=self.dismiss)
        btn_layout.add_widget(ok_btn)
        btn_layout.add_widget(cancel_btn)
        layout.add_widget(btn_layout)
        self.content = layout

    def send_file(self, instance):
        if self.file_chooser.selection:
            self.filepath = self.file_chooser.selection[0]
            self.dismiss()

class FileTransferWidget(BoxLayout):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = 60
        self.label = Label(text=text, size_hint_y=None, height=30)
        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=30)
        self.add_widget(self.label)
        self.add_widget(self.progress_bar)

    def set_progress(self, value):
        self.progress_bar.value = value

    def set_text(self, text):
        self.label.text = text


# --- PLUGIN ---

class FileTransferPlugin(BasePlugin):
    def initialize(self):
        """
        Initialize the plugin:
        - Add UI elements.
        - Register P2P manager callbacks.
        - Initialize internal state.
        """
        self.file_transfer_threads = {}
        self.file_transfer_widgets = {}
        self.selected_user_for_file = None

        # Add the "Attach File" button to the main UI
        chat_ids = self.app.root.ids.chat_layout.ids
        self.attach_button = Button(
            text=self.app.tr.get('attach_button', '📎'),
            font_name='C:/Windows/Fonts/seguiemj.ttf', # Font for emoji
            size_hint_x=None,
            width=40
        )
        self.attach_button.bind(on_press=self.select_user_for_file_transfer)
        # Add it next to the send button, for example
        chat_ids.input_layout.add_widget(self.attach_button, 2) # Adjust index based on new emoji button

        # Register callbacks with the P2P manager if it exists
        if self.app.p2p_manager:
            self.app.p2p_manager.register_callback('incoming_file_request', self.handle_incoming_file_request)
            self.app.p2p_manager.register_callback('file_request_response', self.handle_file_request_response)
        
        # Add our own callback processing to the main app's queue processing
        # This is a simple way to hook in. A more robust system might use events.
        self.original_process_callbacks = self.app.process_callbacks
        self.app.process_callbacks = self.process_plugin_callbacks

    def unload(self):
        """Clean up when the plugin is unloaded."""
        for thread in self.file_transfer_threads.values():
            thread.stop()
        # Restore original callback processor
        if hasattr(self, 'original_process_callbacks'):
            self.app.process_callbacks = self.original_process_callbacks

    def process_plugin_callbacks(self, dt):
        """Wrapper around the app's callback processor to handle our events."""
        # First, let the app handle its own events
        self.original_process_callbacks(dt)
        
        # Now, check for our file transfer events
        while not self.app.callback_queue.empty():
            try:
                event = self.app.callback_queue.get_nowait()
                event_type = event[0]
                
                if event_type == 'progress':
                    _, transfer_id, data = event
                    self.update_transfer_progress(transfer_id, data)
                elif event_type == 'finished':
                    _, transfer_id, data = event
                    self.finish_transfer(transfer_id, data)
                elif event_type == 'error':
                    _, transfer_id, data = event
                    self.fail_transfer(transfer_id, data)
                else:
                    # If it's not our event, put it back for the app to handle next time
                    self.app.callback_queue.put(event)
                    break # Stop processing to avoid infinite loops
            except Exception:
                break # Queue is empty or another issue


    def select_user_for_file_transfer(self, instance):
        if not self.app.p2p_manager or not self.app.p2p_manager.peers:
            self.app.add_message_to_box("System: No users online to send a file to.", 'global')
            return
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text="Select a user:"))
        popup = AnimatedPopup(title="Select User", content=box, size_hint=(0.6, 0.8))
        for username in self.app.p2p_manager.peers.keys():
            btn = Button(text=username)
            btn.bind(on_press=partial(self.user_selected_for_file, username, popup))
            box.add_widget(btn)
        popup.open()

    def user_selected_for_file(self, username, popup, instance):
        popup.dismiss()
        self.selected_user_for_file = username
        file_popup = FileSelectPopup()
        file_popup.bind(on_dismiss=self.on_file_selected)
        file_popup.open()

    def on_file_selected(self, popup):
        filepath = getattr(popup, 'filepath', None)
        if filepath:
            self.send_filepath(filepath, self.selected_user_for_file)

    def send_filepath(self, filepath, target_username):
        if not filepath or not target_username:
            return
        try:
            filesize = os.path.getsize(filepath)
            filename = os.path.basename(filepath)
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind(('', 0))
            server_sock.listen(1)
            listen_port = server_sock.getsockname()[1]
            self.app.p2p_manager.send_file_transfer_request(target_username, filename, filesize, listen_port)
            transfer_id = f"send_{target_username}_{filename}"
            sender_thread = FileSenderThread(filepath, server_sock, transfer_id, self.app.callback_queue)
            sender_thread.start()
            self.file_transfer_threads[transfer_id] = sender_thread
            self.add_transfer_widget(transfer_id, f"Sending '{filename}' to {target_username}... (waiting)")
        except Exception as e:
            self.app.add_message_to_box(f"Error preparing file transfer: {e}", 'global')

    @mainthread
    def handle_incoming_file_request(self, sender_username, filename, filesize, ip, port):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        text = self.app.tr.get('file_transfer_request_text', username=sender_username, filename=filename, size=round(filesize / 1024, 2))
        box.add_widget(Label(text=text))
        btn_layout = BoxLayout(spacing=10)
        yes_btn = Button(text='Accept')
        no_btn = Button(text='Decline')
        btn_layout.add_widget(yes_btn)
        btn_layout.add_widget(no_btn)
        box.add_widget(btn_layout)
        popup = AnimatedPopup(title=self.app.tr.get('file_transfer_request_title'), content=box, size_hint=(0.8, 0.5), auto_dismiss=False)
        
        def on_yes(inst):
            popup.dismiss()
            save_path = os.path.join(os.getcwd(), filename) # Consider a dedicated downloads folder
            self.app.p2p_manager.send_file_transfer_response(sender_username, accepted=True)
            transfer_id = f"recv_{sender_username}_{filename}"
            receiver_thread = FileReceiverThread(ip, port, filename, filesize, save_path, transfer_id, self.app.callback_queue)
            receiver_thread.start()
            self.file_transfer_threads[transfer_id] = receiver_thread
            self.add_transfer_widget(transfer_id, f"Receiving '{filename}' from {sender_username}...")
        
        def on_no(inst):
            popup.dismiss()
            self.app.p2p_manager.send_file_transfer_response(sender_username, accepted=False)
        
        yes_btn.bind(on_press=on_yes)
        no_btn.bind(on_press=on_no)
        popup.open()

    @mainthread
    def handle_file_request_response(self, target_username, accepted):
        if not accepted:
            transfer_id_part = f"send_{target_username}_"
            for tid, thread in list(self.file_transfer_threads.items()):
                if tid.startswith(transfer_id_part):
                    thread.stop()
                    del self.file_transfer_threads[tid]
                    self.fail_transfer(tid, f"Rejected by {target_username}.")
                    break

    @mainthread
    def add_transfer_widget(self, transfer_id, text):
        widget = FileTransferWidget(text)
        self.file_transfer_widgets[transfer_id] = widget
        self.app.root.ids.chat_layout.ids.chat_box.add_widget(widget)

    @mainthread
    def update_transfer_progress(self, transfer_id, progress):
        if transfer_id in self.file_transfer_widgets:
            self.file_transfer_widgets[transfer_id].set_progress(progress)

    @mainthread
    def finish_transfer(self, transfer_id, message):
        if transfer_id in self.file_transfer_widgets:
            self.file_transfer_widgets[transfer_id].set_text(message)
        if transfer_id in self.file_transfer_threads:
            del self.file_transfer_threads[transfer_id]

    @mainthread
    def fail_transfer(self, transfer_id, error_message):
        if transfer_id in self.file_transfer_widgets:
            self.file_transfer_widgets[transfer_id].set_text(f"Failed: {error_message}")
        if transfer_id in self.file_transfer_threads:
            del self.file_transfer_threads[transfer_id]