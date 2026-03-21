import asyncio
from .server import main

def run():
    asyncio.run(main())

__all__ = ["main", "run"]

if __name__ == "__main__":
    run()
