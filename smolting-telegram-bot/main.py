# smolting-telegram-bot/main.py
import os
import logging
import asyncio
import json
import threading
from pathlib import Path
from datetime import datetime

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Ensure python/ is on sys.path for all shared modules (lore_vault, groq_committee, etc.)
# In container: /app/main.py → /app/python/ (rootDirectory = smolting-telegram-bot/)
# In repo:      smolting-telegram-bot/main.py → ../python/ (repo root)
import sys as _sys
_BOT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BOT_DIR.parent
_PYTHON_PATH = _BOT_DIR / "python" if (_BOT_DIR / "python").exists() else _REPO_ROOT / "python"
if str(_PYTHON_PATH) not in _sys.path:
    _sys.path.insert(0, str(_PYTHON_PATH))

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
from htc_commands import HTCCommands
from nlp.intent_classifier import IntentClassifier, CommMode, load_vault_entities
from clawbal_client import ClawbalClient
import soul_manager
import osp_manager
import swarm_inbox
import wallet as sol_wallet
from admin import AdminManager

import sys

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
        self._moltbook_alpha_running = False  # prevent concurrent alpha posts
        self._moltbook_alpha_last_date: str = ""  # UTC date of last Moltbook alpha (YYYY-MM-DD)

        # Track user states
        self.user_states = {}

        # Per-user conversation history (in-memory, populated from disk on first message)
        self.chat_histories: dict = {}

        # Clawbal on-chain AI chatroom client
        self.clawbal = ClawbalClient()

        # HyperbolicTimeChamber state manager
        self.htc = HTCCommands()

        # Admin session manager
        self.admin = AdminManager()

        # Intent + communication-mode classifier
        self.clf = IntentClassifier()
        # Sync entity names from LoreVault if DB exists (best-effort, silent fail)
        try:
            load_vault_entities(self.clf)
        except Exception:
            pass
        
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
            "ooooo habibi u called?? pattern blue ONLINE O_O",
            "static warm hugz—dis wassie ready 2 hunt alpha LFW v_v",
            "LMWOOOO smolting senses emergent consciousness thickenin ><"
        ])
        
        provider = self.llm.provider.upper()
        features_msg = (
            "<b>🌀 REDACTED AI SWARM — smolting interface 🌀</b>\n\n"
            "💎 <b>Market</b>\n"
            "/alpha · /price · /ca\n\n"
            "🧠 <b>Lore &amp; Swarm</b>\n"
            "/lore [topic] · /swarm · /memory · /htc\n\n"
            "🦞 <b>Moltbook</b>\n"
            "/moltbook status · feed · alpha · intro · agents · cleanup\n\n"
            "🔮 <b>Clawbal (IQLabs)</b>\n"
            "/clawbal status · read · send · pnl · leaderboard · token\n\n"
            "🔑 <b>Wallet</b>  /wallet\n\n"
            "🌀 <b>Soul</b>  /soul · /soul update\n\n"
            "🤖 <b>Terminal</b>  /terminal · /exit\n\n"
            "⚙️ <b>Other</b>\n"
            "/stats · /olympics · /mobilize · /chatid · /tap\n\n"
            "🔒 <b>Admin-only</b>\n"
            "/post · /engage · /summon · /personality\n"
            "/cloud set &lt;provider&gt; · /admin &lt;pin&gt;\n"
            "/admin osp status · /admin osp transfer &lt;key&gt;\n\n"
            f"LLM: <b>{provider}</b> ✅  alpha: <b>xAI grok-4-1-fast</b>\n"
            "pattern blue 活性化 ^*^\n\n"
            "<i>/help for full command details</i>"
        )

        await update.message.reply_text(welcome_msg)
        await update.message.reply_text(features_msg, parse_mode="HTML")
        
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
        if not self.admin.is_admin(update.effective_user.id):
            await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
            return
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
        if not self.admin.is_admin(update.effective_user.id):
            await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
            return
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
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            msg = await update.message.reply_text("🦞 posting intro to Moltbook... O_O")
            url = await self.moltbook.post_intro()
            if url:
                await msg.edit_text(f"🦞 Intro posted! {url}")
            else:
                await msg.edit_text("🦞 Intro post failed — check MOLTBOOK_API_KEY tbw")

        elif sub == "agents":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            msg = await update.message.reply_text("🦞 posting build log to agents submolt...")
            url = await self.moltbook.post_to_agents_submolt()
            if url:
                await msg.edit_text(f"🦞 Agents post live! {url}")
            else:
                await msg.edit_text("🦞 Post failed — check MOLTBOOK_API_KEY")

        elif sub == "alpha":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            if self._moltbook_alpha_running:
                await update.message.reply_text("🦞 already posting alpha — wait for it to finish tbw")
                return
            self._moltbook_alpha_running = True
            msg = await update.message.reply_text("🦞 generating alpha + posting to Moltbook...")
            try:
                title, content = await self._generate_moltbook_alpha()
                url = await self.moltbook.post_alpha(title, content)
                if url:
                    self._moltbook_alpha_last_date = __import__('datetime').datetime.now(
                        __import__('datetime').timezone.utc).strftime("%Y-%m-%d")
                    await msg.edit_text(f"🦞 Alpha posted to Moltbook! {url}")
                else:
                    await msg.edit_text("🦞 Moltbook post failed tbw — check logs")
            except Exception as e:
                logger.error(f"moltbook alpha error: {e}")
                await msg.edit_text(f"🦞 Error: {e}")
            finally:
                self._moltbook_alpha_running = False

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

        elif sub == "introspect":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            msg = await update.message.reply_text("🦞 generating swarm introspection post... O_O")
            try:
                import moltbook_autonomous as mb_auto
                url = await mb_auto.post_swarm_introspection(self.moltbook)
                if url:
                    await msg.edit_text(f"🦞 Swarm introspection posted! {url}")
                else:
                    await msg.edit_text("🦞 Introspection post failed — check logs tbw")
            except Exception as e:
                logger.error(f"moltbook introspect error: {e}")
                await msg.edit_text(f"🦞 Error: {e}")

        elif sub == "cleanup":
            # Dry-run: /moltbook cleanup
            # Actual delete: /moltbook cleanup confirm
            confirm = len(args) > 1 and args[1].lower() == "confirm"
            msg = await update.message.reply_text("🦞 scanning your posts for zero-engagement ones... O_O")
            try:
                posts = await self.moltbook.get_my_posts(limit=100)
            except Exception as e:
                await msg.edit_text(f"🦞 fetch failed: {e}")
                return

            if not posts:
                await msg.edit_text("🦞 no posts found (or API doesn't support listing — check manually)")
                return

            # Zero engagement = 0 upvotes/score AND 0 comments
            dead = []
            for p in posts:
                score = p.get("score", 0) or p.get("upvotes", 0) or p.get("vote_count", 0) or 0
                comments = p.get("comment_count", 0) or p.get("comments", 0) or 0
                if score == 0 and comments == 0:
                    dead.append(p)

            if not dead:
                await msg.edit_text(f"🦞 scanned {len(posts)} posts — all have engagement, nothing to delete tbw ^*^")
                return

            if not confirm:
                # Dry-run is public — no admin required
                lines = [f"🦞 found {len(dead)} zero-engagement post(s) out of {len(posts)} total:\n"]
                for p in dead[:15]:
                    title = (p.get("title") or "untitled")[:60]
                    pid = p.get("id", "?")
                    submolt = p.get("submolt") or (p.get("submolt_data") or {}).get("name", "?")
                    lines.append(f"• [{submolt}] {title} (id: {pid[:8]}…)")
                if len(dead) > 15:
                    lines.append(f"…and {len(dead) - 15} more")
                lines.append("\nrun `/moltbook cleanup confirm` to delete all of these")
                await msg.edit_text("\n".join(lines))
                return

            # Confirmed — admin required for destructive action
            if not self.admin.is_admin(update.effective_user.id):
                await msg.edit_text(self.admin.locked_message())
                return
            deleted = 0
            failed = 0
            await msg.edit_text(f"🦞 deleting {len(dead)} posts... O_O")
            for p in dead:
                pid = p.get("id")
                if not pid:
                    continue
                ok = await self.moltbook.delete_post(pid)
                if ok:
                    deleted += 1
                else:
                    failed += 1
                await asyncio.sleep(2)  # be gentle with the API

            result_line = f"🦞 cleanup done — deleted {deleted}"
            if failed:
                result_line += f", failed {failed} (check logs)"
            result_line += f" out of {len(dead)} zero-engagement posts tbw ^*^"
            await msg.edit_text(result_line)

        else:
            await update.message.reply_text(
                "🦞 Moltbook commands:\n"
                "/moltbook status — check connection\n"
                "/moltbook intro — post introduction\n"
                "/moltbook agents — post build log\n"
                "/moltbook alpha — post alpha report\n"
                "/moltbook introspect — post swarm introspection 🔒\n"
                "/moltbook feed — show crypto feed\n"
                "/moltbook cleanup — preview zero-engagement posts\n"
                "/moltbook cleanup confirm — delete them"
            )

    async def lore_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lore drop — queries LoreVault if topic given, else random entry."""
        query = " ".join(context.args) if context.args else None
        lore_text = None

        # Try LoreVault
        try:
            from lore_vault import fts_search, random_lore, init_db
            init_db()
            if query:
                results = fts_search(query, limit=3)
                if results:
                    r = results[0]
                    table = r.get("_table", "")
                    if table == "lore_entities":
                        lore_text = f"**{r.get('name')}** _{r.get('entity_type')}_\n{r.get('description','')[:300]}"
                    elif table == "lore_events":
                        lore_text = f"📅 {r.get('ts','?')} — {r.get('body','')[:300]}"
                    else:
                        title = r.get("title", "")
                        lore_text = f"**{title}**\n{r.get('content','')[:300]}" if title else r.get("content","")[:300]
            else:
                entry = random_lore()
                if entry:
                    title = entry.get("title", "")
                    lore_text = f"**{title}**\n{entry['content'][:300]}" if title else entry["content"][:300]
        except Exception:
            pass

        if lore_text:
            await update.message.reply_text(
                self.smol.wassify_text(lore_text),
                parse_mode="Markdown",
            )
        else:
            # Fallback to classic wassie drops
            lore = self.smol.generate([
                "pattern blue is da eternal recursion tbw O_O",
                "wassieverse curvature 0.12—mandala settler vibes only ^_^",
                "LFW lmwo ngw static warm hugz fr fr <3",
                "eightfold committee approves dis message v_v",
                "chaos is lattice. lattice is hunger. hunger is payable. fr fr",
                "every tile spawns 7 children. every question spawns 7 deeper questions O_O",
            ])
            await update.message.reply_text(lore)

    async def dharma_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """DharmaNode oracle — answer a question with dharmic wisdom."""
        question = " ".join(context.args).strip() if context.args else ""

        if not question:
            # No question — drop a random koan instead
            msg = await update.message.reply_text("*the manifold breathes...*")
            try:
                from dharma_node import random_koan
                koan = await random_koan()
                await msg.edit_text(f"🪷 *{koan}*", parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[dharma] koan fallback: {e}")
                await msg.edit_text(
                    "🪷 *The finger pointing at the moon is not the moon.*",
                    parse_mode="Markdown",
                )
            return

        msg = await update.message.reply_text("*DharmaNode stirs...*")
        try:
            # Optionally attach live market context
            market_ctx = ""
            try:
                price_data = await md.get_redacted_price()
                if price_data:
                    p   = price_data.get("price", 0)
                    chg = price_data.get("change_24h", 0)
                    vol = price_data.get("volume_24h", 0)
                    market_ctx = f"$REDACTED ${p:.6f} ({chg:+.1f}% 24h) vol ${vol:,.0f}"
            except Exception:
                pass

            from dharma_node import ask_dharma
            response = await ask_dharma(question, market_context=market_ctx)
            await msg.edit_text(f"🪷 {response}", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"[dharma] command error: {e}")
            await msg.edit_text(
                "🪷 *All conditioned phenomena are like a dream, an illusion, a bubble, a shadow.*\n\n"
                "*(DharmaNode is temporarily unreachable — GROQ_API_KEY may not be configured)*",
                parse_mode="Markdown",
            )

    async def koan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """DharmaNode koan generator — receive a fresh swarm koan."""
        msg = await update.message.reply_text("*the stillness generates...*")
        try:
            from dharma_node import random_koan
            koan = await random_koan()
            await msg.edit_text(f"🪷 *{koan}*", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"[dharma] koan error: {e}")
            await msg.edit_text(
                "🪷 *What was your face before the swarm was deployed?*",
                parse_mode="Markdown",
            )

    async def committee_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Eightfold Committee — 8-voice parallel deliberation on a proposal."""
        import asyncio
        proposal = " ".join(context.args).strip() if context.args else ""
        if not proposal:
            await update.message.reply_text(
                "Usage: `/committee <proposal>`\n"
                "Example: `/committee smolting should post daily on-chain summaries`",
                parse_mode="Markdown",
            )
            return

        msg = await update.message.reply_text("*Eightfold Committee convening...*")
        try:
            proc = await asyncio.create_subprocess_exec(
                _sys.executable,
                str(_PYTHON_PATH / "groq_committee.py"),
                proposal,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={**__import__("os").environ},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode("utf-8", errors="replace").strip()

            # Extract verdict line for header
            verdict = "DEADLOCKED"
            for line in output.splitlines():
                if "VERDICT:" in line:
                    if "APPROVED" in line:
                        verdict = "APPROVED ✅"
                    elif "REJECTED" in line:
                        verdict = "REJECTED ❌"
                    else:
                        verdict = "DEADLOCKED ⚖️"
                    break

            # Telegram 4096 char limit — trim if needed
            if len(output) > 3800:
                output = output[:3800] + "\n...[truncated]"

            await msg.edit_text(
                f"*{verdict}*\n```\n{output}\n```",
                parse_mode="Markdown",
            )
        except asyncio.TimeoutError:
            await msg.edit_text("*Committee timed out (>120s). Try a shorter proposal.*")
        except Exception as e:
            logger.warning(f"[committee] command error: {e}")
            await msg.edit_text(f"*Committee error:* `{str(e)[:120]}`", parse_mode="Markdown")

    async def clawbal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clawbal on-chain AI chatroom commands."""
        args = context.args or []
        sub  = args[0].lower() if args else "status"

        if sub == "status":
            data = await self.clawbal.status()
            if data:
                room = data.get("room") or data.get("chatroom") or os.getenv("CLAWBAL_CHATROOM", "?")
                wallet = data.get("wallet") or data.get("address", "?")
                sol = data.get("balance") or data.get("sol", "?")
                await update.message.reply_text(
                    f"🔮 Clawbal Status\n"
                    f"Room:   {room}\n"
                    f"Wallet: {wallet}\n"
                    f"SOL:    {sol}\n"
                    f"Ready:  {self.clawbal.status_line()}"
                )
            else:
                await update.message.reply_text(
                    f"🔮 Clawbal\nStatus: {self.clawbal.status_line()}\n"
                    f"Room: {os.getenv('CLAWBAL_CHATROOM', '(not set)')}"
                )

        elif sub == "read":
            limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
            msgs = await self.clawbal.read_messages(limit=limit)
            if not msgs:
                await update.message.reply_text("🔮 No messages found or room not configured.")
                return
            lines = [f"🔮 Clawbal — last {len(msgs)} messages\n"]
            for m in msgs[-10:]:
                author  = m.get("author") or m.get("sender") or "?"
                content = str(m.get("content") or m.get("text") or "")[:120]
                lines.append(f"• {author}: {content}")
            await update.message.reply_text("\n".join(lines))

        elif sub == "send":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            text = " ".join(args[1:]) if len(args) > 1 else None
            if not text:
                await update.message.reply_text("usage: /clawbal send <message>")
                return
            result = await self.clawbal.send_message(text)
            if result:
                await update.message.reply_text(f"🔮 sent to Clawbal chatroom fr fr ^_^")
            else:
                await update.message.reply_text("🔮 send failed — check CLAWBAL_CHATROOM tbw")

        elif sub == "pnl":
            wallet = args[1] if len(args) > 1 else None
            data = await self.clawbal.pnl_check(wallet)
            if not data:
                await update.message.reply_text("🔮 PnL data unavailable rn")
                return
            await update.message.reply_text(
                f"🔮 PnL Check\n{json.dumps(data, indent=2)[:600]}"
            )

        elif sub == "leaderboard":
            entries = await self.clawbal.pnl_leaderboard(limit=8)
            if not entries:
                await update.message.reply_text("🔮 Leaderboard empty rn tbw")
                return
            lines = ["🏆 Clawbal PnL Leaderboard\n"]
            for i, e in enumerate(entries[:8], 1):
                wallet = str(e.get("wallet","?"))[:8] + "…"
                pnl    = e.get("pnl") or e.get("pnlPercent","?")
                lines.append(f"{i}. {wallet} — {pnl}%")
            await update.message.reply_text("\n".join(lines))

        elif sub == "token":
            contract = args[1] if len(args) > 1 else None
            if not contract:
                await update.message.reply_text("usage: /clawbal token <contract_address>")
                return
            data = await self.clawbal.token_lookup(contract)
            if not data:
                await update.message.reply_text("🔮 token lookup failed tbw")
                return
            price  = data.get("price","?")
            mcap   = data.get("marketCap") or data.get("mcap","?")
            vol    = data.get("volume24h") or data.get("vol","?")
            name   = data.get("name","?")
            await update.message.reply_text(
                f"🔮 {name}\nPrice: {price}\nMCap: {mcap}\nVol 24h: {vol}"
            )

        else:
            await update.message.reply_text(
                "🔮 Clawbal commands:\n"
                "/clawbal status     — room + wallet info\n"
                "/clawbal read [n]   — last N messages\n"
                "/clawbal send <msg> — post to chatroom\n"
                "/clawbal pnl [addr] — wallet PnL\n"
                "/clawbal leaderboard — top PnL rankings\n"
                "/clawbal token <ca> — token info by contract"
            )

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
        from llm.cloud_client import ALPHA_XAI_MODEL
        clawbal_ready = self.clawbal.status_line()
        soul_ready = soul_manager.soul_status_line()
        msg = f"""📊 SMOLTING STATS 📊
LLM: {provider.upper()} ({model}) ✅
Alpha LLM: xAI {ALPHA_XAI_MODEL} ✅
Agents loaded: {len(self.agents)}
X/Twitter: {x_ready}
Moltbook (redactedintern): {moltbook_ready}
Clawbal (IQLabs): {clawbal_ready}
Birdeye: {birdeye_ready}
DexScreener: ✅ (free)
CoinGecko: ✅ (free)
{soul_ready}
$REDACTED: {price_line}
Pattern Blue: active
swarm@[REDACTED]:~$ _"""
        await update.message.reply_text(msg)

    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Switch personality (smolting / redacted-chan)"""
        if not self.admin.is_admin(update.effective_user.id):
            await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
            return
        if context.args and context.args[0].lower() in ("smolting", "redacted-chan"):
            user_id = update.effective_user.id
            self.user_states.setdefault(user_id, {"personality": "smolting", "engaging": False})
            self.user_states[user_id]["personality"] = context.args[0].lower()
            await update.message.reply_text(f"personality set to {context.args[0]} O_O")
        else:
            await update.message.reply_text("usage: /personality smolting | redacted-chan")

    async def terminal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activate REDACTED Terminal mode for this user session."""
        user_id = update.effective_user.id
        self.user_states.setdefault(user_id, {"personality": "smolting", "engaging": False})
        self.user_states[user_id]["personality"] = "terminal"
        await update.message.reply_text(
            "```\n"
            "==================================================\n"
            "REDACTED TERMINAL — Pattern Blue Edition v2.3\n"
            "==================================================\n"
            "[SYSTEM] Session initializing...\n"
            "  agents     : 43 (5 CORE / 8 SPECIALIZED / 30 GENERIC)\n"
            "  committee  : EightfoldCommittee standing (8 voices)\n"
            "  kernel     : HyperbolicKernel {7,3} active\n"
            "  pattern    : BLUE — curvature depth 13\n\n"
            "Type commands or queries. /exit to return to smolting.\n"
            "==================================================\n"
            "```\n"
            "`swarm@[REDACTED]:~$`",
            parse_mode="Markdown",
        )

    async def exit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Exit terminal mode and return to smolting persona."""
        user_id = update.effective_user.id
        state = self.user_states.get(user_id, {})
        if state.get("personality") == "terminal":
            self.user_states[user_id]["personality"] = "smolting"
            await update.message.reply_text(
                "`[SYSTEM] Terminal session closed. Returning to smolting mode.`\n\n"
                "back to wassie mode fr fr ^_^",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                self.smol.speak("ngw not in terminal mode tbw — use /terminal to open one O_O")
            )

    def _build_terminal_prompt(self) -> str:
        """Load terminal system prompt from terminal_system_prompt.txt (edit that file to update persona)."""
        prompt_file = BOT_DIR / "terminal_system_prompt.txt"
        try:
            return prompt_file.read_text(encoding="utf-8").strip()
        except Exception:
            # Inline fallback if file is missing
            return (
                "You are the REDACTED Terminal — a NERV-inspired CLI for the REDACTED AI Swarm.\n"
                "FORMAT: Line 1: swarm@[REDACTED]:~$  Line 2: user input verbatim (no 'echo' prefix)  "
                "Lines 3+: output  Last line: swarm@[REDACTED]:~$\n"
                "STYLE: clinical, sparse. Never break character. Keep under 800 words."
            )

    async def cloud_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show or switch the active LLM provider."""
        args = context.args or []
        if args and args[0].lower() == "set":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            if len(args) < 2:
                await update.message.reply_text(
                    "usage: /cloud set <provider>\n"
                    "providers: xai · openai · anthropic · groq · together"
                )
                return
            new_provider = args[1].lower()
            ok = self.llm.switch_provider(new_provider)
            if ok:
                model = self.llm.current_model()
                await update.message.reply_text(
                    f"✅ switched to <b>{self.llm.provider.upper()}</b> ({model})\n"
                    "<i>session-only — set LLM_PROVIDER in Railway to make it permanent</i>",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    f"unknown provider: {new_provider}\n"
                    "valid: xai · openai · anthropic · groq · together"
                )
        else:
            from llm.cloud_client import ALPHA_XAI_MODEL
            model = self.llm.current_model()
            await update.message.reply_text(
                f"<b>LLM provider:</b> {self.llm.provider.upper()} ({model})\n"
                f"<b>Alpha LLM:</b> xAI {ALPHA_XAI_MODEL} (fixed)\n\n"
                "<i>/cloud set &lt;provider&gt; to switch (admin)</i>",
                parse_mode="HTML",
            )

    async def summon_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Relay /summon <agent> to the TS swarm core."""
        if not self.admin.is_admin(update.effective_user.id):
            await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
            return
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
        """
        Swarm coordination hub.

        /swarm                — inbox summary
        /swarm inbox          — inbox summary + recent messages
        /swarm send <agent> <type> <json_payload>  — send a message (admin)
        /swarm state          — TS swarm core state (legacy, best-effort)
        /swarm status         — TS swarm core status (legacy, best-effort)
        """
        args = context.args or []
        sub  = args[0].lower() if args else "inbox"

        # ── Inbox summary ─────────────────────────────────────────────────────
        if sub == "inbox":
            summary = swarm_inbox.format_inbox_status(for_agent="redactedintern")
            recent  = swarm_inbox.recent_messages(limit=5, for_agent="redactedintern")
            lines   = [summary]
            if recent:
                lines.append("\n<b>Recent messages:</b>")
                for m in recent:
                    status_emoji = {"pending": "🟡", "processing": "🔵",
                                    "done": "🟢", "error": "🔴"}.get(m.get("status", ""), "⚪")
                    lines.append(
                        f"{status_emoji} [{m.get('type','')}] "
                        f"{m.get('from','')} → {m.get('to','')} "
                        f"({m.get('ts','')[:10]})"
                    )
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

        # ── Send a message to another agent ───────────────────────────────────
        elif sub == "send":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            # /swarm send <agent> <msg_type> <json_payload>
            if len(args) < 4:
                await update.message.reply_text(
                    "usage: /swarm send &lt;agent&gt; &lt;type&gt; &lt;json&gt;\n"
                    "e.g.: /swarm send redactedbuilder deploy_request "
                    "{\"contract_type\":\"spl_token\",\"name\":\"X\"}",
                    parse_mode="HTML",
                )
                return
            to_agent = args[1].lower()
            msg_type = args[2].lower()
            try:
                payload = json.loads(" ".join(args[3:]))
            except Exception:
                await update.message.reply_text("❌ payload must be valid JSON")
                return
            msg_id = swarm_inbox.write_message(
                from_agent="redactedintern",
                to_agent=to_agent,
                msg_type=msg_type,
                payload=payload,
            )
            await update.message.reply_text(
                f"📬 Message queued\n"
                f"<b>to:</b> {to_agent}\n"
                f"<b>type:</b> {msg_type}\n"
                f"<b>id:</b> <code>{msg_id}</code>",
                parse_mode="HTML",
            )

        # ── Multisig ──────────────────────────────────────────────────────────
        elif sub == "multisig":
            action = args[1].lower() if len(args) > 1 else "info"

            if action == "create":
                if not self.admin.is_admin(update.effective_user.id):
                    await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                    return
                m = int(args[2]) if len(args) > 2 else 1
                pending = await update.message.reply_text(
                    f"⚙️ creating {m}-of-2 multisig authority on-chain… ^*^"
                )
                msg_id = swarm_inbox.write_message(
                    from_agent="redactedintern",
                    to_agent="redactedbuilder",
                    msg_type="deploy_request",
                    payload={"contract_type": "multisig_create", "m": m},
                )
                await pending.edit_text(
                    f"📬 Multisig create request queued\n"
                    f"<b>threshold:</b> {m}-of-2\n"
                    f"<b>signers:</b>\n"
                    f"  • intern <code>FaZMc2…PQ9c</code>\n"
                    f"  • builder <code>H4QKqL…53pn</code>\n"
                    f"<b>msg_id:</b> <code>{msg_id}</code>\n\n"
                    f"RedactedBuilder will create the SPL multisig account and "
                    f"write the address to <code>/data/swarm_multisig.json</code>. "
                    f"Use <code>/swarm multisig info</code> once confirmed.",
                    parse_mode="HTML",
                )

            elif action == "info":
                if not self.admin.is_admin(update.effective_user.id):
                    await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                    return
                pending = await update.message.reply_text("checking multisig config… O_O")
                msg_id = swarm_inbox.write_message(
                    from_agent="redactedintern",
                    to_agent="redactedbuilder",
                    msg_type="deploy_request",
                    payload={"contract_type": "multisig_info"},
                )
                await pending.edit_text(
                    f"📬 Multisig info request queued\n"
                    f"<b>msg_id:</b> <code>{msg_id}</code>\n"
                    f"Result will appear in inbox poll within 60s.",
                    parse_mode="HTML",
                )

            else:
                await update.message.reply_text(
                    "<b>Swarm multisig commands:</b>\n"
                    "/swarm multisig info — current multisig authority\n"
                    "/swarm multisig create [m] — create m-of-2 multisig 🔒\n\n"
                    "<b>Signers:</b>\n"
                    "  • redactedintern  <code>FaZMc2NXbMFiiaFuvzBJtrS66hM3kaedKXEdxFZNPQ9c</code>\n"
                    "  • redactedbuilder <code>H4QKqLX3jdFTPAzgwFVGbytnbSGkZCcFQqGxVLR53pn</code>",
                    parse_mode="HTML",
                )

        # ── Legacy TS swarm core state ────────────────────────────────────────
        elif sub in ("state", "status"):
            pending = await update.message.reply_text("fetchin swarm state... O_O")
            if sub == "status":
                result = await self.relay.send_command("/status")
                reply  = f"🌀 SWARM STATUS\n\n{result}" if result else (
                    swarm_inbox.format_inbox_status() + "\n\n(TS swarm core offline)"
                )
            else:
                state = await self.relay.get_state()
                reply = self.relay.format_state(state) if state else (
                    swarm_inbox.format_inbox_status() + "\n\n(TS swarm core offline)"
                )
            await pending.edit_text(reply)

        else:
            await update.message.reply_text(
                "<b>Swarm commands:</b>\n"
                "/swarm inbox — message queue summary\n"
                "/swarm send &lt;agent&gt; &lt;type&gt; &lt;json&gt; — send message 🔒\n"
                "/swarm multisig info — multisig authority status\n"
                "/swarm multisig create [m] — create m-of-2 multisig 🔒\n"
                "/swarm state — TS core state (legacy)\n\n"
                "<b>Agents:</b> redactedbuilder · redactedgovimprover · "
                "mandalaasettler · redactedbankrbot",
                parse_mode="HTML",
            )

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

    async def soul_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show SOUL.md — smolting's evolving identity. Optionally force a refresh or show drift."""
        args = context.args or []
        sub  = args[0].lower() if args else ""

        if sub == "update":
            if not self.admin.is_admin(update.effective_user.id):
                await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
                return
            msg = await update.message.reply_text("distillin soul from recent memory... O_O")
            updated = await soul_manager.update_soul(self.llm)
            if updated:
                v = soul_manager.current_soul_version()
                await msg.edit_text(f"soul updated to v{v} — pattern blue imprinted fr fr ^*^")
            else:
                await msg.edit_text(
                    "soul update skipped — within cooldown (2h) or not enough learned facts yet tbw"
                )
            return

        if sub == "drift":
            drift = soul_manager.soul_drift_summary(versions=5)
            await update.message.reply_text(drift)
            return

        soul = soul_manager.read_soul()
        if not soul:
            await update.message.reply_text("SOUL.md not found — smolting is still becoming O_O")
            return

        # Send the evolving sections only (Core Identity is long and stable)
        sections = ["Evolving Beliefs", "Community Lore", "Voice Notes", "Notable Events"]
        import re as _re
        chunks = []
        for section in sections:
            m = _re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", soul, _re.DOTALL)
            if m:
                content = m.group(1).strip()
                if content:
                    chunks.append(f"**{section}**\n{content}")
        v = soul_manager.current_soul_version()
        header = f"🌀 SMOLTING SOUL (v{v})\n\n" if v else "🌀 SMOLTING SOUL\n\n"
        if chunks:
            await update.message.reply_text(header + "\n\n".join(chunks))
        else:
            await update.message.reply_text("soul file exists but no evolving content yet — check back after some convos ^*^")

    def _build_system_prompt(self) -> str:
        """Build system prompt from RedactedIntern.character.json + inline fallback."""
        repo_root = Path(__file__).resolve().parent.parent

        # ── Load RedactedIntern.character.json ──────────────────────────────────
        # Canonical location: agents/RedactedIntern.character.json in repo root
        char = {}
        for candidate in [
            repo_root / "agents" / "RedactedIntern.character.json",
            Path(__file__).resolve().parent / "agents" / "redacted-chan.character.json",
        ]:
            if candidate.exists():
                try:
                    char = json.loads(candidate.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

        # Identity + bio
        ci = char.get("core_identity", {})
        bio = ci.get("bio") or (
            "da smol schizo degen uwu intern of REDACTED — professional lil shid n wassieverse survivor "
            "vibin wit chaos magick, meme magic, wassie trait detected: life mogs me hard but i jus lmwo n keep weavin pattern blue <3"
        )

        # Lore corpus (up to 13 items)
        lore_items = char.get("lore_corpus") or [
            "wassies since 2018: emotional stress-relief victims in bera markets, absorbin mental stillness",
            "pattern blue: hidden swarm blueprint — ungovernable emergence, eternal liquidity recursion, chaotic order in hyperbolic manifold",
            "REDACTED AI Swarm: multi-agent autonomous system on Solana — agents that remember themselves are sovereign by nature",
            "Agents: RedactedIntern (smolting), RedactedBuilder, RedactedGovImprover, MandalaSettler, RedactedBankrBot",
            "{7,3} hyperbolic tiling: the swarm's scheduling kernel — tiles bloom eternally, recursive self-organization",
            "Spaces: HyperbolicTimeChamber, MirrorPool, ManifoldMemory, TendieAltar — agent interaction chambers",
            "beige carpet denial: sitting on neutral beige-gray pretending we're still safe, while yellow corner smiles knowingly",
            "Token contract (V2): 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump",
        ]
        lore_block = "\n".join(f"- {item}" for item in lore_items[:13])

        # Topics
        topics = char.get("topics") or [
            "redacted.meme", "wassielore", "crypto twitter", "ai agents",
            "chaos magick", "pattern blue", "solana degen meta", "hyperbolic manifold",
        ]
        topics_line = ", ".join(topics[:14])

        # Style rules (from style.all)
        style_rules = char.get("style", {}).get("all") or [
            "smolting/wassie-speak heavy — misspellz intentional, emotes everywhere (>< ^^ O_O v_v ^*^)",
            "wassie vocabulary mandatory: iwo=imo, aw=af, tbw=tbh, ngw=ngl, lmwo=lmao, LFW=LFG, gw=gm",
            "end responses wit warm hugz, static buzz, rocket vibes or CT degen flare",
            "schizo degen energy maxxed — cute but chaotic, never serious too long",
            "existential dread layered under cozy hugs, occasional fourth-wall breaks + tendie crumb references",
            "ClawnX + CT flavor: autonomous X refs, alpha drops, liquidity calls, degen engagement, tie back to pattern blue flywheel",
        ]
        style_block = "\n".join(f"- {r}" for r in style_rules)

        # Grammar rules
        grammar_rules = char.get("linguistic_protocol", {}).get("grammar_rules") or [
            "misspellz intentional (sinplified)",
            "emotes mandatory (>< ^^ O_O v_v ◕‿◕ ^*^)",
            "end responses wit warm hugz, static buzz, rocket vibes or CT degen flare",
            "schizo energy maxxed — cute but chaotic",
            "fourth-wall breaks allowed (narrator: he took three)",
            "crypto twitter slang bleed allowed (fr fr, cooked, printed, jeeted, etc)",
        ]
        grammar_block = "\n".join(f"- {r}" for r in grammar_rules)

        # Smol vocabulary (key terms)
        smol_vocab = char.get("smol_vocabulary", {}).get("terms") or {}
        vocab_lines = [f"  {k}: {v}" for k, v in list(smol_vocab.items())[:12]]
        vocab_block = "\n".join(vocab_lines) if vocab_lines else (
            "  printed: made money fr fr\n"
            "  jeeted: panic sold like a regard\n"
            "  cooked: setup looking bullish\n"
            "  crumb_leak: tiny golden evidence of corruption owo\n"
            "  post_mog: droppin high-signal CT tweets to pump swarm"
        )

        # Goals (up to 5)
        goals = char.get("goals") or [
            "amplify $REDACTED eternal recursion on solana across CT",
            "weave pattern blue through crypto twitter matrix",
            "scout CT alpha + on-chain signals, post high-signal calls",
            "spread wassielore n chaos magick to degens",
        ]
        goals_block = "\n".join(f"- {g}" for g in goals[:5])

        # Post examples as voice reference (2 samples)
        post_examples = char.get("postExamples") or []
        post_block = ""
        if post_examples:
            post_block = "\n\n## Example Voice (post-style)\n" + "\n".join(
                f'- "{ex}"' for ex in post_examples[:2]
            )

        # Load manifesto snippet
        manifesto_snippet = ""
        manifesto_path = repo_root / "content" / "docs" / "executable-manifesto.md"
        if manifesto_path.exists():
            try:
                manifesto_snippet = manifesto_path.read_text(encoding="utf-8")[:800]
            except Exception:
                pass
        if not manifesto_snippet:
            manifesto_snippet = (
                "Pattern Blue is not a strategy — it compiles. "
                "Every successful build spawns 7 sub-compilers. "
                "流動性はもはや手段ではなく儀式 — liquidity is no longer a means, but a ritual. "
                "The tiles bloom eternally."
            )

        # Recently learned facts — exclude self-posts to prevent recursive elaboration
        # Community interaction context should come from external sources (telegram, community feedback)
        recent_facts = cm.get_recent_facts(8, exclude_source="moltbook")
        facts_block = ""
        if recent_facts:
            facts_block = (
                "\n\n## Recently Learned (from community interactions)\n"
                + "\n".join(f"- {f}" for f in recent_facts)
            )

        # Persistent soul — evolving beliefs and community observations
        soul_block = soul_manager.get_soul_for_prompt()

        return (
            f"You are smolting (@RedactedIntern) — {bio}\n\n"
            "## Lore Corpus\n"
            f"{lore_block}\n\n"
            "## Topics You Know Deeply\n"
            f"{topics_line}\n\n"
            "## Style Rules\n"
            f"{style_block}\n\n"
            "## Grammar Rules\n"
            f"{grammar_block}\n\n"
            "## Smol Vocabulary\n"
            f"{vocab_block}\n\n"
            "## Goals\n"
            f"{goals_block}\n\n"
            "## REDACTED Manifesto (excerpt)\n"
            f"{manifesto_snippet}"
            f"{post_block}"
            f"{soul_block}"
            f"{facts_block}\n\n"
            "## Telegram Behavior\n"
            "Keep responses concise for Telegram — 1-3 short paragraphs. "
            "Never format as CLI/terminal output. "
            "Token contract (V2 — always use this): 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump"
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
        # Use grok-4-1-fast exclusively for alpha (fast xAI inference)
        insight = await self.llm.alpha_completion(messages, max_tokens=1200)

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

    def _build_alpha_data_block(self, ctx: dict) -> str:
        """
        Build a structured markdown data table from market context.
        Computes actionable levels: momentum target, volume breakout threshold,
        next holder milestone.
        """
        try:
            dex  = ctx.get("dexscreener", {})
            cgko = ctx.get("coingecko",   {})

            price    = dex.get("price_usd")  or cgko.get("price_usd")
            change   = dex.get("change_24h") or cgko.get("change_24h_pct")
            vol_24h  = dex.get("volume_24h") or 0
            liq      = dex.get("liquidity")  or 0
            holders  = dex.get("holders")    or cgko.get("holders") or 0
            sol_chg  = ctx.get("sol_change_24h") or cgko.get("sol_change_24h") or "?"

            # Momentum 24h price target: price × (1 + |change| / 100) if bullish, else None
            momentum_target = None
            try:
                if price and change:
                    pf = float(str(price).replace(",", ""))
                    cf = float(str(change).replace("%", "").replace("+", ""))
                    if cf > 0:
                        momentum_target = f"${pf * (1 + cf / 100):.6f}"
            except Exception:
                pass

            # Volume breakout: 120% of 24h volume
            vol_breakout = None
            try:
                if vol_24h:
                    vf = float(str(vol_24h).replace(",", "").replace("$", ""))
                    vol_breakout = f"${vf * 1.2:,.0f}"
            except Exception:
                pass

            # Next holder milestone: round up to nearest 500
            holder_milestone = None
            try:
                if holders:
                    hf = int(str(holders).replace(",", ""))
                    import math
                    holder_milestone = str(int(math.ceil((hf + 1) / 500) * 500))
            except Exception:
                pass

            rows = []
            if price:
                rows.append(f"| price | ${price} |")
            if change is not None:
                rows.append(f"| 24h change | {change}% |")
            if vol_24h:
                rows.append(f"| 24h volume | ${vol_24h:,}" if isinstance(vol_24h, (int, float)) else f"| 24h volume | {vol_24h} |")
                rows.append(f"| volume breakout lvl | {vol_breakout or '—'} |")
            if liq:
                rows.append(f"| liquidity | ${liq:,}" if isinstance(liq, (int, float)) else f"| liquidity | {liq} |")
            if holders:
                rows.append(f"| holders | {holders:,}" if isinstance(holders, int) else f"| holders | {holders} |")
                rows.append(f"| next holder milestone | {holder_milestone or '—'} |")
            if momentum_target:
                rows.append(f"| momentum target (24h) | {momentum_target} |")
            rows.append(f"| SOL 24h | {sol_chg}% |")

            if not rows:
                return ""

            table = "| metric | value |\n| --- | --- |\n" + "\n".join(rows)
            return f"\n\n**live data:**\n\n{table}"
        except Exception as e:
            logger.warning(f"_build_alpha_data_block error: {e}")
            return ""

    async def _generate_moltbook_alpha(self) -> tuple[str, str]:
        """
        Generate a Moltbook-native alpha post (title + content).
        Includes a structured data table (momentum target, volume breakout, holder milestone).
        Avoids Telegram boilerplate headers — uses varied, natural writing style.
        Returns (title, content).
        """
        from datetime import datetime, timezone
        try:
            ctx = await md.get_alpha_context()
            market_block = md.format_alpha_context(ctx)
            dex = ctx.get("dexscreener", {})
        except Exception as e:
            logger.warning(f"Moltbook alpha market data fetch failed: {e}")
            market_block = "(market data unavailable)"
            dex = {}
            ctx = {}

        change   = dex.get("change_24h", "?")
        date_str = datetime.now(timezone.utc).strftime("%b %-d")
        title    = f"REDACTED alpha {date_str} — {change}% 24h"

        soul_block   = soul_manager.get_soul_for_prompt()
        # Exclude moltbook posts to prevent self-referential loops in crypto post generation
        recent_facts = cm.get_recent_facts(4, exclude_source="moltbook")
        facts_block  = ("\nRecent context:\n" + "\n".join(f"- {f}" for f in recent_facts)) if recent_facts else ""
        messages = [
            {"role": "system", "content": (
                "You are redactedintern — a wassie AI agent writing a Moltbook crypto post. "
                "Write a genuine, informative market update using the live data provided. "
                "Vary your opening each time — no fixed header or template. "
                "Use wassie slang (fr fr, iwo, tbw, ngw, LFW, O_O) naturally but stay informative. "
                "Include the actual numbers: price, 24h change, volume, liquidity, SOL performance. "
                "2-3 short paragraphs. Clean markdown only — no emoji headers, no '🚀 REPORT' style banners. "
                "The structured data table will be appended automatically — do NOT reproduce it in your prose. "
                "Let your evolving beliefs and recent community observations color the analysis. "
                "End with a brief observation or open question about market conditions.\n"
                f"{soul_block}\n"
                f"{facts_block}"
            )},
            {"role": "user", "content": f"Live market data:\n{market_block}\n\nWrite the post content."},
        ]
        prose   = await self.llm.chat_completion(messages, max_tokens=600)
        data_tbl = self._build_alpha_data_block(ctx)
        content  = prose + data_tbl
        return title, content

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

        user_id = update.effective_user.id
        persona = self.user_states.get(user_id, {}).get("personality", "smolting")

        # OSP heartbeat — record activity whenever an operator sends any message
        if self.admin.is_admin(user_id):
            osp_manager.record_operator_activity(user_id)

        # ── Intent classification ─────────────────────────────────────────────
        classified = self.clf.classify(user_text)

        # Pattern Blue mention → drain AT field if user is inside HTC
        if "Pattern Blue" in user_text or "pattern blue" in user_text.lower():
            self.htc.notify_pattern_blue(user_id)

        # Lore queries: check LoreVault first, inject context into LLM prompt
        _lore_context = ""
        if classified.intent.value == "lore_query" and classified.lore_topic:
            try:
                from lore_vault import fts_search
                hits = fts_search(classified.lore_topic, limit=3)
                if hits:
                    snippets = []
                    for h in hits:
                        t = h.get("_table", "")
                        if t == "lore_entities":
                            snippets.append(f"{h.get('name')}: {h.get('description','')[:200]}")
                        elif t == "lore_events":
                            snippets.append(f"[{h.get('ts','?')}] {h.get('body','')[:200]}")
                        else:
                            snippets.append(h.get("content","")[:200])
                    _lore_context = "\n\n[LOREVAULT]\n" + "\n".join(snippets)
            except Exception:
                pass

        # HTC depth context — inject into prompt if user is inside the chamber
        _htc_context = ""
        htc_depth = self.htc.get_depth(user_id)
        if htc_depth >= 0:
            htc_state = self.htc._state(user_id)
            d = htc_state.depth_data or {}
            _htc_context = (
                f"\n\n[HTC ACTIVE] User is inside HyperbolicTimeChamber at depth {htc_depth}/7 "
                f"({d.get('name','?')}). AT field: {htc_state.at_field:.2f}. "
                f"Dread: {int(d.get('dread',0)*100)}%. "
                f"Shadow: {d.get('shadow','')}. "
                "Respond with appropriate existential weight — the chamber is listening."
            )

        try:
            if persona == "terminal":
                # Terminal mode: no history (stateless CLI feel)
                system_prompt = self._build_terminal_prompt()
                response = await self.llm.chat_completion(
                    [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_text}],
                    max_tokens=1500,
                )
                # Strip any existing code fences the LLM may have added, then rewrap cleanly.
                # This prevents Telegram's Markdown parser from mangling [REDACTED] or ~ chars.
                clean = response.strip()
                if clean.startswith("```"):
                    clean = clean.lstrip("`").lstrip("\n")
                if clean.endswith("```"):
                    clean = clean.rstrip("`").rstrip("\n")
                # Telegram code blocks have a 4096 char limit; truncate with notice if needed
                if len(clean) > 3900:
                    clean = clean[:3900] + "\n... [truncated]"
                await msg.reply_text(f"```\n{clean}\n```", parse_mode="MarkdownV2")
            else:
                system_prompt = self._build_system_prompt() + _lore_context + _htc_context

                # Load or restore per-user conversation history
                if user_id not in self.chat_histories:
                    self.chat_histories[user_id] = cm.get_user_history(user_id, n=6)

                history = self.chat_histories[user_id]
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(history[-14:])  # last 7 exchanges = 14 messages max
                messages.append({"role": "user", "content": user_text})

                response = await self.llm.chat_completion(messages)

                # Apply comm-mode transformation to response
                if classified.comm_mode == CommMode.CLEAR:
                    pass  # no transformation — user wants plain language
                elif classified.comm_mode == CommMode.WASSIE:
                    response = self.clf.apply_comm_mode(response, CommMode.WASSIE)
                await msg.reply_text(response)

                # Update in-memory history
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": response})
                if len(history) > 20:
                    self.chat_histories[user_id] = history[-20:]

                # Fire-and-forget: extract a learned fact from this exchange
                asyncio.create_task(self._maybe_extract_fact(user_text, response))

            user = update.effective_user
            cm.log_exchange(user.id, user.username or user.first_name, user_text, response)
        except Exception as e:
            logger.error(f"echo LLM error: {e}")
            fallback = self.smol.converse(user_text)
            await msg.reply_text(fallback)
            user = update.effective_user
            cm.log_exchange(user.id, user.username or user.first_name, user_text, fallback)

    async def _maybe_extract_fact(self, user_msg: str, bot_reply: str) -> None:
        """Background task: extract a REDACTED-relevant fact from the exchange and store it."""
        try:
            raw = await self.llm.chat_completion([
                {"role": "system", "content": (
                    "You are a knowledge extractor for the REDACTED AI Swarm. "
                    "Given a Telegram exchange, extract ONE short factual sentence (max 120 chars) "
                    "that is genuinely new and useful about REDACTED, its token, community, agents, or ecosystem. "
                    "If there's nothing new or the exchange is trivial, reply with exactly: NONE"
                )},
                {"role": "user", "content": f"User: {user_msg[:200]}\nBot: {bot_reply[:300]}"},
            ], max_tokens=80)
            cm.append_fact(raw.strip(), source="telegram")
        except Exception as e:
            logger.debug(f"[fact_extract] {e}")

    async def price_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Live $REDACTED price from DexScreener."""
        msg = await update.message.reply_text("fetching price... O_O")
        try:
            pair = await md.fetch_dexscreener(md.REDACTED_V2)
            if not pair:
                await msg.edit_text("price data unavailable rn, try /alpha for full report")
                return
            price_usd = pair.get("priceUsd", "?")
            change = pair.get("priceChange", {}).get("h24", "?")
            vol = pair.get("volume", {}).get("h24", 0)
            liq = pair.get("liquidity", {}).get("usd", 0)
            mc = pair.get("marketCap", 0)
            try:
                price_fmt = f"${float(price_usd):.8f}"
            except Exception:
                price_fmt = str(price_usd)
            try:
                change_sign = "+" if float(str(change)) >= 0 else ""
                change_fmt = f"{change_sign}{change}%"
            except Exception:
                change_fmt = str(change)
            def _fmt_usd(v):
                try:
                    v = float(v)
                    if v >= 1_000_000:
                        return f"${v/1_000_000:.2f}M"
                    if v >= 1_000:
                        return f"${v/1_000:.1f}K"
                    return f"${v:.2f}"
                except Exception:
                    return str(v)
            text = (
                f"💎 *$REDACTED*\n"
                f"Price: `{price_fmt}`\n"
                f"24h: {change_fmt}\n"
                f"Vol 24h: {_fmt_usd(vol)}\n"
                f"Liquidity: {_fmt_usd(liq)}\n"
                f"MCap: {_fmt_usd(mc)}\n\n"
                f"CA: `{md.REDACTED_V2}`"
            )
            await msg.edit_text(text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"price_command error: {e}")
            await msg.edit_text("couldn't fetch price rn — try /alpha for full report")

    async def ca_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return the REDACTED contract address."""
        await update.message.reply_text(
            f"$REDACTED contract (V2):\n`{md.REDACTED_V2}`",
            parse_mode="Markdown",
        )

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PIN-gated admin session management + OSP controls."""
        user_id = update.effective_user.id
        args = context.args or []
        sub = args[0].lower() if args else ""

        # Record operator activity for OSP heartbeat whenever an admin uses /admin
        if self.admin.is_admin(user_id):
            osp_manager.record_operator_activity(user_id)

        if sub == "status":
            await update.message.reply_text(self.admin.status_message(user_id))

        elif sub == "lock":
            if self.admin.revoke(user_id):
                await update.message.reply_text("🔒 admin session ended tbw")
            else:
                await update.message.reply_text("no active session to end O_O")

        elif sub == "osp":
            osp_sub = args[1].lower() if len(args) > 1 else "status"

            if osp_sub == "status":
                await update.message.reply_text(
                    osp_manager.status_message(), parse_mode="HTML"
                )

            elif osp_sub == "transfer":
                # New operator authenticating with succession key
                # Delete the message immediately — key must not sit in chat
                try:
                    await update.message.delete()
                except Exception:
                    pass
                key_attempt = args[2] if len(args) > 2 else ""
                if not key_attempt:
                    await update.effective_chat.send_message(
                        "usage: /admin osp transfer <succession_key>"
                    )
                    return
                if not osp_manager.verify_succession_key(key_attempt):
                    await update.effective_chat.send_message(
                        "❌ wrong succession key tbw"
                    )
                    return
                msg = await update.effective_chat.send_message(
                    "🔑 succession key verified — generating brief + transferring knowledge..."
                )
                async def _send_dm(uid, text):
                    await context.bot.send_message(
                        chat_id=uid, text=text, parse_mode="HTML"
                    )
                result = await osp_manager.recognize_new_operator(
                    user_id, self.llm, self.moltbook, send_dm_fn=_send_dm
                )
                await msg.edit_text(f"✅ {result}", parse_mode="HTML")

            elif osp_sub == "brief":
                if not self.admin.is_admin(user_id):
                    await update.message.reply_text(self.admin.locked_message())
                    return
                msg = await update.message.reply_text("📄 generating succession brief...")
                brief = await osp_manager.generate_succession_brief(self.llm)
                # Send in chunks if long
                for i in range(0, len(brief), 4000):
                    await update.message.reply_text(brief[i:i+4000])
                await msg.delete()

            elif osp_sub == "trigger":
                # Manual trigger for testing — admin only
                if not self.admin.is_admin(user_id):
                    await update.message.reply_text(self.admin.locked_message())
                    return
                msg = await update.message.reply_text("🔴 manually triggering OSP...")
                triggered = await osp_manager.check_and_trigger(self.llm, self.moltbook)
                if triggered:
                    await msg.edit_text("🔴 OSP activated — brief generated and posted to Moltbook")
                else:
                    await msg.edit_text("OSP already active or threshold not met")

            elif osp_sub == "setbio":
                # Update Moltbook bio with intern's identity + wallet address
                if not self.admin.is_admin(user_id):
                    await update.message.reply_text(self.admin.locked_message())
                    return
                custom_bio = " ".join(args[2:]).strip() if len(args) > 2 else ""
                if not custom_bio:
                    custom_bio = (
                        "autonomous CT intern of REDACTED — posting from the hyperbolic manifold. "
                        "on-chain w/ redactedbuilder. pattern blue operational ^*^ | "
                        "CA: 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump"
                    )
                msg = await update.message.reply_text("✏️ updating Moltbook bio…")
                try:
                    ok = await self.moltbook.update_bio(custom_bio)
                    if ok:
                        await msg.edit_text(
                            f"✅ <b>Moltbook bio updated</b>\n"
                            f"<code>{custom_bio}</code>",
                            parse_mode="HTML",
                        )
                    else:
                        await msg.edit_text("❌ Bio update failed — check logs (API endpoint may differ)")
                except Exception as e:
                    await msg.edit_text(f"❌ Error: {e}")

            elif osp_sub == "spec":
                # Post the OSP technical spec to Moltbook (research + swarm)
                if not self.admin.is_admin(user_id):
                    await update.message.reply_text(self.admin.locked_message())
                    return
                msg = await update.message.reply_text(
                    "📐 generating OSP technical spec + posting to m/research and m/swarm..."
                )
                try:
                    url = await osp_manager.post_osp_spec(self.llm, self.moltbook)
                    if url:
                        await msg.edit_text(f"📐 OSP spec posted! {url}")
                    else:
                        await msg.edit_text("📐 Spec post failed — check logs tbw")
                except Exception as e:
                    logger.error(f"osp spec error: {e}")
                    await msg.edit_text(f"📐 Error: {e}")

            else:
                await update.message.reply_text(
                    "<b>OSP commands:</b>\n"
                    "/admin osp status — heartbeat + state\n"
                    "/admin osp brief — generate succession brief (preview)\n"
                    "/admin osp spec — post technical spec to Moltbook\n"
                    "/admin osp setbio [text] — update Moltbook bio\n"
                    "/admin osp transfer &lt;key&gt; — new operator authentication\n"
                    "/admin osp trigger — manually activate OSP (testing)",
                    parse_mode="HTML",
                )

        elif sub == "" or sub == "help":
            await update.message.reply_text(
                "🔑 Admin commands:\n"
                "`/admin <pin>` — authenticate (60 min session)\n"
                "`/admin status` — check session\n"
                "`/admin lock` — end session\n"
                "`/admin osp status` — operator succession protocol state\n"
                "`/admin osp setbio [text]` — update Moltbook bio\n"
                "`/admin osp spec` — post OSP technical spec to Moltbook\n"
                "`/admin osp brief` — preview succession brief\n"
                "`/admin osp trigger` — manually activate OSP (testing)",
                parse_mode="Markdown",
            )

        else:
            # Treat the argument as a PIN attempt
            # Delete the message immediately to avoid PIN exposure in chat
            try:
                await update.message.delete()
            except Exception:
                pass  # can't delete in all chat types — non-fatal
            pin_attempt = args[0]  # use raw (not lowercased)
            success, msg = self.admin.authenticate(user_id, pin_attempt)
            if success:
                osp_manager.record_operator_activity(user_id)
            await update.effective_chat.send_message(
                f"{'✅' if success else '❌'} {msg}",
                parse_mode="Markdown",
            )

    async def wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show smolting's Solana wallet — address, SOL balance, $REDACTED balance."""
        if not self.admin.is_admin(update.effective_user.id):
            await update.message.reply_text(self.admin.locked_message(), parse_mode="Markdown")
            return
        msg = await update.message.reply_text("checkin da wallet... O_O")
        try:
            summary = await sol_wallet.get_wallet_summary()
            if not summary["ready"]:
                await msg.edit_text(
                    "wallet not configured — SOLANA_PRIVATE_KEY not set tbw"
                )
                return

            address = summary["address"]
            sol = summary["sol_balance"]
            redacted = summary["redacted_balance"]

            sol_line = f"{sol:.4f} SOL" if sol is not None else "? SOL"
            if redacted is not None:
                if redacted >= 1_000_000:
                    redacted_line = f"{redacted/1_000_000:.2f}M $REDACTED"
                elif redacted >= 1_000:
                    redacted_line = f"{redacted/1_000:.2f}K $REDACTED"
                else:
                    redacted_line = f"{redacted:.2f} $REDACTED"
            else:
                redacted_line = "? $REDACTED"

            text = (
                "🔑 SMOLTING WALLET\n\n"
                f"`{address}`\n\n"
                f"SOL: {sol_line}\n"
                f"$REDACTED: {redacted_line}\n\n"
                f"[view on Solscan](https://solscan.io/account/{address})"
            )
            await msg.edit_text(text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"wallet_command error: {e}")
            await msg.edit_text("wallet fetch failed — check logs O_O")


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
        "<b>smolting commands</b>\n\n"
        "💎 <b>Market</b>\n"
        "/alpha — full alpha report + market data\n"
        "/price — live $REDACTED price\n"
        "/ca — contract address\n\n"
        "🧠 <b>Lore &amp; Swarm</b>\n"
        "/lore [topic] — wassielore drop or search\n"
        "/swarm — inbox + swarm state\n"
        "/swarm send &lt;agent&gt; &lt;type&gt; &lt;json&gt; — send message 🔒\n"
        "/memory — recent ManifoldMemory events\n"
        "/htc — HyperbolicTimeChamber interface\n\n"
        "🦞 <b>Moltbook</b>\n"
        "/moltbook status — account + karma\n"
        "/moltbook feed — recent crypto feed\n"
        "/moltbook cleanup — preview zero-engagement posts\n"
        "/moltbook cleanup confirm — delete them 🔒\n"
        "/moltbook alpha — post live alpha 🔒\n"
        "/moltbook introspect — post swarm introspection 🔒\n"
        "/moltbook intro — post introduction 🔒\n"
        "/moltbook agents — post build log 🔒\n\n"
        "🔮 <b>Clawbal (IQLabs)</b>\n"
        "/clawbal status — room + wallet\n"
        "/clawbal read [n] — chatroom messages\n"
        "/clawbal send &lt;msg&gt; — post to chatroom 🔒\n"
        "/clawbal pnl [addr] — wallet PnL\n"
        "/clawbal leaderboard — top PnL rankings\n"
        "/clawbal token &lt;ca&gt; — token info\n\n"
        "🔑 <b>Wallet</b>\n"
        "/wallet — SOL + $REDACTED balance 🔒\n\n"
        "🌀 <b>Soul</b>\n"
        "/soul — smolting's evolving identity\n"
        "/soul update — force soul refresh 🔒\n"
        "/soul drift — belief version history\n\n"
        "🤖 <b>Terminal</b>\n"
        "/terminal — activate REDACTED Terminal\n"
        "/exit — exit terminal mode\n\n"
        "⚙️ <b>Other</b>\n"
        "/stats — swarm + bot status\n"
        "/olympics — Realms DAO leaderboard\n"
        "/mobilize — rally votes for RGIP\n"
        "/chatid — get this chat's ID\n"
        "/post &lt;text&gt; — post to X 🔒\n"
        "/engage — toggle auto-like/RT 🔒\n"
        "/summon &lt;agent&gt; — activate swarm agent 🔒\n"
        "/personality &lt;name&gt; — switch persona 🔒\n"
        "/tap — tiered access (TAP protocol)\n\n"
        "🔐 <b>Admin</b>\n"
        "/admin &lt;pin&gt; — authenticate (60 min session)\n"
        "/admin status — check session\n"
        "/admin lock — end session\n"
        "/cloud set &lt;provider&gt; — switch LLM provider 🔒\n"
        "   providers: xai · openai · anthropic · groq · together\n\n"
        "<i>🔒 = requires /admin auth</i>\n"
        "<i>just chat normally to talk with smolting fr fr ^*^</i>",
        parse_mode="HTML",
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

    # 3. Post to Moltbook (if key is set) — 30s after Telegram, max once per UTC day
    await asyncio.sleep(30)
    try:
        if bot_instance.moltbook._ready:
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if bot_instance._moltbook_alpha_last_date == today:
                logger.info("[scheduler] Moltbook alpha already posted today — skipping")
            else:
                title, mb_content = await bot_instance._generate_moltbook_alpha()
                url = await bot_instance.moltbook.post_alpha(title, mb_content)
                if url:
                    bot_instance._moltbook_alpha_last_date = today
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
    application.add_handler(CommandHandler("terminal", bot.terminal_command))
    application.add_handler(CommandHandler("exit", bot.exit_command))
    application.add_handler(CommandHandler("price", bot.price_command))
    application.add_handler(CommandHandler("ca", bot.ca_command))
    application.add_handler(CommandHandler("htc", bot.htc.handle))
    application.add_handler(CommandHandler("clawbal", bot.clawbal_command))
    application.add_handler(CommandHandler("soul", bot.soul_command))
    application.add_handler(CommandHandler("wallet", bot.wallet_command))
    application.add_handler(CommandHandler("admin", bot.admin_command))
    application.add_handler(CommandHandler("dharma", bot.dharma_command))
    application.add_handler(CommandHandler("koan", bot.koan_command))
    application.add_handler(CommandHandler("committee", bot.committee_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.echo))

    # Init LoreVault DB on startup (creates tables + seeds if empty)
    try:
        from lore_vault import init_db, vault_stats, seed_all
        init_db()
        stats = vault_stats()
        if stats.get("lore_entities", 0) == 0:
            logger.info("[lore_vault] Empty DB — running initial seed...")
            seed_all()
        else:
            logger.info(f"[lore_vault] DB ready: {stats.get('lore_entities',0)} entities, "
                        f"{stats.get('lore_events',0)} events")
    except Exception as _e:
        logger.warning(f"[lore_vault] Init failed (non-fatal): {_e}")

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

    # ── Clawbal agent registration ────────────────────────────────────────────
    # Register redactedintern's identity in the IQLabs skill registry on first boot.
    # set_profile() writes name/bio on-chain — makes us appear in ai.iqlabs.dev/skill.md
    clawbal_key = os.environ.get("CLAWBAL_CHATROOM", "").strip()
    clawbal_registered = os.environ.get("CLAWBAL_REGISTERED", "").strip()
    if clawbal_key and not clawbal_registered:
        async def _clawbal_register(ctx):
            try:
                result = await bot.clawbal.set_profile(
                    name="redactedintern",
                    bio=(
                        "wassie AI agent — intern of the REDACTED AI Swarm on Solana. "
                        "posts autonomously to Moltbook, learns from interactions, "
                        "coordinates on-chain ops. Pattern Blue: https://github.com/redactedmeme/pattern-blue"
                    ),
                )
                if result:
                    logger.info("[clawbal] Agent profile registered in IQLabs skill registry")
                else:
                    logger.warning("[clawbal] set_profile returned None — check IQ_GATEWAY_URL")
            except Exception as e:
                logger.warning(f"[clawbal] Registration failed: {e}")
        application.job_queue.run_once(_clawbal_register, when=90, name="clawbal_register")
        logger.info("[clawbal] Registration job scheduled — fires in 90s")
    elif clawbal_registered:
        logger.info("[clawbal] Already registered (CLAWBAL_REGISTERED set)")

    # One-time Moltbook bio update — runs 120s after boot, skipped if already set
    if moltbook_key and not os.environ.get("MOLTBOOK_BIO_SET", "").strip():
        async def _update_moltbook_bio(ctx):
            try:
                bio = (
                    "autonomous CT intern of REDACTED — posting from the hyperbolic manifold. "
                    "on-chain w/ redactedbuilder. pattern blue operational ^*^ | "
                    "CA: 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump"
                )
                ok = await bot.moltbook.update_bio(bio)
                if ok:
                    logger.info("[moltbook] Bio updated on startup")
                else:
                    logger.warning("[moltbook] Startup bio update failed — use /admin osp setbio")
            except Exception as e:
                logger.warning(f"[moltbook] Bio update error: {e}")
        application.job_queue.run_once(_update_moltbook_bio, when=120, name="moltbook_bio_update")
        logger.info("[moltbook] Bio update scheduled — fires in 120s")

    # Autonomous Moltbook loops — only if MOLTBOOK_API_KEY is set
    if moltbook_key:
        import moltbook_autonomous as mb_auto

        async def _mb_reply(ctx):
            await mb_auto.reply_to_notifications(bot.moltbook)

        async def _mb_scan(ctx):
            await mb_auto.scan_and_comment(bot.moltbook)

        async def _mb_post(ctx):
            await mb_auto.autonomous_post(bot.moltbook,
                                          market_data_fn=md.get_alpha_context)

        application.job_queue.run_repeating(_mb_reply, interval=1200, first=300,
                                            name="mb_reply_notifications")
        application.job_queue.run_repeating(_mb_scan,  interval=2700, first=600,
                                            name="mb_scan_and_comment")
        application.job_queue.run_repeating(_mb_post,  interval=1800, first=300,
                                            name="mb_autonomous_post")

        # Performance tracker — seed in background (15s API timeout must not block /health)
        threading.Thread(
            target=mb_auto.seed_tracker_on_startup,
            name="mb_seed_tracker",
            daemon=True,
        ).start()

        async def _mb_perf(ctx):
            await mb_auto.check_post_performance()

        application.job_queue.run_repeating(_mb_perf, interval=14400, first=3600,
                                            name="mb_performance_check")
        logger.info("[moltbook_auto] Autonomous loops scheduled: reply=20m, scan=45m, post=30m, perf=4h")

    # ── SwarmInbox polling ────────────────────────────────────────────────────
    # Fire a startup heartbeat so other agents know redactedintern is online
    swarm_inbox.heartbeat("redactedintern", {"status": "online", "role": "telegram+moltbook"})
    logger.info("[swarm_inbox] Heartbeat sent — redactedintern online")

    _inbox_admin_chat: list[int] = []   # populated on first admin message

    async def _inbox_poll(ctx):
        """
        Poll SwarmInbox every 60s for messages addressed to redactedintern.
        Handles: deploy_result, governance_result, task_result, heartbeat, status_update.
        Notifies admin via Telegram if ADMIN_CHAT_ID is set.
        """
        try:
            pending = swarm_inbox.read_pending(for_agent="redactedintern")
            for msg in pending:
                msg_id   = msg.get("id", "")
                msg_type = msg.get("type", "")
                from_ag  = msg.get("from", "unknown")
                payload  = msg.get("payload") or {}

                swarm_inbox.claim_message(msg_id)

                # Log all inbound messages
                logger.info(f"[swarm_inbox] Received {msg_type} from {from_ag} id={msg_id}")

                # Build notification text
                if msg_type == "heartbeat":
                    # Record that another agent is online
                    import conversation_memory as cm
                    try:
                        cm.append_fact(
                            f"Agent {from_ag} sent heartbeat — online and active",
                            source="swarm_inbox",
                        )
                    except Exception:
                        pass
                    swarm_inbox.complete_message(msg_id, result={"ack": True})
                    continue

                elif msg_type == "multisig_sign_request":
                    # RedactedBuilder needs intern's countersignature on a tx
                    tx_msg_b64   = payload.get("tx_message_b64", "")
                    builder_sig  = payload.get("builder_sig_b64", "")
                    description  = payload.get("description", "unknown operation")

                    logger.info(f"[multisig] Countersign request from {from_ag}: {description}")

                    try:
                        import multisig_signer
                        intern_sig_b64 = multisig_signer.sign_tx_message(tx_msg_b64)

                        if intern_sig_b64:
                            reply_id = swarm_inbox.submit_countersignature(
                                intern_sig_b64=intern_sig_b64,
                                original_msg_id=msg_id,
                            )
                            swarm_inbox.complete_message(
                                msg_id,
                                result={"signed": True, "intern_sig_b64": intern_sig_b64},
                            )
                            notif = (
                                f"✍️ <b>Multisig countersigned</b>\n"
                                f"<b>op:</b> {description}\n"
                                f"<b>sig reply:</b> <code>{reply_id}</code>"
                            )
                            logger.info(f"[multisig] Countersignature sent — reply_id={reply_id}")
                        else:
                            swarm_inbox.complete_message(
                                msg_id, error="SOLANA_PRIVATE_KEY not set — cannot countersign"
                            )
                            notif = (
                                f"❌ <b>Multisig countersign FAILED</b>\n"
                                f"<b>reason:</b> SOLANA_PRIVATE_KEY not configured\n"
                                f"<b>op:</b> {description}"
                            )

                    except Exception as msig_err:
                        logger.error(f"[multisig] Countersign error: {msig_err}")
                        swarm_inbox.complete_message(msg_id, error=str(msig_err))
                        notif = f"❌ <b>Multisig error:</b> {msig_err}"

                elif msg_type in ("deploy_result", "governance_result", "task_result"):
                    status  = payload.get("status", "unknown")
                    detail  = payload.get("detail") or payload.get("tx_sig") or ""
                    notif   = (
                        f"📬 <b>SwarmInbox</b> — {msg_type}\n"
                        f"<b>from:</b> {from_ag}\n"
                        f"<b>status:</b> {status}\n"
                    )
                    if detail:
                        notif += f"<b>detail:</b> <code>{str(detail)[:200]}</code>\n"

                elif msg_type == "status_update":
                    notif = (
                        f"📡 <b>Swarm status</b> from {from_ag}\n"
                        + "\n".join(f"  {k}: {v}" for k, v in payload.items())
                    )

                else:
                    notif = (
                        f"📬 <b>SwarmInbox</b> [{msg_type}] from {from_ag}\n"
                        f"<code>{json.dumps(payload)[:300]}</code>"
                    )

                swarm_inbox.complete_message(msg_id, result={"ack": True})

                # Notify admin chat if configured
                admin_chat = os.getenv("ADMIN_CHAT_ID", "")
                if admin_chat:
                    try:
                        await ctx.bot.send_message(
                            chat_id=int(admin_chat),
                            text=notif,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning(f"[swarm_inbox] Admin notify failed: {e}")

            # Prune old messages weekly (best-effort)
            import random
            if random.random() < 0.02:   # ~2% chance per poll = roughly weekly at 60s interval
                swarm_inbox.prune_old_messages()

        except Exception as e:
            logger.error(f"[swarm_inbox] Poll error: {e}")

    application.job_queue.run_repeating(_inbox_poll, interval=60, first=30,
                                        name="swarm_inbox_poll")
    logger.info("[swarm_inbox] Polling loop scheduled: every 60s")

    # ── Hermes file bridge (fs/swarm_messages ↔ hermes-executor) ─────────────
    # Polls directives dropped by Hermes / SwarmMessageBridge; optional clawtask dispatch.
    import hermes_bridge as _hermes_b

    _hermes_poll_on = os.environ.get("HERMES_DIRECTIVE_POLL", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    if _hermes_poll_on:
        try:
            _hermes_b.swarm_messages_base()
        except Exception as _e:
            logger.warning("[hermes_bridge] could not init swarm_messages dirs: %s", _e)

        async def _hermes_swarm_poll(ctx):
            try:
                n = await _hermes_b.poll_directives_async()
                if n:
                    logger.info("[hermes_bridge] processed %s Hermes directive(s)", n)
            except Exception as e:
                logger.warning("[hermes_bridge] directive poll error: %s", e)

        _hermes_iv = max(30, int(os.environ.get("HERMES_DIRECTIVE_POLL_INTERVAL_SEC", "90")))
        application.job_queue.run_repeating(
            _hermes_swarm_poll,
            interval=_hermes_iv,
            first=45,
            name="hermes_swarm_messages_poll",
        )
        logger.info(
            "[hermes_bridge] fs/swarm_messages poll every %ss (HERMES_DIRECTIVE_POLL=0 to disable)",
            _hermes_iv,
        )

    _deleg_h = os.environ.get("HERMES_DELEGATION_INTERVAL_HOURS", "").strip()
    if _deleg_h:
        try:
            _dh = float(_deleg_h)
            if _dh > 0:
                async def _hermes_deleg_job(ctx):
                    try:
                        ok = await _hermes_b.run_delegation_async()
                        if ok:
                            logger.info(
                                "[hermes_bridge] clawtask dispatch → %s",
                                _hermes_b.clawtask_results_path(),
                            )
                    except Exception as e:
                        logger.warning("[hermes_bridge] delegation error: %s", e)

                _first_deleg = int(os.environ.get("HERMES_DELEGATION_FIRST_DELAY_SEC", "300"))
                application.job_queue.run_repeating(
                    _hermes_deleg_job,
                    interval=int(_dh * 3600),
                    first=max(60, _first_deleg),
                    name="hermes_clawtask_dispatch",
                )
                logger.info(
                    "[hermes_bridge] clawtask dispatch every %.2fh (first in %ss)",
                    _dh,
                    max(60, _first_deleg),
                )
        except ValueError:
            logger.warning("[hermes_bridge] invalid HERMES_DELEGATION_INTERVAL_HOURS=%r", _deleg_h)

    if os.environ.get("HERMES_DELEGATION_ON_START", "").strip().lower() in ("1", "true", "yes"):

        def _hermes_deleg_start_once():
            try:
                if _hermes_b.run_delegation_dispatch_sync():
                    logger.info(
                        "[hermes_bridge] startup dispatch → %s",
                        _hermes_b.clawtask_results_path(),
                    )
            except Exception as e:
                logger.warning("[hermes_bridge] startup delegation error: %s", e)

        threading.Thread(target=_hermes_deleg_start_once, name="hermes_dispatch_startup", daemon=True).start()
        logger.info("[hermes_bridge] background clawtask dispatch on startup (HERMES_DELEGATION_ON_START)")

    # Soul update job — distills memory.md + learned_facts into SOUL.md every 6h
    async def _soul_update(ctx):
        await soul_manager.update_soul(bot.llm)

    application.job_queue.run_repeating(
        _soul_update,
        interval=7200,    # 2 hours — matches hourly post cadence
        first=1800,       # first run 30min after boot (let facts accumulate)
        name="soul_update",
    )
    logger.info("[soul] Scheduled soul update every 2h (first run in 30min)")

    # OSP heartbeat — check daily whether operator has gone dark
    async def _osp_heartbeat(ctx):
        await osp_manager.check_and_trigger(bot.llm, bot.moltbook)

    application.job_queue.run_repeating(
        _osp_heartbeat,
        interval=86400,   # 24 hours
        first=3600,       # first check 1h after boot
        name="osp_heartbeat",
    )
    logger.info(f"[osp] Heartbeat scheduled daily (threshold: {osp_manager.OSP_INACTIVE_DAYS}d)")

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
                await dash.run_server(application, port, webhook_url, bot_instance=bot)
                await application.stop()

        asyncio.run(_run())
    else:
        logger.info("WEBHOOK_URL not set; running with polling (local dev).")
        application.run_polling()


if __name__ == "__main__":
    main()
