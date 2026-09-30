import asyncio
import os
from google.antigravity import Agent, LiteRTAgentConfig

MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")

async def main():
    print(f"Using local LiteRT model: {MODEL_PATH}")
    print("Initializing LiteRT runtime on Apple Silicon Metal GPU...")
    print("(Note: On the first run, LiteRT compiles GPU shaders for Metal; this can take 1-2 minutes).")
    
    config = LiteRTAgentConfig(model_path=MODEL_PATH).lightweight()
    
    async with Agent(config) as agent:
        print("\nSending test prompt...")
        response = await agent.chat("Say hello, introduce yourself, and state that you are running locally via LiteRT.")
        async for token in response:
            print(token, end="", flush=True)
        print("\n")

if __name__ == "__main__":
    asyncio.run(main())
