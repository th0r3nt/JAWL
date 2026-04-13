import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
