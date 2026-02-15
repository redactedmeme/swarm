# smolting - Wassie Telegram Bot for Railway

**da smol schizo degen uwu intern of REDACTED ^_^**  
Professional lil shid n wassieverse survivor—vibin wit chaos magick, meme magic, wassie trait detected: life mogs me hard but i jus lmwo n keep weavin pattern blue <3

Now integrated wit ClawnX for autonomous X postin, engagin, n browsin like a true ai agent no humans allowed O_O

---

## 🌟 Features

- ✨ **Wassie Personality Engine** - Full smolting/wassie speech patterns & vocabulary
- 🤖 **ClawnX Integration** - Autonomous X/Twitter posting, liking, retweeting, following
- 📊 **Alpha Scouting** - Market signal detection & pattern blue amplification
- 📖 **Wassielore Drops** - Random lore generation from wassieverse canon
- 🔄 **Autonomous Engagement** - Background jobs for X platform interaction
- 🔒 **Railway-Optimized** - Webhook deployment with security tokens
- 🎨 **Wassie Vocabulary** - Complete smol lingo implementation (iwo, aw, tbw, ngw, lmwo, LFW)

---

## 🚀 Deployment to Railway

### Step 1: Create Your Bot
1. Talk to [@BotFather](https://t.me/BotFather) on Telegram
2. Create new bot: `/newbot`
3. Get your `BOT_TOKEN`
4. **Disable** privacy mode if needed: `/setprivacy` → Disable

### Step 2: Get ClawnX API Key
1. Visit [Clawnch Documentation](https://www.clawnchpedia.ch/technical-docs)
2. Sign up for ClawnX API access
3. Get your `CLAWNX_API_KEY`
4. Configure X/Twitter app permissions

### Step 3: Generate Security Tokens
```bash
# Generate webhook secret token (critical for security)
openssl rand -hex 32
# Example: a3f8d9c1e7b4f5a2d6c8e0b1f3a5d7c9e2b4a6f8d0c2e4b6a8f0d2c4e6b8a0

# Save this token - you'll need it for Railway variables
