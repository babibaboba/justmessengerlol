import json
import os

class Translator:
    def __init__(self, config_manager, lang_path='localization.json'):
        self.config_manager = config_manager
        self.lang_path = lang_path
        self.translations = self.load_translations()
        self.language = self.get_language()

    def load_translations(self):
        """Loads the entire translation file."""
        try:
            # Look for the localization file in the same directory as this script
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, self.lang_path)
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading translation file: {e}")
            return {}

    def get_language(self):
        """Gets the saved language from the config, defaulting to 'en'."""
        config = self.config_manager.load_config()
        return config.get('language', 'en')

    def set_language(self, lang_code):
        """Saves the selected language to the config."""
        if lang_code in self.translations:
            self.language = lang_code
            config = self.config_manager.load_config()
            config['language'] = lang_code
            self.config_manager.save_config(config)
            return True
        return False

    def get(self, key, default_text=None, **kwargs):
        """
        Gets a translated string for a given key.
        - key: The key for the desired string (e.g., "window_title").
        - default_text: An optional fallback text if the key is not found.
        - **kwargs: Placeholders to be formatted into the string (e.g., username="Roo").
        """
        # Use the default text if provided and key is missing
        if default_text is None:
            default_text = key.replace('_', ' ').capitalize()

        # Get the string from the current language, or fall back to English, then to default.
        string = self.translations.get(self.language, {}).get(key,
                    self.translations.get('en', {}).get(key, default_text))

        # Format the string with any provided keyword arguments
        try:
            return string.format(**kwargs)
        except KeyError as e:
            print(f"Warning: Placeholder {e} not found in translation for key '{key}'")
            return string

# Example Usage:
if __name__ == '__main__':
    # This part is for testing the Translator class independently.
    # It requires a mock or real ConfigManager.

    # Mock ConfigManager for testing purposes
    class MockConfigManager:
        def __init__(self):
            self.config = {'language': 'ru'}
        def load_config(self):
            return self.config
        def save_config(self, data):
            self.config = data
            print(f"Saved config: {self.config}")

    mock_manager = MockConfigManager()
    tr = Translator(mock_manager)

    # Test getting a simple string
    print(f"Title in Russian: {tr.get('window_title')}") # Should be "JustMessenger" (no Russian translation in the provided JSON snippet)

    # Test with placeholders
    print(f"Call window title: {tr.get('call_window_title', peer_username='Andrey')}")

    # Switch language and test again
    tr.set_language('en')
    print(f"Title in English: {tr.get('window_title')}")

    # Test fallback
    print(f"Non-existent key: {tr.get('non_existent_key')}")
    print(f"Non-existent key with default: {tr.get('non_existent_key', default_text='Default Value')}")
