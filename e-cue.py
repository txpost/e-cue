#!/usr/bin/env python3
"""e-cue: A journaling application with AI coaching and semantic search."""

import json
import os
import sys
import re
import subprocess
import platform
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, TypedDict
from datetime import datetime, timedelta
import asyncio
import threading
import time
import ollama
import chromadb
import click

# Constants
MODEL = "llama3:latest"
ENTRIES_DIR = "entries"
COLLECTION_NAME = "journal_entries"
CHROMA_DB_PATH = "chroma_db"

# Initialize ChromaDB client in persistent mode
chroma_client: Optional[Any] = None  # type: ignore
chroma_collection: Optional[chromadb.Collection] = None

# ANSI color codes
COLOR_RESET = "\x1b[0m"
COLOR_USER = "\x1b[96m"  # Bright cyan
COLOR_E_CUE = "\x1b[92m"  # Bright green


# ==============================
# Type Definitions
# ==============================
class Analysis(TypedDict):
    sentiment: str
    emotions: List[str]
    tone: str
    topics: List[str]
    summary: str
    keywords: List[str]


class EntryFile(TypedDict):
    id: str
    timestamp: str
    content: str
    word_count: int
    exchanges: List[Dict[str, str]]
    analysis: Optional[Analysis]


class JournalMetadata(TypedDict):
    current_daily_streak: int
    all_time_daily_streak: int
    total_word_count: int
    average_word_count_per_day: float
    average_word_count_per_session: float
    total_entries: int
    last_entry_date: Optional[str]


class SearchResult(TypedDict):
    entryId: str
    score: float
    content: str
    timestamp: str


# ==============================
# ChromaDB Functions
# ==============================
def get_chroma_collection() -> chromadb.Collection:
    """Get or create ChromaDB collection using persistent client."""
    global chroma_client, chroma_collection

    if chroma_client is None:
        # Use persistent client mode - stores data locally in chroma_db directory
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    if chroma_collection is None:
        assert chroma_client is not None
        chroma_collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    assert chroma_collection is not None
    return chroma_collection


# ==============================
# Spinner animation
# ==============================
class Spinner:
    spinner_cycle = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking"):
        self.message = message
        self.current_index = 0
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def _get_next_char(self) -> str:
        char = self.spinner_cycle[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.spinner_cycle)
        return char

    def _spin(self) -> None:
        while self.running:
            sys.stdout.write(f"\r{self.message} {self._get_next_char()}")
            sys.stdout.flush()
            time.sleep(0.1)

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        clear_length = len(self.message) + 4
        sys.stdout.write("\r" + " " * clear_length + "\r")
        sys.stdout.flush()


# ==============================
# File handling
# ==============================
def load_json(filename: str, default_value: Any) -> Any:
    """Load JSON from file or return default."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_value


def save_json(filename: str, data: Any) -> None:
    """Save data as JSON to file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def load_persona(persona_file: str) -> str:
    """Load persona file content."""
    try:
        with open(persona_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"[error] Persona file '{persona_file}' not found.")
        sys.exit(1)


def ensure_entries_dir() -> None:
    """Ensure entries directory exists."""
    Path(ENTRIES_DIR).mkdir(parents=True, exist_ok=True)


def save_entry(entry: EntryFile) -> None:
    """Save journal entry to file."""
    ensure_entries_dir()
    # Format timestamp for filename: replace colons and spaces, keep ISO format
    timestamp_part = entry['timestamp'].replace(':', '-').replace('.', '-').replace('T', '-').replace('Z', '').rstrip('-')
    filename = f"{timestamp_part}-{entry['id']}.json"
    filepath = Path(ENTRIES_DIR) / filename
    save_json(str(filepath), entry)


def load_all_entries() -> List[EntryFile]:
    """Load all journal entries."""
    ensure_entries_dir()
    entries: List[EntryFile] = []

    try:
        entries_dir = Path(ENTRIES_DIR)
        json_files = [f for f in entries_dir.iterdir() if f.suffix == '.json']

        for file in json_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    entry = json.load(f)
                    entries.append(entry)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[error] Failed to load entry file {file}: {e}")

    except Exception:
        # Directory might not exist yet, return empty array
        return []

    # Sort by timestamp (newest first)
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return entries


def load_entry_by_id(entry_id: str) -> Optional[EntryFile]:
    """Load a specific entry by ID."""
    ensure_entries_dir()
    try:
        entries_dir = Path(ENTRIES_DIR)
        json_files = [f for f in entries_dir.iterdir() if f.suffix == '.json' and entry_id in f.name]

        if not json_files:
            return None

        with open(json_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def update_entry(entry: EntryFile) -> None:
    """Update an existing entry."""
    ensure_entries_dir()
    timestamp_part = entry['timestamp'].replace(':', '-').replace('.', '-').replace('T', '-').replace('Z', '').rstrip('-')
    filename = f"{timestamp_part}-{entry['id']}.json"
    filepath = Path(ENTRIES_DIR) / filename
    save_json(str(filepath), entry)


# ==============================
# Metadata calculations
# ==============================
def load_metadata() -> JournalMetadata:
    """Load journal metadata."""
    default_metadata: JournalMetadata = {
        'current_daily_streak': 0,
        'all_time_daily_streak': 0,
        'total_word_count': 0,
        'average_word_count_per_day': 0.0,
        'average_word_count_per_session': 0.0,
        'total_entries': 0,
        'last_entry_date': None,
    }

    metadata = load_json("metadata.json", default_metadata)

    # Calculate metadata from all entries
    entries = load_all_entries()
    if entries:
        return calculate_metadata(entries)

    return metadata


def save_metadata(metadata: JournalMetadata) -> None:
    """Save journal metadata."""
    save_json("metadata.json", metadata)


def calculate_metadata(entries: List[EntryFile]) -> JournalMetadata:
    """Calculate journal metadata from entries."""
    if not entries:
        return {
            'current_daily_streak': 0,
            'all_time_daily_streak': 0,
            'total_word_count': 0,
            'average_word_count_per_day': 0.0,
            'average_word_count_per_session': 0.0,
            'total_entries': 0,
            'last_entry_date': None,
        }

    MIN_WORDS_FOR_STREAK = 750

    # Calculate total word count and track dates with qualifying sessions (750+ words)
    total_word_count = 0
    dates = set()
    qualifying_dates = set()  # Dates with at least one 750+ word session
    date_word_counts: Dict[str, int] = {}  # Track total words per day
    last_entry_date: Optional[str] = None

    for entry in entries:
        word_count = entry.get('word_count', 0)
        total_word_count += word_count

        # Extract date from timestamp (ISO format: "2025-11-18T13:58:26Z")
        date_str = entry['timestamp'].split('T')[0]
        dates.add(date_str)

        # Track total words per day
        date_word_counts[date_str] = date_word_counts.get(date_str, 0) + word_count

        # Track dates with at least one qualifying session (750+ words)
        if word_count >= MIN_WORDS_FOR_STREAK:
            qualifying_dates.add(date_str)

        # Track most recent entry date
        if not last_entry_date or entry['timestamp'] > last_entry_date:
            last_entry_date = date_str

    # Calculate averages
    average_word_count_per_session = total_word_count / len(entries)
    unique_days_count = len(dates)
    average_word_count_per_day = total_word_count / unique_days_count if unique_days_count > 0 else 0

    # Sort qualifying dates for streak calculation
    sorted_qualifying_dates = sorted(qualifying_dates)

    # Calculate current daily streak (consecutive days ending today with 750+ word session)
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    current_streak = 0
    # Only count streak if there's a qualifying entry today
    if today_str in qualifying_dates:
        # Check backwards from today
        check_date = today
        streak_date = today_str

        while streak_date in qualifying_dates:
            current_streak += 1
            check_date = check_date - timedelta(days=1)
            streak_date = check_date.strftime('%Y-%m-%d')

    # Calculate all-time daily streak (longest consecutive period with 750+ word sessions)
    all_time_streak = 0
    if sorted_qualifying_dates:
        max_streak = 1
        current_consecutive = 1

        for i in range(1, len(sorted_qualifying_dates)):
            prev_date = datetime.fromisoformat(sorted_qualifying_dates[i - 1])
            curr_date = datetime.fromisoformat(sorted_qualifying_dates[i])
            diff_days = (curr_date - prev_date).days

            if diff_days == 1:
                # Consecutive day
                current_consecutive += 1
                max_streak = max(max_streak, current_consecutive)
            else:
                # Gap found, reset counter
                current_consecutive = 1

        all_time_streak = max_streak

    return {
        'current_daily_streak': current_streak,
        'all_time_daily_streak': all_time_streak,
        'total_word_count': total_word_count,
        'average_word_count_per_day': round(average_word_count_per_day * 100) / 100,
        'average_word_count_per_session': round(average_word_count_per_session * 100) / 100,
        'total_entries': len(entries),
        'last_entry_date': last_entry_date,
    }


def count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.strip().split()) if text.strip() else 0


# ==============================
# Ollama Integration
# ==============================
async def generate_analysis(content: str) -> Analysis:
    """Generate analysis for journal entry."""
    analysis_prompt = f"""Analyze the following journal entry and provide a structured analysis in JSON format with the following fields:
- sentiment: one word describing overall sentiment (e.g., "positive", "negative", "mixed", "neutral")
- emotions: array of 2-5 emotion words (e.g., ["happy", "anxious", "hopeful"])
- tone: one word describing the writing tone (e.g., "reflective", "energetic", "melancholic", "optimistic")
- topics: array of 3-7 main topics or themes (e.g., ["work", "relationships", "health"])
- summary: a brief 1-2 sentence summary of the entry
- keywords: array of 5-10 important keywords or phrases

Journal entry:
{content}

Respond with ONLY valid JSON in this exact format:
{{
  "sentiment": "...",
  "emotions": [...],
  "tone": "...",
  "topics": [...],
  "summary": "...",
  "keywords": [...]
}}"""

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        response_text = response['message']['content'].strip()
        # Try to extract JSON from the response (in case there's extra text)
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            analysis = json.loads(json_match.group(0))
            return {
                'sentiment': analysis.get('sentiment', 'neutral'),
                'emotions': analysis.get('emotions', []) if isinstance(analysis.get('emotions'), list) else [],
                'tone': analysis.get('tone', 'neutral'),
                'topics': analysis.get('topics', []) if isinstance(analysis.get('topics'), list) else [],
                'summary': analysis.get('summary', ''),
                'keywords': analysis.get('keywords', []) if isinstance(analysis.get('keywords'), list) else [],
            }
        raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"[error] Failed to generate analysis: {e}")
        # Return default analysis on error
        return {
            'sentiment': 'neutral',
            'emotions': [],
            'tone': 'neutral',
            'topics': [],
            'summary': '',
            'keywords': [],
        }


async def generate_embedding(content: str) -> List[float]:
    """Generate embedding for content."""
    try:
        response = ollama.embeddings(model=MODEL, prompt=content)
        return response['embedding']
    except Exception as e:
        print(f"[error] Failed to generate embedding: {e}")
        return []


# ==============================
# Enrichment Functions
# ==============================
async def enrich_entry(entry_id: str) -> None:
    """Enrich a single entry with analysis and embedding."""
    entry = load_entry_by_id(entry_id)
    if not entry:
        print(f"[error] Entry with ID {entry_id} not found.")
        return

    # Check if already enriched and indexed
    collection = get_chroma_collection()
    try:
        existing = collection.get(ids=[entry_id])
        if existing and existing.get('ids') and entry.get('analysis'):
            print(f"Entry {entry_id} already has analysis and is indexed.")
            return
    except Exception:
        # Collection might be empty, continue with enrichment
        pass

    print(f"Generating analysis and embedding for entry {entry_id}...")
    spinner = Spinner("Processing")
    spinner.start()

    try:
        # Generate analysis if missing
        if not entry.get('analysis'):
            entry['analysis'] = await generate_analysis(entry['content'])

        # Generate embedding
        embedding = await generate_embedding(entry['content'])

        if not embedding:
            raise ValueError("Failed to generate embedding")

        # Store embedding in ChromaDB
        analysis = entry.get('analysis')
        collection.upsert(
            ids=[entry_id],
            embeddings=[embedding],
            documents=[entry['content']],
            metadatas=[{
                'timestamp': entry['timestamp'],
                'word_count': str(entry['word_count']),
                'sentiment': analysis['sentiment'] if analysis else '',
                'tone': analysis['tone'] if analysis else '',
            }],
        )

        # Update entry file (without embedding)
        update_entry(entry)
        spinner.stop()
        print(f"{COLOR_E_CUE}✓ Successfully enriched and indexed entry {entry_id}.{COLOR_RESET}")
    except Exception as e:
        spinner.stop()
        print(f"[error] Failed to enrich entry: {e}")


async def enrich_all_entries() -> None:
    """Enrich all entries that need it."""
    entries = load_all_entries()
    collection = get_chroma_collection()

    # Get all indexed entry IDs
    indexed_ids = set()
    try:
        all_indexed = collection.get()
        indexed_ids = set(all_indexed.get('ids', []))
    except Exception:
        # Collection might be empty, continue
        pass

    # Filter entries that need enrichment (missing analysis or not indexed)
    entries_to_enrich = [
        e for e in entries
        if not e.get('analysis') or e['id'] not in indexed_ids
    ]

    if not entries_to_enrich:
        print("All entries are already enriched and indexed.")
        return

    print(f"Found {len(entries_to_enrich)} entries to enrich and index.")

    for entry in entries_to_enrich:
        await enrich_entry(entry['id'])

    print(f"{COLOR_E_CUE}✓ Finished enriching and indexing all entries.{COLOR_RESET}")


# ==============================
# Search Functions
# ==============================
async def search_entries(query: str, limit: int = 5) -> List[SearchResult]:
    """Search journal entries semantically."""
    try:
        collection = get_chroma_collection()

        # Generate embedding for query
        query_embedding = await generate_embedding(query)
        if not query_embedding:
            raise ValueError("Failed to generate query embedding")

        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )

        # Map results to SearchResult format
        search_results: List[SearchResult] = []
        ids_list = results.get('ids')
        if ids_list and len(ids_list) > 0 and ids_list[0]:
            distances_list = results.get('distances', [])
            documents_list = results.get('documents', [])
            metadatas_list = results.get('metadatas', [])

            for i in range(len(ids_list[0])):
                entry_id = ids_list[0][i]
                if not isinstance(entry_id, str):
                    continue

                distance = None
                if distances_list and len(distances_list) > 0 and i < len(distances_list[0]):
                    dist_val = distances_list[0][i]
                    if isinstance(dist_val, (int, float)):
                        distance = float(dist_val)

                # Convert distance to similarity score (1 - distance, assuming cosine distance)
                score = max(0.0, 1.0 - distance) if distance is not None else 0.0

                content = ""
                if documents_list and len(documents_list) > 0 and i < len(documents_list[0]):
                    doc_val = documents_list[0][i]
                    if isinstance(doc_val, str):
                        content = doc_val

                timestamp = ""
                if metadatas_list and len(metadatas_list) > 0 and i < len(metadatas_list[0]):
                    metadata = metadatas_list[0][i]
                    if isinstance(metadata, dict):
                        timestamp_val = metadata.get('timestamp', '')
                        if isinstance(timestamp_val, str):
                            timestamp = timestamp_val

                search_results.append({
                    'entryId': entry_id,
                    'score': score,
                    'content': content,
                    'timestamp': timestamp,
                })

        return search_results
    except Exception as e:
        print(f"[error] Failed to search entries: {e}")
        return []


async def search_entries_command(query: str, limit: Optional[int] = None) -> None:
    """Command handler for search."""
    print(f'Searching for: "{query}"\n')
    spinner = Spinner("Searching")
    spinner.start()

    try:
        results = await search_entries(query, limit or 5)
        spinner.stop()

        if not results:
            print("No matching entries found.")
            return

        print(f"Found {len(results)} matching entries:\n")
        for i, result in enumerate(results, 1):
            entry = load_entry_by_id(result['entryId'])
            date_str = "Unknown date"
            if result['timestamp']:
                try:
                    date_obj = datetime.fromisoformat(result['timestamp'].replace('Z', '+00:00'))
                    date_str = date_obj.strftime('%Y-%m-%d')
                except Exception:
                    pass

            print(f"{COLOR_E_CUE}{i}. Entry {result['entryId']}{COLOR_RESET}")
            print(f"   Date: {date_str}")
            print(f"   Similarity: {result['score'] * 100:.1f}%")
            if entry and entry.get('analysis'):
                analysis = entry['analysis']
                if analysis and analysis.get('summary'):
                    print(f"   Summary: {analysis['summary']}")
            content_preview = result['content'][:150] + ('...' if len(result['content']) > 150 else '')
            print(f"   Content: {content_preview}")
            print()
    except Exception as e:
        spinner.stop()
        print(f"[error] Search failed: {e}")


# ==============================
# Main journaling loop
# ==============================
async def journal_loop(persona_file: str) -> None:
    """Main interactive journaling loop."""
    # Clear the terminal screen
    clear_command = 'cls' if platform.system() == 'Windows' else 'clear'
    subprocess.run(clear_command, shell=True, check=False)

    persona = load_persona(persona_file)

    system_prompt = persona
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    print(f"Journaling with persona: {persona_file}")
    print("Type 'save' to save and exit, or 'exit'/'quit' to end without saving.\n")

    cumulative_words = 0
    session_start_time = datetime.now()
    session_exchanges: List[Dict[str, str]] = []

    while True:
        try:
            user_input = input(f"{COLOR_USER}You:{COLOR_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEnding journal session (not saved).")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("\nEnding journal session (not saved).")
            break

        if user_input.lower() == "save":
            # Save session as a single entry
            if session_exchanges:
                # Concatenate all user inputs into content field
                content = ' '.join(ex['user'] for ex in session_exchanges)

                entry_id = str(uuid.uuid4())
                timestamp = session_start_time.isoformat() + 'Z'

                entry: EntryFile = {
                    'id': entry_id,
                    'timestamp': timestamp,
                    'content': content,
                    'word_count': cumulative_words,
                    'exchanges': session_exchanges,
                    'analysis': None,
                }

                save_entry(entry)

                # Calculate and update metadata
                all_entries = load_all_entries()
                metadata = calculate_metadata(all_entries)
                save_metadata(metadata)

                print(f"\n{COLOR_E_CUE}✓ Saved session with {len(session_exchanges)} exchanges to entry {entry_id}.{COLOR_RESET}\n")
            else:
                print(f"\n{COLOR_E_CUE}No entries to save.{COLOR_RESET}\n")
            print("Ending journal session.")
            break

        # Show cumulative word count after input
        word_count = count_words(user_input)
        cumulative_words += word_count
        print(f"{COLOR_USER}[{word_count} words this entry, {cumulative_words} words total]{COLOR_RESET}")

        messages.append({"role": "user", "content": user_input})

        spinner = Spinner()
        spinner.start()
        try:
            response = ollama.chat(
                model=MODEL,
                messages=messages,
            )

            spinner.stop()

            ai_message = response['message']['content'].strip()
            print(f"\n{COLOR_E_CUE}e-cue:{COLOR_RESET} {ai_message}\n")
            messages.append({"role": "e-cue", "content": ai_message})

            # Store exchange in session (not saved yet)
            exchange = {
                'user': user_input,
                'assistant': ai_message,
            }
            session_exchanges.append(exchange)
        except Exception as e:
            spinner.stop()
            print(f"\n[error] {e}")
            continue


# ==============================
# CLI Commands
# ==============================
@click.group()
@click.option('--persona', default='persona.txt', help='Path to persona file')
@click.pass_context
def cli(ctx: click.Context, persona: str) -> None:
    """Journal with different personas."""
    ctx.ensure_object(dict)
    ctx.obj['persona'] = persona


@cli.command()
@click.argument('entry_id')
def enrich(entry_id: str) -> None:
    """Generate analysis and embedding for an entry, and index it in ChromaDB."""
    asyncio.run(enrich_entry(entry_id))


@cli.command(name='enrich-all')
def enrich_all() -> None:
    """Generate analysis and embedding for all entries that need it, and index them in ChromaDB."""
    asyncio.run(enrich_all_entries())


@cli.command()
@click.argument('query')
@click.option('-n', '--limit', default=5, type=int, help='Maximum number of results')
def search(query: str, limit: int) -> None:
    """Search journal entries semantically using ChromaDB."""
    asyncio.run(search_entries_command(query, limit))


def main() -> None:
    """Main entry point."""
    # Check if running without a command (default to journal loop)
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] not in ('enrich', 'enrich-all', 'search', '--help', '-h')):
        # Parse --persona option manually for journal loop
        persona_file = "persona.txt"
        if '--persona' in sys.argv:
            idx = sys.argv.index('--persona')
            if idx + 1 < len(sys.argv):
                persona_file = sys.argv[idx + 1]

        asyncio.run(journal_loop(persona_file))
    else:
        cli()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

