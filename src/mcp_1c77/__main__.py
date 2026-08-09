import os
import sys

if "--stdio" in sys.argv:
    from .server import mcp
    mcp.run()
else:
    import uvicorn
    from .web import app

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

