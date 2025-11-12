import json
import ollama
import os
from datetime import datetime
from typing import Any, Dict, List

# === File Paths ===
MEMORY_PATH = "memory.json"      # short-term conversation + summary
SESSIONS_PATH = "sessions.json"  # session summaries
PROFILE_PATH = "profile.json"    # long-term profile
PERSONA_PATH = "persona.txt"
SUMMARIZE_PROMPT_PATH = "summarize_prompt.txt"

# === Helper Functions ===
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_persona():
    with open(PERSONA_PATH, "r") as f:
        return f.read()

def load_summarize_prompt():
    with open(SUMMARIZE_PROMPT_PATH, "r") as f:
        return f.read()

# === Memory Loaders ===
def load_memory():
    raw = load_json(MEMORY_PATH, None)
    if raw is None:
        return {"history": [], "summary": ""}
    
    history = raw.get("history", [])
    summary = raw.get("summary", "")

    # Handle old format without "summary"
    if "summary" not in raw:
        if len(history) > 6:
            recent = history[-6:]
            old_messages = history[:-6]
            old_summary = json.dumps(old_messages, indent=2)
            summary = f"Previous conversation:\n{old_summary}"
            history = recent
        else:
            summary = ""
    return {"history": history, "summary": summary}

def save_memory(memory): save_json(MEMORY_PATH, memory)
def load_sessions(): return load_json(SESSIONS_PATH, [])
def save_sessions(sessions): save_json(SESSIONS_PATH, sessions)
def load_profile(): return load_json(PROFILE_PATH, {
    "name": "Unknown",
    "emotional_themes": [],
    "growth_goals": [],
    "preferred_tone": "gentle and curious",
    "progress_notes": []
})
def save_profile(profile): save_json(PROFILE_PATH, profile)

def get_model_name() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3:latest")

# === Summarization Helpers ===
def summarize_session(model, messages, persona):
    summarize_prompt = load_summarize_prompt()
    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": summarize_prompt}] + messages
    )
    return response["message"]["content"].strip()

def summarize_short_term(model, persona, memory):
    if not memory["history"]:
        return ""
    summary_prompt = f"""{persona}

Summarize the following conversation in 2–3 sentences, focusing on emotional tone and key reflections. 
Avoid repeating exact user words. Keep it human and concise.

Conversation:
{json.dumps(memory['history'], indent=2)}
"""
    response = ollama.chat(model=model, messages=[{"role": "system", "content": summary_prompt}])
    return response["message"]["content"].strip()

def update_profile(model, persona, profile, summary):
    profile_update_prompt = f"""{persona}

Here is the user's long-term emotional profile:
{json.dumps(profile, indent=2)}

Update the profile with any new emotional themes, growth insights, or progress from this session summary:
{summary}

Return the updated profile as valid JSON. If unsure, leave the profile unchanged.
"""
    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": profile_update_prompt}]
    )
    content = response["message"]["content"].strip()
    try:
        return json.loads(content)
    except:
        profile["progress_notes"].append({
            "date": str(datetime.now().date()),
            "note": summary
        })
        return profile

# === Main Chat Loop ===
def main():
    model = get_model_name()
    persona = load_persona()
    memory = load_memory()
    sessions = load_sessions()
    profile = load_profile()

    # System prompt with persona + profile
    system_prompt = f"""{persona}

Here is what you currently know about the user:
{json.dumps(profile, indent=2)}
"""
    messages = [{"role": "system", "content": system_prompt}]
    messages += memory["history"]

    # === Initial greeting ===
    print("🧠 e-cue Emotional Intelligence Chat\n")
    print("🤖 Hey, how are you feeling?\n")
    print("Type 'exit' to end the session.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            print("\n🌱 Reflecting on this session...\n")

            # Summarize entire session
            summary = summarize_session(model, messages, persona)
            print("🪞 Session summary:\n", summary, "\n")

            # Save session summary
            sessions.append({
                "date": str(datetime.now().date()),
                "summary": summary
            })
            save_sessions(sessions)

            # Update long-term profile
            profile = update_profile(model, persona, profile, summary)
            save_profile(profile)

            # Clear short-term memory
            save_memory({"history": [], "summary": ""})

            print("Session saved. Goodbye 🌿\n")
            break

        # Add user message
        messages.append({"role": "user", "content": user_input})
        memory["history"].append({"role": "user", "content": user_input})

        # Prepare context: system prompt + short-term summary + last few messages
        context_messages = [{"role": "system", "content": system_prompt}]
        if memory.get("summary"):
            context_messages.append({"role": "system", "content": memory["summary"]})
        context_messages += memory["history"][-6:]

        # Get AI reply
        response = ollama.chat(model=model, messages=context_messages)
        reply = response["message"]["content"].strip()

        print(f"\n🤖 {reply}\n")
        messages.append({"role": "assistant", "content": reply})
        memory["history"].append({"role": "assistant", "content": reply})

        # Summarize short-term memory every 15 messages
        if len(memory["history"]) >= 15:
            new_summary = summarize_short_term(model, persona, memory)
            if memory.get("summary"):
                memory["summary"] += "\n" + new_summary
            else:
                memory["summary"] = new_summary
            # Keep only last 6 messages for natural flow
            memory["history"] = memory["history"][-6:]

        # Save short-term memory
        save_memory(memory)

if __name__ == "__main__":
    main()
