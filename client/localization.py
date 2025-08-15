# -*- coding: utf-8 -*-

translations = {
    'en': {
        # Mode Selection
        'mode_selection_title': "Mode Selection",
        'mode_selection_label': "Select the messenger's operating mode:",
        'mode_client_server': "Client-Server",
        'mode_p2p_internet': "P2P (Internet)",
        'mode_p2p_local': "P2P (Local Network)",

        # Username Input
        'username_dialog_title': "Username",
        'username_dialog_label': "Enter your name for the session:",

        # Main Window
        'window_title': "JustMessenger",
        'users_in_chat_label': "Users online:",
        'search_placeholder': "Username for search",
        'search_button': "Find",
        'send_button': "Send",
        'change_status_button': "Change Status",
        'call_button': "📞 Call",
        'change_theme_button': "Change Theme",
        'settings_button': "Settings",
        
        # Settings Dialog
        'settings_title': "Settings",
        'input_device_label': "Input device (microphone):",
        'output_device_label': "Output device (speakers):",
        'language_label': "Language:",
        'save_button': "Save",

        # Call Window
        'call_window_title': "Call with {peer_username}",
        'call_label': "In a call with {peer_username}...",
        'mute_button': "Mute",
        'unmute_button': "Unmute",
        'hang_up_button': "Hang Up",

        # Context Menus
        'user_ctx_menu_mute': "Mute",
        'user_ctx_menu_unmute': "Unmute",
        'message_ctx_menu_edit': "Edit Message",
        'message_ctx_menu_delete': "Delete Message",
        
        # Message Edit Dialog
        'edit_dialog_title': "Edit Message",
        'edit_dialog_label': "New text:",

        # System Messages
        'system_p2p_local_start': "System: You are in P2P (Local Network) mode. Searching for other users...",
        'system_p2p_internet_start': "System: You are in P2P (Internet) mode. Use search to find users.",
        'system_searching_for_peer': "System: Searching for {peer_name} in DHT...",
        'system_user_online': "System: {username} is online.",
        'system_user_offline': "System: {username} has left.",
        'system_connected_to_server': "System: Connected to server {host}:{port}",
        'system_connection_failed': "Failed to connect to server {host}:{port}.",
        'system_connection_lost': "Connection to the server has been lost.",
        'system_call_setup': "System: Establishing connection with {target_username} (NAT Traversal)...",
        'system_hole_punch_success_caller': "System: Connection with {username} established at {public_address}. Sending call request...",
        'system_hole_punch_success_callee': "System: Two-way connection with {username} established. Answering the call...",
        'system_incoming_call_prompt_title': "Incoming Call",
        'system_incoming_call_prompt_text': "{sender_username} is calling you. Answer?",
        'system_call_accepted_callee': "System: Call from {sender_username} accepted. Starting NAT Traversal...",
        'system_call_accepted_caller': "System: {sender_username} accepted your call. Starting conversation.",
        'system_call_rejected': "System: {sender_username} rejected your call.",
        'system_peer_busy': "System: {sender_username} is busy.",
        'system_call_ended': "System: Call ended.",
        'system_peer_ended_call': "System: {sender_username} ended the call.",
        'system_status_not_implemented': "System: Status change feature is not yet implemented.",
        'system_delete_not_implemented_server': "System: Deleting messages in 'server' mode is not yet implemented.",
        'system_edit_not_implemented_server': "System: Editing messages in 'server' mode is not yet implemented.",

        # Errors
        'error_title': "Error",
        'edited_suffix': "edited",
        'error_already_in_call': "You are already in a call.",
        'error_select_user_for_call': "Select a user to call.",
        'error_failed_to_determine_address': "Error: Failed to determine address for the call with {peer_username}.",
        'error_send_data_to_server': "Error sending data to server: {e}",
    },
    'ru': {
        # Mode Selection
        'mode_selection_title': "Выбор режима",
        'mode_selection_label': "Выберите режим работы мессенджера:",
        'mode_client_server': "Клиент-Сервер",
        'mode_p2p_internet': "P2P (Интернет)",
        'mode_p2p_local': "P2P (Локальная сеть)",

        # Username Input
        'username_dialog_title': "Имя пользователя",
        'username_dialog_label': "Введите ваше имя для сессии:",

        # Main Window
        'window_title': "JustMessenger",
        'users_in_chat_label': "Пользователи в сети:",
        'search_placeholder': "Имя пользователя для поиска",
        'search_button': "Найти",
        'send_button': "Отправить",
        'change_status_button': "Сменить статус",
        'call_button': "📞 Позвонить",
        'change_theme_button': "Сменить тему",
        'settings_button': "Настройки",

        # Settings Dialog
        'settings_title': "Настройки",
        'input_device_label': "Устройство ввода (микрофон):",
        'output_device_label': "Устройство вывода (динамики):",
        'language_label': "Язык:",
        'save_button': "Сохранить",

        # Call Window
        'call_window_title': "Звонок с {peer_username}",
        'call_label': "Идет разговор с {peer_username}...",
        'mute_button': "Выключить микрофон",
        'unmute_button': "Включить микрофон",
        'hang_up_button': "Завершить звонок",

        # Context Menus
        'user_ctx_menu_mute': "Выключить звук",
        'user_ctx_menu_unmute': "Включить звук",
        'message_ctx_menu_edit': "Редактировать сообщение",
        'message_ctx_menu_delete': "Удалить сообщение",

        # Message Edit Dialog
        'edit_dialog_title': "Редактировать сообщение",
        'edit_dialog_label': "Новый текст:",

        # System Messages
        'system_p2p_local_start': "Система: Вы в режиме P2P (Локальная сеть). Идет поиск других пользователей...",
        'system_p2p_internet_start': "Система: Вы в режиме P2P (Интернет). Используйте поиск, чтобы найти пользователей.",
        'system_searching_for_peer': "Система: Ищем {peer_name} в DHT...",
        'system_user_online': "Система: {username} в сети.",
        'system_user_offline': "Система: {username} вышел из сети.",
        'system_connected_to_server': "Система: Подключено к серверу {host}:{port}",
        'system_connection_failed': "Не удалось подключиться к серверу {host}:{port}.",
        'system_connection_lost': "Соединение с сервером потеряно.",
        'system_call_setup': "Система: Начинаем установку соединения с {target_username} (NAT Traversal)...",
        'system_hole_punch_success_caller': "Система: Соединение с {username} установлено по адресу {public_address}. Отправляем запрос на звонок...",
        'system_hole_punch_success_callee': "Система: Двустороннее соединение с {username} установлено. Отвечаем на звонок...",
        'system_incoming_call_prompt_title': "Входящий звонок",
        'system_incoming_call_prompt_text': "{sender_username} звонит вам. Ответить?",
        'system_call_accepted_callee': "Система: Принят звонок от {sender_username}. Начинаем NAT Traversal...",
        'system_call_accepted_caller': "Система: {sender_username} принял ваш звонок. Начинаем разговор.",
        'system_call_rejected': "Система: {sender_username} отклонил ваш звонок.",
        'system_peer_busy': "Система: {sender_username} занят.",
        'system_call_ended': "Система: Звонок завершен.",
        'system_peer_ended_call': "Система: {sender_username} завершил звонок.",
        'system_status_not_implemented': "Система: Функция смены статуса еще не реализована.",
        'system_delete_not_implemented_server': "Система: Удаление сообщений в режиме 'сервер' еще не реализовано.",
        'system_edit_not_implemented_server': "Система: Редактирование сообщений в режиме 'сервер' еще не реализовано.",

        # Errors
        'error_title': "Ошибка",
        'edited_suffix': "изменено",
        'error_already_in_call': "Вы уже в звонке.",
        'error_select_user_for_call': "Выберите пользователя для звонка.",
        'error_failed_to_determine_address': "Ошибка: Не удалось определить адрес для звонка с {peer_username}.",
        'error_send_data_to_server': "Ошибка отправки данных на сервер: {e}",
    }
}

class Translator:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.language = 'en' # Default language
        self.load_language()

    def load_language(self):
        config = self.config_manager.load_config()
        self.language = config.get('language', 'en')

    def set_language(self, lang_code):
        if lang_code in translations:
            self.language = lang_code
            config = self.config_manager.load_config()
            config['language'] = lang_code
            self.config_manager.save_config(config)

    def get(self, key, default=None, **kwargs):
        """
        Получает переведенную строку по ключу.
        Поддерживает форматирование с помощью kwargs.
        Пример: tr.get('call_window_title', peer_username='John')
        """
        # Сначала пытаемся получить перевод для текущего языка
        template = translations.get(self.language, {}).get(key)

        # Если ключ не найден, пытаемся получить его из английского языка (fallback)
        if template is None:
            template = translations.get('en', {}).get(key)

        # Если ключ так и не найден, используем значение по умолчанию или сам ключ
        if template is None:
            if default is not None:
                template = default
            else:
                template = f"[{key}]"
        
        try:
            return template.format(**kwargs)
        except KeyError as e:
            # В случае, если для форматирования не хватает ключа
            print(f"Localization key error for '{key}': missing format key {e}")
            return template
