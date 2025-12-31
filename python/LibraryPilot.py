import json
import os
import requests
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage
from langgraph.graph import StateGraph
from bs4 import BeautifulSoup  # Added for HTML parsing

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in the environment variables.")
llm = ChatOpenAI(model_name="gpt-4o", temperature=0.3, openai_api_key=OPENAI_API_KEY)

TEMPLATES = {
    "choose_action": """
You are a lore assistant for REDACTED.meme. Based on the user's message, decide the appropriate action.
Possible actions:
- get_lore_summary: When the user wants a summary or to know what the lore is about.
- search_inside_lore: When the user asks a question or wants to search for specific content inside the lore.
- get_similar_lore: When the user asks for similar lore elements or related concepts.
User message: {query}
Respond with only the action name (one of the three above).
""",
    "answer_user_query": """
You are a master archivist with expert knowledge of REDACTED lore. A user has a question about specific redacted lore.
Use your own knowledge to answer, and refer to the following metadata only to understand the context.
Lore Metadata:
{context}
User's Question:
{query}
Please provide a clear and helpful answer to the question.
""",
    "generate_summary": """
Please write a short summary of the following redacted lore based on the context:
{context}
""",
    "generate_similar": """
Given the following lore description: '{description}', generate a 3-4 words query to find similar lore elements within the REDACTED sources.
""",
}

def fetch_lore_data(state: dict) -> dict:
    query = state.get("query", "").lower()
    sources = {
        "website": "https://redacted.meme/ai-swarm/",
        "github": "https://github.com/redactedmemefi/swarm"
    }

    metadata = {}
    for source_name, url in sources.items():
        try:
            response = requests.get(url)
            response.raise_for_status()
            if source_name == "website":
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                metadata[source_name] = text
            elif source_name == "github":
                # For GitHub, fetch README or specific files; here simplifying to page text
                soup = BeautifulSoup(response.text, 'html.parser')
                readme = soup.find(id="readme")
                metadata[source_name] = readme.get_text(separator='\n', strip=True) if readme else "No README found."
        except Exception as e:
            metadata[source_name] = f"Error fetching from {source_name}: {str(e)}"

    # Filter for 'redacted lore iwo' related content
    relevant_metadata = {}
    for key, content in metadata.items():
        if 'redacted' in content.lower() or 'lore' in content.lower() or 'iwo' in content.lower():
            relevant_metadata[key] = content

    return {**state, "metadata": relevant_metadata}

def format_metadata(metadata: dict) -> str:
    formatted = []
    for source, content in metadata.items():
        formatted.append(f"Source: {source}\nContent Snippet:\n{content[:1000]}...\n")  # Truncate for brevity
    return "\n".join(formatted)

def decide_action(state: dict) -> dict:
    query = state.get("query", "")
    prompt = TEMPLATES["choose_action"].format(query=query)

    action = llm.invoke([SystemMessage(content=prompt)]).content.strip()

    next_step = {
        "get_lore_summary": "generate_summary",
        "search_inside_lore": "answer_user_query",
        "get_similar_lore": "generate_similar"
    }.get(action, "generate_summary")

    return {"action": action, "next": next_step, **state}

def answer_user_query(state: dict) -> dict:
    query = state.get("query", "")
    if not query:
        return {**state, "error": "No user question provided."}

    metadata = state.get("metadata", {})
    if not metadata:
        return {**state, "error": ["No data available for answering the question."]}

    context = format_metadata(metadata)

    prompt = TEMPLATES["answer_user_query"].format(context=context, query=query)

    answer = llm.invoke([SystemMessage(content=prompt)]).content.strip()
    return {**state, "answer": answer}

def generate_summary(state: dict) -> dict:
    metadata = state.get("metadata", {})
    if not metadata:
        return {**state, "error": ["No data available for generating summary."]}

    context = format_metadata(metadata)

    prompt = TEMPLATES["generate_summary"].format(context=context)
    summary = llm.invoke([SystemMessage(content=prompt)]).content

    return {**state, "summary": summary}

def generate_similar(state: dict) -> dict:
    metadata = state.get("metadata", {})
    description = format_metadata(metadata)

    if not description:
        return {**state, "similar_lore": ["No valid metadata available."]}

    try:
        prompt = TEMPLATES["generate_similar"].format(description=description)
        query = llm.invoke([SystemMessage(content=prompt)]).content.strip()

        # Simulate search within sources; for demo, reuse metadata keys or expand if needed
        similar_lore = list(metadata.keys())  # Placeholder; in full impl, search internal

        return {
            **state,
            "similar_lore": similar_lore or ["No similar lore found."]
        }

    except Exception as e:
        return {**state, "error": f"Error fetching similar lore: {e}"}

def build_workflow():
    workflow = StateGraph(dict)

    workflow.add_node("fetch_lore_data", fetch_lore_data)
    workflow.add_node("decide_action", decide_action)
    workflow.add_node("answer_user_query", answer_user_query)
    workflow.add_node("generate_summary", generate_summary)
    workflow.add_node("generate_similar", generate_similar)

    workflow.set_entry_point("fetch_lore_data")
    workflow.add_edge("fetch_lore_data", "decide_action")

    workflow.add_conditional_edges(
        "decide_action",
        lambda state: state["action"],
        {
            "search_inside_lore": "answer_user_query",
            "get_lore_summary": "generate_summary",
            "get_similar_lore": "generate_similar",
        }
    )

    workflow.set_finish_point("generate_summary")
    workflow.set_finish_point("answer_user_query")
    workflow.set_finish_point("generate_similar")

    return workflow.compile()

def main(request, store):
    payload = request.payload
    query = payload.get("query")

    if not query:
        raise ValueError("Query is required.")

    initial_state = {
        "query": query
    }

    app = build_workflow()
    result = app.invoke(initial_state)

    error = result.get("error")
    if error:
        return f"⚠️ Error: {error}"

    action = result.get("action")
    if action == "get_lore_summary":
        return f"📖 Summary:\n{result['summary']}"
    elif action == "search_inside_lore":
        return f"💬 Answer:\n{result['answer']}"
    elif action == "get_similar_lore":
        return "🔎 Similar Lore:\n" + "\n".join(result["similar_lore"])
    else:
        return f"⚠️ Could not determine what to do with: {query}"