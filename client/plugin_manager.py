import os
import importlib.util
import sys

class PluginManager:
    def __init__(self, plugin_folder='plugins'):
        self.plugin_folder = plugin_folder
        self.plugins = []
        self.hooks = {}

    def discover_plugins(self):
        """Находит и загружает плагины из указанной папки."""
        if not os.path.exists(self.plugin_folder):
            print(f"Plugin folder '{self.plugin_folder}' not found.")
            return

        for item in os.listdir(self.plugin_folder):
            item_path = os.path.join(self.plugin_folder, item)
            if os.path.isdir(item_path):
                self.load_plugin(item_path)

    def load_plugin(self, plugin_path):
        """Загружает отдельный плагин."""
        main_file = os.path.join(plugin_path, 'main.py')
        if not os.path.exists(main_file):
            return

        try:
            spec = importlib.util.spec_from_file_location(f"plugin.{os.path.basename(plugin_path)}", main_file)
            plugin_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(plugin_module)
            
            # Предполагается, что в плагине есть функция initialize()
            if hasattr(plugin_module, 'initialize'):
                plugin_instance = plugin_module.initialize(self)
                self.plugins.append(plugin_instance)
                print(f"Loaded plugin: {os.path.basename(plugin_path)}")

        except Exception as e:
            print(f"Failed to load plugin from {plugin_path}: {e}")

    def register_hook(self, hook_name, function):
        """Регистрирует функцию для определенного хука."""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        self.hooks[hook_name].append(function)

    def trigger_hook(self, hook_name, *args, **kwargs):
        """
        Вызывает все функции, зарегистрированные для хука.
        Если какая-либо из функций-обработчиков вернет False,
        то дальнейшее выполнение прерывается и возвращается False.
        """
        if hook_name in self.hooks:
            for function in self.hooks[hook_name]:
                result = function(*args, **kwargs)
                if result is False:
                    return False
        return True
