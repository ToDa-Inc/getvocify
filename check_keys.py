import os
from dotenv import load_dotenv
from pathlib import Path

# Load from root
load_dotenv(Path("/Users/danizal/getvocify/.env"))

for key in sorted(os.environ.keys()):
    if "KEY" in key or "API" in key or "SECRET" in key:
        print(f"{key}: {'FOUND' if os.environ[key] else 'EMPTY'}")
