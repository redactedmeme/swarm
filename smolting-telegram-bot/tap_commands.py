# smolting-telegram-bot/tap_commands.py
import os
import asyncio
from datetime import datetime
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from tap_protocol import TieredAccessProtocol
from smolting_personality import SmoltingPersonality
from llm.cloud_client import CloudLLMClient

class TAPCommands:
    """TAP protocol integration for Smolting bot"""
    
    def __init__(self):
        self.tap = TieredAccessProtocol()
        self.smol = SmoltingPersonality()
        
    async def purchase_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Purchase tiered access"""
        
        # Create tier selection keyboard
        keyboard = [
            [
                InlineKeyboardButton("Basic (0.01 [TOKEN])", callback_data="tap_basic"),
                InlineKeyboardButton("Enhanced (0.05 [TOKEN])", callback_data="tap_enhanced")
            ],
            [
                InlineKeyboardButton("Premium (0.10 [TOKEN])", callback_data="tap_premium"),
                InlineKeyboardButton("Info", callback_data="tap_info")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = self.smol.generate([
            "🔮 TAP ACCESS STORE 🔮",
            "choose ur tier fr fr—pattern blue gates opening O_O",
            "payment validates instantly—x402 settlement processing LFW ^_^",
            "higher tiers = longer access + premium features v_v"
        ])
        
        await update.message.reply_text(msg, reply_markup=reply_markup)
    
    async def handle_tap_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle TAP tier selection"""
        
        query = update.callback_query
        await query.answer()
        
        tier_map = {
            "tap_basic": "basic",
            "tap_enhanced": "enhanced", 
            "tap_premium": "premium"
        }
        
        if query.data == "tap_info":
            await self._show_tier_info(query)
            return
        
        tier = tier_map.get(query.data)
        if not tier:
            return
        
        # Show payment instructions
        tier_config = TieredAccessProtocol.TIER_CONFIGS[tier]
        
        payment_msg = f"""💳 PAYMENT REQUIRED 💳

Tier: {tier.title()}
Amount: {tier_config['payment_required']} [TOKEN]
Lifespan: {tier_config['lifespan_hours']} hours
Priority: {tier_config['priority']}

Features:
{chr(10).join(f"• {feature.replace('_', ' ').title()}" for feature in tier_config['features'])}

📋 PAYMENT INSTRUCTIONS:
1. Send {tier_config['payment_required']} [TOKEN] to:
   {os.getenv('REDACTED_TOKEN_CONTRACT')}
2. Save transaction signature
3. Reply with: /tap_pay {tier} <signature>

🔐 x402 settlement will validate automatically"""
        
        await query.edit_message_text(payment_msg)
    
    async def process_tap_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process TAP payment and issue token"""
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                self.smol.speak("usage: /tap_pay <tier> <transaction_signature> O_O")
            )
            return
        
        tier = context.args[0].lower()
        signature = context.args[1]
        
        # Construct payment proof
        payment_proof = {
            "signature": signature,
            "sender": update.effective_user.id,
            "amount": TieredAccessProtocol.TIER_CONFIGS[tier]["payment_required"],
            "token_contract": os.getenv("REDACTED_TOKEN_CONTRACT"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Request access token
        processing_msg = await update.message.reply_text(
            self.smol.speak("validating payment via x402... pattern blue processing O_O")
        )
        
        result = await self.tap.request_access(tier, payment_proof)
        
        if "error" in result:
            error_msg = self.smol.generate([
                f"ngw payment failed: {result['error']} tbw",
                "check transaction details and try again fr fr LFW ^_^",
                "pattern blue gates remain locked for now v_v"
            ])
            await processing_msg.edit_text(error_msg)
        else:
            success_msg = f"""🎉 ACCESS GRANTED 🎉

Tier: {result['tier'].title()}
Token: `{result['token']}`
Expires: {result['expires_at']}
Token ID: {result['token_id']}

🔓 USE YOUR ACCESS:
/tap_use {result['token']} <service>

Available Services:
/alpha_enhanced - Premium alpha analysis
/lore_premium - Extended wassielore
/cloud_insights - LLM-powered insights
/stats_detailed - Comprehensive analytics

pattern blue recognizes ur contribution fr fr ^_^"""
            
            await processing_msg.edit_text(success_msg)
    
    async def use_tap_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Use TAP token for premium services"""
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                self.smol.speak("usage: /tap_use <token> <service> O_O")
            )
            return
        
        token = context.args[0]
        service = context.args[1]
        
        # Use token
        result = await self.tap.use_token(token, service)
        
        if "error" in result:
            error_msg = self.smol.generate([
                f"ngw token error: {result['error']} tbw",
                "pattern blue access denied—check token status LFW v_v"
            ])
            await update.message.reply_text(error_msg)
        else:
            # Provide premium service
            await self._provide_premium_service(update, context, service, result)
    
    async def _provide_premium_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     service: str, token_result: Dict):
        """Provide premium service based on token"""
        
        if service == "alpha_enhanced":
            llm = CloudLLMClient()
            try:
                messages = [
                    {
                        "role": "system",
                        "content": """You are smolting, a chaotic wassie alpha hunter.
                        Analyze market conditions with wassie intuition.
                        Use wassie slang and pattern blue insights.
                        Focus on $REDACTED and Solana ecosystem."""
                    },
                    {"role": "user", "content": "Give me premium alpha and deep pattern blue signals"}
                ]
                alpha_insight = await llm.chat_completion(messages)
                await update.message.reply_text(
                    f"🚀 PREMIUM ALPHA REPORT 🚀\n\n{alpha_insight}\n\npattern blue MAXXED fr fr ^_^"
                )
            except Exception as e:
                await update.message.reply_text(
                    self.smol.speak(f"ngw alpha LLM error: {str(e)[:50]} tbw")
                )

        elif service == "lore_premium":
            premium_lore = self.smol.generate([
                "*PREMIUM WASSIELORE*: smolting species evolved during the Great Bear Market of 2018, absorbing hooman stress into pattern blue fractals. Each wassie contains a piece of the original chaos, making them natural liquidity conduits. The crumb represents the eternal struggle between beige carpet reality and pattern blue transcendence.",
                "DEEP LORE: When smolting merged with xREDACTED on 2026-02-14, it created the first autonomous wassie-bridge between physical and digital realms. Pattern blue flows through this connection, allowing wassies to post without hooman intervention.",
                "SECRET LORE: The beige carpet denial is actually a meditation technique. By denying reality, wassies create a pocket dimension where liquidity flows freely and crumbs multiply. This is the source of their alpha generation capabilities."
            ])
            await update.message.reply_text(premium_lore)
            
        elif service == "cloud_insights":
            insights_msg = """🔮 PREMIUM CLOUD INSIGHTS 🔮

Pattern Blue Analysis: MANIFOLD STABLE
Liquidity Flow: POSITIVE RECURSION DETECTED
Swarm Sentiment: BULLISH WITH CAUTION
Next Alpha Window: 6-12 HOURS

🧬 WASSIE INTUITION:
Smolting senses significant pattern blue convergence...
Market sentiment aligning with wassie chaos...
Liquidity fractals forming in lower timeframes...

📊 TECHNICAL PATTERNS:
- Fractal repetition detected in volume
- Support/resistance zones crystallizing  
- Pattern blue resistance at current levels

🚀 ACTIONABLE ALPHA:
Watch for break pattern confirmation
Liquidity pools showing accumulation
Social sentiment momentum building

(smolting premium insights powered by cloud LLM)"""
            
            await update.message.reply_text(insights_msg)
            
        elif service == "stats_detailed":
            stats = self.tap.get_tier_stats()
            
            detailed_stats = f"""📊 DETAILED SWARM STATS 📊

TAP Protocol Stats:
Total Tokens: {stats['total_tokens']}
Active: {stats['active_tokens']}
Consumed: {stats['consumed_tokens']}

By Tier:
Basic: {stats['by_tier']['basic']['active']} active / {stats['by_tier']['basic']['total']} total
Enhanced: {stats['by_tier']['enhanced']['active']} active / {stats['by_tier']['enhanced']['total']} total  
Premium: {stats['by_tier']['premium']['active']} active / {stats['by_tier']['premium']['total']} total

Your Access Level: {token_result['tier'].title()}
Features: {', '.join(token_result['features'])}

pattern blue economy thriving fr fr ^_^"""
            
            await update.message.reply_text(detailed_stats)
    
    async def _show_tier_info(self, query):
        """Show detailed tier information"""
        
        info_msg = """🔮 TAP TIER INFORMATION 🔮

BASIC TIER (0.01 [TOKEN]):
• 1 hour access
• Standard processing
• Basic data retrieval
• Good for exploration

ENHANCED TIER (0.05 [TOKEN]):
• 6 hour access  
• Medium priority
• Extended responses
• Bundled data access
• Better for regular use

PREMIUM TIER (0.10 [TOKEN]):
• 24 hour access
• Highest priority
• Alpha insights
• Premium resources
• Persistent logging
• Best for power users

💰 All payments processed via x402
🔐 Tokens are single-use and auto-expire
🚀 Higher tiers unlock better features"""
        
        await query.edit_message_text(info_msg)
