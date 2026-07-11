import asyncio
from llm.deepseek_client import stream_chat_completion


async def main():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello and nothing else."},
    ]
    reply = await stream_chat_completion(messages, json_mode=False, temperature=0.2)
    print(f"reply: {reply}")


if __name__ == "__main__":
    asyncio.run(main())
