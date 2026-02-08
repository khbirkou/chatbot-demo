import os
from openai import OpenAI

client = OpenAI(
    base_url="https://ai-orderbooking-01.openai.azure.com/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

resp = client.responses.create(
    model="gpt-4.1-mini",
    input="What is the capital of Germany?",
)

print(resp.output_text)
