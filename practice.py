import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence


DATA_DIR = Path(__file__).resolve().parent
EMOTIONS_PATH = DATA_DIR / "emotions.json"
FEELINGS_WHEEL_PATH = DATA_DIR / "feelings_wheel.json"
STATE_PATH = DATA_DIR / "practice_state.json"

DEFAULT_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
FOUR_HOURS = timedelta(hours=4)
LEGACY_VARIANT_ID = "definition-input"


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


@dataclass(frozen=True)
class FeelingsWheelEntry:
    primary: str
    secondary: str
    tertiary: str


@dataclass(frozen=True)
class PracticeCard:
    card_id: str
    variant_id: str
    payload: Dict[str, Any]


@dataclass
class PracticeResult:
    correct: bool
    feedback: List[str]
    retry: bool = False


@dataclass
class PracticeQuestion:
    prompt_lines: List[str]
    evaluate: Callable[[str], PracticeResult]
    choices: Optional[List[str]] = None


class PracticeVariant(Protocol):
    variant_id: str
    label: str

    def build_cards(self) -> Sequence[PracticeCard]:
        ...

    def prepare_question(self, card: PracticeCard, rng: random.Random) -> PracticeQuestion:
        ...


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


def build_definition_lookup(cards: Sequence[EmotionCard]) -> Dict[str, List[str]]:
    lookup: Dict[str, List[str]] = {}
    for card in cards:
        lookup.setdefault(card.definition, []).append(card.emotion)
    return lookup


def load_feelings_wheel() -> List[FeelingsWheelEntry]:
    if not FEELINGS_WHEEL_PATH.exists():
        raise FileNotFoundError(f"Could not locate {FEELINGS_WHEEL_PATH}")

    with FEELINGS_WHEEL_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    entries: List[FeelingsWheelEntry] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        primary = str(entry.get("primary", "")).strip()
        secondary = str(entry.get("secondary", "")).strip()
        tertiary = str(entry.get("tertiary", "")).strip()
        if not primary or not secondary or not tertiary:
            continue
        entries.append(FeelingsWheelEntry(primary=primary, secondary=secondary, tertiary=tertiary))

    if not entries:
        raise ValueError("No valid entries were loaded from feelings_wheel.json")

    return entries


def sanitize_progress(meta: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = to_iso(utc_now())
    progress: Dict[str, Any] = {}

    def as_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return DEFAULT_EASE

    progress["streak"] = max(0, as_int(meta.get("streak", 0)))
    progress["interval"] = max(0, as_int(meta.get("interval", 0)))
    ease = as_float(meta.get("ease", DEFAULT_EASE))
    progress["ease"] = round(min(MAX_EASE, max(MIN_EASE, ease)), 2)

    last_result = meta.get("last_result")
    if isinstance(last_result, str) and last_result:
        progress["last_result"] = last_result

    last_reviewed = meta.get("last_reviewed")
    if isinstance(last_reviewed, str) and last_reviewed:
        progress["last_reviewed"] = last_reviewed

    next_due = meta.get("next_due")
    if isinstance(next_due, str) and next_due.strip():
        progress["next_due"] = next_due
    else:
        progress["next_due"] = now_iso

    return progress


def load_state() -> Dict[str, Dict[str, Dict[str, Any]]]:
    state: Dict[str, Dict[str, Dict[str, Any]]] = {"cards": {}}
    if not STATE_PATH.exists():
        return state

    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return state

    if not isinstance(loaded, dict):
        return state

    raw_cards = loaded.get("cards")
    if not isinstance(raw_cards, dict):
        return state

    for key, meta in raw_cards.items():
        if not isinstance(meta, dict):
            continue
        new_key = key if ":" in key else f"{LEGACY_VARIANT_ID}:{key}"
        state["cards"][new_key] = sanitize_progress(meta)

    return state


def save_state(state: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    snapshot = {"cards": state.get("cards", {})}
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)


class DefinitionInputVariant:
    variant_id = LEGACY_VARIANT_ID
    label = "Definition → Emotion"

    def __init__(self, cards: Sequence[EmotionCard], definition_lookup: Dict[str, List[str]]):
        self._cards = list(cards)
        self._definition_lookup = definition_lookup

    def build_cards(self) -> Sequence[PracticeCard]:
        practice_cards: List[PracticeCard] = []
        for card in self._cards:
            practice_cards.append(
                PracticeCard(
                    card_id=f"{self.variant_id}:{card.emotion.lower()}",
                    variant_id=self.variant_id,
                    payload={"emotion": card},
                )
            )
        return practice_cards

    def prepare_question(self, card: PracticeCard, rng: random.Random) -> PracticeQuestion:  # noqa: ARG002
        emotion_card: EmotionCard = card.payload["emotion"]
        expected = emotion_card.emotion
        definition = emotion_card.definition
        alternatives = [
            option
            for option in self._definition_lookup.get(definition, [])
            if option.lower() != expected.lower()
        ]

        def evaluate(response: str) -> PracticeResult:
            cleaned = response.strip().lower()
            correct = cleaned == expected.lower()
            if correct:
                return PracticeResult(correct=True, feedback=["✅ Correct!"])

            feedback = [f"❌ Incorrect. The emotion is '{expected}'."]
            if alternatives:
                feedback.append(f"(Accepted alternative: {alternatives[0]})")
            return PracticeResult(correct=False, feedback=feedback)

        return PracticeQuestion(prompt_lines=[definition], evaluate=evaluate)


class DefinitionMultipleChoiceVariant:
    variant_id = "definition-multiple-choice"
    label = "Definition → Multiple Choice"

    def __init__(self, cards: Sequence[EmotionCard]):
        self._cards = list(cards)

    def build_cards(self) -> Sequence[PracticeCard]:
        practice_cards: List[PracticeCard] = []
        for card in self._cards:
            practice_cards.append(
                PracticeCard(
                    card_id=f"{self.variant_id}:{card.emotion.lower()}",
                    variant_id=self.variant_id,
                    payload={"emotion": card},
                )
            )
        return practice_cards

    def prepare_question(self, card: PracticeCard, rng: random.Random) -> PracticeQuestion:
        emotion_card: EmotionCard = card.payload["emotion"]
        correct = emotion_card.emotion
        distractors = self._choose_distractors(correct, rng)
        options = [correct, *distractors]
        rng.shuffle(options)

        def evaluate(response: str) -> PracticeResult:
            selection = self._normalise_selection(response, options)
            if selection is None:
                return PracticeResult(
                    correct=False,
                    feedback=["Please choose one of the listed options (number or text)."],
                    retry=True,
                )

            if selection.lower() == correct.lower():
                return PracticeResult(correct=True, feedback=["✅ Correct!"])

            return PracticeResult(
                correct=False,
                feedback=[f"❌ Incorrect. The correct emotion is '{correct}'."],
            )

        prompt = [
            emotion_card.definition,
            "Select the matching emotion:",
        ]
        return PracticeQuestion(prompt_lines=prompt, evaluate=evaluate, choices=options)

    def _choose_distractors(self, answer: str, rng: random.Random) -> List[str]:
        pool = [card for card in self._cards if card.emotion.lower() != answer.lower()]
        rng.shuffle(pool)
        distractors: List[str] = []
        seen = set()
        for card in pool:
            key = card.emotion.lower()
            if key in seen:
                continue
            seen.add(key)
            distractors.append(card.emotion)
            if len(distractors) == 2:
                break
        if len(distractors) < 2:
            raise ValueError("Not enough distinct emotions to build multiple-choice options.")
        return distractors

    @staticmethod
    def _normalise_selection(response: str, options: Sequence[str]) -> Optional[str]:
        cleaned = response.strip()
        if not cleaned:
            return None
        if cleaned.isdigit():
            index = int(cleaned)
            if 1 <= index <= len(options):
                return options[index - 1]
            return None
        lowered = cleaned.lower()
        for option in options:
            if option.lower() == lowered:
                return option
        return None


class FeelingsLayerVariant:
    variant_id = "feelings-layer"
    label = "Feelings Wheel Layer"

    def __init__(self, entries: Sequence[FeelingsWheelEntry]):
        self._entries = list(entries)
        self._cards = self._build_unique_cards()

    def _build_unique_cards(self) -> List[PracticeCard]:
        seen: Dict[tuple[str, str], PracticeCard] = {}
        for entry in self._entries:
            for layer, emotion in (
                ("primary", entry.primary),
                ("secondary", entry.secondary),
                ("tertiary", entry.tertiary),
            ):
                name = emotion.strip()
                if not name:
                    continue
                key = (name.lower(), layer)
                if key in seen:
                    continue
                payload = {
                    "emotion": name,
                    "layer": layer,
                    "path": (entry.primary, entry.secondary, entry.tertiary),
                }
                card_id = f"{self.variant_id}:{layer}:{name.lower()}"
                seen[key] = PracticeCard(card_id=card_id, variant_id=self.variant_id, payload=payload)
        return list(seen.values())

    def build_cards(self) -> Sequence[PracticeCard]:
        return self._cards

    def prepare_question(self, card: PracticeCard, rng: random.Random) -> PracticeQuestion:  # noqa: ARG002
        emotion = card.payload["emotion"]
        layer = card.payload["layer"]
        path = card.payload["path"]

        options = ["Primary", "Secondary", "Tertiary"]
        option_lookup = {option.lower(): option for option in options}
        alias_lookup = {"p": "Primary", "s": "Secondary", "t": "Tertiary"}

        def evaluate(response: str) -> PracticeResult:
            cleaned = response.strip().lower()
            selection: Optional[str] = None

            if cleaned in option_lookup:
                selection = option_lookup[cleaned]
            elif cleaned in alias_lookup:
                selection = alias_lookup[cleaned]
            elif cleaned.isdigit():
                index = int(cleaned)
                if 1 <= index <= len(options):
                    selection = options[index - 1]

            if selection is None:
                return PracticeResult(
                    correct=False,
                    feedback=[
                        "Please answer with primary, secondary, or tertiary (or 1-3 / p / s / t)."
                    ],
                    retry=True,
                )

            if selection.lower() == layer:
                return PracticeResult(correct=True, feedback=["✅ Correct!"])

            if layer == "primary":
                chain = path[0]
            elif layer == "secondary":
                chain = f"{path[0]} → {path[1]}"
            else:
                chain = f"{path[0]} → {path[1]} → {path[2]}"
            return PracticeResult(
                correct=False,
                feedback=[f"❌ Incorrect. '{emotion}' is a {layer.title()} emotion ({chain})."],
            )

        prompt = [
            f"Emotion: {emotion}",
            "Which layer does this emotion belong to?",
        ]
        return PracticeQuestion(prompt_lines=prompt, evaluate=evaluate, choices=options)


class PracticeSession:
    def __init__(
        self,
        variants: Sequence[PracticeVariant],
        state: Dict[str, Dict[str, Dict[str, Any]]],
        rng: Optional[random.Random] = None,
    ):
        self.variants: Dict[str, PracticeVariant] = {variant.variant_id: variant for variant in variants}
        self.cards: List[PracticeCard] = []
        seen_ids: set[str] = set()
        for variant in variants:
            for card in variant.build_cards():
                if card.card_id in seen_ids:
                    raise ValueError(f"Duplicate card identifier detected: {card.card_id}")
                self.cards.append(card)
                seen_ids.add(card.card_id)

        self.card_index: Dict[str, PracticeCard] = {card.card_id: card for card in self.cards}
        self.state = state
        self.rng = rng or random.Random()
        self._quit_requested = False

        new_cards = [card for card in self.cards if card.card_id not in self.state["cards"]]
        self._new_cards: List[PracticeCard] = new_cards
        self.rng.shuffle(self._new_cards)

    def next_card(self) -> Optional[PracticeCard]:
        now = utc_now()
        due: List[tuple[datetime, PracticeCard]] = []
        upcoming: List[tuple[datetime, PracticeCard]] = []

        for card_id, meta in self.state["cards"].items():
            card = self.card_index.get(card_id)
            if not card:
                continue

            next_due_raw = meta.get("next_due")
            next_due = from_iso(next_due_raw) if isinstance(next_due_raw, str) else now

            if next_due <= now:
                due.append((next_due, card))
            else:
                upcoming.append((next_due, card))

        if due:
            due.sort(key=lambda item: item[0])
            return due[0][1]

        if self._new_cards:
            return self._new_cards.pop()

        if upcoming:
            upcoming.sort(key=lambda item: item[0])
            return upcoming[0][1]

        if self.cards:
            return self.rng.choice(self.cards)

        return None

    def update_progress(self, card: PracticeCard, correct: bool) -> None:
        now = utc_now()
        meta = self.state["cards"].setdefault(
            card.card_id,
            {
                "streak": 0,
                "interval": 0,
                "ease": DEFAULT_EASE,
                "next_due": to_iso(now),
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
        return len(self._new_cards)

    def due_count(self) -> int:
        now = utc_now()
        count = 0
        for card_id, meta in self.state["cards"].items():
            if card_id not in self.card_index:
                continue
            next_due_raw = meta.get("next_due")
            if not isinstance(next_due_raw, str):
                continue
            if from_iso(next_due_raw) <= now:
                count += 1
        return count

    def ask_question(self, question: PracticeQuestion) -> Optional[bool]:
        while True:
            print(" " * 60)
            for line in question.prompt_lines:
                print(line)
            if question.choices:
                for idx, choice in enumerate(question.choices, start=1):
                    print(f"{idx}. {choice}")

            try:
                response = input("").strip()
            except EOFError:
                print("\nNo input detected. Exiting practice.")
                self._quit_requested = True
                return None

            if not response:
                print("Please enter a response (or type 'quit' to exit).")
                continue

            lowered = response.lower()
            if lowered in {"quit", "exit"}:
                print("Exiting practice...")
                self._quit_requested = True
                return None

            result = question.evaluate(response)
            for line in result.feedback:
                print(line)

            if result.retry:
                continue

            return result.correct

    def run(self) -> Dict[str, int]:
        stats = {"total": 0, "correct": 0}

        while not self._quit_requested:
            card = self.next_card()
            if not card:
                print("No cards available for review. Exiting.")
                break

            variant = self.variants[card.variant_id]
            question = variant.prepare_question(card, self.rng)
            outcome = self.ask_question(question)

            if outcome is None:
                break

            stats["total"] += 1
            if outcome:
                stats["correct"] += 1

            self.update_progress(card, outcome)
            save_state(self.state)

        return stats


def choose_variants(variants: Sequence[PracticeVariant]) -> List[PracticeVariant]:
    if not variants:
        return []

    print("Available practice variants:")
    for idx, variant in enumerate(variants, start=1):
        print(f"{idx}. {variant.label} ({variant.variant_id})")

    print("Select variants by number or id (comma-separated). Press Enter for all variants.")

    while True:
        try:
            selection = input("> ").strip()
        except EOFError:
            print("\nNo input detected. Using all variants.")
            return list(variants)

        if not selection:
            return list(variants)

        lowered = selection.lower()
        if lowered in {"quit", "exit"}:
            print("Exiting practice...")
            return []

        parts = [part.strip() for part in selection.split(",") if part.strip()]
        chosen: List[PracticeVariant] = []

        for part in parts:
            if part.isdigit():
                index = int(part)
                if 1 <= index <= len(variants):
                    variant = variants[index - 1]
                else:
                    print(f"Selection '{part}' is out of range.")
                    chosen = []
                    break
            else:
                variant = next(
                    (
                        item
                        for item in variants
                        if item.variant_id.lower() == part.lower() or item.label.lower() == part.lower()
                    ),
                    None,
                )
                if variant is None:
                    print(f"Unrecognised variant '{part}'.")
                    chosen = []
                    break

            if variant not in chosen:
                chosen.append(variant)

        if chosen:
            return chosen

        print("No valid variants selected. Try again or press Enter to use all variants.")


def main() -> int:
    emotion_cards = load_emotion_cards()
    definition_lookup = build_definition_lookup(emotion_cards)
    feelings_entries = load_feelings_wheel()

    variants: List[PracticeVariant] = [
        DefinitionInputVariant(emotion_cards, definition_lookup),
        DefinitionMultipleChoiceVariant(emotion_cards),
        FeelingsLayerVariant(feelings_entries),
    ]

    selected_variants = choose_variants(variants)
    if not selected_variants:
        print("No variants selected. Exiting.")
        return 0

    state = load_state()
    session = PracticeSession(selected_variants, state)

    print("Emotion practice started. Type 'quit' to exit.")
    print(f"Loaded {len(session.cards)} cards across {len(selected_variants)} variant(s).")
    print(f"{session.due_count()} due | {session.remaining_new()} new cards.\n")

    stats = session.run()
    save_state(state)

    print("Practice session complete.")
    if stats["total"]:
        print(f"Score: {stats['correct']}/{stats['total']} correct.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPractice interrupted.")
        sys.exit(0)
