import sys
import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage

class YoutubeSearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, api_key, query, days, video_type):
        super().__init__()
        self.api_key = api_key
        self.query = query
        self.days = days
        self.video_type = video_type
        self.base_url = "https://www.googleapis.com/youtube/v3/"

    def run(self):
        try:
            # 1. Search API
            # RFC 3339 format ex) 2023-01-01T00:00:00Z
            published_after = (datetime.utcnow() - timedelta(days=self.days)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            params = {
                'part': 'snippet',
                'type': 'video',
                'order': 'viewCount',
                'publishedAfter': published_after,
                'maxResults': 50,
                'q': self.query,
                'key': self.api_key,
                'regionCode': 'KR',
                'relevanceLanguage': 'ko'
            }
            if self.video_type and self.video_type != 'any':
                params['videoDuration'] = self.video_type

            query_string = urllib.parse.urlencode(params)
            url = f"{self.base_url}search?{query_string}"
            
            self.log_signal.emit("🔍 YouTube 검색 API 호출 중...")
            data = self._fetch_json(url)
            
            items = data.get('items', [])
            if not items:
                self.finished.emit([])
                return

            video_ids = [item['id']['videoId'] for item in items]
            channel_ids = [item['snippet']['channelId'] for item in items]
            
            # 2. Channels API (Batch)
            self.log_signal.emit(f"📊 채널 정보 조회 중... ({len(set(channel_ids))}개)")
            channels_map = {}
            if channel_ids:
                # API limit per request is 50. channel_ids can be up to 50, so one requests usually enough.
                # If unique channels < 50, it works fine.
                unique_cids = list(set(channel_ids))
                
                # Split chunks if needed (defensive)
                for i in range(0, len(unique_cids), 50):
                    chunk = unique_cids[i:i+50]
                    c_params = {
                        'part': 'snippet,statistics',
                        'id': ','.join(chunk), 
                        'key': self.api_key
                    }
                    c_url = f"{self.base_url}channels?{urllib.parse.urlencode(c_params)}"
                    c_data = self._fetch_json(c_url)
                    for item in c_data.get('items', []):
                        channels_map[item['id']] = item
            
            # 3. Videos API (Batch)
            self.log_signal.emit(f"🎥 영상 상세 정보 조회 중... ({len(video_ids)}개)")
            videos_map = {}
            if video_ids:
                # Video IDs are unique per item, max 50
                v_params = {
                    'part': 'snippet,statistics',
                    'id': ','.join(video_ids),
                    'key': self.api_key
                }
                v_url = f"{self.base_url}videos?{urllib.parse.urlencode(v_params)}"
                v_data = self._fetch_json(v_url)
                for item in v_data.get('items', []):
                    videos_map[item['id']] = item

            # 4. Merge Data
            results = []
            for idx, item in enumerate(items):
                vid = item['id']['videoId']
                cid = item['snippet']['channelId']
                
                v_detail = videos_map.get(vid, {})
                c_detail = channels_map.get(cid, {})
                
                # Safely get nested keys
                v_snip = v_detail.get('snippet', {})
                v_stat = v_detail.get('statistics', {})
                c_snip = c_detail.get('snippet', {})
                c_stat = c_detail.get('statistics', {})
                
                # 썸네일: medium (320x180) or standard if avail
                thumb_url = item['snippet']['thumbnails'].get('medium', {}).get('url', '')
                if not thumb_url:
                    thumb_url = item['snippet']['thumbnails'].get('default', {}).get('url', '')

                row = {
                    'number': idx + 1,
                    'video_id': vid,
                    'channel_id': cid,
                    'thumbnail_url': thumb_url,
                    'channel_name': item['snippet']['channelTitle'],
                    'title': item['snippet']['title'], # HTML unescape might be needed but usually OK
                    'view_count': int(v_stat.get('viewCount', 0)),
                    'subscriber_count': int(c_stat.get('subscriberCount', 0)),
                    'video_total': int(c_stat.get('videoCount', 0)),
                    'lang': v_snip.get('defaultLanguage', '-'),
                    'audio_lang': v_snip.get('defaultAudioLanguage', '-'),
                    'country': c_snip.get('country', '-'),
                    'published_at': item['snippet']['publishedAt']
                }
                results.append(row)
            
            self.log_signal.emit(f"✅ 검색 완료: {len(results)}건")
            self.finished.emit(results)
            
        except Exception as e:
            self.error.emit(str(e))

    def _fetch_json(self, url):
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                raise Exception(f"HTTP Error {response.status}")
            return json.loads(response.read().decode('utf-8'))

class ImageLoadWorker(QThread):
    loaded = pyqtSignal(int, QPixmap) # row_idx, pixmap
    
    def __init__(self, tasks):
        # tasks: list of (row_idx, url)
        super().__init__()
        self.tasks = tasks

    def run(self):
        for row_idx, url in self.tasks:
            try:
                if not url: continue
                data = urllib.request.urlopen(url).read()
                image = QImage()
                image.loadFromData(data)
                # Scale if needed? QTableWidget handles icon size but we can resize here used generic size
                # 120x90 roughly
                pixmap = QPixmap.fromImage(image)
                self.loaded.emit(row_idx, pixmap)
            except:
                pass
