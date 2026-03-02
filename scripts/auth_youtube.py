import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import urllib.request
import urllib.parse

# Add parent directory to path to import config if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # REQUIRED for Community Promotion (Comments)
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
]
CLIENT_SECRET_FILE = "Credentials/client_secret.json"
TOKEN_FILE = "Credentials/token.json"

def authenticate():
    print("🚀 Starting Manual YouTube Authentication...")
    
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"❌ Error: {CLIENT_SECRET_FILE} not found!")
        print("Please download your OAuth 2.0 Client ID JSON from Google Cloud Console")
        print("and save it as 'client_secret.json' in the 'Credentials' directory.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    
    print("\n" + "="*50)
    print("📢 ACTION REQUIRED: YouTube Authentication Needed")
    print("="*50)
    
    try:
        # Try local server first (works on local PC)
        creds = flow.run_local_server(
            port=0, 
            access_type='offline', 
            prompt='consent',
            open_browser=True
        )
    except Exception as e:
        print(f"\nℹ️ Automated browser failed (likely Headless/Colab): {e}")
        print("\n👇 PLEASE AUTHORIZE MANUALLY BY CLICKING THIS LINK:")
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        print(f"\n🔗 {auth_url}\n")
        
        # --- TELEGRAM NOTIFICATION ---
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        if token and admin_id:
            try:
                msg = f"⚠️ YouTube Auth Required!\n\nPlease authorize here:\n{auth_url}"
                api_url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": admin_id, "text": msg}).encode("utf-8")
                urllib.request.urlopen(api_url, data=data, timeout=10)
                print("📡 Auth link sent to your Telegram!")
            except Exception as te:
                print(f"⚠️ Could not send Telegram notification: {te}")
        
        # Note: run_local_server with open_browser=False still tries to listen on localhost.
        # For true headless in 2024+, the user often needs to copy the code from the 
        # redirect URL (even if it's a 404 localhost).
        print("1. Click the link above and authorize.")
        print("2. After authorizing, you will be redirected to a 'localhost' page that might not load.")
        print("3. Copy the 'code' parameter from the URL in your browser address bar.")
        print("   (Example: http://localhost/?code=4/P7q... -> copy the 4/P7q... part)")
        
        # We'll try run_local_server with open_browser=False as it provides a cleaner 
        # way to handle the local redirect if the user can reach it,
        # but for Colab, we just need the code.
        code = input("\n👉 Enter the authorization code: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
    
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
        
    print(f"✅ Authentication successful! Token saved to {TOKEN_FILE}")
    print("You can now restart the bot or try uploading again.")

if __name__ == "__main__":
    # Ensure we are in the root directory
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)
    authenticate()
