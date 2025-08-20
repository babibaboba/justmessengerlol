import os
import importlib
import inspect
import sys
import json

class PluginManager:
    """
    Manages the discovery, loading, and lifecycle of client-side plugins.
    """
    def __init__(self, app):
        self.app = app
        self.plugins = [] # Will now be a list of dicts
        self.themed_widgets = []
        self.plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir)
        # Add the plugins directory to the path so subdirectories can be imported
        if self.plugins_dir not in sys.path:
            sys.path.insert(0, self.plugins_dir)

    def register_themed_widget(self, widget):
        """Allows plugins to register a widget to be themed by the main app."""
        if widget not in self.themed_widgets:
            self.themed_widgets.append(widget)

    def discover_and_load_plugins(self):
        """
        Finds and loads all valid plugins from subdirectories in the plugins folder.
        """
        print(f"Discovering client plugins in: {self.plugins_dir}")
        for dir_name in os.listdir(self.plugins_dir):
            plugin_dir = os.path.join(self.plugins_dir, dir_name)
            if not os.path.isdir(plugin_dir):
                continue

            # Look for the metadata file
            metadata_path = os.path.join(plugin_dir, 'plugin.json')
            if not os.path.exists(metadata_path):
                continue

            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception as e:
                print(f"Error reading metadata for {dir_name}: {e}")
                continue

            # Find the main plugin python file
            py_file = None
            is_enabled = False
            for file in os.listdir(plugin_dir):
                if file.endswith('.py'):
                    py_file = file
                    is_enabled = True
                    break
                elif file.endswith('.py.disabled'):
                    py_file = file
                    is_enabled = False
                    break
            
            if not py_file:
                continue
                
            module_name = py_file.replace('.py.disabled', '').replace('.py', '')
            
            plugin_info = {
                'id': dir_name,
                'name': metadata.get('name', dir_name),
                'description': metadata.get('description', 'No description.'),
                'enabled': is_enabled,
                'module_name': module_name,
                'path': plugin_dir,
                'instance': None
            }

            if is_enabled:
                self._load_plugin_from_module(plugin_info, dir_name, module_name)
            
            self.plugins.append(plugin_info)

        # Initialize loaded plugins after all have been discovered
        for plugin_info in self.plugins:
            if plugin_info['instance']:
                try:
                    plugin_info['instance'].initialize()
                except Exception as e:
                    print(f"Error initializing plugin {plugin_info['name']}: {e}")

    def _load_plugin_from_module(self, plugin_info, dir_name, module_name):
        try:
            # The module to import is now relative to the plugins dir, e.g., "file_transfer.file_transfer_plugin"
            full_module_path = f"{dir_name}.{module_name}"
            module = importlib.import_module(full_module_path)
            importlib.reload(module) # Reload in case of changes

            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_instance = obj(self.app)
                    plugin_info['instance'] = plugin_instance
                    print(f"Loaded plugin: {plugin_info['name']}")
                    break # Load the first valid class found
        except Exception as e:
            import traceback
            print(f"Failed to load plugin from {full_module_path}: {e}")
            traceback.print_exc()
            plugin_info['enabled'] = False
            plugin_info['instance'] = None

    def unload_plugins(self):
        """Calls the cleanup method on all loaded plugin instances."""
        for plugin_info in self.plugins:
            if plugin_info.get('instance'):
                try:
                    plugin_info['instance'].unload()
                except Exception as e:
                    print(f"Error unloading plugin {plugin_info['name']}: {e}")
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
