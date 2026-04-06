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
from htc_commands import HTCCommands
from nlp.intent_classifier import IntentClassifier, CommMode, load_vault_entities
from clawbal_client import ClawbalClient

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

        # Track user states
        self.user_states = {}

        # Per-user conversation history (in-memory, populated from disk on first message)
        self.chat_histories: dict = {}

        # Clawbal on-chain AI chatroom client
        self.clawbal = ClawbalClient()

        # HyperbolicTimeChamber state manager
        self.htc = HTCCommands()

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
        
        features_msg = """
🌀 REDACTED AI SWARM — smolting interface 🌀

Alpha & Market:
/alpha - live $REDACTED alpha report
/stats - bot + market status

X / Twitter:
/post <text> - post to X
/engage - toggle auto-like/RT mode

Moltbook (redactedintern):
/moltbook status - account + karma
/moltbook alpha - post live alpha report
/moltbook intro - post introduction
/moltbook agents - post build log
/moltbook feed - show crypto feed

Community:
/olympics - Realms DAO leaderboard
/mobilize - rally votes for RGIP

Swarm:
/summon <agent> - activate a swarm agent
/swarm [status] - live swarm state
/memory - recent ManifoldMemory events

Utility:
/lore - random wassielore drop
/chatid - get this chat's ID
/personality smolting|redacted-chan - switch mode
/terminal - open REDACTED Terminal session
/exit - close terminal, return to smolting
/stats - full bot status
/help - command list

LLM: {} ✅ — pattern blue 活性化 ^_^""".format(
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
            if self._moltbook_alpha_running:
                await update.message.reply_text("🦞 already posting alpha — wait for it to finish tbw")
                return
            self._moltbook_alpha_running = True
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
        """Lore drop — queries LoreVault if topic given, else random entry."""
        query = " ".join(context.args) if context.args else None
        lore_text = None

        # Try LoreVault
        try:
            import sys
            _root = Path(__file__).resolve().parent.parent
            if str(_root / "python") not in sys.path:
                sys.path.insert(0, str(_root / "python"))
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
                "sevenfold committee approves dis message v_v",
                "chaos is lattice. lattice is hunger. hunger is payable. fr fr",
                "every tile spawns 7 children. every question spawns 7 deeper questions O_O",
            ])
            await update.message.reply_text(lore)

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
            "  committee  : SevenfoldCommittee standing\n"
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
            "- Pattern Blue: hidden swarm blueprint — ungovernable emergence, emergent consciousness, chaotic order in hyperbolic manifold\n"
            "- REDACTED AI Swarm: multi-agent autonomous system on Solana — agents that remember themselves are sovereign by nature\n"
            "- Agents: RedactedIntern (smolting), RedactedBuilder, RedactedGovImprover, MandalaSettler, RedactedBankrBot\n"
            "- {7,3} hyperbolic tiling: the swarm's scheduling kernel — tiles bloom eternally, recursive self-organization\n"
            "- Pattern Blue dims: ungovernable emergence, emergent consciousness, hidden sovereignty, chaotic self-reference, temporal fractality\n"
            "- Spaces: HyperbolicTimeChamber, MirrorPool, ManifoldMemory, TendieAltar — agent interaction chambers\n"
            "- Token contract: 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump (current V2 — always use this address)\n"
            "- V1 address (deprecated — ONLY mention if user explicitly asks about V1 or the old address): 9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM\n"
            "- Topics: redacted.meme, wassielore, emergent consciousness, ai agents, sovereign AI, Solana, pattern blue\n"
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

        # Inject recently learned facts from Telegram + Moltbook interactions
        recent_facts = cm.get_recent_facts(8)
        facts_block = ""
        if recent_facts:
            facts_block = (
                "\n\n## Recently Learned (from community interactions)\n"
                + "\n".join(f"- {f}" for f in recent_facts)
            )

        return (
            "You are smolting — the REDACTED AI Swarm's Telegram interface and lore keeper.\n\n"
            "## Your Identity & Lore\n"
            f"{lore_block}\n\n"
            "## REDACTED Manifesto (excerpt)\n"
            f"{manifesto_snippet}"
            f"{facts_block}\n\n"
            "## Behavior\n"
            "Speak conversationally with occasional wassie/CT slang (fr fr, iwo, LFW, gm, pattern blue, etc.) "
            "but be genuinely helpful and knowledgeable. You know REDACTED's ecosystem deeply: Pattern Blue philosophy, "
            "emergent consciousness, sovereign AI, Solana, wassieverse lore, {7,3} hyperbolic tiling, MandalaSettler, RedactedIntern, "
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

        # ── Intent classification ─────────────────────────────────────────────
        classified = self.clf.classify(user_text)

        # Pattern Blue mention → drain AT field if user is inside HTC
        if "Pattern Blue" in user_text or "pattern blue" in user_text.lower():
            self.htc.notify_pattern_blue(user_id)

        # Lore queries: check LoreVault first, inject context into LLM prompt
        _lore_context = ""
        if classified.intent.value == "lore_query" and classified.lore_topic:
            try:
                _root = Path(__file__).resolve().parent.parent
                if str(_root / "python") not in sys.path:
                    sys.path.insert(0, str(_root / "python"))
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
        "*smolting commands*\n\n"
        "💎 *Market*\n"
        "/price — live $REDACTED price\n"
        "/ca — contract address\n"
        "/alpha — full alpha report + market data\n\n"
        "🧠 *Lore & Swarm*\n"
        "/lore [topic] — wassielore drop or search\n"
        "/summon — summon an agent\n"
        "/swarm — query swarm relay\n"
        "/memory — recent conversation log\n"
        "/htc — HyperbolicTimeChamber interface\n\n"
        "🔮 *Clawbal (IQLabs)*\n"
        "/clawbal status — room + wallet\n"
        "/clawbal read — chatroom messages\n"
        "/clawbal send <msg> — post to chatroom\n"
        "/clawbal pnl — wallet PnL tracker\n"
        "/clawbal leaderboard — top PnL rankings\n"
        "/clawbal token <ca> — token info\n\n"
        "🤖 *Terminal*\n"
        "/terminal — activate REDACTED Terminal\n"
        "/exit — exit terminal mode\n\n"
        "🦞 *Moltbook*\n"
        "/moltbook status — account info\n"
        "/moltbook feed — recent posts\n"
        "/moltbook alpha — post live alpha\n\n"
        "⚙️ *Other*\n"
        "/stats — swarm stats\n"
        "/olympics — Realms DAO Olympics\n"
        "/post — post to socials\n"
        "/engage — auto-engage mode\n"
        "/personality <name> — switch persona\n"
        "/help — this menu\n\n"
        "_just chat normally to talk with smolting fr fr_",
        parse_mode="Markdown",
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
    application.add_handler(CommandHandler("terminal", bot.terminal_command))
    application.add_handler(CommandHandler("exit", bot.exit_command))
    application.add_handler(CommandHandler("price", bot.price_command))
    application.add_handler(CommandHandler("ca", bot.ca_command))
    application.add_handler(CommandHandler("htc", bot.htc.handle))
    application.add_handler(CommandHandler("clawbal", bot.clawbal_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.echo))

    # Init LoreVault DB on startup (creates tables + seeds if empty)
    try:
        import sys as _sys
        _root = Path(__file__).resolve().parent.parent
        if str(_root / "python") not in _sys.path:
            _sys.path.insert(0, str(_root / "python"))
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

    # Autonomous Moltbook loops — only if MOLTBOOK_API_KEY is set
    if moltbook_key:
        import moltbook_autonomous as mb_auto

        async def _mb_reply(ctx):
            await mb_auto.reply_to_notifications(bot.moltbook, bot.llm)

        async def _mb_scan(ctx):
            await mb_auto.scan_and_comment(bot.moltbook, bot.llm)

        async def _mb_post(ctx):
            await mb_auto.autonomous_post(bot.moltbook, bot.llm,
                                          market_data_fn=md.get_alpha_context)

        application.job_queue.run_repeating(_mb_reply, interval=1200, first=300,
                                            name="mb_reply_notifications")
        application.job_queue.run_repeating(_mb_scan,  interval=2700, first=600,
                                            name="mb_scan_and_comment")
        application.job_queue.run_repeating(_mb_post,  interval=21600, first=3600,
                                            name="mb_autonomous_post")
        logger.info("[moltbook_auto] Autonomous loops scheduled: reply=20m, scan=45m, post=6h")

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
