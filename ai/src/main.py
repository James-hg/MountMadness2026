import os
from dotenv import load_dotenv
from google import genai

def main():
    load_dotenv()  # loads ai/.env when run from ai/

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY. Put it in ai/.env")

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model="models/gemini-2.5-pro",
        contents="Say hello in one short sentence."
    )
    print(resp.text)

if __name__ == "__main__":
    main()
