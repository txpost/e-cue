# e-cue

A minimal, AI-powered journaling application that uses local LLMs (via Ollama) to guide your writing sessions with customizable personas.

## Features

- 🤖 **AI-Powered Journaling**: Interactive journaling sessions powered by local LLMs through Ollama
- 🎭 **Customizable Personas**: Switch between different persona files to change the AI's coaching style
- 📝 **Session Tracking**: Automatically saves journal entries with timestamps, word counts, and full conversation history
- 🎨 **Beautiful CLI**: Color-coded interface with loading spinners for a smooth terminal experience
- 📊 **Word Count Tracking**: Real-time word count tracking for each session
- 💾 **JSON Storage**: All journal entries saved in a structured JSON format
- 🔍 **Semantic Search**: Search journal entries using ChromaDB vector embeddings
- 📊 **Entry Analysis**: AI-powered analysis of journal entries (sentiment, emotions, topics, etc.)

## Prerequisites

- [Python](https://www.python.org/) (v3.8 or higher recommended)
- [Ollama](https://ollama.ai/) installed and running locally
- The `llama3:latest` model pulled in Ollama (or modify the model in `e-cue.py`)
- ChromaDB (will be installed via pip and started locally, see setup below)

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

3. ChromaDB server will be started automatically when needed!

   The app will automatically start a ChromaDB server on `localhost:8000` when you use enrichment or search features. No manual setup required!

## Usage

### Basic Usage

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
python3 e-cue.py --persona persona_0002_strategic-collaborator.txt
```

Or with the Makefile:
```bash
make dev  # Then pass --persona as needed
```

### During a Session

- Type your thoughts and press Enter to get an AI response
- Type `save` to save the session and exit
- Type `exit` or `quit` to end without saving
- Word counts are displayed after each entry

### Enriching Entries

After creating journal entries, you can enrich them with AI analysis and embeddings:

Enrich a single entry:
```bash
make enrich ID=<entry-id>
```

Or directly:
```bash
python3 e-cue.py enrich <entry-id>
```

Enrich all entries:
```bash
make enrich-all
```

Or directly:
```bash
python3 e-cue.py enrich-all
```

### Searching Entries

Search journal entries semantically:
```bash
make search QUERY="your search query" LIMIT=5
```

Or directly:
```bash
python3 e-cue.py search "your search query" --limit 5
```

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
✓ Saved session with 3 exchanges to journal.
```

## Project Structure

```
e-cue/
├── e-cue.py              # Main application file
├── entries/              # Journal entry JSON files
├── vectorstore/          # ChromaDB data (created automatically)
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
  "timestamp": "2025-11-19T14:14:38Z",
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

## Configuration

To use a different Ollama model, edit the `MODEL` constant in `e-cue.py`:

```python
MODEL = "llama3:latest"  # Change to your preferred model
```

## Requirements

- **Python**: v3.8+
- **Ollama**: Latest version with `llama3:latest` model
- **ChromaDB**: Installed via pip, server started automatically when needed

## ChromaDB Setup

ChromaDB is used for storing embeddings and enabling semantic search. The app automatically starts a ChromaDB server when needed!

### Automatic Server Mode

When you run enrichment or search commands, the app will:
1. Check if a ChromaDB server is running on `localhost:8000`
2. If not, automatically start one using the `chroma` CLI
3. Connect to the server and perform the operation

The server runs in the background and will be reused for subsequent operations.

### Using a Remote ChromaDB Server (Optional)

If you want to use a remote ChromaDB server instead of the local one, set the `CHROMA_URL` environment variable:
```bash
CHROMA_URL=http://your-chroma-server:8000 python3 e-cue.py enrich-all
```

Or with the Makefile:
```bash
CHROMA_URL=http://your-chroma-server:8000 make enrich-all
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

