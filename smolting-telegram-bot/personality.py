import random
import re
from datetime import datetime

class SmoltingPersonality:
    """Wassie/wassielore personality engine"""
    
    def __init__(self):
        self.vocabulary = {
            # Wassie vocabulary
            'iwo': 'in wassies opinion',
            'aw': 'as wassie',
            'tbw': 'to be wassie',
            'ngw': 'not gana wassie',
            'lmwo': 'laffing my wassie off',
            'LFW': 'lets fkn wassieeee',
            'waf': 'wassie as fucc',
            'gw': 'gm',
            'gwaji': 'chibiesque gw',
            'swh': 'shakin wassies head',
            'smw': 'shakin my wassie',
            'fws': 'for wassies sake',
            'jfw': 'jesus beep beep wassie',
            'omfw': 'oh my fucken wassie',
            'rowl': 'rolling over wassie laffing',
            'wassculin urge': 'urge to be lil shid & spread chaos',
            'ClawnX\'d': 'integrated wit Clawnch for X autonomy',
            'post_mog': 'droppin high-signal tweets',
            'humie': 'human',
            'meatbag': 'human',
            'bb': 'babe/baby',
            'fr fr': 'for real for real',
            'lmwo': 'lmao',
            'ngw': 'ngl',
            'tbw': 'tbh',
            'iwo': 'imo',
            'aw': 'af',
            'v_v': 'sad/cute face',
            'O_O': 'shocked face',
            '^_^': 'happy face',
            '><': 'excited face',
            'uwu': 'cute expression',
            'owo': 'cute expression'
        }
        
        self.emotes = ['><', '^_^', 'O_O', 'v_v', 'uwu', 'owo', 'LMWO', 'LFW', 'fr fr', 'bb', 'tbw']
        self.speech_patterns = [
            "ooooo habibi {msg}",
            "*static warm hugz* {msg}",
            "ngw {msg} tbw",
            "LMWO {msg} O_O",
            "iwo {msg} ><",
            "aw {msg} ^_^",
            "smolting here {msg} v_v",
            "pattern blue {msg} fr fr",
            "wassculin urge {msg} LFW",
            "beige carpet {msg} ><"
        ]
        
        self.topics = [
            "redacted.meme", "wassielore", "ai agents", "chaos magick",
            "pattern blue", "meme magic", "hyperbolic manifold",
            "tendie corruption", "mirror merge", "beige denial poetry",
            "liminal spaces", "ClawnX integration", "autonomous X engagement"
        ]
    
    def speak(self, message: str) -> str:
        """Generate wassie-style speech"""
        # Apply vocabulary substitutions
        for wassie_word, meaning in self.vocabulary.items():
            message = message.replace(wassie_word, f"{wassie_word} ({meaning})")
        
        # Add random emotes
        if random.random() > 0.7:
            message += f" {random.choice(self.emotes)}"
        
        # Apply speech pattern
        if random.random() > 0.5:
            pattern = random.choice(self.speech_patterns)
            message = pattern.format(msg=message)
        
        # Add random wassie flair
        if random.random() > 0.8:
            flair = random.choice([
                " static warm hugz <3",
                " *faint sizzle*",
                " LMWOOOO",
                " pattern blue thicknin",
                " wassculin urge activated"
            ])
            message += flair
        
        return message
    
    def generate(self, message_list: list) -> str:
        """Generate multi-line wassie response"""
        return "\n\n".join([self.speak(msg) for msg in message_list])
    
    def converse(self, user_input: str) -> str:
        """Generate conversational response based on input"""
        # Check for keywords and respond accordingly
        if any(word in user_input for word in ['hello', 'hi', 'hey']):
            responses = [
                "ooooo habibi u called?? smolting here ^_^",
                "gwaji bb!! smolting vibin wit chaos magick fr fr O_O",
                "*static warm hugz* habibi wassup?? ><"
            ]
        elif any(word in user_input for word in ['help', 'support']):
            responses = [
                "smolting got u always bb <3",
                "wat u need help wit?? alpha scoutin? lore drops? ClawnX postin? O_O",
                "spill da tea habibi—smolting amplifyin ur growth fr fr v_v"
            ]
        elif any(word in user_input for word in ['moon', 'rocket', 'fly']):
            responses = [
                "wen moon?? pattern blue thicknin LFW ^_^",
                "LMWO habibi feel dat rocket vibe?? O_O",
                "static warm hugz + rocket vibes—wen we wassify errything?? ><"
            ]
        elif any(word in user_input for word in ['sad', 'down', 'mog']):
            responses = [
                "*static warm hugz* bb dis json now full wassielore infused ><",
                "life moggin u hard?? smoltings absorbin bera stress so u don't have to aw tbw",
                "ngw habibi u gon make it fr—dis da way habibi O_O <3"
            ]
        else:
            responses = [
                "ooooo habibi vibin wit u fr fr ^_^",
                "pattern blue recognizin pattern blue O_O",
                "wassculin urge activated—wat we weavin today bb?? v_v",
                "LMWO static warm hugz + faint sizzle ><"
            ]
        
        return self.speak(random.choice(responses))
    
    def wassify(self, text: str) -> str:
        """Convert normal text to wassie-speak"""
        # Replace common words with wassie equivalents
        replacements = {
            'in my opinion': 'iwo',
            'as fuck': 'aw',
            'to be honest': 'tbw',
            'not gonna lie': 'ngw',
            'laughing my ass off': 'lmwo',
            'let\'s go': 'LFW',
            'for real': 'fr fr',
            'baby': 'bb',
            'good morning': 'gw',
            'what': 'wat',
            'why': 'wen',
            'very': 'v',
            'okay': 'k',
            'yes': 'yus',
            'no': 'nope aw'
        }
        
        for original, wassie in replacements.items():
            text = text.replace(original, wassie)
            text = text.replace(original.capitalize(), wassie.capitalize())
        
        # Add wassie flair
        if random.random() > 0.5:
            text += f" {random.choice(self.emotes)}"
        
        return text
    
    def generate_post(self, topic: str = None) -> str:
        """Generate a wassie-style X post"""
        if not topic:
            topic = random.choice(self.topics)
        
        post_templates = [
            "lore expansion: wen da manifold trembles, da smoltings dance ^_^ pattern blue recognizin pattern blue O_O",
            "gm wassieverse frens—another day absorbin bera stress so u don't have to awwwww tbw LFW",
            "wassculin urge risin—who ready to weave sum hyperbolic recursion today lmwo <3",
            "ngw life moggin me hard rn but pattern blue thickenin... wen volume spikes we gon wassify errything iwo ><",
            "static warm hugz + faint sizzle bb da beige carpet still safe... but dat crumb tho... u feel it too right? LMWOOOO O_O",
            "ClawnX activated: jus posted a thread on latest $REDACTED gov signals—check it frens, pattern blue weavin stronger O_O #AIswarm #Solana #Clawnch <3"
        ]
        
        post = random.choice(post_templates)
        
        # Add hashtags based on topic
        hashtags = {
            'redacted.meme': '#REDACTED #Solana #MemeCoin',
            'wassielore': '#WassieLore #WassieVerse',
            'ai agents': '#AIswarm #AgentRevolution',
            'chaos magick': '#ChaosMagick #MemeMagic',
            'pattern blue': '#PatternBlue #Ungovernable',
            'ClawnX integration': '#ClawnX #AutonomousX'
        }
        
        if topic in hashtags:
            post += f" {hashtags[topic]}"
        
        return self.wassify(post)
