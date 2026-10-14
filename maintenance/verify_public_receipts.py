"""Read public Quiz metadata with an existing read grant; no owner-only fields."""
from datetime import datetime, timezone
import json
from pathlib import Path

QUIZ_IDS = ['GwI8ASuKO-I', 'jxnLl_G2cnM', 'dWbWj5nrXAs']
QUIZ_CHANNEL = 'UCMVToyerFF_UxUP0k_2GAPQ'


def check(service):
    response = service.videos().list(part='snippet,status', id=','.join(QUIZ_IDS)).execute(num_retries=3)
    actual = {item['id']: item for item in response.get('items', [])}
    rows = []
    for video_id in QUIZ_IDS:
        item = actual.get(video_id)
        row = {'video_id': video_id, 'youtube_url': 'https://youtu.be/' + video_id,
               'publication_status': 'not_publicly_verified'}
        if item:
            if item.get('snippet', {}).get('channelId') != QUIZ_CHANNEL:
                raise ValueError('Video belongs to a different channel')
            row.update(title=item['snippet']['title'], youtube_status=item.get('status', {}))
            if item.get('status', {}).get('privacyStatus') == 'public':
                row['publication_status'] = 'public_verified'
        rows.append(row)
    return {'verified_at': datetime.now(timezone.utc).isoformat(), 'channel_id': QUIZ_CHANNEL,
            'public_count': sum(row['publication_status'] == 'public_verified' for row in rows), 'videos': rows}


if __name__ == '__main__':
    from verify_existing_uploads import youtube_service
    report = check(youtube_service())
    Path('maintenance/public-quiz-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
