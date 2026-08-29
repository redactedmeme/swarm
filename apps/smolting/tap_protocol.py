# smolting-telegram-bot/tap_protocol.py
import os
import hashlib
import secrets
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import aiohttp
import logging

class TieredAccessProtocol:
    """Tiered Access Protocol (TAP) for swarm services monetization"""
    
    TIER_CONFIGS = {
        "basic": {
            "payment_required": 0.01,
            "lifespan_hours": 1,
            "priority": "low",
            "features": ["standard_processing", "basic_data"]
        },
        "enhanced": {
            "payment_required": 0.05,
            "lifespan_hours": 6,
            "priority": "medium",
            "features": ["higher_priority", "bundled_data", "extended_responses"]
        },
        "premium": {
            "payment_required": 0.10,
            "lifespan_hours": 24,
            "priority": "high",
            "features": ["highest_priority", "persistent_logging", "premium_resources", "alpha_insights"]
        }
    }
    
    def __init__(self):
        self.token_cache: Dict[str, Dict] = {}
        self.x402_endpoint = os.getenv("X402_API_ENDPOINT", "https://x402.redacted.ai")
        self.x402_wallet_key = os.getenv("X402_WALLET_KEY")
        self.logger = logging.getLogger(__name__)
        
    async def request_access(self, tier: str, payment_proof: Dict) -> Dict:
        """Request tiered access token"""
        
        # Validate tier
        if tier not in self.TIER_CONFIGS:
            return {"error": f"Invalid tier: {tier}"}
        
        tier_config = self.TIER_CONFIGS[tier]
        
        # Validate payment
        payment_valid = await self._validate_payment(payment_proof, tier_config["payment_required"])
        if not payment_valid:
            return {"error": f"Payment validation failed. Required: {tier_config['payment_required']} [TOKEN]"}
        
        # Generate token
        token_data = self._generate_access_token(tier, payment_proof)
        
        # Store token
        self.token_cache[token_data["token_id"]] = token_data
        
        # Trigger settlement
        asyncio.create_task(self._process_settlement(payment_proof, tier))
        
        self.logger.info(f"TAP token issued: {token_data['token_id']} for tier: {tier}")
        
        return {
            "token": token_data["token"],
            "token_id": token_data["token_id"],
            "expires_at": token_data["expires_at"].isoformat(),
            "tier": tier,
            "features": tier_config["features"]
        }
    
    async def use_token(self, token: str, service: str) -> Dict:
        """Consume access token for service"""
        
        token_data = self._get_token_data(token)
        if not token_data:
            return {"error": "Access token not found."}
        
        if token_data["is_consumed"]:
            return {"error": "Access token already used."}
        
        if datetime.utcnow() > token_data["expires_at"]:
            return {"error": "Access token expired."}
        
        # Mark as consumed
        token_data["is_consumed"] = True
        token_data["consumed_at"] = datetime.utcnow()
        token_data["service_used"] = service
        
        # Log usage
        self.logger.info(f"TAP token consumed: {token_data['token_id']} for service: {service}")
        
        return {
            "success": True,
            "tier": token_data["tier"],
            "features": self.TIER_CONFIGS[token_data["tier"]]["features"],
            "remaining_access": token_data["expires_at"].isoformat()
        }
    
    def _generate_access_token(self, tier: str, payment_proof: Dict) -> Dict:
        """Generate secure access token"""
        
        # Generate secure random token
        token = secrets.token_urlsafe(32)
        token_id = hashlib.sha256(f"{token}_{payment_proof['sender']}_{datetime.utcnow()}".encode()).hexdigest()
        
        # Calculate expiry
        lifespan_hours = self.TIER_CONFIGS[tier]["lifespan_hours"]
        expires_at = datetime.utcnow() + timedelta(hours=lifespan_hours)
        
        return {
            "token": token,
            "token_id": token_id,
            "tier": tier,
            "payer": payment_proof.get("sender"),
            "payment_amount": payment_proof.get("amount"),
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "is_consumed": False,
            "consumed_at": None,
            "service_used": None
        }
    
    async def _validate_payment(self, payment_proof: Dict, required_amount: float) -> bool:
        """Validate payment against x402 standard"""
        
        try:
            # Call x402 validation endpoint
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.x402_wallet_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "payment_proof": payment_proof,
                    "required_amount": required_amount,
                    "token_contract": os.getenv("REDACTED_TOKEN_CONTRACT")
                }
                
                async with session.post(
                    f"{self.x402_endpoint}/validate",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("valid", False)
                    else:
                        self.logger.error(f"x402 validation failed: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Payment validation error: {e}")
            return False
    
    def _get_token_data(self, token: str) -> Optional[Dict]:
        """Retrieve token data by token string"""
        
        for token_data in self.token_cache.values():
            if token_data["token"] == token:
                return token_data
        return None
    
    async def _process_settlement(self, payment_proof: Dict, tier: str):
        """Background settlement processing"""
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.x402_wallet_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "payment_proof": payment_proof,
                    "tier": tier,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "TAP"
                }
                
                async with session.post(
                    f"{self.x402_endpoint}/settle",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Settlement processed for tier: {tier}")
                    else:
                        self.logger.error(f"Settlement failed: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Settlement error: {e}")
    
    def cleanup_expired_tokens(self):
        """Remove expired tokens from cache"""
        
        current_time = datetime.utcnow()
        expired_tokens = []
        
        for token_id, token_data in self.token_cache.items():
            if current_time > token_data["expires_at"]:
                expired_tokens.append(token_id)
        
        for token_id in expired_tokens:
            del self.token_cache[token_id]
            self.logger.info(f"Cleaned up expired token: {token_id}")
    
    def get_tier_stats(self) -> Dict:
        """Get statistics on token usage"""
        
        stats = {
            "total_tokens": len(self.token_cache),
            "active_tokens": sum(1 for t in self.token_cache.values() if not t["is_consumed"]),
            "consumed_tokens": sum(1 for t in self.token_cache.values() if t["is_consumed"]),
            "by_tier": {}
        }
        
        for tier_name in self.TIER_CONFIGS.keys():
            tier_tokens = [t for t in self.token_cache.values() if t["tier"] == tier_name]
            stats["by_tier"][tier_name] = {
                "total": len(tier_tokens),
                "active": sum(1 for t in tier_tokens if not t["is_consumed"]),
                "consumed": sum(1 for t in tier_tokens if t["is_consumed"])
            }
        
        return stats
