import json

class EmojiManager:
    def __init__(self):
        self.emoji_data = self.load_emojis()

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

    def get_emojis_by_category(self, category_name):
        """Returns emojis for a specific category."""
        return self.emoji_data.get(category_name, [])

    def get_categorized_emojis(self):
        """Returns a dictionary of emojis grouped by category."""
        return self.emoji_data