# -*- coding: utf-8 -*-
from elevenlabs_client import ElevenLabsClient # Import early to avoid mysql-connector/PyQt5 conflict
import sys
import time
import re
import collections
import os
import base64
import subprocess
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                             QPushButton, QLabel, QFileDialog, QHBoxLayout, 
                             QTabWidget, QComboBox, QSlider, QSpinBox, QGroupBox, QDoubleSpinBox, QFormLayout, QLineEdit, QGridLayout, QCheckBox, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QRect, QRectF
from PyQt5.QtGui import QPalette, QColor, QFont, QImage, QPainter, QPen, QBrush, QPixmap
import threading
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import moviepy.editor as mpe

class GenSparkMultiTabWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str) 
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, file_path, items, driver, custom_target_dir=None):
        super().__init__()
        self.file_path = file_path
        self.items = items
        self.driver = driver # 이미 열려있는 드라이버 사용
        
        if custom_target_dir:
            self.target_dir = custom_target_dir
        else:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            self.target_dir = os.path.join(r"D:\ai\image", base_name)
            
        os.makedirs(self.target_dir, exist_ok=True)

    def run(self):
        start_timestamp = time.time()
        try:
            if len(self.driver.window_handles) < 2:
                self.error.emit("❌ 오류: 브라우저 탭이 2개 미만입니다. 탭을 추가해주세요.")
                return

            tabs = self.driver.window_handles[:2]
            wait = WebDriverWait(self.driver, 20)

            total = len(self.items)
            tab_status = {tabs[0]: None, tabs[1]: None}
            tab_old_srcs = {tabs[0]: [], tabs[1]: []}
            
            processed_count = 0
            item_idx = 0
            failed_items = []

            while processed_count < total:
                for tab in tabs:
                    self.driver.switch_to.window(tab)
                    
                    if tab_status[tab] is None and item_idx < total:
                        current_item = self.items[item_idx]
                        num, prompt = current_item
                        self.log_signal.emit(f"▶ [탭 {tabs.index(tab)+1}] {num}번 생성 시작...")
                        
                        tab_old_srcs[tab] = self.driver.execute_script("return Array.from(document.querySelectorAll('img')).map(img => img.src);")
                        
                        input_box = wait.until(EC.element_to_be_clickable((By.TAG_NAME, "textarea")))
                        input_box.click()
                        input_box.send_keys(Keys.CONTROL + "a")
                        input_box.send_keys(Keys.DELETE)
                        input_box.send_keys(prompt.strip())
                        time.sleep(1)
                        input_box.send_keys(Keys.ENTER)
                        
                        tab_status[tab] = {"item": current_item, "start_time": time.time()}
                        item_idx += 1
                        self.progress.emit(f"진행: {processed_count}/{total}")

                    elif tab_status[tab] is not None:
                        target_num = tab_status[tab]["item"][0]
                        img_data = self.check_image_once(self.driver, tab_old_srcs[tab])
                        
                        if img_data:
                            save_path = os.path.join(self.target_dir, f"{target_num}.png")
                            with open(save_path, "wb") as f:
                                f.write(base64.b64decode(img_data))
                            self.log_signal.emit(f"  ✅ [탭 {tabs.index(tab)+1}] {target_num}번 저장 완료")
                            tab_status[tab] = None
                            processed_count += 1
                        
                        elif time.time() - tab_status[tab]["start_time"] > 220: # 타임아웃 약간 상향
                            self.log_signal.emit(f"  ❌ [탭 {tabs.index(tab)+1}] {target_num}번 타임아웃")
                            failed_items.append(tab_status[tab]["item"])
                            tab_status[tab] = None
                            processed_count += 1
                
                time.sleep(3)

            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))

    def check_image_once(self, driver, old_srcs):
        script = r"""
            var old = arguments[0];
            var imgs = document.querySelectorAll('img');
            for (var i = imgs.length - 1; i >= 0; i--) {
                var img = imgs[i];
                if (!old.includes(img.src) && img.naturalWidth >= 600 && !img.src.includes('banana') && img.complete) {
                    var canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').replace(/^data:image\/png;base64,/, "");
                }
            }
            return null;
        """
        return driver.execute_script(script, old_srcs)

class VideoMergerWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, image_dir, audio_dir, output_dir, subtitles=None, style=None):
        super().__init__()
        self.image_dir = image_dir
        self.audio_dir = audio_dir
        self.output_dir = output_dir
        self.subtitles = subtitles
        self.style = style
        os.makedirs(self.output_dir, exist_ok=True)

    def run(self):
        start_time = time.time()
        try:
            # 이미지 파일 리스트 (.jpg, .png, .jpeg)
            img_files = [f for f in os.listdir(self.image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            
            success_count = 0
            total = len(img_files)

            if total == 0:
                self.error.emit("❌ 이미지 폴더가 비어있습니다.")
                return

            for i, img_name in enumerate(img_files):
                base_name = os.path.splitext(img_name)[0] # 예: "1"
                
                # 대응하는 오디오 파일 찾기 (.mp3)
                audio_name = base_name + ".mp3"
                audio_path = os.path.join(self.audio_dir, audio_name)
                
                if not os.path.exists(audio_path):
                    self.log_signal.emit(f"⚠️ 오디오 없음 스킵: {audio_name}")
                    continue
                
                img_path = os.path.join(self.image_dir, img_name)
                output_path = os.path.join(self.output_dir, base_name + ".mp4")
                
                try:
                    self.log_signal.emit(f"🎬 합성 중 ({i+1}/{total}): {base_name}.mp4")
                    
                    audio_clip = mpe.AudioFileClip(audio_path)
                    duration = audio_clip.duration
                    
                    # 1. 배경 이미지 클립
                    image_clip = mpe.ImageClip(img_path).set_duration(duration)
                    
                    # 2. 자막 처리 (있는 경우)
                    final_clip = image_clip
                    if self.subtitles and base_name in self.subtitles:
                        sub_list = self.subtitles[base_name]
                        num_subs = len(sub_list)
                        sub_duration = duration / num_subs
                        
                        subtitle_clips = []
                        for idx, text in enumerate(sub_list):
                            # QImage로 텍스트 이미지 생성 -> ImageClip
                            txt_img = self.create_text_image(text, image_clip.size)
                            txt_clip = mpe.ImageClip(txt_img).set_duration(sub_duration).set_start(idx * sub_duration).set_position(('center', 'center')) # 'bottom' 대신 일단 center 테스트
                            subtitle_clips.append(txt_clip)
                        
                        final_clip = mpe.CompositeVideoClip([image_clip] + subtitle_clips)
                    
                    video = final_clip.set_audio(audio_clip)
                    video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", logger=None)
                    
                    # 메모리 해제
                    audio_clip.close()
                    image_clip.close()
                    if final_clip != image_clip:
                        final_clip.close()
                    
                    success_count += 1
                except Exception as e:
                    self.log_signal.emit(f"❌ 합성 실패 ({base_name}): {e}")

            elapsed = time.time() - start_time
            result_msg = f"영상 합성 완료 (성공 {success_count} / 총 {total})"
            self.finished.emit(result_msg, elapsed)

        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")

    def create_text_image(self, text, size):
        # PyQt의 QImage/QPainter 사용
        width, height = size
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # 폰트 설정
        font = QFont(self.style['font_family'], self.style['font_size'])
        font.setBold(True)
        painter.setFont(font)
        
        # 텍스트 레이아웃 (중아 하단)
        # 넉넉한 렉트 확보
        full_rect = Qt.QRect(20, 0, width - 40, height - 50)
        
        # 배경/테두리/글자 그리기
        # 1. 배경 (Transparent가 아닐 때만)
        if self.style['bg_color'] != "Transparent":
            # 실제 텍스트 크기 측정
            text_rect = painter.boundingRect(full_rect, Qt.AlignCenter | Qt.AlignBottom | Qt.TextWordWrap, text)
            painter.setBrush(QBrush(QColor(self.style['bg_color'])))
            painter.setPen(Qt.NoPen)
            painter.drawRect(text_rect.adjusted(-10, -5, 10, 5))

        # 2. 테두리 (Shadow/Outline)
        if self.style['outline_color']:
            painter.setPen(QColor(self.style['outline_color']))
            for dx, dy in [(-2,-2), (2,-2), (-2,2), (2,2)]:
                painter.drawText(full_rect.translated(dx, dy), Qt.AlignCenter | Qt.AlignBottom | Qt.TextWordWrap, text)

        # 3. 본문 글자
        painter.setPen(QColor(self.style['text_color']))
        painter.drawText(full_rect, Qt.AlignCenter | Qt.AlignBottom | Qt.TextWordWrap, text)
        
        painter.end()
        
        # QImage -> Numpy Array
        image = image.convertToFormat(QImage.Format_RGB888)
        width = image.width()
        height = image.height()
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        import numpy as np
        return np.frombuffer(ptr, np.uint8).reshape((height, width, 3))

class MainApp(QWidget):
    # Signals must be class variables
    log_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    enable_button_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.driver = None
        self.start_time = 0
        self.loaded_items = []
        self.current_file_path = ""
        self.initUI()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_timer_display)

    def initUI(self):
        self.setWindowTitle("GenSpark 2-Tab 수동설정 매니저")
        self.setGeometry(300, 300, 550, 750)
        layout = QVBoxLayout()

        # 메인 레이아웃을 탭 위젯으로 변경
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 탭 1: GenSpark Image
        self.tab1 = QWidget()
        self.initTab1()
        self.tabs.addTab(self.tab1, "GenSpark Image")

        # 탭 2: ElevenLabs TTS
        self.tab2 = QWidget()
        self.initTab2()
        self.tabs.addTab(self.tab2, "ElevenLabs TTS")

        # 탭 3: Video Composite
        self.tab3 = QWidget()
        self.initTab3()
        self.tabs.addTab(self.tab3, "Video Composite")

        self.setLayout(layout)

    def initTab1(self):
        layout = QVBoxLayout()

        self.status_label = QLabel("1단계: 브라우저를 먼저 준비해 주세요.")
        self.status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.status_label)

        self.timer_label = QLabel("소요 시간: 00:00:00")
        layout.addWidget(self.timer_label)

        # 저장 경로 설정
        path_layout = QHBoxLayout()
        self.image_path_edit = QLineEdit(r"D:\ai\image")
        self.image_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_image = QPushButton("찾아보기")
        btn_browse_image.clicked.connect(self.browse_image_path)
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.image_path_edit)
        path_layout.addWidget(btn_browse_image)
        layout.addLayout(path_layout)

        # 버튼들
        self.btn_prepare = QPushButton("🌐 1. 브라우저 및 탭 준비 (설정용)")
        self.btn_prepare.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 10px;")
        self.btn_prepare.clicked.connect(self.launch_browser_and_tabs)
        layout.addWidget(self.btn_prepare)

        # 텍스트 입력창 추가
        layout.addWidget(QLabel("이미지 프롬프트 입력:"))
        self.image_prompt_input = QTextEdit()
        self.image_prompt_input.setPlaceholderText("1. {프롬프트내용}\n2. {프롬프트내용}\n형식으로 입력하세요.")
        self.image_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.image_prompt_input)

        btn_h_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 이미지 생성 시작")
        self.btn_start.setEnabled(True)
        self.btn_start.setStyleSheet("""
            QPushButton { height: 60px; font-weight: bold; background-color: #28a745; color: white; border-radius: 10px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_start.clicked.connect(self.start_automation)
        
        btn_h_layout.addWidget(self.btn_start)
        layout.addLayout(btn_h_layout)

        # 압축 버튼 추가
        self.btn_compress = QPushButton("🗜️ 4. 이미지 압축 (용량 줄이기)")
        self.btn_compress.setStyleSheet("height: 40px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 10px; margin-top: 5px;")
        self.btn_compress.clicked.connect(self.compress_images)
        layout.addWidget(self.btn_compress)

        # 로그 디스플레이 (하단으로 이동)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        self.log_display.setMaximumHeight(150) # 조금 더 여유 있게
        layout.addWidget(self.log_display)

        self.tab1.setLayout(layout)

    def initTab2(self):
        layout = QVBoxLayout()
        
        # API 초기화 (파일 경로 없음)
        try:
            self.tts_client = ElevenLabsClient()
            self.api_keys = self.tts_client.get_api_keys()
            self.voices = self.tts_client.get_voices()
            self.models = self.tts_client.get_models()
        except Exception as e:
            layout.addWidget(QLabel(f"API/DB 초기화 오류: {e}"))
            self.tab2.setLayout(layout)
            return


        # 저장 경로 설정
        path_layout = QHBoxLayout()
        self.audio_path_edit = QLineEdit(r"D:\ai\audio")
        self.audio_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_audio = QPushButton("찾아보기")
        btn_browse_audio.clicked.connect(self.browse_audio_path)
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.audio_path_edit)
        path_layout.addWidget(btn_browse_audio)
        layout.addLayout(path_layout)

        # 설정 그룹
        settings_group = QGroupBox("TTS 설정")
        form_layout = QFormLayout()

        # API Key 선택
        self.combo_apikey = QComboBox()
        for k in self.api_keys:
            self.combo_apikey.addItem(k['name'], k['api_key']) # name displayed, api_key as data
        
        # 기본 선택된 키 설정
        if self.api_keys:
            self.tts_client.set_api_key(self.api_keys[0]['api_key'])
            
        self.combo_apikey.currentIndexChanged.connect(self.on_apikey_changed)
        form_layout.addRow("API Key:", self.combo_apikey)

        # 성우 선택
        self.combo_voice = QComboBox()
        for v in self.voices:
            self.combo_voice.addItem(f"{v['name']}", v['voice_id'])
        form_layout.addRow("성우 (Voice):", self.combo_voice)

        # 모델 선택
        self.combo_model = QComboBox()
        for m in self.models:
            self.combo_model.addItem(m['name'], m['model_id'])
        form_layout.addRow("모델 (Model):", self.combo_model)

        # 설정 슬라이더들
        self.slider_stability = self.create_slider(0, 100, 50) # 0.5
        form_layout.addRow("안정성 (Stability):", self.slider_stability)

        self.slider_similarity = self.create_slider(0, 100, 75) # 0.75
        form_layout.addRow("유사성 (Similarity):", self.slider_similarity)
        
        self.slider_style = self.create_slider(0, 100, 0) # 0.0
        form_layout.addRow("스타일 (Style Exaggeration):", self.slider_style)

        settings_group.setLayout(form_layout)
        layout.addWidget(settings_group)

        # 생성 버튼
        self.btn_generate_tts = QPushButton("🔊 오디오 생성 (Generate Audio)")
        self.btn_generate_tts.setStyleSheet("height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 10px;")
        self.btn_generate_tts.clicked.connect(self.generate_audio)
        layout.addWidget(self.btn_generate_tts)

        # 텍스트 입력
        layout.addWidget(QLabel("입력 텍스트:"))
        self.tts_input = QTextEdit()
        self.tts_input.setPlaceholderText("변환할 텍스트를 입력하세요...")
        layout.addWidget(self.tts_input)

        # 로그
        self.tts_log = QTextEdit()
        self.tts_log.setReadOnly(True)
        self.tts_log.setMaximumHeight(100)
        layout.addWidget(self.tts_log)

        self.tab2.setLayout(layout)

        # Connect signals for thread safety (AFTER UI creation)
        self.log_signal.connect(self.tts_log.append)
        self.enable_button_signal.connect(self.set_btn_enable)
        self.error_signal.connect(self.tts_log.append)

    def initTab3(self):
        layout = QVBoxLayout()

        # 상단 통합 작업 폴더 선택
        workspace_layout = QHBoxLayout()
        self.video_workspace_path = QLineEdit(r"D:\ai")
        btn_workspace = QPushButton("폴더 선택")
        btn_workspace.clicked.connect(lambda: self.browse_folder(self.video_workspace_path))
        workspace_layout.addWidget(QLabel("작업 폴더 (Image/Audio 가 있는 곳):"))
        workspace_layout.addWidget(self.video_workspace_path)
        workspace_layout.addWidget(btn_workspace)
        layout.addLayout(workspace_layout)

        # 스타일 설정 그룹
        style_group = QGroupBox("자막 스타일 설정")
        style_layout = QGridLayout()
        
        self.chk_use_sub = QCheckBox("자막 사용")
        self.chk_use_sub.setChecked(True)
        style_layout.addWidget(self.chk_use_sub, 0, 0)

        # 폰트
        self.combo_font = QComboBox()
        self.combo_font.addItems(["GmarketSansTTFBold", "NanumSquareRoundEB", "ChosunKm", "CulturalB", "Hakgyoansim_PosterB", "KCC-Ganpan", "Malgun Gothic"])
        style_layout.addWidget(QLabel("폰트:"), 0, 1)
        style_layout.addWidget(self.combo_font, 0, 2)

        # 크기
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 200)
        self.spin_font_size.setValue(60)
        style_layout.addWidget(QLabel("크기:"), 0, 3)
        style_layout.addWidget(self.spin_font_size, 0, 4)

        # 색상들
        self.color_text = "white"
        self.color_outline = "black"
        self.color_bg = "Transparent"

        btn_color_txt = QPushButton("글자색")
        btn_color_txt.clicked.connect(lambda: self.pick_color('text'))
        style_layout.addWidget(btn_color_txt, 1, 0)

        btn_color_out = QPushButton("테두리색")
        btn_color_out.clicked.connect(lambda: self.pick_color('outline'))
        style_layout.addWidget(btn_color_out, 1, 1)

        btn_color_bg = QPushButton("배경색")
        btn_color_bg.clicked.connect(lambda: self.pick_color('bg'))
        style_layout.addWidget(btn_color_bg, 1, 2)

        style_group.setLayout(style_layout)
        layout.addWidget(style_group)

        # 자막 입력란
        layout.addWidget(QLabel("자막 입력 (형식: 1-1 자막내용...):"))
        self.video_sub_input = QTextEdit()
        self.video_sub_input.setPlaceholderText("1-1 첫번째 자막\n1-2 두번째 자막\n2-1 다음 영상 자막...")
        layout.addWidget(self.video_sub_input)

        # 시작 버튼
        self.btn_merge_video = QPushButton("🎬 영상 합성 시작 (자막 포함)")
        self.btn_merge_video.setStyleSheet("height: 60px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 10px;")
        self.btn_merge_video.clicked.connect(self.start_video_merge)
        layout.addWidget(self.btn_merge_video)

        # 로그
        self.video_log = QTextEdit()
        self.video_log.setReadOnly(True)
        self.video_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        self.video_log.setMaximumHeight(150)
        layout.addWidget(self.video_log)

        self.tab3.setLayout(layout)

    def pick_color(self, target):
        from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            if target == 'text': self.color_text = hex_color
            elif target == 'outline': self.color_outline = hex_color
            elif target == 'bg': self.color_bg = hex_color

    def parse_subtitles(self, text):
        subs = collections.defaultdict(list)
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            # 1-1 내용 or 1-1. 내용
            match = re.match(r'^(\d+)-\d+\.?\s*(.*)', line)
            if match:
                major_id = match.group(1)
                content = match.group(2)
                subs[major_id].append(content)
        return subs

    def browse_folder(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if path:
            line_edit.setText(path)

    def start_video_merge(self):
        workspace = self.video_workspace_path.text().strip()
        img_dir = workspace
        audio_dir = workspace
        out_dir = workspace

        if not os.path.exists(workspace):
            self.video_log.append(f"❌ 폴더가 존재하지 않습니다: {workspace}")
            return

        # 자막 파싱
        subtitles = None
        if self.chk_use_sub.isChecked():
            subtitles = self.parse_subtitles(self.video_sub_input.toPlainText())

        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg
        }

        self.btn_merge_video.setEnabled(False)
        self.video_log.append("⏳ 영상 합성 작업을 시작합니다...")

        self.merger_worker = VideoMergerWorker(img_dir, audio_dir, out_dir, subtitles, style)
        self.merger_worker.log_signal.connect(self.video_log.append)
        self.merger_worker.finished.connect(self.on_video_merge_finished)
        self.merger_worker.error.connect(lambda e: self.video_log.append(f"❌ 오류: {e}"))
        self.merger_worker.start()


    def on_video_merge_finished(self, msg, elapsed):
        self.btn_merge_video.setEnabled(True)
        h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
        self.video_log.append(f"✅ {msg} (소요 시간: {h:02d}:{m:02d}:{s:02d})")

    def create_slider(self, min_val, max_val, default):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        return slider

    def on_apikey_changed(self, index):
        api_key = self.combo_apikey.currentData()
        if api_key:
            self.tts_client.set_api_key(api_key)
            self.tts_log.append(f"ℹ️ API Key 변경됨: {self.combo_apikey.currentText()}")

    def generate_audio(self):
        text = self.tts_input.toPlainText().strip()
        if not text:
            self.tts_log.append("❌ 텍스트를 입력하세요.")
            return

        voice_id = self.combo_voice.currentData()
        model_id = self.combo_model.currentData()
        stability = self.slider_stability.value() / 100.0
        similarity = self.slider_similarity.value() / 100.0
        style = self.slider_style.value() / 100.0

        # 파싱 로직: 그룹별로 텍스트 묶기
        tasks = []
        
        # 1. 1-1, 1-2 패턴 확인
        lines = text.split('\n')
        groups = collections.defaultdict(list)
        has_pattern = False
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # 정규식: "숫자-숫자 텍스트" (예: "1-1 내용")
            # 숫자 뒤에 대시, 숫자, 그리고 공백이 있어야 함
            match = re.match(r'^(\d+)-\d+\s+(.*)', line)
            if match:
                has_pattern = True
                major_id = match.group(1) # "1"
                content = match.group(2) # "내용"
                groups[major_id].append(content)
        
        if has_pattern:
            for major_id, contents in groups.items():
                combined_text = " ".join(contents)
                if combined_text:
                    filename = f"{major_id}.mp3"
                    tasks.append((combined_text, filename))
            self.tts_log.append(f"📋 배치 모드 감지: {len(tasks)}개의 파일 생성 예정")
        else:
            # 패턴 없으면 전체 텍스트를 하나로 생성 (UUID 파일명)
            tasks.append((text, None))

        self.btn_generate_tts.setEnabled(False)
        self.tts_log.append("⏳ 생성 시작...")

        # 스레드로 실행 (tasks 리스트 전달)
        audio_target = self.audio_path_edit.text().strip()
        threading.Thread(target=self._run_tts_thread, args=(tasks, voice_id, model_id, stability, similarity, style, audio_target), daemon=True).start()

    def _run_tts_thread(self, tasks, voice_id, model_id, stability, similarity, style, custom_dir):
        success_count = 0
        try:
            for text_chunk, filename in tasks:
                try:
                    save_path = self.tts_client.generate_audio(
                        text=text_chunk, 
                        voice_id=voice_id, 
                        model_id=model_id,
                        stability=stability,
                        similarity_boost=similarity,
                        style=style,
                        filename=filename,
                        custom_dir=custom_dir
                    )
                    self.log_signal.emit(f"✅ 생성 완료: {os.path.basename(save_path)}")
                    success_count += 1
                except Exception as e:
                    self.log_signal.emit(f"❌ 생성 실패 ({filename}): {e}")
            
            self.log_signal.emit(f"🎉 전체 작업 완료 ({success_count}/{len(tasks)})")
            
        except Exception as e:
            self.error_signal.emit(f"❌ 치명적 오류: {e}")
        finally:
            # 버튼 활성화는 시그널로 처리해야 안전하지만, 여기선 간단히
            # 실제로는 시그널을 통해 메인 스레드에서 처리하는 것이 좋음.
            # self.btn_generate_tts.setEnabled(True) -> UI 스레드 접근 위반 가능성
            # 여기서는 log_signal을 통해 간접적으로 알림.
            self.enable_button_signal.emit(True)
            
    # 버튼 활성화를 위한 시그널 연결이 필요할 수 있음. 
    # 기존 코드 구조상 finished 시그널을 활용하거나 log_signal에 의존.
    # 안전하게 하기 위해 버튼 활성화 메서드 추가
            
    def set_btn_enable(self, enabled):
        self.btn_generate_tts.setEnabled(enabled)

    def launch_browser_and_tabs(self):
        try:
            self.log_display.append("🌐 브라우저를 실행합니다...")
            chrome_cmd = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            if not os.path.exists(chrome_cmd):
                self.log_display.append(f"❌ 크롬 실행 파일을 찾을 수 없습니다: {chrome_cmd}")
                return

            user_data = r'C:\sel_chrome'
            target_url = "https://www.genspark.ai/agents?type=moa_generate_image"
            if not os.path.exists(user_data): os.makedirs(user_data)
            subprocess.Popen([chrome_cmd, '--remote-debugging-port=9222', f'--user-data-dir={user_data}', target_url])
            
            time.sleep(3) # 브라우저 뜨는 대기 시간
            opt = Options()
            opt.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
            
            # 2번째 탭 생성
            if len(self.driver.window_handles) < 2:
                self.driver.execute_script(f"window.open('{target_url}');")
                self.log_display.append("✅ 2번째 탭을 생성했습니다.")
            
            self.log_display.append("💡 각 탭에서 [이미지 비율] 등을 설정한 후 파일을 불러오세요.")
            self.status_label.setText("상태: 브라우저 준비됨. 설정을 마치고 파일을 불러오세요.")
            self.btn_prepare.setEnabled(False) # 한 번 실행 후 비활성화
        except Exception as e:
            self.log_display.append(f"❌ 브라우저 실행 실패: {e}")

    def browse_image_path(self):
        path = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if path:
            self.image_path_edit.setText(path)

    def browse_audio_path(self):
        path = QFileDialog.getExistingDirectory(self, "오디오 저장 폴더 선택")
        if path:
            self.audio_path_edit.setText(path)

    def update_timer_display(self):
        if self.start_time > 0:
            elapsed = int(time.time() - self.start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self.timer_label.setText(f"소요 시간: {h:02d}:{m:02d}:{s:02d}")

    def start_automation(self):
        if not self.driver:
            self.log_display.append("❌ 브라우저가 준비되지 않았습니다.")
            return
        
        text = self.image_prompt_input.toPlainText().strip()
        if not text:
            self.log_display.append("❌ 입력된 프롬프트가 없습니다.")
            return

        # 프롬프트 파싱: (\d+)\s*\.\s*\{(.*?)\}
        self.loaded_items = re.findall(r'(\d+)\s*\.\s*\{(.*?)\}', text, re.DOTALL)
        
        if not self.loaded_items:
            self.log_display.append("❌ 프롬프트 형식이 올바르지 않습니다 (예: 1. {프롬프트})")
            return

        self.btn_start.setEnabled(False)
        self.start_time = time.time()
        self.ui_timer.start(1000) 
        
        # 가상의 파일 경로 사용
        self.current_file_path = "manual_input_" + time.strftime("%H%M%S")
        
        image_target = self.image_path_edit.text().strip()
        self.worker = GenSparkMultiTabWorker(self.current_file_path, self.loaded_items, self.driver, custom_target_dir=image_target)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.log_signal.connect(lambda m: self.log_display.append(m))
        self.worker.finished.connect(self.on_success)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_success(self, msg, elapsed):
        self.ui_timer.stop()
        self.btn_start.setEnabled(True)
        self.log_display.append(f"🏁 {msg}")
        
        # 생성 완료 후 자동 압축 실행
        if hasattr(self, 'worker') and self.worker.target_dir:
            self.log_display.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
            self.compress_images(dir_path=self.worker.target_dir)

    def on_error(self, err):
        self.ui_timer.stop()
        self.btn_start.setEnabled(True)
        self.log_display.append(f"❗ 오류: {err}")

    def compress_images(self, dir_path=None):
        if not dir_path:
            dir_path = QFileDialog.getExistingDirectory(self, "이미지가 있는 폴더 선택")
            
        if not dir_path:
            return
            
        self.log_display.append(f"📦 압축(JPG 변환) 시작: {dir_path}")
        try:
            count = 0
            saved_size = 0
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    lower_file = file.lower()
                    if lower_file.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.jfif')):
                        full_path = os.path.join(root, file)
                        try:
                            old_size = os.path.getsize(full_path)
                            
                            # 이미지 열기 및 RGB 변환
                            img = Image.open(full_path)
                            rgb_img = img.convert('RGB')
                            
                            # 새 파일 경로 (확장자를 jpg로 변경)
                            file_base = os.path.splitext(full_path)[0]
                            new_path = file_base + ".jpg"
                            
                            # JPG로 저장 (압축률 85%)
                            rgb_img.save(new_path, "JPEG", optimize=True, quality=85)
                            
                            new_size = os.path.getsize(new_path)
                            saved_size += (old_size - new_size)
                            count += 1
                            
                            # 원본이 jpg가 아니었고, 파일명이 달라졌다면 원본 삭제
                            if full_path != new_path:
                                os.remove(full_path)
                                
                        except Exception as e:
                            self.log_display.append(f"  ❌ {file} 실패: {e}")
                            
            mb_saved = saved_size / (1024 * 1024)
            self.log_display.append(f"✅ 변환 완료: {count}개 파일 처리됨.")
            self.log_display.append(f"📉 총 절약 용량: {mb_saved:.2f} MB")
            
        except Exception as e:
            self.log_display.append(f"❌ 압축 중 오류: {e}")

    def closeEvent(self, event):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 다크 테마 적용
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    ex = MainApp()
    ex.show()
    sys.exit(app.exec_())