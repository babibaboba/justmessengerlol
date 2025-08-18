import emoji
from collections import defaultdict

class EmojiManager:
    def __init__(self):
        # Using the 'en' (English) emoji database as it's the most comprehensive
        self.categorized_emojis = self._categorize_emojis()

    def _categorize_emojis(self):
        """Categorizes emojis based on their group/subgroup."""
        categories = defaultdict(list)
        
        # A simplified mapping of subgroups to broader categories for the UI
        category_map = {
            'face-smiling': 'Faces',
            'face-affection': 'Faces',
            'face-tongue': 'Faces',
            'face-hand': 'Faces',
            'face-neutral-skeptical': 'Faces',
            'face-sleepy': 'Faces',
            'face-unwell': 'Faces',
            'face-hat': 'Faces',
            'face-glasses': 'Faces',
            'face-concerned': 'Faces',
            'face-negative': 'Faces',
            'face-costume': 'Faces',
            'cat-face': 'Animals',
            'monkey-face': 'Animals',
            'emotion': 'Faces',
            'person': 'People',
            'person-gesture': 'People',
            'person-role': 'People',
            'person-fantasy': 'People',
            'person-activity': 'People',
            'person-sport': 'People',
            'person-resting': 'People',
            'family': 'People',
            'person-symbol': 'People',
            'body-parts': 'People',
            'animal-mammal': 'Animals',
            'animal-bird': 'Animals',
            'animal-amphibian': 'Animals',
            'animal-reptile': 'Animals',
            'animal-marine': 'Animals',
            'animal-bug': 'Animals',
            'plant-flower': 'Nature',
            'plant-other': 'Nature',
            'food-fruit': 'Food',
            'food-vegetable': 'Food',
            'food-prepared': 'Food',
            'food-asian': 'Food',
            'food-marine': 'Food',
            'food-sweet': 'Food',
            'drink': 'Food',
            'dishware': 'Food',
            'place-map': 'Travel',
            'place-geographic': 'Travel',
            'place-building': 'Travel',
            'place-religious': 'Travel',
            'place-other': 'Travel',
            'transport-ground': 'Travel',
            'transport-water': 'Travel',
            'transport-air': 'Travel',
            'hotel': 'Travel',
            'time': 'Travel',
            'sky & weather': 'Nature',
            'event': 'Activities',
            'award-medal': 'Activities',
            'sport': 'Activities',
            'game': 'Activities',
            'arts & crafts': 'Activities',
            'clothing': 'Objects',
            'sound': 'Objects',
            'music': 'Objects',
            'musical-instrument': 'Objects',
            'phone': 'Objects',
            'computer': 'Objects',
            'light & video': 'Objects',
            'book-paper': 'Objects',
            'money': 'Objects',
            'office': 'Objects',
            'lock': 'Objects',
            'tool': 'Objects',
            'science': 'Objects',
            'medical': 'Objects',
            'household': 'Objects',
            'other-object': 'Objects',
            'transport-sign': 'Symbols',
            'warning': 'Symbols',
            'arrow': 'Symbols',
            'religion': 'Symbols',
            'zodiac': 'Symbols',
            'av-symbol': 'Symbols',
            'gender': 'Symbols',
            'math': 'Symbols',
            'punctuation': 'Symbols',
            'currency': 'Symbols',
            'other-symbol': 'Symbols',
            'keycap': 'Symbols',
            'alphanum': 'Symbols',
            'geometric': 'Symbols',
            'flag': 'Flags',
            'country-flag': 'Flags',
            'subdivision-flag': 'Flags',
        }

        for emj, data in emoji.EMOJI_DATA.items():
            if data['status'] == 'fully-qualified':
                group = data.get('subgroup')
                category = category_map.get(group, 'Other')
                categories[category].append(emj)
        
        return dict(sorted(categories.items()))

    def get_all_emojis(self):
        """Returns a flat list of all available emoji characters."""
        return [emj for sublist in self.categorized_emojis.values() for emj in sublist]

    def get_categorized_emojis(self):
        """Returns a dictionary of emojis grouped by category."""
        return self.categorized_emojis
