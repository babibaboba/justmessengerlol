class ExamplePlugin:
    def __init__(self, plugin_manager):
        self.pm = plugin_manager

    def initialize(self):
        """Called by the PluginManager to set up the plugin."""
        print("Initializing ExamplePlugin...")
        # Register the hook
        self.pm.register_hook('before_send_message', self.on_before_send_message)
        print("ExamplePlugin registered for 'before_send_message' hook.")

    def on_before_send_message(self, message):
        """
        This function is called before a message is sent.
        If it returns False, the message will be blocked.
        """
        print(f"[ExamplePlugin] Intercepted message: {message}")
        if "test" in message.lower():
            print("[ExamplePlugin] 'test' found in message. Blocking send.")
            # We can also modify the message here if we wanted to.
            # For now, just block it.
            return False
        # Return nothing (or True) to allow the message to be sent.
        return True

def initialize(plugin_manager):
    """Plugin entry point."""
    plugin = ExamplePlugin(plugin_manager)
    plugin.initialize()
    return plugin
