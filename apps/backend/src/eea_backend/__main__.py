"""Run the API with safe local defaults."""

import uvicorn


def main() -> None:
    """Start the backend on loopback."""

    uvicorn.run("eea_backend.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
