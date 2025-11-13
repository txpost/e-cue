import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


DATA_DIR = Path(__file__).resolve().parent
EMOTIONS_PATH = DATA_DIR / "emotions.json"
STATE_PATH = DATA_DIR / "practice_state.json"

DEFAULT_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
FOUR_HOURS = timedelta(hours=4)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def from_iso(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return utc_now()


@dataclass(frozen=True)
class EmotionCard:
    emotion: str
    definition: str
    quadrant: str


def load_emotion_cards() -> List[EmotionCard]:
    if not EMOTIONS_PATH.exists():
        raise FileNotFoundError(f"Could not locate {EMOTIONS_PATH}")

    with EMOTIONS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    cards: List[EmotionCard] = []
    seen_emotions = set()

    for entry in data:
        if not isinstance(entry, dict):
            continue

        emotion = str(entry.get("emotion", "")).strip()
        definition = str(entry.get("definition", "")).strip()
        quadrant = str(entry.get("quadrant", "")).strip().lower() or "unknown"

        if not emotion or not definition:
            continue

        key = emotion.lower()
        if key in seen_emotions:
            continue

        seen_emotions.add(key)
        cards.append(EmotionCard(emotion=emotion, definition=definition, quadrant=quadrant))

    if not cards:
        raise ValueError("No valid emotions were loaded from emotions.json")

    return cards


def build_definition_lookup(cards: List[EmotionCard]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for card in cards:
        if card.definition not in lookup:
            lookup[card.definition] = card.emotion
    return lookup


def load_state() -> Dict[str, Dict[str, Dict[str, object]]]:
    state: Dict[str, Dict[str, Dict[str, object]]] = {"cards": {}}
    if STATE_PATH.exists():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict) and isinstance(loaded.get("cards"), dict):
                state["cards"] = loaded["cards"]
        except (json.JSONDecodeError, OSError):
            pass
    return state


def save_state(state: Dict[str, Dict[str, Dict[str, object]]]) -> None:
    snapshot = {"cards": state.get("cards", {})}
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)


class PracticeSession:
    def __init__(self, cards: List[EmotionCard], state: Dict[str, Dict[str, Dict[str, object]]]):
        self.cards = cards
        self.state = state
        self.card_index: Dict[str, EmotionCard] = {card.emotion.lower(): card for card in cards}
        self.new_cards = [card for card in cards if card.emotion.lower() not in self.state["cards"]]
        random.shuffle(self.new_cards)

    def next_card(self) -> Optional[EmotionCard]:
        now = utc_now()
        due: List[EmotionCard] = []
        upcoming: List[EmotionCard] = []

        for key, meta in self.state["cards"].items():
            card = self.card_index.get(key)
            if not card:
                continue

            next_due_raw = meta.get("next_due")
            if isinstance(next_due_raw, str):
                next_due = from_iso(next_due_raw)
            else:
                next_due = now

            if next_due <= now:
                due.append(card)
            else:
                upcoming.append(card)

        if due:
            due.sort(
                key=lambda card: from_iso(
                    str(self.state["cards"][card.emotion.lower()].get("next_due", to_iso(now)))
                )
            )
            return due[0]

        if self.new_cards:
            return self.new_cards.pop()

        if upcoming:
            upcoming.sort(
                key=lambda card: from_iso(
                    str(self.state["cards"][card.emotion.lower()].get("next_due", to_iso(now)))
                )
            )
            return upcoming[0]

        if self.cards:
            return random.choice(self.cards)

        return None

    def update_progress(self, card: EmotionCard, correct: bool) -> None:
        now = utc_now()
        key = card.emotion.lower()
        meta = self.state["cards"].setdefault(
            key,
            {
                "emotion": card.emotion,
                "definition": card.definition,
                "quadrant": card.quadrant,
                "streak": 0,
                "interval": 0,
                "ease": DEFAULT_EASE,
            },
        )

        streak = int(meta.get("streak", 0))
        interval = int(meta.get("interval", 0))
        ease = float(meta.get("ease", DEFAULT_EASE))

        if correct:
            streak += 1
            if streak == 1:
                interval = 1
            elif streak == 2:
                interval = 3
            else:
                interval = max(1, round(interval * ease))
            ease = min(MAX_EASE, ease + 0.1)
            next_due = now + timedelta(days=interval)
        else:
            streak = 0
            interval = 0
            ease = max(MIN_EASE, ease - 0.3)
            next_due = now + FOUR_HOURS

        meta.update(
            {
                "streak": streak,
                "interval": interval,
                "ease": round(ease, 2),
                "last_result": "correct" if correct else "incorrect",
                "last_reviewed": to_iso(now),
                "next_due": to_iso(next_due),
            }
        )

    def remaining_new(self) -> int:
        return len(self.new_cards)

    def due_count(self) -> int:
        now = utc_now()
        count = 0
        for meta in self.state["cards"].values():
            next_due_raw = meta.get("next_due")
            if not isinstance(next_due_raw, str):
                continue
            if from_iso(next_due_raw) <= now:
                count += 1
        return count


def format_timedelta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "due now"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts) if parts else "due soon"


def main() -> int:
    cards = load_emotion_cards()
    definition_lookup = build_definition_lookup(cards)
    state = load_state()
    session = PracticeSession(cards, state)

    print("Emotion practice started. Type 'quit' to exit.")
    print(f"Loaded {len(cards)} cards. {session.remaining_new()} new cards remain.\n")

    stats = {"total": 0, "correct": 0}

    while True:
        card = session.next_card()
        if not card:
            print("No cards available for review. Exiting.")
            break

        print("=" * 60)
        print(f"Definition: {card.definition}")
        try:
            user_answer = input("Emotion (or 'quit'): ").strip()
        except EOFError:
            print("\nNo input detected. Exiting practice.")
            break

        if not user_answer:
            print("Please enter an emotion (or type 'quit' to exit).")
            continue

        if user_answer.lower() in {"quit", "exit"}:
            print("Exiting practice...")
            break

        correct = user_answer.strip().lower() == card.emotion.lower()
        stats["total"] += 1

        if correct:
            stats["correct"] += 1
            print("✅ Correct!")
        else:
            expected = card.emotion
            print(f"❌ Incorrect. The emotion is '{expected}'.")
            if user_answer.lower() != expected.lower():
                alt = definition_lookup.get(card.definition)
                if alt and alt.lower() != expected.lower():
                    print(f"(Accepted alternative: {alt})")

        session.update_progress(card, correct)
        save_state(state)

        updated_meta = state["cards"].get(card.emotion.lower())
        if updated_meta and isinstance(updated_meta.get("next_due"), str):
            next_due = from_iso(updated_meta["next_due"])
            wait = next_due - utc_now()
            if wait.total_seconds() > 0:
                print(f"Next review for this card in ~{format_timedelta(wait)}.")

        print(
            f"Progress: {stats['correct']}/{stats['total']} correct | "
            f"{session.due_count()} due | {session.remaining_new()} new remaining"
        )

    save_state(state)
    print("Practice session complete.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPractice interrupted.")
        sys.exit(0)

