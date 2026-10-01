"""Use the most relevant returned asset, then prefer portrait quality."""
import requests
import main as bot
from stock_relevance import relevance

def search_pexels_video(query):
    try:
        response=requests.get('https://api.pexels.com/videos/search',
            headers={'Authorization':bot.PEXELS_API_KEY},
            params={'query':query,'per_page':20,'orientation':'portrait','size':'large'},timeout=20)
        response.raise_for_status()
        candidates=[]
        for asset in response.json().get('videos',[]):
            match=relevance(query,asset)
            for file in asset.get('video_files',[]):
                width=int(file.get('width') or 0);height=int(file.get('height') or 0)
                if width>0 and height>=width and file.get('link'):
                    candidates.append((match,min(float(asset.get('duration') or 0),30),width*height,file['link']))
        return max(candidates)[-1] if candidates else None
    except Exception as exc:
        bot.logger.warning('Pexels subject search failed (%s): %s',query,exc)
        return None
