import os, requests

# Replace this with your actual API key
API_KEY=os.getenv("TOGETHERAI_API_KEY") 
TOGETHERAI_MODEL = os.getenv("TOGETHERAI_MODEL")
url = "https://api.together.ai/v1/completions"
headers = {"Authorization": f"Bearer {API_KEY}"}
data = {
    "model": TOGETHERAI_MODEL,  # Use  model specified
    "prompt": "Describe a cyberpunk city at night.",
    "max_tokens": 200
}

response = requests.post(url, headers=headers, json=data)

# Print the AI's response
print(response.json())
