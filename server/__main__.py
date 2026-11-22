"""Start the Configure server:  .venv/bin/python -m server   then open http://127.0.0.1:8765 (Configure tab)."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.app:app", host="127.0.0.1", port=8765)
