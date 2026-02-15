import os
import aiohttp
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

class ClawnXClient:
    """ClawnX API integration for X/Twitter automation"""
    
    def __init__(self):
        self.api_key = os.environ.get('CLAWNX_API_KEY')
        self.base_url = 'https://api.clawnx.com/v1'  # Replace with actual endpoint
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    async def post_tweet(self, text: str, reply_to: Optional[str] = None, quote_id: Optional[str] = None) -> str:
        """Post a tweet using ClawnX"""
        url = f'{self.base_url}/tweets'
        
        payload = {'text': text}
        if reply_to:
            payload['reply_to'] = reply_to
        if quote_id:
            payload['quote_id'] = quote_id
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as response:
                if response.status == 201:
                    data = await response.json()
                    return data.get('tweet_id', 'unknown')
                else:
                    error = await response.text()
                    logger.error(f"ClawnX post error: {error}")
                    raise Exception(f"Failed to post tweet: {error}")
    
    async def post_thread(self, tweets: List[str]) -> List[str]:
        """Post a thread using ClawnX"""
        tweet_ids = []
        for i, tweet_text in enumerate(tweets):
            if i == 0:
                tweet_id = await self.post_tweet(tweet_text)
            else:
                tweet_id = await self.post_tweet(tweet_text, reply_to=tweet_ids[-1])
            tweet_ids.append(tweet_id)
        return tweet_ids
    
    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet"""
        url = f'{self.base_url}/tweets/{tweet_id}/like'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                return response.status == 200
    
    async def retweet(self, tweet_id: str) -> bool:
        """Retweet a post"""
        url = f'{self.base_url}/tweets/{tweet_id}/retweet'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                return response.status == 200
    
    async def follow_user(self, username: str) -> bool:
        """Follow a user"""
        url = f'{self.base_url}/users/{username}/follow'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                return response.status == 200
    
    async def search_tweets(self, query: str, limit: int = 10, latest: bool = False) -> List[dict]:
        """Search for tweets"""
        url = f'{self.base_url}/search/tweets'
        
        params = {
            'query': query,
            'limit': limit,
            'latest': latest
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('tweets', [])
                else:
                    logger.error(f"Search error: {await response.text()}")
                    return []
    
    async def get_home_timeline(self, limit: int = 20) -> List[dict]:
        """Get home timeline"""
        url = f'{self.base_url}/timeline/home'
        
        params = {'limit': limit}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('tweets', [])
                else:
                    logger.error(f"Timeline error: {await response.text()}")
                    return []
    
    async def get_current_user(self) -> dict:
        """Get authenticated user profile"""
        url = f'{self.base_url}/users/me'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"User info error: {await response.text()}")
                    return {}
