import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

DATA_DIR = Path(__file__).resolve().parent
CARDS_PATH = DATA_DIR / "cards.json"
STATE_PATH = DATA_DIR / "learn_state.json"

DEFAULT_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
FOUR_HOURS = timedelta(hours=4)

SUPPORTED_VARIANTS = {"definition", "multiple-choice", "true-false"}
QUIT_WORDS = {"quit", "exit", "q"}


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


def slugify(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class CardOption:
    text: str
    value: Union[str, int, bool]


@dataclass(frozen=True)
class Card:
    card_id: str
    variant: str
    prompt: str
    answer: Union[str, int, bool]
    options: Sequence[CardOption]
    image: Optional[str]
    source_text: Optional[str]
    source_url: Optional[str]
    tags: Sequence[str]


def build_card_id(
    variant: str, prompt: str, back: object, explicit_id: Optional[object] = None
) -> str:
    if explicit_id is not None:
        identifier = str(explicit_id).strip()
        if identifier:
            return identifier
    return f"{variant}:{slugify(prompt)}:{repr(back).lower()}"


def load_cards() -> List[Card]:
    if not CARDS_PATH.exists():
        raise FileNotFoundError(f"Could not locate {CARDS_PATH}")

    with CARDS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    cards: List[Card] = []

    if not isinstance(data, list):
        raise ValueError("cards.json must contain a list of cards")

    for entry in data:
        if not isinstance(entry, dict):
            continue

        raw_variant = str(entry.get("variant", "")).strip().lower()
        if raw_variant not in SUPPORTED_VARIANTS:
            continue

        front = entry.get("front") or {}
        prompt = str(front.get("prompt", "")).strip()
        if not prompt:
            continue

        image = front.get("image")
        options_raw = front.get("options")

        back = entry.get("back")

        source = entry.get("source") or {}
        source_text = source.get("text")
        source_url = source.get("url")
        tags = entry.get("tags") or []
        if isinstance(tags, list):
            tags = [str(tag) for tag in tags]
        else:
            tags = [str(tags)]

        card_id = build_card_id(raw_variant, prompt, back, entry.get("id"))

        options: List[CardOption] = []
        if raw_variant in {"multiple-choice", "true-false"}:
            if not isinstance(options_raw, list) or not options_raw:
                raise ValueError(f"Card '{prompt}' requires non-empty options list.")
            for opt in options_raw:
                if not isinstance(opt, dict):
                    continue
                text = str(opt.get("text", "")).strip()
                if not text:
                    continue
                value = opt.get("value")
                options.append(CardOption(text=text, value=value))
            if not options:
                raise ValueError(f"Card '{prompt}' produced no valid options.")

        if raw_variant == "true-false":
            if not isinstance(back, bool):
                raise ValueError(f"Card '{prompt}' must have boolean back value.")
        elif raw_variant == "multiple-choice":
            if back is None:
                raise ValueError(f"Card '{prompt}' must define a correct answer on back.")
        elif raw_variant == "definition":
            if not isinstance(back, str) or not back.strip():
                raise ValueError(f"Card '{prompt}' must have a non-empty string back value.")

        answers = [opt.value for opt in options] if options else []
        if answers and back not in answers:
            # allow matching by index or text, but warn by continuing
            pass

        cards.append(
            Card(
                card_id=card_id,
                variant=raw_variant,
                prompt=prompt,
                answer=back,
                options=tuple(options),
                image=image if isinstance(image, str) else None,
                source_text=str(source_text).strip() if source_text else None,
                source_url=str(source_url).strip() if source_url else None,
                tags=tuple(tags),
            )
        )

    if not cards:
        raise ValueError("No valid cards were loaded from cards.json")

    return cards


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


class CardSession:
    def __init__(self, cards: List[Card], state: Dict[str, Dict[str, Dict[str, object]]]):
        self.cards = cards
        self.state = state
        self.card_index: Dict[str, Card] = {card.card_id: card for card in cards}
        self.new_cards = [card for card in cards if card.card_id not in self.state["cards"]]
        random.shuffle(self.new_cards)

    def next_card(self) -> Optional[Card]:
        now = utc_now()
        due: List[Card] = []
        upcoming: List[Card] = []

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
                    str(self.state["cards"][card.card_id].get("next_due", to_iso(now)))
                )
            )
            return due[0]

        if self.new_cards:
            return self.new_cards.pop()

        if upcoming:
            upcoming.sort(
                key=lambda card: from_iso(
                    str(self.state["cards"][card.card_id].get("next_due", to_iso(now)))
                )
            )
            return upcoming[0]

        if self.cards:
            return random.choice(self.cards)

        return None

    def update_progress(self, card: Card, correct: bool) -> None:
        now = utc_now()
        key = card.card_id
        meta = self.state["cards"].setdefault(
            key,
            {
                "card_id": card.card_id,
                "variant": card.variant,
                "prompt": card.prompt,
                "answer": card.answer,
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


def describe_correct_answer(card: Card) -> str:
    if card.variant == "definition":
        return str(card.answer)
    for option in card.options:
        if option.value == card.answer:
            return option.text
    return str(card.answer)


def parse_multiple_choice_input(
    card: Card, user_input: str
) -> Optional[Tuple[Optional[CardOption], Union[str, int, bool, None]]]:
    normalized = user_input.strip().lower()
    if not normalized:
        return None

    # Accept numeric indices (1-based)
    if normalized.isdigit():
        idx = int(normalized)
        if 1 <= idx <= len(card.options):
            option = card.options[idx - 1]
            return option, option.value

    # Accept shorthand for true/false
    if card.variant == "true-false":
        if normalized in {"t", "true"}:
            for option in card.options:
                if isinstance(option.value, bool) and option.value is True:
                    return option, True
            return None
        if normalized in {"f", "false"}:
            for option in card.options:
                if isinstance(option.value, bool) and option.value is False:
                    return option, False
            return None

    for option in card.options:
        if normalized == option.text.lower():
            return option, option.value
        if isinstance(option.value, str) and normalized == option.value.lower():
            return option, option.value
        if not isinstance(option.value, str) and normalized == str(option.value).lower():
            return option, option.value

    return None


def prompt_card(card: Card) -> Optional[bool]:
    print("\n" + "-" * 60)
    print(card.prompt)
    if card.image:
        print(f"[image: {card.image}]")

    if card.variant in {"multiple-choice", "true-false"} and card.options:
        for idx, option in enumerate(card.options, start=1):
            print(f"{idx}. {option.text}")

    while True:
        try:
            user_answer = input("> ").strip()
        except EOFError:
            print("\nNo input detected. Exiting learn mode.")
            return None

        if not user_answer:
            print("Please enter a response (or type 'quit' to exit).")
            continue

        if user_answer.lower() in QUIT_WORDS:
            print("Exiting learn mode...")
            return None

        if card.variant == "definition":
            correct = user_answer.strip().lower() == str(card.answer).strip().lower()
            return correct

        if card.variant in {"multiple-choice", "true-false"}:
            parsed = parse_multiple_choice_input(card, user_answer)
            if not parsed:
                print("Input not recognized. Please choose one of the listed options.")
                continue
            _, selection = parsed
            correct = selection == card.answer
            return correct

        print("Unsupported card variant encountered.")
        return False


def display_result(card: Card, correct: bool) -> None:
    if correct:
        print("✅ Correct!")
    else:
        expected = describe_correct_answer(card)
        print(f"❌ Incorrect. Correct answer: {expected}")

    if card.source_text:
        if card.source_url:
            print(f"Source: {card.source_text} ({card.source_url})")
        else:
            print(f"Source: {card.source_text}")
    if card.tags:
        print(f"Tags: {', '.join(card.tags)}")


def main() -> int:
    cards = load_cards()
    state = load_state()
    session = CardSession(cards, state)

    print("Learn mode started. Type 'quit' to exit.")
    print(f"Loaded {len(cards)} cards. {session.remaining_new()} new cards remain.\n")

    stats = {"total": 0, "correct": 0}

    while True:
        card = session.next_card()
        if not card:
            print("No cards available for review. Exiting.")
            break

        result = prompt_card(card)
        if result is None:
            break

        stats["total"] += 1
        if result:
            stats["correct"] += 1

        display_result(card, result)

        session.update_progress(card, result)
        save_state(state)

        updated_meta = state["cards"].get(card.card_id)
        if updated_meta and isinstance(updated_meta.get("next_due"), str):
            next_due = from_iso(updated_meta["next_due"])
            wait = next_due - utc_now()
            print(f"Next review for this card in ~{format_timedelta(wait)}.")

        print(
            f"Progress: {stats['correct']}/{stats['total']} correct | "
            f"{session.due_count()} due | {session.remaining_new()} new remaining"
        )

    save_state(state)
    print("Learn session complete.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nLearn session interrupted.")
        sys.exit(0)


