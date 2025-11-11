import json
import ollama
import os
from typing import Any, Dict, List

def load_memory():
    default_memory = {"history": []}

    if not os.path.exists("memory.json"):
        return default_memory

    try:
        with open("memory.json", "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_memory

    if isinstance(data, dict) and isinstance(data.get("history"), list):
        return data

    if isinstance(data, list):
        return {"history": data}

    return default_memory

def save_memory(memory):
    with open("memory.json", "w") as f:
        json.dump(memory, f, indent=2)

def load_persona():
    with open("persona.txt", "r") as f:
        return f.read()

def load_mood_meter():
    with open("mood_meter.json", "r") as f:
        return json.load(f)

def get_model_name() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1")

def main():
    model = get_model_name()
    persona = load_persona()
    memory = load_memory()
    mood_meter = load_mood_meter()

    print("🧠 Emotional Intelligence Chat\n")
    print("Type 'exit' to quit.\n")

    system_prompt = f"""{persona}

Here is the Mood Meter reference (for your internal use, do not print this unless asked):
{json.dumps(mood_meter, indent=2)}
"""

    # Initialize conversation history
    messages = [{"role": "system", "content": system_prompt}]
    messages += memory["history"]

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye 🌱\n")
            break

        messages.append({"role": "user", "content": user_input})

        # Ask Ollama
        try:
            response = ollama.chat(model=model, messages=messages)
        except Exception as error:
            print(f"\n⚠️  Unable to generate a response using model '{model}': {error}\n")
            print("Tip: ensure the model is installed locally or set OLLAMA_MODEL to another available model.\n")
            # remove the last user message so it can be retried with a different model later
            messages.pop()
            continue

        reply = response["message"]["content"].strip()
        print(f"\n🤖 {reply}\n")

        messages.append({"role": "assistant", "content": reply})
        memory["history"].append({"role": "user", "content": user_input})
        memory["history"].append({"role": "assistant", "content": reply})
        save_memory(memory)

if __name__ == "__main__":
    main()
