# e-cue

A minimal, AI-powered journaling application that uses local LLMs (via Ollama) to guide your writing sessions with customizable personas. Track your writing habits, analyze your entries, and search your journal semantically.

## Features

- 🤖 **AI-Powered Journaling**: Interactive journaling sessions powered by local LLMs through Ollama
- 🎭 **Customizable Personas**: Switch between different persona files to change the AI's coaching style
- 📝 **Session Tracking**: Automatically saves journal entries with timestamps, word counts, and full conversation history
- 🎨 **Beautiful CLI**: Color-coded interface with loading spinners for a smooth terminal experience
- 📊 **Word Count Tracking**: Real-time word count tracking for each session
- 💾 **JSON Storage**: All journal entries saved in a structured JSON format
- 🔍 **Semantic Search**: Search journal entries using ChromaDB vector embeddings
- 📊 **Entry Analysis**: AI-powered analysis of journal entries (sentiment, emotions, topics, summaries, keywords)
- 📈 **Writing Statistics**: Track daily streaks, word counts, and writing habits via metadata
- 🎯 **Enrichment System**: Add AI analysis and embeddings to entries for enhanced search capabilities

## Prerequisites

- [Python](https://www.python.org/) (v3.8 or higher recommended)
- [Ollama](https://ollama.ai/) installed and running locally
- The `llama3:latest` model pulled in Ollama (or modify the model in `e-cue.py`)

### Installing Ollama

1. Visit [ollama.ai](https://ollama.ai/) and install Ollama for your platform
2. Pull the required model:
   ```bash
   ollama pull llama3:latest
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd e-cue
   ```

2. Install dependencies using the Makefile (recommended):
   ```bash
   make install
   ```

   This will create a virtual environment and install all required packages.

   Or manually:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. ChromaDB uses persistent client mode - no server setup required!

   The app uses ChromaDB's persistent client mode, which stores data locally in the `chroma_db/` directory. No server process is needed - everything works automatically!

## Usage

### Starting a Journal Session

Start a journaling session with the default persona:
```bash
make dev
```

Or directly with Python:
```bash
python3 e-cue.py
```

If using a virtual environment:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python3 e-cue.py
```

### Using Different Personas

Specify a custom persona file:
```bash
python3 e-cue.py --persona persona_0000.txt
```

Or with the Makefile:
```bash
make dev  # Then pass --persona as needed
```

### During a Session

- Type your thoughts and press Enter to get an AI response
- Type `save` to save the session and exit
- Type `exit` or `quit` to end without saving
- Word counts are displayed after each entry (both per-entry and cumulative)

### Enriching Entries

After creating journal entries, you can enrich them with AI analysis and embeddings. Enrichment adds:
- Sentiment analysis
- Emotion detection
- Tone identification
- Topic extraction
- Summary generation
- Keyword extraction
- Vector embeddings for semantic search

**Enrich a single entry:**
```bash
make enrich ID=<entry-id>
```

Or directly:
```bash
python3 e-cue.py enrich <entry-id>
```

**Enrich all entries:**
```bash
make enrich-all
```

Or directly:
```bash
python3 e-cue.py enrich-all
```

### Searching Entries

Search journal entries semantically using vector embeddings:
```bash
make search QUERY="your search query" LIMIT=5
```

Or directly:
```bash
python3 e-cue.py search "your search query" --limit 5
```

Search results include:
- Entry ID and date
- Similarity score (percentage)
- Summary (if entry is enriched)
- Content preview

### Example Session

```
Journaling with persona: persona.txt
Type 'save' to save and exit, or 'exit'/'quit' to end without saving.

You: I've been thinking about starting a side project but keep putting it off
[15 words this entry, 15 words total]

e-cue: What's holding you back from starting? Is it fear, lack of time, or something else?

You: I think it's a combination of not knowing where to start and worrying it won't be good enough
[20 words this entry, 35 words total]

e-cue: What would "good enough" look like to you? Sometimes the first step is more important than perfection.

You: I guess good enough would be something I'm proud to share, even if it's not perfect. Maybe I should just start with a small prototype
[25 words this entry, 60 words total]

e-cue: That sounds like a solid approach. What would that first small prototype look like?

You: save
✓ Saved session with 3 exchanges to entry c826fae4-a441-4438-bd7b-f9a8ac817038.
```

## Project Structure

```
e-cue/
├── e-cue.py              # Main application file
├── entries/              # Journal entry JSON files
├── chroma_db/            # ChromaDB persistent storage (created automatically)
├── persona.txt           # Default persona file
├── persona_*.txt        # Additional persona files
├── requirements.txt      # Python dependencies
├── metadata.json         # Journal metadata (auto-generated)
└── Makefile              # Build shortcuts
```

## Creating Custom Personas

Persona files are simple text files that define how the AI should behave during journaling sessions. Create a new `.txt` file with instructions for the AI, for example:

```
You are a strategic thinking partner. Help me explore ideas deeply
by asking probing questions and challenging my assumptions.
```

Then use it with:
```bash
python3 e-cue.py --persona my-custom-persona.txt
```

## Journal Format

Journal entries are saved as individual JSON files in the `entries/` directory with the following structure:

```json
{
  "id": "uuid-here",
  "timestamp": "2025-11-21T14:06:35.964876Z",
  "content": "Full text of all user entries in this session",
  "word_count": 1160,
  "exchanges": [
    {
      "user": "Your journal entry...",
      "assistant": "AI response..."
    }
  ],
  "analysis": {
    "sentiment": "positive",
    "emotions": ["happy", "hopeful"],
    "tone": "reflective",
    "topics": ["work", "relationships"],
    "summary": "Brief summary...",
    "keywords": ["keyword1", "keyword2"]
  }
}
```

The `analysis` field is optional and only present after enrichment.

## Metadata and Statistics

The app automatically tracks writing statistics in `metadata.json`:

- **Current Daily Streak**: Consecutive days with at least one 750+ word session (ending today)
- **All-Time Daily Streak**: Longest consecutive period with 750+ word sessions
- **Total Word Count**: Sum of all words across all entries
- **Average Word Count Per Day**: Average words written per unique day
- **Average Word Count Per Session**: Average words per journal entry
- **Total Entries**: Number of journal entries
- **Last Entry Date**: Date of the most recent entry

Metadata is automatically updated when you save a journal session.

## Development

### Running

Run the application:
```bash
make dev
```

Or directly:
```bash
python3 e-cue.py
```

Make sure you have activated your virtual environment if you installed dependencies manually:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python3 e-cue.py
```

### Available Commands

- **Journal session** (default): `python3 e-cue.py [--persona <file>]`
- **Enrich entry**: `python3 e-cue.py enrich <entry-id>`
- **Enrich all**: `python3 e-cue.py enrich-all`
- **Search**: `python3 e-cue.py search "<query>" [--limit <n>]`

## Configuration

To use a different Ollama model, edit the `MODEL` constant in `e-cue.py`:

```python
MODEL = "llama3:latest"  # Change to your preferred model
```

Note: The same model is used for both chat and embeddings. Make sure your chosen model supports embeddings (most Ollama models do).

## Requirements

- **Python**: v3.8+
- **Ollama**: Latest version with `llama3:latest` model (or your preferred model)
- **ChromaDB**: Installed via pip, uses persistent client mode
- **Click**: For CLI argument parsing

## ChromaDB Setup

ChromaDB is used for storing embeddings and enabling semantic search. The app uses ChromaDB's persistent client mode, which means:

- **No server required**: Data is stored locally in the `chroma_db/` directory
- **Automatic setup**: The database directory is created automatically when first used
- **Persistent storage**: All embeddings and search data persist between application runs
- **Simple and fast**: No server startup delays or management overhead

The `chroma_db/` directory will be created automatically in your project root when you first use enrichment or search features. You can safely add it to `.gitignore` if you don't want to commit the database files.