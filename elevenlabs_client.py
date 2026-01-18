import os
import mysql.connector
from elevenlabs import ElevenLabs
import base64
from typing import List, Dict
import subprocess
import tempfile
import io
import imageio_ffmpeg

class ElevenLabsClient:
    def __init__(self):
        self.db_config = {
            'user': 'youtube',
            'password': 'youtube2122',
            'host': 'devlab.pics',
            'database': 'youtubedb',
            'port': 3306,
            'use_pure': True
        }
        self.client = None
        self.output_dir = r"D:\youtube"
        os.makedirs(self.output_dir, exist_ok=True)
        # Default key setter not called here, will be called from UI

    def get_db_connection(self):
        return mysql.connector.connect(**self.db_config)

    def get_api_keys(self) -> List[Dict]:
        """Fetch all AUDIO type API keys from key_manager."""
        keys = []
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name, api_key FROM key_mgr WHERE kind='AUDIO' AND use_yn='Y' AND user_id='admin'")
            keys = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            error_msg = f"Error fetching API keys: {e}\n"
            print(error_msg)
            with open("db_error_log.txt", "a", encoding="utf-8") as f:
                f.write(error_msg)
        return keys

    def get_youtube_keys(self) -> List[Dict]:
        """Fetch all YOUTUBE type API keys from key_manager."""
        keys = []
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name, api_key FROM key_mgr WHERE kind='YOUTUBE' AND use_yn='Y' AND user_id='admin'")
            keys = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            error_msg = f"Error fetching YouTube API keys: {e}\n"
            print(error_msg)
            with open("db_error_log.txt", "a", encoding="utf-8") as f:
                f.write(error_msg)
        return keys

    def get_google_keys(self) -> List[Dict]:
        """Fetch all GOOGLE type API keys from key_manager."""
        keys = []
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name, api_key FROM key_mgr WHERE kind='GOOGLE' AND use_yn='Y' AND user_id='admin'")
            keys = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            error_msg = f"Error fetching Google API keys: {e}\n"
            print(error_msg)
            with open("db_error_log.txt", "a", encoding="utf-8") as f:
                f.write(error_msg)
        return keys

    def set_api_key(self, api_key: str):
        """Set the API key and re-initialize the client."""
        if not api_key:
            return
        try:
            self.client = ElevenLabs(api_key=api_key)
        except Exception as e:
            print(f"Error setting API key: {e}")

    def get_voices(self) -> List[Dict]:
        """Fetch voices from voice_actor table."""
        voices_data = []
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # Fetch prompt (voice_name) and model_id (actual voice ID)
            cursor.execute("SELECT voice_name, model_id FROM voice_actor WHERE use_yn='Y'")
            rows = cursor.fetchall()
            
            for row in rows:
                voices_data.append({
                    "voice_id": row['model_id'], # DB model_id is actually the Voice ID
                    "name": row['voice_name'],
                    "category": "DB" # Placeholder
                })
            cursor.close()
            conn.close()
        except Exception as e:
            error_msg = f"Error fetching voices: {e}\n"
            print(error_msg)
            with open("db_error_log.txt", "a", encoding="utf-8") as f:
                f.write(error_msg)
        return voices_data

    def get_models(self) -> List[Dict]:
        """Return hardcoded list of requested models."""
        return [
            {"model_id": "eleven_v3", "name": "Eleven v3"},
            {"model_id": "eleven_multilingual_v2", "name": "Eleven Multilingual v2"},
            {"model_id": "eleven_turbo_v2_5", "name": "Eleven Turbo v2.5"},
        ]

    def generate_audio(self, text: str, voice_id: str, model_id: str = "eleven_multilingual_v2", 
                       stability: float = 0.5, similarity_boost: float = 0.75, 
                       style: float = 0.0, use_speaker_boost: bool = True,
                       speed: float = 1.0, 
                       volume: float = 1.0, # 볼륨 조절 추가
                       filename: str = None, custom_dir: str = None,
                       sub_segments: List[str] = None) -> str:
        
        if not self.client:
            raise ValueError("API Key not set. Please select an API Key.")

        output_dir = custom_dir if custom_dir else self.output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        try:
            # 타임스탬프를 포함하여 생성 요청
            response = self.client.text_to_speech.convert_with_timestamps(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                voice_settings={
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": use_speaker_boost,
                    "speed": speed # 속도 설정 반영
                }
            )
            
            # 오디오 데이터 추출 (SDK 버전/타입에 따라 다양할 수 있음)
            # 최근 SDK 버전에서는 audio_base_64 (언더바 2개) 형식을 사용함
            audio_raw = None
            alignment = None
            
            if hasattr(response, "audio_base_64"):
                audio_raw = response.audio_base_64
            elif hasattr(response, "audio_base64"):
                audio_raw = response.audio_base64
            elif hasattr(response, "audio"):
                audio_raw = response.audio
            elif isinstance(response, dict):
                audio_raw = response.get("audio_base_64") or response.get("audio_base64") or response.get("audio")
                
            if hasattr(response, "alignment"):
                alignment = response.alignment
            elif isinstance(response, dict):
                alignment = response.get("alignment")

            if audio_raw is None:
                raise AttributeError(f"Could not find audio data in response: {type(response)}")
                
            audio_bytes = base64.b64decode(audio_raw)

            # 파일명 결정
            if filename:
                if not filename.endswith('.mp3'):
                    filename += ".mp3"
                filepath = os.path.join(output_dir, filename)
            else:
                import uuid
                filename = f"{uuid.uuid4()}.mp3"
                filepath = os.path.join(output_dir, filename)

            # 오디오 파일 저장
            if volume == 1.0:
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
            else:
                # ffmpeg를 직접 사용하여 볼륨 조절
                try:
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        tmp.write(audio_bytes)
                        tmp_path = tmp.name
                    
                    # ffmpeg 명령어: volume=2.0 (2배), volume=0.5 (절반)
                    cmd = [
                        ffmpeg_exe, "-y", "-i", tmp_path,
                        "-filter:a", f"volume={volume}",
                        "-c:a", "libmp3lame", "-q:a", "2",
                        filepath
                    ]
                    
                    # 콘솔창 안뜨게 설정 (Windows)
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    result = subprocess.run(cmd, check=True, startupinfo=startupinfo, capture_output=True)
                    print(f"Volume adjusted to {volume} using FFmpeg.")
                    
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception as fe:
                    print(f"ffmpeg 볼륨 조절 오류 (원본 저장): {fe}")
                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)

            # 타이밍 메타데이터(JSON) 저장 - SRT 대신 데이터로 관리
            meta_path = filepath.replace(".mp3", ".json")
            self.save_alignment_metadata(alignment, meta_path, sub_segments)
            
            return filepath
        except Exception as e:
            raise e

    def save_alignment_metadata(self, alignment, json_path, sub_segments=None):
        """ElevenLabs alignment 데이터를 JSON으로 저장 (향후 실시간 매칭용)"""
        try:
            import json
            data = {
                "characters": alignment.characters,
                "character_start_times_seconds": alignment.character_start_times_seconds,
                "character_end_times_seconds": alignment.character_end_times_seconds,
                "sub_segments": sub_segments
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"타이밍 메타데이터 저장 오류: {e}")
