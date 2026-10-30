from __future__ import annotations

from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from .security import validate_runtime_configuration


def main() -> None:
    validate_runtime_configuration()
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(config, "head")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, access_log=False)


if __name__ == "__main__":
    main()
