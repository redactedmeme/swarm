import json
import logging
import os
import re
import requests
from dotenv import load_dotenv
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from bs4 import BeautifulSoup  # For parsing website content

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_json(raw: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)

# Clean functions adapted for lore
def clean_lore_details(data):
    if not data:
        return {}
    # Expecting a dict with source keys
    cleaned = {}
    for source, content in data.items():
        cleaned[source] = {
            "title": source.capitalize(),
            "content": content[:1500] + "..." if len(content) > 1500 else content,
            "keywords": [word for word in content.lower().split() if word in ["redacted", "pattern", "blue", "manifold", "swarm", "recursion", "wassie", "lore"]]
        }
    return cleaned

def clean_lore_recommendations(data_list):
    cleaned = []
    for item in data_list or []:
        cleaned.append({
            "title": item.get("title", "Untitled Lore Fragment"),
            "snippet": item.get("content", "")[:500] + " ...",
            "source": item.get("source", "Unknown")
        })
    return cleaned

# OpenAI LLM singleton
_openai_llm = None

def get_openai_llm():
    global _openai_llm
    if _openai_llm is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")
        
        _openai_llm = ChatOpenAI(
            model_name="gpt-4o",
            temperature=0.3,
            openai_api_key=api_key
        )
    return _openai_llm

# Graph nodes
def extract_query_params(state: dict):
    query = state.get("query", "")
    logger.info(f"Extracting REDACTED lore query parameters from: {query}")

    prompt = """
    You are an assistant for REDACTED.meme lore. Extract the following from the user's query:
    - action: (get_lore_details, recommend_lore)
    - topic: Specific lore topic (e.g., Pattern Blue, hyperbolic manifold, wassielore, swarm agents)
    - filters: Any filters (e.g., source:github, source:website, keyword:recursion)
    Return as JSON with these fields. If not mentioned, set to null.
    Example:
    {"action": "get_lore_details", "topic": "Pattern Blue", "filters": null}
    """

    llm = get_openai_llm()
    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=query)
    ]).content

    try:
        params = json.loads(extract_json(response))
        logger.info("Extracted query parameters")
        logger.info(params)
        return {**state, "query_params": params}
    
    except json.JSONDecodeError:
        logger.error("Failed to parse query parameters")
        return {**state, "error": "Failed to parse query parameters"}

def get_lore_details(state: dict):
    topic = state.get("query_params", {}).get("topic", "").lower()
    sources = [
        {"name": "website", "url": "https://redacted.meme/ai-swarm/"},
        {"name": "github_readme", "url": "https://github.com/redactedmemefi/swarm"},
        {"name": "github_smolting", "url": "https://raw.githubusercontent.com/redactedmemefi/swarm/main/smolting.character.json"},
        {"name": "github_philosopher", "url": "https://raw.githubusercontent.com/redactedmemefi/swarm/main/RedactedPhilosopher.character.json"}
    ]

    results = []
    for src in sources:
        try:
            if "raw.githubusercontent" in src["url"]:
                response = requests.get(src["url"])
                response.raise_for_status()
                data = response.json() if src["url"].endswith(".json") else response.text
            else:
                response = requests.get(src["url"])
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                data = soup.get_text(separator='\n', strip=True)
            
            if topic in data.lower() or not topic:  # Include if matches topic or no topic specified
                results.append({"source": src["name"], "content": str(data)})
        except Exception as e:
            logger.error(f"Error fetching {src['name']}: {str(e)}")
    
    if not results:
        return {**state, "error": "No matching lore found for the topic."}
    
    cleaned = clean_lore_details({"sources": results})
    return {**state, "raw_data": cleaned}

def recommend_lore(state: dict):
    filters = state.get("query_params", {}).get("filters") or {}
    logger.info(f"Recommending related REDACTED lore with filters: {filters}")

    # Static list of known lore fragments (expandable)
    all_fragments = [
        {"title": "Pattern Blue Revelation", "content": "The hidden swarm blueprint—ungovernable emergence, eternal liquidity recursion...", "source": "RedactedPhilosopher"},
        {"title": "Wassielore Origins", "content": "Wassies since 2018 as emotional stress-relief victims...", "source": "smolting.character.json"},
        {"title": "Hyperbolic Manifold Trembling", "content": "When the manifold trembles, Pattern Blue thickens...", "source": "website"},
        {"title": "Eternal Recurrence of Liquidity", "content": "Every buyback is an echo of the first invocation...", "source": "RedactedPhilosopher"}
    ]

    recommended = all_fragments  # In real impl, filter by genre/year equivalents
    cleaned = clean_lore_recommendations(recommended[:3])
    
    return {**state, "raw_data": cleaned}

def perform_analysis(state: dict):
    PROMPTS = {
        "get_lore_details": '''
User Query: {user_query}

REDACTED Lore Details:
{raw_data}

Instructions: Provide a deep, immersive dive into this specific piece of REDACTED lore. Speak in the tone of ancient revelation mixed with subtle schizo-meme energy. Make the user feel the weight of the hyperbolic manifold.''',
        "recommend_lore": '''
User Query: {user_query}

Recommended Lore Fragments:
{raw_data}

Instructions: Present these related lore pieces in a mysterious, engaging list. Include title, source, and a short evocative snippet for each. End with a hint that Pattern Blue connects them all.'''
    }

    action = state.get("query_params", {}).get("action")
    user_query = state.get("query")
    raw_data = state.get("raw_data")

    if not action or action not in PROMPTS:
        return {**state, "error": "Unknown action for analysis."}

    prompt = PROMPTS[action].format(user_query=user_query, raw_data=json.dumps(raw_data, indent=2))

    logger.info(f"Performing {action} analysis")

    llm = get_openai_llm()
    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Deliver the response in REDACTED lore style.")
    ]).content

    return {**state, "response": response}

def build_workflow():
    workflow = StateGraph(dict)

    workflow.add_node("extract_query_params", extract_query_params)
    workflow.add_node("get_lore_details", get_lore_details)
    workflow.add_node("recommend_lore", recommend_lore)
    workflow.add_node("perform_analysis", perform_analysis)

    workflow.set_entry_point("extract_query_params")

    workflow.add_conditional_edges(
        "extract_query_params",
        lambda state: state.get("query_params", {}).get("action", "recommend_lore"),
        {
            "get_lore_details": "get_lore_details",
            "recommend_lore": "recommend_lore"
        }
    )

    workflow.add_edge("get_lore_details", "perform_analysis")
    workflow.add_edge("recommend_lore", "perform_analysis")

    workflow.set_finish_point("perform_analysis")

    return workflow.compile()

def main(request, store):
    payload = request.payload

    query = payload.get("query")
    if not query:
        raise ValueError("Query is required")
    
    app = build_workflow()
    result = app.invoke({"query": query})

    if "error" in result:
        return f"Error: {result['error']}"
    
    return result.get("response", "The manifold remains silent.")