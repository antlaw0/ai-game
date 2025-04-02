import os, requests

# Replace this with your actual API key
API_KEY=os.getenv("REMOVED_SECRET") 

url = "https://api.together.ai/v1/completions"
headers = {"Authorization": f"Bearer {API_KEY}"}
data = {
    "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",  # Use Mixtral chat model
    "prompt": "Describe a cyberpunk city at night.",
    "max_tokens": 200
}

response = requests.post(url, headers=headers, json=data)

# Print the AI's response
print(response.json())
