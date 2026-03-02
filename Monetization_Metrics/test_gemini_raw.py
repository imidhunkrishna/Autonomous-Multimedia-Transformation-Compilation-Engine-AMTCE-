import os
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

def test_raw_gemini():
    print("Testing Raw Gemini Connectivity...")
    # Load from the correct place
    load_dotenv("Credentials/.env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ No API Key!")
        return

    genai.configure(api_key=key)
    
    # Try gemini-2.5-flash
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    print(f"Calling Gemini with {model.model_name}...")
    try:
        # Simple text prompt
        response = model.generate_content("Hello, reply with 'READY'")
        if response:
            print(f"Text Response: {response.text}")
        else:
            print("❌ Empty response from Gemini.")
        
        # Simple image prompt
        img = Image.new('RGB', (100, 100), color = 'blue')
        response = model.generate_content(["What color is this?", img])
        print(f"Image Response: {response.text}")
        
    except Exception as e:
        print(f"❌ Gemini Error: {e}")

if __name__ == "__main__":
    test_raw_gemini()
