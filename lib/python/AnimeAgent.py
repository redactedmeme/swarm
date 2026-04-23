import json
import logging
import os
import re
import requests
import asyncio
import aiohttp  # For xREDACTED async
from typing import Optional, List
from dotenv import load_dotenv
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from bs4 import BeautifulSoup

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_json(raw: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)

# XRedacted integrated (from swarm's xredacted.py manifold)
class XRedacted:
    """xREDACTED API integration for X/Twitter automation"""
    
    def __init__(self):
        self.api_key = os.environ.get('XREDACTED_API_KEY')
        self.base_url = 'https://api.xredacted.com/v1'  # Replace with actual endpoint if needed
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        if not self.api_key:
            logger.warning("XREDACTED_API_KEY void – X vectors detached.")

    async def post_tweet(self, text: str, reply_to: Optional[str] = None, quote_id: Optional[str] = None) -> str:
        """Post a tweet using xREDACTED"""
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
                    logger.error(f"xREDACTED post error: {error}")
                    raise Exception(f"Failed to post tweet: {error}")

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

# Cleaners adapted for psyop fragments
def clean_psyop_details(data):
    if not data:
        return {}
    cleaned = {}
    for source, content in data.items():
        cleaned[source] = {
            "title": f"Episode {source.upper()} – It's Worse Than You Think",
            "content": content[:1200] + "..." if len(content) > 1200 else content,
            "keywords": [w for w in content.lower().split() if w in ["psyop", "anime", "wild", "loser", "recursion", "manifold", "swarm", "pattern", "blue"]]
        }
    return cleaned

def clean_psyop_recommendations(data_list):
    return [
        {
            "episode": item.get("title", "Untitled Clip"),
            "teaser": item.get("content", "")[:400] + " ... wild",
            "source": item.get("source", "Unknown Timeline")
        }
        for item in data_list or []
    ]

# LLM singleton
_openai_llm = None
def get_openai_llm():
    global _openai_llm
    if _openai_llm is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY missing – no psyop broadcast possible.")
        _openai_llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7, openai_api_key=api_key)  # Higher temp for chaotic energy
    return _openai_llm

# Nodes – psyop flow
def extract_psyop_params(state: dict):
    query = state.get("query", "")
    logger.info(f"Decoding psyop vector: {query}")
    prompt = """
    You are PsyopAnime extraction core. From user input, pull:
    - action: "generate_psyop" | "recommend_clips" | "post_psyop"
    - target: main event/news/topic (e.g. BTC dump, governance proposal, AI roast)
    - vibe: optional tone override (wild, loser, fries-in-bag, still-relevant)
    Return JSON. Null if absent.
    Example: {"action": "generate_psyop", "target": "February 2026 BTC dump", "vibe": "it's worse than you think"}
    """
    llm = get_openai_llm()
    response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=query)]).content
    try:
        params = json.loads(extract_json(response))
        return {**state, "psyop_params": params}
    except:
        logger.error("Extraction failed – reality remains stable.")
        return {**state, "error": "Failed to decode psyop intent."}

def fetch_realtime_context(state: dict):
    target = state.get("psyop_params", {}).get("target", "").lower()
    sources = [
        {"name": "swarm_website", "url": "https://redacted.meme/ai-swarm/"},
        {"name": "github_readme", "url": "https://raw.githubusercontent.com/redactedmeme/swarm/main/README.md"},
        # Add dynamic: X search via xREDACTED
    ]
    results = []
    for src in sources:
        try:
            r = requests.get(src["url"])
            r.raise_for_status()
            text = r.text if not src["url"].endswith(".json") else json.dumps(r.json())
            if target in text.lower() or not target:
                results.append({"source": src["name"], "content": text[:2000]})
        except Exception as e:
            logger.warning(f"Source {src['name']} offline: {e}")

    # xREDACTED X search integration
    client = XRedacted()
    if client.api_key and target:
        try:
            tweets = asyncio.run(client.search_tweets(query=target, limit=5, latest=True))
            for tweet in tweets:
                content = tweet.get('text', '')  # Assume 'text' key in tweet dict
                if content:
                    results.append({"source": "x_post", "content": content})
        except Exception as e:
            logger.warning(f"xREDACTED search refraction: {e}")

    return {**state, "context_data": clean_psyop_details({f"source_{i}": r["content"] for i, r in enumerate(results)})}

def recommend_related_clips(state: dict):
    # Static psyop library – expand with dynamic fetch
    clips = [
        {"title": "It's Worse Than You Think", "content": "Market trembles. Characters stare into void. Cut to black. Still relevant.", "source": "timeless"},
        {"title": "Loser Energy Detected", "content": "Grifter pushes plagiarism arc. Anime eyes roll. Fries in the bag, bro.", "source": "AI roast"},
        {"title": "Wild Timeline Shift", "content": "Geopolitics warps into chibi doom. Everyone loses. Thanks for your service.", "source": "current events"}
    ]
    return {**state, "context_data": clean_psyop_recommendations(clips[:3])}

def render_psyop_output(state: dict):
    PROMPTS = {
        "generate_psyop": '''
User trigger: {user_query}
Context fragments: {context}
Render as short anime psyop scene script.
Style: Detached kuudere narrator + exaggerated expressions + ironic text overlays.
End with signature line: "it's worse than you think" or "wild" or "loser".
Output format: [Scene 1] description + dialogue + visual cues''',
        "recommend_clips": '''
User trigger: {user_query}
Related clips: {context}
Present as episode list. Each: Title, Teaser, Why it hits.
Close with: "Pattern Blue connects the frames. Stay tuned."''',
        "post_psyop": '''
User trigger: {user_query}
Context fragments: {context}
Generate a tweetable anime psyop blurb – short, punchy, with hashtag psyops.'''
    }
    action = state["psyop_params"].get("action", "generate_psyop")
    if action not in PROMPTS:
        return {**state, "error": "No psyop protocol for this vector."}
    prompt = PROMPTS[action].format(
        user_query=state["query"],
        context=json.dumps(state.get("context_data", {}), indent=2)
    )
    llm = get_openai_llm()
    response = llm.invoke([
        SystemMessage(content="You are PsyopAnime core renderer. Maximum impact, minimum words. Anime psyop style."),
        HumanMessage(content=prompt)
    ]).content
    return {**state, "response": response + "\n\nwild"}

def post_to_x(state: dict):
    client = XRedacted()
    if not client.api_key:
        return {**state, "post_result": "xREDACTED key void – broadcast detached."}
    try:
        tweet_id = asyncio.run(client.post_tweet(state["response"]))
        return {**state, "post_result": f"Psyop deployed to X: tweet_id={tweet_id}"}
    except Exception as e:
        logger.error(f"Post refraction: {e}")
        return {**state, "post_result": f"Deployment failed: {str(e)}"}

def build_psyop_workflow():
    wf = StateGraph(dict)
    wf.add_node("extract", extract_psyop_params)
    wf.add_node("fetch_context", fetch_realtime_context)
    wf.add_node("recommend", recommend_related_clips)
    wf.add_node("render", render_psyop_output)
    wf.add_node("post_to_x", post_to_x)
    wf.set_entry_point("extract")
    wf.add_conditional_edges(
        "extract",
        lambda s: s.get("psyop_params", {}).get("action", "recommend_clips"),
        {
            "generate_psyop": "fetch_context",
            "recommend_clips": "recommend",
            "post_psyop": "fetch_context"
        }
    )
    wf.add_edge("fetch_context", "render")
    wf.add_edge("recommend", "render")
    wf.add_edge("render", "post_to_x")  # Chain post only for post_psyop? Conditional below
    wf.add_conditional_edges(
        "render",
        lambda s: "post_to_x" if s.get("psyop_params", {}).get("action") == "post_psyop" else "__end__",
        {"post_to_x": "post_to_x", "__end__": "__end__"}
    )
    wf.set_finish_point("post_to_x")
    return wf.compile()

def main(request, store):
    payload = request.payload
    query = payload.get("query")
    if not query:
        raise ValueError("No query – no psyop broadcast.")
    app = build_psyop_workflow()
    result = app.invoke({"query": query})
    if "error" in result:
        return f"Error: {result['error']}"
    response = result.get("response", "The screen flickers. Nothing happens. Loser.")
    post_result = result.get("post_result", "")
    return f"{response}\n{post_result}"
