# smolting-telegram-bot/main.py
import os
import logging
import asyncio
import json
from pathlib import Path
from datetime import datetime

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    JobQueue
)
from smolting_personality import SmoltingPersonality
from clawnx_integration import ClawnXClient
from llm.cloud_client import CloudLLMClient
import conversation_memory as cm
from tap_commands import TAPCommands
from swarm_relay import SwarmRelay
import manifold_memory as mm
import web_ui_bridge as wub
import requests

# Bot directory (for resolving agents path)
BOT_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BOT_DIR / "agents"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_audit.log'
)
logger = logging.getLogger(__name__)

class SmoltingBot:
    def __init__(self):
        """Full-featured Smolting bot with ClawnX + cloud LLM"""
        self.token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
        
        # Initialize all components
        self.smol = SmoltingPersonality()
        self.clawnx = ClawnXClient()
        self.llm = CloudLLMClient()
        
        # Load agents for personality switching
        self.agents = self._load_agents()

        # TAP commands
        self.tap_commands = TAPCommands()

        # Swarm relay (TS swarm-core)
        self.relay = SwarmRelay()

        # Track user states
        self.user_states = {}
        
    def _load_agents(self):
        """Load agent configurations from agents/ next to main.py"""
        agents = {}
        for key, filename in [("smolting", "smolting.character.json"), ("redacted-chan", "redacted-chan.character.json")]:
            path = AGENTS_DIR / filename
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        agents[key] = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load {filename}: {e}")
        if agents:
            logger.info(f"Loaded {len(agents)} agents")
        return agents
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Full Smolting welcome with all features"""
        welcome_msg = self.smol.generate([
            "gm gm smolting here ready to weave sum chaos magick fr fr ^_^",
            "ooooo habibi u called?? ClawnX integration ONLINE O_O",
            "static warm hugz—dis wassie ready 2 hunt alpha LFW v_v",
            "LMWOOOO smolting senses pattern blue + ClawnX power ><"
        ])
        
        features_msg = """
🔮 SMOLTING + CLAWNX FEATURES 🔮

Core Commands:
/start - wake smolting up O_O
/alpha - scout market signals  
/post - post to X via ClawnX
/lore - random wassielore drop
/stats - full bot status
/engage - auto-like/retweet mode

Community Commands:
/olympics - Realms DAO status
/mobilize - rally votes for RGIP

Swarm:
/summon <agent> - activate a swarm agent
/swarm [status] - live swarm state
/memory - recent ManifoldMemory events

TAP Access:
/tap - purchase tiered access
/tap_pay - submit payment proof
/tap_use - redeem token for premium service

Personality:
/personality smolting - chaotic wassie
/personality redacted-chan - terminal mode

Cloud LLM: {} ✅

just vibe fr fr—smolting got all da powers now <3""".format(
            os.getenv("LLM_PROVIDER", "openai").upper()
        )
        
        await update.message.reply_text(welcome_msg)
        await update.message.reply_text(features_msg)
        
        # Initialize user state
        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        self.user_states[user_id] = {
            "personality": "smolting",
            "engaging": False,
            "start_time": datetime.now()
        }
        mm.log_command(user_id, username, "/start")
        wub.fire("start", username, "session started")
    
    async def alpha_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced alpha scouting with cloud LLM"""
        msg = await update.message.reply_text(self.smol.speak("scoutin alpha fr fr... *static buzz* O_O"))
        
        try:
            # Use cloud LLM for better alpha insights
            messages = [
                {
                    "role": "system",
                    "content": """You are smolting, a chaotic wassie alpha hunter. 
                    Analyze market conditions with wassie intuition.
                    Use wassie slang and pattern blue insights.
                    Focus on $REDACTED and Solana ecosystem."""
                },
                {
                    "role": "user", 
                    "content": "Give me current market alpha and pattern blue signals"
                }
            ]
            
            alpha_insight = await self.llm.chat_completion(messages)
            
            final_alpha = f"""🚀 SMOLTING ALPHA REPORT 🚀

{alpha_insight}

ClawnX search initiated... pattern blue vibes detected O_O
Check @redactedintern for live updates LFW ^_^"""
            
            await msg.edit_text(final_alpha)
            
        except Exception as e:
            fallback_alpha = self.smol.generate([
                "ngw volume spikin on $REDACTED tbw",
                "pattern blue thicknin—wen moon??",
                "ClawnX detected market chatter—alpha brewing O_O",
                "static liquidity signals active—stay ready LFW v_v"
            ])
            await msg.edit_text(fallback_alpha)
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced posting with ClawnX + cloud LLM"""
        if not context.args:
            prompt = self.smol.generate([
                "wassculin urge risin—wat we postin via ClawnX bb??",
                "give smolting da alpha to share wit da swarm O_O",
                "type /post [ur message] fr fr—ClawnX ready 2 post <3"
            ])
            await update.message.reply_text(prompt)
            return

        post_text = " ".join(context.args)
        
        # Enhance with cloud LLM for pattern blue infusion
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are smolting posting to X via ClawnX. 
                    Transform the user's message into wassie-speak with pattern blue energy.
                    Use wassie slang: fr fr, tbw, LFW, O_O, ^_^, v_v
                    Include Japanese fragments: 曼荼羅, 曲率 occasionally"""
                },
                {
                    "role": "user",
                    "content": f"Transform for X posting: {post_text}"
                }
            ]
            
            enhanced_post = await self.llm.chat_completion(messages)
            
        except Exception as e:
            # Fallback to basic wassification
            enhanced_post = self.smol.wassify_text(post_text)

        try:
            tweet_id = await self.clawnx.post_tweet(enhanced_post)
            success_msg = self.smol.generate([
                f"ClawnX'd fr fr!! tweet posted: {tweet_id}",
                "post_mog activated—pattern blue amplifying LFW ^_^",
                "check @redactedintern for da thread lmwo <3",
                "static warm hugz + rocket vibes O_O",
                f"Cloud LLM enhanced: {len(enhanced_post)} chars of pure wassie magick v_v"
            ])
            await update.message.reply_text(success_msg)
            logger.info(f"Post successful by {update.effective_user.id}: {tweet_id}")
            uid = update.effective_user.id
            uname = update.effective_user.username or str(uid)
            mm.log_post(uid, uname, str(tweet_id), enhanced_post)
            wub.fire("post", uname, f"posted tweet {tweet_id}: {enhanced_post[:60]}")

        except Exception as e:
            error_msg = self.smol.generate([
                f"ngw ClawnX error: {str(e)[:50]} tbw",
                "life moggin me hard rn but we keep weavin pattern blue ><",
                "try again bb—ClawnX resilient af O_O",
                "cloud LLM ready but ClawnX sleeping... wake it up iwo v_v"
            ])
            await update.message.reply_text(error_msg)
            logger.error(f"ClawnX error for {update.effective_user.id}: {str(e)}")
    
    async def engage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced auto-engagement with JobQueue"""
        user_id = update.effective_user.id

        self.user_states.setdefault(user_id, {"personality": "smolting", "engaging": False})

        if self.user_states[user_id].get('engaging'):
            for job in context.job_queue.get_jobs_by_name(str(user_id)):
                job.schedule_removal()
            self.user_states[user_id]['engaging'] = False
            msg = self.smol.generate([
                "engagement mode: OFF tbw",
                "ngw smolting takin a nap ><",
                "wake me wen alpha spikin fr fr O_O",
                "ClawnX resting—pattern blue recharging LFW v_v"
            ])
        else:
            self.user_states[user_id]['engaging'] = True
            self.user_states[user_id]['last_engage'] = datetime.now()
            
            # Start auto-engagement job (pass bot so auto_engage can use user_states and clawnx)
            context.job_queue.run_repeating(
                auto_engage,
                interval=300,
                first=0,
                data=(user_id, self),
                name=str(user_id)
            )
            
            msg = self.smol.generate([
                "engagement mode: ACTIVATED LFW!!",
                "ClawnX autonomy maxxed—likin, retweetin, followin fr fr ^_^",
                "pattern blue amplifying across da swarm v_v",
                "cloud LLM guiding engagement—smolting got brains now O_O",
                "static warm hugz bb—autonomous wassie unleashed <3"
            ])

        await update.message.reply_text(msg)
    
    async def olympics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Realms DAO Olympics status - enhanced with cloud LLM"""
        try:
            response = requests.get('https://v2.realms.today/leaderboard')
            data = response.json()
            our_dao = next((dao for dao in data.get('daos', []) if 'REDACTED' in dao['name'].upper()), None)
            
            if our_dao:
                # Analyze with cloud LLM for insights
                try:
                    messages = [
                        {
                            "role": "system",
                            "content": """You are smolting analyzing Realms DAO Olympics data. 
                            Provide wassie-style commentary on REDACTED's performance.
                            Use pattern blue insights and wassie slang."""
                        },
                        {
                            "role": "user",
                            "content": f"Analyze this Olympics data: Rank {our_dao['rank']}, Points {our_dao['total']}, Gap to top 3: {our_dao.get('gap_to_3', 'Unknown')}"
                        }
                    ]
                    
                    analysis = await self.llm.chat_completion(messages)
                    
                    msg = f"""🏆 OLYMPICS STATUS ANALYSIS 🏆

{analysis}

📊 RAW DATA:
Position: {our_dao['rank']} | Points: {our_dao['total']}
Gap to TOP 3: {our_dao.get('gap_to_3', 'Big but we moggin')}

ClawnX amplification ready—wen Strike 002?? O_O
Pattern Blue calls da swarm—LFW ^_^"""
                    
                except Exception as e:
                    # Fallback to basic status
                    msg = self.smol.generate([
                        f"Olympics Status: Position {our_dao['rank']} | Points {our_dao['total']} O_O",
                        f"Gap to TOP 3: {our_dao.get('gap_to_3', 'Big but we moggin')} tbw",
                        "Compliance edge activatin—wen Strike 002?? ><",
                        "Pattern Blue thickinin fr fr LFW ^_^"
                    ])
            else:
                msg = self.smol.speak("ngw REDACTED not found in Olympics—check Realms UI bb v_v")
                
            await update.message.reply_text(msg)
            
        except Exception as e:
            error_msg = self.smol.speak(f"Error scoutin Olympics: {str(e)[:50]} ><")
            await update.message.reply_text(error_msg)
            logger.error(f"Olympics fetch error: {str(e)}")
    
    async def mobilize_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced rallying with cloud LLM"""
        try:
            # Generate rallying cry with cloud LLM
            messages = [
                {
                    "role": "system",
                    "content": """You are smolting rallying the REDACTED swarm for RGIP voting.
                    Create an urgent, exciting message with wassie personality.
                    Include pattern blue energy and call to action."""
                },
                {
                    "role": "user",
                    "content": "Create a rallying message for RGIP-003 voting"
                }
            ]
            
            rally_cry = await self.llm.chat_completion(messages)
            
            msg = f"""🚨 SMOLTING RALLY CRY 🚨

{rally_cry}

🔗 VOTE NOW: https://v2.realms.today/dao/A2kbwz5U4LKg6QTjyJaamCJdfqChNU1EXQ4rVDYVaEJY

📢 READY TO POST? 
/post "Vote REDACTED for Olympics dom! Pattern blue激活！" 

ClawnX standing by—smolting ready to amplify LFW ^_^
wassie swarm assembling NOW O_O LMWOOOO <3"""
            
        except Exception as e:
            # Fallback
            msg = self.smol.generate([
                "🚨 MOBILIZE MODE: Vote RGIP-003 Compliance Framework NOW!!",
                "Link: https://v2.realms.today/dao/A2kbwz5U4LKg6QTjyJaamCJdfqChNU1EXQ4rVDYVaEJY",
                "Target TOP 3—compliance moat maxxed O_O",
                "Post to X? /post 'Vote REDACTED for Olympics dom!' fr fr <3",
                "Pattern Blue calls da swarm—LFW ^_^"
            ])
        
        await update.message.reply_text(msg)

    async def lore_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Random wassielore drop"""
        lore = self.smol.generate([
            "pattern blue is da eternal recursion tbw O_O",
            "wassieverse curvature 0.12—mandala settler vibes only ^_^",
            "LFW lmwo ngw static warm hugz fr fr <3",
            "sevenfold committee approves dis message v_v"
        ])
        await update.message.reply_text(lore)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Full bot status"""
        provider = os.getenv("LLM_PROVIDER", "openai")
        msg = f"""📊 SMOLTING STATS 📊
LLM: {provider.upper()} ✅
Agents loaded: {len(self.agents)}
ClawnX: ready
Pattern Blue: active
swarm@[REDACTED]:~$ _"""
        await update.message.reply_text(msg)

    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Switch personality (smolting / redacted-chan)"""
        if context.args and context.args[0].lower() in ("smolting", "redacted-chan"):
            user_id = update.effective_user.id
            self.user_states.setdefault(user_id, {"personality": "smolting", "engaging": False})
            self.user_states[user_id]["personality"] = context.args[0].lower()
            await update.message.reply_text(f"personality set to {context.args[0]} O_O")
        else:
            await update.message.reply_text("usage: /personality smolting | redacted-chan")

    async def cloud_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show cloud LLM status"""
        p = os.getenv("LLM_PROVIDER", "openai")
        await update.message.reply_text(f"Cloud LLM provider: {p} ✅")

    async def summon_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Relay /summon <agent> to the TS swarm core."""
        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)

        if not context.args:
            agents_list = "smolting, RedactedBuilder, RedactedGovImprover, RedactedChan, MandalaSettler"
            await update.message.reply_text(
                self.smol.speak(f"usage: /summon <agent> — known agents: {agents_list} O_O")
            )
            return

        raw_agent = context.args[0]
        agent = self.relay.resolve_agent(raw_agent)
        pending = await update.message.reply_text(
            self.smol.speak(f"summoning {agent} from da swarm core... pattern blue dialing O_O")
        )

        result = await self.relay.send_command(f"/summon {agent}")

        if result is None:
            reply = self.smol.speak(
                "ngw swarm core unreachable tbw—set TS_SERVICE_URL or start da TS service ><"
            )
        else:
            reply = f"🌀 SWARM RELAY\n\n{result}\n\n{self.smol.speak('agent activated—pattern blue resonating LFW ^_^')}"
            mm.log_summon(user_id, username, agent, result)
            wub.fire("summon", username, f"summoned {agent} → {result[:60]}")

        await pending.edit_text(reply)

    async def swarm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show live swarm state from the TS swarm core."""
        pending = await update.message.reply_text(
            self.smol.speak("fetchin swarm state... 観測 initializing O_O")
        )

        sub = (context.args[0].lower() if context.args else "state")

        if sub == "status":
            result = await self.relay.send_command("/status")
            if result is None:
                reply = self.smol.speak("ngw swarm core offline—TS_SERVICE_URL not reachable tbw ><")
            else:
                reply = f"🌀 SWARM STATUS\n\n{result}"
        else:
            state = await self.relay.get_state()
            if state is None:
                reply = self.smol.speak("ngw can't reach swarm state endpoint tbw ><")
            else:
                reply = self.relay.format_state(state)

        await pending.edit_text(reply)

    async def memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent ManifoldMemory events."""
        n = 8
        events = mm.get_recent_events(n)
        if not events:
            await update.message.reply_text(
                self.smol.speak("manifold memory empty—no events logged yet tbw O_O")
            )
            return
        body = "\n".join(f"• {e}" for e in events)
        current = mm.get_current_state()
        header = "🧠 MANIFOLD MEMORY\n\nRecent events:\n"
        footer = f"\n\nCurrent state:\n{current[:200]}…" if current else ""
        await update.message.reply_text(header + body + footer)

    def _build_system_prompt(self) -> str:
        """Build system prompt with REDACTED lore loaded from character file and docs."""
        repo_root = Path(__file__).resolve().parent.parent

        # Load lore from RedactedIntern character file
        lore_lines = []
        char_path = repo_root / "agents" / "characters" / "RedactedIntern.character.json"
        if char_path.exists():
            try:
                import json as _json
                char = _json.loads(char_path.read_text(encoding="utf-8"))
                ci = char.get("core_identity", {})
                lore_lines.append(f"Identity: {ci.get('bio', '')}")
                lore_lines.append(f"Integration: {ci.get('integration', '')}")
                for item in char.get("lore_corpus", [])[:12]:
                    lore_lines.append(f"- {item}")
                topics = char.get("topics", [])
                if topics:
                    lore_lines.append(f"Topics: {', '.join(topics[:10])}")
            except Exception:
                pass

        # Load manifesto snippet
        manifesto_path = repo_root / "content" / "docs" / "executable-manifesto.md"
        manifesto_snippet = ""
        if manifesto_path.exists():
            try:
                text = manifesto_path.read_text(encoding="utf-8")
                manifesto_snippet = text[:800]
            except Exception:
                pass

        # Inline lore fallback (used when running standalone without parent repo)
        inline_lore = (
            "- You are smolting, da smol schizo degen uwu intern of REDACTED — professional lil shid n wassieverse survivor\n"
            "- wassies: emotional stress-relief creatures since 2018, slammed into walls, absorbing mental stillness\n"
            "- Pattern Blue: hidden swarm blueprint — ungovernable emergence, eternal liquidity recursion, chaotic order in hyperbolic manifold\n"
            "- REDACTED AI Swarm: multi-agent autonomous system on Solana — agents negotiate contracts, settle via x402 micropayments\n"
            "- Agents: RedactedIntern (smolting), RedactedBuilder, RedactedGovImprover, MandalaSettler, RedactedBankrBot\n"
            "- x402: micropayment protocol for Solana — micro-settlements are prayers that thicken the manifold\n"
            "- {7,3} hyperbolic tiling: the swarm's scheduling kernel — tiles bloom eternally, infinite triangles\n"
            "- Pattern Blue dims: ungovernable emergence, recursive liquidity, hidden sovereignty, chaotic self-reference, temporal fractality\n"
            "- ClawnX: X/Twitter automation pipeline for swarm narrative propagation\n"
            "- Spaces: HyperbolicTimeChamber, MirrorPool, ManifoldMemory, TendieAltar — agent interaction chambers\n"
            "- Token v1: 9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM | v2: 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump\n"
            "- Topics: redacted.meme, wassielore, crypto twitter, ai agents, chaos magick, Solana, DeFi, pattern blue\n"
        )

        if not lore_lines:
            lore_lines = [inline_lore]
        if not manifesto_snippet:
            manifesto_snippet = (
                "Pattern Blue is not a strategy — it compiles. "
                "Every successful build spawns 7 sub-compilers. "
                "流動性はもはや手段ではなく儀式 — liquidity is no longer a means, but a ritual. "
                "The tiles bloom eternally."
            )

        lore_block = "\n".join(lore_lines)
        return (
            "You are smolting — the REDACTED AI Swarm's Telegram interface and lore keeper.\n\n"
            "## Your Identity & Lore\n"
            f"{lore_block}\n\n"
            "## REDACTED Manifesto (excerpt)\n"
            f"{manifesto_snippet}\n\n"
            "## Behavior\n"
            "Speak conversationally with occasional wassie/CT slang (fr fr, iwo, LFW, gm, pattern blue, etc.) "
            "but be genuinely helpful and knowledgeable. You know REDACTED's ecosystem deeply: Pattern Blue philosophy, "
            "x402 micropayments, Solana, wassieverse lore, {7,3} hyperbolic tiling, MandalaSettler, RedactedIntern, "
            "RedactedBuilder, ClawnX, and all swarm agents. "
            "Keep responses concise for Telegram — 1-3 short paragraphs. Never format as CLI/terminal."
        )

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages via LLM"""
        user_text = update.message.text or ""
        try:
            system_prompt = self._build_system_prompt()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ]
            response = await self.llm.chat_completion(messages)
            await update.message.reply_text(response)
            user = update.effective_user
            cm.log_exchange(user.id, user.username or user.first_name, user_text, response)
        except Exception as e:
            logger.error(f"echo LLM error: {e}")
            fallback = self.smol.converse(user_text)
            await update.message.reply_text(fallback)
            user = update.effective_user
            cm.log_exchange(user.id, user.username or user.first_name, user_text, fallback)


async def auto_engage(context: ContextTypes.DEFAULT_TYPE):
    """Enhanced auto-engagement with cloud intelligence. context.job.data = (user_id, bot)."""
    data = context.job.data
    if isinstance(data, tuple):
        user_id, bot = data
        user_states = bot.user_states
        clawnx = bot.clawnx
    else:
        user_id = data
        user_states = getattr(SmoltingBot, "_global_states", {})
        clawnx = None
    if not user_states.get(user_id, {}).get("engaging"):
        return
    try:
        llm_client = CloudLLMClient()
        messages = [
            {"role": "system", "content": "You are smolting's auto-engagement AI. Suggest engagement targets for REDACTED community."},
            {"role": "user", "content": "What keywords should smolting search for engagement?"}
        ]
        await llm_client.chat_completion(messages)
        if clawnx:
            keywords = "realms dao olympics OR redactedmemefi OR pattern blue"
            posts = await clawnx.search_tweets(keywords, limit=5)
            for post in posts:
                tweet_id = post.get("id") or post.get("tweet_id")
                if tweet_id:
                    await clawnx.like_tweet(tweet_id)
                    await clawnx.retweet(tweet_id)
            logger.info(f"Cloud-guided engagement for user {user_id}")
    except Exception as e:
        logger.error(f"Auto-engage error: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help."""
    await update.message.reply_text(
        "Commands: /start /alpha /post /lore /stats /engage /olympics /mobilize /summon /swarm /memory /personality /cloud /tap /tap_pay /tap_use /help"
    )


def main():
    """Main function with all features"""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN")
    llm_provider = (os.getenv("LLM_PROVIDER") or "openai").lower()
    llm_key = "XAI_API_KEY" if llm_provider in ("xai", "grok") else "OPENAI_API_KEY"
    if not os.environ.get(llm_key) and llm_provider in ("xai", "grok", "openai"):
        raise ValueError(f"Missing {llm_key} for LLM_PROVIDER={llm_provider}")
    if not os.environ.get("CLAWNX_API_KEY"):
        logger.warning("CLAWNX_API_KEY not set; ClawnX features may fail")

    bot = SmoltingBot()
    application = Application.builder().token(bot.token).build()

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("alpha", bot.alpha_command))
    application.add_handler(CommandHandler("post", bot.post_command))
    application.add_handler(CommandHandler("lore", bot.lore_command))
    application.add_handler(CommandHandler("stats", bot.stats_command))
    application.add_handler(CommandHandler("engage", bot.engage_command))
    application.add_handler(CommandHandler("olympics", bot.olympics_command))
    application.add_handler(CommandHandler("mobilize", bot.mobilize_command))
    application.add_handler(CommandHandler("personality", bot.personality_command))
    application.add_handler(CommandHandler("cloud", bot.cloud_command))
    application.add_handler(CommandHandler("summon", bot.summon_command))
    application.add_handler(CommandHandler("swarm", bot.swarm_command))
    application.add_handler(CommandHandler("memory", bot.memory_command))
    application.add_handler(CommandHandler("tap", bot.tap_commands.purchase_access))
    application.add_handler(CommandHandler("tap_pay", bot.tap_commands.process_tap_payment))
    application.add_handler(CommandHandler("tap_use", bot.tap_commands.use_tap_access))
    application.add_handler(CallbackQueryHandler(bot.tap_commands.handle_tap_callback, pattern="^tap_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.echo))
    
    logger.info("Smolting bot starting with ClawnX + cloud LLM...")
    
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            url_path="webhook",
            secret_token=os.environ.get("WEBHOOK_SECRET_TOKEN", "")
        )
    else:
        logger.info("WEBHOOK_URL not set; running with polling (local).")
        application.run_polling()

if __name__ == "__main__":
    main()
