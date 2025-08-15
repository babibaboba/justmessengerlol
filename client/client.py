import sys
import socket
import threading
import json
import pyaudio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget, QMessageBox,
                             QDialog, QLabel, QFormLayout, QListWidget, QHBoxLayout, QSplitter,
                             QInputDialog, QGridLayout, QComboBox, QMenu, QTabWidget, QScrollArea)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize, QMetaObject

# Проверяем, существуют ли файлы, и импортируем их
try:
    from config_manager import ConfigManager
    from p2p_manager import P2PManager
    from plugin_manager import PluginManager
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что файлы config_manager.py, p2p_manager.py и plugin_manager.py находятся в той же директории.")
    sys.exit(1)


HOST = '127.0.0.1'
PORT = 12345
# --- Аудио ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100


# --- Диалоговые окна ---

class CallWindow(QDialog):
    """Окно активного звонка."""
    hang_up_pressed = pyqtSignal()
    mute_toggled = pyqtSignal(bool)

    def __init__(self, peer_username, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Звонок с {peer_username}")
        self.setFixedSize(300, 180)
        self.muted = False
        
        self.layout = QVBoxLayout(self)
        self.label = QLabel(f"Идет разговор с {peer_username}...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.mute_button = QPushButton("Выключить микрофон")
        self.mute_button.setCheckable(True)
        self.mute_button.clicked.connect(self.toggle_mute)

        self.hang_up_button = QPushButton("Завершить звонок")
        
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.mute_button)
        self.layout.addWidget(self.hang_up_button)
        
        self.hang_up_button.clicked.connect(self.hang_up_pressed.emit)
        self.hang_up_pressed.connect(self.accept) # Закрыть окно при нажатии

    def toggle_mute(self, checked):
        self.muted = checked
        self.mute_button.setText("Включить микрофон" if self.muted else "Выключить микрофон")
        self.mute_toggled.emit(self.muted)

class EmojiPanel(QWidget):
    """Панель для выбора эмодзи."""
    emoji_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        self.emojis = {
            "Smileys & People": [
                '😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇', '🙂', '🙃', '😉', '😌', '😍', '🥰',
                '😘', '😗', '😙', '😚', '😋', '😛', '😝', '😜', '🤪', '🤨', '🧐', '🤓', '😎', '🤩', '🥳', '😏',
                '😒', '😞', '😔', '😟', '😕', '🙁', '☹️', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠',
                '😡', '🤬', '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '🤥',
                '😶', '😐', '😑', '😬', '🙄', '😯', '😦', '😧', '😮', '😲', '🥱', '😴', '🤤', '😪', '😵', '🤐',
                '🥴', '🤢', '🤮', '🤧', '😷', '🤒', '🤕', '🤑', '🤠', '😈', '👿', '👹', '👺', '🤡', '💩', '👻',
                '💀', '☠️', '👽', '👾', '🤖', '🎃', '😺', '😸', '😹', '😻', '😼', '😽', '🙀', '😿', '😾', '👋',
                '🤚', '🖐', '✋', '🖖', '👌', '🤏', '✌️', '🤞', '🤟', '🤘', '🤙', '👈', '👉', '👆', '🖕', '👇',
                '☝️', '👍', '👎', '✊', '👊', '🤛', '🤜', '👏', '🙌', '👐', '🤲', '🤝', '🙏', '✍️', '💅', '🤳',
                '💪', '🦾', '🦵', '🦿', '🦶', '👂', '🦻', '👃', '🧠', '🦷', '🦴', '👀', '👁', '👅', '👄', '👶',
                '🧒', '👦', '👧', '🧑', '👱', '👨', '🧔', '👨‍🦰', '👨‍🦱', '👨‍🦳', '👨‍🦲', '👩', '👩‍🦰', '🧑‍🦰',
                '👩‍🦱', '🧑‍🦱', '👩‍🦳', '🧑‍🦳', '👩‍🦲', '🧑‍🦲', '👱‍♀️', '👱‍♂️', '🧓', '👴', '👵', '🙍', '🙎',
                '🙅', '🙆', '💁', '🙋', '🧏', '🙇', '🤦', '🤷', '👮', '🕵', '💂', '👷', '🤴', '👸', '👳', '👲',
                '🧕', '🤵', '👰', '🤰', '🤱', '👼', '🎅', '🤶', '🦸', '🦹', '🧙', '🧚', '🧛', '🧜', '🧝', '🧞',
                '🧟', '💆', '💇', '🚶', '🧍', '🧎', '🏃', '💃', '🕺', '🕴', '👯', '🧖', '🧗', '🤺', '🏇', '⛷',
                '🏂', '🏌', '🏄', '🚣', '🏊', '⛹', '🏋', '🚴', '🚵', '🤸', '🤼', '🤽', '🤾', '🤹', '🧘', '🛀',
                '🛌', '🧑‍🤝‍🧑', '👭', '👫', '👬', '💏', '👩‍❤️‍💋‍👨', '👨‍❤️‍💋‍👨', '👩‍❤️‍💋‍👩', '💑', '👩‍❤️‍👨',
                '👨‍❤️‍👨', '👩‍❤️‍👩', '👨‍👩‍👦', '👨‍👩‍👧', '👨‍👩‍👧‍👦', '👨‍👩‍👦‍👦', '👨‍👩‍👧‍👧', '👨‍👨‍👦', '👨‍👨‍👧',
                '👨‍👨‍👧‍👦', '👨‍👨‍👦‍👦', '👨‍👨‍👧‍👧', '👩‍👩‍👦', '👩‍👩‍👧', '👩‍👩‍👧‍👦', '👩‍👩‍👦‍👦', '👩‍👩‍👧‍👧', '🗣',
                '👤', '👥', '👣'
            ],
            "Animals & Nature": [
                '🙈', '🙉', '🙊', '🐒', '🦍', '🦧', '🐶', '🐕', '🦮', '🐕‍🦺', '🐩', '🐺', '🦊', '🦝', '🐱', '🐈',
                '🦁', '🐯', '🐅', '🐆', '🐴', '🐎', '🦄', '🦓', '🦌', '🐮', '🐂', '🐃', '🐄', '🐷', '🐖', '🐗',
                '🐽', '🐏', '🐑', '🐐', '🐪', '🐫', '🦙', '🦒', '🐘', '🦏', '🦛', '🐭', '🐁', '🐀', '🐹', '🐰',
                '🐇', '🐿', '🦔', '🦇', '🐻', '🐨', '🐼', '🦥', '🦦', '🦨', '🦘', '🦡', '🐾', '🦃', '🐔', '🐓',
                '🐣', '🐤', '🐥', '🐦', '🐧', '🕊', '🦅', '🦆', '🦢', '🦉', '🦩', '🦚', '🦜', '🐸', '🐊', '🐢',
                '🦎', '🐍', '🐲', '🐉', '🦕', '🦖', '🐳', '🐋', '🐬', '🐟', '🐠', '🐡', '🦈', '🐙', '🐚', '🐌',
                '🦋', '🐛', '🐜', '🐝', '🐞', '🦗', '🕷', '🕸', '🦂', '🦟', '🦠', '💐', '🌸', '💮', '🏵', '🌹',
                '🥀', '🌺', '🌻', '🌼', '🌷', '🌱', '🌲', '🌳', '🌴', '🌵', '🌾', '🌿', '☘️', '🍀', '🍁', '🍂',
                '🍃'
            ],
            "Food & Drink": [
                '🍇', '🍈', '🍉', '🍊', '🍋', '🍌', '🍍', '🥭', '🍎', '🍏', '🍐', '🍑', '🍒', '🍓', '🥝', '🍅',
                '🥥', '🥑', '🍆', '🥔', '🥕', '🌽', '🌶', '🥒', '🥬', '🥦', '🧄', '🧅', '🍄', '🥜', '🌰', '🍞',
                '🥐', '🥖', '🥨', '🥯', '🥞', '🧇', '🧀', '🍖', '🍗', '🥩', '🥓', '🍔', '🍟', '🍕', '🌭', '🥪',
                '🥙', '🧆', '🌮', '🌯', '🥗', '🥘', '🥫', '🍝', '🍜', '🍲', '🍛', '🍣', '🍱', '🥟', '🦪', '🍤',
                '🍙', '🍚', '🍘', '🍥', '🥠', '🥮', '🍢', '🍡', '🍧', '🍨', '🍦', '🥧', '🧁', '🍰', '🎂', '🍮',
                '🍭', '🍬', '🍫', '🍿', '🍩', '🍪', '🍯', '🍼', '🥛', '☕️', '🍵', '🍶', '🍾', '🍷', '🍸', '🍹',
                '🍺', '🍻', '🥂', '🥃', '🥤', '🧃', '🧉', '🧊', '🥢', '🍽', '🍴', '🥄'
            ],
            "Objects": [
                '⌚️', '📱', '📲', '💻', '⌨️', '🖥', '🖨', '🖱', '🖲', '🕹', '🗜', '💾', '💿', '📀', '📼', '📷',
                '📸', '📹', '🎥', '📽', '🎞', '📞', '☎️', '📟', '📠', '📺', '📻', '🎙', '🎚', '🎛', '🧭', '⏱',
                '⏲', '⏰', '🕰', '⌛️', '⏳', '📡', '🔋', '🔌', '💡', '🔦', '🕯', '🪔', '🧯', '🛢', '💸', '💵',
                '💴', '💶', '💷', '💰', '💳', '💎', '⚖️', '🧰', '🔧', '🔨', '⚒', '🛠', '⛏', '🔩', '⚙️', '🧱',
                '⛓', '🧲', '🔫', '💣', '🧨', '🪓', '🔪', '🗡', '⚔️', '🛡', '🚬', '⚰️', '⚱️', '🏺', '🔮', '📿',
                '🧿', '💈', '⚗️', '🔭', '🔬', '🕳', '🩹', '🩺', '💊', '💉', '🩸', '🧬', '🦠', '🧫', '🧪', '🌡',
                '🧹', '🧺', '🧻', '🚽', '🚰', '🚿', '🛁', '🛀', '🧼', '🪒', '🧽', '🧴', '🛎', '🔑', '🗝', '🚪',
                '🪑', '🛋', '🛏', '🛌', '🧸', '🖼', '🛍', '🛒', '🎁', '🎈', '🎏', '🎀', '🎊', '🎉', '🎎', '🏮',
                '🎐', '🧧', '✉️', '📩', '📨', '📧', '💌', '📮', '📪', '📫', '📬', '📭', '📦', '📯', '📥', '📤',
                '📜', '📃', '📑', '🧾', '📊', '📈', '📉', '🗒', '🗓', '📆', '📅', '🗑', '📇', '🗃', '🗳', '🗄',
                '📋', '📁', '📂', '🗂', '🗞', '📰', '📓', '📔', '📒', '📕', '📗', '📘', '📙', '📚', '📖', '🔖',
                '🧷', '🔗', '📎', '🖇', '📐', '📏', '🧮', '📌', '📍', '✂️', '🖊', '🖋', '✒️', '🖌', '🖍', '📝',
                '✏️', '🔍', '🔎', '🔏', '🔐', '🔒', '🔓'
            ]
        }
        
        for category, emoji_list in self.emojis.items():
            self.tabs.addTab(self._create_emoji_tab(emoji_list), category)

    def _create_emoji_tab(self, emoji_list):
        tab_widget = QWidget()
        layout = QGridLayout(tab_widget)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(tab_widget)
        
        col, row = 0, 0
        for emoji in emoji_list:
            button = QPushButton(emoji)
            button.setFixedSize(40, 40)
            button.setStyleSheet("font-size: 20px; border: none;")
            button.clicked.connect(lambda _, e=emoji: self.emoji_selected.emit(e))
            layout.addWidget(button, row, col)
            col += 1
            if col > 6:
                col = 0
                row += 1
        return scroll_area


class ModeSelectionDialog(QDialog):
   """Диалог для выбора режима работы."""
   def __init__(self, parent=None):
       super().__init__(parent)
       self.setWindowTitle("Выбор режима")
       self.layout = QVBoxLayout(self)
       self.result = None

       self.label = QLabel("Выберите режим работы мессенджера:")
       self.layout.addWidget(self.label)

       self.server_button = QPushButton("Клиент-Сервер")
       self.server_button.clicked.connect(lambda: self.set_mode('server'))
       self.layout.addWidget(self.server_button)

       self.p2p_internet_button = QPushButton("P2P (Интернет)")
       self.p2p_internet_button.clicked.connect(lambda: self.set_mode('p2p_internet'))
       self.layout.addWidget(self.p2p_internet_button)

       self.p2p_local_button = QPushButton("P2P (Локальная сеть)")
       self.p2p_local_button.clicked.connect(lambda: self.set_mode('p2p_local'))
       self.layout.addWidget(self.p2p_local_button)

   def set_mode(self, mode):
       self.result = mode
       self.accept()

class SettingsDialog(QDialog):
   """Диалог настроек аудиоустройств."""
   def __init__(self, config_manager, parent=None):
       super().__init__(parent)
       self.config_manager = config_manager
       self.setWindowTitle("Настройки")
       self.setFixedSize(400, 200)
       
       self.layout = QFormLayout(self)
       
       self.input_device_combo = QComboBox()
       self.output_device_combo = QComboBox()
       
       self.layout.addRow("Устройство ввода (микрофон):", self.input_device_combo)
       self.layout.addRow("Устройство вывода (динамики):", self.output_device_combo)
       
       self.save_button = QPushButton("Сохранить")
       self.save_button.clicked.connect(self.save_and_close)
       self.layout.addRow(self.save_button)
       
       self.populate_devices()
       self.load_settings()

   def populate_devices(self):
       p = pyaudio.PyAudio()
       for i in range(p.get_device_count()):
           info = p.get_device_info_by_index(i)
           if info.get('maxInputChannels') > 0:
               self.input_device_combo.addItem(info.get('name'), i)
           if info.get('maxOutputChannels') > 0:
               self.output_device_combo.addItem(info.get('name'), i)
       p.terminate()

   def load_settings(self):
       config = self.config_manager.load_config()
       input_idx = config.get('input_device_index')
       output_idx = config.get('output_device_index')

       if input_idx is not None:
           index = self.input_device_combo.findData(input_idx)
           if index != -1:
               self.input_device_combo.setCurrentIndex(index)
       
       if output_idx is not None:
           index = self.output_device_combo.findData(output_idx)
           if index != -1:
               self.output_device_combo.setCurrentIndex(index)

   def save_and_close(self):
       config = self.config_manager.load_config()
       config['input_device_index'] = self.input_device_combo.currentData()
       config['output_device_index'] = self.output_device_combo.currentData()
       self.config_manager.save_config(config)
       self.accept()

# --- Сетевые потоки ---

class ServerNetworkThread(QThread):
    """Поток для сетевого взаимодействия с центральным сервером."""
    message_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()

    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self.running = True

    def run(self):
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                response = json.loads(data.decode('utf-8'))
                self.message_received.emit(response)
            except (socket.error, json.JSONDecodeError, ConnectionResetError):
                if self.running:
                    self.running = False
        self.connection_lost.emit()

    def stop(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except (socket.error, OSError):
            pass
        self.sock.close()

# --- Поток для аудио ---

class AudioThread(QThread):
    """Поток для отправки и получения аудиоданных."""
    def __init__(self, udp_socket, peer_addr, input_device_index=None, output_device_index=None):
        super().__init__()
        self.udp_socket = udp_socket
        self.peer_addr = peer_addr
        self.running = True
        self.muted = False
        self.muted_addrs = set()
        self.audio = pyaudio.PyAudio()
        
        self.output_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                             rate=RATE, output=True,
                                             frames_per_buffer=CHUNK,
                                             output_device_index=output_device_index)
        
        self.input_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                            rate=RATE, input=True,
                                            frames_per_buffer=CHUNK,
                                            input_device_index=input_device_index)

    def run(self):
        send_thread = threading.Thread(target=self.send_audio)
        receive_thread = threading.Thread(target=self.receive_audio)
        
        send_thread.start()
        receive_thread.start()
        
        send_thread.join()
        receive_thread.join()

    def send_audio(self):
        while self.running:
            try:
                if self.muted:
                    data = b'\x00' * CHUNK
                else:
                    data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                self.udp_socket.sendto(data, self.peer_addr)
            except (IOError, OSError):
                break

    def receive_audio(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(CHUNK * 2)
                if addr not in self.muted_addrs:
                    self.output_stream.write(data)
            except (IOError, OSError):
                break

    def stop(self):
        self.running = False
        # Даем потокам немного времени на завершение
        self.join(500) 
        
        if self.input_stream.is_active():
            self.input_stream.stop_stream()
        self.input_stream.close()
        
        if self.output_stream.is_active():
            self.output_stream.stop_stream()
        self.output_stream.close()
        
        self.audio.terminate()
        # UDP сокет закрывается в hang_up_call
        print("Аудиопоток остановлен.")

    @pyqtSlot(bool)
    def set_muted(self, muted):
        self.muted = muted

    @pyqtSlot(set)
    def update_muted_addrs(self, addrs):
        self.muted_addrs = addrs

# --- Главное окно ---

class ChatWindow(QMainWindow):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.username = None
        self.p2p_manager = None
        self.network_thread = None
        self.sock = None
        self.plugin_manager = PluginManager(plugin_folder='VoiceChat/plugins')
        self.config_manager = ConfigManager()
        
        # Для звонков
        self.udp_socket = None
        self.audio_thread = None
        self.call_window = None
        self.current_peer_addr = None
        self.pending_call_target = None # Хранит имя пользователя, которому мы пытаемся позвонить
        self.current_theme = 'light'
        self.muted_peers = set()

        self.setup_ui()
        self.apply_theme()
        self.plugin_manager.discover_plugins()
        self.initialize_mode()

    def setup_ui(self):
        self.setWindowTitle(f"JustMessenger ({self.mode.replace('_', ' ').title()})")
        self.setGeometry(100, 100, 500, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        
        input_layout = QHBoxLayout()
        self.msg_entry = QLineEdit()
        self.msg_entry.returnPressed.connect(self.send_message)
        
        self.emoji_button = QPushButton("😀")
        self.emoji_button.setFixedSize(QSize(40, 28))
        self.emoji_button.setCheckable(True)
        self.emoji_button.clicked.connect(self.toggle_emoji_panel)

        self.send_button = QPushButton("Отправить")
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.msg_entry)
        input_layout.addWidget(self.emoji_button)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(self.chat_box)
        chat_layout.addLayout(input_layout)
        splitter.addWidget(chat_widget)

        users_widget = QWidget()
        users_layout = QVBoxLayout(users_widget)
        self.users_list = QListWidget()
        self.users_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.users_list.customContextMenuRequested.connect(self.show_user_context_menu)
        users_layout.addWidget(QLabel("Пользователи в сети:"))
        
        self.peer_search_widget = QWidget()
        peer_search_layout = QHBoxLayout(self.peer_search_widget)
        peer_search_layout.setContentsMargins(0, 0, 0, 0)
        self.peer_search_input = QLineEdit()
        self.peer_search_input.setPlaceholderText("Имя пользователя для поиска")
        self.peer_search_button = QPushButton("Найти")
        peer_search_layout.addWidget(self.peer_search_input)
        peer_search_layout.addWidget(self.peer_search_button)
        self.peer_search_widget.setVisible(False)
        users_layout.addWidget(self.peer_search_widget)

        users_layout.addWidget(self.users_list)
        
        self.status_button = QPushButton("Сменить статус")
        self.status_button.clicked.connect(self.change_status)
        users_layout.addWidget(self.status_button)
        self.status_button.setVisible(False)

        self.emoji_panel = EmojiPanel()
        self.emoji_panel.emoji_selected.connect(self.insert_emoji)
        self.emoji_panel.setVisible(False)
        users_layout.addWidget(self.emoji_panel)

        splitter.addWidget(users_widget)
        
        splitter.setSizes([350, 150])
        self.main_layout.addWidget(splitter)

        self.theme_button = QPushButton("Сменить тему")
        self.theme_button.clicked.connect(self.toggle_theme)
        
        self.settings_button = QPushButton("Настройки")
        self.settings_button.clicked.connect(self.open_settings)

        # Добавляем кнопки в один ряд
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.theme_button)
        button_layout.addWidget(self.settings_button)
        chat_layout.addLayout(button_layout)

    def initialize_mode(self):
        if self.mode == 'p2p_local':
            self.init_p2p_mode(p2p_mode='local')
        elif self.mode == 'p2p_internet':
            self.init_p2p_mode(p2p_mode='internet')
        elif self.mode == 'server':
            self.init_server_mode()

    def init_p2p_mode(self, p2p_mode='internet'):
        self.call_button = QPushButton("📞 Позвонить")
        self.call_button.clicked.connect(self.initiate_call)
        self.call_button.setEnabled(False)
        self.users_list.itemSelectionChanged.connect(lambda: self.call_button.setEnabled(True))
        
        # Добавляем кнопку в layout пользователей
        users_layout = self.main_layout.itemAt(0).widget().findChild(QVBoxLayout)
        if users_layout:
             users_layout.insertWidget(2, self.call_button)

        config_manager = ConfigManager()
        config = config_manager.load_config()
        self.username = config.get('username')

        if not self.username:
            text, ok = QInputDialog.getText(self, 'Имя пользователя', 'Введите ваше имя для сессии:')
            if ok and text:
                self.username = text
                config_manager.save_config({'username': self.username})
            else:
                sys.exit()
        
        self.setWindowTitle(f"JustMessenger ({self.mode.replace('_', ' ').title()}) - {self.username}")
        
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('', 0)) # Привязка к случайному порту

        self.p2p_manager = P2PManager(self.username, self.udp_socket, mode=p2p_mode)
        self.p2p_manager.peer_discovered.connect(self.add_peer)
        self.p2p_manager.peer_lost.connect(self.remove_peer)
        self.p2p_manager.message_received.connect(self.p2p_message_received)
        self.p2p_manager.incoming_p2p_call.connect(self.handle_p2p_call_request)
        self.p2p_manager.p2p_call_response.connect(self.handle_p2p_call_response)
        self.p2p_manager.p2p_hang_up.connect(self.handle_p2p_hang_up)
        self.p2p_manager.hole_punch_successful.connect(self.on_hole_punch_success)
        self.p2p_manager.start()

        if p2p_mode == 'local':
            self.add_message_to_box("Система: Вы в режиме P2P (Локальная сеть). Идет поиск других пользователей...")
            self.peer_search_widget.setVisible(False)
        else: # internet
            self.add_message_to_box("Система: Вы в режиме P2P (Интернет). Используйте поиск, чтобы найти пользователей.")
            self.peer_search_widget.setVisible(True)
            self.peer_search_button.clicked.connect(self.search_peer_in_dht)
            self.peer_search_input.returnPressed.connect(self.search_peer_in_dht)

    def init_server_mode(self):
        config_manager = ConfigManager()
        config = config_manager.load_config()
        self.username = config.get('username')

        if not self.username:
            text, ok = QInputDialog.getText(self, 'Имя пользователя', 'Введите ваше имя для сессии:')
            if ok and text:
                self.username = text
                config_manager.save_config({'username': self.username})
            else:
                sys.exit()

        self.setWindowTitle(f"JustMessenger (Сервер) - {self.username}")
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            
            self.network_thread = ServerNetworkThread(self.sock)
            self.network_thread.message_received.connect(self.handle_server_message)
            self.network_thread.connection_lost.connect(self.handle_connection_lost)
            self.network_thread.start()
            self.enable_input()
            self.add_message_to_box(f"Система: Подключено к серверу {HOST}:{PORT}")

        except ConnectionRefusedError:
            self.show_error(f"Не удалось подключиться к серверу {HOST}:{PORT}.")
            self.disable_input()

    def send_message(self):
        message = self.msg_entry.text()
        if not message: return

        continue_sending = self.plugin_manager.trigger_hook('before_send_message', message=message)
        if continue_sending is False:
            self.msg_entry.clear()
            return

        if self.mode.startswith('p2p'):
            self.p2p_manager.broadcast_message(message)
            self.add_message_to_box(f"Вы: {message}")
        elif self.mode == 'server':
            self.send_command_to_server({'type': 'text_message', 'sender': self.username, 'text': message})
            # Не отображаем свое сообщение, ждем его от сервера
        
        self.msg_entry.clear()

    def send_command_to_server(self, command_dict):
        if not self.sock: return
        try:
            self.sock.sendall(json.dumps(command_dict).encode('utf-8'))
        except socket.error as e:
            self.show_error(f"Ошибка отправки данных на сервер: {e}")
            self.handle_connection_lost()

    def handle_server_message(self, response):
        msg_type = response.get('type')
        
        if msg_type == 'user_list':
            self.update_user_list(response.get('users', []))
        elif msg_type == 'text_message':
            sender = response.get('sender', 'Сервер')
            text = response.get('text', '')
            self.add_message_to_box(f"{sender}: {text}")
        elif msg_type == 'server_broadcast':
            text = response.get('text', '')
            self.plugin_manager.trigger_hook('on_server_broadcast', text=text)
            self.add_message_to_box(f"СЕРВЕР: {text}")

    def p2p_message_received(self, sender, text):
        # This slot receives sender (str) and text (str) from the p2p_manager signal
        if sender != self.username:
            self.add_message_to_box(f"{sender}: {text}")

    def add_peer(self, username, address_info):
        if username == self.username: return
        items = self.users_list.findItems(username, Qt.MatchFlag.MatchExactly)
        if not items:
            self.users_list.addItem(username)
            self.add_message_to_box(f"Система: {username} в сети.")

    def remove_peer(self, username):
        items = self.users_list.findItems(username, Qt.MatchFlag.MatchExactly)
        for item in items:
            self.users_list.takeItem(self.users_list.row(item))
        self.add_message_to_box(f"Система: {username} вышел из сети.")

    def search_peer_in_dht(self):
        peer_name = self.peer_search_input.text()
        if peer_name and peer_name != self.username:
            self.add_message_to_box(f"Система: Ищем {peer_name} в DHT...")
            self.p2p_manager.find_peer(peer_name)
            self.peer_search_input.clear()

    # --- Логика звонков ---
    def initiate_call(self):
        if self.audio_thread:
            self.show_error("Вы уже в звонке.")
            return
            
        selected_items = self.users_list.selectedItems()
        if not selected_items:
            self.show_error("Выберите пользователя для звонка.")
            return
            
        target_username = selected_items[0].text()
        self.pending_call_target = target_username
        
        self.add_message_to_box(f"Система: Начинаем установку соединения с {target_username} (NAT Traversal)...")
        self.p2p_manager.initiate_hole_punch(target_username)

    def on_hole_punch_success(self, username, public_address):
        """Вызывается, когда hole punching удался."""
        # Эта функция вызывается и у звонящего, и у отвечающего.
        # Нужно четко разделить их логику.

        # Логика для инициатора звонка (того, кто нажал "Позвонить")
        if self.pending_call_target == username:
            self.add_message_to_box(f"Система: Соединение с {username} установлено по адресу {public_address}. Отправляем запрос на звонок...")
            self.current_peer_addr = (public_address[0], public_address[1])
            self.p2p_manager.send_p2p_call_request(username)
            return # Важно завершить выполнение здесь, чтобы не перейти к логике отвечающего

        # Логика для отвечающего на звонок (того, кто нажал "Да" в диалоге)
        # Флаг self.current_peer_addr == True устанавливается в handle_p2p_call_request
        if self.current_peer_addr is True:
             self.add_message_to_box(f"Система: Двустороннее соединение с {username} установлено. Отвечаем на звонок...")
             # Теперь у нас есть реальный адрес, сохраняем его
             self.current_peer_addr = (public_address[0], public_address[1])
             self.p2p_manager.send_p2p_call_response(username, 'accept')


    def handle_p2p_call_request(self, sender_username):
        if self.audio_thread:
            self.p2p_manager.send_p2p_call_response(sender_username, 'busy')
            return

        reply = QMessageBox.question(self, 'Входящий звонок',
                                     f'{sender_username} звонит вам. Ответить?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.add_message_to_box(f"Система: Принят звонок от {sender_username}. Начинаем NAT Traversal...")
            # Сохраняем имя, чтобы после успешного hole punch отправить 'accept'
            self.current_peer_addr = True # Флаг, что мы в процессе ответа
            self.p2p_manager.initiate_hole_punch(sender_username)
        else:
            self.p2p_manager.send_p2p_call_response(sender_username, 'reject')

    def handle_p2p_call_response(self, sender_username, response):
        if response == 'accept':
            if self.pending_call_target == sender_username:
                self.add_message_to_box(f"Система: {sender_username} принял ваш звонок. Начинаем разговор.")
                self.start_audio_stream(sender_username)
        elif response == 'reject':
            self.add_message_to_box(f"Система: {sender_username} отклонил ваш звонок.")
            self.pending_call_target = None
            self.current_peer_addr = None
        elif response == 'busy':
            self.add_message_to_box(f"Система: {sender_username} занят.")
            self.pending_call_target = None
            self.current_peer_addr = None

    def start_audio_stream(self, peer_username):
        if not self.current_peer_addr or not isinstance(self.current_peer_addr, tuple):
             self.show_error(f"Ошибка: Не удалось определить адрес для звонка с {peer_username}.")
             self.pending_call_target = None
             return

        config = self.config_manager.load_config()
        input_device_index = config.get('input_device_index')
        output_device_index = config.get('output_device_index')

        self.audio_thread = AudioThread(
            self.udp_socket,
            self.current_peer_addr,
            input_device_index=input_device_index,
            output_device_index=output_device_index
        )
        self.audio_thread.start()
        
        self.call_window = CallWindow(peer_username, self)
        self.call_window.hang_up_pressed.connect(self.hang_up_call)
        self.call_window.mute_toggled.connect(self.audio_thread.set_muted)
        self.call_window.show()
        self.pending_call_target = None # Сбрасываем, так как звонок начался

    def hang_up_call(self):
        if self.audio_thread:
            self.audio_thread.stop()
            self.audio_thread = None
            
            # Найти имя пользователя по адресу
            peer_username = self.p2p_manager.get_peer_username_by_addr(self.current_peer_addr)
            if peer_username:
                self.p2p_manager.send_p2p_hang_up(peer_username)

            self.add_message_to_box("Система: Звонок завершен.")
        
        if self.call_window:
            self.call_window.close()
            self.call_window = None
            
        self.current_peer_addr = None

    def handle_p2p_hang_up(self, sender_username):
        self.add_message_to_box(f"Система: {sender_username} завершил звонок.")
        if self.audio_thread:
            self.audio_thread.stop()
            self.audio_thread = None
        if self.call_window:
            self.call_window.close()
            self.call_window = None
        self.current_peer_addr = None

    # --- Вспомогательные функции ---
    def add_message_to_box(self, message):
        self.chat_box.append(message)

    def update_user_list(self, users):
        self.users_list.clear()
        for user in users:
            self.users_list.addItem(user)

    def toggle_emoji_panel(self, checked):
        self.emoji_panel.setVisible(checked)

    def open_emoji_panel(self):
        # This method is now obsolete, but kept for compatibility in case it's called elsewhere.
        # The new behavior is handled by toggle_emoji_panel.
        self.emoji_button.setChecked(not self.emoji_button.isChecked())
        self.toggle_emoji_panel(self.emoji_button.isChecked())

    def insert_emoji(self, emoji):
        current_text = self.msg_entry.text()
        self.msg_entry.setText(current_text + emoji)

    def change_status(self):
        # Заглушка
        self.add_message_to_box("Система: Функция смены статуса еще не реализована.")

    def toggle_theme(self):
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.apply_theme()

    def open_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        dialog.exec()

    def show_user_context_menu(self, position):
        item = self.users_list.itemAt(position)
        if not item:
            return
        
        username = item.text().split(' ')[0] # Убираем возможный статус "[Muted]"
        
        menu = QMenu()
        mute_action_text = "Включить звук" if username in self.muted_peers else "Выключить звук"
        mute_action = menu.addAction(mute_action_text)
        
        action = menu.exec(self.users_list.mapToGlobal(position))
        
        if action == mute_action:
            self.toggle_peer_mute(username)

    def toggle_peer_mute(self, username):
        if username in self.muted_peers:
            self.muted_peers.remove(username)
        else:
            self.muted_peers.add(username)
        
        # Обновляем отображение в списке
        for i in range(self.users_list.count()):
            item = self.users_list.item(i)
            peer_name = item.text().split(' ')[0]
            if peer_name == username:
                item.setText(f"{username} [Muted]" if username in self.muted_peers else username)
                break
        
        # Обновляем список замученных адресов в аудиопотоке
        if self.audio_thread:
            muted_addrs = set()
            for peer in self.muted_peers:
                if peer in self.p2p_manager.peers:
                    peer_data = self.p2p_manager.peers[peer]
                    addr = peer_data.get('public_addr') or (peer_data.get('local_ip'), 12346) # P2P_PORT
                    if addr:
                        muted_addrs.add(addr)
            self.audio_thread.update_muted_addrs(muted_addrs)

    def apply_theme(self):
        if self.current_theme == 'dark':
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2b2b2b;
                    color: #f0f0f0;
                }
                QTextEdit, QLineEdit {
                    background-color: #3c3f41;
                    color: #f0f0f0;
                    border: 1px solid #555;
                }
                QPushButton {
                    background-color: #555;
                    color: #f0f0f0;
                    border: 1px solid #666;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
                QListWidget {
                    background-color: #3c3f41;
                    color: #f0f0f0;
                }
            """)
        else: # light
            self.setStyleSheet("") # Сброс к стилю по умолчанию

    def show_error(self, message):
        QMessageBox.critical(self, "Ошибка", message)

    def enable_input(self):
        self.msg_entry.setEnabled(True)
        self.send_button.setEnabled(True)

    def disable_input(self):
        self.msg_entry.setEnabled(False)
        self.send_button.setEnabled(False)

    def handle_connection_lost(self):
        if self.network_thread:
            self.network_thread.stop()
            self.network_thread = None
        self.show_error("Соединение с сервером потеряно.")
        self.disable_input()
        self.update_user_list([])

    def closeEvent(self, event):
        if self.network_thread:
            self.network_thread.stop()
        if self.p2p_manager:
            self.p2p_manager.stop()
        if self.audio_thread:
            self.hang_up_call()
        if self.udp_socket:
            self.udp_socket.close()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Запускаем диалог выбора режима
    mode_dialog = ModeSelectionDialog()
    if mode_dialog.exec() == QDialog.DialogCode.Accepted:
        mode = mode_dialog.result
        if mode:
            window = ChatWindow(mode=mode)
            window.show()
            sys.exit(app.exec())
    else:
        # Пользователь закрыл диалог, ничего не делаем
        sys.exit(0)

if __name__ == '__main__':
    main()