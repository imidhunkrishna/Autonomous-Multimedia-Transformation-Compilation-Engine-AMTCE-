import os
import sys
import json
import logging

# Add project root to path
sys.path.append(os.getcwd())

from Intelligence_Modules.monetization_brain import brain

# Enable logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

def test_fashion_scout():
    print("Testing Fashion Scout Integration...")
    
    # 1. Test Brain Analysis (Mocked Input)
    # We need a frame path to trigger fashion scout
    test_image = "assets/snapped_thumbs/test_frame.jpg"
    if not os.path.exists("assets/snapped_thumbs"):
        os.makedirs("assets/snapped_thumbs")
    
    # Create a dummy image if it doesn't exist
    if not os.path.exists(test_image):
        from PIL import Image
        img = Image.new('RGB', (100, 100), color = 'red')
        img.save(test_image)

    print("\nRunning Full Brain Analysis with Fashion Scout...")
    res = brain.analyze_content("Celebrity in elegant evening gown", 15.0, image_paths=[test_image])
    
    print(f"Approved: {res.get('approved')}")
    
    fashion = res.get('fashion_scout')
    if fashion:
        print("✅ Fashion Scout data found in brain response!")
        print(f"Vibe: {fashion.get('vibe')}")
        
        ctas = fashion.get('imaginative_ctas', {})
        print("\nImaginative CTAs:")
        print(f"🇮🇳 Hinglish: {ctas.get('hinglish')}")
        print(f"🇵🇰 Roman Urdu: {ctas.get('roman_urdu')}")
        print(f"🇺🇸 English: {ctas.get('english')}")
        print(f"🇧🇩 Bengali: {ctas.get('bengali')}")
        
        links = fashion.get('search_links', {})
        print("\nSearch Links:")
        print(f"- Myntra: {links.get('myntra')}")
        print(f"- Amazon IN: {links.get('amazon_in')}")
        print(f"- Nykaa: {links.get('nykaa')}")
    else:
        print("❌ Fashion Scout data missing. Check logs or Gemini quota.")

if __name__ == "__main__":
    test_fashion_scout()
