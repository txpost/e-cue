import argparse
import json
import itertools
import os
import sys
import threading
import time
from datetime import datetime
import ollama


MODEL = "llama3:latest"

# ANSI color codes
COLOR_RESET = "\033[0m"
COLOR_USER = "\033[96m"  # Bright cyan
COLOR_E_CUE = "\033[92m"  # Bright green


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


def load_persona(persona_file):
    try:
        with open(persona_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"[error] Persona file '{persona_file}' not found.")
        sys.exit(1)


def load_journal():
    return load_json("journal.json", {"entries": []})


def append_to_journal(journal_data, persona_file, user_message, e_cue_message):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "persona_file": persona_file,
        "user": user_message,
        "e-cue": e_cue_message,
    }
    journal_data.setdefault("entries", []).append(entry)
    save_json("journal.json", journal_data)


# ==============================
# Main journaling loop
# ==============================
def journal_loop(persona_file):
    # Clear the terminal screen
    os.system('cls' if os.name == 'nt' else 'clear')
    
    persona = load_persona(persona_file)
    journal_data = load_journal()

    system_prompt = persona
    messages = [{"role": "system", "content": system_prompt}]

    print(f"Journaling with persona: {persona_file}")
    print("Type 'exit' or 'quit' to end the session.\n")

    while True:
        user_input = input(f"{COLOR_USER}You:{COLOR_RESET} ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("\nEnding journal session.")
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
        print(f"\n{COLOR_E_CUE}e-cue:{COLOR_RESET} {ai_message}\n")
        messages.append({"role": "e-cue", "content": ai_message})

        # Append to journal immediately
        append_to_journal(journal_data, persona_file, user_input, ai_message)


def main():
    parser = argparse.ArgumentParser(description="Journal with different personas")
    parser.add_argument(
        "--persona",
        type=str,
        default="persona.txt",
        help="Path to persona file (default: persona.txt)",
    )
    args = parser.parse_args()

    journal_loop(args.persona)


if __name__ == "__main__":
    main()

