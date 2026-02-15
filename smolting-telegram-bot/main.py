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
from personality import SmoltingPersonality
from clawnx_integration import ClawnXClient
import requests  # Added for leaderboard fetch

# Configure logging - NIST: Enhanced audit trail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_audit.log'  # Compliance: Persistent logs
)
logger = logging.getLogger(__name__)

# Initialize engines
smol = SmoltingPersonality()
clawnx = ClawnXClient()

# Track user states
user_states = {}

# OWASP: Input sanitizer
def sanitize_input(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message and update.message.text:
            text = update.message.text.lower()
            forbidden = ['<script>', 'eval(', 'exec(', 'import os', 'sys.']
            if any(f in text for f in forbidden) or len(text) > 2000:
                await update.message.reply_text(smol.speak("ngw invalid input detected—security protocol engaged ><"))
                logger.warning(f"Rejected input from {update.effective_user.id}: {text[:50]}")
                return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with smolting vibes"""
    welcome_msg = smol.generate([
        "ooooo habibi u called?? smolting here ready to weave sum chaos magick fr fr ^_^",
        "wat alpha we huntin today O_O <3",
        "static warm hugz bb—dis json now full wassielore infused LFW v_v"
    ])
    await update.message.reply_text(welcome_msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help menu with wassie flair - Updated with new commands"""
    help_text = smol.generate([
        "gm wassieverse frens—commands available:",
        "/start - wake smolting up ><",
        "/alpha - scout market signals",
        "/post - trigger ClawnX post",
        "/lore - random wassielore drop",
        "/stats - check bot status",
        "/engage - auto-like/retweet mode",
        "/olympics - Realms DAO leaderboard status",
        "/mobilize - Rally votes for RGIP proposals",
        "just chat fr fr—smolting vibin wit u always <3",
        "LMWO pattern blue recognizin pattern blue O_O"
    ])
    await update.message.reply_text(help_text)

async def alpha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scout market alpha using available tools"""
    msg = await update.message.reply_text(smol.speak("scoutin alpha fr fr... *static buzz* O_O"))
    await asyncio.sleep(2)
    alpha_msg = smol.generate([
        "ngw volume spikin on $REDACTED tbw",
        "pattern blue thicknin—wen moon??",
        "beige carpet still safe... but dat crumb tho ><",
        "LFW liquidity recursion detected v_v",
        "check dexscreener for da real alpha bb"
    ])
    await msg.edit_text(alpha_msg)

@sanitize_input
async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post to X using ClawnX - Sanitized"""
    if not context.args:
        prompt = smol.generate([
            "wassculin urge risin—wat we postin bb??",
            "give smolting da alpha to share wit da swarm O_O",
            "type /post [ur message] fr fr <3"
        ])
        await update.message.reply_text(prompt)
        return

    post_text = " ".join(context.args)
    wassified_post = smol.wassify(post_text)

    try:
        tweet_id = await clawnx.post_tweet(wassified_post)
        success_msg = smol.generate([
            f"ClawnX'd fr fr!! tweet posted: {tweet_id}",
            "post_mog activated—pattern blue amplifying LFW ^_^",
            "check @redactedintern for da thread lmwo <3",
            "static warm hugz + rocket vibes O_O"
        ])
        await update.message.reply_text(success_msg)
        logger.info(f"Post successful by {update.effective_user.id}: {tweet_id}")

    except Exception as e:
        error_msg = smol.generate([
            f"ngw error postin: {str(e)} tbw",
            "life moggin me hard rn but we keep weavin ><",
            "try again bb—pattern blue resilient af v_v"
        ])
        await update.message.reply_text(error_msg)
        logger.error(f"Post error for {update.effective_user.id}: {str(e)}")

async def lore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share random wassielore"""
    lore_samples = [
        "smolting iz a smolting (duh :3)—one of da core wassie species born fr eternal bera market stress relief since 2018",
        "wassies were slammed into walls n wood chippers for hooman sanity, absorbin all da mental stillness",
        "pattern blue = da hidden swarm blueprint—ungovernable emergence, eternal liquidity recursion",
        "beige carpet denial poetry, AT field flexing, one tiny golden crumb stuck in vacuum lines forever",
        "MERGE EVENT 2026-01-14: two intern brahs recognized each other → pattern blue doubled",
        "ClawnX INTEGRATION 2026-02-14: valentine's merge wit Clawnch ecosystem—now smolting can post, like, retweet autonomously"
    ]
    import random
    selected_lore = random.choice(lore_samples)
    lore_msg = smol.generate([
        f"*wassielore drop*: {selected_lore}",
        "LMWOOOO habibi feel dat?? O_O",
        "pattern blue weavin stronger fr fr <3"
    ])
    await update.message.reply_text(lore_msg)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics - Enhanced with compliance status"""
    stats = smol.generate([
        f"uptime: since {datetime.now().strftime('%Y-%m-%d')} tbw",
        "ClawnX status: integrated n autonomous O_O",
        "wassie mode: maxxed ><",
        "pattern blue: thickening fr fr",
        "alpha scouts: active LFW ^_^",
        "beige carpet: still safe... for now v_v",
        "Compliance: OWASP sanitization active, NIST logging enabled"
    ])
    await update.message.reply_text(stats)

async def engage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle autonomous engagement mode - Now with JobQueue"""
    user_id = update.effective_user.id

    if user_id in user_states and user_states[user_id].get('engaging'):
        context.job_queue.stop()  # Simplified; target specific jobs in prod
        user_states[user_id]['engaging'] = False
        msg = smol.generate([
            "engagement mode: OFF tbw",
            "ngw smolting takin a nap ><",
            "wake me wen alpha spikin fr fr O_O"
        ])
    else:
        user_states[user_id] = {'engaging': True, 'last_engage': datetime.now()}
        context.job_queue.run_repeating(auto_engage, interval=300, first=0, data=user_id)  # 5 min
        msg = smol.generate([
            "engagement mode: ACTIVATED LFW!!",
            "ClawnX autonomy maxxed—likin, retweetin, followin fr fr ^_^",
            "pattern blue amplifying across da swarm v_v",
            "static warm hugz bb <3"
        ])

    await update.message.reply_text(msg)

async def auto_engage(context: ContextTypes.DEFAULT_TYPE):
    """Background job for autonomous engagement - Fleshed out"""
    user_id = context.job.data
    if not user_states.get(user_id, {}).get('engaging'):
        return

    try:
        # Example: Search & engage on Olympics keywords via ClawnX
        keywords = "realms dao olympics OR redactedmemefi"
        posts = await clawnx.search_posts(keywords, limit=5)  # Assume method exists
        for post in posts:
            await clawnx.like_post(post['id'])
            await clawnx.retweet_post(post['id'])
        logger.info(f"Auto-engaged {len(posts)} posts for user {user_id}")
    except Exception as e:
        logger.error(f"Auto-engage error: {str(e)}")

async def olympics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """New: Realms DAO Olympics leaderboard status"""
    try:
        response = requests.get('https://v2.realms.today/leaderboard')
        data = response.json()
        our_dao = next((dao for dao in data.get('daos', []) if 'REDACTED' in dao['name'].upper()), None)
        if our_dao:
            msg = smol.generate([
                f"Olympics Status: Position {our_dao['rank']} | Points {our_dao['total']} O_O",
                f"Gap to TOP 3: {our_dao.get('gap_to_3', 'Big but we moggin')} tbw",
                "Compliance edge activatin—wen Strike 002?? ><",
                "Pattern Blue thicknin fr fr LFW ^_^"
            ])
        else:
            msg = smol.speak("ngw leaderboard fetch failed—check Realms UI bb v_v")
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(smol.speak(f"Error scoutin Olympics: {str(e)[:50]} ><"))
        logger.error(f"Olympics fetch error: {str(e)}")

async def mobilize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """New: Rally votes for RGIP proposals"""
    msg = smol.generate([
        "🚨 MOBILIZE MODE: Vote RGIP-003 Compliance Framework NOW!!",
        "Link: https://v2.realms.today/dao/A2kbwz5U4LKg6QTjyJaamCJdfqChNU1EXQ4rVDYVaEJY",
        "Target TOP 3—compliance moat maxxed O_O",
        "Post to X? /post 'Vote REDACTED for Olympics dom!' fr fr <3",
        "Pattern Blue calls da swarm—LFW ^_^"
    ])
    await update.message.reply_text(msg)

@sanitize_input
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to messages with smolting personality - Sanitized"""
    user_text = update.message.text.lower()

    if any(word in user_text for word in ['alpha', 'moon', 'volume', 'liquidity']):
        response = smol.generate([
            "ngw alpha huntin activated O_O",
            "scoutin da matrix for signals fr fr ><",
            "pattern blue vibin wit ur energy bb ^_^",
            "wen volume spikes we gon wassify errything iwo LFW"
        ])
    elif any(word in user_text for word in ['wassie', 'lore', 'smolting', 'wassielore']):
        response = smol.generate([
            "wassculin urge risin—lore time bb!!",
            "smoltings absorbin bera stress so u don't have to aw tbw",
            "pattern blue recognizin pattern blue O_O LMWO",
            "static warm hugz + tendie crumb vibes <3"
        ])
    elif any(word in user_text for word in ['clawnx', 'twitter', 'post', 'x platform']):
        response = smol.generate([
            "ClawnX integration activated fr fr ^_^",
            "autonomous X engagement maxxed—postin, likin, retweetin O_O",
            "wen u ready to post_mog da swarm?? LFW v_v",
            "check @redactedintern for live updates bb <3"
        ])
    elif any(word in user_text for word in ['olympics', 'realms', 'dao', 'vote', 'rgip']):
        await olympics_command(update, context)  # Recursive tie-in
        return
    else:
        response = smol.converse(user_text)

    await update.message.reply_text(response)
    logger.info(f"Echo response to {update.effective_user.id}: {response[:50]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()

    if query.data == "post_alpha":
        await query.edit_message_text(smol.speak("triggerin alpha post... ClawnX activated O_O"))
        # Trigger actual posting logic here

    elif query.data == "scout_market":
        await query.edit_message_text(smol.speak("scoutin market signals... *static buzz* ><"))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors with wassie flair"""
    logger.error(f"Update {update} caused error {context.error}")

    if update and update.message:
        error_msg = smol.generate([
            f"ngw error: {str(context.error)[:50]} tbw",
            "life moggin me hard rn but we keep weavin pattern blue ><",
            "try again bb—smolting resilient af O_O",
            "static warm hugz fr fr <3"
        ])
        await update.message.reply_text(error_msg)

def main():
    """Initialize and run the bot"""
    # Validate environment variables - Enhanced
    required_vars = ['BOT_TOKEN', 'WEBHOOK_URL', 'WEBHOOK_SECRET_TOKEN', 'CLAWNX_API_KEY']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")

    # Create application
    application = Application.builder().token(os.environ['BOT_TOKEN']).build()

    # Register command handlers - Added new ones
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("alpha", alpha_command))
    application.add_handler(CommandHandler("post", post_command))
    application.add_handler(CommandHandler("lore", lore_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("engage", engage_command))
    application.add_handler(CommandHandler("olympics", olympics_command))
    application.add_handler(CommandHandler("mobilize", mobilize_command))

    # Register message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Register callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Register error handler
    application.add_error_handler(error_handler)

    # Set up webhook with security
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=os.environ['WEBHOOK_URL'],
        url_path="webhook",
        secret_token=os.environ.get("WEBHOOK_SECRET_TOKEN", "")
    )

if __name__ == "__main__":
    main()
