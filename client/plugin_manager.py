import os
import importlib
import inspect
import sys

class PluginManager:
    """
    Manages the discovery, loading, and lifecycle of plugins.
    """
    def __init__(self, app):
        self.app = app
        self.plugins = []
        # Correctly determine the plugins directory relative to this file's location
        self.plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir)
        # Add plugins directory to Python path to allow direct imports
        if self.plugins_dir not in sys.path:
            sys.path.insert(0, self.plugins_dir)


    def discover_and_load_plugins(self):
        """Finds and loads all plugins from the plugins directory."""
        print(f"Discovering plugins in: {self.plugins_dir}")
        for item in os.listdir(self.plugins_dir):
            if item.endswith('_plugin.py'):
                module_name = item[:-3]
                self._load_plugin_from_module(module_name)
        
        # Initialize loaded plugins after all have been loaded
        for plugin_instance in self.plugins:
            try:
                plugin_instance.initialize()
            except Exception as e:
                print(f"Error initializing plugin {plugin_instance.__class__.__name__}: {e}")


    def _load_plugin_from_module(self, module_name):
        try:
            # We can import directly since the path is in sys.path
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module):
                # Load classes that inherit from BasePlugin and are not BasePlugin itself
                if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    # Instantiate the plugin, passing the app instance
                    plugin_instance = obj(self.app)
                    self.plugins.append(plugin_instance)
                    print(f"Loaded plugin: {name}")
        except Exception as e:
            print(f"Failed to load plugin from {module_name}: {e}")

    def unload_plugins(self):
        """Calls the cleanup method on all loaded plugins."""
        for plugin in self.plugins:
            try:
                plugin.unload()
            except Exception as e:
                print(f"Error unloading plugin {plugin.__class__.__name__}: {e}")
        self.plugins = []

class BasePlugin:
    """
    Base class for all plugins.
    Plugins should inherit from this class.
    """
    def __init__(self, app):
        """
        Initializes the plugin.
        :param app: The main VoiceChatApp instance.
        """
        self.app = app

    def initialize(self):
        """
        Called after all plugins are loaded. Use this to set up UI elements,
        register callbacks, etc.
        """
        pass

    def unload(self):
        """
        Called when the application is shutting down. Use this for cleanup.
        """
        pass
