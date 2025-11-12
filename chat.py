import json
import itertools
import re
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


DEFAULT_SESSION_PAYLOAD = {
    "summary_text": "",
    "mood_meter": "",
    "emotional_themes": [],
    "growth_goals": [],
    "progress_note": "",
    "preferred_tone": "",
}


def strip_code_fences(text):
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        inner = stripped[3:-3].strip()
        if inner.lower().startswith("json"):
            inner = inner.split("\n", 1)[1].strip() if "\n" in inner else inner[4:].strip()
        return inner
    return text


def ensure_session_payload(payload, fallback_text):
    data = DEFAULT_SESSION_PAYLOAD.copy()
    if isinstance(payload, dict):
        for key in data.keys():
            value = payload.get(key)
            if key in ("emotional_themes", "growth_goals") and isinstance(value, list):
                data[key] = [str(item) for item in value if isinstance(item, str)]
            elif isinstance(value, str):
                data[key] = value.strip()
    if not data["summary_text"]:
        data["summary_text"] = fallback_text
    if not data["progress_note"]:
        data["progress_note"] = fallback_text
    return data


def parse_json_with_recovery(text):
    stripped = text.strip()

    def add_candidate(container, candidate):
        candidate = candidate.strip()
        if candidate and candidate not in container:
            container.append(candidate)

    candidates = []
    add_candidate(candidates, stripped)

    no_trailing_commas = re.sub(r",\s*([}\]])", r"\1", stripped)
    add_candidate(candidates, no_trailing_commas)

    if stripped.startswith("{"):
        diff = stripped.count("{") - stripped.count("}")
        if diff > 0:
            add_candidate(candidates, stripped + "}" * diff)
            add_candidate(candidates, no_trailing_commas + "}" * diff)
    if stripped.startswith("["):
        diff = stripped.count("[") - stripped.count("]")
        if diff > 0:
            add_candidate(candidates, stripped + "]" * diff)
            add_candidate(candidates, no_trailing_commas + "]" * diff)

    last_exc = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise json.JSONDecodeError("Unable to parse JSON response", stripped, 0)


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
            cleaned = strip_code_fences(content)
            try:
                payload = parse_json_with_recovery(cleaned)
                fallback = fallback_summary(messages, label="session")
                return ensure_session_payload(payload, fallback)
            except json.JSONDecodeError:
                sample = cleaned.strip()
                print(f"[warn] summarize_session expected JSON, received (len={len(sample)}): {sample}")
                pass
    except Exception as exc:
        print(f"[warn] summarize_session fallback due to error: {exc}")

    fallback = fallback_summary(messages, label="session")
    return ensure_session_payload({}, fallback)


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

    summary_payload = {}
    if isinstance(session_summary, dict):
        summary_payload = session_summary
    elif isinstance(session_summary, str):
        try:
            summary_payload = json.loads(session_summary)
        except (json.JSONDecodeError, TypeError):
            summary_payload = {}

    if isinstance(summary_payload, dict):
        name = summary_payload.get("name")
        if isinstance(name, str) and name.strip():
            profile["name"] = name.strip()

        tone = summary_payload.get("preferred_tone")
        if isinstance(tone, str) and tone.strip():
            profile["preferred_tone"] = tone.strip()

        emotional_themes = summary_payload.get("emotional_themes")
        if isinstance(emotional_themes, list):
            merged = profile.get("emotional_themes", [])
            for theme in emotional_themes:
                if isinstance(theme, str):
                    cleaned = theme.strip()
                    if cleaned and cleaned not in merged:
                        merged.append(cleaned)
            profile["emotional_themes"] = merged

        growth_goals = summary_payload.get("growth_goals")
        if isinstance(growth_goals, list):
            merged = profile.get("growth_goals", [])
            for goal in growth_goals:
                if isinstance(goal, str):
                    cleaned = goal.strip()
                    if cleaned and cleaned not in merged:
                        merged.append(cleaned)
            profile["growth_goals"] = merged

        progress_note = summary_payload.get("progress_note")
        note_text = (
            progress_note.strip()
            if isinstance(progress_note, str) and progress_note.strip()
            else summary_payload.get("summary_text", "")
        )
    else:
        note_text = session_summary if isinstance(session_summary, str) else ""

    if note_text:
        profile["progress_notes"].append(
            {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "note": note_text,
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
            summary_text = session_summary.get("summary_text", "")
            print(f"\nSession summary:\n{summary_text}\n")

            memory_data = update_memory_summary(memory_data, summary_text)
            save_json("memory.json", memory_data)
            append_session_log(summary_text)
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
