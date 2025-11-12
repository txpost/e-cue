import json
import itertools
import sys
import threading
import time
from datetime import datetime
import ollama


MODEL = "llama3:latest"


# ==============================
# Spinner animation
# ==============================
class Spinner:
    spinner_cycle = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

    def __init__(self, message="Thinking"):
        self.message = message
        self.stop_running = threading.Event()
        self.thread = threading.Thread(target=self.init_spinner)

    def init_spinner(self):
        while not self.stop_running.is_set():
            sys.stdout.write(f"\r{self.message} {next(self.spinner_cycle)}")
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write("\r" + " " * (len(self.message) + 4) + "\r")
        sys.stdout.flush()

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_running.set()
        self.thread.join()


# ==============================
# File handling
# ==============================
def load_json(filename, default):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


# ==============================
# Load system files
# ==============================
def load_persona():
    try:
        with open("persona.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are e-cue, a calm and empathetic emotional intelligence guide."


def load_summarize_prompt():
    try:
        with open("summarize_prompt.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return (
            "Summarize this session in 3–5 sentences capturing emotional tone, key insights, and themes. "
            "Be concise but human."
        )


# ==============================
# Summarization
# ==============================
def fallback_summary(messages, label="session"):
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    if not user_msgs:
        return f"(no {label} activity)"
    return f"Summary of {label}: " + " | ".join(user_msgs[-3:])


def summarize_session(model, messages, persona):
    summarize_prompt = load_summarize_prompt()

    # Extract only user and assistant messages (skip system)
    dialogue = [m for m in messages if m["role"] in ("user", "assistant")]

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": summarize_prompt},
                {"role": "user", "content": json.dumps(dialogue, indent=2)},
            ],
        )
        content = response.get("message", {}).get("content", "")
        if content and content.strip():
            return content.strip()
    except Exception as exc:
        print(f"[warn] summarize_session fallback due to error: {exc}")

    return fallback_summary(messages, label="session")


# ==============================
# Memory management
# ==============================
def normalize_history_entries(history):
    normalized = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        summary = entry.get("summary")
        if not summary:
            role = entry.get("role")
            content = entry.get("content")
            if role and content:
                summary = f"{role}: {content}"
            else:
                summary = json.dumps(entry, ensure_ascii=False)
        timestamp = (
            entry.get("timestamp")
            or entry.get("time")
            or entry.get("date")
            or "unknown"
        )
        normalized.append({"timestamp": timestamp, "summary": summary})
    return normalized


def update_memory_summary(memory_data, session_summary):
    history = normalize_history_entries(memory_data.get("history", []))
    history.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": session_summary,
        }
    )

    if len(history) > 10:
        history = history[-10:]  # Keep only last 10 summaries

    # Update condensed long-term memory
    full_context = "\n".join([h["summary"] for h in history])
    memory_data["summary"] = full_context
    memory_data["history"] = history
    return memory_data


# ==============================
# Session log management
# ==============================
def append_session_log(session_summary):
    sessions = load_json("sessions.json", [])
    if not isinstance(sessions, list):
        sessions = []

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": session_summary,
    }
    sessions.append(entry)
    save_json("sessions.json", sessions)


# ==============================
# Profile management
# ==============================
DEFAULT_PROFILE = {
    "name": "Unknown",
    "emotional_themes": [],
    "growth_goals": [],
    "preferred_tone": "gentle and curious",
    "progress_notes": [],
}


def normalize_progress_notes(progress_notes):
    normalized = []
    for note in progress_notes or []:
        if isinstance(note, dict):
            normalized.append(
                {
                    "date": note.get("date", "unknown"),
                    "note": note.get("note", ""),
                }
            )
        elif isinstance(note, str):
            normalized.append({"date": "unknown", "note": note})
    return normalized


def update_profile_with_summary(session_summary):
    profile = load_json("profile.json", DEFAULT_PROFILE.copy())
    if not isinstance(profile, dict):
        profile = DEFAULT_PROFILE.copy()

    profile.setdefault("name", DEFAULT_PROFILE["name"])
    profile.setdefault("emotional_themes", [])
    profile.setdefault("growth_goals", [])
    profile.setdefault("preferred_tone", DEFAULT_PROFILE["preferred_tone"])
    profile.setdefault("progress_notes", [])

    profile["progress_notes"] = normalize_progress_notes(profile.get("progress_notes", []))

    summary_payload = None
    if isinstance(session_summary, str):
        try:
            summary_payload = json.loads(session_summary)
        except (json.JSONDecodeError, TypeError):
            summary_payload = None

    if isinstance(summary_payload, dict):
        if "name" in summary_payload and isinstance(summary_payload["name"], str):
            profile["name"] = summary_payload["name"]
        if "preferred_tone" in summary_payload and isinstance(summary_payload["preferred_tone"], str):
            profile["preferred_tone"] = summary_payload["preferred_tone"]
        if "emotional_themes" in summary_payload and isinstance(summary_payload["emotional_themes"], list):
            profile["emotional_themes"] = summary_payload["emotional_themes"]
        if "growth_goals" in summary_payload and isinstance(summary_payload["growth_goals"], list):
            profile["growth_goals"] = summary_payload["growth_goals"]
        if "progress_notes" in summary_payload and isinstance(summary_payload["progress_notes"], list):
            profile["progress_notes"] = normalize_progress_notes(summary_payload["progress_notes"])
    else:
        profile["progress_notes"].append(
            {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "note": session_summary,
            }
        )

    save_json("profile.json", profile)


# ==============================
# Main chat loop
# ==============================
def chat_loop():
    memory_data = load_json("memory.json", {"summary": "", "history": []})
    persona = load_persona()

    system_prompt = f"{persona}\n\nUser background summary:\n{memory_data.get('summary', '')}"
    messages = [{"role": "system", "content": system_prompt}]

    print("e-cue 🌿: Hey, how are you feeling?")

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("e-cue 🌿: Before you go, let me summarize what we discussed...")
            session_summary = summarize_session(MODEL, messages, persona)
            print(f"\nSession summary:\n{session_summary}\n")

            memory_data = update_memory_summary(memory_data, session_summary)
            save_json("memory.json", memory_data)
            append_session_log(session_summary)
            update_profile_with_summary(session_summary)
            print("✅ Memory updated. See you next time.")
            break

        messages.append({"role": "user", "content": user_input})

        spinner = Spinner()
        spinner.start()
        try:
            response = ollama.chat(model=MODEL, messages=messages)
            spinner.stop()
        except Exception as e:
            spinner.stop()
            print(f"\n[error] {e}")
            continue

        ai_message = response["message"]["content"].strip()
        print(f"\ne-cue 🌿: {ai_message}")
        messages.append({"role": "assistant", "content": ai_message})


if __name__ == "__main__":
    chat_loop()
