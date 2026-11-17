"""
YouTube Data API v3 Auto-Uploader
Uploads generated vertical video clips directly to your YouTube channel as Shorts.
Handles OAuth2 token caching, video metadata, and gaming category tagging.
"""

import os
import logging
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(
        self,
        client_secrets_file: str = "client_secret.json",
        token_file: str = "token.json",
    ):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.service = None

    def authenticate(self) -> bool:
        """Authenticates with YouTube API using saved token or OAuth flow."""
        creds = None
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                logger.warning(f"Error loading token: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Error refreshing token: {e}")
                    creds = None

            if not creds:
                if not os.path.exists(self.client_secrets_file):
                    logger.error(
                        f"Missing '{self.client_secrets_file}'. "
                        "Download OAuth Client ID credentials from Google Cloud Console."
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        self.service = build("youtube", "v3", credentials=creds)
        logger.info("YouTube API client authenticated successfully.")
        return True

    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        privacy_status: str = "public",
    ) -> Optional[str]:
        """
        Uploads an MP4 file as a YouTube Short.
        Returns the published video URL if successful.
        """
        if not self.service:
            if not self.authenticate():
                logger.error("Failed to authenticate YouTube client.")
                return None

        # Ensure #Shorts is present in title/description for YouTube Shorts algorithm
        if "#Shorts" not in title and "#shorts" not in title:
            title = f"{title} #Shorts"

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags or ["GTA 6", "Shorts", "Gaming"],
                "categoryId": "20",  # 20 = Gaming category
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        logger.info(f"Uploading '{video_path}' to YouTube Shorts (Status: {privacy_status})...")

        try:
            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 4,
            )
            request = self.service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")

            video_id = response.get("id")
            video_url = f"https://youtu.be/{video_id}"
            logger.info(f"🎉 Upload Complete! Watch Short: {video_url}")
            return video_url

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return None
