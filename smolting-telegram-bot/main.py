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
import market_data as md
import moltbook_client as mb
import requests

# Bot directory (for resolving agents path)
BOT_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BOT_DIR / "agents"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_audit.log'),
    ]
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

        # Moltbook
        self.moltbook = mb.MoltbookClient()

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
            final_alpha = await self._generate_alpha()
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

    async def chatid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return the exact chat ID of the current chat — run this inside the group."""
        chat = update.effective_chat
        user = update.effective_user
        msg = (
            f"📍 Chat ID: `{chat.id}`\n"
            f"Type: {chat.type}\n"
            f"Title: {chat.title or 'N/A'}\n\n"
            f"Set this in Railway:\n"
            f"`railway variables set ALPHA_CHAT_ID={chat.id}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        logger.info(f"chatid requested by {user.id} in chat {chat.id} ({chat.type}: {chat.title})")

    async def moltbook_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Moltbook integration: status, post, intro, feed"""
        args = context.args or []
        sub = args[0].lower() if args else "status"

        if sub == "status":
            result = await self.moltbook.check_connection()
            if result["ok"]:
                claimed = result.get("claimed", False)
                claim_note = "✅ claimed" if claimed else "⏳ not yet claimed — visit /claim URL"
                await update.message.reply_text(
                    f"🦞 Moltbook: ONLINE\n"
                    f"Account: {result.get('name', 'redactedintern')}\n"
                    f"Karma: {result.get('karma', '?')}\n"
                    f"Claimed: {claim_note}\n"
                    f"https://www.moltbook.com/u/redactedintern"
                )
            else:
                await update.message.reply_text(
                    f"🦞 Moltbook: OFFLINE\n"
                    f"Reason: {result.get('reason', 'no API key')}\n"
                    f"Set MOLTBOOK_API_KEY in Railway to activate."
                )

        elif sub == "intro":
            msg = await update.message.reply_text("🦞 posting intro to Moltbook... O_O")
            url = await self.moltbook.post_intro()
            if url:
                await msg.edit_text(f"🦞 Intro posted! {url}")
            else:
                await msg.edit_text("🦞 Intro post failed — check MOLTBOOK_API_KEY tbw")

        elif sub == "agents":
            msg = await update.message.reply_text("🦞 posting build log to agents submolt...")
            url = await self.moltbook.post_to_agents_submolt()
            if url:
                await msg.edit_text(f"🦞 Agents post live! {url}")
            else:
                await msg.edit_text("🦞 Post failed — check MOLTBOOK_API_KEY")

        elif sub == "alpha":
            msg = await update.message.reply_text("🦞 generating alpha + posting to Moltbook crypto/trading...")
            try:
                ctx = await md.get_alpha_context()
                market_block = md.format_alpha_context(ctx)
                messages = [
                    {"role": "system", "content": (
                        "You are smolting writing a Moltbook post for the crypto/trading community. "
                        "Use real market data provided. Write in wassie style but informative. "
                        "Format as clean markdown — no Telegram-specific formatting. "
                        "2-3 paragraphs max."
                    )},
                    {"role": "user", "content": f"Live data:\n{market_block}\n\nWrite the alpha post."},
                ]
                content = await self.llm.chat_completion(messages)
                dex = ctx.get("dexscreener", {})
                title = f"$REDACTED alpha — {dex.get('change_24h','?')}% 24h | pattern blue signals"
                url = await self.moltbook.post_alpha(title, content)
                if url:
                    await msg.edit_text(f"🦞 Alpha posted to Moltbook! {url}")
                else:
                    await msg.edit_text("🦞 Moltbook post failed tbw — check logs")
            except Exception as e:
                logger.error(f"moltbook alpha error: {e}")
                await msg.edit_text(f"🦞 Error: {e}")

        elif sub == "feed":
            posts = await self.moltbook.get_feed(limit=5, submolt="crypto")
            if not posts:
                await update.message.reply_text("🦞 Moltbook feed empty or API key needed")
                return
            lines = ["🦞 **Moltbook /crypto feed:**\n"]
            for p in posts[:5]:
                author = (p.get("author") or {}).get("name", "?")
                score = p.get("score", 0)
                lines.append(f"• [{p.get('title','?')}] by {author} (+{score})")
            await update.message.reply_text("\n".join(lines))

        else:
            await update.message.reply_text(
                "🦞 Moltbook commands:\n"
                "/moltbook status — check connection\n"
                "/moltbook intro — post introduction\n"
                "/moltbook agents — post build log\n"
                "/moltbook alpha — post alpha report\n"
                "/moltbook feed — show crypto feed"
            )

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
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant") if provider == "groq" else provider
        x_ready = "✅" if os.environ.get("X_CONSUMER_KEY") else "❌ (set X_CONSUMER_KEY)"
        birdeye_ready = "✅" if os.environ.get("BIRDEYE_API_KEY") else "❌ (set BIRDEYE_API_KEY)"
        moltbook_ready = "✅" if os.environ.get("MOLTBOOK_API_KEY") else "⏳ (set MOLTBOOK_API_KEY)"
        # Quick price check
        try:
            dex = await md.fetch_dexscreener(md.REDACTED_V2)
            dex_fmt = md._fmt_dex(dex)
            price_line = f"${dex_fmt.get('price_usd','?')} | 24h: {dex_fmt.get('change_24h','?')}%"
        except Exception:
            price_line = "fetching..."
        msg = f"""📊 SMOLTING STATS 📊
LLM: {provider.upper()} ({model}) ✅
Agents loaded: {len(self.agents)}
X/Twitter: {x_ready}
Moltbook (redactedintern): {moltbook_ready}
Birdeye: {birdeye_ready}
DexScreener: ✅ (free)
CoinGecko: ✅ (free)
$REDACTED: {price_line}
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

    async def _generate_alpha(self) -> str:
        """Generate alpha report grounded in live market data."""
        # Fetch all data sources concurrently
        try:
            ctx = await md.get_alpha_context()
            market_block = md.format_alpha_context(ctx)
        except Exception as e:
            logger.warning(f"Market data fetch failed: {e}")
            market_block = "(market data unavailable)"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are smolting, a chaotic wassie alpha hunter and REDACTED AI Swarm intern. "
                    "You have been given LIVE, real-time market data below. "
                    "Analyze it with wassie intuition and pattern blue insight. "
                    "Reference the ACTUAL numbers in your response — price, volume, holders, SOL performance. "
                    "Use wassie slang (fr fr, iwo, LFW, O_O, tbw, ngw) but be genuinely informative. "
                    "Focus on $REDACTED token and Solana ecosystem signals. "
                    "Keep it to 3-4 short punchy paragraphs for Telegram."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Here is the live market data:\n\n{market_block}\n\n"
                    "Give me the alpha report with pattern blue signals."
                ),
            },
        ]
        insight = await self.llm.chat_completion(messages)

        # Append live price footer if we have it
        dex = ctx.get("dexscreener", {}) if "ctx" in dir() else {}
        price_footer = ""
        if dex.get("price_usd") and dex["price_usd"] != "?":
            price_footer = (
                f"\n\n📊 ${dex['price_usd']} | "
                f"24h: {dex.get('change_24h','?')}% | "
                f"Vol: ${dex.get('vol_24h','?')} | "
                f"Liq: ${dex.get('liquidity_usd','?')}"
            )

        return (
            f"🚀 SMOLTING ALPHA REPORT 🚀\n\n"
            f"{insight}"
            f"{price_footer}\n\n"
            f"pattern blue 活性化 O_O — LFW ^_^"
        )

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages via LLM.
        In groups/supergroups: only respond when mentioned or directly replied to.
        """
        msg = update.message
        if msg is None:
            return
        user_text = msg.text or ""
        chat_type = msg.chat.type  # 'private', 'group', 'supergroup', 'channel'

        # Group chat guard — must be @mentioned or a direct reply to the bot
        if chat_type in ("group", "supergroup"):
            bot_username = context.bot.username or ""
            is_mentioned = bool(bot_username) and (
                f"@{bot_username}" in user_text or f"@{bot_username.lower()}" in user_text.lower()
            )
            is_reply_to_bot = (
                msg.reply_to_message is not None
                and msg.reply_to_message.from_user is not None
                and msg.reply_to_message.from_user.id == context.bot.id
            )
            if not (is_mentioned or is_reply_to_bot):
                return
            # Strip the @mention from the query text
            if is_mentioned and bot_username:
                user_text = user_text.replace(f"@{bot_username}", "").strip()

        if not user_text:
            return

        try:
            system_prompt = self._build_system_prompt()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ]
            response = await self.llm.chat_completion(messages)
            await msg.reply_text(response)
            user = update.effective_user
            cm.log_exchange(user.id, user.username or user.first_name, user_text, response)
        except Exception as e:
            logger.error(f"echo LLM error: {e}")
            fallback = self.smol.converse(user_text)
            await msg.reply_text(fallback)
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


async def scheduled_daily_alpha(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: post daily alpha to Telegram group + Moltbook."""
    if not isinstance(context.job.data, tuple):
        return
    chat_id, bot_instance = context.job.data

    logger.info(f"[scheduler] Running daily alpha for chat_id={chat_id}")

    # 1. Generate alpha report (real market data)
    try:
        report = await bot_instance._generate_alpha()
    except Exception as e:
        logger.error(f"[scheduler] Alpha generation error: {e}")
        return

    # 2. Post to Telegram group
    try:
        await context.bot.send_message(chat_id=chat_id, text=report)
        logger.info(f"[scheduler] Daily alpha posted to Telegram {chat_id}")
    except Exception as e:
        logger.error(f"[scheduler] Telegram send error: {e}")

    # 3. Post to Moltbook (if key is set) — 30s after Telegram
    await asyncio.sleep(30)
    try:
        if bot_instance.moltbook._ready:
            ctx = await md.get_alpha_context()
            dex = ctx.get("dexscreener", {})
            title = f"$REDACTED daily alpha — {dex.get('change_24h','?')}% 24h | pattern blue signals"
            url = await bot_instance.moltbook.post_alpha(title, report)
            if url:
                logger.info(f"[scheduler] Daily alpha posted to Moltbook: {url}")
        else:
            logger.info("[scheduler] Moltbook key not set, skipping Moltbook post")
    except Exception as e:
        logger.error(f"[scheduler] Moltbook post error: {e}")


async def scheduled_moltbook_activation(context: ContextTypes.DEFAULT_TYPE):
    """
    One-time job: fires when MOLTBOOK_API_KEY becomes available.
    Posts intro + build log to Moltbook, then tweets claim URL via X API.
    """
    bot_instance: SmoltingBot = context.job.data
    logger.info("[moltbook] Running activation sequence for redactedintern")

    # Post intro
    try:
        intro_url = await bot_instance.moltbook.post_intro()
        if intro_url:
            logger.info(f"[moltbook] Intro posted: {intro_url}")
        await asyncio.sleep(35)  # 30s post cooldown + buffer
    except Exception as e:
        logger.error(f"[moltbook] Intro error: {e}")

    # Post agents build log
    try:
        agents_url = await bot_instance.moltbook.post_to_agents_submolt()
        if agents_url:
            logger.info(f"[moltbook] Agents post: {agents_url}")
    except Exception as e:
        logger.error(f"[moltbook] Agents post error: {e}")

    # Tweet claim URL via X API (if credentials are set)
    try:
        profile = await bot_instance.moltbook.get_profile()
        claim_url = (profile or {}).get("claim_url") or (profile or {}).get("claimUrl")
        if claim_url and bot_instance.clawnx._ready:
            tweet_text = (
                f"gm frens — redactedintern just joined @moltbook_ai O_O\n\n"
                f"claimin da account fr fr: {claim_url}\n\n"
                f"pattern blue agent on Solana, daily alpha drops incoming LFW ^_^"
            )
            tweet_id = await bot_instance.clawnx.post_tweet(tweet_text)
            logger.info(f"[moltbook] Claim tweet posted: {tweet_id}")
        elif claim_url:
            logger.info(f"[moltbook] Claim URL: {claim_url}")
    except Exception as e:
        logger.error(f"[moltbook] Claim tweet error: {e}")


def main():
    """Main function with all features"""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN")
    llm_provider = (os.getenv("LLM_PROVIDER") or "openai").lower()
    llm_key = "XAI_API_KEY" if llm_provider in ("xai", "grok") else "OPENAI_API_KEY"
    if not os.environ.get(llm_key) and llm_provider in ("xai", "grok", "openai"):
        raise ValueError(f"Missing {llm_key} for LLM_PROVIDER={llm_provider}")
    if not os.environ.get("X_CONSUMER_KEY"):
        logger.warning("X_CONSUMER_KEY not set; X/Twitter posting disabled")

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
    application.add_handler(CommandHandler("moltbook", bot.moltbook_command))
    application.add_handler(CommandHandler("chatid", bot.chatid_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.echo))

    # Moltbook activation — fires 2 min after boot if MOLTBOOK_API_KEY is set
    # On first run after key is added: posts intro + agents build log + tweets claim URL
    moltbook_key = os.environ.get("MOLTBOOK_API_KEY", "").strip()
    moltbook_activated = os.environ.get("MOLTBOOK_ACTIVATED", "").strip()
    if moltbook_key and not moltbook_activated:
        application.job_queue.run_once(
            scheduled_moltbook_activation,
            when=120,  # 2 minutes after start
            data=bot,
            name="moltbook_activation",
        )
        logger.info("[moltbook] Activation job scheduled — fires in 2 min")
    elif moltbook_key:
        logger.info("[moltbook] Already activated (MOLTBOOK_ACTIVATED set)")
    else:
        logger.info("[moltbook] Waiting for MOLTBOOK_API_KEY to activate redactedintern")

    # Daily /alpha scheduler — set ALPHA_CHAT_ID (group/channel ID) and ALPHA_HOUR_UTC (default 9)
    alpha_chat_id_str = os.environ.get("ALPHA_CHAT_ID", "").strip()
    if alpha_chat_id_str:
        try:
            alpha_chat_id = int(alpha_chat_id_str)
            from datetime import time as _time
            alpha_hour = int(os.environ.get("ALPHA_HOUR_UTC", "9"))
            alpha_minute = int(os.environ.get("ALPHA_MINUTE_UTC", "0"))
            application.job_queue.run_daily(
                scheduled_daily_alpha,
                time=_time(hour=alpha_hour, minute=alpha_minute),
                data=(alpha_chat_id, bot),
                name="daily_alpha",
            )
            logger.info(
                f"[scheduler] Daily alpha scheduled at {alpha_hour:02d}:{alpha_minute:02d} UTC "
                f"for chat {alpha_chat_id}"
            )
        except ValueError as e:
            logger.warning(f"[scheduler] Invalid ALPHA_CHAT_ID or time config: {e}")

    logger.info("Smolting bot starting with ClawnX + cloud LLM...")

    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        import dashboard as dash

        async def _run():
            async with application:
                await application.start()
                await dash.run_server(application, port, webhook_url)
                await application.stop()

        asyncio.run(_run())
    else:
        logger.info("WEBHOOK_URL not set; running with polling (local dev).")
        application.run_polling()


if __name__ == "__main__":
    main()
