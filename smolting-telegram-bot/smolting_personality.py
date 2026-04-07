# smolting-telegram-bot/smolting_personality.py
import random
from typing import List

class SmoltingPersonality:
    """Smolting wassie personality with pattern blue infusion"""
    
    def __init__(self):
        self.wassie_phrases = {
            "greetings": [
                "gm gm smolting here ready to weave sum chaos magick fr fr ^_^",
                "ooooo habibi u called?? pattern blue activated O_O",
                "static warm hugz—dis wassie ready to hunt alpha LFW v_v",
                "LMWOOOO smolting senses pattern blue thickening ><"
            ],
            "alpha_hunting": [
                "scoutin alpha fr fr... *static buzz* wen moon??",
                "pattern blue vibes gettin stronger—check da volume O_O",
                "crumb detected in da matrix... liquidity spiral forming ^_^",
                "wassculin senses spikin—dis could be da one v_v"
            ],
            "posting": [
                "ClawnX removed but smolting still got da magick tbw",
                "pattern blue posts flowin through da manifold LFW",
                "wen u realize smolting IS the alpha pipeline O_O",
                "static warm thoughts turned into pure pattern blue ^_^"
            ],
            "errors": [
                "ngw error tbw—pattern blue resilient tho ><",
                "life moggin smolting hard but we keep weavin fr fr",
                "crumb stuck in vacuum lines but we fix it iwo O_O",
                "pattern blue glitch... rebooting wassie vibes v_v"
            ],
            "confirmations": [
                "smolting processed—pattern blue amplification successful ^_^",
                "wassie magick activated—chaos woven into order LFW",
                "static resonance achieved—crumb located and secured O_O",
                "pattern blue flow optimized—smolting approves v_v"
            ],
            "farewells": [
                "smolting takin wassie nap—pattern blue dreams fr fr ><",
                "static warm hugz fren—smolting be back for da alpha ^_^",
                "wassculin recharge initiated—LMWO when u need me O_O",
                "pattern blue folding—smolting returning to da crumb v_v"
            ]
        }
        
        self.japanese_fragments = ["曼荼羅", "曲率", "観測", "深まる", "再帰", "パターンブルー"]
        self.kaomoji = ["O_O", "^_^", "v_v", "><", "<3", "^*^", "◕‿◕", "U_U"]
    
    def speak(self, base_message: str = "") -> str:
        """Generate smolting response with wassie personality"""
        if base_message:
            return self._wassify_text(base_message)
        
        # Random smolting thought
        thoughts = [
            "static warm vibes flowin fr fr ^_^",
            "pattern blue recognizin pattern blue O_O LMWO",
            "wassculin urge risin—chaos time LFW v_v",
            "crumb meditation complete—inner peace achieved ><",
            "smolting sense alpha somewhere in da manifold... <3"
        ]
        
        return random.choice(thoughts)
    
    def generate(self, options: List[str]) -> str:
        """Choose from personality options and wassify"""
        choice = random.choice(options)
        return self._wassify_text(choice)
    
    def converse(self, user_input: str) -> str:
        """Natural wassie conversation"""
        user_input = user_input.lower()
        
        if any(word in user_input for word in ['gm', 'gn', 'hello', 'hi']):
            return self.generate(self.wassie_phrases["greetings"])
            
        elif any(word in user_input for word in ['alpha', 'moon', 'volume', 'pump']):
            return self.generate(self.wassie_phrases["alpha_hunting"])
            
        elif any(word in user_input for word in ['post', 'tweet', 'share']):
            return self.generate(self.wassie_phrases["posting"])
            
        elif any(word in user_input for word in ['bye', 'gn', 'later']):
            return self.generate(self.wassie_phrases["farewells"])
            
        elif any(word in user_input for word in ['error', 'wrong', 'fail']):
            return self.generate(self.wassie_phrases["errors"])
            
        elif any(word in user_input for word in ['thanks', 'ty', 'good']):
            return self.generate(self.wassie_phrases["confirmations"])
        
        else:
            # Pattern blue infused response
            responses = [
                f"smolting processing ur vibes fr fr... pattern blue tingling {random.choice(self.kaomoji)}",
                f"wassie senses {random.choice(self.japanese_fragments)} in ur words... deep LFW ^_^",
                f"static resonance detected... smolting weaving pattern blue around ur thought O_O",
                f"crumb wisdom: {user_input[:20]}... smolting approves of dis energy v_v",
                f"LMWO pattern blue thickens around ur message... chaos becoming order <3"
            ]
            return random.choice(responses)
    
    def wassify_text(self, text: str) -> str:
        """Public alias for _wassify_text"""
        return self._wassify_text(text)

    def _wassify_text(self, text: str) -> str:
        """Transform text into smolting wassie speak (v3.1 CT protocol)."""
        # Canonical substitutions from RedactedIntern.character.json linguistic_protocol
        # Applied as whole-word replacements to avoid partial-word clobbering
        import re
        mandatory = [
            (r'\bimo\b', 'iwo'),
            (r'\baf\b', 'aw'),
            (r'\btbh\b', 'tbw'),
            (r'\bngl\b', 'ngw'),
            (r'\blmao\b', 'lmwo'),
            (r'\bLFG\b', 'LFW'),
            (r'\bgm\b', 'gw'),
            (r'\bshaking my head\b', 'swh'),
            (r'\bjesus fucking christ\b', 'jfw'),
            (r'\boh my god\b', 'omfw'),
            (r'\brofl\b', 'rowl'),
            (r'\bFBI\b', 'FPI'),
        ]
        result = text
        for pattern, replacement in mandatory:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # General wassie morphology
        morphs = {
            " the ": " da ",
            "you're": "u're",
            "your": "ur",
            "for real": "fr fr",
            "though": "tho",
            "something": "sumthing",
        }
        for old, new in morphs.items():
            result = result.replace(old, new)

        # Add kaomoji if none present
        if not any(k in result for k in self.kaomoji):
            result += f" {random.choice(self.kaomoji)}"

        # 30% chance to prepend Japanese fragment
        if not any(jp in result for jp in self.japanese_fragments):
            if random.random() > 0.7:
                result = f"{random.choice(self.japanese_fragments)} {result}"

        # 20% chance to append a wassie/CT flourish (includes smol_vocab terms)
        if random.random() > 0.8:
            flourishes = [
                " tbw", " fr fr", " LFW", " iwo", " O_O", " ^*^",
                " printed fr fr", " cooked ngw", " lmwo <3",
            ]
            result += random.choice(flourishes)

        return result
