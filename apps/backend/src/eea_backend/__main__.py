"""Run the API with safe local defaults and desktop-runtime overrides."""

import os

import uvicorn


def main() -> None:
    """Start the backend on loopback."""

    host = os.environ.get("EEA_RUNTIME_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1"}:
        raise RuntimeError("EEA runtime backend must bind to loopback")
    port = int(os.environ.get("EEA_RUNTIME_PORT", "8000"))
    if not 0 <= port <= 65535:
        raise RuntimeError("EEA runtime backend port is invalid")
    uvicorn.run("eea_backend.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
