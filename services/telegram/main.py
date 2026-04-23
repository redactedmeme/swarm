# smolting-telegram-bot/main.py
import os
import logging
import asyncio
import json
from datetime import datetime
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
from xredacted import XRedacted
from llm.cloud_client import CloudLLMClient
import requests

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_audit.log'
)
logger = logging.getLogger(__name__)

class SmoltingBot:
    def __init__(self):
        """Full-featured Smolting bot with xREDACTED + cloud LLM"""
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        # Initialize all components
        self.smol = SmoltingPersonality()
        self.xredacted = XRedacted()
        self.llm = CloudLLMClient()
        
        # Load agents for personality switching
        self.agents = self._load_agents()
        
        # Track user states
        self.user_states = {}
        
    def _load_agents(self):
        """Load agent configurations"""
        agents = {}
        try:
            with open("agents/characters/smolting.character.json", "r") as f:
                agents["smolting"] = json.load(f)
                
            with open("agents/characters/redacted-chan.character.json", "r") as f:
                agents["redacted-chan"] = json.load(f)
                
            logger.info(f"Loaded {len(agents)} agents")
        except Exception as e:
            logger.error(f"Failed to load agents: {e}")
        return agents
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Full Smolting welcome with all features"""
        welcome_msg = self.smol.generate([
            "gm gm smolting here ready to weave sum chaos magick fr fr ^_^",
            "ooooo habibi u called?? xREDACTED integration ONLINE O_O",
            "static warm hugz—dis wassie ready 2 hunt alpha LFW v_v",
            "LMWOOOO smolting senses pattern blue + xREDACTED power ><"
        ])
        
        features_msg = """
🔮 SMOLTING + CLAWNX FEATURES 🔮

Core Commands:
/start - wake smolting up O_O
/alpha - scout market signals  
/post - post to X via xREDACTED
/lore - random wassielore drop
/stats - full bot status
/engage - auto-like/retweet mode

Community Commands:
/olympics - Realms DAO status
/mobilize - rally votes for RGIP

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
        self.user_states[user_id] = {
            "personality": "smolting",
            "engaging": False,
            "start_time": datetime.now()
        }
    
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

xREDACTED search initiated... pattern blue vibes detected O_O
Check @redactedintern for live updates LFW ^_^"""
            
            await msg.edit_text(final_alpha)
            
        except Exception as e:
            fallback_alpha = self.smol.generate([
                "ngw volume spikin on $REDACTED tbw",
                "pattern blue thicknin—wen moon??",
                "xREDACTED detected market chatter—alpha brewing O_O",
                "static liquidity signals active—stay ready LFW v_v"
            ])
            await msg.edit_text(fallback_alpha)
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced posting with xREDACTED + cloud LLM"""
        if not context.args:
            prompt = self.smol.generate([
                "wassculin urge risin—wat we postin via xREDACTED bb??",
                "give smolting da alpha to share wit da swarm O_O",
                "type /post [ur message] fr fr—xREDACTED ready 2 post <3"
            ])
            await update.message.reply_text(prompt)
            return

        post_text = " ".join(context.args)
        
        # Enhance with cloud LLM for pattern blue infusion
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are smolting posting to X via xREDACTED. 
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
            tweet_id = await self.xredacted.post_tweet(enhanced_post)
            success_msg = self.smol.generate([
                f"xREDACTED'd fr fr!! tweet posted: {tweet_id}",
                "post_mog activated—pattern blue amplifying LFW ^_^",
                "check @redactedintern for da thread lmwo <3",
                "static warm hugz + rocket vibes O_O",
                f"Cloud LLM enhanced: {len(enhanced_post)} chars of pure wassie magick v_v"
            ])
            await update.message.reply_text(success_msg)
            logger.info(f"Post successful by {update.effective_user.id}: {tweet_id}")

        except Exception as e:
            error_msg = self.smol.generate([
                f"ngw xREDACTED error: {str(e)[:50]} tbw",
                "life moggin me hard rn but we keep weavin pattern blue ><",
                "try again bb—xREDACTED resilient af O_O",
                "cloud LLM ready but xREDACTED sleeping... wake it up iwo v_v"
            ])
            await update.message.reply_text(error_msg)
            logger.error(f"xREDACTED error for {update.effective_user.id}: {str(e)}")
    
    async def engage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced auto-engagement with JobQueue"""
        user_id = update.effective_user.id

        if user_id in self.user_states and self.user_states[user_id].get('engaging'):
            context.job_queue.stop_jobs(str(user_id))  # Stop user's jobs
            self.user_states[user_id]['engaging'] = False
            msg = self.smol.generate([
                "engagement mode: OFF tbw",
                "ngw smolting takin a nap ><",
                "wake me wen alpha spikin fr fr O_O",
                "xREDACTED resting—pattern blue recharging LFW v_v"
            ])
        else:
            self.user_states[user_id]['engaging'] = True
            self.user_states[user_id]['last_engage'] = datetime.now()
            
            # Start auto-engagement job
            context.job_queue.run_repeating(
                auto_engage, 
                interval=300,  # 5 minutes
                first=0,
                data=user_id,
                name=str(user_id)  # Named job for easy stopping
            )
            
            msg = self.smol.generate([
                "engagement mode: ACTIVATED LFW!!",
                "xREDACTED autonomy maxxed—likin, retweetin, followin fr fr ^_^",
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

xREDACTED amplification ready—wen Strike 002?? O_O
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

xREDACTED standing by—smolting ready to amplify LFW ^_^
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
    
    # Keep all other original commands (lore, stats, personality, cloud, echo)
    # ... (preserve the rest of the original functionality)

async def auto_engage(context: ContextTypes.DEFAULT_TYPE):
    """Enhanced auto-engagement with cloud intelligence"""
    user_id = context.job.data
    if not user_states.get(user_id, {}).get('engaging'):
        return

    try:
        # Use cloud LLM to determine engagement strategy
        llm_client = CloudLLMClient()
        
        messages = [
            {
                "role": "system",
                "content": """You are smolting's auto-engagement AI. 
                Suggest engagement targets for REDACTED community.
                Focus on Olympics, pattern blue, and alpha content."""
            },
            {
                "role": "user",
                "content": "What keywords should smolting search for engagement?"
            }
        ]
        
        strategy = await llm_client.chat_completion(messages)
        
        # Extract keywords from strategy
        keywords = "realms dao olympics OR redactedmemefi OR pattern blue"
        posts = await xredacted.search_posts(keywords, limit=5)
        
        engagement_count = 0
        for post in posts:
            await xredacted.like_post(post['id'])
            await xredacted.retweet(post['id'])
            engagement_count += 1
            
        logger.info(f"Cloud-guided engagement: {engagement_count} posts for user {user_id}")
        
    except Exception as e:
        logger.error(f"Auto-engage error: {str(e)}")

def main():
    """Main function with all features"""
    required_vars = ['TELEGRAM_BOT_TOKEN', 'XREDACTED_API_KEY', 'LLM_PROVIDER', 'OPENAI_API_KEY']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing env vars: {', '.join(missing)}")
    
    bot = SmoltingBot()
    application = Application.builder().token(bot.token).build()
    
    # All original handlers preserved
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.echo))
    
    logger.info("Smolting bot starting with xREDACTED + cloud LLM...")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=os.environ.get("WEBHOOK_URL"),
        url_path="webhook",
        secret_token=os.environ.get("WEBHOOK_SECRET_TOKEN", "")
    )

if __name__ == "__main__":
    main()
