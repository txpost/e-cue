#!/usr/bin/env python3
"""FastAPI REST API for e-cue journaling application."""

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import ollama

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import e-cue module (handling hyphen in filename)
try:
    spec = importlib.util.spec_from_file_location("e_cue", Path(__file__).parent / "e-cue.py")
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load e-cue.py module")
    e_cue = importlib.util.module_from_spec(spec)
    sys.modules["e_cue"] = e_cue
    spec.loader.exec_module(e_cue)
except Exception as e:
    print(f"ERROR: Failed to import e-cue module: {e}")
    raise

# Import necessary functions and types from dynamically loaded module
try:
    load_all_entries = e_cue.load_all_entries
    load_entry_by_id = e_cue.load_entry_by_id
    save_entry = e_cue.save_entry
    update_entry = e_cue.update_entry
    enrich_entry = e_cue.enrich_entry
    enrich_all_entries = e_cue.enrich_all_entries
    search_entries = e_cue.search_entries
    format_entry_context = e_cue.format_entry_context
    load_metadata = e_cue.load_metadata
    calculate_metadata = e_cue.calculate_metadata
    save_metadata = e_cue.save_metadata
    count_words = e_cue.count_words
    load_persona = e_cue.load_persona
    EntryFile = e_cue.EntryFile
    JournalMetadata = e_cue.JournalMetadata
    SearchResult = e_cue.SearchResult
    Analysis = e_cue.Analysis
    MODEL = e_cue.MODEL
except AttributeError as e:
    print(f"ERROR: Failed to import functions from e-cue module: {e}")
    raise

app = FastAPI(title="e-cue API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================
# Pydantic Models
# ==============================

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "journal"  # "journal" or "insight"
    conversation_history: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    response: str
    mode: str
    word_count: Optional[int] = None
    conversation_history: List[ChatMessage]


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class SaveEntryRequest(BaseModel):
    content: str
    exchanges: List[Dict[str, str]]
    word_count: int


class EntryResponse(BaseModel):
    id: str
    timestamp: str
    content: str
    word_count: int
    exchanges: List[Dict[str, str]]
    analysis: Optional[Dict[str, Any]] = None


class MetadataResponse(BaseModel):
    current_daily_streak: int
    all_time_daily_streak: int
    total_word_count: int
    average_word_count_per_day: float
    average_word_count_per_session: float
    total_entries: int
    last_entry_date: Optional[str]


class SearchResultResponse(BaseModel):
    entryId: str
    score: float
    content: str
    timestamp: str


# ==============================
# Helper Functions
# ==============================

def load_mode_persona(mode: str) -> str:
    """Load the appropriate persona file based on mode."""
    if mode == "insight":
        return load_persona("persona_insight.txt")
    else:
        return load_persona("persona_journal.txt")


def build_messages_from_history(
    conversation_history: Optional[List[ChatMessage]], mode: str, context: str = ""
) -> List[Dict[str, str]]:
    """Build messages array for Ollama from conversation history."""
    messages: List[Dict[str, str]] = []
    
    # Load persona and set as system message
    persona_base = load_mode_persona(mode)
    
    if mode == "insight":
        if context:
            persona = persona_base.replace("<<<CHROMA_RETRIEVAL>>>", context)
        else:
            persona = persona_base.replace("<<<CHROMA_RETRIEVAL>>>\n", "").replace(
                "<<<CHROMA_RETRIEVAL>>>", ""
            ).strip()
    else:
        persona = persona_base
    
    messages.append({"role": "system", "content": persona})
    
    # Add conversation history if provided
    if conversation_history:
        for msg in conversation_history:
            # Skip system messages from history (we already have one)
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})
    
    return messages


# ==============================
# API Endpoints
# ==============================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "e-cue API is running"}


@app.get("/api/entries", response_model=List[EntryResponse])
async def get_entries():
    """Get all journal entries, sorted by timestamp (newest first)."""
    try:
        entries = load_all_entries()
        return entries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load entries: {str(e)}")


@app.get("/api/entries/{entry_id}", response_model=EntryResponse)
async def get_entry(entry_id: str):
    """Get a specific journal entry by ID."""
    entry = load_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.post("/api/entries", response_model=EntryResponse, status_code=201)
async def create_entry(request: SaveEntryRequest):
    """Create a new journal entry."""
    try:
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat() + "Z"
        
        entry: EntryFile = {
            "id": entry_id,
            "timestamp": timestamp,
            "content": request.content,
            "word_count": request.word_count,
            "exchanges": request.exchanges,
            "analysis": None,
        }
        
        save_entry(entry)
        
        # Update metadata
        all_entries = load_all_entries()
        metadata = calculate_metadata(all_entries)
        save_metadata(metadata)
        
        return entry
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create entry: {str(e)}")


@app.put("/api/entries/{entry_id}", response_model=EntryResponse)
async def update_entry_endpoint(entry_id: str, request: SaveEntryRequest):
    """Update an existing journal entry."""
    existing_entry = load_entry_by_id(entry_id)
    if not existing_entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    try:
        updated_entry: EntryFile = {
            "id": entry_id,
            "timestamp": existing_entry["timestamp"],  # Keep original timestamp
            "content": request.content,
            "word_count": request.word_count,
            "exchanges": request.exchanges,
            "analysis": existing_entry.get("analysis"),  # Preserve analysis if exists
        }
        
        update_entry(updated_entry)
        
        # Update metadata
        all_entries = load_all_entries()
        metadata = calculate_metadata(all_entries)
        save_metadata(metadata)
        
        return updated_entry
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update entry: {str(e)}")


@app.post("/api/search", response_model=List[SearchResultResponse])
async def search_endpoint(request: SearchRequest):
    """Search journal entries semantically using ChromaDB."""
    try:
        results = await search_entries(request.query, request.limit)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/api/metadata", response_model=MetadataResponse)
async def get_metadata():
    """Get journal metadata and statistics."""
    try:
        metadata = load_metadata()
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load metadata: {str(e)}")


@app.post("/api/entries/{entry_id}/enrich")
async def enrich_entry_endpoint(entry_id: str):
    """Enrich a single entry with AI analysis and embedding."""
    entry = load_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    try:
        await enrich_entry(entry_id)
        return {"status": "success", "message": f"Entry {entry_id} enriched successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enrich entry: {str(e)}")


@app.post("/api/entries/enrich-all")
async def enrich_all_entries_endpoint():
    """Enrich all entries that need enrichment."""
    try:
        await enrich_all_entries()
        return {"status": "success", "message": "All entries enriched successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enrich entries: {str(e)}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message in journal or insight mode and get AI response."""
    # Handle mode switching commands
    user_input = request.message.strip().lower()
    mode = request.mode
    
    if user_input == "insight":
        mode = "insight"
        return ChatResponse(
            response="Switched to insight mode. Responses will include context from your journal entries.",
            mode=mode,
            conversation_history=request.conversation_history or [],
        )
    
    if user_input == "journal":
        mode = "journal"
        return ChatResponse(
            response="Switched to journal mode. Regular journaling mode active.",
            mode=mode,
            conversation_history=request.conversation_history or [],
        )
    
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Build messages array
    context_text = ""
    
    # In insight mode, retrieve relevant entries for context
    if mode == "insight":
        try:
            relevant_entries = await search_entries(request.message, limit=5)
            if relevant_entries:
                context_text = format_entry_context(relevant_entries)
        except Exception as e:
            # Continue without context if search fails
            pass
    
    messages = build_messages_from_history(request.conversation_history, mode, context_text)
    
    # Add current user message
    messages.append({"role": "user", "content": request.message})
    
    # Get AI response
    try:
        response = ollama.chat(
            model=MODEL,
            messages=messages,
        )
        
        ai_message = response["message"]["content"].strip()
        
        # Build updated conversation history
        updated_history = request.conversation_history or []
        updated_history.append(ChatMessage(role="user", content=request.message))
        updated_history.append(ChatMessage(role="assistant", content=ai_message))
        
        # Calculate word count for journal mode
        word_count = None
        if mode == "journal":
            word_count = count_words(request.message)
        
        return ChatResponse(
            response=ai_message,
            mode=mode,
            word_count=word_count,
            conversation_history=updated_history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get AI response: {str(e)}")

