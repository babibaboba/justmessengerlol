import sys
import socket
import threading
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget, QMessageBox,
                             QDialog, QLabel, QFormLayout, QListWidget, QHBoxLayout, QSplitter,
                             QInputDialog, QGridLayout)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt6.QtGui import QMovie
import pyaudio

# Проверяем, существуют ли файлы, и импортируем их
try:
    from config_manager import ConfigManager
    from p2p_manager import P2PManager
except ImportError:
    print("Ошибка: Не найдены модули config_manager.py или p2p_manager.py")
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

    def __init__(self, peer_username, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Звонок с {peer_username}")
        self.setFixedSize(300, 150)
        
        self.layout = QVBoxLayout(self)
        self.label = QLabel(f"Идет разговор с {peer_username}...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hang_up_button = QPushButton("Завершить звонок")
        
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.hang_up_button)
        
        self.hang_up_button.clicked.connect(self.hang_up_pressed.emit)
        self.hang_up_pressed.connect(self.accept) # Закрыть окно при нажатии

class EmojiPanel(QDialog):
    """Панель для выбора эмодзи."""
    emoji_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выберите эмодзи")
        self.setFixedSize(300, 200)
        
        self.layout = QGridLayout(self)
        
        # Простой набор эмодзи для примера
        emojis = [
            '😀', '😂', '😍', '🤔', '👍', '👎', '❤️', '🔥',
            '🚀', '🎉', '👋', '😢', '😠', '🙏', '💻', '🍕'
        ]
        
        row, col = 0, 0
        for emoji in emojis:
            button = QPushButton(emoji)
            button.setFixedSize(40, 40)
            button.setStyleSheet("font-size: 20px;")
            button.clicked.connect(lambda _, e=emoji: self.select_emoji(e))
            self.layout.addWidget(button, row, col)
            col += 1
            if col > 5:
                col = 0
                row += 1
                
    def select_emoji(self, emoji):
        self.emoji_selected.emit(emoji)
        self.accept()

class GifPanel(QDialog):
   """Панель для выбора GIF."""
   gif_selected = pyqtSignal(str)

   def __init__(self, parent=None):
       super().__init__(parent)
       self.setWindowTitle("Выберите GIF")
       self.setFixedSize(400, 300)
       
       self.layout = QGridLayout(self)
       
       # TODO: Загружать гифки из сети или локально
       gifs = ["gif1.gif", "gif2.gif"] # Заглушки
       
       row, col = 0, 0
       for gif_path in gifs:
           label = QLabel()
           movie = QMovie(gif_path)
           label.setMovie(movie)
           movie.start()
           
           button = QPushButton("Выбрать")
           button.clicked.connect(lambda _, p=gif_path: self.select_gif(p))
           
           container = QWidget()
           container_layout = QVBoxLayout(container)
           container_layout.addWidget(label)
           container_layout.addWidget(button)
           
           self.layout.addWidget(container, row, col)
           col += 1
           if col > 2:
               col = 0
               row += 1

   def select_gif(self, gif_path):
       self.gif_selected.emit(gif_path)
       self.accept()

class ModeSelectionDialog(QDialog):
    """Диалог для выбора режима P2P или Клиент-Сервер."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор режима")
        self.layout = QVBoxLayout(self)
        self.result = None

        self.label = QLabel("Выберите режим работы мессенджера:")
        self.layout.addWidget(self.label)

        self.server_button = QPushButton("Клиент-Сервер (Интернет)")
        self.server_button.clicked.connect(lambda: self.set_mode('server'))
        self.layout.addWidget(self.server_button)

        self.p2p_button = QPushButton("P2P (Локальная сеть)")
        self.p2p_button.clicked.connect(lambda: self.set_mode('p2p'))
        self.layout.addWidget(self.p2p_button)

    def set_mode(self, mode):
        self.result = mode
        self.accept()

class LoginDialog(QDialog):
    """Диалоговое окно для входа и регистрации в серверном режиме."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход")
        self.layout = QFormLayout(self)

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.layout.addRow("Имя пользователя:", self.username_input)
        self.layout.addRow("Пароль:", self.password_input)

        self.login_button = QPushButton("Войти")
        self.register_button = QPushButton("Регистрация")
        
        self.layout.addWidget(self.login_button)
        self.layout.addWidget(self.register_button)

        self.login_button.clicked.connect(self.accept)
        # Отправляем кастомный код, чтобы отличить от простого закрытия
        self.register_button.clicked.connect(lambda: self.done(2)) 

    def get_credentials(self):
        return self.username_input.text(), self.password_input.text()

# --- Сетевые потоки ---

class ServerNetworkThread(QThread):
    """Поток для сетевого взаимодействия с центральным сервером."""
    response_received = pyqtSignal(dict)
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
                self.response_received.emit(response)
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
    def __init__(self, udp_socket, peer_addr):
        super().__init__()
        self.udp_socket = udp_socket
        self.peer_addr = peer_addr
        self.running = True
        self.audio = pyaudio.PyAudio()
        
        self.output_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                             rate=RATE, output=True,
                                             frames_per_buffer=CHUNK)
        
        self.input_stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                            rate=RATE, input=True,
                                            frames_per_buffer=CHUNK)

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
                data = self.input_stream.read(CHUNK)
                self.udp_socket.sendto(data, self.peer_addr)
            except (IOError, OSError):
                break

    def receive_audio(self):
        while self.running:
            try:
                data, _ = self.udp_socket.recvfrom(CHUNK * 2)
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
        self.udp_socket.close()
        print("Аудиопоток остановлен.")

# --- Главное окно ---

class ChatWindow(QMainWindow):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.username = None
        self.network_thread = None
        self.p2p_manager = None
        self.sock = None
        
        # Для звонков
        self.udp_socket = None
        self.audio_thread = None
        self.call_window = None
        self.current_peer_addr = None # Адрес для P2P звонка
        self.current_theme = 'light'

        self.setup_ui()
        self.apply_theme() # Применяем тему по умолчанию
        self.initialize_mode()

    def setup_ui(self):
        """Настраивает основной интерфейс окна."""
        self.setWindowTitle(f"Мессенджер ({'P2P' if self.mode == 'p2p' else 'Клиент-Сервер'})")
        self.setGeometry(100, 100, 500, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        
        # Layout для поля ввода и кнопок
        input_layout = QHBoxLayout()
        self.msg_entry = QLineEdit()
        self.msg_entry.returnPressed.connect(self.send_message)
        
        self.emoji_button = QPushButton("😀")
        self.emoji_button.setFixedSize(QSize(40, 28))
        self.emoji_button.clicked.connect(self.open_emoji_panel)

        self.gif_button = QPushButton("GIF")
        self.gif_button.setFixedSize(QSize(40, 28))
        self.gif_button.clicked.connect(self.open_gif_panel)

        self.send_button = QPushButton("Отправить")
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.msg_entry)
        input_layout.addWidget(self.emoji_button)
        input_layout.addWidget(self.gif_button)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(self.chat_box)
        chat_layout.addLayout(input_layout)
        splitter.addWidget(chat_widget)

        users_widget = QWidget()
        users_layout = QVBoxLayout(users_widget)
        self.users_list = QListWidget()
        users_layout.addWidget(QLabel("Пользователи в сети:"))
        users_layout.addWidget(self.users_list)
        
        self.status_button = QPushButton("Сменить статус")
        self.status_button.clicked.connect(self.change_status)
        users_layout.addWidget(self.status_button)
        self.status_button.setVisible(False) # Скрываем до входа в систему

        splitter.addWidget(users_widget)
        
        splitter.setSizes([350, 150])
        self.main_layout.addWidget(splitter)

        # Добавляем кнопку смены темы в основной layout
        self.theme_button = QPushButton("Сменить тему")
        self.theme_button.clicked.connect(self.toggle_theme)
        chat_layout.addWidget(self.theme_button)

    def initialize_mode(self):
        """Инициализирует логику в зависимости от выбранного режима."""
        if self.mode == 'p2p':
            self.init_p2p_mode()
        else:
            self.init_server_mode()

    def init_p2p_mode(self):
        """Настройка для P2P режима."""
        # Добавляем кнопку звонка
        self.call_button = QPushButton("📞 Позвонить")
        self.call_button.clicked.connect(self.initiate_call)
        self.call_button.setEnabled(False)
        self.users_list.itemSelectionChanged.connect(lambda: self.call_button.setEnabled(True))
        self.main_layout.itemAt(1).widget().layout().insertWidget(0, self.call_button)

        config_manager = ConfigManager()
        config = config_manager.load_config()
        self.username = config.get('username')

        if not self.username:
            text, ok = QInputDialog.getText(self, 'Имя пользователя', 'Введите ваше имя для P2P сессии:')
            if ok and text:
                self.username = text
                config_manager.save_config({'username': self.username})
            else:
                sys.exit()
        
        self.setWindowTitle(f"Мессенджер (P2P) - {self.username}")
        self.p2p_manager = P2PManager(self.username)
        self.p2p_manager.peer_discovered.connect(self.add_peer)
        self.p2p_manager.peer_lost.connect(self.remove_peer)
        self.p2p_manager.message_received.connect(self.p2p_message_received)
        # Подключаем новые сигналы звонков
        self.p2p_manager.incoming_p2p_call.connect(self.handle_p2p_call_request)
        self.p2p_manager.p2p_call_response.connect(self.handle_p2p_call_response)
        self.p2p_manager.p2p_hang_up.connect(self.handle_p2p_hang_up)
        self.p2p_manager.start()
        self.add_message_to_box("Система: Вы в режиме P2P. Идет поиск других пользователей...")

    def init_server_mode(self):
        """Настройка для Клиент-Серверного режима."""
        self.users_list.setVisible(True)
        self.call_button = QPushButton("📞 Позвонить")
        self.call_button.clicked.connect(self.initiate_call)
        self.call_button.setEnabled(False)
        self.users_list.itemSelectionChanged.connect(lambda: self.call_button.setEnabled(True))
        
        # Вставляем кнопку перед списком пользователей
        self.main_layout.itemAt(1).widget().layout().insertWidget(0, self.call_button)

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            
            self.network_thread = ServerNetworkThread(self.sock)
            self.network_thread.response_received.connect(self.handle_server_response)
            self.network_thread.connection_lost.connect(self.handle_connection_lost)
            self.network_thread.start()

            self.show_login_dialog()
        except ConnectionRefusedError:
            self.show_error("Не удалось подключиться к серверу.")
            self.disable_input()

    def show_login_dialog(self):
        """Показывает диалог входа/регистрации и обрабатывает результат."""
        dialog = LoginDialog(self)
        result = dialog.exec()
        username, password = dialog.get_credentials()

        if not username or not password:
            self.close()
            return

        if result == QDialog.DialogCode.Accepted:
            self.send_command('login', {'username': username, 'password': password})
        elif result == 2:
            self.send_command('register', {'username': username, 'password': password})
            # После попытки регистрации снова покажем окно для входа
            QMessageBox.information(self, "Регистрация", "Запрос на регистрацию отправлен. Теперь попробуйте войти.")
            self.show_login_dialog()

    def send_command(self, command, payload):
        """Отправляет JSON-команду на сервер."""
        if not self.sock: return
        request = {'command': command, 'payload': payload}
        try:
            self.sock.sendall(json.dumps(request).encode('utf-8'))
        except socket.error:
            self.handle_connection_lost()

    def handle_server_response(self, response):
        """Обрабатывает ответы от сервера."""
        status = response.get('status')
        data = response.get('data', '')

        if status == 'login_success':
            self.username = data.get('username')
            self.setWindowTitle(f"Мессенджер - {self.username}")
            self.add_message_to_box("Система: Вы успешно вошли в систему.")
            self.enable_input()
            self.status_button.setVisible(True) # Показываем кнопку смены статуса
            # Список пользователей придет через broadcast_user_list_update от сервера
        
        elif status == 'user_list':
            self.update_user_list(data.get('users', []))

        elif status == 'new_message':
           self.display_new_message(data)

        elif status == 'incoming_call':
            from_user = data.get('from_user')
            caller_addr = tuple(data.get('caller_addr')) # (ip, port)
            
            reply = QMessageBox.question(self, 'Входящий звонок',
                                         f"Вам звонит {from_user}. Принять?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.udp_socket = self.create_udp_socket()
                if not self.udp_socket: return

                _, udp_port = self.udp_socket.getsockname()
                self.send_command('call_response', {
                    'to_user': from_user,
                    'answer': 'accept',
                    'udp_port': udp_port
                })
                self.start_call_session(from_user, caller_addr)
            else:
                self.send_command('call_response', {'to_user': from_user, 'answer': 'reject'})

        elif status == 'call_response':
            from_user = data.get('from_user')
            answer = data.get('answer')
            if answer == 'accept':
                callee_addr = tuple(data.get('callee_addr'))
                self.add_message_to_box(f"Система: {from_user} принял ваш звонок. Соединение...")
                self.start_call_session(from_user, callee_addr)
            else:
                self.add_message_to_box(f"Система: {from_user} отклонил ваш звонок.")
                self.hang_up_call() # Закрываем наш UDP сокет, если он был создан

        elif status == 'status_update_success':
            self.add_message_to_box(f"Система: Ваш статус обновлен на {data.get('status_emoji')}")

        elif status == 'error':
            self.show_error(str(data))
        elif status == 'info':
            self.add_message_to_box(f"Сервер: {data}")

    def send_message(self):
        message = self.msg_entry.text()
        if not message: return

        if self.mode == 'p2p':
            self.p2p_manager.broadcast_message(message)
            self.add_message_to_box(f"Вы: {message}")
        else: # server mode
            self.send_command('send_message', {'type': 'text', 'text': message})
            self.add_message_to_box(f"Вы: {message}")
            
        self.msg_entry.clear()

    def initiate_call(self):
        """Начинает звонок выбранному пользователю в зависимости от режима."""
        selected_items = self.users_list.selectedItems()
        if not selected_items: return
        
        # Извлекаем имя пользователя, игнорируя статус и "(Вы)"
        full_text = selected_items[0].text()
        clean_text = full_text.split(' (Вы)')[0]
        target_user = clean_text.split(' ', 1)[1] if ' ' in clean_text else clean_text

        if target_user == self.username:
            self.show_error("Вы не можете позвонить самому себе.")
            return
        
        self.udp_socket = self.create_udp_socket()
        if not self.udp_socket: return

        _, udp_port = self.udp_socket.getsockname()
        self.add_message_to_box(f"Система: Выполняется звонок пользователю {target_user}...")

        if self.mode == 'p2p':
            # В P2P режиме IP адрес уже известен, отправляем только порт
            self.p2p_manager.send_peer_command(target_user, 'p2p_call_request', {'udp_port': udp_port})
        else: # server mode
            self.send_command('call_request', {'to_user': target_user, 'udp_port': udp_port})

    def start_call_session(self, peer_username, peer_addr):
        """Начинает аудиопоток и открывает окно звонка."""
        if self.audio_thread and self.audio_thread.isRunning():
            self.add_message_to_box("Система: Вы уже в звонке.")
            return

        self.add_message_to_box(f"Система: Начало сеанса связи с {peer_username} по адресу {peer_addr}.")
        
        try:
            self.audio_thread = AudioThread(self.udp_socket, peer_addr)
            self.audio_thread.start()

            self.call_window = CallWindow(peer_username, self)
            self.call_window.hang_up_pressed.connect(self.hang_up_call)
            self.call_window.show()
        except Exception as e:
            self.show_error(f"Ошибка инициализации аудио: {e}")
            self.hang_up_call()

    def hang_up_call(self, notify_peer=True):
        """Завершает текущий звонок."""
        # Уведомляем другого пользователя о завершении, если мы инициатор
        if self.mode == 'p2p' and notify_peer and self.call_window:
            target_user = self.call_window.windowTitle().replace("Звонок с ", "")
            self.p2p_manager.send_peer_command(target_user, 'p2p_hang_up', {})

        if self.audio_thread:
            self.audio_thread.stop()
            self.audio_thread.wait()
            self.audio_thread = None
        
        if self.call_window:
            self.call_window.close()
            self.call_window = None
        
        self.udp_socket = None
        self.current_peer_addr = None
        self.add_message_to_box("Система: Звонок завершен.")

    def create_udp_socket(self):
        """Создает и возвращает UDP сокет."""
        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.bind(('', 0)) # Привязать к любому доступному порту
            return udp_sock
        except socket.error as e:
            self.show_error(f"Не удалось создать UDP сокет: {e}")
            return None

    def update_user_list(self, users_data):
       """Обновляет список пользователей в GUI, включая их статусы."""
       self.users_list.clear()
       # Сначала добавляем себя в список
       my_status = '😀' # Статус по умолчанию, если что-то пойдет не так
       for user_info in users_data:
           if user_info['username'] == self.username:
               my_status = user_info['status']
               break
       self.users_list.addItem(f"{my_status} {self.username} (Вы)")

       # Затем добавляем остальных
       for user_info in users_data:
           if user_info['username'] != self.username:
               self.users_list.addItem(f"{user_info['status']} {user_info['username']}")

    # --- Слоты и обработчики ---

    def open_emoji_panel(self):
        panel = EmojiPanel(self)
        panel.emoji_selected.connect(self.insert_emoji)
        # Позиционируем панель рядом с кнопкой
        button_pos = self.emoji_button.mapToGlobal(self.emoji_button.rect().bottomLeft())
        panel.move(button_pos)
        panel.exec()

    def insert_emoji(self, emoji):
        self.msg_entry.insert(emoji)
        self.msg_entry.setFocus()

    def add_message_to_box(self, message):
       # Проверяем, является ли сообщение HTML-тегом img
       if message.strip().startswith('<img'):
           # Для GIF-ов и изображений просто вставляем HTML
           self.chat_box.append(message)
       else:
           # Для обычного текста экранируем HTML-символы
           self.chat_box.append(message.replace('&', '&').replace('<', '<').replace('>', '>'))

    def display_new_message(self, data):
       """Отображает входящее сообщение в чате (текст или GIF)."""
       sender = data.get('sender', 'Система')
       msg_type = data.get('type', 'text')

       if msg_type == 'text':
           text = data.get('text', '')
           self.add_message_to_box(f"<b>{sender}:</b> {text}")
       elif msg_type == 'gif':
           gif_path = data.get('gif_path')
           if gif_path:
               self.add_message_to_box(f"<b>{sender}</b> отправил GIF:")
               # Используем HTML для отображения GIF
               self.add_message_to_box(f'<img src="{gif_path}" width="150" />')

    def open_gif_panel(self):
       """Открывает панель выбора GIF."""
       panel = GifPanel(self)
       panel.gif_selected.connect(self.send_gif)
       button_pos = self.gif_button.mapToGlobal(self.gif_button.rect().bottomLeft())
       panel.move(button_pos)
       panel.exec()

    def send_gif(self, gif_path):
       """Отправляет GIF как сообщение."""
       if self.mode == 'server':
           self.send_command('send_message', {'type': 'gif', 'gif_path': gif_path})
       elif self.mode == 'p2p':
           # TODO: Реализовать P2P отправку GIF (потребует передачи файла)
           self.add_message_to_box("<i>Отправка GIF в P2P режиме пока не реализована.</i>")
           return
       
       # Локальное отображение отправленного GIF
       self.add_message_to_box(f"<b>Вы</b> отправили GIF:")
       self.add_message_to_box(f'<img src="{gif_path}" width="150" />')

    def change_status(self):
       """Открывает панель эмодзи для смены статуса."""
       panel = EmojiPanel(self)
       panel.emoji_selected.connect(self.set_new_status)
       button_pos = self.status_button.mapToGlobal(self.status_button.rect().bottomLeft())
       panel.move(button_pos)
       panel.exec()

    def set_new_status(self, emoji):
       """Отправляет команду на сервер для обновления статуса."""
       if self.mode == 'server':
           self.send_command('set_status', {'status_emoji': emoji})

    def p2p_message_received(self, username, text):
        self.add_message_to_box(f"{username}: {text}")

    # --- Обработчики P2P звонков ---

    def handle_p2p_call_request(self, from_user, payload):
        """Обработка входящего P2P звонка."""
        udp_port = payload.get('udp_port')
        peer_ip = self.p2p_manager.peers.get(from_user)[0]
        self.current_peer_addr = (peer_ip, udp_port)

        reply = QMessageBox.question(self, 'Входящий P2P звонок',
                                     f"Вам звонит {from_user}. Принять?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.udp_socket = self.create_udp_socket()
            if not self.udp_socket: return
            
            _, my_udp_port = self.udp_socket.getsockname()
            self.p2p_manager.send_peer_command(from_user, 'p2p_call_response', {
                'answer': 'accept',
                'udp_port': my_udp_port
            })
            self.start_call_session(from_user, self.current_peer_addr)
        else:
            self.p2p_manager.send_peer_command(from_user, 'p2p_call_response', {'answer': 'reject'})
            self.current_peer_addr = None

    def handle_p2p_call_response(self, from_user, payload):
        """Обработка ответа на P2P звонок."""
        answer = payload.get('answer')
        if answer == 'accept':
            udp_port = payload.get('udp_port')
            peer_ip = self.p2p_manager.peers.get(from_user)[0]
            self.current_peer_addr = (peer_ip, udp_port)
            
            self.add_message_to_box(f"Система: {from_user} принял ваш звонок. Соединение...")
            self.start_call_session(from_user, self.current_peer_addr)
        else:
            self.add_message_to_box(f"Система: {from_user} отклонил ваш звонок.")
            self.hang_up_call(notify_peer=False)

    def handle_p2p_hang_up(self, from_user):
        """Обработка завершения звонка со стороны другого пира."""
        self.add_message_to_box(f"Система: {from_user} завершил звонок.")
        self.hang_up_call(notify_peer=False)

    def handle_connection_lost(self):
        self.add_message_to_box("Система: Соединение с сервером потеряно.")
        self.disable_input()

    def add_peer(self, username, address):
        self.add_message_to_box(f"Система: {username} теперь в сети.")
        self.users_list.addItem(username)

    def remove_peer(self, username):
        self.add_message_to_box(f"Система: {username} покинул сеть.")
        items = self.users_list.findItems(username, Qt.MatchFlag.MatchExactly)
        for item in items:
            self.users_list.takeItem(self.users_list.row(item))

    def enable_input(self):
        self.msg_entry.setEnabled(True)
        self.send_button.setEnabled(True)

    def disable_input(self):
        self.msg_entry.setEnabled(False)
        self.send_button.setEnabled(False)

    def show_error(self, message):
        QMessageBox.critical(self, "Ошибка", message)

    def toggle_theme(self):
       """Переключает между светлой и темной темой."""
       self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
       self.apply_theme()

    def apply_theme(self):
       """Применяет выбранную тему к приложению."""
       if self.current_theme == 'dark':
           self.setStyleSheet("""
               QWidget {
                   background-color: #2b2b2b;
                   color: #ffffff;
                   border: 1px solid #4f4f4f;
               }
               QMainWindow, QDialog {
                   background-color: #2b2b2b;
               }
               QTextEdit, QLineEdit, QListWidget {
                   background-color: #3c3c3c;
                   color: #ffffff;
                   border: 1px solid #555555;
               }
               QPushButton {
                   background-color: #555555;
                   color: #ffffff;
                   border: 1px solid #666666;
                   padding: 5px;
               }
               QPushButton:hover {
                   background-color: #666666;
               }
               QPushButton:pressed {
                   background-color: #777777;
               }
               QLabel {
                   border: none;
               }
           """)
       else: # light theme
           self.setStyleSheet("") # Сбрасываем на стиль по умолчанию

    def closeEvent(self, event):
        self.hang_up_call() # Завершаем звонок, если он активен
        if self.network_thread:
            self.network_thread.stop()
        if self.p2p_manager:
            self.p2p_manager.stop()
        event.accept()

# --- Точка входа ---

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    mode_dialog = ModeSelectionDialog()
    if mode_dialog.exec():
        mode = mode_dialog.result
        window = ChatWindow(mode)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)