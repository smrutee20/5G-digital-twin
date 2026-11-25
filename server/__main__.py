"""Start the Configure server:  .venv/bin/python -m server   then open http://127.0.0.1:8765 (Configure tab).

TWIN_HOST / TWIN_PORT choose the address (default 127.0.0.1:8765, this computer only); the Docker image sets
TWIN_HOST=0.0.0.0 so that "docker run -p 8765:8765 ..." can reach it.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.app:app", host=os.environ.get("TWIN_HOST", "127.0.0.1"),
                port=int(os.environ.get("TWIN_PORT", "8765")))
