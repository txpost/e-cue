#!/usr/bin/env python3
"""Simple script to start ChromaDB server."""

import sys

if __name__ == "__main__":
    try:
        import uvicorn
        from chromadb.app import app
    except ImportError as e:
        print(f"[error] Missing required dependency: {e}")
        print("Please install dependencies: pip install uvicorn fastapi")
        sys.exit(1)
    
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    
    print(f"Starting ChromaDB server on {host}:{port}...")
    print("Press Ctrl+C to stop the server.\n")
    
    uvicorn.run(app, host=host, port=port)

