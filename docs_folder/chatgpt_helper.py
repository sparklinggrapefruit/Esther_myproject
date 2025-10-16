import os
from openai import OpenAI  # pip install openai --upgrade
from keys import open_ai_api_key  # you must enter your OpenAI API key in a file called keys.py

client = OpenAI(
    api_key=open_ai_api_key
)

prompt = (
    "Could you do this math for me? 1+2+3+4+5+6+7+8+9+10+11+12+13+14+15+16+17+18+19+20"
)   

response = client.responses.create(
    model="gpt-4.1",   
    input=prompt,
    temperature=0,  # do not be creative!
    text={"format": {"type": "text"}}, # defaults to markdown unless specified otherwise in prompt!
)

result = response.output_text
print(result)