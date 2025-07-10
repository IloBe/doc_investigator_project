# check_google_models.py file for testing via CLI

import google.generativeai as genai
import os
import getpass

# Use the same API key loading logic
api_key = os.environ.get('GOOGLE_API_KEY')
if not api_key:
    api_key = getpass.getpass('Enter your Google Gemini API Key: ')
genai.configure(api_key=api_key)

# check existing model names
print("Available models that support 'generateContent':")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(f"- {m.name}")
    