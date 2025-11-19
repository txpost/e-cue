# e-cue

A minimal, AI-powered journaling application that uses local LLMs (via Ollama) to guide your writing sessions with customizable personas.

## Features

- 🤖 **AI-Powered Journaling**: Interactive journaling sessions powered by local LLMs through Ollama
- 🎭 **Customizable Personas**: Switch between different persona files to change the AI's coaching style
- 📝 **Session Tracking**: Automatically saves journal entries with timestamps, word counts, and full conversation history
- 🎨 **Beautiful CLI**: Color-coded interface with loading spinners for a smooth terminal experience
- 📊 **Word Count Tracking**: Real-time word count tracking for each session
- 💾 **JSON Storage**: All journal entries saved in a structured JSON format

## Prerequisites

- [Node.js](https://nodejs.org/) (v20 or higher recommended)
- [Ollama](https://ollama.ai/) installed and running locally
- The `llama3:latest` model pulled in Ollama (or modify the model in `e-cue.ts`)

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

2. Install dependencies:
   ```bash
   npm install
   ```
   
   Or using the Makefile:
   ```bash
   make install
   ```

## Usage

### Basic Usage

Start a journaling session with the default persona:
```bash
npm run dev
```

Or using the Makefile:
```bash
make dev
```

### Using Different Personas

Specify a custom persona file:
```bash
npm run dev -- --persona persona_0002_strategic-collaborator.txt
```

### During a Session

- Type your thoughts and press Enter to get an AI response
- Type `save` to save the session and exit
- Type `exit` or `quit` to end without saving
- Word counts are displayed after each entry

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
├── e-cue.ts              # Main application file
├── journal.json          # Saved journal entries (auto-generated)
├── persona.txt           # Default persona file
├── persona_*.txt        # Additional persona files
├── package.json          # Node.js dependencies
├── tsconfig.json         # TypeScript configuration
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
npm run dev -- --persona my-custom-persona.txt
```

## Journal Format

Journal entries are saved in `journal.json` with the following structure:

```json
{
  "entries": [
    {
      "timestamp": "2025-11-19 14:14:38",
      "persona_file": "persona.txt",
      "word_count": 1160,
      "exchanges": [
        {
          "user": "Your journal entry...",
          "e-cue": "AI response..."
        }
      ]
    }
  ]
}
```

## Development

### Building

Compile TypeScript:
```bash
npm run build
```

### Running

Run directly with ts-node:
```bash
npm run dev
```

## Configuration

To use a different Ollama model, edit the `MODEL` constant in `e-cue.ts`:

```typescript
const MODEL = "llama3:latest";  // Change to your preferred model
```

## Requirements

- **Node.js**: v20+
- **TypeScript**: v5.3+
- **Ollama**: Latest version with `llama3:latest` model

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

