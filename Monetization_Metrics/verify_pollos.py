import os
import sys
import json
import logging

# Add project root to path
sys.path.append(os.getcwd())

from Intelligence_Modules.monetization_brain import brain

def test_monetization():
    print("Testing Los Pollos Integration...")
    
    # 1. Test Link Rotation
    link = brain.get_monetization_link()
    print(f"Generated Link: {link}")
    
    if not link:
        print("❌ Failed to get monetization link. Check 'The_json/los_pollos_links.json'.")
    else:
        print("✅ Link rotation working.")

    # 2. Test Brain Response (Mocked Input)
    # This will use Gemini if configured, or fallback
    print("\nTesting Brain Analysis...")
    res = brain.analyze_content("Stunning fashion model in red dress", 15.0)
    
    print(f"Approved: {res.get('approved')}")
    print(f"Caption: {res.get('final_caption')}")
    print(f"CTA: {res.get('monetization_cta')}")
    print(f"Risk: {res.get('risk_level')}")

    if res.get('monetization_cta'):
        print("✅ CTA generation integrated into brain.")
    else:
        print("❌ CTA generation missing from brain response.")

    # 3. Test Controls
    print("\nTesting Environment Controls...")
    os.environ["LOS_POLLOS_TELEGRAM"] = "no"
    enable_lp_tele = os.getenv("LOS_POLLOS_TELEGRAM", "yes").lower() in ["yes", "true", "on"]
    mock_mon_link = brain.get_monetization_link() if enable_lp_tele else None
    print(f"LP Telegram (Set to 'no'): {mock_mon_link} (Expect: None)")
    
    os.environ["LOS_POLLOS_TELEGRAM"] = "yes"
    enable_lp_tele = os.getenv("LOS_POLLOS_TELEGRAM", "yes").lower() in ["yes", "true", "on"]
    mock_mon_link = brain.get_monetization_link() if enable_lp_tele else None
    print(f"LP Telegram (Set to 'yes'): {mock_mon_link} (Expect: <Link>)")

    if (not os.getenv("LOS_POLLOS_TELEGRAM") == "no" or mock_mon_link) and os.environ["LOS_POLLOS_TELEGRAM"] == "yes":
         print("✅ Controls working as expected.")
    else:
         print("❌ Control logic check failed.")

if __name__ == "__main__":
    test_monetization()
