import flet as ft
import json

class EmojiManager:
    def __init__(self, app):
        self.app = app
        self.emoji_data = self.load_emojis()
        self.emoji_container = self.create_emoji_container()

    def load_emojis(self):
        # Hardcoded emoji data as a fallback since a dedicated file is missing
        return {
            "Smileys & People": [
                "😀", "😁", "😂", "🤣", "😃", "😄", "😅", "😆", "😉", "😊",
                "😋", "😎", "😍", "😘", "🥰", "😗", "😙", "😚", "🙂", "🤗",
                "🤩", "🤔", "🤨", "😐", "😑", "😶", "🙄", "😏", "😣", "😥",
                "😮", "🤐", "😯", "😪", "😫", "😴", "😌", "😛", "😜", "😝",
                "🤤", "😒", "😓", "😔", "😕", "🙃", "🤑", "😲", "☹️", "🙁",
                "😖", "😞", "😟", "😤", "😢", "😭", "😦", "😧", "😨", "😩",
                "🤯", "😬", "😰", "😱", "🥵", "🥶", "😳", "🤪", "😵", "😡",
                "😠", "🤬", "😷", "🤒", "🤕", "🤢", "🤮", "🤧", "😇", "🤠"
            ],
            "Animals & Nature": [
                "🐵", "🐒", "🦍", "🦧", "🐶", "🐕", "🦮", "🐕‍🦺", "🐩", "🐺",
                "🦊", "🦝", "🐱", "🐈", "🐈‍⬛", "🦁", "🐯", "🐅", "🐆", "🐴"
            ],
            "Food & Drink": [
                "🍇", "🍈", "🍉", "🍊", "🍋", "🍌", "🍍", "🥭", "🍎", "🍏",
                "🍐", "🍑", "🍒", "🍓", "🥝", "🍅", "🥥", "🥑", "🍆", "🥔"
            ]
        }

    def create_emoji_container(self):
        # This will be a more complex control with categories and search
        # For now, a simple grid
        grid = ft.GridView(expand=True, max_extent=40, child_aspect_ratio=1.0)
        for category, emojis in self.emoji_data.items():
            for emoji_char in emojis:
                grid.controls.append(
                    ft.TextButton(
                        text=emoji_char,
                        on_click=lambda e, emoji=emoji_char: self.app.on_emoji_click(emoji)
                    )
                )
        return grid

    def get_emoji_picker(self):
        return self.emoji_container

    def get_emojis_by_category(self, category_name):
        """Returns emojis for a specific category."""
        return self.emoji_data.get(category_name, [])

    def get_categorized_emojis(self):
        """Returns a dictionary of emojis grouped by category."""
        return self.emoji_data