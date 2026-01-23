import sys
import requests
import subprocess
import os
import collections
import base64
import ftplib
import traceback
import webbrowser  # Added for opening URLs
try:
    from elevenlabs_client import ElevenLabsClient # Import early to avoid mysql-connector/PyQt5 conflict
except ImportError:
    pass
import time
import re
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                             QPushButton, QLabel, QFileDialog, QHBoxLayout, 
                             QTabWidget, QComboBox, QSlider, QSpinBox, QGroupBox, QDoubleSpinBox, 
                             QFormLayout, QLineEdit, QGridLayout, QCheckBox, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStackedWidget,
                             QSizePolicy)
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QRect, QRectF
from PyQt5.QtGui import (QPalette, QColor, QFont, QImage, QPainter, QPen, QBrush, QPixmap, QFontDatabase, QFontInfo, 
                         QPainterPath, QTextDocument, QAbstractTextDocumentLayout, QLinearGradient, QRadialGradient, QFontMetrics)
import threading
import concurrent.futures
import multiprocessing
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
# Monkey Patch for Pillow > 9.x not having ANTIALIAS, which MoviePy needs
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS


import moviepy.editor as mpe
from youtube_workers import YoutubeSearchWorker, ImageLoadWorker


from youtube_worker_ai import GenSparkMultiTabWorker, ImageFXMultiTabWorker, GeminiAPIImageWorker
from youtube_worker_video import VideoMergerWorker, SingleVideoWorker, VideoDubbingWorker, BatchDubbingWorker, VideoConcatenatorWorkerOld
from youtube_worker_launcher import BrowserLauncherWorker

class CustomTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        
        # Button Container
        self.btn_container = QWidget()
        self.btn_layout = QGridLayout(self.btn_container)
        self.btn_layout.setContentsMargins(0,0,0,0)
        self.btn_layout.setSpacing(1)
        self.layout.addWidget(self.btn_container)
        
        # Stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("border: 1px solid #444; border-top: none;")
        self.layout.addWidget(self.stack)
        
        self.buttons = []
        
    def addTab(self, widget, title):
        self.stack.addWidget(widget)
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setFixedHeight(40) # 적당한 높이
        btn.clicked.connect(lambda: self.setCurrentIndex(self.stack.indexOf(widget)))
        
        idx = len(self.buttons)
        row = idx // 6
        col = idx % 6
        
        self.btn_layout.addWidget(btn, row, col)
        self.buttons.append(btn)
        
        # 처음 탭을 기본 선택
        if len(self.buttons) == 1:
            self.setCurrentIndex(0)
            
    def setCurrentIndex(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.buttons):
            if i == index:
                btn.setChecked(True)
                # Selected Style
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #444444;
                        color: #ffffff;
                        border: 1px solid #444;
                        font-weight: bold;
                        font-family: 'Malgun Gothic';
                        font-size: 13px;
                    }
                """)
            else:
                btn.setChecked(False)
                # Normal Style
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2b2b2b;
                        color: #b1b1b1;
                        border: 1px solid #444;
                        font-family: 'Malgun Gothic';
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #333333;
                    }
                """)

class MainApp(QWidget):
    # Signals must be class variables
    log_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    enable_button_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.driver = None
        self.start_time_gen = 0

        self.start_time_fx = 0
        self.loaded_items = []
        self.current_file_path = ""
        self.initUI()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_timer_display)

    def initUI(self):
        self.setWindowTitle("YouTube Video Creator Master")
        self.setGeometry(200, 100, 950, 850) # 폭을 약간 늘림 (2단 탭 버튼 대비)
        layout = QVBoxLayout()

        # 메인 레이아웃을 커스텀 탭 위젯으로 변경
        self.tabs = CustomTabWidget()
        layout.addWidget(self.tabs)

        # ========== 1단 (Upper Row) ==========
        
        # 1. GenSpark Image
        self.tab1 = QWidget()
        self.initTab1()
        self.tabs.addTab(self.tab1, "Ganspark Image")

        # 2. ImageFX Image
        self.tab_fx = QWidget()
        self.initTabImageFX()
        self.tabs.addTab(self.tab_fx, "ImageFX Image")

        # 3. Gemini API Image
        self.tab_gemini = QWidget()
        self.initTabGeminiAPI()
        self.tabs.addTab(self.tab_gemini, "Gemini API Image")

        # 3. ElevenLabs TTS
        self.tab2 = QWidget()
        self.initTab2()
        self.tabs.addTab(self.tab2, "ElevenLabs TTS")

        # 4. Video Composite
        self.tab3 = QWidget()
        self.initTab3()
        self.tabs.addTab(self.tab3, "자막설정")

        # 5. Video Dubbing
        self.tab6 = QWidget()
        self.initTab6()
        self.tabs.addTab(self.tab6, "그록동영상")

        # 6. Video Effects
        self.tab5 = QWidget()
        self.initTab5()
        self.tabs.addTab(self.tab5, "영상효과")

        # ========== 2단 (Lower Row) ==========

        # 7. Video Concat
        self.tab4 = QWidget()
        self.initTab4()
        self.tabs.addTab(self.tab4, "최종영상")

        # 8. Audio Transcribe
        self.tab_transcribe = QWidget()
        self.initTabAudioTranscribe()
        self.tabs.addTab(self.tab_transcribe, "Audio Transcribe")

        # 9. Audio To Video
        self.tab_audio_video = QWidget()
        self.initTabAudioToVideo()
        self.tabs.addTab(self.tab_audio_video, "Audio To Video")

        # 10. YouTube 분석
        self.tab7 = QWidget()
        self.initTab7()
        self.tabs.addTab(self.tab7, "YouTube 분석")

        # 11. FTP Upload
        self.tab_ftp = QWidget()
        self.initTabFTP()
        self.tabs.addTab(self.tab_ftp, "FTP Upload")

        # 12. Video List
        self.tab_video_list = QWidget()
        self.initTabVideoList()
        self.tabs.addTab(self.tab_video_list, "영상관리")

        # 13. Prompt
        self.tab_prompt = QWidget()
        self.initTabPrompt()
        self.tabs.addTab(self.tab_prompt, "프롬프트")

        # 14. Gold Price Shorts
        self.tab_gold_price = QWidget()
        self.initTabGoldPrice()
        self.tabs.addTab(self.tab_gold_price, "금시세")



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
        self.image_path_edit = QLineEdit(r"D:\youtube")
        self.image_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_image = QPushButton("찾아보기")
        btn_browse_image.clicked.connect(self.browse_image_path)
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.image_path_edit)
        path_layout.addWidget(btn_browse_image)
        layout.addLayout(path_layout)

        # 버튼들
        self.btn_prepare = QPushButton("🌐 1. 브라우저 및 탭 준비 (설정용)")
        self.btn_prepare.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_prepare.clicked.connect(self.launch_browser_and_tabs)
        layout.addWidget(self.btn_prepare)

        # 텍스트 입력창 추가
        layout.addWidget(QLabel("이미지 프롬프트 입력:"))
        self.image_prompt_input = QTextEdit()
        self.image_prompt_input.setPlaceholderText("프롬프트 내용을 입력하세요.\n1. 프롬프트1\n2. 프롬프트2")
        self.image_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.image_prompt_input)

        btn_h_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 2. 이미지 생성 시작")
        self.btn_start.setEnabled(True)
        self.btn_start.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_start.clicked.connect(self.start_automation)
        
        self.btn_stop = QPushButton("🛑 중지")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_stop.clicked.connect(self.stop_automation)

        btn_h_layout.addWidget(self.btn_start)
        btn_h_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_h_layout)

        # 압축 버튼 추가
        self.btn_compress = QPushButton("🗜️ 3. 이미지 압축 (용량 줄이기)")
        self.btn_compress.setStyleSheet("height: 50px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 8px; margin-top: 5px;")
        self.btn_compress.clicked.connect(self.compress_images)
        layout.addWidget(self.btn_compress)

        # 로그 디스플레이 (하단으로 이동)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        self.log_display.setMaximumHeight(150) # 조금 더 여유 있게
        layout.addWidget(self.log_display)

        self.tab1.setLayout(layout)


    def initTabImageFX(self):
        layout = QVBoxLayout()

        self.fx_status_label = QLabel("1단계: ImageFX 브라우저를 준비해 주세요.")
        self.fx_status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.fx_status_label)

        self.fx_timer_label = QLabel("소요 시간: 00:00:00")
        layout.addWidget(self.fx_timer_label)

        # 저장 경로
        path_layout = QHBoxLayout()
        self.fx_image_path_edit = QLineEdit(r"D:\youtube")
        self.fx_image_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_fx = QPushButton("찾아보기")
        btn_browse_fx.clicked.connect(lambda: self.browse_image_path_custom(self.fx_image_path_edit))
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.fx_image_path_edit)
        path_layout.addWidget(btn_browse_fx)
        layout.addLayout(path_layout)
        
        # 브라우저 준비 버튼
        self.btn_fx_prepare = QPushButton("🌐 1. ImageFX 브라우저 준비")
        self.btn_fx_prepare.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_fx_prepare.clicked.connect(self.launch_browser_imagefx)
        layout.addWidget(self.btn_fx_prepare)
        
        # 프롬프트 입력
        layout.addWidget(QLabel("이미지 프롬프트 입력:"))
        self.fx_prompt_input = QTextEdit()
        self.fx_prompt_input.setPlaceholderText("프롬프트 입력 (예: 1. 고양이)")
        self.fx_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.fx_prompt_input)
        
        # 시작 버튼
        btn_fx_h_layout = QHBoxLayout()
        self.btn_fx_start = QPushButton("🚀 2. ImageFX 생성 시작")
        self.btn_fx_start.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_fx_start.clicked.connect(self.start_automation_imagefx)

        self.btn_fx_stop = QPushButton("🔴 중지")
        self.btn_fx_stop.setEnabled(False)
        self.btn_fx_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #6c757d; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #454d55; color: #aaa; }
        """)
        self.btn_fx_stop.clicked.connect(self.stop_automation_imagefx)

        btn_fx_h_layout.addWidget(self.btn_fx_start)
        btn_fx_h_layout.addWidget(self.btn_fx_stop)
        layout.addLayout(btn_fx_h_layout)
        
        # 압축 버튼
        self.btn_fx_compress = QPushButton("🗜️ 3. 이미지 압축")
        self.btn_fx_compress.setStyleSheet("height: 50px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 8px; margin-top: 5px;")
        self.btn_fx_compress.clicked.connect(lambda: self.compress_images_custom(self.fx_image_path_edit, self.fx_log_display))
        layout.addWidget(self.btn_fx_compress)
        
        # 로그창
        self.fx_log_display = QTextEdit()
        self.fx_log_display.setReadOnly(True)
        self.fx_log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        self.fx_log_display.setMaximumHeight(150)
        layout.addWidget(self.fx_log_display)
        
        self.tab_fx.setLayout(layout)

    def initTab2(self):
        layout = QVBoxLayout()
        
        # 로그 디스플레이 먼저 생성하여 API 오류 시에도 안전하게 로그 출력 가능하게 함
        self.tts_log = QTextEdit()
        self.tts_log.setReadOnly(True)
        self.tts_log.setMaximumHeight(100)

        # API 초기화 (파일 경로 없음)
        try:
            self.tts_client = ElevenLabsClient()
            self.api_keys = self.tts_client.get_api_keys()
            self.voices = self.tts_client.get_voices()
            self.models = self.tts_client.get_models()
        except Exception as e:
            layout.addWidget(QLabel(f"API/DB 초기화 오류: {e}"))
            layout.addWidget(self.tts_log) # 오류 상황에서도 로그창은 보여줌
            self.tab2.setLayout(layout)
            return


        # 저장 경로 설정
        path_layout = QHBoxLayout()
        self.audio_path_edit = QLineEdit(r"D:\youtube")
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
        # 안정성
        self.slider_stability = self.create_slider(0, 100, 50)
        self.lbl_stability = QLabel("0.50")
        self.lbl_stability.setFixedWidth(40)
        self.slider_stability.valueChanged.connect(lambda v: self.lbl_stability.setText(f"{v/100:.2f}"))
        row_stability = QHBoxLayout()
        row_stability.addWidget(self.slider_stability)
        row_stability.addWidget(self.lbl_stability)
        form_layout.addRow("안정성 (Stability):", row_stability)

        # 유사성
        self.slider_similarity = self.create_slider(0, 100, 75)
        self.lbl_similarity = QLabel("0.75")
        self.lbl_similarity.setFixedWidth(40)
        self.slider_similarity.valueChanged.connect(lambda v: self.lbl_similarity.setText(f"{v/100:.2f}"))
        row_similarity = QHBoxLayout()
        row_similarity.addWidget(self.slider_similarity)
        row_similarity.addWidget(self.lbl_similarity)
        form_layout.addRow("유사성 (Similarity):", row_similarity)
        
        # 스타일
        self.slider_style = self.create_slider(0, 100, 0)
        self.lbl_style = QLabel("0.00")
        self.lbl_style.setFixedWidth(40)
        self.slider_style.valueChanged.connect(lambda v: self.lbl_style.setText(f"{v/100:.2f}"))
        row_style = QHBoxLayout()
        row_style.addWidget(self.slider_style)
        row_style.addWidget(self.lbl_style)
        form_layout.addRow("스타일 (Style):", row_style)

        # 음성 속도
        self.slider_speed = self.create_slider(70, 120, 100)
        self.lbl_speed = QLabel("1.00")
        self.lbl_speed.setFixedWidth(40)
        self.slider_speed.valueChanged.connect(lambda v: self.lbl_speed.setText(f"{v/100:.2f}"))
        row_speed = QHBoxLayout()
        row_speed.addWidget(self.slider_speed)
        row_speed.addWidget(self.lbl_speed)
        form_layout.addRow("음성 속도 (Speed):", row_speed)

        # 음성 볼륨 (TTS 생성 시 자체 볼륨)
        self.slider_tts_volume = self.create_slider(0, 300, 100)
        self.lbl_tts_volume = QLabel("100%")
        self.lbl_tts_volume.setFixedWidth(40)
        self.slider_tts_volume.valueChanged.connect(lambda v: self.lbl_tts_volume.setText(f"{v}%"))
        row_tts_vol = QHBoxLayout()
        row_tts_vol.addWidget(self.slider_tts_volume)
        row_tts_vol.addWidget(self.lbl_tts_volume)
        form_layout.addRow("음성 볼륨 (Volume):", row_tts_vol)
        
        # 노이즈 제거용 트리밍
        self.spin_tts_trim = QDoubleSpinBox()
        self.spin_tts_trim.setRange(0.0, 2.0)
        self.spin_tts_trim.setSingleStep(0.05)
        self.spin_tts_trim.setValue(0.0)
        self.spin_tts_trim.setSuffix(" 초")
        form_layout.addRow("잡음 제거 (Trim End):", self.spin_tts_trim)

        settings_group.setLayout(form_layout)
        layout.addWidget(settings_group)

        # 버튼 레이아웃
        btn_layout = QHBoxLayout()

        # 생성 버튼
        self.btn_generate_tts = QPushButton("🔊 오디오 생성 (Generate Audio)")
        self.btn_generate_tts.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 10px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_generate_tts.clicked.connect(self.generate_audio)
        
        # 중지 버튼
        self.btn_stop_tts = QPushButton("🛑 중지 (Stop)")
        self.btn_stop_tts.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 10px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_stop_tts.setEnabled(False)
        self.btn_stop_tts.clicked.connect(self.stop_tts)

        btn_layout.addWidget(self.btn_generate_tts)
        btn_layout.addWidget(self.btn_stop_tts)
        layout.addLayout(btn_layout)

        # 텍스트 입력
        layout.addWidget(QLabel("입력 텍스트:"))
        self.tts_input = QTextEdit()
        self.tts_input.setPlaceholderText("변환할 텍스트를 입력하세요...")
        layout.addWidget(self.tts_input)

        # 로그창은 위에서 이미 생성됨
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
        self.video_workspace_path = QLineEdit(r"D:\youtube")
        btn_workspace = QPushButton("폴더 선택")
        btn_workspace.clicked.connect(lambda: self.browse_folder(self.video_workspace_path))
        workspace_layout.addWidget(QLabel("작업 폴더 (Image/Audio 가 있는 곳):"))
        workspace_layout.addWidget(self.video_workspace_path)
        workspace_layout.addWidget(btn_workspace)
        layout.addLayout(workspace_layout)

        # 스타일 설정 그룹 (Shared)
        self.style_group = self.create_style_group()
        layout.addWidget(self.style_group)
        
        # 안내 문구 (JSON 자동 로드 알림)
        layout.addWidget(QLabel("ℹ️ 자막은 오디오 파일(MP3)과 같은 이름의 .json 파일에서 자동으로 불러옵니다."))

        # 시작 버튼
        self.btn_merge_video = QPushButton("🎬 영상 합성 시작 (자막 포함)")
        self.btn_merge_video.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px; margin-top: 10px;")
        self.btn_merge_video.clicked.connect(self.start_video_merge)
        layout.addWidget(self.btn_merge_video)

        # 로그
        self.video_log = QTextEdit()
        self.video_log.setReadOnly(True)
        self.video_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.video_log)

        # 여백 최적화
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)

        # 기본 폰트 로드
        self.load_custom_fonts()
        self.update_color_indicators()

        self.tab3.setLayout(layout)

    def create_style_group(self):
        # 스타일 설정 그룹
        group = QGroupBox("자막 스타일 설정")
        style_layout = QGridLayout()
        
        self.chk_use_sub = QCheckBox("자막 사용")
        self.chk_use_sub.setChecked(True)
        style_layout.addWidget(self.chk_use_sub, 0, 0)
        
        # 랜덤 효과 체크박스 추가
        self.chk_random_effect = QCheckBox("랜덤 화면 효과 (Zoom/Pan 1.0->1.1)")
        self.chk_random_effect.setChecked(False)
        style_layout.addWidget(self.chk_random_effect, 0, 1, 1, 3)

        # 1행: 폰트 폴더
        font_folder_label = QLabel("폰트 폴더:")
        self.font_folder_path = QLineEdit(r"D:\youtube\fonts")
        btn_font_folder = QPushButton("찾기")
        btn_font_folder.clicked.connect(lambda: self.browse_folder(self.font_folder_path, self.load_custom_fonts))
        style_layout.addWidget(font_folder_label, 1, 0)
        style_layout.addWidget(self.font_folder_path, 1, 1, 1, 3)
        style_layout.addWidget(btn_font_folder, 1, 4)

        # 2행: 폰트 및 크기
        self.combo_font = QComboBox()
        
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 200)
        self.spin_font_size.setValue(60)
        
        style_layout.addWidget(QLabel("폰트 선택:"), 2, 0)
        style_layout.addWidget(self.combo_font, 2, 1, 1, 2)
        style_layout.addWidget(QLabel("크기:"), 2, 3)
        style_layout.addWidget(self.spin_font_size, 2, 4)

        # 3행: 색상 선택
        self.color_text = "black"
        self.color_outline = "white"
        self.color_bg = "Transparent"

        # 글자색
        self.btn_text_color = QPushButton("글자색")
        self.btn_text_color.clicked.connect(lambda: self.pick_color('text'))
        self.ind_text_color = QLabel()
        self.ind_text_color.setFixedSize(20, 20)
        
        # 테두리색
        self.btn_outline_color = QPushButton("테두리색")
        self.btn_outline_color.clicked.connect(lambda: self.pick_color('outline'))
        self.ind_outline_color = QLabel()
        self.ind_outline_color.setFixedSize(20, 20)
        
        # 배경색
        self.btn_bg_color = QPushButton("배경색")
        self.btn_bg_color.clicked.connect(lambda: self.pick_color('bg'))
        self.ind_bg_color = QLabel()
        self.ind_bg_color.setFixedSize(20, 20)
        
        self.checkbox_use_outline = QCheckBox("테두리 사용")
        self.checkbox_use_outline.setChecked(True)
        self.checkbox_use_outline.stateChanged.connect(self.update_color_indicators)
        
        style_layout.addWidget(self.btn_text_color, 3, 0)
        style_layout.addWidget(self.ind_text_color, 3, 1)
        style_layout.addWidget(self.btn_outline_color, 3, 2)
        style_layout.addWidget(self.ind_outline_color, 3, 3)
        style_layout.addWidget(self.checkbox_use_outline, 3, 4)

        # 4행: 배경색 및 사용 여부
        self.checkbox_use_bg = QCheckBox("배경색 사용")
        self.checkbox_use_bg.setChecked(True)
        self.checkbox_use_bg.stateChanged.connect(self.update_color_indicators)
        
        style_layout.addWidget(self.checkbox_use_bg, 4, 0)
        style_layout.addWidget(self.btn_bg_color, 4, 1, 1, 2)
        style_layout.addWidget(self.ind_bg_color, 4, 3)
        
        # 5행: 배경 투명도 조절
        style_layout.addWidget(QLabel("배경 투명도:"), 5, 0)
        self.slider_bg_opacity = QSlider(Qt.Horizontal)
        self.slider_bg_opacity.setRange(0, 100)
        self.slider_bg_opacity.setValue(80) 
        self.lbl_bg_opacity = QLabel("80%")
        self.lbl_bg_opacity.setFixedWidth(40)
        self.slider_bg_opacity.valueChanged.connect(self.update_color_indicators)
        self.slider_bg_opacity.valueChanged.connect(lambda v: self.lbl_bg_opacity.setText(f"{v}%"))
        
        row_opacity = QHBoxLayout()
        row_opacity.addWidget(self.slider_bg_opacity)
        row_opacity.addWidget(self.lbl_bg_opacity)
        style_layout.addLayout(row_opacity, 5, 1, 1, 3)

        # 6행: 소리 볼륨 조절 (배경 투명도 바로 밑)
        style_layout.addWidget(QLabel("소리 볼륨:"), 6, 0)
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(0, 300)
        self.slider_volume.setValue(100)
        self.lbl_volume = QLabel("100%")
        self.lbl_volume.setFixedWidth(40)
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_volume.setText(f"{v}%"))
        
        row_vol = QHBoxLayout()
        row_vol.addWidget(self.slider_volume)
        row_vol.addWidget(self.lbl_volume)
        style_layout.addLayout(row_vol, 6, 1, 1, 3)

        group.setLayout(style_layout)
        return group



    def initTab4(self):
        layout = QVBoxLayout()

        # 경로 설정 그룹
        path_group = QGroupBox("영상 경로 설정")
        path_layout = QGridLayout()

        self.concat_input_dir = QLineEdit(r"D:\youtube")
        btn_browse_input = QPushButton("영상 폴더 선택")
        btn_browse_input.clicked.connect(lambda: self.browse_folder(self.concat_input_dir))
        
        path_layout.addWidget(QLabel("입력 영상 폴더:"), 0, 0)
        path_layout.addWidget(self.concat_input_dir, 0, 1)
        path_layout.addWidget(btn_browse_input, 0, 2)

        self.concat_output_file = QLineEdit(r"D:\youtube\final_video.mp4")
        btn_browse_output = QPushButton("저장 파일 지정")
        btn_browse_output.clicked.connect(self.browse_save_file)
        
        path_layout.addWidget(QLabel("최종 파일 이름:"), 1, 0)
        path_layout.addWidget(self.concat_output_file, 1, 1)
        path_layout.addWidget(btn_browse_output, 1, 2)
        
        # 워터마크 선택 (New)
        self.watermark_path = QLineEdit()
        self.watermark_path.setPlaceholderText("워터마크 이미지 (선택 사항)")
        btn_browse_wm = QPushButton("워터마크 선택")
        btn_browse_wm.clicked.connect(lambda: self.browse_single_file(self.watermark_path, "Images (*.png *.jpg)"))
        
        path_layout.addWidget(QLabel("워터마크(로고):"), 2, 0)
        path_layout.addWidget(self.watermark_path, 2, 1)
        path_layout.addWidget(btn_browse_wm, 2, 2)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)


        # 합치기/중지 버튼 (Horizontal Layout)
        btn_layout = QHBoxLayout()
        
        self.btn_start_concat = QPushButton("🎞️ 영상 하나로 합치기 (Combine Videos)")
        self.btn_start_concat.setStyleSheet("height: 50px; font-weight: bold; background-color: #ff5722; color: white; border-radius: 8px;")
        self.btn_start_concat.clicked.connect(self.start_video_concat)
        
        self.btn_stop_concat = QPushButton("🛑 중지 (Stop)")
        self.btn_stop_concat.setEnabled(False)
        self.btn_stop_concat.setStyleSheet("height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px;")
        self.btn_stop_concat.clicked.connect(self.stop_video_concat)
        
        btn_layout.addWidget(self.btn_start_concat)
        btn_layout.addWidget(self.btn_stop_concat)
        layout.addLayout(btn_layout)

        # 로그창
        layout.addWidget(QLabel("진행 로그:"))
        self.concat_log = QTextEdit()
        self.concat_log.setReadOnly(True)
        self.concat_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.concat_log)

        self.tab4.setLayout(layout)

    def initTab5(self):
        layout = QVBoxLayout()

        # 파일 선택 그룹
        # 폴더 선택 그룹 (Batch Processing)
        file_group = QGroupBox("폴더 설정 (일괄 처리)")
        file_layout = QGridLayout()

        # 입력 폴더 (오디오 + 이미지)
        self.eff_input_dir = QLineEdit()
        self.eff_input_dir.setPlaceholderText("오디오(.mp3)와 이미지 파일이 있는 폴더")
        btn_browse_in = QPushButton("입력 폴더 선택")
        btn_browse_in.clicked.connect(lambda: self.browse_folder(self.eff_input_dir))
        
        file_layout.addWidget(QLabel("입력(소스) 폴더:"), 0, 0)
        file_layout.addWidget(self.eff_input_dir, 0, 1)
        file_layout.addWidget(btn_browse_in, 0, 2)

        # 출력 폴더
        self.eff_output_dir = QLineEdit()
        self.eff_output_dir.setPlaceholderText("결과물(.mp4) 저장 폴더")
        btn_browse_out = QPushButton("출력 폴더 선택")
        btn_browse_out.clicked.connect(lambda: self.browse_folder(self.eff_output_dir))
        
        file_layout.addWidget(QLabel("출력(저장) 폴더:"), 1, 0)
        file_layout.addWidget(self.eff_output_dir, 1, 1)
        file_layout.addWidget(btn_browse_out, 1, 2)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 오디오 트리밍 설정
        trim_layout = QHBoxLayout()
        self.spin_trim_end = QDoubleSpinBox()
        self.spin_trim_end.setRange(0.0, 10.0)
        self.spin_trim_end.setSingleStep(0.1)
        self.spin_trim_end.setValue(0.0)
        self.spin_trim_end.setSuffix(" 초")
        trim_layout.addWidget(QLabel("오디오 뒷부분 자르기 (트리밍):"))
        trim_layout.addWidget(self.spin_trim_end)
        trim_layout.addWidget(QLabel("※ ElevenLabs 잡음 제거용"))
        
        self.btn_trim_audio_only = QPushButton("✂️ MP3만 자르기")
        self.btn_trim_audio_only.setStyleSheet("height: 30px; font-weight: bold; background-color: #757575; color: white; border-radius: 5px;")
        self.btn_trim_audio_only.clicked.connect(self.run_mp3_trimming)
        trim_layout.addWidget(self.btn_trim_audio_only)
        
        trim_layout.addStretch()
        layout.addLayout(trim_layout)
        
        # 영상 효과 설정 (Ken Burns Effect)
        effect_group = QGroupBox("영상 효과 설정 (Ken Burns Effect)")
        effect_layout = QGridLayout()
        
        self.combo_effect_type = QComboBox()
        self.combo_effect_type.addItems(["효과 없음", "Zoom (확대/축소)", "Pan Left to Right (좌→우)", "Pan Right to Left (우→좌)"])
        
        self.spin_start_scale = QDoubleSpinBox()
        self.spin_start_scale.setRange(0.1, 5.0)
        self.spin_start_scale.setSingleStep(0.05)
        self.spin_start_scale.setValue(1.0) # 기본 1.0 (원본 크기)
        self.spin_start_scale.setSuffix("x")
        
        self.spin_end_scale = QDoubleSpinBox()
        self.spin_end_scale.setRange(0.1, 5.0)
        self.spin_end_scale.setSingleStep(0.05)
        self.spin_end_scale.setValue(1.15) # 기본 1.15 (115% 확대)
        self.spin_end_scale.setSuffix("x")
        
        self.combo_effect_type.addItems(["효과 없음", "Zoom (확대/축소)", "Pan Left to Right (좌→우)", "Pan Right to Left (우→좌)"])
        
        # [NEW] 랜덤 효과 체크박스
        self.chk_random_effect = QCheckBox("🎲 랜덤 적용")
        self.chk_random_effect.setStyleSheet("font-weight: bold; color: #00BCD4;")
        self.chk_random_effect.toggled.connect(lambda checked: self.combo_effect_type.setDisabled(checked))
        
        effect_layout.addWidget(QLabel("효과 종류:"), 0, 0)
        effect_layout.addWidget(self.combo_effect_type, 0, 1)
        effect_layout.addWidget(self.chk_random_effect, 0, 2)
        
        effect_layout.addWidget(QLabel("시작 배율:"), 1, 0)
        effect_layout.addWidget(self.spin_start_scale, 1, 1)
        effect_layout.addWidget(QLabel("종료 배율:"), 1, 2)
        effect_layout.addWidget(self.spin_end_scale, 1, 3)
        
        # Pan Speed Control
        self.spin_pan_speed = QDoubleSpinBox()
        self.spin_pan_speed.setRange(0.1, 10.0)
        self.spin_pan_speed.setSingleStep(0.1)
        self.spin_pan_speed.setValue(1.0)
        self.spin_pan_speed.setSuffix("x")
        self.spin_pan_speed.setToolTip("1.0: 영상 길이에 맞춰 완주\n2.0: 2배 빠르게 완주 후 정지\n0.5: 절반만 이동")
        
        effect_layout.addWidget(QLabel("Pan 속도(배속):"), 2, 0)
        effect_layout.addWidget(self.spin_pan_speed, 2, 1)
        effect_group.setLayout(effect_layout)
        layout.addWidget(effect_group)

        # 스타일 정보 안내 (트리밍 바로 밑으로 이동)
        share_label = QLabel("ℹ️ 상단 자막설정 탭의 스타일 설정(폰트, 색상, 소리 볼륨 등)이 공유됩니다.")
        share_label.setStyleSheet("color: #008CBA; font-style: italic; margin-bottom: 5px;")
        layout.addWidget(share_label)

        # 생성/중지 버튼 (Horizontal Layout)
        btn_layout = QHBoxLayout()
        
        self.btn_start_single = QPushButton("🎬 영상 효과 적용 일괄 시작 (Batch Effect)")
        self.btn_start_single.setStyleSheet("height: 50px; font-weight: bold; background-color: #008CBA; color: white; border-radius: 8px;")
        self.btn_start_single.clicked.connect(self.start_batch_video_effect)
        
        self.btn_stop_single = QPushButton("🛑 중지 (Stop)")
        self.btn_stop_single.setEnabled(False)
        self.btn_stop_single.setStyleSheet("height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px;")
        self.btn_stop_single.clicked.connect(self.stop_batch_video_effect)
        
        btn_layout.addWidget(self.btn_start_single)
        btn_layout.addWidget(self.btn_stop_single)
        layout.addLayout(btn_layout)

        # 로그
        self.single_log = QTextEdit()
        self.single_log.setReadOnly(True)
        self.single_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.single_log)

        self.tab5.setLayout(layout)

    def initTab6(self):
        layout = QVBoxLayout()
        
        # 안내 문구
        layout.addWidget(QLabel("📢 배경 동영상과 같은 이름의 MP3를 찾아 자동으로 더빙 영상을 제작합니다."))
        layout.addWidget(QLabel("   (자막 파일(.json)이 있으면 자동으로 포함됩니다.)"))

        # 폴더 선택 그룹 (Batch Processing)
        file_group = QGroupBox("폴더 선택 (일괄 처리)")
        file_layout = QGridLayout()

        # 배경 동영상 폴더
        self.dub_video_dir = QLineEdit()
        self.dub_video_dir.setPlaceholderText("동영상(.mp4)과 오디오(.mp3)가 있는 폴더")
        btn_browse_vid = QPushButton("배경 동영상 폴더 선택")
        btn_browse_vid.clicked.connect(lambda: self.browse_folder(self.dub_video_dir))
        
        file_layout.addWidget(QLabel("작업 폴더:"), 0, 0)
        file_layout.addWidget(self.dub_video_dir, 0, 1)
        file_layout.addWidget(btn_browse_vid, 0, 2)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 스타일 안내
        layout.addWidget(QLabel("ℹ️ 자막 스타일(폰트, 크기, 색상)은 '자막설정' 탭의 설정을 따릅니다."))

        # 시작 버튼
        self.btn_start_dubbing = QPushButton("🎬 일괄 더빙 시작 (Batch Start)")
        self.btn_start_dubbing.setStyleSheet("height: 50px; font-weight: bold; background-color: #9C27B0; color: white; border-radius: 8px;")
        self.btn_start_dubbing.clicked.connect(self.start_video_dubbing)
        layout.addWidget(self.btn_start_dubbing)

        # 로그
        self.dub_log = QTextEdit()
        self.dub_log.setReadOnly(True)
        self.dub_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.dub_log)

        self.tab6.setLayout(layout)

    def start_video_dubbing(self):
        v_dir = self.dub_video_dir.text().strip()
        
        if not os.path.exists(v_dir):
            QMessageBox.warning(self, "경고", "작업 폴더가 존재하지 않습니다.")
            return

        # 스타일 (탭3에서 가져옴)
        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg,
            'bg_opacity': int(self.slider_bg_opacity.value() * 2.55),
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked()
        }
        
        volume = self.slider_volume.value() / 100.0

        self.btn_start_dubbing.setEnabled(False)
        self.dub_log.append(f"⏳ 일괄 더빙 작업 시작: {v_dir}")
        self.dub_log.append(f"⚙️ 적용 스타일: 폰트[{style['font_family']}]")
        
        # BatchDubbingWorker class must be defined (will be added in next step)
        self.dub_worker = BatchDubbingWorker(v_dir, style, volume)
        self.dub_worker.log_signal.connect(self.dub_log.append)
        self.dub_worker.finished.connect(lambda m, e: [self.dub_log.append(f"🏁 {m}"), self.btn_start_dubbing.setEnabled(True)])
        self.dub_worker.error.connect(lambda e: [self.dub_log.append(f"❌ {e}"), self.btn_start_dubbing.setEnabled(True)])
        self.dub_worker.start()

    def browse_single_file(self, line_edit, filter):
        file, _ = QFileDialog.getOpenFileName(self, "파일 선택", "", filter)
        if file:
            line_edit.setText(file)
            # 이미지나 오디오 선택 시 자동으로 출력 파일명 제안 (mp4)
            if hasattr(self, 'single_output_path') and not self.single_output_path.text():
                base = os.path.splitext(file)[0]
                self.single_output_path.setText(base + ".mp4")

    def browse_single_save_file(self, line_edit):
        file, _ = QFileDialog.getSaveFileName(self, "저장 파일 지정", line_edit.text(), "Video Files (*.mp4)")
        if file:
            line_edit.setText(file)

    def start_single_video_merge(self):
        img_path = self.single_img_path.text().strip()
        audio_path = self.single_audio_path.text().strip()
        out_path = self.single_output_path.text().strip()

        if not os.path.exists(img_path) or not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "이미지 또는 오디오 파일이 존재하지 않습니다.")
            return

        # 자막 파싱 (JSON 자동 로드이므로 subtitles는 None으로 전달하여 worker가 JSON을 찾게 함)
        subtitles = None

        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg,
            'bg_opacity': int(self.slider_bg_opacity.value() * 2.55),
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked()
        }

        self.btn_start_single.setEnabled(False)
        self.single_log.append("⏳ 개별 영상 합성 작업을 시작합니다...")

        volume_factor = self.slider_volume.value() / 100.0 # 설정값 수집
        trim_end = self.spin_trim_end.value()
        
        effect_config = {
            'type': self.combo_effect_type.currentIndex(), # 0:None, 1:Zoom, 2:PanL->R, 3:PanR->L
            'start_scale': self.spin_start_scale.value(),
            'end_scale': self.spin_end_scale.value(),
            'pan_speed': self.spin_pan_speed.value()
        }
        
        # 워커 시작
        self.single_worker = SingleVideoWorker(img_path, audio_path, out_path, subtitles, style, volume_factor, trim_end, effect_config)
        self.single_worker.log_signal.connect(self.single_log.append)
        self.single_worker.finished.connect(lambda m, e: [self.single_log.append(f"🏁 {m}"), self.btn_start_single.setEnabled(True)])
        self.single_worker.error.connect(lambda e: [self.single_log.append(f"❌ 오류: {e}"), self.btn_start_single.setEnabled(True)])
        self.single_worker.start()

    def start_video_merge(self):
        # 작업 폴더 확인
        workspace = self.video_workspace_path.text().strip()
        if not os.path.exists(workspace):
            QMessageBox.warning(self, "경로 오류", "작업 폴더가 존재하지 않습니다.")
            return

        # 스타일 dict 생성
        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline if self.checkbox_use_outline.isChecked() else None,
            'bg_color': self.color_bg if self.checkbox_use_bg.isChecked() else "Transparent",
            'bg_opacity': self.slider_bg_opacity.value(),
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked()
        }
        
        # 폰트 검증
        if not style['font_family']:
            QMessageBox.warning(self, "폰트 오류", "폰트가 선택되지 않았습니다.")
            return
            
        # 자막 리스트 로드 (JSON 우선)
        # VideoMergerWorker 내부에서 각 mp3에 맞는 JSON을 찾아서 로드함.
        # 여기서는 "자막 사용" 여부만 알리면 됨 (혹은 빈 딕셔너리 전달)
        subtitles = {} # Worker will load from JSON
        if not self.chk_use_sub.isChecked():
            subtitles = None # 아예 자막 끔
            
        # 랜덤 효과 여부
        use_random = getattr(self, 'chk_random_effect', None) and self.chk_random_effect.isChecked()

        # 워커 시작
        # output_dir = workspace/output
        output_dir = os.path.join(workspace, "output_video")
        
        # Vol, Trim settings from Tab 5 (Single) - shared or distinct?
        # User said shared.
        vol = self.slider_volume.value() / 100.0
        trim = self.spin_trim_end.value()
        
        self.merger_worker = VideoMergerWorker(
            image_dir=workspace,
            audio_dir=workspace,
            output_dir=output_dir,
            subtitles=subtitles,
            style=style,
            volume=vol,
            trim_end=trim,
            use_random_effects=use_random
        )
        self.merger_worker.log_signal.connect(self.video_log.append)
        self.merger_worker.finished.connect(self.on_video_merge_finished)
        self.merger_worker.error.connect(self.on_error)
        
        self.set_btn_enable(False)
        self.merger_worker.start()

    def run_mp3_trimming(self):
        audio_path = self.single_audio_path.text().strip()
        trim_val = self.spin_trim_end.value()

        if not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "오디오 파일이 존재하지 않습니다.")
            return
        
        if trim_val <= 0:
            QMessageBox.information(self, "알림", "자를 시간(초)이 0입니다.")
            return

        try:
            self.single_log.append(f"⏳ MP3 트리밍 시작: {os.path.basename(audio_path)} (뒷부분 {trim_val}초 제거)")
            
            # 새 파일명 생성
            base, ext = os.path.splitext(audio_path)
            output_trimmed = base + "_trimmed" + ext
            
            audio_clip = mpe.AudioFileClip(audio_path)
            new_duration = max(0.1, audio_clip.duration - trim_val)
            trimmed_clip = audio_clip.subclip(0, new_duration)
            
            trimmed_clip.write_audiofile(output_trimmed, logger=None)
            
            audio_clip.close()
            trimmed_clip.close()
            
            self.single_log.append(f"✅ 트리밍 완료! 저장됨: {os.path.basename(output_trimmed)}")
            QMessageBox.information(self, "완료", f"트리밍된 파일이 저장되었습니다:\n{output_trimmed}")
            
            # 입력 칸을 트리밍된 파일로 자동 교체해줄지 여부 (편의성)
            # self.single_audio_path.setText(output_trimmed)
            
        except Exception as e:
            self.single_log.append(f"❌ 트리밍 오류: {e}")
            QMessageBox.critical(self, "오류", f"트리밍 중 오류 발생:\n{e}")

    def browse_save_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, "최종 영상 저장", self.concat_output_file.text(), "Video Files (*.mp4)")
        if filename:
            self.concat_output_file.setText(filename)

    def start_video_concat(self):
        in_dir = self.concat_input_dir.text().strip()
        out_file = self.concat_output_file.text().strip()
        wm_path = self.watermark_path.text().strip() # New

        if not os.path.exists(in_dir):
            QMessageBox.warning(self, "경고", "입력 영상 폴더가 존재하지 않습니다.")
            return

        self.btn_start_concat.setEnabled(False)
        self.btn_stop_concat.setEnabled(True)
        self.concat_log.append("⏳ 영상 합치기 작업을 시작합니다...")

        self.concat_worker = VideoConcatenatorWorker(in_dir, out_file, wm_path) # Pass wm_path
        self.concat_worker.log_signal.connect(self.concat_log.append)
        self.concat_worker.finished.connect(self.on_video_concat_finished)
        self.concat_worker.error.connect(lambda e: [self.concat_log.append(f"❌ 오류: {e}"), self.btn_start_concat.setEnabled(True), self.btn_stop_concat.setEnabled(False)])
        self.concat_worker.start()

    def on_video_concat_finished(self, msg, elapsed):
        self.btn_start_concat.setEnabled(True)
        self.btn_stop_concat.setEnabled(False)
        h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
        self.concat_log.append(f"{msg} (소요 시간: {h:02d}:{m:02d}:{s:02d})")

    def update_color_indicators(self):
        # 선택된 색상을 작은 네모로 표시
        self.ind_text_color.setStyleSheet(f"background-color: {self.color_text}; border: 1px solid white;")
        
        out_col = self.color_outline if self.color_outline.lower() != "none" else "transparent"
        self.ind_outline_color.setStyleSheet(f"background-color: {out_col}; border: 1px solid white;")
        
        # 배경색은 투명도 슬라이더 값 반영하여 인디케이터에 표시
        opacity = int(self.slider_bg_opacity.value() * 2.55)
        if self.color_bg.lower() == "transparent" or not self.checkbox_use_bg.isChecked():
            self.ind_bg_color.setStyleSheet("background-color: transparent; border: 1px solid white;")
        else:
            col = QColor(self.color_bg)
            self.ind_bg_color.setStyleSheet(f"background-color: rgba({col.red()}, {col.green()}, {col.blue()}, {self.slider_bg_opacity.value()/100.0}); border: 1px solid white;")
            
        # 테두리 인디케이터 투명 처리
        if not self.checkbox_use_outline.isChecked():
            self.ind_outline_color.setStyleSheet("background-color: transparent; border: 1px solid white;")
        else:
            self.ind_outline_color.setStyleSheet(f"background-color: {self.color_outline}; border: 1px solid white;")

    def pick_color(self, target):
        from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            if target == 'text': self.color_text = hex_color
            elif target == 'outline': self.color_outline = hex_color
            elif target == 'bg': self.color_bg = hex_color
            self.update_color_indicators() # 네모칸 색상 갱신

    def parse_subtitles(self, text):
        # returns { major_id: [ {"original": "...", "tts": "..."}, ... ] }
        subs = collections.defaultdict(list)
        
        # 1. 전역 정규식 파싱 (Global Regex Parsing)
        # 한 줄에 여러 항목이 있거나 줄바꿈이 불규칙해도 "ID 원본: ... TTS: ..." 패턴을 모두 찾아냄.
        # 패턴: 12-34 원본: ... TTS: ... (다음 ID 패턴이나 헤더가 나오기 전까지)
        # Lookahead: 다음 "숫자-숫자 원본:" 혹은 "숫자. {}" 헤더 혹은 문장 끝
        
        regex_pattern = r'(\d+)-(\d+)\s*원본:(.*?)\s*TTS:(.*?)(?=\s*\d+-\d+\s*원본:|\s*\d+\.\s*\{|$)'
        
        # re.DOTALL: .이 개행문자도 포함 (여러 줄 걸친 내용도 매칭)
        matches = list(re.finditer(regex_pattern, text, re.DOTALL | re.IGNORECASE))
        
        if len(matches) > 0:
            self.log_signal.emit(f"📋 패턴 감지 성공: {len(matches)}개의 항목을 찾았습니다.")
            for match in matches:
                major_id = match.group(1)
                # sub_id = match.group(2)
                original_text = match.group(3).strip()
                tts_text = match.group(4).strip()
                
                # 끝부분의 콤마 제거
                if original_text.endswith(','): original_text = original_text[:-1].strip()
                if tts_text.endswith(','): tts_text = tts_text[:-1].strip()
                
                subs[major_id].append({
                    "original": original_text,
                    "tts": tts_text
                })
            return subs
        
        # 2. 기존 라인 단위 파싱 (Fallback)
        # 위 패턴매칭에 실패한 경우 (예: 원본/TTS 키워드가 없거나 포맷이 다른 경우)
        
        lines = text.strip().split('\n')
        current_id = None
        current_item = {"original": "", "tts": ""}
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Skip major group headers like "1. {}" if pure header
            if re.match(r'^\d+\.\s*\{.*\}', line):
                 if "원본:" not in line and "TTS:" not in line:
                    continue
            
            # 여기서부터는 키워드가 정확하지 않은 구형 포맷 등을 처리
            # 하지만 1번 로직에서 잡지 못한 "ID 원본: ... TTS: ..."는 사실상 형식이 깨진 것이므로
            # 여기서는 전통적인 ID 줄바꿈 방식 등을 처리.
            
            id_match = re.match(r'^(\d+)-(\d+)$', line)
            if id_match:
                current_id = id_match.group(1)
                current_item = {"original": "", "tts": ""}
                continue
                
            if line.startswith("원본:"):
                current_item["original"] = line[len("원본:"):].strip()
            elif line.startswith("TTS:"):
                current_item["tts"] = line[len("TTS:"):].strip()
                if current_id:
                    if not current_item["original"]:
                        current_item["original"] = current_item["tts"]
                    subs[current_id].append(dict(current_item))
                    current_item = {"original": "", "tts": ""}
            else:
                # 구형 포맷: 키워드 없이 "1-1 내용"
                # 단, 원본/TTS 키워드가 있는 줄은 위에서 처리되어야 하므로 제외
                if "원본:" in line or "TTS:" in line:
                    continue 

                match = re.match(r'^(\d+)-\d+\.?\s*(.*)', line)
                if match:
                    major_id = match.group(1)
                    content = match.group(2)
                    subs[major_id].append({"original": content, "tts": content})
                    
        return subs

    def browse_folder(self, line_edit, callback=None):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if path:
            line_edit.setText(path)
            if callback:
                callback()

    def load_custom_fonts(self):
        font_dir = self.font_folder_path.text().strip()
        
        # 1. 폰트 폴더에서 폰트 파일 로드 & 로드된 패밀리 추적
        loaded_families = set()
        if os.path.exists(font_dir) and font_dir.lower() != r"c:\windows\fonts":
            for f in os.listdir(font_dir):
                if f.lower().endswith(('.ttf', '.otf')):
                    font_path = os.path.join(font_dir, f)
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        fams = QFontDatabase.applicationFontFamilies(font_id)
                        for fam in fams:
                            loaded_families.add(fam)
        
        # 2. 모든 사용 가능한 폰트 패밀리 가져오기
        all_families = QFontDatabase().families()
        
        # 3. 필터링 (사용자 요청: Gmarket, Nanum, Malgun)
        # 디렉토리에서 로드된 폰트는 무조건 포함
        target_keywords = ["Gmarket", "Nanum", "Malgun", "BIZ", "Hannari", "Noto"]
        
        matched_families = set(loaded_families) # 로드된 폰트 우선 포함
        
        for family in all_families:
            # 이미 포함된 건 패스
            if family in matched_families:
                continue
                
            # 키워드 매칭 확인
            for kw in target_keywords:
                if kw.lower() in family.lower():
                    matched_families.add(family)
                    break 
        
        # 4. 드롭다운 목록 업데이트
        self.combo_font.clear()
        
        if matched_families:
            final_list = sorted(list(matched_families))
            self.combo_font.addItems(final_list)
            
            # 우선순위: Gmarket > Nanum > Malgun
            # 사용자가 "GmarketSansTTFBold"를 대표로 언급했으므로 'Gmarket Sans'가 포함된 걸 최우선으로 찾음
            target_set = False
            
            # 1순위: Gmarket Sans (Bold 선호하지만 Family 레벨이므로 Gmarket Sans 찾기)
            for i in range(self.combo_font.count()):
                text = self.combo_font.itemText(i)
                if "Gmarket Sans" in text: # Gmarket Sans TTF 등
                    self.combo_font.setCurrentIndex(i)
                    target_set = True
                    break
            
            # 2순위: Gmarket 아무거나
            if not target_set:
                for i in range(self.combo_font.count()):
                    text = self.combo_font.itemText(i)
                    if "Gmarket" in text:
                        self.combo_font.setCurrentIndex(i)
                        target_set = True
                        break
                        
            # 3순위: Nanum
            if not target_set:
                for i in range(self.combo_font.count()):
                    text = self.combo_font.itemText(i)
                    if "Nanum" in text:
                        self.combo_font.setCurrentIndex(i)
                        break
                        
        else:
            # 매칭되는 게 없을 때의 폴백
            fallback_fonts = ["Malgun Gothic", "맑은 고딕", "Arial"]
            available_fallbacks = [f for f in fallback_fonts if f in all_families]
            self.combo_font.addItems(available_fallbacks if available_fallbacks else ["Arial"])

        if hasattr(self, 'video_log') and self.video_log:
            self.video_log.append(f"ℹ️ 폰트 로드 완료: {len(matched_families)}개의 폰트 패밀리 (Gmarket/Nanum/Malgun/Load)")




    def on_video_merge_finished(self, msg, elapsed):
        try:
            self.btn_merge_video.setEnabled(True)
            h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
            log_msg = f"✅ {msg} (소요 시간: {h:02d}:{m:02d}:{s:02d})"
            self.video_log.append(log_msg)
            print(log_msg) # 콘솔 출력 추가
        except Exception as e:
            print(f"Error in on_video_merge_finished: {e}")
            traceback.print_exc()

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

    def stop_tts(self):
        self.stop_tts_flag = True
        self.tts_log.append("🛑 작업 중지 요청됨...")
        self.btn_stop_tts.setEnabled(False)

    def generate_audio(self):
        self.stop_tts_flag = False
        text = self.tts_input.toPlainText().strip()
        if not text:
            self.tts_log.append("❌ 텍스트를 입력하세요.")
            return

        voice_id = self.combo_voice.currentData()
        model_id = self.combo_model.currentData()
        stability = self.slider_stability.value() / 100.0
        similarity = self.slider_similarity.value() / 100.0
        style = self.slider_style.value() / 100.0
        speed = self.slider_speed.value() / 100.0
        volume = self.slider_tts_volume.value() / 100.0
        trim_end = self.spin_tts_trim.value() # 트리밍 값

        # 파싱 로직: 그룹별로 텍스트 묶기
        subs_map = self.parse_subtitles(text)
        tasks = []
        
        if subs_map:
            for major_id, items in subs_map.items():
                combined_tts = " ".join([item['tts'] for item in items])
                if combined_tts:
                    filename = f"{major_id}.mp3"
                    tasks.append((combined_tts, filename, items))
            self.tts_log.append(f"📋 배치 모드 감지: {len(tasks)}개의 파일 생성 예정")
        else:
            # 패턴 없으면 전체 텍스트를 하나로 생성 (UUID 파일명)
            tasks.append((text, None, [{"original": text, "tts": text}]))

        self.btn_generate_tts.setEnabled(False)
        self.btn_stop_tts.setEnabled(True)
        self.tts_log.append("⏳ 생성 시작...")

        # 스레드로 실행 (tasks 리스트 전달)
        audio_target = self.audio_path_edit.text().strip()
        threading.Thread(target=self._run_tts_thread, args=(tasks, voice_id, model_id, stability, similarity, style, speed, volume, audio_target, trim_end), daemon=True).start()

    def _run_tts_thread(self, tasks, voice_id, model_id, stability, similarity, style, speed, volume, custom_dir, trim_end=0.0):
        success_count = 0
        try:
            for task in tasks:
                if self.stop_tts_flag:
                    self.log_signal.emit("🛑 사용자에 의해 작업이 중지되었습니다.")
                    break
                # task 구조: (combined_text, filename, sub_segments)
                text_chunk = task[0]
                filename = task[1]
                sub_segments = task[2] if len(task) > 2 else None
                
                try:
                    save_path = self.tts_client.generate_audio(
                        text=text_chunk, 
                        voice_id=voice_id, 
                        model_id=model_id,
                        stability=stability,
                        similarity_boost=similarity,
                        style=style,
                        speed=speed,
                        volume=volume, # 볼륨 추가
                        filename=filename,
                        custom_dir=custom_dir,
                        sub_segments=sub_segments # 자막 세그먼트 전달
                    )
                    self.log_signal.emit(f"✅ 생성 완료: {os.path.basename(save_path)}")
                    
                    # 트리밍 적용
                    if trim_end > 0 and os.path.exists(save_path):
                        try:
                            # 임시 파일명으로 저장 후 덮어쓰기 (같은 파일 작성이 moviepy에서 문제될 수 있음)
                            temp_trim_path = save_path + ".temp.mp3"
                            
                            aclip = mpe.AudioFileClip(save_path)
                            if aclip.duration > trim_end:
                                new_dur = aclip.duration - trim_end
                                sub = aclip.subclip(0, new_dur)
                                sub.write_audiofile(temp_trim_path, logger=None, bitrate="192k")
                                aclip.close()
                                sub.close()
                                
                                # 원본 삭제 후 교체
                                os.remove(save_path)
                                os.rename(temp_trim_path, save_path)
                                self.log_signal.emit(f"   ✂️ 잡음 제거 완료: {trim_end}초 단축됨")
                            else:
                                aclip.close()
                                self.log_signal.emit(f"   ⚠️ 파일이 너무 짧아 트리밍 건너뜀")
                        except Exception as te:
                             self.log_signal.emit(f"   ⚠️ 트리밍 실패: {te}")
                             
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
        if enabled:
            self.btn_stop_tts.setEnabled(False)

    def browse_image_path(self):
        path = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if path:
            self.image_path_edit.setText(path)

    def browse_image_path_custom(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if path:
            line_edit.setText(path)

    def launch_browser_and_tabs(self):
        # UI Freezing Prevented by Worker
        self.btn_prepare.setEnabled(False)
        self.status_label.setText("1단계: 브라우저 실행 중...")
        
        self.browser_worker = BrowserLauncherWorker('genspark')
        self.browser_worker.log_signal.connect(self.log_display.append)
        self.browser_worker.finished.connect(self.on_browser_launch_finished)
        self.browser_worker.start()

    def on_browser_launch_finished(self, result):
        driver, error = result
        self.btn_prepare.setEnabled(True)
        
        if driver:
            self.driver = driver
            window_count = len(self.driver.window_handles)
            self.log_display.append(f"✅ 브라우저 연결 성공. 현재 탭 수: {window_count}")
            if window_count < 2:
                self.log_display.append("⚠️ 경고: 자동 탭 열기 실패. 수동으로 탭을 열어주세요.")
            self.status_label.setText("2단계: 프롬프트 입력 후 시작 버튼을 누르세요.")
        else:
            self.log_display.append(f"❌ 브라우저 실패: {error}")
            self.status_label.setText("오류 발생 (로그 확인)")


    def launch_browser_imagefx(self):
        self.btn_fx_prepare.setEnabled(False)
        self.fx_status_label.setText("1단계: 브라우저 실행 중...")
        
        self.fx_browser_worker = BrowserLauncherWorker('imagefx')
        self.fx_browser_worker.log_signal.connect(self.fx_log_display.append)
        self.fx_browser_worker.finished.connect(self.on_fx_browser_launch_finished)
        self.fx_browser_worker.start()

    def on_fx_browser_launch_finished(self, result):
        driver, error = result
        self.btn_fx_prepare.setEnabled(True)
        
        if driver:
            self.driver_fx = driver
            window_count = len(self.driver_fx.window_handles)
            self.fx_log_display.append(f"✅ ImageFX 준비됨. (탭: {window_count})")
            if window_count < 2:
                self.fx_log_display.append("⚠️ 경고: 자동 탭 열기 실패. 수동으로 탭을 열어주세요.")
            self.fx_status_label.setText("상태: 브라우저 준비됨.")
        else:
            self.fx_log_display.append(f"❌ 오류: {error}")
            self.fx_status_label.setText("오류 발생")

    def start_automation_imagefx(self):
        if not hasattr(self, 'driver_fx') or self.driver_fx is None:
            QMessageBox.warning(self, "경고", "먼저 브라우저를 준비해 주세요.")
            return

        text = self.fx_prompt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "프롬프트를 입력해 주세요.")
            return

        # 프롬프트 파싱: 1. {프롬프트} 형태 지원
        # 기존: match = re.match(r'^(\d+)\.?\s*(.*)', line.strip())
        # 변경: re.findall 사용
        
        # 1. 1. {내용} 형태 우선 파싱
        parsed_items = re.findall(r'(\d+)\s*\.\s*\{(.*?)\}', text, re.DOTALL)
        
        if parsed_items:
            items = parsed_items
        else:
            # 2. 기존 방식 (1. 내용) 파싱 (백업)
            for line in text.split('\n'):
                match = re.match(r'^(\d+(?:-\d+)?)\.?\s*(.*)', line.strip())
                if match:
                    items.append((match.group(1), match.group(2)))

        if not items:
            QMessageBox.warning(self, "경고", "올바른 형식이 아닙니다 (예: 1. {프롬프트})")
            return

        target_dir = self.fx_image_path_edit.text().strip()
        self.btn_fx_start.setEnabled(False)
        self.btn_fx_stop.setEnabled(True)
        self.start_time_fx = time.time()
        if not self.ui_timer.isActive():
            self.ui_timer.start(1000)

        self.fx_worker = ImageFXMultiTabWorker("", items, self.driver_fx, target_dir)
        self.fx_worker.log_signal.connect(self.fx_log_display.append)
        self.fx_worker.progress.connect(lambda p: self.fx_status_label.setText(p))
        self.fx_worker.finished.connect(self.on_success_fx)
        self.fx_worker.error.connect(self.on_error_fx)
        self.fx_worker.start()

    def on_success_fx(self, msg, elapsed):
        self.start_time_fx = 0
        # If no other timer is running, stop the timer
        if self.start_time_gen == 0:
            self.ui_timer.stop()
            
        self.btn_fx_start.setEnabled(True)
        self.btn_fx_stop.setEnabled(False)
        self.fx_log_display.append(f"🏁 {msg}")
        
        # 자동 압축 (Tab 1과 동일 로직 사용)
        if hasattr(self, 'fx_worker') and self.fx_worker.target_dir:
            self.fx_log_display.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
            self.compress_images_custom(self.fx_image_path_edit, self.fx_log_display)

    def on_error_fx(self, err):
        self.start_time_fx = 0
        if self.start_time_gen == 0:
            self.ui_timer.stop()
            
        self.btn_fx_start.setEnabled(True)
        self.btn_fx_stop.setEnabled(False)
        self.fx_log_display.append(f"❗ 오류: {err}")

    def stop_automation_imagefx(self):
        if hasattr(self, 'fx_worker') and self.fx_worker.isRunning():
            self.fx_worker.stop()
            self.fx_log_display.append("🛑 중지 요청 중... (현재 작업 완료 후 중단됩니다)")
            self.btn_fx_stop.setEnabled(False)

    def compress_images_custom(self, path_edit, log_widget):
        target_dir = path_edit.text().strip()
        if not os.path.exists(target_dir):
            QMessageBox.warning(self, "경고", "폴더가 존재하지 않습니다.")
            return
            
        log_widget.append("⏳ 이미지 압축 시작...")
        count = 0
        for f in os.listdir(target_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                img_path = os.path.join(target_dir, f)
                try:
                    img = Image.open(img_path)
                    img.save(img_path, "JPEG", quality=85, optimize=True)
                    count += 1
                except:
                    pass
        log_widget.append(f"✅ total {count} images compressed.")

    def initTabGeminiAPI(self):
        layout = QVBoxLayout()
        
        self.status_label_gemini = QLabel("1단계: API Key와 모델을 선택하세요.")
        self.status_label_gemini.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.status_label_gemini)
        
        # API Key Selection
        key_layout = QHBoxLayout()
        self.combo_gemini_key = QComboBox()
        # Load Keys
        try:
            if hasattr(self, 'tts_client') and self.tts_client:
                keys = self.tts_client.get_google_keys()
            else:
                from elevenlabs_client import ElevenLabsClient
                self.tts_client = ElevenLabsClient()
                keys = self.tts_client.get_google_keys()
                
            for k in keys:
                self.combo_gemini_key.addItem(k['name'], k['api_key'])
        except Exception as e:
            self.status_label_gemini.setText(f"API Key 로드 실패: {e}")

        key_layout.addWidget(QLabel("Google API Key:"))
        key_layout.addWidget(self.combo_gemini_key)
        layout.addLayout(key_layout)
        
        # Model Selection
        idx_layout = QHBoxLayout()
        self.combo_gemini_model = QComboBox()
        self.combo_gemini_model.addItem("Gemini 3.0 Pro (Preview)", "gemini-3-pro-image-preview")
        self.combo_gemini_model.addItem("Gemini 2.5 Flash", "gemini-2.5-flash-image")
        
        idx_layout.addWidget(QLabel("Model:"))
        idx_layout.addWidget(self.combo_gemini_model)
        layout.addLayout(idx_layout)

        # Path
        path_layout = QHBoxLayout()
        self.gemini_save_dir = QLineEdit(r"D:\youtube")
        btn_browse_gemini = QPushButton("저장 폴더")
        btn_browse_gemini.clicked.connect(lambda: self.browse_folder(self.gemini_save_dir))
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.gemini_save_dir)
        path_layout.addWidget(btn_browse_gemini)
        layout.addLayout(path_layout)
        
        # Prompt
        layout.addWidget(QLabel("이미지 프롬프트 입력 (형식: 2. {프롬프트 내용})"))
        self.gemini_prompt_input = QTextEdit()
        self.gemini_prompt_input.setPlaceholderText("2. {Cute cat in Korea ...}\n2-1 설명...")
        self.gemini_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.gemini_prompt_input)
        
        # Buttons
        btn_h_layout = QHBoxLayout()
        self.btn_gemini_start = QPushButton("🚀 2. 이미지 가져오기 (API 호출)")
        self.btn_gemini_start.setStyleSheet("height: 50px; font-weight: bold; background-color: #2196F3; color: white; border-radius: 8px;")
        self.btn_gemini_start.clicked.connect(self.start_gemini_automation)
        
        self.btn_gemini_stop = QPushButton("🛑 중지")
        self.btn_gemini_stop.setEnabled(False)
        self.btn_gemini_stop.setStyleSheet("height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px;")
        self.btn_gemini_stop.clicked.connect(self.stop_gemini_automation)
        
        btn_h_layout.addWidget(self.btn_gemini_start)
        btn_h_layout.addWidget(self.btn_gemini_stop)
        layout.addLayout(btn_h_layout)
        
        # Compress
        self.btn_gemini_compress = QPushButton("🗜️ 3. 이미지 압축 (용량 줄이기)")
        self.btn_gemini_compress.setStyleSheet("height: 40px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 8px; margin-top: 5px;")
        self.btn_gemini_compress.clicked.connect(lambda: self.compress_images(dir_path=self.gemini_save_dir.text().strip()))
        layout.addWidget(self.btn_gemini_compress)

        # Log
        self.gemini_log = QTextEdit()
        self.gemini_log.setReadOnly(True)
        self.gemini_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.gemini_log)
        
        self.tab_gemini.setLayout(layout)

    def start_gemini_automation(self):
        api_key = self.combo_gemini_key.currentData()
        if not api_key:
            QMessageBox.warning(self, "경고", "API Key가 선택되지 않았습니다.")
            return

        model_name = self.combo_gemini_model.currentData()
        save_dir = self.gemini_save_dir.text().strip()
        text = self.gemini_prompt_input.toPlainText().strip()
        
        if not text:
             QMessageBox.warning(self, "경고", "프롬프트를 입력하세요.")
             return
             
        # Parse
        items = re.findall(r'(\d+)\s*\.\s*\{(.*?)\}', text, re.DOTALL)
        if not items:
            self.gemini_log.append("❌ 프롬프트 형식이 올바르지 않습니다 (예: 2. {프롬프트})")
            return
            
        self.btn_gemini_start.setEnabled(False)
        self.btn_gemini_stop.setEnabled(True)
        self.gemini_log.append(f"🚀 Gemini API 이미지 생성 시작 ({len(items)}장)")
        
        self.gemini_worker = GeminiAPIImageWorker(items, api_key, model_name, save_dir)
        self.gemini_worker.log_signal.connect(self.gemini_log.append)
        self.gemini_worker.progress.connect(self.status_label_gemini.setText)
        self.gemini_worker.finished.connect(self.on_gemini_success)
        self.gemini_worker.error.connect(self.on_gemini_error)
        self.gemini_worker.start()
        
    def stop_gemini_automation(self):
        if hasattr(self, 'gemini_worker'):
            self.gemini_worker.stop()
            self.gemini_log.append("🛑 중지 요청됨...")
            self.btn_gemini_stop.setEnabled(False)

    def on_gemini_success(self, msg, elapsed):
        self.btn_gemini_start.setEnabled(True)
        self.btn_gemini_stop.setEnabled(False)
        self.gemini_log.append(f"🏁 {msg} ({elapsed:.1f}s)")
        
        # Auto compress (Disabled by user request)
        # self.gemini_log.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
        # self.compress_images(dir_path=self.gemini_save_dir.text().strip())
        self.gemini_log.append("ℹ️ 생성된 이미지는 원본 화질 그대로 저장되었습니다.")

    def on_gemini_error(self, err):
        self.btn_gemini_start.setEnabled(True)
        self.btn_gemini_stop.setEnabled(False)
        self.gemini_log.append(f"❗ 오류: {err}")

    def browse_audio_path(self):
        path = QFileDialog.getExistingDirectory(self, "오디오 저장 폴더 선택")
        if path:
            self.audio_path_edit.setText(path)

    def update_timer_display(self):
        now = time.time()
        
        # GenSpark Timer
        if hasattr(self, 'start_time_gen') and self.start_time_gen > 0:
            elapsed = int(now - self.start_time_gen)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            if hasattr(self, 'timer_label'):
                self.timer_label.setText(f"소요 시간: {h:02d}:{m:02d}:{s:02d}")
        
            if hasattr(self, 'fx_timer_label'):
                self.fx_timer_label.setText(f"소요 시간: {h:02d}:{m:02d}:{s:02d}")


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
        self.btn_stop.setEnabled(True)
        self.start_time_gen = time.time()
        if not self.ui_timer.isActive():
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
        self.start_time_gen = 0
        if self.start_time_fx == 0:
            self.ui_timer.stop()
            
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_display.append(f"🏁 {msg}")
        
        # 생성 완료 후 자동 압축 실행
        if hasattr(self, 'worker') and self.worker.target_dir:
            self.log_display.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
            self.compress_images(dir_path=self.worker.target_dir)

    def on_error(self, err):
        self.start_time_gen = 0
        if self.start_time_fx == 0:
            self.ui_timer.stop()
            
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_display.append(f"❗ 오류: {err}")

    def stop_automation(self):
            self.log_display.append("🛑 중지 요청 중... (현재 작업 완료 후 중단됩니다)")
            self.btn_stop.setEnabled(False)


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


    def initTabFTP(self):
        layout = QVBoxLayout()
        
        # 안내
        layout.addWidget(QLabel("📡 FTP 서버로 파일을 일괄 업로드합니다."))

        # Server Info Group
        server_group = QGroupBox("FTP 서버 정보")
        form_layout = QFormLayout()
        
        self.ftp_host = QLineEdit("devlab.pics")
        self.ftp_host.setPlaceholderText("서버 주소 (예: 192.168.0.1)")
        
        self.ftp_port = QLineEdit("21")
        self.ftp_port.setFixedWidth(50)
        
        self.ftp_id = QLineEdit()
        self.ftp_id.setPlaceholderText("ID")
        
        self.ftp_pw = QLineEdit()
        self.ftp_pw.setPlaceholderText("Password")
        self.ftp_pw.setEchoMode(QLineEdit.Password)
        
        # Host/Port Layout
        host_layout = QHBoxLayout()
        host_layout.addWidget(self.ftp_host)
        host_layout.addWidget(QLabel("Port:"))
        host_layout.addWidget(self.ftp_port)
        
        form_layout.addRow("서버 주소:", host_layout)
        form_layout.addRow("아이디:", self.ftp_id)
        form_layout.addRow("비밀번호:", self.ftp_pw)
        
        server_group.setLayout(form_layout)
        layout.addWidget(server_group)

        # Login/Logout Buttons Group (New)
        login_btn_layout = QHBoxLayout()
        
        self.btn_ftp_login = QPushButton("로그인 (접속 테스트)")
        self.btn_ftp_login.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_ftp_login.clicked.connect(self.ftp_login)
        
        self.btn_ftp_logout = QPushButton("로그아웃")
        self.btn_ftp_logout.setStyleSheet("background-color: #757575; color: white; font-weight: bold;")
        self.btn_ftp_logout.clicked.connect(self.ftp_logout)
        
        login_btn_layout.addWidget(self.btn_ftp_login)
        login_btn_layout.addWidget(self.btn_ftp_logout)
        
        layout.addLayout(login_btn_layout)
        
        # Path Info Group
        path_group = QGroupBox("전송 설정")
        path_layout = QGridLayout()
        
        # Local Folder
        self.ftp_local_dir = QLineEdit()
        btn_local = QPushButton("내 PC 폴더 선택")
        btn_local.clicked.connect(lambda: self.browse_folder(self.ftp_local_dir))
        
        path_layout.addWidget(QLabel("내 PC 폴더:"), 0, 0)
        path_layout.addWidget(self.ftp_local_dir, 0, 1)
        path_layout.addWidget(btn_local, 0, 2)
        
        # Remote Path
        self.ftp_remote_dir = QLineEdit()
        self.ftp_remote_dir.setPlaceholderText("서버 경로 (예: /public_html/video)")
        
        path_layout.addWidget(QLabel("서버 저장 경로:"), 1, 0)
        path_layout.addWidget(self.ftp_remote_dir, 1, 1, 1, 2)
        
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)
        
        # Start Button
        self.btn_ftp_start = QPushButton("🚀 FTP 업로드 시작")
        self.btn_ftp_start.setStyleSheet("height: 50px; font-weight: bold; background-color: #009688; color: white; border-radius: 8px;")
        self.btn_ftp_start.clicked.connect(self.start_ftp_upload)
        layout.addWidget(self.btn_ftp_start)
        
        # Log
        self.ftp_log = QTextEdit()
        self.ftp_log.setReadOnly(True)
        self.ftp_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.ftp_log)
        
        self.tab_ftp.setLayout(layout)

    def start_ftp_upload(self):
        host = self.ftp_host.text().strip()
        port = self.ftp_port.text().strip()
        user = self.ftp_id.text().strip()
        passwd = self.ftp_pw.text().strip()
        local_dir = self.ftp_local_dir.text().strip()
        remote_dir = self.ftp_remote_dir.text().strip()
        
        if not host or not user or not passwd:
            QMessageBox.warning(self, "경고", "서버 정보(주소, ID, 비번)를 모두 입력해주세요.")
            return
            
        if not local_dir or not os.path.exists(local_dir):
            QMessageBox.warning(self, "경고", "내 PC 폴더가 유효하지 않습니다.")
            return

        if not remote_dir:
            QMessageBox.warning(self, "경고", "서버 저장 경로를 입력해주세요.")
            return
            
        self.btn_ftp_start.setEnabled(False)
        self.ftp_log.append("⏳ FTP 연결 및 업로드 시작...")
        
        self.ftp_worker = FTPUploadWorker(host, port, user, passwd, local_dir, remote_dir)
        self.ftp_worker.log_signal.connect(self.ftp_log.append)
        self.ftp_worker.finished.connect(lambda m: [self.ftp_log.append(f"🏁 {m}"), self.btn_ftp_start.setEnabled(True)])
        self.ftp_worker.error.connect(lambda e: [self.ftp_log.append(f"❌ {e}"), self.btn_ftp_start.setEnabled(True)])
        self.ftp_worker.start()

    def ftp_login(self):
        host = self.ftp_host.text().strip()
        port = self.ftp_port.text().strip()
        user = self.ftp_id.text().strip()
        passwd = self.ftp_pw.text().strip()
        
        if not host or not user or not passwd:
            QMessageBox.warning(self, "경고", "서버 주소, 아이디, 비밀번호를 입력해주세요.")
            return

        self.btn_ftp_login.setEnabled(False)
        self.ftp_log.append("⏳ FTP 접속 테스트 중...")
        
        self.login_worker = FTPLoginWorker(host, port, user, passwd)
        self.login_worker.log_signal.connect(self.ftp_log.append)
        self.login_worker.finished.connect(lambda m: [self.ftp_log.append(f"🔔 {m}"), self.btn_ftp_login.setEnabled(True)])
        self.login_worker.error.connect(lambda e: [self.ftp_log.append(f"❌ 접속 실패: {e}"), self.btn_ftp_login.setEnabled(True)])
        self.login_worker.start()

    def ftp_logout(self):
        self.ftp_log.append("🔒 로그아웃(연결 정보 초기화) 되었습니다.")

    def initTab7(self):
        layout = QVBoxLayout()

        # 1. Filter Group
        filter_layout = QGridLayout()
        
        # API Key
        self.combo_yt_key = QComboBox()
        # Load keys from DB (using tts_client if available)
        self.yt_keys = []
        if hasattr(self, 'tts_client') and self.tts_client:
            self.yt_keys = self.tts_client.get_youtube_keys()
            for k in self.yt_keys:
                self.combo_yt_key.addItem(k['name'], k['api_key'])
        
        filter_layout.addWidget(QLabel("키 (API Key):"), 0, 0)
        filter_layout.addWidget(self.combo_yt_key, 0, 1)

        # Search Date (Days)
        self.combo_yt_days = QComboBox()
        self.combo_yt_days.addItem("1 일간", 1)
        self.combo_yt_days.addItem("2 일간", 2)
        self.combo_yt_days.addItem("3 일간", 3)
        self.combo_yt_days.addItem("4 일간", 4)
        self.combo_yt_days.addItem("5 일간", 5)
        
        filter_layout.addWidget(QLabel("검색일자:"), 0, 2)
        filter_layout.addWidget(self.combo_yt_days, 0, 3)

        # Video Type
        self.combo_yt_type = QComboBox()
        self.combo_yt_type.addItem("쇼츠 (Short)", "short")
        self.combo_yt_type.addItem("전체 (Any)", "any")
        self.combo_yt_type.addItem("중영상 (Medium, 4~20분)", "medium")
        self.combo_yt_type.addItem("장영상 (Long, 20분+)", "long")
        
        filter_layout.addWidget(QLabel("영상종류:"), 1, 0)
        filter_layout.addWidget(self.combo_yt_type, 1, 1)

        # Search Query
        self.edit_yt_query = QLineEdit()
        self.edit_yt_query.setPlaceholderText("검색어 입력")
        self.edit_yt_query.returnPressed.connect(self.start_youtube_search)
        
        self.btn_yt_search = QPushButton("검색")
        self.btn_yt_search.setStyleSheet("background-color: #0056b3; color: white; font-weight: bold;")
        self.btn_yt_search.clicked.connect(self.start_youtube_search)

        filter_layout.addWidget(QLabel("검색어:"), 1, 2)
        
        query_layout = QHBoxLayout()
        query_layout.addWidget(self.edit_yt_query)
        query_layout.addWidget(self.btn_yt_search)
        filter_layout.addLayout(query_layout, 1, 3)
        
        layout.addLayout(filter_layout)
        
        # 2. Result Table
        self.table_youtube = QTableWidget()
        self.table_youtube.setColumnCount(13)
        self.table_youtube.setHorizontalHeaderLabels([
            "번호", "썸네일", "채널명", "제목", "조회수", "구독자", "조회수/구독자", "영상길이", "영상수", "기본언어", "오디오언어", "채널국가", "업로드날짜"
        ])
        
        # Style
        self.table_youtube.verticalHeader().setVisible(False)
        self.table_youtube.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_youtube.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_youtube.setIconSize(QRect(0,0,120,90).size()) # Thumbnail Size
        self.table_youtube.setColumnWidth(1, 130) # Thumbnail Column
        self.table_youtube.cellClicked.connect(self.on_table_cell_clicked) # Click Event
        
        header = self.table_youtube.horizontalHeader()
        # 모든 컬럼이 내용에 맞춰 늘어나도록 설정
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # 썸네일(1), 제목(3) 등 일부 컬럼은 고정하거나 비율 조정이 필요할 수 있으나 우선 다 보이게 설정
        
        layout.addWidget(self.table_youtube)

        # 3. Log
        layout.addWidget(QLabel("로그:"))
        self.log_youtube = QTextEdit()
        self.log_youtube.setReadOnly(True)
        self.log_youtube.setMaximumHeight(100)
        self.log_youtube.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.log_youtube)

        self.tab7.setLayout(layout)

    def start_youtube_search(self):
        # 1. Validation
        api_key = self.combo_yt_key.currentData()
        if not api_key:
            if self.combo_yt_key.count() > 0:
                # If data was not set properly but text exists (fallback)
                idx = self.combo_yt_key.currentIndex()
                if 0 <= idx < len(self.yt_keys):
                     api_key = self.yt_keys[idx]['api_key']
            
            if not api_key:
                QMessageBox.warning(self, "경고", "YouTube API 키를 선택해주세요. (DB에 키가 있어야 합니다)")
                return

        query = self.edit_yt_query.text().strip()
        if not query:
            QMessageBox.warning(self, "경고", "검색어를 입력해주세요.")
            return
            
        days = self.combo_yt_days.currentData()
        video_type = self.combo_yt_type.currentData()
        
        # 2. UI Update
        self.btn_yt_search.setEnabled(False)
        self.table_youtube.setSortingEnabled(False) # Disable sorting while clearing/inserting
        self.table_youtube.setRowCount(0)
        self.log_youtube.append(f"🔍 검색 시작: '{query}' (최근 {days}일, {video_type})")
        
        # 3. Start Worker
        self.worker_yt = YoutubeSearchWorker(api_key, query, days, video_type)
        self.worker_yt.log_signal.connect(self.log_youtube.append)
        self.worker_yt.finished.connect(self.on_yt_search_done)
        self.worker_yt.error.connect(lambda e: [self.log_youtube.append(f"❌ {e}"), self.btn_yt_search.setEnabled(True)])
        self.worker_yt.start()

    def on_yt_search_done(self, results):
        self.btn_yt_search.setEnabled(True)
        if not results:
            self.log_youtube.append("⚠️ 검색 결과가 없습니다.")
            return
        
        self.table_youtube.setRowCount(len(results))
        self.table_youtube.setStyleSheet("QTableWidget::item { padding: 5px; }")
        
        img_tasks = []
        
        for r, row in enumerate(results):
            # Helper for alignment
            def make_item(text, align):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                return it

            # Helper for numeric items
            def make_numeric_item(text, align, color=None, font=None):
                it = NumericTableWidgetItem(str(text))
                it.setTextAlignment(align)
                if color: it.setForeground(color)
                if font: it.setFont(font)
                return it

            # 0: Number (Center)
            self.table_youtube.setItem(r, 0, make_numeric_item(row['number'], Qt.AlignCenter))
            
            # 1: Thumbnail (Placeholder first)
            thumb_item = QTableWidgetItem("Loading...")
            thumb_item.setData(Qt.UserRole, row.get('video_id')) # Store Video ID
            self.table_youtube.setItem(r, 1, thumb_item)
            if row['thumbnail_url']:
                img_tasks.append((r, row['thumbnail_url']))
            
            # 2: Channel (Left)
            chan_item = make_item(row['channel_name'], Qt.AlignLeft | Qt.AlignVCenter)
            chan_item.setData(Qt.UserRole, row.get('channel_id')) # Store Channel ID
            self.table_youtube.setItem(r, 2, chan_item)
            
            # 3: Title (Left)
            self.table_youtube.setItem(r, 3, make_item(row['title'], Qt.AlignLeft | Qt.AlignVCenter))
            
            # 4: Views (Right) - Numeric
            self.table_youtube.setItem(r, 4, make_numeric_item(f"{row['view_count']:,}", Qt.AlignRight | Qt.AlignVCenter))
            
            # 5: Subs (Right) - Numeric
            self.table_youtube.setItem(r, 5, make_numeric_item(f"{row['subscriber_count']:,}", Qt.AlignRight | Qt.AlignVCenter))
            
            # 6: Ratio (Right) [New] - Numeric
            ratio = 0
            if row['subscriber_count'] > 0:
                ratio = (row['view_count'] / row['subscriber_count']) * 100
            
            # 색상 강조: 100% 이상이면 초록, 50% 이상 파랑, 그외 평범
            ratio_text = f"{ratio:.1f}%"
            ratio_color = QColor("#D4D4D4")
            ratio_font = None
            
            if ratio >= 100:
                ratio_color = QColor("#4CAF50") # Green
                ratio_font = QFont("Arial", 9, QFont.Bold)
            elif ratio >= 50:
                ratio_color = QColor("#2196F3") # Blue
                ratio_font = QFont("Arial", 9, QFont.Bold)
                 
            self.table_youtube.setItem(r, 6, make_numeric_item(ratio_text, Qt.AlignRight | Qt.AlignVCenter, ratio_color, ratio_font))

            # 7: Duration (Center) - Moved here
            self.table_youtube.setItem(r, 7, make_item(row.get('duration_str', '-'), Qt.AlignCenter))

            # 8: Video Total (Center) - Numeric
            self.table_youtube.setItem(r, 8, make_numeric_item(f"{row['video_total']:,}", Qt.AlignCenter))
            
            # 9: Lang (Center)
            self.table_youtube.setItem(r, 9, make_item(row['lang'], Qt.AlignCenter))
            
            # 10: Audio Lang (Center)
            self.table_youtube.setItem(r, 10, make_item(row['audio_lang'], Qt.AlignCenter))
            
            # 11: Country (Center)
            self.table_youtube.setItem(r, 11, make_item(row['country'], Qt.AlignCenter))
            
            # 12: Date (Center)
            date_str = row['published_at'].replace("T", " ").replace("Z", "")
            self.table_youtube.setItem(r, 12, make_item(date_str, Qt.AlignCenter))
            
            # Row Height adjustment for thumbnail
            self.table_youtube.setRowHeight(r, 96)
            
        # 4. Enable Sorting (Turn on after populating to avoid weird jumps during insert, or just set it here)
        self.table_youtube.setSortingEnabled(True)

        # Start Image Loader
        if img_tasks:
            self.worker_img = ImageLoadWorker(img_tasks)
            self.worker_img.loaded.connect(self.on_thumb_loaded)
            self.worker_img.start()

    def on_thumb_loaded(self, row, pixmap):
        item = QTableWidgetItem()
        # Scale pixmap to fit icon size nicely?
        # Icon handles scaling usually, but good to be explicit if needed.
        # scaled_pix = pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        from PyQt5.QtGui import QIcon
        # 기존 아이템을 가져와서 아이콘만 설정 (데이터 보존)
        item = self.table_youtube.item(row, 1)
        if not item:
            item = QTableWidgetItem()
            self.table_youtube.setItem(row, 1, item)
            
        item.setIcon(QIcon(pixmap))
        item.setText("") # Remove loading text

    def on_table_cell_clicked(self, row, col):
        # 선택 시에도 컬럼 크기 유지 (또는 재조정)
        header = self.table_youtube.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        item = self.table_youtube.item(row, col)
        if not item: return
        
        data_id = item.data(Qt.UserRole)
        if not data_id: return
        
        url = ""
        if col == 1: # Thumbnail -> Video
            url = f"https://www.youtube.com/watch?v={data_id}"
        elif col == 2: # Channel Name -> Channel
            url = f"https://www.youtube.com/channel/{data_id}"
            
        if url:
            self.log_youtube.append(f"🌐 링크 열기: {url}")
            webbrowser.open(url)            



    def start_batch_video_effect(self):
        input_dir = self.eff_input_dir.text().strip()
        output_dir = self.eff_output_dir.text().strip()
        
        if not input_dir or not os.path.exists(input_dir):
            QMessageBox.warning(self, "경고", "입력 폴더가 존재하지 않습니다.")
            return
            
        if not output_dir:
            QMessageBox.warning(self, "경고", "출력 폴더를 지정해주세요.")
            return
            
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                QMessageBox.warning(self, "경고", "출력 폴더를 생성할 수 없습니다.")
                return

        # 설정값 읽기
        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg,
            'bg_opacity': int(self.slider_bg_opacity.value() * 2.55),
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked()
        }
        volume = self.slider_volume.value() / 100.0
        trim_end = self.spin_trim_end.value()
        
        # Effect Config
        effect_config = {
            'type': self.combo_effect_type.currentIndex(), 
            # 0: None, 1: Zoom, 2: Pan L->R, 3: Pan R->L
            'start_scale': self.spin_start_scale.value(),
            'end_scale': self.spin_end_scale.value(),
            'pan_speed': self.spin_pan_speed.value(),
            'random': self.chk_random_effect.isChecked()
        }

        self.btn_start_single.setEnabled(False)
        self.btn_stop_single.setEnabled(True)
        self.single_log.append(f"⏳ 일괄 작업 시작: {input_dir}")
        self.single_log.append(f"   출력 대상: {output_dir}")

        self.batch_eff_worker = BatchVideoEffectWorker(
            input_dir, output_dir, style, volume, trim_end, effect_config
        )
        self.batch_eff_worker.log_signal.connect(self.single_log.append)
        self.batch_eff_worker.finished.connect(self.on_batch_eff_finished)
        self.batch_eff_worker.error.connect(lambda e: [self.single_log.append(f"❌ {e}"), self.btn_start_single.setEnabled(True), self.btn_stop_single.setEnabled(False)])
        self.batch_eff_worker.start()

    def stop_batch_video_effect(self):
        if hasattr(self, 'batch_eff_worker') and self.batch_eff_worker.isRunning():
            self.batch_eff_worker.stop()
            self.btn_stop_single.setEnabled(False)
            self.single_log.append("🛑 중지 요청 중...")

    def stop_video_concat(self):
        if hasattr(self, 'concat_worker') and self.concat_worker.isRunning():
            self.concat_worker.stop()
            self.btn_stop_concat.setEnabled(False)
            self.concat_log.append("🛑 중지 요청 중...")

    def initTabAudioToVideo(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("🎬 MP3 + SRT + 이미지를 결합하여 영상을 제작합니다."))
        layout.addWidget(QLabel("   - 폴더 내의 1.mp3, 1.srt 파일을 찾아 1.mp4를 만듭니다."))
        layout.addWidget(QLabel("   - SRT 인덱스에 맞는 이미지(1.jpg, 2.jpg...)가 있으면 해당 시점에 배경으로 사용합니다."))
        layout.addWidget(QLabel("   - 자막 스타일은 'Video Composite' 탭의 설정을 따릅니다."))
        
        # Folder Selection
        dir_layout = QHBoxLayout()
        self.atv_dir = QLineEdit()
        btn_dir = QPushButton("작업 폴더 선택")
        btn_dir.clicked.connect(lambda: self.browse_folder(self.atv_dir))
        dir_layout.addWidget(QLabel("작업 폴더:"))
        dir_layout.addWidget(self.atv_dir)
        dir_layout.addWidget(btn_dir)
        layout.addLayout(dir_layout)
        
        # Start Button
        self.btn_atv_start = QPushButton("영상 생성 시작")
        self.btn_atv_start.setStyleSheet("height: 40px; font-weight: bold; background-color: #673AB7; color: white;")
        self.btn_atv_start.clicked.connect(self.start_audio_to_video)
        layout.addWidget(self.btn_atv_start)
        
        # Log
        self.atv_log = QTextEdit()
        self.atv_log.setReadOnly(True)
        self.atv_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.atv_log)
        
        self.tab_audio_video.setLayout(layout)

    def start_audio_to_video(self):
        target_dir = self.atv_dir.text().strip()
        if not target_dir or not os.path.exists(target_dir):
            QMessageBox.warning(self, "경고", "올바른 작업 폴더를 선택해주세요.")
            return

        # 스타일 설정 읽기 (tab3의 컨트롤 재사용)
        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg,
            'bg_opacity': int(self.slider_bg_opacity.value() * 2.55), # 0-100 -> 0-255
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked(),
            'font_folder': self.font_folder_path.text().strip()
        }
        
        self.atv_log.append(f"🚀 작업 시작: {target_dir}")
        self.btn_atv_start.setEnabled(False)
        
        self.atv_worker = AudioToVideoWorker(target_dir, style)
        self.atv_worker.log_signal.connect(self.atv_log.append)
        self.atv_worker.finished.connect(self.on_atv_finished)
        self.atv_worker.error.connect(self.on_atv_error)
        self.atv_worker.start()
        
    def on_atv_finished(self, msg, elapsed):
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        time_str = f" ({h:02d}:{m:02d}:{s:02d})"
        
        self.atv_log.append(f"🏁 {msg}{time_str}")
        self.btn_atv_start.setEnabled(True)
        
    def on_atv_error(self, err):
        self.atv_log.append(f"❌ 오류: {err}")
        self.btn_atv_start.setEnabled(True)

    def on_batch_eff_finished(self, msg, elapsed):
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        time_str = f" ({h:02d}:{m:02d}:{s:02d})"
        self.single_log.append(f"🏁 {msg}{time_str}")
        self.btn_start_single.setEnabled(True)
        self.btn_stop_single.setEnabled(False)

    def initTabAudioTranscribe(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🎙️ 오디오 변환 및 자막 생성 (Whisper)"))
        layout.addWidget(QLabel("   (OpenAI Whisper 모델을 사용하여 MP3를 SRT 자막으로 변환합니다.)"))

        # Model Selection
        model_group = QGroupBox("Whisper 모델 설정")
        model_layout = QHBoxLayout()
        
        self.combo_whisper_model = QComboBox()
        # Models: tiny, base, small, medium, large
        self.combo_whisper_model.addItems(["base", "tiny", "small", "medium", "large"])
        self.combo_whisper_model.setCurrentText("base")
        
        model_layout.addWidget(QLabel("모델 크기:"))
        model_layout.addWidget(self.combo_whisper_model)
        model_layout.addWidget(QLabel("(클수록 정확하지만 느림, GPU 권장)"))
        
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # 3 Tabs for sub-functions
        sub_tabs = QTabWidget()
        
        # SubTab 1: M4A -> MP3
        tab_conv = QWidget()
        l_conv = QVBoxLayout()
        
        conv_in_group = QGroupBox("M4A 파일 선택")
        conv_in_layout = QHBoxLayout()
        self.at_m4a_files = QLineEdit()
        self.at_m4a_files.setPlaceholderText("선택된 파일이 없습니다.")
        btn_m4a = QPushButton("파일 찾기")
        btn_m4a.clicked.connect(lambda: self.browse_files(self.at_m4a_files, "Audio Files (*.m4a)"))
        conv_in_layout.addWidget(self.at_m4a_files)
        conv_in_layout.addWidget(btn_m4a)
        conv_in_group.setLayout(conv_in_layout)
        
        l_conv.addWidget(conv_in_group)
        
        self.btn_at_convert = QPushButton("1. M4A -> MP3 변환 시작 (선택 파일)")
        self.btn_at_convert.setStyleSheet("background-color: #009688; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_convert.clicked.connect(lambda: self.start_audio_transcribe("convert"))
        l_conv.addWidget(self.btn_at_convert)
        l_conv.addStretch()
        
        tab_conv.setLayout(l_conv)
        sub_tabs.addTab(tab_conv, "1. Convert MP3")
        
        # SubTab 2: MP3 -> SRT
        tab_srt = QWidget()
        l_srt = QVBoxLayout()
        
        srt_in_group = QGroupBox("MP3 파일 선택")
        srt_in_layout = QHBoxLayout()
        self.at_mp3_files = QLineEdit()
        self.at_mp3_files.setPlaceholderText("선택된 파일이 없습니다.")
        btn_mp3 = QPushButton("파일 찾기")
        btn_mp3.clicked.connect(lambda: self.browse_files(self.at_mp3_files, "Audio Files (*.mp3)"))
        srt_in_layout.addWidget(self.at_mp3_files)
        srt_in_layout.addWidget(btn_mp3)
        srt_in_group.setLayout(srt_in_layout)
        
        l_srt.addWidget(srt_in_group)
        
        self.btn_at_transcribe = QPushButton("2. MP3 -> SRT 자막 생성 시작 (선택 파일)")
        self.btn_at_transcribe.setStyleSheet("background-color: #673AB7; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_transcribe.clicked.connect(lambda: self.start_audio_transcribe("transcribe"))
        l_srt.addWidget(self.btn_at_transcribe)
        l_srt.addStretch()
        
        tab_srt.setLayout(l_srt)
        sub_tabs.addTab(tab_srt, "2. Make SRT")
        
        # SubTab 3: All-in-One
        tab_all = QWidget()
        l_all = QVBoxLayout()
        
        all_in_group = QGroupBox("M4A 파일 선택 (원본)")
        all_in_layout = QHBoxLayout()
        self.at_all_files = QLineEdit()
        self.at_all_files.setPlaceholderText("선택된 파일이 없습니다.")
        btn_all = QPushButton("파일 찾기")
        btn_all.clicked.connect(lambda: self.browse_files(self.at_all_files, "Audio Files (*.m4a)"))
        all_in_layout.addWidget(self.at_all_files)
        all_in_layout.addWidget(btn_all)
        all_in_group.setLayout(all_in_layout)
        
        l_all.addWidget(all_in_group)
        
        l_all.addWidget(QLabel("ℹ️ 선택한 M4A를 MP3로 변환하고 즉시 SRT를 생성합니다."))
        self.btn_at_all = QPushButton("3. M4A -> MP3 -> SRT 일괄 실행 (선택 파일)")
        self.btn_at_all.setStyleSheet("background-color: #E91E63; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_all.clicked.connect(lambda: self.start_audio_transcribe("all"))
        l_all.addWidget(self.btn_at_all)
        l_all.addStretch()
        
        tab_all.setLayout(l_all)
        sub_tabs.addTab(tab_all, "3. All-in-One")
        
        layout.addWidget(sub_tabs)
        
        # Log
        self.at_log = QTextEdit()
        self.at_log.setReadOnly(True)
        self.at_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.at_log)
        
        self.tab_transcribe.setLayout(layout)

    def browse_files(self, line_edit, filter_str):
        files, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", filter_str)
        if files:
            line_edit.setText("; ".join(files))

    def start_audio_transcribe(self, mode):
        # mode: 'convert', 'transcribe', 'all'
        target_files = []
        raw_text = ""
        
        if mode == "convert":
            raw_text = self.at_m4a_files.text().strip()
        elif mode == "transcribe":
            raw_text = self.at_mp3_files.text().strip()
        elif mode == "all":
            raw_text = self.at_all_files.text().strip()
            
        if not raw_text:
            QMessageBox.warning(self, "경고", "선택된 파일이 없습니다.")
            return

        target_files = [f.strip() for f in raw_text.split(";") if f.strip()]
        
        if not target_files:
            QMessageBox.warning(self, "경고", "파일 목록이 유효하지 않습니다.")
            return

        model_name = self.combo_whisper_model.currentText()
        
        self.at_log.append(f"🚀 작업 시작: {mode} (Model: {model_name})")
        self.at_log.append(f"📂 대상: {len(target_files)}개 파일")
        
        # Disable buttons
        self.btn_at_convert.setEnabled(False)
        self.btn_at_transcribe.setEnabled(False)
        self.btn_at_all.setEnabled(False)
        
        self.at_worker = AudioTranscriberWorker(target_files, mode, model_name)
        self.at_worker.log_signal.connect(self.at_log.append)
        self.at_worker.finished.connect(self.on_at_finished)
        self.at_worker.error.connect(self.on_at_error)
        self.at_worker.start()
        
    def on_at_finished(self, msg):
        self.at_log.append(f"🏁 {msg}")
        self.btn_at_convert.setEnabled(True)
        self.btn_at_transcribe.setEnabled(True)
        self.btn_at_all.setEnabled(True)
        
    def on_at_error(self, err):
        self.at_log.append(f"❌ 오류: {err}")
        self.btn_at_convert.setEnabled(True)
        self.btn_at_transcribe.setEnabled(True)
        self.btn_at_all.setEnabled(True)

    def copy_to_clipboard(self, widget):
        text = ""
        if isinstance(widget, QTextEdit):
            text = widget.toPlainText()
        elif isinstance(widget, QLineEdit):
            text = widget.text()
        
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.log_signal.emit("📋 클립보드에 복사되었습니다.")

    def initTabVideoList(self):
        # Main Layout using StackedWidget for page navigation (List <-> Form)
        self.video_list_layout = QVBoxLayout()
        self.video_list_stack = QStackedWidget()
        
        # === Page 1: List View ===
        self.page_list = QWidget()
        list_layout = QVBoxLayout()
        
        # Header
        list_layout.addWidget(QLabel("📋 영상 데이터 목록 (Video Board)"))
        
        # Controls
        btn_layout = QHBoxLayout()
        
        self.btn_new_video = QPushButton("➕ 신규 등록 (New)")
        self.btn_new_video.setFixedWidth(150)
        self.btn_new_video.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_new_video.clicked.connect(lambda: self.switch_to_form_view(None))
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_new_video)
        list_layout.addLayout(btn_layout)
        
        # Table
        self.video_table = QTableWidget()
        self.video_table.setColumnCount(9)
        self.video_table.setHorizontalHeaderLabels([
            "ID", "채널", "제목", "대본", "이미지스크립트", 
            "TTS", "설명", "사용여부", "생성일자"
        ])
        self.video_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.video_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.video_table.cellDoubleClicked.connect(self.on_video_table_double_click)
        
        # Table Header Styling
        header = self.video_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch) # Title is now col 2 
        
        self.video_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b; color: #d4d4d4; gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #333333; color: #ffffff; padding: 4px; border: 1px solid #444;
            }
        """)
        list_layout.addWidget(self.video_table)
        
        # Pagination Controls
        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()
        
        self.btn_prev_page = QPushButton("◀ 이전")
        self.btn_prev_page.setFixedSize(80, 30)
        self.btn_prev_page.clicked.connect(lambda: self.change_page(-1))
        
        self.lbl_page_info = QLabel("1 / 1")
        self.lbl_page_info.setStyleSheet("color: white; font-weight: bold; margin: 0 10px;")
        self.lbl_page_info.setAlignment(Qt.AlignCenter)
        
        self.btn_next_page = QPushButton("다음 ▶")
        self.btn_next_page.setFixedSize(80, 30)
        self.btn_next_page.clicked.connect(lambda: self.change_page(1))
        
        pagination_layout.addWidget(self.btn_prev_page)
        pagination_layout.addWidget(self.lbl_page_info)
        pagination_layout.addWidget(self.btn_next_page)
        pagination_layout.addStretch()
        
        list_layout.addLayout(pagination_layout)
        
        self.page_list.setLayout(list_layout)
        
        # === Page 2: Form View (Create / Edit) ===
        self.page_form = QWidget()
        form_wrapper = QVBoxLayout()
        
        form_group = QGroupBox("영상 데이터 입력/수정")
        input_layout = QGridLayout()
        
        # Channel Selection
        self.combo_channel = QComboBox()
        
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("제목 (Title)")
        
        self.input_script = QTextEdit()
        self.input_script.setPlaceholderText("대본 (Script)")
        self.input_script.setMinimumHeight(100)
        
        self.input_img_script = QTextEdit()
        self.input_img_script.setPlaceholderText("이미지 스크립트 (Image Script)")
        self.input_img_script.setMinimumHeight(100)
        
        self.input_tts_text = QTextEdit()
        self.input_tts_text.setPlaceholderText("TTS 텍스트 (TTS Text)")
        self.input_tts_text.setMinimumHeight(100)
        
        self.input_description = QTextEdit()
        self.input_description.setPlaceholderText("설명 (Description)")
        self.input_description.setMinimumHeight(100)

        # Fields Layout
        input_layout.addWidget(QLabel("채널:"), 0, 0)
        input_layout.addWidget(self.combo_channel, 0, 1)

        input_layout.addWidget(QLabel("제목:"), 1, 0)
        input_layout.addWidget(self.input_title, 1, 1)
        
        input_layout.addWidget(QLabel("대본:"), 2, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_script, 2, 1)
        
        input_layout.addWidget(QLabel("이미지 스크립트:"), 3, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_img_script, 3, 1)
        
        input_layout.addWidget(QLabel("TTS 텍스트:"), 4, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_tts_text, 4, 1)

        input_layout.addWidget(QLabel("설명:"), 5, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_description, 5, 1)
        
        form_group.setLayout(input_layout)
        form_wrapper.addWidget(form_group)
        
        # Form Buttons
        btn_form_layout = QHBoxLayout()
        
        # Copy Buttons Removed
        btn_form_layout.addStretch() # Right alignment
        
        self.btn_cancel_form = QPushButton("목록")
        self.btn_cancel_form.setFixedSize(120, 30)
        self.btn_cancel_form.clicked.connect(self.show_list_view)
        
        self.btn_save_video = QPushButton("저장")
        self.btn_save_video.setFixedSize(120, 30)
        self.btn_save_video.setStyleSheet("font-weight: bold; background-color: #007bff; color: white; border-radius: 5px;")
        self.btn_save_video.clicked.connect(self.save_video_data)
        
        btn_form_layout.addWidget(self.btn_cancel_form)
        btn_form_layout.addWidget(self.btn_save_video)
        
        form_wrapper.addLayout(btn_form_layout)
        self.page_form.setLayout(form_wrapper)
        
        # Add pages to stack
        self.video_list_stack.addWidget(self.page_list) # Index 0
        self.video_list_stack.addWidget(self.page_form) # Index 1
        
        self.video_list_layout.addWidget(self.video_list_stack)
        self.tab_video_list.setLayout(self.video_list_layout)
        
        # State
        self.current_video_id = None
        self.current_page = 1
        self.items_per_page = 15
        self.total_pages = 1
        
        # Init Load
        QTimer.singleShot(1000, self.load_video_list)

    def change_page(self, delta):
        new_page = self.current_page + delta
        if 1 <= new_page <= self.total_pages:
            self.current_page = new_page
            self.load_video_list()

    def show_list_view(self):
        self.video_list_stack.setCurrentIndex(0)
        self.load_video_list()

    def load_channels(self):
        try:
            self.combo_channel.clear()
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT channel_id, channel_name FROM channel WHERE state='1' ORDER BY channel_id ASC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            for row in rows:
                self.combo_channel.addItem(row['channel_name'], row['channel_id'])
                
        except Exception as e:
            self.log_signal.emit(f"채널 로드 오류: {e}")

    def switch_to_form_view(self, video_id=None):
        self.current_video_id = video_id
        
        # Load Channels first
        self.load_channels()
        
        # Clear fields
        self.input_title.clear()
        self.input_script.clear()
        self.input_img_script.clear()
        self.input_tts_text.clear()
        self.input_description.clear()
        
        if video_id is None:
            # Create Mode
            self.btn_save_video.setText("저장")
        else:
            # Edit Mode - Fetch Data
            self.btn_save_video.setText("수정")
            self.load_video_detail(video_id)
            
        self.video_list_stack.setCurrentIndex(1)

    def load_video_detail(self, video_id):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM video WHERE id = %s", (video_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                # Set Channel
                channel_id = row['channel_id']
                index = self.combo_channel.findData(channel_id)
                if index >= 0:
                    self.combo_channel.setCurrentIndex(index)
                
                self.input_title.setText(row['title'] or "")
                self.input_script.setText(row['script'] or "")
                self.input_img_script.setText(row['img_script'] or "")
                self.input_tts_text.setText(row['tts_text'] or "")
                self.input_description.setText(row['description'] or "")
            else:
                QMessageBox.warning(self, "오류", "데이터를 찾을 수 없습니다.")
                self.show_list_view()
                
        except Exception as e:
            QMessageBox.warning(self, "DB 오류", f"상세 조회 실패: {e}")
            self.show_list_view()

    def on_video_table_double_click(self, row, col):
        # Get ID from first column
        item = self.video_table.item(row, 0)
        if item:
            video_id = item.text()
            self.switch_to_form_view(video_id)

    def save_video_data(self):
        title = self.input_title.text().strip()
        script = self.input_script.toPlainText().strip()
        img_script = self.input_img_script.toPlainText().strip()
        tts_text = self.input_tts_text.toPlainText().strip()
        description = self.input_description.toPlainText().strip()
        channel_id = self.combo_channel.currentData()
        
        if not title:
            QMessageBox.warning(self, "입력 오류", "제목은 필수 입력 항목입니다.")
            return

        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor()
            
            if self.current_video_id is None:
                # INSERT
                query = """
                    INSERT INTO video (channel_id, title, script, img_script, tts_text, description, use_yn)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Y')
                """
                cursor.execute(query, (channel_id, title, script, img_script, tts_text, description))
                msg = "새로운 영상 데이터가 등록되었습니다."
            else:
                # UPDATE
                query = """
                    UPDATE video 
                    SET channel_id=%s, title=%s, script=%s, img_script=%s, tts_text=%s, description=%s
                    WHERE id=%s
                """
                cursor.execute(query, (channel_id, title, script, img_script, tts_text, description, self.current_video_id))
                msg = "영상 데이터가 수정되었습니다."
                
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "성공", msg)
            
            # 신규 등록일 때만 목록으로 이동 (수정 시에는 유지)
            if self.current_video_id is None:
                self.show_list_view()
            
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"DB 저장 중 오류 발생:\n{e}")
            self.log_signal.emit(f"DB 저장 오류: {e}")

    def load_video_list(self):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # 1. Get Total Count (Only state='1' channels)
            cursor.execute("SELECT COUNT(*) as cnt FROM video v JOIN channel c ON v.channel_id = c.channel_id WHERE c.state = '1'")
            total_count = cursor.fetchone()['cnt']
            
            # 2. Calculate Pagination
            import math
            self.total_pages = math.ceil(total_count / self.items_per_page)
            if self.total_pages < 1: self.total_pages = 1
            
            # Clamp current page
            if self.current_page > self.total_pages: self.current_page = self.total_pages
            if self.current_page < 1: self.current_page = 1
            
            offset = (self.current_page - 1) * self.items_per_page
            
            # 3. Fetch Data with Limit/Offset (Only state='1' channels)
            query = f"""
                SELECT v.*, c.channel_name 
                FROM video v 
                JOIN channel c ON v.channel_id = c.channel_id 
                WHERE c.state = '1'
                ORDER BY v.id DESC 
                LIMIT {self.items_per_page} OFFSET {offset}
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Update UI
            self.lbl_page_info.setText(f"{self.current_page} / {self.total_pages}")
            self.btn_prev_page.setEnabled(self.current_page > 1)
            self.btn_next_page.setEnabled(self.current_page < self.total_pages)
            
            self.video_table.setRowCount(0)
            
            for row in rows:
                row_idx = self.video_table.rowCount()
                self.video_table.insertRow(row_idx)
                
                # ID
                self.video_table.setItem(row_idx, 0, QTableWidgetItem(str(row['id'])))
                # Channel Name
                self.video_table.setItem(row_idx, 1, QTableWidgetItem(str(row['channel_name'] or '')))
                # Title
                self.video_table.setItem(row_idx, 2, QTableWidgetItem(str(row['title'])))
                
                # Script (Y/N) - Col 3
                script_val = "Y" if row['script'] and str(row['script']).strip() else "N"
                item_script = QTableWidgetItem(script_val)
                item_script.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 3, item_script)
                
                # Img Script (Y/N) - Col 4
                img_val = "Y" if row['img_script'] and str(row['img_script']).strip() else "N"
                item_img = QTableWidgetItem(img_val)
                item_img.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 4, item_img)
                
                # TTS (Y/N) - Col 5
                tts_val = "Y" if row['tts_text'] and str(row['tts_text']).strip() else "N"
                item_tts = QTableWidgetItem(tts_val)
                item_tts.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 5, item_tts)
                
                # Desc (Y/N) - Col 6
                desc_val = "Y" if row['description'] and str(row['description']).strip() else "N"
                item_desc = QTableWidgetItem(desc_val)
                item_desc.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 6, item_desc)
                
                # Use YN - Col 7
                item_use = QTableWidgetItem(str(row['use_yn']))
                item_use.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 7, item_use)
                
                # Created At (YYYY-MM-DD hh:mm) - Col 8
                created_at = row['created_at']
                date_str = ""
                if created_at:
                    if hasattr(created_at, 'strftime'):
                         date_str = created_at.strftime("%Y-%m-%d %H:%M")
                    else:
                         date_str = str(created_at)[:16]
                
                item_date = QTableWidgetItem(date_str)
                item_date.setTextAlignment(Qt.AlignCenter)
                self.video_table.setItem(row_idx, 8, item_date)
            
            self.video_table.resizeColumnsToContents()
            self.video_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch) # Stretch Title

            cursor.close()
            conn.close()
            self.log_signal.emit(f"영상 목록 {len(rows)}개 로드 완료.")
        except Exception as e:
            # QMessageBox.warning(self, "DB Error", f"데이터 로드 중 오류: {e}")
            self.log_signal.emit(f"데이터 로드 중 오류: {e}")

    def initTabPrompt(self):
        # State for Prompt Tab
        self.current_prompt_id = None
        self.current_prompt_page = 1
        self.prompt_items_per_page = 15
        self.prompt_total_pages = 1
        
        # Main Layout using StackedWidget
        self.prompt_layout = QVBoxLayout()
        self.prompt_stack = QStackedWidget()
        
        # === Page 1: List View ===
        self.page_prompt_list = QWidget()
        list_layout = QVBoxLayout()
        
        # Header
        list_layout.addWidget(QLabel("📋 프롬프트/메모 목록"))
        
        
        # Controls
        btn_layout = QHBoxLayout()
        
        # Filter Combo
        self.combo_prompt_filter_type = QComboBox()
        self.combo_prompt_filter_type.setFixedWidth(120)
        self.combo_prompt_filter_type.addItems(['전체', '대본', '설명', '이미지', 'TTS', '기타'])
        self.combo_prompt_filter_type.currentIndexChanged.connect(lambda: self.change_prompt_page(0)) # Reset to page 1 on filter
        
        self.btn_new_prompt = QPushButton("➕ 신규 등록 (New)")
        self.btn_new_prompt.setFixedWidth(150)
        self.btn_new_prompt.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_new_prompt.clicked.connect(lambda: self.switch_to_prompt_form(None))
        
        btn_layout.addWidget(QLabel("구분 필터:"))
        btn_layout.addWidget(self.combo_prompt_filter_type)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_new_prompt)
        list_layout.addLayout(btn_layout)
        
        # Table
        self.prompt_table = QTableWidget()
        self.prompt_table.setColumnCount(6)
        self.prompt_table.setHorizontalHeaderLabels(["ID", "채널", "구분", "제목", "사용", "생성일자"])
        self.prompt_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.prompt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.prompt_table.cellDoubleClicked.connect(self.on_prompt_table_double_click)
        
        # Table Header Styling
        header = self.prompt_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch) # Title Stretch
        
        self.prompt_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b; color: #d4d4d4; gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #333333; color: #ffffff; padding: 4px; border: 1px solid #444;
            }
        """)
        list_layout.addWidget(self.prompt_table)
        
        # Pagination Controls
        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()
        
        self.btn_prev_prompt_page = QPushButton("◀ 이전")
        self.btn_prev_prompt_page.setFixedSize(80, 30)
        self.btn_prev_prompt_page.clicked.connect(lambda: self.change_prompt_page(-1))
        
        self.lbl_prompt_page_info = QLabel("1 / 1")
        self.lbl_prompt_page_info.setStyleSheet("color: white; font-weight: bold; margin: 0 10px;")
        self.lbl_prompt_page_info.setAlignment(Qt.AlignCenter)
        
        self.btn_next_prompt_page = QPushButton("다음 ▶")
        self.btn_next_prompt_page.setFixedSize(80, 30)
        self.btn_next_prompt_page.clicked.connect(lambda: self.change_prompt_page(1))
        
        pagination_layout.addWidget(self.btn_prev_prompt_page)
        pagination_layout.addWidget(self.lbl_prompt_page_info)
        pagination_layout.addWidget(self.btn_next_prompt_page)
        pagination_layout.addStretch()
        
        list_layout.addLayout(pagination_layout)
        self.page_prompt_list.setLayout(list_layout)
        
        # === Page 2: Form View ===
        self.page_prompt_form = QWidget()
        form_wrapper = QVBoxLayout()
        
        form_group = QGroupBox("프롬프트/메모 입력")
        input_layout = QGridLayout()
        
        # Channel Selection
        self.combo_prompt_channel = QComboBox()
        
        # Prompt Type Selection
        self.combo_prompt_type = QComboBox()
        self.combo_prompt_type.addItems(['대본', '설명', '이미지', 'TTS', '기타'])
        
        self.input_prompt_title = QLineEdit()
        self.input_prompt_title.setPlaceholderText("제목 (Title)")
        
        self.input_prompt_contents = QTextEdit()
        self.input_prompt_contents.setPlaceholderText("프롬프트 내용 (Contents)")
        self.input_prompt_contents.setMinimumHeight(200)
        
        # Use YN (Radio Buttons or Checkbox - let's use Checkbox checked by default)
        self.chk_prompt_use = QCheckBox("사용 여부 (Use)")
        self.chk_prompt_use.setChecked(True)
        
        input_layout.addWidget(QLabel("채널:"), 0, 0)
        input_layout.addWidget(self.combo_prompt_channel, 0, 1)
        
        input_layout.addWidget(QLabel("구분:"), 1, 0)
        input_layout.addWidget(self.combo_prompt_type, 1, 1)
        
        input_layout.addWidget(QLabel("제목:"), 2, 0)
        input_layout.addWidget(self.input_prompt_title, 2, 1)
        
        input_layout.addWidget(QLabel("내용:"), 3, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_prompt_contents, 3, 1)
        
        input_layout.addWidget(self.chk_prompt_use, 4, 1)
        
        form_group.setLayout(input_layout)
        form_wrapper.addWidget(form_group)
        
        # Form Buttons
        btn_form_layout = QHBoxLayout()
        
        btn_copy_content = QPushButton("내용 복사")
        btn_copy_content.setFixedSize(100, 30)
        btn_copy_content.clicked.connect(lambda: self.copy_to_clipboard(self.input_prompt_contents))
        btn_form_layout.addWidget(btn_copy_content)
        
        # Download Button
        btn_download_content = QPushButton("다운로드 (.txt)")
        btn_download_content.setFixedSize(120, 30)
        btn_download_content.setStyleSheet("background-color: #17a2b8; color: white;")
        btn_download_content.clicked.connect(self.download_prompt_content)
        btn_form_layout.addWidget(btn_download_content)
        
        btn_form_layout.addStretch()
        
        self.btn_cancel_prompt = QPushButton("목록")
        self.btn_cancel_prompt.setFixedSize(100, 30)
        self.btn_cancel_prompt.clicked.connect(self.show_prompt_list_view)
        
        self.btn_delete_prompt = QPushButton("삭제")
        self.btn_delete_prompt.setFixedSize(100, 30)
        self.btn_delete_prompt.setStyleSheet("background-color: #dc3545; color: white;")
        self.btn_delete_prompt.clicked.connect(self.delete_prompt_data)
        
        self.btn_save_prompt = QPushButton("저장")
        self.btn_save_prompt.setFixedSize(100, 30)
        self.btn_save_prompt.setStyleSheet("background-color: #007bff; color: white;")
        self.btn_save_prompt.clicked.connect(self.save_prompt_data)
        
        btn_form_layout.addWidget(self.btn_cancel_prompt)
        btn_form_layout.addWidget(self.btn_delete_prompt)
        btn_form_layout.addWidget(self.btn_save_prompt)
        
        form_wrapper.addLayout(btn_form_layout)
        self.page_prompt_form.setLayout(form_wrapper)
        
        # Add to stack
        self.prompt_stack.addWidget(self.page_prompt_list)
        self.prompt_stack.addWidget(self.page_prompt_form)
        
        self.prompt_layout.addWidget(self.prompt_stack)
        self.tab_prompt.setLayout(self.prompt_layout)
        
        # Init Load
        QTimer.singleShot(1500, self.load_prompt_list)

    def change_prompt_page(self, delta):
        # 0 delta means reset (e.g. filter change)
        if delta == 0:
             self.current_prompt_page = 1
        else:
            new_page = self.current_prompt_page + delta
            if 1 <= new_page <= self.prompt_total_pages:
                self.current_prompt_page = new_page
        
        self.load_prompt_list()

    def show_prompt_list_view(self):
        self.prompt_stack.setCurrentIndex(0)
        self.load_prompt_list()

    def load_prompt_channels(self):
        try:
            self.combo_prompt_channel.clear()
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT channel_id, channel_name FROM channel WHERE state='1' ORDER BY channel_id ASC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            for row in rows:
                self.combo_prompt_channel.addItem(row['channel_name'], row['channel_id'])
                
        except Exception as e:
            self.log_signal.emit(f"채널 로드 오류: {e}")

    def download_prompt_content(self):
        content = self.input_prompt_contents.toPlainText()
        if not content:
            QMessageBox.warning(self, "경고", "다운로드할 내용이 없습니다.")
            return

        title = self.input_prompt_title.text().strip()
        default_filename = f"{title}.txt" if title else "prompt_content.txt"
        
        # Clean filename
        default_filename = re.sub(r'[\\/*?:"<>|]', "", default_filename)
        
        file_path, _ = QFileDialog.getSaveFileName(self, "텍스트 파일 저장", default_filename, "Text Files (*.txt);;All Files (*)")
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "성공", f"파일이 저장되었습니다:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"파일 저장 중 오류: {e}")

    def switch_to_prompt_form(self, prompt_id=None):
        self.current_prompt_id = prompt_id
        
        # Load Channels
        self.load_prompt_channels()
        
        self.input_prompt_title.clear()
        self.input_prompt_contents.clear()
        self.combo_prompt_type.setCurrentIndex(0)
        self.chk_prompt_use.setChecked(True)
        
        if prompt_id is None:
            # Create
            self.btn_save_prompt.setText("저장")
            self.btn_delete_prompt.setVisible(False)
        else:
            # Edit
            self.btn_save_prompt.setText("수정")
            self.btn_delete_prompt.setVisible(True)
            self.load_prompt_detail(prompt_id)
            
        self.prompt_stack.setCurrentIndex(1)

    def load_prompt_detail(self, prompt_id):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM prompt WHERE id = %s", (prompt_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                # Channel
                channel_id = row['channel_id']
                idx = self.combo_prompt_channel.findData(channel_id)
                if idx >= 0:
                    self.combo_prompt_channel.setCurrentIndex(idx)
                    
                # Type
                p_type = row['prompt_type']
                t_idx = self.combo_prompt_type.findText(p_type)
                if t_idx >= 0:
                    self.combo_prompt_type.setCurrentIndex(t_idx)
                else:
                    self.combo_prompt_type.setCurrentText(p_type) # Allow custom text if combo is editable, but it's not set to editable based on my code. Defaults to 0 if not found is safer or add item.
                
                self.input_prompt_title.setText(row['title'] or "")
                self.input_prompt_contents.setText(row['contents'] or "")
                self.chk_prompt_use.setChecked(row['use_yn'] == 'Y')
            else:
                QMessageBox.warning(self, "오류", "데이터를 찾을 수 없습니다.")
                self.show_prompt_list_view()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"상세 조회 실패: {e}")
            self.show_prompt_list_view()

    def on_prompt_table_double_click(self, row, col):
        item = self.prompt_table.item(row, 0)
        if item:
            prompt_id = item.text()
            self.switch_to_prompt_form(prompt_id)

    def save_prompt_data(self):
        channel_id = self.combo_prompt_channel.currentData()
        prompt_type = self.combo_prompt_type.currentText()
        title = self.input_prompt_title.text().strip()
        contents = self.input_prompt_contents.toPlainText().strip()
        use_yn = 'Y' if self.chk_prompt_use.isChecked() else 'N'
        
        if not title:
            QMessageBox.warning(self, "입력 오류", "제목은 필수 입력 항목입니다.")
            return
            
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor()
            
            if self.current_prompt_id is None:
                # INSERT
                query = """
                    INSERT INTO prompt (channel_id, prompt_type, title, contents, use_yn) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(query, (channel_id, prompt_type, title, contents, use_yn))
                msg = "프롬프트가 저장되었습니다."
            else:
                # UPDATE
                query = """
                    UPDATE prompt 
                    SET channel_id=%s, prompt_type=%s, title=%s, contents=%s, use_yn=%s 
                    WHERE id=%s
                """
                cursor.execute(query, (channel_id, prompt_type, title, contents, use_yn, self.current_prompt_id))
                msg = "프롬프트가 수정되었습니다."
            
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "성공", msg)
            self.show_prompt_list_view()
            
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"DB 저장 중 오류 발생: {e}")

    def delete_prompt_data(self):
        if not self.current_prompt_id:
            return
            
        res = QMessageBox.question(self, "삭제 확인", "정말 삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return
            
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor()
            # Hard delete based on previous pattern, but could be soft delete if requested. 
            # User said "same as video list". Video list doesn't have a delete button in the code I saw (only INSERT/UPDATE).
            # But I added a delete button here. I'll stick to DELETE for now as 'use_yn' is also editable.
            cursor.execute("DELETE FROM prompt WHERE id = %s", (self.current_prompt_id,))
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "삭제", "삭제되었습니다.")
            self.show_prompt_list_view()
        except Exception as e:
            QMessageBox.critical(self, "삭제 오류", f"삭제 실패: {e}")

    def load_prompt_list(self):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            filter_type = self.combo_prompt_filter_type.currentText()
            where_clause = "WHERE c.state = '1'"
            params = []
            
            if filter_type != '전체':
                where_clause += " AND p.prompt_type = %s"
                params.append(filter_type)
            
            # 1. Total Count
            count_query = f"SELECT COUNT(*) as cnt FROM prompt p JOIN channel c ON p.channel_id = c.channel_id {where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()['cnt']
            
            # 2. Pagination
            import math
            self.prompt_total_pages = math.ceil(total_count / self.prompt_items_per_page)
            if self.prompt_total_pages < 1: self.prompt_total_pages = 1
            
            if self.current_prompt_page > self.prompt_total_pages: self.current_prompt_page = self.prompt_total_pages
            if self.current_prompt_page < 1: self.current_prompt_page = 1
            
            offset = (self.current_prompt_page - 1) * self.prompt_items_per_page
            
            # 3. Fetch
            query = f"""
                SELECT p.*, c.channel_name 
                FROM prompt p 
                JOIN channel c ON p.channel_id = c.channel_id 
                {where_clause}
                ORDER BY p.id DESC 
                LIMIT {self.prompt_items_per_page} OFFSET {offset}
            """
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Update UI
            self.lbl_prompt_page_info.setText(f"{self.current_prompt_page} / {self.prompt_total_pages}")
            self.btn_prev_prompt_page.setEnabled(self.current_prompt_page > 1)
            self.btn_next_prompt_page.setEnabled(self.current_prompt_page < self.prompt_total_pages)
            
            self.prompt_table.setRowCount(0)
            for row in rows:
                row_idx = self.prompt_table.rowCount()
                self.prompt_table.insertRow(row_idx)
                
                # ID
                self.prompt_table.setItem(row_idx, 0, QTableWidgetItem(str(row['id'])))
                # Channel
                self.prompt_table.setItem(row_idx, 1, QTableWidgetItem(str(row['channel_name'] or '')))
                # Type
                self.prompt_table.setItem(row_idx, 2, QTableWidgetItem(str(row['prompt_type'] or '')))
                # Title
                self.prompt_table.setItem(row_idx, 3, QTableWidgetItem(str(row['title'] or '')))
                
                # Use YN
                item_use = QTableWidgetItem(str(row['use_yn'] or 'Y'))
                item_use.setTextAlignment(Qt.AlignCenter)
                self.prompt_table.setItem(row_idx, 4, item_use)
                # Date
                created_at = row['created_at']
                date_str = str(created_at)[:16] if created_at else ""
                item_date = QTableWidgetItem(date_str)
                item_date.setTextAlignment(Qt.AlignCenter)
                self.prompt_table.setItem(row_idx, 5, item_date)
            
            self.prompt_table.resizeColumnsToContents()
            self.prompt_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            
            cursor.close()
            conn.close()
        except Exception as e:
            self.log_signal.emit(f"프롬프트 목록 로드 오류: {e}")

    def initTabGoldPrice(self):
        layout = QVBoxLayout()
        
        # Input Folder Selection
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("작업 폴더:"))
        self.txt_gold_input_dir = QLineEdit()
        self.txt_gold_input_dir.setPlaceholderText("mp4, mp3, json 파일이 있는 폴더를 선택하세요")
        input_layout.addWidget(self.txt_gold_input_dir)
        
        btn_sel_input = QPushButton("폴더 선택")
        btn_sel_input.clicked.connect(self.select_gold_input_dir)
        input_layout.addWidget(btn_sel_input)
        layout.addLayout(input_layout)

        btn_layout = QHBoxLayout()
        
        self.btn_fetch_price = QPushButton("금은시세")
        self.btn_fetch_price.setFixedSize(120, 40)
        self.btn_fetch_price.setStyleSheet("font-weight: bold; background-color: #FF9800; color: white;")
        self.btn_fetch_price.clicked.connect(self.fetch_gold_price)
        btn_layout.addWidget(self.btn_fetch_price)

        self.btn_create_gold_video = QPushButton("영상 생성")
        self.btn_create_gold_video.setFixedSize(150, 40)
        self.btn_create_gold_video.setStyleSheet("background-color: #673AB7; color: white; font-weight: bold;")
        self.btn_create_gold_video.clicked.connect(self.create_gold_video)
        btn_layout.addWidget(self.btn_create_gold_video)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.txt_gold_price_result = QTextEdit()
        self.txt_gold_price_result.setPlaceholderText("1. 금은시세 버튼으로 데이터 확인\n2. 폴더 선택 (mp4, mp3, json)\n3. 영상 생성 버튼 클릭")
        layout.addWidget(self.txt_gold_price_result)
        
        self.tab_gold_price.setLayout(layout)
        
        self.gold_data = None 
        self.last_gold_image_path = None
        self.gold_worker = None

    def select_gold_input_dir(self):
        d = QFileDialog.getExistingDirectory(self, "작업 폴더 선택", r"D:\youtube")
        if d:
            self.txt_gold_input_dir.setText(d)

    def fetch_gold_price(self):
        try:
            # Import locally to ensure it's available after install
            from bs4 import BeautifulSoup
            import requests
            
            # --- 1. Domestic Data (Scraping) ---
            url = "https://www.kumsise.com/main/index.php"
            response = requests.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            target_div = soup.find('div', class_='korGold_price')
            
            domestic_text = ""
            
            if target_div:
                # 1. Date
                date_elem = target_div.find('p', class_='pricedate')
                date_str = date_elem.get_text(strip=True) if date_elem else datetime.now().strftime("%Y-%m-%d")
                
                formatted_date = date_str.replace('-', '.')
                domestic_text = f"🌎 국내 시세  - {formatted_date} 기준\n"
                
                self.gold_data = {
                    'date': date_str,
                    'rows': [],
                    'international': {'gold': '-', 'silver': '-'}
                }
                
                # 2. Table Parsing
                rows = target_div.find_all('tr')
                
                for row in rows:
                    cols = row.find_all(['th', 'td'])
                    if not cols: continue
                    
                    has_td = row.find('td')
                    if not has_td: continue
                    
                    if len(cols) >= 3:
                        item_name = cols[0].get_text(strip=True)
                        
                        def parse_price_cell(col):
                            # Price
                            price = col.get_text(strip=True).split('원')[0]
                            if "제품시세" in col.get_text():
                                price = "제품시세 적용"
                                change_txt = ""
                            else:
                                # Change info inside span
                                span = col.find('span')
                                change_txt = span.get_text(" ", strip=True) if span else "" 
                            return price, change_txt
                            
                        price_sell, change_sell = parse_price_cell(cols[1])
                        price_buy, change_buy = parse_price_cell(cols[2])
                        
                        self.gold_data['rows'].append({
                            'name': item_name,
                            'sell_price': price_sell,
                            'sell_change': change_sell,
                            'buy_price': price_buy,
                            'buy_change': change_buy
                        })
                        
                        domestic_text += f"🏷️ {item_name}\n"
                        dct_sell = f" ({change_sell})" if change_sell else ""
                        domestic_text += f"  🔻 팔때: {price_sell}원{dct_sell}\n"
                        dct_buy = f" ({change_buy})" if change_buy else ""
                        domestic_text += f"  🔺 살때: {price_buy}원{dct_buy}\n"
                        domestic_text += "-" * 30 + "\n"
            else:
                domestic_text = "지정된 요소(<div class='korGold_price'>)를 찾을 수 없습니다."
                self.log_signal.emit("⚠️ 금시세 요소를 찾을 수 없습니다.")
                return False

            # --- 2. International Spot Data (Playwright Scraping sdbullion widget) ---
            international_text = ""
            try:
                from playwright.sync_api import sync_playwright
                
                errors = []
                
                def get_prices_with_playwright():
                    with sync_playwright() as p:
                        # Launch headless browser
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page()
                        
                        # Direct Widget URL (found via investigation)
                        # This bypasses the main site wrapper and gives direct access to the ticker HTML
                        widget_url = "https://widget.nfusionsolutions.com/widget/ticker/1/30d00216-cb7b-4935-b6a2-273d495f1d98/7b9cdfda-d566-4d60-8fff-5c817f87db2b"
                        try:
                            page.goto(widget_url, timeout=30000)
                            page.wait_for_selector('table[data-symbol="gold"]', timeout=10000)
                        except Exception as e:
                            errors.append(f"Nav/Wait Error: {str(e)}")
                            browser.close()
                            return ('-', '-'), ('-', '-')

                        def extract_data(symbol_key):
                            try:
                                # Locate the table
                                table = page.locator(f'table[data-symbol="{symbol_key}"]')
                                if not table.count():
                                    return '-', '-'
                                
                                # Ask Price
                                ask_elem = table.locator('.quote-field.ask .value')
                                if not ask_elem.count():
                                    return '-', '-'
                                price_text = ask_elem.inner_text().replace('$', '').replace(',', '').strip()
                                curr_price = float(price_text)
                                
                                # Change Value
                                change_elem = table.locator('.quote-field.oneDayChange .value')
                                change_text = change_elem.inner_text().replace('$', '').replace(',', '').replace('+', '').strip() if change_elem.count() else '0'
                                change_val = float(change_text)
                                
                                # Calculate Yesterday
                                prev_price = curr_price - change_val
                                return f"{curr_price:,.2f}", f"{prev_price:,.2f}"
                                
                            except Exception as e:
                                errors.append(f"{symbol_key}: {str(e)}")
                                return '-', '-'

                        res_gold = extract_data('gold')
                        res_silver = extract_data('silver')
                        
                        browser.close()
                        return res_gold, res_silver

                (intl_gold, hist_gold), (intl_silver, hist_silver) = get_prices_with_playwright()

                if self.gold_data:
                    self.gold_data['international'] = {
                        'gold': intl_gold,
                        'silver': intl_silver,
                        'gold_yesterday': hist_gold,
                        'silver_yesterday': hist_silver,
                        'time': datetime.now().strftime("%Y.%m.%d %H:%M") 
                    }
                
                international_text += f"🌎 국제 시세 (SDBullion/Widget) - {self.gold_data['international']['time']} 기준\n"
                international_text += f"  💰 Gold: ${intl_gold} (어제: ${hist_gold})\n"
                international_text += f"  🥈 Silver: ${intl_silver} (어제: ${hist_silver})\n"
                
                if errors:
                    international_text += "\n⚠️ 스크래핑 오류 상세:\n" + "\n".join(errors) + "\n"
                
            except Exception as e_spot:
                international_text += f"\n⚠️ 국제 시세 조회 실패: {e_spot}\n"

            # --- 3. Combine Results (International FIRST, then Domestic) ---
            final_text = international_text + "\n" + domestic_text
            self.txt_gold_price_result.setText(final_text)
            self.log_signal.emit("✅ 금시세 데이터를 성공적으로 가져왔습니다.")
            return True
                
        except Exception as e:
            self.txt_gold_price_result.setText(f"오류 발생: {e}")
            self.log_signal.emit(f"❌ 금시세 가져오기 실패: {e}")
            return False



    def create_gold_image(self):
        if not self.gold_data:
            # QMessageBox.warning(self, "데이터 없음", "먼저 금시세를 가져와주세요.")
            self.log_signal.emit("⚠️ 금시세 데이터가 없습니다.")
            return False
            
        try:
            # Full HD Portrait (9:16) - Video Overlay Mode
            W, H = 1080, 1920
            image = QImage(W, H, QImage.Format_ARGB32)
            # Transparent Background
            image.fill(Qt.transparent)
            
            painter = QPainter(image)
            try:
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.TextAntialiasing)

                # --- Layout Config ---
                # Top Bar: Title + Date + Intl
                top_bg_h = 280 
                
                # Bottom Panel: Prices
                # --- 2. Bottom Content: Domestic Table ---
                # Calculate required height and position at very bottom
                
                # Height Calc
                # Header (55) + Gap(5) + 5 Rows * (RowH(70) + Gap(2)) + BottomPadding(20)
                # 60 + 5 * 72 + 20 = 80 + 360 = 440 approx
                
                rows_count = len(self.gold_data['rows'])
                header_h = 55
                row_h = 70
                gap = 2
                bottom_padding = 30
                
                total_table_h = header_h + 5 + (rows_count * (row_h + gap)) + bottom_padding
                
                # New Start Y
                bottom_bg_start = H - total_table_h
                bottom_bg_h = total_table_h
                
                # Draw Bottom Background Here (override previous if needed, or just draw new)
                # We need to clear previous bottom rect? No, just draw over or relying on previous fill?
                # Actually, in previous code we drew rect at 'bottom_bg_start' which was fixed 1250.
                # Let's redraw the black rect at correct new position.
                
                # Background Colors
                bg_color = QColor(0, 0, 0, 150) # More transparent

                # Draw Top Background 
                painter.setBrush(bg_color)
                painter.setPen(Qt.NoPen)
                painter.drawRect(0, 0, W, top_bg_h)
                
                # --- 1. Top Content ---
                # Line 1: "오늘의 금시세"
                painter.setFont(QFont("Malgun Gothic", 50, QFont.Bold)) # Increased from 40
                painter.setPen(QColor("#FDB931")) # Gold
                painter.drawText(QRect(0, 20, W, 80), Qt.AlignCenter, "오늘의 금시세")

                # Line 2: Date + Time "2026/01/18 20:20 기준"
                date_str = self.gold_data['date'] 
                time_str = ""
                if 'international' in self.gold_data:
                    intl_t = self.gold_data['international'].get('time', '')
                    if ' ' in intl_t:
                         time_str = intl_t.split(' ')[1]
                if not time_str:
                    time_str = datetime.now().strftime("%H:%M")

                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    date_display = dt.strftime("%Y/%m/%d")
                except:
                    date_display = date_str
                
                full_date_str = f"{date_display} {time_str} 기준"
                
                painter.setFont(QFont("Malgun Gothic", 34, QFont.Bold)) # Increased from 28
                painter.setPen(QColor("#DDDDDD"))
                painter.drawText(QRect(0, 110, W, 50), Qt.AlignCenter, full_date_str)

                # Line 3: International Spot Prices
                if 'international' in self.gold_data:
                    intl = self.gold_data['international']
                    if intl['gold'] != '-':
                        # Split: "국제시세" (White), "Gold $..." (Yellow), "Silver $..." (White)
                        
                        font_label = QFont("Malgun Gothic", 30, QFont.Bold) # Increased from 26
                        painter.setFont(font_label)
                        fm = QFontMetrics(font_label)
                        
                        txt_label = "국제시세  "
                        txt_gold = f"Gold ${intl['gold']}/oz  "
                        txt_silver = f"Silver ${intl['silver']}/oz"
                        
                        w_label = fm.width(txt_label)
                        w_gold = fm.width(txt_gold)
                        w_silver = fm.width(txt_silver)
                        
                        # Center block
                        total_w = w_label + w_gold + w_silver
                        start_x = (W - total_w) // 2
                        
                        y_pos = 180 # Slightly lower to accommodate larger text above
                        h_height = 60
                        
                        # 1. Label
                        painter.setPen(QColor("#FFFFFF"))
                        painter.drawText(QRect(start_x, y_pos, w_label, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_label)
                        
                        # 2. Gold
                        painter.setPen(QColor("#FDB931")) # Yellow/Gold
                        painter.drawText(QRect(start_x + w_label, y_pos, w_gold, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_gold)
                        
                        # 3. Silver
                        painter.setPen(QColor("#FFFFFF"))
                        painter.drawText(QRect(start_x + w_label + w_gold, y_pos, w_silver, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_silver)

                # Draw Bottom Background Here
                painter.setBrush(bg_color)
                painter.setPen(Qt.NoPen)
                painter.drawRect(0, bottom_bg_start, W, bottom_bg_h)
                
                # --- Helper ---
                def draw_glass_rect(rect, radius=15):
                    painter.setBrush(QColor(40, 40, 40, 130)) # More transparent
                    painter.setPen(QPen(QColor(100, 100, 100, 50), 1))
                    painter.drawRoundedRect(rect, radius, radius)
                
                curr_y = bottom_bg_start + 15 # Top padding inside box
                
                # Column Config
                mx = 40
                grid_w = W - (mx * 2)
                col1_w = int(grid_w * 0.25)
                col2_w = int(grid_w * 0.375)
                col3_w = int(grid_w * 0.375)
                
                col1_x = mx
                col2_x = mx + col1_w
                col3_x = mx + col1_w + col2_w
                
                # A. Table Headers
                # Rects
                h_name = QRect(col1_x, curr_y, col1_w, header_h)
                h_sell = QRect(col2_x, curr_y, col2_w, header_h)
                h_buy  = QRect(col3_x, curr_y, col3_w, header_h)
                
                draw_glass_rect(h_name, 10)
                draw_glass_rect(h_sell, 10)
                draw_glass_rect(h_buy, 10)
                
                # Text
                painter.setFont(QFont("Malgun Gothic", 24, QFont.Bold)) # Slightly smaller
                painter.setPen(QColor("#DDDDDD")) 
                
                painter.drawText(h_name, Qt.AlignCenter, "품목")
                painter.drawText(h_sell, Qt.AlignCenter, "파실때") 
                painter.drawText(h_buy, Qt.AlignCenter, "사실때") 
                
                curr_y += header_h + 5 # Gap
                
                # B. Data Rows
                font_name = QFont("Malgun Gothic", 26, QFont.Bold)
                font_price = QFont("Malgun Gothic", 30, QFont.Bold)
                
                for row in self.gold_data['rows']:
                    # Rects
                    r_name = QRect(col1_x, curr_y, col1_w, row_h)
                    r_sell = QRect(col2_x, curr_y, col2_w, row_h)
                    r_buy  = QRect(col3_x, curr_y, col3_w, row_h)
                    
                    # Bg
                    draw_glass_rect(r_name, 10)
                    draw_glass_rect(r_sell, 10)
                    draw_glass_rect(r_buy, 10)
                    
                    # Name
                    painter.setFont(font_name)
                    painter.setPen(QColor("#E0E0E0"))
                    
                    name = row['name']
                    if "돈" not in name: name += "(1돈)"
                    painter.drawText(r_name, Qt.AlignCenter, name)
                    
                    # Prices
                    painter.setFont(font_price)
                    
                    # Middle (User Sells / Shop Buys) -> Header "파실때"
                    painter.setPen(QColor("#FFFFFF"))
                    painter.drawText(r_sell, Qt.AlignCenter, f"{row['sell_price']}") # Corrected to sell_price
                    
                    # Right (User Buys / Shop Sells) -> Header "사실때"
                    painter.setPen(QColor("#FDD017")) 
                    painter.drawText(r_buy, Qt.AlignCenter, f"{row['buy_price']}") # Corrected to buy_price
                    
                    curr_y += row_h + gap
                    
            finally:
                painter.end()
                    

            
            # Save
            filename = "gold_price_premium.png"
            path = os.path.join(os.getcwd(), filename)
            image.save(path)
            self.last_gold_image_path = path

            # Enable video creation
            # self.btn_create_gold_video.setEnabled(True) # Removed
            
            # QMessageBox.information(self, "완료", f"이미지가 재생성되었습니다 (높이 축소형):\n{path}")
            # os.startfile(path) # Don't open automatically in batch mode
            self.log_signal.emit(f"✅ 이미지 생성 완료: {path}")
            return True
            
        except Exception as e:
            # QMessageBox.critical(self, "이미지 생성 실패", f"오류: {e}")
            self.log_signal.emit(f"❌ 이미지 생성 오류: {e}")
            return False

    def create_gold_video(self):
        # 1. Fetch Price Check
        if not self.gold_data:
            if not self.fetch_gold_price():
                QMessageBox.critical(self, "오류", "금시세 데이터를 먼저 가져와주세요.")
                return

        # 2. Create Image Check
        if not self.last_gold_image_path or not os.path.exists(self.last_gold_image_path):
             if not self.create_gold_image():
                return
        
        # 3. Input Dir Check
        if not hasattr(self, 'txt_gold_input_dir'): 
             QMessageBox.critical(self, "오류", "UI 초기화 오류")
             return
        input_dir = self.txt_gold_input_dir.text().strip()
        if not input_dir or not os.path.exists(input_dir):
            QMessageBox.warning(self, "오류", "작업 폴더를 선택해주세요.")
            return
            
        # 4. Find Files (mp4, mp3) - JSON is auto-detected by worker
        try:
            files = os.listdir(input_dir)
            mp4_file = next((f for f in files if f.lower().endswith('.mp4')), None)
            mp3_file = next((f for f in files if f.lower().endswith('.mp3')), None)
            
            if not mp4_file:
                QMessageBox.warning(self, "오류", "폴더에 MP4 영상 파일이 없습니다.")
                return
            if not mp3_file:
                QMessageBox.warning(self, "오류", "폴더에 MP3 오디오 파일이 없습니다.")
                return
                
            base_video_path = os.path.join(input_dir, mp4_file)
            audio_path = os.path.join(input_dir, mp3_file)
            
        except Exception as e:
             QMessageBox.critical(self, "오류", f"파일 검색 중 오류: {e}")
             return

        # Output Setup
        output_dir = r"D:\youtube\shortz"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # --- Step 1: Overlay Gold Image on Base Video ---
        temp_overlay_video = os.path.join(input_dir, f"temp_gold_base_{timestamp}.mp4")
        
        self.txt_gold_price_result.append("\n🎬 [1단계] 금시세 이미지 합성 중...")
        self.log_signal.emit(f"🎬 [1단계] 베이스 영상 생성 시작: {base_video_path}")
        QApplication.processEvents()
        
        ffmpeg_exe = os.path.join(os.getcwd(), "ffmpeg_bin", "ffmpeg.exe")
        if not os.path.exists(ffmpeg_exe): ffmpeg_exe = "ffmpeg"
        
        # Filter: Scale Video to 1080x1920 -> Overlay Image
        # Note: Previous step modified this filter. We reuse it here.
        cmd = [
            ffmpeg_exe, "-y",
            "-i", base_video_path,
            "-i", self.last_gold_image_path,
            "-filter_complex", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v0];[v0][1:v]overlay=0:0[outv]",
            "-map", "[outv]",
            "-map", "0:a?", 
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            temp_overlay_video
        ]
        
        try:
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
            self.log_signal.emit("✅ [1단계] 이미지 합성 완료.")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8') if e.stderr else str(e)
            QMessageBox.critical(self, "오류", f"1단계 영상 생성 실패:\n{err[-300:]}")
            self.log_signal.emit(f"❌ 1단계 실패: {err}")
            return

        # --- Step 2: Merge Overlay-Video + MP3 + Subtitles ---
        self.txt_gold_price_result.append("🎬 [2단계] 자막 및 오디오 합성 중...")
        self.log_signal.emit("🎬 [2단계] 자막/오디오 합성 작업을 시작합니다.")
        QApplication.processEvents()
        
        final_output_path = os.path.join(output_dir, f"Gold_Shorts_{timestamp}.mp4")
        
        # Style (Default - Malgun Gothic, 70px White with Black Outline)
        style = {
            "font_family": "Malgun Gothic",
            "font_size": 70,
            "text_color": "#FFFFFF",
            "outline_color": "#000000",
            "bg_color": "Transparent",
            "use_outline": True,
            "use_bg": False
        }
        
        try:
            from youtube_worker_video import SingleVideoWorker
            
            # Note: We pass the 'temp_overlay_video' as the 'img_path'. 
            self.gold_worker = SingleVideoWorker(
                img_path=temp_overlay_video,
                audio_path=audio_path,
                output_path=final_output_path,
                subtitles=None, # Worker auto-detects JSON by audio filename
                style=style,
                volume=1.0,
                trim_end=0.0,
                is_shorts=True
            )
            
            self.gold_worker.log_signal.connect(self.log_signal.emit)
            self.gold_worker.finished.connect(lambda msg, t: self.on_gold_video_finished(msg, final_output_path, temp_overlay_video))
            self.gold_worker.error.connect(lambda err: QMessageBox.critical(self, "오류", f"2단계 작업 실패: {err}"))
            
            self.gold_worker.start()
            
            # Disable button during processing
            self.btn_create_gold_video.setEnabled(False)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"워커 시작 실패: {e}")

    def on_gold_video_finished(self, msg, output_path, temp_path):
        self.txt_gold_price_result.append(f"✅ 모든 작업 완료!\n저장위치: {output_path}")
        self.log_signal.emit(f"✅ 최종 완료: {msg}")
        self.btn_create_gold_video.setEnabled(True)
        QMessageBox.information(self, "성공", f"영상 생성이 완료되었습니다.\n{output_path}")
        
        # Clean up temp
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
            
        try:
            os.startfile(os.path.dirname(output_path))
        except: pass


class BatchVideoEffectWorker(VideoMergerWorker):
    def __init__(self, input_dir, output_dir, style=None, volume=1.0, trim_end=0.0, effect_config=None):
        # 부모 생성자 호출 (경로는 input_dir로 설정)
        super().__init__(input_dir, input_dir, output_dir, subtitles=None, style=style, volume=volume, trim_end=trim_end)
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.effect_config = effect_config # 부모 process_single_video가 이 속성을 참조하여 효과 적용
        self.is_running = True
        self.executor = None

    def stop(self):
        self.is_running = False
        if self.executor:
            # 보류 중인 작업 취소
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.log_signal.emit("🛑 중지 요청: 남은 대기 작업을 취소합니다.")
        
    def run(self):
        start_time = time.time()
        try:
            # MP3 파일 검색
            if not os.path.exists(self.input_dir):
                self.error.emit(f"입력 폴더 없음: {self.input_dir}")
                return

            all_files = os.listdir(self.input_dir)
            mp3_files = [f for f in all_files if f.lower().endswith('.mp3')]
            
            if not mp3_files:
                self.error.emit("입력 폴더에 .mp3 파일이 없습니다.")
                return
                
            # 자연스러운 정렬 (1.mp3, 2.mp3, 10.mp3)
            mp3_files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)])
            
            total = len(mp3_files)
            success_count = 0
            
            # 1. 큐 준비 (Task 생성 및 효과 배정)
            import random
            tasks = []
            
            # 효과 타입 다양화 (ZoomIn, ZoomOut, PanLR, PanRL)
            effect_types = []
            if self.effect_config and self.effect_config.get('random'):
                # 4가지 효과를 골고루 섞어서 리스트 생성
                base_types = [
                    {'type': 1, 'start_scale': 1.0, 'end_scale': 1.15}, # Zoom In
                    {'type': 1, 'start_scale': 1.15, 'end_scale': 1.0}, # Zoom Out
                    {'type': 2, 'start_scale': 1.1}, # Pan L->R
                    {'type': 3, 'start_scale': 1.1}  # Pan R->L
                ]
                # 파일 수만큼 충분히 리스트 확장 후 섞기
                while len(effect_types) < len(mp3_files):
                    shuffled_base = base_types.copy()
                    random.shuffle(shuffled_base)
                    effect_types.extend(shuffled_base)
            
            self.log_signal.emit("📋 [작업 계획] 효과 배정 결과:")
            for idx, mp3 in enumerate(mp3_files):
                base_name = os.path.splitext(mp3)[0]
                audio_path = os.path.join(self.input_dir, mp3)
                output_path = os.path.join(self.output_dir, f"{base_name}.mp4")
                
                # 이미지 찾기
                img_path = None
                for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                    check = os.path.join(self.input_dir, base_name + ext)
                    if os.path.exists(check):
                        img_path = check
                        break
                
                if not img_path:
                    self.log_signal.emit(f"   ⚠️ [{base_name}] 이미지 없음 (건너뜀)")
                    continue

                # 효과 배정 (랜덤 모드일 경우 준비된 리스트에서 추출)
                current_effect = None
                if self.effect_config:
                    if self.effect_config.get('random'):
                        current_effect = self.effect_config.copy()
                        assigned = effect_types[idx]
                        current_effect.update(assigned)
                        
                        eff_name = "Zoom In" if assigned['type']==1 and assigned['end_scale'] > 1.0 else \
                                   "Zoom Out" if assigned['type']==1 else \
                                   "Pan L->R" if assigned['type']==2 else "Pan R->L"
                        self.log_signal.emit(f"   - {base_name}: {eff_name}")
                    else:
                        current_effect = self.effect_config.copy()
                
                tasks.append((img_path, audio_path, output_path, base_name, current_effect))

            if not tasks:
                self.error.emit("처리할 유효한 태스크가 없습니다.")
                return

            self.log_signal.emit(f"🚀 총 {len(tasks)}개의 영상 처리를 시작합니다. (병렬 처리 모드: 2개씩)")
            
            # 2. ThreadPoolExecutor 병렬 실행
            import multiprocessing
            import concurrent.futures
            max_workers = min(2, multiprocessing.cpu_count()) # 8K 고화질 처리로 인해 메모리 보호차원 2개 제한
            success_count = 0
            
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
            with self.executor as executor:
                # {future: (base_name, output_path)}
                future_to_info = {executor.submit(self.process_single_video, task): task[3] for task in tasks}
                
                for future in concurrent.futures.as_completed(future_to_info):
                    if not self.is_running:
                        self.log_signal.emit("🛑 사용자에 의해 중지되었습니다.")
                        break
                    task_base = future_to_info[future]
                    try:
                        res = future.result()
                        if res:
                            success_count += 1
                            # 성공 로그는 process_single_video 내부나 여기서 출력
                        else:
                            self.log_signal.emit(f"❌ [{task_base}] 처리 실패")
                    except Exception as e:
                        self.log_signal.emit(f"❌ [{task_base}] 오류 발생: {e}")
            
            elapsed = time.time() - start_time
            self.finished.emit(f"전체 작업 완료: {success_count}/{total} 성공", elapsed)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"오류: {e}")

class VideoConcatenatorWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, video_dir, output_file, watermark_path=None):
        super().__init__()
        self.video_dir = video_dir
        self.output_file = output_file
        self.watermark_path = watermark_path
        self.process = None

    def stop(self):
        if self.process:
            self.process.kill()
            self.log_signal.emit("🛑 FFmpeg 프로세스를 강제 종료합니다.")

    def run(self):
        start_time = time.time()
        temp_list_path = ""
        try:
            self.log_signal.emit("📂 영상 합치기 준비 중 (Concat Demuxer Mode)...")
            
            ffmpeg_exe = "ffmpeg"
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except: pass

            if not os.path.exists(self.video_dir):
                self.error.emit("입력 폴더가 존재하지 않습니다.")
                return

            all_files = os.listdir(self.video_dir)
            files = [os.path.join(self.video_dir, f) for f in all_files if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
            
            if not files:
                self.error.emit("합칠 영상 파일이 없습니다.")
                return

            files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)])
            
            self.log_signal.emit(f"🔢 총 {len(files)}개의 영상 파일 발견.")

            temp_list_path = os.path.join(self.video_dir, f"concat_list_{int(time.time())}.txt")
            with open(temp_list_path, "w", encoding='utf-8') as f:
                for vid_path in files:
                    safe_path = vid_path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
            
            command = [ffmpeg_exe]
            command.extend(["-y", "-f", "concat", "-safe", "0", "-i", temp_list_path])
            
            map_options = []
            
            if self.watermark_path and os.path.exists(self.watermark_path):
                command.extend(["-i", self.watermark_path])
                filter_complex = "[1:v]scale=100:-1[wm];[0:v][wm]overlay=20:20[v_out]"
                command.extend(["-filter_complex", filter_complex])
                map_options = ["-map", "[v_out]", "-map", "0:a"]
            else:
                map_options = ["-map", "0"]

            command.extend(map_options)
            
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            
            command.append(self.output_file)
            
            self.log_signal.emit(f"🚀 합치기 실행 (파일 리스트 방식)...")
            
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            self.process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                encoding='utf-8',
                creationflags=creation_flags
            )
            
            stdout, stderr = self.process.communicate()
            
            if self.process.returncode != 0:
                self.error.emit(f"❌ FFmpeg 오류: {stderr}")
            else:
                elapsed = time.time() - start_time
                self.finished.emit(f"✅ 완료: {os.path.basename(self.output_file)}", elapsed)
            
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if temp_list_path and os.path.exists(temp_list_path):
                try: os.remove(temp_list_path)
                except: pass

def exception_hook(exctype, value, tb):
    tb_str = "".join(traceback.format_exception(exctype, value, tb))
    print(tb_str)
    # Use static method for QMessageBox if possible, or just create it
    QMessageBox.critical(None, "Fatal Error", f"심각한 오류가 발생했습니다:\n\n{tb_str}")
    sys.exit(1)

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            # 쉼표, %, 공백 제거 후 비교
            v1 = float(self.text().replace(',', '').replace('%', '').strip())
            v2 = float(other.text().replace(',', '').replace('%', '').strip())
            return v1 < v2
        except ValueError:
            # 숫자가 아니면 문자열 비교
            return super().__lt__(other)

class FTPUploadWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, host, port, user, passwd, local_dir, remote_dir):
        super().__init__()
        self.host = host
        self.port = int(port) if port.isdigit() else 21
        self.user = user
        self.passwd = passwd
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        


    def run(self):
        ftp = None
        try:
            self.log_signal.emit(f"🔌 연결 중: {self.host}:{self.port}")
            ftp = ftplib.FTP()
            ftp.encoding = 'utf-8' # 한글 경로 지원을 위해 UTF-8 설정
            ftp.connect(self.host, self.port, timeout=30)
            ftp.login(self.user, self.passwd)
            self.log_signal.emit("✅ 로그인 성공")
            
            # Base Remote Dir Ensure
            # self.remote_dir 경로가 없을 수도 있고, 여러 계단일 수도 있음.
            # 가장 안전한 방법: 루트부터 하나씩 이동/생성
            # 하지만 간단히: cwd 시도 -> 실패시 mkd 시도 (단, 재귀적 생성함수 사용 권장)
            
            if not self.ensure_remote_dir(ftp, self.remote_dir):
                self.error.emit(f"서버 경로 이동/생성 실패: {self.remote_dir}")
                ftp.quit()
                return
            
            self.log_signal.emit(f"📂 작업 폴더 준비 완료: {self.remote_dir}")

            # Walk Local Directory
            total_uploaded = 0
            
            for root, dirs, files in os.walk(self.local_dir):
                # Calculate current remote path
                rel_path = os.path.relpath(root, self.local_dir)
                
                if rel_path == '.':
                    current_remote = self.remote_dir
                else:
                    # Windows path separator(\) to FTP standard(/)
                    normalized_rel = rel_path.replace(os.sep, '/')
                    current_remote = f"{self.remote_dir}/{normalized_rel}"
                    # Check/Create subdirectory
                    if not self.ensure_remote_dir(ftp, current_remote):
                        self.log_signal.emit(f"   ⚠️ 폴더 생성 실패, 건너뜀: {current_remote}")
                        continue
                
                # CWD to current remote (just to be safe, or use full path in stor?)
                # storbinary with relative filename usually puts in CWD.
                # So we CWD.
                try:
                    ftp.cwd(current_remote)
                except Exception as e:
                    self.log_signal.emit(f"   ⚠️ 폴더 이동 실패: {current_remote} ({e})")
                    continue

                for filename in files:
                    local_file_path = os.path.join(root, filename)
                    self.log_signal.emit(f"⬆️ 업로드 중: {filename}")
                    
                    try:
                        with open(local_file_path, "rb") as f:
                            ftp.storbinary(f"STOR {filename}", f)
                            total_uploaded += 1
                    except Exception as e:
                        self.log_signal.emit(f"   ❌ 실패: {filename} ({e})")
            
            ftp.quit()
            self.finished.emit(f"전체 업로드 완료 (총 {total_uploaded}개 파일)")
            
        except Exception as e:
            self.error.emit(f"FTP 오류: {e}")
            if ftp:
                try: ftp.quit()
                except: pass

    def ensure_remote_dir(self, ftp, path):
        """
        경로가 존재하면 True, 없으면 생성 후 True, 실패 시 False
        계층적 경로 생성 지원 (예: /a/b/c)
        """
        # 절대 경로 처리를 위해 시작점 초기화
        original_cwd = ftp.pwd()
        
        try:
            ftp.cwd(path)
            # 이미 존재함
            return True
        except ftplib.error_perm:
            pass # 생성 필요
        
        # 다시 원래 위치로 (혹시 cwd 실패하며 이상한데 갔을까봐)
        # 하지만 error_perm이면 이동 안했을 것임.
        
        # 계층적 생성 시도
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        
        # 시작 위치 잡기
        if path.startswith('/'):
            ftp.cwd('/') # 루트에서 시작
            
        for part in parts:
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                try:
                    ftp.mkd(part)
                    ftp.cwd(part)
                except Exception as e:
                    # print(f"MKD Fail: {part} in {ftp.pwd()} >> {e}")
                    return False
        
        return True

class FTPLoginWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, host, port, user, passwd):
        super().__init__()
        self.host = host
        self.port = int(port) if port.isdigit() else 21
        self.user = user
        self.passwd = passwd
        
    def run(self):
        ftp = None
        try:
            self.log_signal.emit(f"🔌 연결 시도: {self.host}:{self.port}")
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port, timeout=15)
            ftp.login(self.user, self.passwd)
            
            welcome = ftp.getwelcome()
            self.log_signal.emit(f"✅ 로그인 성공! (Welcome: {welcome})")
            
            # Simple list to verify permissions
            self.log_signal.emit("📂 루트 디렉토리 목록 조회:")
            files = []
            try:
                ftp.dir(files.append) # Use dir instead of nlst for detail
                for line in files[:5]: # Show top 5
                    self.log_signal.emit(f"   {line}")
                if len(files) > 5:
                    self.log_signal.emit(f"   ... (총 {len(files)}개 항목)")
            except:
                self.log_signal.emit("   (목록 조회 권한이 없거나 실패함)")
                
            ftp.quit()
            self.finished.emit("접속 테스트 성공")
            
        except Exception as e:
            self.error.emit(str(e))
            if ftp:
                try: ftp.quit()
                except: pass


class AudioTranscriberWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, target_files, mode, model_name):
        super().__init__()
        self.target_files = target_files # List of absolute file paths
        self.mode = mode # 'convert', 'transcribe', 'all'
        self.model_name = model_name

    def run(self):
        job_start_time = time.time()
        try:
            # 1. FFmpeg Check (Common)
            # 1. FFmpeg Check & Setup for Whisper
            try:
                import imageio_ffmpeg
                import shutil
                
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                # ImageIO provides 'ffmpeg-win-x86_64-vX.X.exe', but Whisper calls 'ffmpeg'
                # So we must create a copy named 'ffmpeg.exe' in a folder and add to PATH
                
                base_dir = os.path.dirname(os.path.abspath(__file__))
                bin_dir = os.path.join(base_dir, "ffmpeg_bin")
                os.makedirs(bin_dir, exist_ok=True)
                
                target_fft_exe = os.path.join(bin_dir, "ffmpeg.exe")
                
                if not os.path.exists(target_fft_exe):
                    self.log_signal.emit(f"   ℹ️ FFmpeg 복사 중... ({ffmpeg_exe} -> {target_fft_exe})")
                    shutil.copy2(ffmpeg_exe, target_fft_exe)
                    
                # Add bin_dir to PATH
                if bin_dir not in os.environ["PATH"]:
                    self.log_signal.emit(f"   ℹ️ PATH 추가: {bin_dir}")
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
                    
            except ImportError:
                ffmpeg_exe = "ffmpeg"
                self.log_signal.emit("   ⚠️ imageio_ffmpeg 모듈 없음. 시스템 FFmpeg 사용.")

            # 2. Whisper Load (if needed)
            whisper_model = None
            if self.mode in ["transcribe", "all"]:
                try:
                    import whisper
                    try:
                        import torch
                        device = "cuda" if torch.cuda.is_available() else "cpu"
                        self.log_signal.emit(f"   ℹ️ Whisper 로드 중 ({self.model_name}, Device: {device})...")
                    except:
                        device = "cpu"
                        
                    whisper_model = whisper.load_model(self.model_name, device=device)
                    self.log_signal.emit("   ✅ Whisper 모델 로드 완료")
                except ImportError:
                    self.error.emit("openai-whisper 모듈이 설치되지 않았습니다. (pip install openai-whisper)")
                    return
                except Exception as e:
                    self.error.emit(f"Whisper 로드 실패: {e}")
                    return

            self.target_files.sort()
            
            # --- M4A -> MP3 ---
            if self.mode in ["convert", "all"]:
                # Filter M4A from the selected list
                m4a_files = [f for f in self.target_files if f.lower().endswith('.m4a')]

                if not m4a_files:
                    self.log_signal.emit("⚠️ 선택된 파일 중 M4A 파일이 없습니다.")
                else:
                    self.log_signal.emit(f"🔄 M4A -> MP3 변환 시작 (총 {len(m4a_files)}개)")
                    creation_flags = 0x08000000 if os.name == 'nt' else 0
                    
                    for in_path in m4a_files:
                        in_dir = os.path.dirname(in_path)
                        base = os.path.splitext(os.path.basename(in_path))[0]
                        out_path = os.path.join(in_dir, base + ".mp3")
                        f_name = os.path.basename(in_path)
                        
                        if os.path.exists(out_path):
                            self.log_signal.emit(f"   ⏩ 이미 존재함: {base}.mp3")
                            continue
                            
                        self.log_signal.emit(f"   converting: {f_name} ...")
                        cmd = [
                            ffmpeg_exe, "-y", "-i", in_path,
                            "-c:a", "libmp3lame", "-b:a", "64k",
                            out_path
                        ]
                        try:
                            subprocess.run(
                                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True, creationflags=creation_flags
                            )
                        except Exception as e:
                            self.log_signal.emit(f"   ❌ 변환 실패 ({f_name}): {e}")

            # --- MP3 -> SRT ---
            if self.mode in ["transcribe", "all"]:
                mp3_files = []
                
                if self.mode == "all":
                    # In 'all' mode, we infer mp3 paths from the input m4a files
                    m4a_files = [f for f in self.target_files if f.lower().endswith('.m4a')]
                    for m4a in m4a_files:
                        base = os.path.splitext(m4a)[0]
                        mp3_files.append(base + ".mp3")
                else:
                     # In 'transcribe' mode, use the selected mp3 files
                     mp3_files = [f for f in self.target_files if f.lower().endswith('.mp3')]
                
                # Filter out non-existent mp3s (e.g. if conversion failed)
                mp3_files = [f for f in mp3_files if os.path.exists(f)]

                if not mp3_files:
                    self.log_signal.emit("⚠️ MP3 파일이 없습니다 (변환이 실패했거나 선택되지 않음).")
                else:
                    self.log_signal.emit(f"📝 MP3 -> SRT 작업 시작 (총 {len(mp3_files)}개)")
                    for in_path in mp3_files:
                        in_dir = os.path.dirname(in_path)
                        f_name = os.path.basename(in_path)
                        base = os.path.splitext(f_name)[0]
                        srt_path = os.path.join(in_dir, base + ".srt")
                        
                        if os.path.exists(srt_path):
                            self.log_signal.emit(f"   ⚠️ 이미 존재함 (덮어쓰기): {base}.srt")
                            # continue # 덮어쓰기 위해 continue 제거
                            
                        self.log_signal.emit(f"   Transcribing: {f_name} ...")
                        try:
                            # Transcribe
                            # Transcribe
                            result = whisper_model.transcribe(in_path)
                            detected_lang = result.get('language', 'en')
                            limit_len = 16 if detected_lang == 'ja' else 26
                            self.log_signal.emit(f"   ℹ️ 감지된 언어: {detected_lang}, 자막 제한: {limit_len}자")
                            
                            # Write SRT
                            # Write SRT
                            with open(srt_path, "w", encoding="utf-8") as srt_file:
                                srt_index = 1
                                for segment in result["segments"]:
                                    original_text = segment["text"].strip()
                                    start_time = segment["start"]
                                    end_time = segment["end"]
                                    
                                    # 제한 체크 및 분할
                                    if len(original_text) > limit_len:
                                        # 스마트 청크 나누기 (문장 부호 보전 및 문맥 고려)
                                        chunks = []
                                        remain_text = original_text
                                        
                                        delims = ['。', '、', '.', ',', '!', '?', ' ']
                                        max_len = limit_len
                                        
                                        while len(remain_text) > max_len:
                                            cut_idx = -1
                                            
                                            # 1. max_len 안에서 가장 뒤에 있는 구분자(문장부호/공백) 찾기
                                            candidate = remain_text[:max_len]
                                            for i in range(len(candidate) - 1, -1, -1):
                                                if candidate[i] in delims:
                                                    cut_idx = i
                                                    break
                                            
                                            if cut_idx != -1:
                                                # 구분자 뒤에서 자름 (구분자 포함)
                                                chunks.append(remain_text[:cut_idx+1].strip())
                                                remain_text = remain_text[cut_idx+1:].strip()
                                            else:
                                                # 구분자가 없으면 강제 분할하되, 뒤따라오는 문장부호 확인 (부호 고아 방지)
                                                curr_cut = max_len
                                                
                                                # 오버플로우 허용 (최대 3글자까지 문장부호라면 포함)
                                                for _ in range(3):
                                                    if curr_cut < len(remain_text) and remain_text[curr_cut] in delims:
                                                        curr_cut += 1
                                                    else:
                                                        break
                                                
                                                chunks.append(remain_text[:curr_cut].strip())
                                                remain_text = remain_text[curr_cut:].strip()
                                        
                                        if remain_text:
                                            chunks.append(remain_text.strip())
                                        
                                        # 빈 청크 제거
                                        chunks = [c for c in chunks if c]
                                        
                                        # 시간 배분 (글자 수 비율로)
                                        total_duration = end_time - start_time
                                        total_chars = len(original_text.replace(" ", "")) # 공백 제외 글자수 기준이 더 정확할 수 있음
                                        if total_chars == 0: total_chars = 1
                                        
                                        current_start = start_time
                                        
                                        for i, chunk in enumerate(chunks):
                                            chunk_len = len(chunk.replace(" ", ""))
                                            if chunk_len == 0: chunk_len = 1
                                            
                                            # 비례 시간 계산
                                            duration = total_duration * (chunk_len / total_chars)
                                            
                                            # 마지막 청크는 끝 시간 고정 (오차 보정)
                                            if i == len(chunks) - 1:
                                                chunk_end = end_time
                                            else:
                                                chunk_end = current_start + duration
                                            
                                            # SRT 쓰기
                                            srt_file.write(f"{srt_index}\n")
                                            srt_file.write(f"{self.format_timestamp(current_start)} --> {self.format_timestamp(chunk_end)}\n")
                                            srt_file.write(f"{chunk}\n\n")
                                            
                                            srt_index += 1
                                            current_start = chunk_end
                                            
                                    else:
                                        # 26자 이하: 그대로 출력
                                        srt_file.write(f"{srt_index}\n")
                                        srt_file.write(f"{self.format_timestamp(start_time)} --> {self.format_timestamp(end_time)}\n")
                                        srt_file.write(f"{original_text}\n\n")
                                        srt_index += 1
                                    
                            self.log_signal.emit(f"   ✅ 완료: {base}.srt")
                            
                        except Exception as e:
                            self.log_signal.emit(f"   ❌ 실패 ({f_name}): {e}")

            elapsed_time = time.time() - job_start_time
            self.finished.emit(f"모든 작업이 완료되었습니다. (소요시간: {elapsed_time:.2f}초)")

        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")
            import traceback
            traceback.print_exc()

    def format_timestamp(self, seconds):
        # Convert seconds to HH:MM:SS,mmm
        millis = int((seconds - int(seconds)) * 1000)
        seconds = int(seconds)
        minutes = seconds // 60
        hours = minutes // 60
        minutes = minutes % 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


class AudioToVideoWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)
    
    def __init__(self, target_dir, style):
        super().__init__()
        self.target_dir = target_dir
        self.style = style # Dictionary of style settings
        self.temp_sub_dir = os.path.join(self.target_dir, "temp_subs")

    def run(self):
        import shutil
        import time
        start_time = time.time()
        try:
            # Create Temp Dir

            # 1. FFmpeg setup
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = "ffmpeg"
                
            files = os.listdir(self.target_dir)
            mp3_files = [f for f in files if f.lower().endswith('.mp3')]
            
            if not mp3_files:
                self.log_signal.emit("⚠️ MP3 파일이 없습니다.")
                self.finished.emit("작업 없음")
                return

            total = len(mp3_files)
            count = 0
            
            # Temp Folder for ASS or Lists
            # Ensure it exists
            if not os.path.exists(self.temp_sub_dir):
                os.makedirs(self.temp_sub_dir)

            for mp3 in mp3_files:
                base_name = os.path.splitext(mp3)[0]
                srt_file = base_name + ".srt"
                srt_path = os.path.join(self.target_dir, srt_file)
                mp3_path = os.path.join(self.target_dir, mp3)
                # 최종 mp4 파일명을 final_video.mp4로 고정
                out_path = os.path.join(self.target_dir, "final_video.mp4")
                
                if not os.path.exists(srt_path):
                    self.log_signal.emit(f"⚠️ SRT 없음 건너뜀: {srt_file}")
                    continue
                
                self.log_signal.emit(f"🎬 생성 중 (High Speed): {base_name}.mp4 ...")
                
                # 1. Get Duration
                # We need audio duration to fill images until end.
                # Let's use ffprobe.
                duration = self.get_audio_duration(ffmpeg_exe, mp3_path)
                if duration == 0:
                    self.log_signal.emit(f"   ⚠️ 오디오 길이 확인 불가: {mp3}")
                    continue

                # 2. Parse SRT for Subtitles and Images
                segments = self.parse_srt(srt_path)

                # [Restore] 이미지 처리 로직 (사용자 요청: SRT 인덱스번호와 매칭)
                TARGET_W, TARGET_H = 1920, 1080
                FPS = 30
                
                # 3. Create Concat List for Images
                concat_list_path = os.path.join(self.temp_sub_dir, f"inputs_{base_name}.txt")
                
                # Logic: Find images matching SRT indices
                checkpoints = []
                for seg in segments:
                    idx = seg['index']
                    t = seg['start']
                    img_name = None
                    for ext in ['.jpg', '.png', '.webp', '.jpeg']:
                        check = os.path.join(self.target_dir, f"{idx}{ext}")
                        if os.path.exists(check):
                            img_name = check
                            break
                    
                    if img_name:
                        checkpoints.append((t, img_name))
                
                checkpoints.sort(key=lambda x: x[0])
                
                # 4. Process Images to Ensure Unified Resolution (1920x1080)
                unified_img_dir = os.path.join(self.temp_sub_dir, f"scaled_{base_name}")
                os.makedirs(unified_img_dir, exist_ok=True)
                
                processed_checkpoints = []
                for t, img_p in checkpoints:
                    img_name_only = os.path.basename(img_p)
                    scaled_p = os.path.join(unified_img_dir, f"proc_{img_name_only}.jpg")
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
                            # PNG로 저장하여 검정 배경(PNG)과의 포맷 불일치 방지
                            final_bg.save(scaled_p, "PNG")
                            processed_checkpoints.append((t, scaled_p))
                    except:
                        pass
                
                # Sync Fix: Ensure timeline starts at 0.0
                if processed_checkpoints:
                    processed_checkpoints.sort(key=lambda x: x[0])
                    if processed_checkpoints[0][0] > 0.001:
                        black_p = os.path.join(self.temp_sub_dir, "black_gap_start.png")
                        if not os.path.exists(black_p):
                            Image.new('RGB', (TARGET_W, TARGET_H), (0,0,0)).save(black_p)
                        processed_checkpoints.insert(0, (0.0, black_p))
                else:
                    black_p = os.path.join(self.temp_sub_dir, "black_full.png")
                    if not os.path.exists(black_p):
                        Image.new('RGB', (TARGET_W, TARGET_H), (0,0,0)).save(black_p)
                    processed_checkpoints = [(0.0, black_p)]

                # Write Concat List
                with open(concat_list_path, "w", encoding='utf-8') as f:
                    for i, (t, img_p) in enumerate(processed_checkpoints):
                        safe_p = img_p.replace("\\", "/")
                        if i < len(processed_checkpoints) - 1:
                            dur = processed_checkpoints[i+1][0] - t
                            f.write(f"file '{safe_p}'\n")
                            f.write(f"duration {dur:.3f}\n")
                        else:
                            dur = duration - t
                            if dur < 0.1: dur = 0.5
                            f.write(f"file '{safe_p}'\n")
                            f.write(f"duration {dur:.3f}\n")
                    # FFmpeg requirement: repeat last file
                    f.write(f"file '{processed_checkpoints[-1][1].replace('\\', '/')}'\n")
                
                self.fix_concat_file(concat_list_path)

                
                # 5. Generate Subtitle PNGs (Identical to Video Composite)
                FPS = 30
                subtitle_inputs = [] # (path, start_t, end_t)
                temp_files = []
                
                if segments:
                    for idx_s, seg in enumerate(segments):
                        text = seg['text']
                        start_t = seg['start']
                        end_t = seg['end']
                        
                        if start_t >= duration: continue
                        real_end = min(end_t, duration)
                        if real_end <= start_t:
                            real_end = min(start_t + 3.0, duration)
                        if real_end <= start_t: continue
                        
                        # Gap Filling
                        if idx_s < len(segments) - 1:
                            next_start = segments[idx_s+1]['start']
                            if 0 < (next_start - real_end) < 0.5:
                                real_end = next_start
                                
                        rgba_arr = self.create_text_image(text, (TARGET_W, TARGET_H))
                        sub_filename = f"sub_{base_name}_{idx_s}.png"
                        sub_path = os.path.join(self.temp_sub_dir, sub_filename)
                        
                        result_img = Image.fromarray(rgba_arr, 'RGBA')
                        result_img.save(sub_path)
                        temp_files.append(sub_path)
                        subtitle_inputs.append((sub_path, start_t, real_end))

                # 6. Run FFmpeg
                cmd = [ffmpeg_exe, "-y", "-fflags", "+genpts"]
                # Input 0: Image Concat List
                cmd.extend(["-f", "concat", "-safe", "0", "-i", concat_list_path])
                cmd.extend(["-i", mp3_path]) # Input 1 (Audio)
                # [Input 2] Subtitles Concat
                concat_sub_list_p = os.path.join(self.temp_sub_dir, f"subs_{base_name}.txt")
                transparent_p = os.path.join(self.temp_sub_dir, "transparent.png")
                if not os.path.exists(transparent_p):
                    Image.new('RGBA', (TARGET_W, TARGET_H), (0,0,0,0)).save(transparent_p)

                with open(concat_sub_list_p, "w", encoding='utf-8') as f:
                    last_time_s = 0.0
                    for s_p, s_t, e_t in subtitle_inputs:
                        gap = s_t - last_time_s
                        if gap > 0.001:
                            f.write(f"file '{transparent_p}'\n")
                            f.write(f"duration {gap:.3f}\n")
                        dur = e_t - s_t
                        if dur < 0.001: dur = 0.1
                        f.write(f"file '{s_p}'\n")
                        f.write(f"duration {dur:.3f}\n")
                        last_time_s = e_t
                    if last_time_s < duration:
                        f.write(f"file '{transparent_p}'\n")
                        f.write(f"duration {duration - last_time_s:.3f}\n")
                    if subtitle_inputs:
                        # FFmpeg concat demuxer: Last entry should have a small duration or be repeated for EOF
                        f.write(f"file '{subtitle_inputs[-1][0]}'\n")
                        f.write(f"duration 0.1\n") # Minimal duration to trigger EOF
                
                self.fix_concat_file(concat_sub_list_p)
                cmd.extend(["-f", "concat", "-safe", "0", "-i", concat_sub_list_p])
                
                # 이미지 스트림과 자막 스트림의 포맷을 yuv420p로 강제 통일하여 메모리 누수 방지
                filter_parts = [f"[0:v]format=yuv420p,fps={FPS},setsar=1:1[v_bg]"]
                final_v_label = "[v_bg]"
                if subtitle_inputs:
                    # overlay 가동 시 포맷 지정으로 안정성 향상
                    filter_parts.append(f"[2:v]format=yuva420p,fps={FPS},setsar=1:1[v_sub]")
                    filter_parts.append(f"{final_v_label}[v_sub]overlay=format=yuv420[v_final]")
                    final_v_label = "[v_final]"
                
                filter_parts.append(f"[1:a]volume=1.0,atrim=duration={duration},aresample=48000:async=1[a_out]")
                filter_complex = ";".join(filter_parts)
                
                # [NEW] filter_complex script path (Fix WinError 206)
                filter_script_p = os.path.join(self.temp_sub_dir, f"filter_{base_name}.txt")
                with open(filter_script_p, "w", encoding='utf-8') as f:
                    f.write(filter_complex)
                temp_files.append(filter_script_p)

                cmd.extend(["-filter_complex_script", filter_script_p])
                cmd.extend(["-map", final_v_label, "-map", "[a_out]"])
                
                # Encoding Options (Memory & Stability Optimized)
                cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"])
                cmd.extend(["-max_muxing_queue_size", "1024", "-threads", "0"]) # 큐 사이즈 확장으로 버퍼 오류 방지
                cmd.extend(["-fps_mode", "cfr"])
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                cmd.append(out_path)
                
                creation_flags = 0x08000000 if os.name == 'nt' else 0
                self.log_signal.emit(f"   🚀 인코딩 중... (Video Composite 스타일 자막 적용)")
                
                res = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False, creationflags=creation_flags, cwd=self.target_dir
                )
                
                if res.returncode != 0:
                    err_msg = res.stderr.decode('utf-8', errors='ignore')
                    # Show last 1000 chars to skip header and see actual error
                    display_err = err_msg[-1000:] if len(err_msg) > 1000 else err_msg
                    self.log_signal.emit(f"   ❌ FFmpeg 오류: {display_err}")
                else:
                    self.log_signal.emit(f"   ✅ 완료: {base_name}.mp4")
                    count += 1
                
                # Cleanup sub PNGs
                for tmp in temp_files:
                    try: os.remove(tmp)
                    except: pass
            
            # Cleanup Temp Dir
            if os.path.exists(self.temp_sub_dir):
                try:
                    shutil.rmtree(self.temp_sub_dir)
                    self.log_signal.emit("   🧹 임시 파일 삭제 완료")
                except Exception as e:
                    self.log_signal.emit(f"   ⚠️ 임시 폴더 삭제 실패: {e}")
 
            elapsed = time.time() - start_time
            self.finished.emit(f"작업 완료: 총 {count}개 영상 생성", elapsed)
 
        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Ensure cleanup even on error
            if os.path.exists(self.temp_sub_dir):
                try: shutil.rmtree(self.temp_sub_dir)
                except: pass
 
    def create_text_image(self, text, size):
        # 폰트 이미지 캐싱
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
        target_bottom = height - margin_bottom
        target_top = target_bottom - box_h
        
        dy = target_top - bg_rect.top()
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
            import math
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
        import numpy as np
        arr = np.frombuffer(ptr, np.uint8).copy().reshape((height, width, 4))
        
        if len(self._text_cache) > 50:
            self._text_cache.clear()
        self._text_cache[cache_key] = arr
        return arr

    def get_audio_duration(self, ffmpeg_exe, mp3_path):
        # Use ffprobe logic or simple ffmpeg -i call parsing
        cmd = [ffmpeg_exe, "-i", mp3_path]
        try:
            r = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            # Duration: 00:00:10.50,
            out = r.stderr.decode('utf-8')
            import re
            m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
            if m:
                h, m, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                return h*3600 + m*60 + s
        except:
            pass
        return 0.0

    def fix_concat_file(self, path):
        # Read lines, ensure single quotes frame properties, replace backslash with forward slash
        print("DEBUG: Executing clean fix_concat_file")
        lines = []
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith('file'):
                    # format: file 'path'
                    parts = line.split("'", 2)
                    if len(parts) >= 2:
                        raw_path = parts[1]
                        fixed_path = raw_path.replace('\\', '/')
                        f.write(f"file '{fixed_path}'\n")
                    else:
                        f.write(line)
                else:
                    f.write(line)



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
        # HH:MM:SS,mmm
        t_str = t_str.replace(',', '.')
        parts = t_str.split(':')
        
        if len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h*3600 + m*60 + s
        return 0.0





if __name__ == '__main__':
    sys.excepthook = exception_hook
    app = QApplication(sys.argv)
    
    # 다크 테마 적용
    # Modern Dark Theme Setup
    app.setStyle("Fusion")
    
    # 1. Color Palette (VS Code Dark Theme Inspired)
    dark_palette = QPalette()
    
    # Backgrounds
    dark_palette.setColor(QPalette.Window, QColor(30, 30, 30))         # Main Window Background
    dark_palette.setColor(QPalette.WindowText, QColor(220, 220, 220))  # Main Text
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))           # Input Fields Background
    dark_palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))  # Alternate Background
    dark_palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))    # Tooltip Background
    dark_palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220)) # Tooltip Text
    dark_palette.setColor(QPalette.Text, QColor(220, 220, 220))        # Input Text
    
    # Buttons & Inputs
    dark_palette.setColor(QPalette.Button, QColor(45, 45, 45))         # Button Background
    dark_palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))  # Button Text
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    
    # Links & Highlights
    dark_palette.setColor(QPalette.Link, QColor(0, 122, 204))          # Link Color
    dark_palette.setColor(QPalette.Highlight, QColor(0, 122, 204))     # Selection Background
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)          # Selection Text
    
    # Disabled States
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Disabled, QPalette.Button, QColor(35, 35, 35))
    
    app.setPalette(dark_palette)
    
    # 2. Modern Stylesheet (QSS)
    app.setStyleSheet("""
        /* Global Reset */
        * {
            outline: none;
        }
        
        /* Tooltips */
        QToolTip { 
            color: #dcdcdc; 
            background-color: #252526; 
            border: 1px solid #3e3e42; 
        }

        /* Message Boxes */
        QMessageBox {
            background-color: #1e1e1e;
        }
        QMessageBox QLabel {
            color: #dcdcdc;
        }

        /* Input Fields (LineEdit, TextEdit, SpinBox, etc.) */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #2d2d2d; /* Slightly lighter than base for visibility */
            color: #dcdcdc;
            border: 1px solid #3e3e42;
            border-radius: 4px;
            padding: 5px;
            selection-background-color: #007acc;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
            border: 1px solid #007acc;
            background-color: #1e1e1e;
        }
        
        /* Buttons - Modern Flat Look */
        QPushButton {
            background-color: #0e639c; /* Primary Blue */
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1177bb;
        }
        QPushButton:pressed {
            background-color: #094771;
            padding-top: 7px; /* Press effect */
            padding-left: 17px;
        }
        QPushButton:disabled {
            background-color: #3e3e42;
            color: #888888;
        }
        
        /* Group Box */
        QGroupBox {
            border: 1px solid #454545;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #007acc; /* Accent Color for Titles */
        }
        
        /* Tab Widget */
        QTabWidget::pane {
            border: 1px solid #3e3e42;
            background-color: #1e1e1e;
            top: -1px; /* Align with tab bar */
        }
        QTabBar::tab {
            background: #2d2d2d;
            color: #aaaaaa;
            padding: 8px 20px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background: #1e1e1e;
            color: #ffffff;
            border-top: 2px solid #007acc; /* Top Accent Line */
            font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
            background: #3e3e40;
            color: #ffffff;
        }
        
        /* Table Widget */
        QTableWidget {
            gridline-color: #333333;
            background-color: #1e1e1e;
            selection-background-color: #094771; /* Darker Blue Selection */
            selection-color: white;
            border: 1px solid #3e3e42;
        }
        QHeaderView::section {
            background-color: #252526;
            color: #dcdcdc;
            padding: 6px;
            border: 1px solid #333333;
            font-weight: bold;
        }
        QHeaderView::section:horizontal {
            border-bottom: 2px solid #3e3e42;
        }
        QHeaderView::section:vertical {
            border-right: 2px solid #3e3e42;
        }
        
        /* Scrollbars (Webkit-like style for Qt) */
        QScrollBar:vertical {
            border: none;
            background: #1e1e1e;
            width: 14px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #424242;
            min-height: 20px;
            border-radius: 7px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover {
            background: #686868;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        QScrollBar:horizontal {
            border: none;
            background: #1e1e1e;
            height: 14px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:horizontal {
            background: #424242;
            min-width: 20px;
            border-radius: 7px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #686868;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """)
    
    try:
        ex = MainApp()
        ex.show()
        sys.exit(app.exec_())
    except Exception as e:
        msg = traceback.format_exc()
        QMessageBox.critical(None, "Error in MainApp", f"MainApp 실행 중 오류:\n\n{msg}")