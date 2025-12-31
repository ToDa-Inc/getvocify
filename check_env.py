import os
from pathlib import Path
from dotenv import load_dotenv

# Check root
root_env = Path("/Users/danizal/getvocify/.env")
backend_env = Path("/Users/danizal/getvocify/backend/.env")

print(f"Checking {root_env} exists: {root_env.exists()}")
print(f"Checking {backend_env} exists: {backend_env.exists()}")

if root_env.exists():
    print("Content of root .env keys:")
    load_dotenv(root_env)
    for key in ["DEEPGRAM_API_KEY", "SPEECHMATICS_API_KEY", "SPEECHNATICS_API_KEY", "OPENROUTER_API_KEY"]:
        val = os.getenv(key)
        print(f"  {key}: {'FOUND (' + val[:4] + '...)' if val else 'NOT FOUND'}")

if backend_env.exists():
    print("\nContent of backend .env keys:")
    load_dotenv(backend_env, override=True)
    for key in ["DEEPGRAM_API_KEY", "SPEECHMATICS_API_KEY", "OPENROUTER_API_KEY"]:
        val = os.getenv(key)
        print(f"  {key}: {'FOUND (' + val[:4] + '...)' if val else 'NOT FOUND'}")

