import sys
import os
import re
import time
import subprocess
import json
import collections
import traceback
import math
import multiprocessing
import concurrent.futures
import numpy as np
import shutil
from PIL import Image

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QRect, QRectF
from PyQt5.QtGui import (QColor, QFont, QImage, QPainter, QPen, QBrush, QPainterPath)

try:
    import moviepy.editor as mpe
except ImportError:
    mpe = None

# Monkey Patch for Pillow > 9.x not having ANTIALIAS, which MoviePy needs
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

class VideoMergerWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, image_dir, audio_dir, output_dir, subtitles=None, style=None, volume=1.0, trim_end=0.0, use_random_effects=False, is_shorts=False):
        super().__init__()
        self.image_dir = image_dir
        self.audio_dir = audio_dir
        self.output_dir = output_dir
        self.subtitles = subtitles
        self.style = style
        self.volume = volume
        self.trim_end = trim_end
        self.use_random_effects = use_random_effects
        self.is_shorts = is_shorts
        self.target_size = (1080, 1920) if is_shorts else (1920, 1080)
        os.makedirs(self.output_dir, exist_ok=True)

    def run(self):
        start_time = time.time()
        try:
            # 오디오 파일 리스트 (.mp3)
            if not os.path.exists(self.audio_dir):
                self.error.emit("❌ 오디오 폴더를 찾을 수 없습니다.")
                return

            audio_files = [f for f in os.listdir(self.audio_dir) if f.lower().endswith('.mp3')]
            
            # 자연스러운 정렬 (1.mp3, 2.mp3, ... 10.mp3)
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
            audio_files.sort(key=natural_keys)

            total = len(audio_files)
            if total == 0:
                self.error.emit("❌ 오디오 폴더에 mp3 파일이 없습니다.")
                return

            # 병렬 처리를 위한 작업 리스트 생성
            tasks = []
            valid_exts = ['.png', '.jpg', '.jpeg', '.webp']
            
            for i, audio_name in enumerate(audio_files):
                base_name = os.path.splitext(audio_name)[0]
                audio_path = os.path.join(self.audio_dir, audio_name)
                
                # 대응하는 이미지 찾기
                img_path = None
                found_img_name = None
                
                # 1. 같은 이름의 이미지 검색
                for ext in valid_exts:
                    check_path = os.path.join(self.image_dir, base_name + ext)
                    if os.path.exists(check_path):
                        img_path = check_path
                        found_img_name = base_name + ext
                        break
                
                # [NEW] Multi-Image Check: If no base image, check if index-based images (1.jpg, etc.) exist
                if not img_path:
                    # Check for 1.jpg, 1.png etc. in image_dir (or a subfolder if user prefers)
                    # For now, check if 1.jpg exists in image_dir or in a subfolder named base_name
                    multi_img_detected = False
                    for ext in valid_exts:
                        if os.path.exists(os.path.join(self.image_dir, "1" + ext)) or \
                           os.path.exists(os.path.join(self.image_dir, base_name, "1" + ext)):
                            multi_img_detected = True
                            break
                    
                    if multi_img_detected:
                        img_path = "MULTI_IMAGE_MODE" # Signal for process_single_video
                        self.log_signal.emit(f"ℹ️ 다중 이미지 모드 감지: {base_name}")
                
                if not img_path:
                    self.log_signal.emit(f"ℹ️ 이미지 없음 (검정 배경 사용): {base_name}")
                    # img_path는 None으로 유지되어 process_single_video에서 처리됨
                
                output_path = os.path.join(self.output_dir, base_name + ".mp4")
                
                # 랜덤 효과 설정 생성
                item_effect = None
                if self.use_random_effects:
                    import random
                    # 효과: 1(Zoom In), 2(Pan L-R), 3(Pan R-L)
                    # Zoom Out 은 Zoom In 과 반대인데, start/end를 뒤집으면 됨.
                    # 하지만 현재 코드 상 Type 1은 start->end.
                    # 사용자 요청: Zoom In, Out, L->R, R->L
                    # Type 1: Zoom (Generic) -> we can randomize start/end scale
                    # Type 2: Pan L->R
                    # Type 3: Pan R->L
                    
                    eff_type = random.choice([1, 1, 2, 3]) # Zoom 비중을 조금 높임? 아니면 균등하게 1,2,3
                    # Zoom In/Out case for Type 1
                    s_scale = 1.0
                    e_scale = 1.1
                    
                    if eff_type == 1:
                        # 50% 확률로 Zoom In or Zoom Out
                        if random.random() > 0.5:
                            # Zoom In
                            s_scale = 1.0
                            e_scale = 1.15
                        else:
                            # Zoom Out
                            s_scale = 1.15
                            e_scale = 1.0
                    
                    item_effect = {
                        'type': eff_type,
                        'start_scale': s_scale,
                        'end_scale': e_scale,
                        'pan_speed': 1.0
                    }
                
                tasks.append((img_path, audio_path, output_path, base_name, item_effect))

            self.log_signal.emit(f"🚀 총 {len(tasks)}개의 영상 합성을 시작합니다. (병렬 처리 모드)")
            
            # ThreadPoolExecutor를 사용하여 병렬 작업 수행
            max_workers = min(2, multiprocessing.cpu_count()) # 메모리 할당 오류 방지를 위해 최대 2개로 제한
            success_count = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(self.process_single_video, task): task for task in tasks}
                for future in concurrent.futures.as_completed(future_to_task):
                    task_base_name = future_to_task[future][3]
                    try:
                        result = future.result()
                        if result:
                            success_count += 1
                            self.log_signal.emit(f"✅ 완료: {task_base_name}.mp4")
                        else:
                            self.log_signal.emit(f"❌ 실패: {task_base_name}.mp4")
                    except Exception as e:
                        self.log_signal.emit(f"❌ 오류 발생 ({task_base_name}): {e}")

            elapsed = time.time() - start_time
            result_msg = f"영상 합성 완료 (성공 {success_count} / 총 {total})"
            self.finished.emit(result_msg, elapsed)

        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")

    def process_single_video(self, task):
        img_path, audio_path, output_path, base_name, task_effect_config = task
        
        # [Fix] 고유 임시 디렉토리 생성 (충돌 방지 및 안전한 삭제)
        temp_dir = os.path.join(os.path.dirname(output_path), f"temp_{base_name}_{int(time.time())}_{os.getpid()}")
        os.makedirs(temp_dir, exist_ok=True)
        
        # 임시 파일 경로들 (정리용)
        temp_files = []
        
        try:
            # 0. FFmpeg 바이너리 확보
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = "ffmpeg"

            # 1. 오디오 정보 확인 (MoviePy로 메타데이터만 빠르게 읽기)
            #    (ffmpeg probe를 subprocess로 띄우는 것보다 로드되어있는 라이브러리 활용이 간편)
            try:
                import soundfile as sf
                f = sf.SoundFile(audio_path)
                original_duration = len(f) / f.samplerate
                f.close()
            except:
                # Fallback
                try:
                    audio_clip = mpe.AudioFileClip(audio_path)
                    original_duration = audio_clip.duration
                    audio_clip.close()
                except:
                    # If moviepy fails or not imported
                    original_duration = 10.0 # Fallback default
                    print("Audio duration check failed, using default 10s")

            # 2. 오디오 옵션 계산
            # - Trim End
            final_duration = original_duration
            if self.trim_end > 0:
                final_duration = max(0.1, final_duration - self.trim_end)
            
            # - Volume, Fadeout (Filter로 처리)
            # volume=1.0 (기본), afade=t=out:st=duration-0.05:d=0.05
            
            # 3. 자막 처리 (기존 create_text_image 활용 -> PNG 저장)
            meta_path = audio_path.replace(".mp3", ".json")
            sub_timing_list = [] 
            
            sub_list = None
            if self.subtitles and base_name in self.subtitles:
                sub_list = self.subtitles[base_name]

            # 항상 SRT 파싱 시도 (다중 이미지 인덱스 매칭용)
            srt_path_check = audio_path.replace(".mp3", ".srt")
            segments = None
            if os.path.exists(srt_path_check):
                segments = self.parse_srt(srt_path_check)
                if not sub_timing_list:
                    for seg in segments:
                        sub_timing_list.append((seg['start'], seg['end'], seg['text']))
                    if sub_timing_list:
                        self.log_signal.emit(f"   ℹ️ [SRT] {base_name}: {len(sub_timing_list)}개 자막 구간 싱크 적용")
            
            if os.path.exists(meta_path):
                # JSON이 있으면 덮어쓰기 (더 정밀함)
                json_timing = self.get_timing_from_metadata(meta_path, sub_list)
                if json_timing:
                    sub_timing_list = json_timing
                    mode_info = "입력창 기준" if sub_list else "JSON 저장 데이터"
                    self.log_signal.emit(f"   ℹ️ [정밀] {base_name}: {len(sub_timing_list)}개 자막 구간 {mode_info} 싱크 적용")
            
            if not sub_timing_list and sub_list:
                num_subs = len(sub_list)
                sub_duration = max(0.5, final_duration / num_subs)
                for idx, text in enumerate(sub_list):
                    if isinstance(text, dict): text = text.get("original", "")
                    start_t = idx * sub_duration
                    actual_dur = sub_duration if idx < num_subs - 1 else (final_duration - start_t)
                    sub_timing_list.append((start_t, start_t + actual_dur, text))

            subtitle_inputs = [] # (path, start_t, end_t)
            
            # 이미지 사이즈 확인 (자막 생성을 위해)
            # 이미지 사이즈 확인 (자막 생성을 위해)
            # [Fix] 자막은 최종 영상 해상도 기준으로 생성해야 오버레이 좌표가 맞음
            TARGET_W, TARGET_H = self.target_size
            w, h = TARGET_W, TARGET_H
            
            # 자막 PNG 생성
            if sub_timing_list:
                # temp_dir는 상단에서 이미 생성됨
                pass
                
                for idx, (start_t, end_t, text) in enumerate(sub_timing_list):
                    # 표시 시간이 영상 길이보다 길면 무시
                    if start_t >= final_duration: continue
                    real_end = min(end_t, final_duration)
                    
                    # [Fix] 타임스탬프 데이터 오류로 길이가 0인 경우 강제 보정
                    if real_end <= start_t:
                        real_end = min(start_t + 3.0, final_duration)
                        
                    if real_end <= start_t: continue
                    
                    # [Gap Filling Logic]
                    # 만약 다음 자막과 매우 가까우면(예: 0.5초 이내), 현재 자막을 늘려서 배경 깜빡임 방지
                    # 단, 마지막 자막은 제외
                    if idx < len(sub_timing_list) - 1:
                        next_start = sub_timing_list[idx+1][0]
                        # 간격이 작으면 현재 자막의 끝을 다음 자막 시작까지 연장
                        if 0 < (next_start - real_end) < 0.5:
                            real_end = next_start

                    # 텍스트 이미지 생성 (numpy array)
                    rgba_arr = self.create_text_image(text, (w, h))
                    
                    # PNG로 저장
                    sub_filename = f"sub_{base_name}_{idx}.png"
                    sub_path = os.path.join(temp_dir, sub_filename)
                    
                    # numpy -> Image -> save
                    start_t_str = f"{start_t:.3f}"
                    end_t_str = f"{real_end:.3f}"
                    
                    result_img = Image.fromarray(rgba_arr, 'RGBA')
                    result_img.save(sub_path)
                    
                    temp_files.append(sub_path)
                    subtitle_inputs.append((sub_path, start_t, real_end))

            # [NEW] Multi-Image Switching Logic
            image_checkpoints = []
            final_img_concat_path = None
            
            # segments were parsed above
            if segments:
                # Use os.path.dirname(audio_path) or self.image_dir as base
                # In run(), we checked self.image_dir.
                search_dirs = [os.path.dirname(audio_path), self.image_dir, os.path.join(self.image_dir, base_name)]
                
                found_at_least_one = False
                for seg in segments:
                    idx = seg['index']
                    t = seg['start']
                    
                    for s_dir in search_dirs:
                        found_path = None
                        for ext in ['.jpg', '.png', '.jpeg', '.webp']:
                            check = os.path.join(s_dir, f"{idx}{ext}")
                            if os.path.exists(check):
                                found_path = check
                                break
                        if found_path:
                            image_checkpoints.append((t, found_path))
                            found_at_least_one = True
                            break
                
                if len(image_checkpoints) > 1:
                    # Create Concat List for Images
                    # [Fix] Use sub-folder in temp_dir for easier cleanup
                    image_temp_dir = os.path.join(temp_dir, "imgs")
                    os.makedirs(image_temp_dir, exist_ok=True)
                    
                    processed_imgs = []
                    for i_p_idx, (t, img_p) in enumerate(image_checkpoints):
                        img_name_only = os.path.basename(img_p)
                        scaled_p = os.path.join(image_temp_dir, f"scaled_{i_p_idx}_{img_name_only}.png")
                        
                        try:
                            with Image.open(img_p) as test_img:
                                if test_img.mode != 'RGB': test_img = test_img.convert('RGB')
                                iw, ih = test_img.size
                                aspect = iw / ih
                                target_aspect = TARGET_W / TARGET_H
                                if aspect > target_aspect:
                                    new_w = TARGET_W; new_h = int(TARGET_W / aspect)
                                else:
                                    new_h = TARGET_H; new_w = int(TARGET_H * aspect)
                                resized = test_img.resize((new_w, new_h), Image.LANCZOS)
                                final_bg = Image.new('RGB', (TARGET_W, TARGET_H), (0, 0, 0))
                                offset = ((TARGET_W - new_w) // 2, (TARGET_H - new_h) // 2)
                                final_bg.paste(resized, offset)
                                final_bg.save(scaled_p)
                                processed_imgs.append((t, scaled_p))
                                temp_files.append(scaled_p)
                        except Exception as e:
                            # Fallback: Black background to prevent resolution mismatch OOM/Error
                            black_fallback = os.path.join(image_temp_dir, f"fallback_{i_p_idx}.png")
                            Image.new('RGB', (TARGET_W, TARGET_H), (0,0,0)).save(black_fallback)
                            processed_imgs.append((t, black_fallback))
                            temp_files.append(black_fallback)
                    
                    # Sync Fix: 0.0s check
                    processed_imgs.sort(key=lambda x: x[0])
                    if processed_imgs and processed_imgs[0][0] > 0.001:
                        black_p = os.path.join(image_temp_dir, "black_start.png")
                        if not os.path.exists(black_p):
                            Image.new('RGB', (TARGET_W, TARGET_H), (0,0,0)).save(black_p)
                        processed_imgs.insert(0, (0.0, black_p))
                        temp_files.append(black_p)
                    
                    final_img_concat_path = os.path.join(image_temp_dir, f"img_list.txt")
                    with open(final_img_concat_path, "w", encoding='utf-8') as f:
                        for i, (t, p) in enumerate(processed_imgs):
                            safe_p = p.replace("\\", "/")
                            if i < len(processed_imgs) - 1:
                                dur = processed_imgs[i+1][0] - t
                                f.write(f"file '{safe_p}'\n")
                                f.write(f"duration {dur:.3f}\n")
                            else:
                                dur = final_duration - t
                                if dur < 0.1: dur = 0.5
                                f.write(f"file '{safe_p}'\n")
                                f.write(f"duration {dur:.3f}\n")
                        # Repeat last for EOF
                        if processed_imgs:
                            f.write(f"file '{processed_imgs[-1][1].replace('\\','/')}'\n")
                    
                    temp_files.append(final_img_concat_path)

            # 4. FFmpeg 명령어 구성
            command = [ffmpeg_exe, "-y", "-fflags", "+genpts"]
            
            # [Input 0] 배경 이미지 (Loop, Concat, or Black) OR 배경 비디오
            FPS = 30
            is_video_input = False
            if img_path and img_path.lower().endswith('.mp4'):
                is_video_input = True
                
            if final_img_concat_path:
                command.extend(["-f", "concat", "-safe", "0", "-i", final_img_concat_path])
            elif is_video_input and os.path.exists(img_path):
                 # Video Input Mode: Loop infinitely, will be trimmed by -t at output
                 command.extend(["-stream_loop", "-1", "-i", img_path])
            elif img_path and os.path.exists(img_path) and img_path != "MULTI_IMAGE_MODE":
                command.extend(["-loop", "1", "-t", f"{final_duration:.6f}", "-i", img_path])
            else:
                # 검정 배경 생성 (lavfi color filter 사용)
                command.extend(["-f", "lavfi", "-i", f"color=c=black:s={TARGET_W}x{TARGET_H}:r={FPS}:d={final_duration:.6f}"])
            
            # [Input 1] 오디오
            command.extend(["-i", audio_path])
            
            # [Input 2] 자막용 Concat 파일 (WinError 206 방지용)
            concat_sub_list_p = os.path.join(temp_dir, f"subs_{base_name}.txt")
            transparent_p = os.path.join(temp_dir, "transparent.png")
            
            # 투명 배경 이미지 생성 (1920x1080)
            if not os.path.exists(transparent_p):
                Image.new('RGBA', (TARGET_W, TARGET_H), (0,0,0,0)).save(transparent_p)
            
            with open(concat_sub_list_p, "w", encoding='utf-8') as f:
                last_time = 0.0
                for s_p, s_t, e_t in subtitle_inputs:
                    # 이전 자막과의 공백 처리
                    gap = s_t - last_time
                    if gap > 0.001:
                        f.write(f"file '{transparent_p}'\n")
                        f.write(f"duration {gap:.3f}\n")
                    
                    # 현재 자막
                    dur = e_t - s_t
                    if dur < 0.001: dur = 0.1 # 최소 길이 보장
                    f.write(f"file '{s_p}'\n")
                    f.write(f"duration {dur:.3f}\n")
                    last_time = e_t
                
                # 영상 끝까지 투명 처리 추가 (필요시)
                if last_time < final_duration:
                    f.write(f"file '{transparent_p}'\n")
                    f.write(f"duration {final_duration - last_time:.3f}\n")
                
                # FFmpeg concat demuxer requirement
                if subtitle_inputs:
                    last_file = subtitle_inputs[-1][0]
                    f.write(f"file '{last_file}'\n") # No duration for EOF hint

            # FFmpeg fix: forward slashes in concat file
            self.fix_concat_file_local(concat_sub_list_p)
            
            command.extend(["-f", "concat", "-safe", "0", "-i", concat_sub_list_p])
                
            filter_complex = ""
            
            # ========== Video Filter ==========
            # Effect Config 확인
            effect_config = task_effect_config if task_effect_config else getattr(self, 'effect_config', None)
            effect_type = effect_config.get('type', 0) if effect_config else 0
            
            if effect_config:
                self.log_signal.emit(f"   🚀 [Ultra-Smooth] Applying 8K Supersampling Effect: {effect_type}")
                pass
            
            filter_parts = []
            if final_img_concat_path:
                # Concat 모드
                filter_parts.append(f"[0:v]fps={FPS},scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1:1[v_bg]")
            elif is_video_input:
                # Video Input Mode: Scale and Crop to Fill 1080x1920 (Shorts)
                # Ensure it fills the screen (increase) then crop
                filter_parts.append(f"[0:v]fps={FPS},scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=idea,crop={TARGET_W}:{TARGET_H},setsar=1:1[v_bg]")
                # Using 'idea' isn't standard in ffmpeg scale? standardized: 'increase' then crop
                # Correct logic: scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920
                # Overwriting previous line logic
                filter_parts.pop() 
                filter_parts.append(f"[0:v]fps={FPS},scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},setsar=1:1[v_bg]")

            elif img_path and os.path.exists(img_path) and img_path != "MULTI_IMAGE_MODE":
                # Effect Config (Zoom/Pan)
                # [Anti-Jitter] 8K(7680x4320) Ultra-Supersampling
                SUPER_W, SUPER_H = 7680, 4320
                filter_parts.append(f"[0:v]scale={SUPER_W}:{SUPER_H}:flags=bicubic,setsar=1:1,fps={FPS}[v_high]")
                
                # Zoom/Pan Expression
                start_scale = effect_config.get('start_scale', 1.0) if effect_config else 1.0
                end_scale = effect_config.get('end_scale', 1.0) if effect_config else 1.0
                total_frames = int(final_duration * FPS)
                if total_frames <= 0: total_frames = 1
                
                z_expr = "1"; x_expr = "0"; y_expr = "0"
                if effect_type == 1: # Zoom (Unified)
                    denom = total_frames - 1 if total_frames > 1 else 1
                    z_expr = f"{start_scale}+({end_scale}-{start_scale})*on/{denom}"
                    x_expr = "(iw-iw/zoom)/2"
                    y_expr = "(ih-ih/zoom)/2"
                elif effect_type == 2: # Pan Left -> Right
                    pan_z = max(start_scale, 1.05)
                    p_speed = effect_config.get('pan_speed', 1.0)
                    z_expr = f"{pan_z}"
                    denom = total_frames - 1 if total_frames > 1 else 1
                    progress_expr = f"(on*{p_speed}/{denom})"
                    x_expr = f"(iw-iw/zoom)*(1-min(1,{progress_expr}))"
                    y_expr = "ih/2-(ih/2/zoom)"
                elif effect_type == 3: # Pan Right -> Left
                    pan_z = max(start_scale, 1.05)
                    p_speed = effect_config.get('pan_speed', 1.0)
                    z_expr = f"{pan_z}"
                    denom = total_frames - 1 if total_frames > 1 else 1
                    progress_expr = f"(on*{p_speed}/{denom})"
                    x_expr = f"(iw-iw/zoom)*min(1,{progress_expr})"
                    y_expr = "ih/2-(ih/2/zoom)"
                
                filter_parts.append(f"[v_high]zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={SUPER_W}x{SUPER_H}:fps={FPS}[v_zoomed]")
                # 최종적으로 4K에서 1080p로 다운스케일
                filter_parts.append(f"[v_zoomed]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:flags=lanczos,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1:1[v_bg]")
            else:
                filter_parts.append(f"[0:v]fps={FPS},setsar=1:1[v_bg]")
            
            # ========== Subtitle Filters ==========
            final_v_label = "[v_bg]"
            if subtitle_inputs:
                filter_parts.append(f"{final_v_label}[2:v]overlay=format=auto[v_final]")
                final_v_label = "[v_final]"
            
            # ========== Audio Filter ==========
            fade_duration = 0.05
            fade_start = max(0, final_duration - fade_duration)
            vol_val = self.volume
            filter_parts.append(f"[1:a]volume={vol_val},atrim=duration={final_duration},aresample=48000:async=1,afade=t=out:st={fade_start}:d={fade_duration}[a_out]")
            
            filter_complex = ";".join(filter_parts)
            
            # filter_complex script path
            filter_script_path = os.path.join(temp_dir, f"filter_fc_{base_name}.txt")
            with open(filter_script_path, "w", encoding='utf-8') as f:
                f.write(filter_complex)
            temp_files.append(filter_script_path)

            # ========== Final Assembly ==========
            command.extend(["-filter_complex_script", filter_script_path])
            command.extend(["-map", final_v_label, "-map", "[a_out]"])
            
            # Encoding Options
            command.extend(["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            # Strictly limit output duration to audio length
            command.extend(["-t", f"{final_duration:.6f}"])
            command.extend(["-y", output_path])
            
            if effect_config:
                print(f"[Debug] Effect Config: {effect_config}")
            
            # Run
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                encoding='utf-8',
                creationflags=creation_flags
            )
            
            try:
                # [Fix] 8K 업스케일링 등 고부하 작업 시 시간이 오래 걸리므로 타임아웃 대폭 증가
                out, err = process.communicate(timeout=max(300, final_duration * 20 + 200))
                if process.returncode != 0:
                    display_err = err[-1000:] if len(err) > 1000 else err
                    raise Exception(f"FFmpeg Error: {display_err}")
            except subprocess.TimeoutExpired:
                process.kill()
                raise Exception("FFmpeg Timeout")

            # Cleanup Temp Files (Include Directory)
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
            
            return True

        except Exception as e:
            print(f"Error processing {base_name}: {e}")
            traceback.print_exc()
            # Cleanup on error
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except: pass
            return False

    def fix_concat_file_local(self, path):
        lines = []
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith('file'):
                    f.write(line.replace('\\', '/'))
                else:
                    f.write(line)

    def get_timing_from_metadata(self, meta_path, sub_list=None):
        try:
            if not os.path.exists(meta_path):
                return []
                
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            chars = data["characters"]
            starts = data["character_start_times_seconds"]
            ends = data["character_end_times_seconds"]
            
            if sub_list is None:
                sub_list = data.get("sub_segments", [])
                
            if not sub_list:
                return []

            results = []
            current_char_idx = 0
            
            for item in sub_list:
                if isinstance(item, dict):
                    original_text = item.get("original", "")
                    tts_text = item.get("tts", "")
                else:
                    original_text = item
                    tts_text = item

                text_clean = re.sub(r'[^\w]', '', tts_text)
                if not text_clean: continue
                
                seg_start_time = None
                seg_end_time = None
                
                temp_match = ""
                match_start_idx = -1
                
                search_idx = current_char_idx
                while search_idx < len(chars):
                    c_char = chars[search_idx]
                    c_clean = re.sub(r'[^\w]', '', c_char)
                    
                    if c_clean:
                        if match_start_idx == -1: match_start_idx = search_idx
                        temp_match += chars[search_idx]
                    
                    if text_clean in temp_match:
                        seg_start_time = starts[match_start_idx]
                        if search_idx < len(ends):
                            seg_end_time = ends[search_idx]
                        else:
                            seg_end_time = starts[search_idx] if search_idx < len(starts) else seg_start_time

                        current_char_idx = search_idx + 1
                        break
                    search_idx += 1
                
                if seg_start_time is not None:
                    results.append((seg_start_time, seg_end_time, original_text))
            
            return results
        except Exception as e:
            print(f"매칭 오류 ({meta_path}): {e}")
            return []

    def parse_srt(self, srt_path):
        segments = []
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(srt_path, 'r', encoding='cp949') as f:
                content = f.read()
            
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    idx = int(lines[0].strip())
                    time_line = lines[1].strip()
                    text = " ".join(lines[2:])
                    
                    if '-->' in time_line:
                        s_str, e_str = time_line.split('-->')
                        start = self.parse_time(s_str.strip())
                        end = self.parse_time(e_str.strip())
                        
                        segments.append({
                            'index': idx,
                            'start': start,
                            'end': end,
                            'text': text
                        })
                except:
                    pass
        return segments

    def parse_time(self, t_str):
        t_str = t_str.replace(',', '.')
        parts = t_str.split(':')
        if len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h*3600 + m*60 + s
        return 0.0

    def create_text_image(self, text, size):
        if not hasattr(self, '_text_cache'): self._text_cache = {}
        cache_key = f"{text}_{size}_{self.style['font_family']}_{self.style['font_size']}_{self.style['text_color']}_{self.style['outline_color']}_{self.style['bg_color']}"
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]

        width, height = size
        image = QImage(width, height, QImage.Format_RGBA8888)
        image.fill(Qt.transparent)
        
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        font_family = self.style['font_family']
        base_font_size = self.style['font_size']
        
        min_dim = min(width, height)
        scale_factor = min_dim / 1024.0
        
        scaled_font_size = int(base_font_size * scale_factor)
        
        font = QFont(font_family)
        font.setPixelSize(scaled_font_size)
        
        if not any(kw in font_family.lower() for kw in ['bold', 'heavy', 'black', 'eb', 'b']):
            font.setBold(True)
        else:
            font.setBold(False)
            
        painter.setFont(font)
        
        margin_lr = int(40 * scale_factor)
        max_rect = QRect(margin_lr, 0, width - (margin_lr * 2), height) 
        text_rect = painter.boundingRect(max_rect, Qt.AlignCenter | Qt.TextWordWrap, text)
        
        margin_bottom = int(height * 0.05)
        
        padding_h = int(40 * scale_factor) 
        padding_v = int(12 * scale_factor)
        
        bg_rect = text_rect.adjusted(-padding_h, -padding_v, padding_h, padding_v)
        
        box_h = bg_rect.height()
        
        if getattr(self, 'is_shorts', False):
            # Shorts: Center + Offset (Avoid overlapping center face or bottom UI)
            # Center Y = height / 2. Move down by 20% of height.
            target_cy = (height / 2) + (height * 0.20)
            target_top = target_cy - (box_h / 2)
        else:
            # Landscape: Bottom
            target_bottom = height - margin_bottom
            target_top = target_bottom - box_h
        
        dy = int(target_top - bg_rect.top())
        bg_rect.translate(0, dy)
        text_rect.translate(0, dy)

        if self.style.get('use_bg', True) and self.style['bg_color'] != "Transparent":
            color = QColor(self.style['bg_color'])
            opacity = self.style.get('bg_opacity', 255)
            color.setAlpha(opacity)
            
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            radius = int(15 * scale_factor)
            painter.drawRoundedRect(bg_rect, radius, radius)

        text_draw_area = bg_rect.translated(0, 6)

        if self.style.get('use_outline', True) and self.style['outline_color'] and self.style['outline_color'].lower() != "none":
            painter.setPen(QColor(self.style['outline_color']))
            outline_width = int(6 * scale_factor)
            if outline_width < 2: outline_width = 2
            
            steps = 24 
            
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                dx = int(round(outline_width * math.cos(angle)))
                dy = int(round(outline_width * math.sin(angle)))
                painter.drawText(text_draw_area.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, text)
            
            if outline_width > 3:
                inner_width = outline_width / 2.0
                for i in range(steps):
                    angle = 2 * math.pi * i / steps
                    dx = int(round(inner_width * math.cos(angle)))
                    dy = int(round(inner_width * math.sin(angle)))
                    painter.drawText(text_draw_area.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, text)

        painter.setPen(QColor(self.style['text_color']))
        painter.drawText(text_draw_area, Qt.AlignCenter | Qt.TextWordWrap, text)
        
        painter.end()
        
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        arr = np.frombuffer(ptr, np.uint8).copy().reshape((height, width, 4))
        
        if len(self._text_cache) > 50:
            self._text_cache.clear()
        self._text_cache[cache_key] = arr
        return arr

class SingleVideoWorker(VideoMergerWorker):
    def __init__(self, img_path, audio_path, output_path, subtitles=None, style=None, volume=1.0, trim_end=0.0, effect_config=None, is_shorts=False):
        super().__init__(os.path.dirname(img_path), os.path.dirname(audio_path), os.path.dirname(output_path), 
                         subtitles=None, style=style, volume=volume, trim_end=trim_end, is_shorts=is_shorts)
        self.single_img = img_path
        self.single_audio = audio_path
        self.single_output = output_path
        self.single_subtitles = subtitles 
        self.effect_config = effect_config

    def run(self):
        start_time = time.time()
        try:
            base_name = os.path.splitext(os.path.basename(self.single_audio))[0]
            if self.single_subtitles:
                self.subtitles = {base_name: self.single_subtitles}
            else:
                self.subtitles = None
            
            task = (self.single_img, self.single_audio, self.single_output, base_name, None)
            self.log_signal.emit(f"🎞️ 개별 영상 제작 시작: {base_name}...")
            
            success = self.process_single_video(task)
            
            elapsed = time.time() - start_time
            if success:
                self.finished.emit(f"✅ 영상 제작 완료: {os.path.basename(self.single_output)}", elapsed)
            else:
                self.error.emit("❌ 영상 제작에 실패했습니다.")
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")

class VideoDubbingWorker(VideoMergerWorker):
    def __init__(self, video_path, audio_path, output_path, subtitles=None, style=None, volume=1.0):
        super().__init__(os.path.dirname(video_path) if video_path else "", 
                         os.path.dirname(audio_path) if audio_path else "", 
                         os.path.dirname(output_path) if output_path else "", 
                         subtitles=None, style=style, volume=volume)
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.subtitle_data = subtitles 
        
    def run(self):
        start_time = time.time()
        try:
            self.log_signal.emit(f"🎬 동영상 더빙 작업 시작: {os.path.basename(self.video_path)}...")
            self.log_signal.emit(f"   오디오: {os.path.basename(self.audio_path)}")
            
            # [Fix] Unique Temp Dir
            temp_dir = os.path.join(os.path.dirname(self.output_path), f"temp_dub_{int(time.time())}_{os.getpid()}")
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = "ffmpeg"
            
            if not os.path.exists(self.audio_path):
                self.error.emit(f"❌ 오디오 파일 없음: {self.audio_path}")
                return
            
            try:
                import soundfile as sf
                f = sf.SoundFile(self.audio_path)
                audio_duration = len(f) / f.samplerate
                f.close()
            except ImportError:
                try:
                    clip = mpe.AudioFileClip(self.audio_path)
                    audio_duration = clip.duration
                    clip.close()
                except:
                   audio_duration = 0
                
            self.log_signal.emit(f"   오디오 길이: {audio_duration:.2f}초")
            
            try:
                v_clip = mpe.VideoFileClip(self.video_path)
                video_duration = v_clip.duration
                v_clip.close()
                self.log_signal.emit(f"   원본 비디오 길이: {video_duration:.2f}초")
            except:
                pass
            
            base, ext = os.path.splitext(self.audio_path)
            meta_path = base + ".json"
            self.log_signal.emit(f"   ℹ️ 자막 JSON 경로 확인: {meta_path}")
            sub_timing_list = []
            
            if os.path.exists(meta_path):
                import json
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    if "saved_sub_segments" in data:
                        for item in data["saved_sub_segments"]:
                             s = float(item['start'])
                             e = float(item['end'])
                             t = item['text']
                             sub_timing_list.append((s, e, t))
                    elif "sub_segments" in data:
                        has_timing_in_segments = True
                        if data["sub_segments"]:
                            first = data["sub_segments"][0]
                            if isinstance(first, dict) and "start" not in first:
                                has_timing_in_segments = False
                        
                        if has_timing_in_segments:
                            for item in data["sub_segments"]:
                                 if isinstance(item, dict):
                                     s = float(item.get('start', 0))
                                     e = float(item.get('end', 0))
                                     t = item.get('text', "")
                                 elif isinstance(item, (list, tuple)) and len(item) >= 3:
                                     s = float(item[0])
                                     e = float(item[1])
                                     t = item[2]
                                 else:
                                     continue
                                 sub_timing_list.append((s, e, t))
                        else:
                            if "characters" in data and "character_start_times_seconds" in data:
                                all_chars = data["characters"]
                                all_starts = data["character_start_times_seconds"]
                                all_ends = data["character_end_times_seconds"] if "character_end_times_seconds" in data else []
                                if not all_ends: # make rudimentary ends if missing
                                    all_ends = [s + 0.1 for s in all_starts]
                                
                                current_char_idx = 0
                                total_chars = len(all_chars)
                                
                                for item in data["sub_segments"]:
                                    text = item.get("original", "") or item.get("tts", "") or item.get("text", "")
                                    if not text: continue
                                    seg_len = len(text)
                                    
                                    if current_char_idx + seg_len > total_chars:
                                        if current_char_idx < total_chars:
                                            seg_len = total_chars - current_char_idx
                                        else:
                                            break
                                            
                                    s = all_starts[current_char_idx]
                                    e = all_ends[current_char_idx + seg_len - 1]
                                    
                                    sub_timing_list.append((s, e, text))
                                    current_char_idx += seg_len
                                    
                                self.log_signal.emit(f"   ℹ️ 문자 정렬 데이터로 자막 {len(sub_timing_list)}개 매핑 성공")
                    elif isinstance(data, list):
                         for item in data:
                             if isinstance(item, dict):
                                 s = float(item.get('start', 0))
                                 e = float(item.get('end', 0))
                                 t = item.get('text', "")
                                 sub_timing_list.append((s, e, t))

                    self.log_signal.emit(f"   ℹ️ JSON 자막 로드 성공 ({len(sub_timing_list)}개)")
                except Exception as e:
                    self.log_signal.emit(f"   ⚠️ JSON 로드 실패: {e}")
            
            if not sub_timing_list and self.subtitle_data:
                count = len(self.subtitle_data)
                seg_len = audio_duration / count
                for i, txt in enumerate(self.subtitle_data):
                    s = i * seg_len
                    e = (i+1) * seg_len
                    sub_timing_list.append((s, e, txt))
            
            temp_files = []
            subtitle_inputs = [] 
            TARGET_W, TARGET_H = 1920, 1080 
            
            if sub_timing_list:
                # Use unique temp_dir
                pass
                os.makedirs(temp_dir, exist_ok=True)
                
                for idx, (start_t, end_t, text) in enumerate(sub_timing_list):
                    if start_t >= audio_duration: continue
                    real_end = min(end_t, audio_duration)
                    
                    if real_end <= start_t:
                        real_end = min(start_t + 3.0, audio_duration)
                        
                    if real_end <= start_t: continue

                    if idx < len(sub_timing_list) - 1:
                        next_start = sub_timing_list[idx+1][0]
                        if 0 < (next_start - real_end) < 0.5:
                            real_end = next_start
                    else:
                        real_end = audio_duration
                    
                    rgba_arr = self.create_text_image(text, (TARGET_W, TARGET_H))
                    
                    sub_filename = f"dub_sub_{idx}.png"
                    sub_path = os.path.join(temp_dir, sub_filename)
                    
                    result_img = Image.fromarray(rgba_arr, 'RGBA')
                    result_img.save(sub_path)
                    
                    temp_files.append(sub_path)
                    subtitle_inputs.append((sub_path, start_t, real_end))

                self.log_signal.emit(f"   📝 자막 이미지 {len(subtitle_inputs)}장 생성 완료")
            else:
                self.log_signal.emit("   ℹ️ 적용할 자막이 없습니다.")

            command = [ffmpeg_exe]
            command.append("-y")
            
            command.extend(["-stream_loop", "-1"])
            command.extend(["-i", self.video_path]) # [0:v]
            
            command.extend(["-i", self.audio_path]) # [1:a]
            
            for s_path, _, _ in subtitle_inputs:
                command.extend(["-i", s_path])
                
            filter_complex = ""
            
            filter_complex += f"[0:v]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=30[v_bg];"
            
            last_v = "[v_bg]"
            for i, (_, start_t, end_t) in enumerate(subtitle_inputs):
                sub_idx = i + 2
                next_v = f"[v_sub{i}]"
                filter_complex += f"{last_v}[{sub_idx}:v]overlay=enable='gte(t,{start_t:.3f})*lt(t,{end_t:.3f})'{next_v};"
                last_v = next_v
            
            vol_val = self.volume
            filter_complex += f"[1:a]volume={vol_val},aresample=48000:async=1[a_out]"
            
            command.extend(["-filter_complex", filter_complex])
            command.extend(["-map", last_v, "-map", "[a_out]"])
            
            command.extend(["-t", f"{audio_duration:.3f}"])
            
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            temp_output = self.output_path + f".temp_{int(time.time())}.mp4"
            command.extend([temp_output])
            
            self.log_signal.emit(f"💾 최종 인코딩 시작 (Native FFmpeg)...")
            
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                encoding='utf-8',
                creationflags=creation_flags
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.error.emit(f"❌ FFmpeg 오류: {stderr}")
                if os.path.exists(temp_output):
                    try: os.remove(temp_output)
                    except: pass
                return
            
            try:
                if os.path.exists(self.output_path):
                    os.remove(self.output_path)
                os.rename(temp_output, self.output_path)
                self.log_signal.emit(f"✅ 파일 덮어쓰기 완료: {os.path.basename(self.output_path)}")
            except Exception as e:
                self.error.emit(f"❌ 파일 교체 실패: {e}")
                return
            
            # Clean up temp subs
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except: pass

            elapsed = time.time() - start_time
            self.finished.emit(f"✅ 작업 완료: {os.path.basename(self.output_path)}", elapsed)
            
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")
            traceback.print_exc()
            # Cleanup
            try:
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except: pass

class BatchDubbingWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, input_dir, style=None, volume=1.0):
        super().__init__()
        self.input_dir = input_dir
        self.style = style
        self.volume = volume

    def run(self):
        start_time = time.time()
        try:
            output_dir = os.path.join(self.input_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            
            if not os.path.exists(self.input_dir):
                 self.error.emit("작업 폴더가 존재하지 않습니다.")
                 return

            all_files = os.listdir(self.input_dir)
            video_files = [f for f in all_files if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov'))]
            
            video_files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)])
            
            if not video_files:
                self.error.emit("작업 폴더에 동영상 파일이 없습니다.")
                return

            total = len(video_files)
            success_count = 0
            
            self.log_signal.emit(f"📂 폴더: {self.input_dir}")
            self.log_signal.emit(f"📂 출력: {output_dir}")
            self.log_signal.emit(f"🔢 총 {total}개의 동영상 발견. 처리 시작...")

            for idx, vid_name in enumerate(video_files):
                base_name = os.path.splitext(vid_name)[0]
                
                video_path = os.path.join(self.input_dir, vid_name)
                audio_path = os.path.join(self.input_dir, base_name + ".mp3")
                output_path = os.path.join(output_dir, vid_name)

                if not os.path.exists(audio_path):
                    self.log_signal.emit(f"⚠️ [{idx+1}/{total}] mp3 없음, 건너뜀: {vid_name}")
                    continue
                
                self.log_signal.emit(f"▶ [{idx+1}/{total}] 처리 중: {vid_name}")

                worker = VideoDubbingWorker(video_path, audio_path, output_path, subtitles=None, style=self.style, volume=self.volume)
                worker.log_signal.connect(self.log_signal.emit)
                
                try:
                    worker.run()
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        success_count += 1
                except Exception as ex:
                    self.log_signal.emit(f"   ❌ 실행 오류: {ex}")
            
            elapsed = time.time() - start_time
            self.finished.emit(f"일괄 작업 완료: {success_count}/{len(video_files)} 성공", elapsed)

        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")

class VideoConcatenatorWorkerOld(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, video_dir, output_file, watermark_path=None):
        super().__init__()
        self.video_dir = video_dir
        self.output_file = output_file
        self.watermark_path = watermark_path

    def run(self):
        start_time = time.time()
        try:
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = "ffmpeg"

            files = [f for f in os.listdir(self.video_dir) if f.lower().endswith('.mp4')]
            
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower()
                        for text in re.split(r'(\d+)', s)]
            
            files.sort(key=natural_sort_key)

            if not files:
                self.error.emit("❌ 합칠 MP4 파일이 없습니다.")
                return

            self.log_signal.emit(f"🚀 총 {len(files)}개의 영상 합치기를 시작합니다 (Native FFmpeg)...")
            if self.watermark_path:
                self.log_signal.emit(f"   🖼️ 워터마크 적용: {os.path.basename(self.watermark_path)}")
            
            command = [ffmpeg_exe]
            
            for f in files:
                path = os.path.join(self.video_dir, f).replace("\\", "/")
                command.extend(["-i", path])
            
            watermark_idx = -1
            if self.watermark_path and os.path.exists(self.watermark_path):
                command.extend(["-i", self.watermark_path])
                watermark_idx = len(files)

            filter_complex = ""
            
            for i in range(len(files)):
                filter_complex += (f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                                   f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=30[v{i}];")
                
                filter_complex += f"[{i}:a]aresample=48000:async=1[a{i}];"
                
            gap_duration = 0.2
            concat_inputs = []
            
            for i in range(len(files)):
                v_source = f"[v{i}]"
                a_source = f"[a{i}]"
                
                if i < len(files) - 1:
                     pad_v_label = f"[v{i}_pad]"
                     pad_a_label = f"[a{i}_pad]"
                     
                     filter_complex += (f"{v_source}tpad=stop_mode=clone:stop_duration={gap_duration}{pad_v_label};"
                                        f"{a_source}apad=pad_dur={gap_duration}{pad_a_label};")
                     
                     concat_inputs.append(pad_v_label)
                     concat_inputs.append(pad_a_label)
                else:
                     concat_inputs.append(v_source)
                     concat_inputs.append(a_source)
            
            for label in concat_inputs:
                filter_complex += label
            
            filter_complex += f"concat=n={len(files)}:v=1:a=1[v_concat][out_a];"
            
            final_v_label = "[v_concat]"
            if watermark_idx != -1:
                filter_complex += f"[{watermark_idx}:v]scale=100:-1[wm];"
                filter_complex += f"[v_concat][wm]overlay=20:20[v_final]"
                final_v_label = "[v_final]"
            
            if filter_complex.endswith(";"): 
                filter_complex = filter_complex[:-1]

            command.extend(["-filter_complex", filter_complex])
            command.extend(["-map", final_v_label, "-map", "[out_a]"])
            
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            
            command.extend(["-y", self.output_file])
            
            self.log_signal.emit(f"   FFmpeg 프로세스 실행 중... (시간이 조금 걸릴 수 있습니다)")
            
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = 0x08000000
                
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                encoding='utf-8',
                creationflags=creation_flags
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.error.emit(f"❌ FFmpeg 오류: {stderr}")
                return

            elapsed = time.time() - start_time
            self.finished.emit(f"✅ 최종 영상 합치기 완료: {os.path.basename(self.output_file)} (Native)", elapsed)

        except Exception as e:
            self.error.emit(f"❌ 합치기 오류: {e}")
            traceback.print_exc()
