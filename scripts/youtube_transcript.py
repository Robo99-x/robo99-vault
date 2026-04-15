#!/usr/bin/env python3
import sys
import re
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def extract_video_id(url_or_id: str):
    # Accept raw id
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id
    # Parse youtu.be or youtube.com URL
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        return m.group(1)
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: youtube_transcript.py <youtube_url_or_id> [lang]")
        sys.exit(1)

    vid = extract_video_id(sys.argv[1])
    if not vid:
        print("ERROR: Could not parse video id.")
        sys.exit(2)

    lang = sys.argv[2] if len(sys.argv) > 2 else "ko"
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(vid, languages=[lang, "en"])
    except (TranscriptsDisabled, NoTranscriptFound):
        print("ERROR: Transcript not available.")
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(4)

    # transcript is list of snippets
    text = "\n".join([t.text for t in transcript])
    print(text)


if __name__ == "__main__":
    main()
