import requests

# Replace this with your actual API key
API_KEY = "a9be60516b6738c9399c86af3491d820e21d48020f48263694288429cb2c9d81"
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
