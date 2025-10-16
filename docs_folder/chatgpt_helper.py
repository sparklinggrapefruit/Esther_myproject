from openai import OpenAI
from keys import open_ai_api_key

client = OpenAI(api_key=open_ai_api_key)

prompt = "Add 1+2+...+20"

chat = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
)

print(chat.choices[0].message.content)

prompt1 = "write a haiku about an orange cat"
chat = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt1}],
    temperature=0,
)

print(chat.choices[0].message.content)

##Creating a safe file for keys.py

from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("open_ai_api_key")
##This part didn't work!!

