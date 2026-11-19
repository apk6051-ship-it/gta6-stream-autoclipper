"""
One-Time YouTube Channel Linker
Run this once after placing client_secret.json in this directory.
It opens a browser window for you to select your YouTube channel and authorizes uploads.
"""

import sys
from src.uploader import YouTubeUploader

def main():
    print("=" * 60)
    print("  Linking YouTube Channel to GTA 6 Auto-Clipper")
    print("=" * 60)
    
    uploader = YouTubeUploader()
    if uploader.authenticate():
        print("\n🎉 SUCCESS! Your YouTube channel is linked.")
        print("A permanent token has been saved to 'token.json'.")
        print("Future uploads will happen automatically without asking again!")
    else:
        print("\n❌ Failed to link. Please ensure 'client_secret.json' is in this folder.")
        sys.exit(1)

if __name__ == "__main__":
    main()
