import os
from fastapi import FastAPI

from routes import router
from Debug import dbg, log_active_flags
from startup import start_tunnel, print_endpoints, print_model_route

app = FastAPI()
app.include_router(router)


if __name__ in {"__main__", "__mp_main__"}:
    import uvicorn  # type: ignore

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "7860"))
    dbg("Launching server")
    log_active_flags()

    public_url = start_tunnel(port)
    print_endpoints(port, public_url)
    print_model_route()

    uvicorn.run(app, host=host, port=port)
