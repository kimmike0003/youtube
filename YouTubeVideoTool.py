import os
# Intel Fortran runtime error (200) fix for Windows
os.environ["FOR_IGNORE_EXCEPTIONS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import math
import requests
import subprocess
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
from PIL import Image
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                             QPushButton, QLabel, QFileDialog, QHBoxLayout, 
                             QTabWidget, QComboBox, QSlider, QSpinBox, QGroupBox, QDoubleSpinBox, 
                             QFormLayout, QLineEdit, QGridLayout, QCheckBox, QMessageBox, QColorDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStackedWidget,
                             QSizePolicy, QScrollArea, QFrame)
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
from PIL import Image, ImageDraw, ImageFont
# Monkey Patch for Pillow > 9.x not having ANTIALIAS, which MoviePy needs
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS


import moviepy.editor as mpe
from youtube_workers import YoutubeSearchWorker, ImageLoadWorker


from youtube_worker_ai import GenSparkMultiTabWorker, GrokMultiTabWorker, WhiskMultiTabWorker
from youtube_worker_video import VideoMergerWorker, SingleVideoWorker, VideoDubbingWorker, BatchDubbingWorker, VideoConcatenatorWorker, AudioSrtMergerWorker
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
        
        # 기본 스타일 즉시 적용 (윈도우 기본 파란색 방지)
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
        
        btn.clicked.connect(lambda checked=False: self.setCurrentIndex(self.stack.indexOf(widget)))
        
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
                # Selected Style (Deep Grey / Point Color)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #444444;
                        color: #ffffff;
                        border: 1px solid #0078d4;
                        font-weight: bold;
                        font-family: 'Malgun Gothic';
                        font-size: 13px;
                    }
                """)
            else:
                btn.setChecked(False)
                # Normal Style (Dark Grey)
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
        self.font_path_map = {}
        self.initUI()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_timer_display)

    def initUI(self):
        self.setWindowTitle("YouTube Video Creator Master")
        self.setGeometry(100, 50, 1280, 900) # 너비를 1280px로 확대
        layout = QVBoxLayout()

        # 메인 레이아웃을 커스텀 탭 위젯으로 변경
        self.tabs = CustomTabWidget()
        layout.addWidget(self.tabs)

        # ========== 1단 (Upper Row): 6개 ==========
        
        # 1. ElevenLabs TTS
        self.tab2 = QWidget()
        self.initTab2()
        self.tabs.addTab(self.tab2, "ElevenLabs TTS")

        # 2. GenSpark Image
        self.tab1 = QWidget()
        self.initTab1()
        self.tabs.addTab(self.tab1, "Ganspark Image")

        # 2-1. Whisk Image
        self.tab_whisk_image = QWidget()
        self.initTabWhiskImage()
        self.tabs.addTab(self.tab_whisk_image, "Whisk Image")

        # 3. 그록생성
        self.tab_grok_gen = QWidget()
        self.initTabGrokGen()
        self.tabs.addTab(self.tab_grok_gen, "그록생성")

        # 4. 영상 생성 (Audio To Video)
        self.tab_audio_video = QWidget()
        self.initTabAudioToVideo()
        self.tabs.addTab(self.tab_audio_video, "영상생성")

        # 5. 영상합치기 (원래 최종영상)
        self.tab4 = QWidget()
        self.initTab4()
        self.tabs.addTab(self.tab4, "영상합치기")

        # 6. 썸네일
        self.tab_thumbnail = QWidget()
        self.initTabThumbnail()
        self.tabs.addTab(self.tab_thumbnail, "썸네일")

        # ========== 2단 (Lower Row): 6개 ==========

        # 7. 금시세
        self.tab_gold_price = QWidget()
        self.initTabGoldPrice()
        self.tabs.addTab(self.tab_gold_price, "금시세")

        # 8. 금은숏츠
        self.tab_shorts = QWidget()
        self.initTabShorts()
        self.tabs.addTab(self.tab_shorts, "금은숏츠")

        # 9. 경제대본
        self.tab_video_list = QWidget()
        self.initTabVideoList()
        self.tabs.addTab(self.tab_video_list, "경제대본")

        # 10. 대본 자르기
        self.tab_script_split = QWidget()
        self.initTabScriptSplit()
        self.tabs.addTab(self.tab_script_split, "대본 자르기")

        # 11. 프롬프트
        self.tab_prompt = QWidget()
        self.initTabPrompt()
        self.tabs.addTab(self.tab_prompt, "프롬프트")

        # 12. Audio Transcribe
        self.tab_transcribe = QWidget()
        self.initTabAudioTranscribe()
        self.tabs.addTab(self.tab_transcribe, "Audio Transcribe")




        # 17. YouTube 분석
        self.tab7 = QWidget()
        self.initTab7()
        self.tabs.addTab(self.tab7, "YouTube 분석")

        # ========== Hidden 처리된 탭들 (초기화는 하되 addTab은 하지 않음) ==========
        
        self.tab3 = QWidget() # 자막설정
        self.initTab3()
        
        self.tab5 = QWidget() # 영상효과
        self.initTab5()
        
        self.tab6 = QWidget() # 그록동영상
        self.initTab6()

        self.setLayout(layout)
        
        # 모든 UI 초기화 후 폰트 및 색상 인디케이터 갱신
        self.load_custom_fonts()
        self.update_color_indicators()

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

    def initTabWhiskImage(self):
        layout = QVBoxLayout()

        self.whisk_status_label = QLabel("1단계: 브라우저를 먼저 준비해 주세요.")
        self.whisk_status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.whisk_status_label)

        self.whisk_timer_label = QLabel("소요 시간: 00:00:00")
        layout.addWidget(self.whisk_timer_label)

        # 저장 경로 설정
        path_layout = QHBoxLayout()
        self.whisk_image_path_edit = QLineEdit(r"D:\youtube")
        self.whisk_image_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_image = QPushButton("찾아보기")
        btn_browse_image.clicked.connect(lambda: self.browse_image_path_custom(self.whisk_image_path_edit))
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.whisk_image_path_edit)
        path_layout.addWidget(btn_browse_image)
        layout.addLayout(path_layout)

        # 버튼들
        self.btn_whisk_prepare = QPushButton("🌐 1. Whisk 브라우저 및 탭 준비")
        self.btn_whisk_prepare.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_whisk_prepare.clicked.connect(self.launch_whisk_browser)
        layout.addWidget(self.btn_whisk_prepare)

        # 텍스트 입력창 추가
        layout.addWidget(QLabel(" Whisk 이미지 프롬프트 입력:"))
        self.whisk_image_prompt_input = QTextEdit()
        self.whisk_image_prompt_input.setPlaceholderText("프롬프트 내용을 입력하세요.\n1. {프롬프트1}\n2. {프롬프트2}")
        self.whisk_image_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.whisk_image_prompt_input)

        btn_h_layout = QHBoxLayout()
        self.btn_whisk_start = QPushButton("🚀 2. Whisk 이미지 생성 시작")
        self.btn_whisk_start.setEnabled(True)
        self.btn_whisk_start.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_whisk_start.clicked.connect(self.start_whisk_automation)
        
        self.btn_whisk_stop = QPushButton("🛑 중지")
        self.btn_whisk_stop.setEnabled(False)
        self.btn_whisk_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_whisk_stop.clicked.connect(self.stop_whisk_automation)

        btn_h_layout.addWidget(self.btn_whisk_start)
        btn_h_layout.addWidget(self.btn_whisk_stop)
        layout.addLayout(btn_h_layout)

        # 압축 버튼 추가
        self.btn_whisk_compress = QPushButton("🗜️ 3. 이미지 압축 (용량 줄이기)")
        self.btn_whisk_compress.setStyleSheet("height: 50px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 8px; margin-top: 5px;")
        self.btn_whisk_compress.clicked.connect(lambda: self.compress_images(dir_path=self.whisk_image_path_edit.text().strip()))
        layout.addWidget(self.btn_whisk_compress)

        # 로그 디스플레이
        self.whisk_log_display = QTextEdit()
        self.whisk_log_display.setReadOnly(True)
        self.whisk_log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        self.whisk_log_display.setMaximumHeight(150)
        layout.addWidget(self.whisk_log_display)

        self.tab_whisk_image.setLayout(layout)


    # Removed initTabImageFX

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
        
        # Merge JSON/MP3 Checkbox
        self.chk_merge_mp3_json = QCheckBox("다운로드 후 merge.json, merge.mp3 만들기")
        self.chk_merge_mp3_json.setChecked(True)
        form_layout.addRow("", self.chk_merge_mp3_json)

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

        # 오디오 병합 버튼 (테스트용)
        self.btn_merge_audio = QPushButton("🔗 오디오 병합 (Merge Audio Only)")
        self.btn_merge_audio.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #17a2b8; color: white; border-radius: 10px; }
            QPushButton:hover { background-color: #138496; }
        """)
        self.btn_merge_audio.clicked.connect(self.merge_existing_audio)

        btn_layout.addWidget(self.btn_generate_tts)
        btn_layout.addWidget(self.btn_stop_tts)
        btn_layout.addWidget(self.btn_merge_audio)
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

        # 기본 폰트 로드는 MainApp.initUI 끝에서 일괄 수행
        # self.load_custom_fonts()
        # self.update_color_indicators()

        self.tab3.setLayout(layout)

    def create_style_group(self):
        # 스타일 설정 그룹
        group = QGroupBox("자막 스타일 설정")
        style_layout = QGridLayout()
        
        self.chk_use_sub = QCheckBox("자막 사용")
        self.chk_use_sub.setChecked(True)
        style_layout.addWidget(self.chk_use_sub, 0, 0)
        
        # 랜덤 효과 체크박스 및 1번 고정 체크박스
        h_eff_layout = QHBoxLayout()
        self.chk_random_effect = QCheckBox("랜덤 화면 효과 (Zoom/Pan 1.0->1.1)")
        self.chk_random_effect.setChecked(False)
        self.chk_fix_first_img = QCheckBox("1번 이미지 고정 (줌/팬 방지)")
        self.chk_fix_first_img.setChecked(True)
        h_eff_layout.addWidget(self.chk_random_effect)
        h_eff_layout.addWidget(self.chk_fix_first_img)
        style_layout.addLayout(h_eff_layout, 0, 1, 1, 3)

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
        self.spin_font_size.setValue(75)
        
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
        self.checkbox_use_bg.setChecked(False)
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
        btn_browse_input.clicked.connect(self.browse_concat_input_folder)
        
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
        self.watermark_path.setText("")
        self.watermark_path.setPlaceholderText("워터마크 이미지 (선택 사항)")
        btn_browse_wm = QPushButton("워터마크 선택")
        btn_browse_wm.clicked.connect(lambda: self.browse_single_file(self.watermark_path, "Images (*.png *.jpg)"))
        
        path_layout.addWidget(QLabel("워터마크(로고):"), 2, 0)
        path_layout.addWidget(self.watermark_path, 2, 1)
        path_layout.addWidget(btn_browse_wm, 2, 2)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Auto SRT Checkbox
        self.chk_auto_srt = QCheckBox("영상 합치기 완료 후 자동으로 SRT 자막 생성 (Whisper)")
        self.chk_auto_srt.setChecked(False)
        self.chk_auto_srt.setStyleSheet("font-weight: bold; color: #E91E63; margin-top: 10px;")
        layout.addWidget(self.chk_auto_srt)

        # [New] Compression and Gap Settings
        options_group = QGroupBox("추가 옵션 및 압축 설정")
        options_layout = QGridLayout()

        # Quality (CRF)
        options_layout.addWidget(QLabel("압축 품질 (낮을수록 고화질):"), 0, 0)
        self.combo_concat_quality = QComboBox()
        self.combo_concat_quality.addItem("고화질 (CRF 23)", 23)
        self.combo_concat_quality.addItem("표준 (CRF 28)", 28)
        self.combo_concat_quality.addItem("저용량 (CRF 32)", 32)
        self.combo_concat_quality.addItem("최저용량 (CRF 36)", 36)
        self.combo_concat_quality.setCurrentIndex(1)
        options_layout.addWidget(self.combo_concat_quality, 0, 1)


        # Gap Duration
        options_layout.addWidget(QLabel("영상 사이 간격 (초):"), 1, 0)
        self.spin_concat_gap = QDoubleSpinBox()
        self.spin_concat_gap.setRange(0.0, 2.0)
        self.spin_concat_gap.setSingleStep(0.1)
        self.spin_concat_gap.setValue(0.0) # 기본 0.0으로 변경 (멈춤 현상 가능성 차단)
        options_layout.addWidget(self.spin_concat_gap, 1, 1)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)


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

        # 출력 폴더 (숨김 처리 - 자동경로 사용)
        self.eff_output_dir = QLineEdit()
        self.eff_output_dir.setPlaceholderText("결과물 ../output 에 자동 저장")
        self.eff_output_dir.setReadOnly(True)
        # btn_browse_out = QPushButton("출력 폴더 선택")
        # btn_browse_out.clicked.connect(lambda: self.browse_folder(self.eff_output_dir))
        
        file_layout.addWidget(QLabel("저장 경로:"), 1, 0)
        file_layout.addWidget(self.eff_output_dir, 1, 1)
        # file_layout.addWidget(btn_browse_out, 1, 2)

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
        self.chk_random_effect.setChecked(True)
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
            use_random_effects=use_random,
            fix_first_img=self.chk_fix_first_img.isChecked() # New Parameter
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

        # [Fix] 워터마크 경로가 유효한 파일인지 확인 (아니면 무시)
        final_wm_path = None
        if wm_path:
            if os.path.isfile(wm_path):
                final_wm_path = wm_path
                self.concat_log.append(f"ℹ️ 워터마크 적용: {os.path.basename(final_wm_path)}")
            else:
                self.concat_log.append(f"ℹ️ 워터마크 경로가 비어있거나 파일이 아닙니다. 워터마크 없이 진행합니다.")
        
        self.btn_start_concat.setEnabled(False)
        self.btn_stop_concat.setEnabled(True)
        self.concat_log.append("⏳ 영상 합치기 작업을 시작합니다...")

        # Get settings
        crf = self.combo_concat_quality.currentData()
        gap = self.spin_concat_gap.value()

        self.concat_worker = VideoConcatenatorWorker(in_dir, out_file, final_wm_path, crf=crf) # Updated (CPU Only)
        self.concat_worker.gap_duration = gap # Pass gap
        self.concat_worker.log_signal.connect(self.concat_log.append)
        self.concat_worker.finished.connect(self.on_video_concat_finished)
        self.concat_worker.error.connect(lambda e: [self.concat_log.append(f"❌ 오류: {e}"), self.btn_start_concat.setEnabled(True), self.btn_stop_concat.setEnabled(False)])
        self.concat_worker.start()

    def on_video_concat_finished(self, msg, elapsed):
        self.btn_start_concat.setEnabled(True)
        self.btn_stop_concat.setEnabled(False)
        h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
        self.concat_log.append(f"{msg} (소요 시간: {h:02d}:{m:02d}:{s:02d})")

        # Auto SRT Logic
        if hasattr(self, 'chk_auto_srt') and self.chk_auto_srt.isChecked():
            out_file = self.concat_output_file.text().strip()
            if os.path.exists(out_file):
                self.concat_log.append("🔄 자동 SRT 생성 시작...")
                
                # Use model from Audio Transcribe tab if available, else 'base'
                model_name = "base"
                if hasattr(self, 'combo_whisper_model'):
                    model_name = self.combo_whisper_model.currentText()
                
                # Reuse AudioTranscriberWorker
                # mode='transcribe' accepts mp3/mp4
                self.auto_srt_worker = AudioTranscriberWorker([out_file], "transcribe", model_name, False)
                
                # Connect signals to concat_log
                self.auto_srt_worker.log_signal.connect(self.concat_log.append)
                self.auto_srt_worker.finished.connect(lambda m: self.concat_log.append(f"✅ SRT 생성 완료: {m}"))
                self.auto_srt_worker.error.connect(lambda e: self.concat_log.append(f"❌ SRT 생성 실패: {e}"))
                self.auto_srt_worker.start()
            else:
                 self.concat_log.append("⚠️ 결과 파일을 찾을 수 없어 SRT 생성을 건너뜁니다.")

    def update_color_indicators(self):
        # 1. 메인 자막 탭 인디케이터
        if hasattr(self, 'ind_text_color'):
            self.ind_text_color.setStyleSheet(f"background-color: {self.color_text}; border: 1px solid white;")
            out_col = self.color_outline if self.color_outline.lower() != "none" else "transparent"
            if not self.checkbox_use_outline.isChecked(): out_col = "transparent"
            self.ind_outline_color.setStyleSheet(f"background-color: {out_col}; border: 1px solid white;")
            
            bg_opacity = self.slider_bg_opacity.value() / 100.0
            if self.color_bg.lower() == "transparent" or not self.checkbox_use_bg.isChecked():
                self.ind_bg_color.setStyleSheet("background-color: transparent; border: 1px solid white;")
            else:
                col = QColor(self.color_bg)
                self.ind_bg_color.setStyleSheet(f"background-color: rgba({col.red()}, {col.green()}, {col.blue()}, {bg_opacity}); border: 1px solid white;")

        # 2. ATV(영상 제작) 탭 인디케이터
        if hasattr(self, 'atv_ind_text_color'):
            self.atv_ind_text_color.setStyleSheet(f"background-color: {self.atv_color_text}; border: 1px solid white;")
            atv_out_col = self.atv_color_outline if self.atv_color_outline.lower() != "none" else "transparent"
            if not self.atv_checkbox_use_outline.isChecked(): atv_out_col = "transparent"
            self.atv_ind_outline_color.setStyleSheet(f"background-color: {atv_out_col}; border: 1px solid white;")
            
            atv_bg_opacity = self.atv_slider_bg_opacity.value() / 100.0
            if self.atv_color_bg.lower() == "transparent" or not self.atv_checkbox_use_bg.isChecked():
                self.atv_ind_bg_color.setStyleSheet("background-color: transparent; border: 1px solid white;")
            else:
                col = QColor(self.atv_color_bg)
                self.atv_ind_bg_color.setStyleSheet(f"background-color: rgba({col.red()}, {col.green()}, {col.blue()}, {atv_bg_opacity}); border: 1px solid white;")

    def pick_color(self, target):
        from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            if target == 'text': self.color_text = hex_color
            elif target == 'outline': self.color_outline = hex_color
            elif target == 'bg': self.color_bg = hex_color
            elif target == 'atv_text': self.atv_color_text = hex_color
            elif target == 'atv_outline': self.atv_color_outline = hex_color
            elif target == 'atv_bg': self.atv_color_bg = hex_color
            self.update_color_indicators()

    def parse_subtitles(self, text):
        # returns { major_id: [ {"original": "...", "tts": "..."}, ... ] }
        subs = collections.defaultdict(list)
        
        # 1. 전역 정규식 파싱 (Global Regex Parsing)
        # 한 줄에 여러 항목이 있거나 줄바꿈이 불규칙해도 "ID 원본: ... TTS: ..." 패턴을 모두 찾아냄.
        # 패턴: 12-34 원본: ... TTS: ... (다음 ID 패턴이나 헤더가 나오기 전까지)
        # Lookahead: 다음 "숫자-숫자 원본:" 혹은 "숫자. {}" 헤더 혹은 문장 끝
        
        # 신규 패턴: 1. 원본: ... TTS: ... 또는 1-1 원본: ... TTS: ...
        # (?:^|\s) 는 항 행의 시작이나 공백 뒤에 숫자가 오도록 함
        regex_pattern = r'(?:^|\s)(\d+)(?:[.\-])(\d+)?\s*원본:(.*?)\s*TTS:(.*?)(?=\s*\d+[\.\-]\d*\s*원본:|\s*\d+\.\s*\{|$)'
        
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

    def browse_concat_input_folder(self):
        path = QFileDialog.getExistingDirectory(self, "영상 폴더 선택")
        if path:
            self.concat_input_dir.setText(path)
            
            # 최종 파일 경로 자동 설정 (선택된 폴더/final_video.mp4)
            # 사용자 요청: 최종파일도 입력 영상 폴더 선택 하면 거기 부터 시작 해야 됨
            final_path = os.path.join(path, "final_video.mp4")
            self.concat_output_file.setText(final_path)
            
            # 워터마크 경로 자동 설정 (선택된 폴더/logo.png 등)
            # 사용자 요청: 워터마크경로도 동일하게
            found_logo = None
            for name in ["logo.png", "logo.jpg", "logo.jpeg", "watermark.png"]:
                check_p = os.path.join(path, name)
                if os.path.exists(check_p):
                    found_logo = check_p
                    break
            
            if found_logo:
                self.watermark_path.setText(found_logo)
            else:
                 # 없으면 비워둘지, 아니면 해당 폴더 경로로 잡을지?
                 # 워터마크는 파일 경로여야 하므로 폴더만 잡을 순 없음.
                 # 파일이 없으면 기존값 유지하거나 안내
                 # 여기서는 파일이 없는 경우엔 변경 안함
                 pass

    def browse_folder(self, line_edit, callback=None):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if path:
            line_edit.setText(path)
            if callback:
                callback()

    def browse_atv_folder(self):
        path = QFileDialog.getExistingDirectory(self, "작업 폴더 선택")
        if path:
            self.atv_dir.setText(path)
            # 폴더 선택 시 결과 파일명을 기본값으로 채워줌
            # default_out = os.path.join(path, "final_video.mp4")
            # self.atv_out_path.setText(default_out)
            self.refresh_atv_timeline()

    def refresh_atv_timeline(self):
        path = self.atv_dir.text().strip()
        if not path or not os.path.exists(path): return

        # 기존 씬 초기화 (위젯 및 스페이서 모두 제거)
        while self.atv_scene_layout.count():
            item = self.atv_scene_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.atv_scenes_data = []

        # MP3, SRT 파일 체크
        files = os.listdir(path)
        srt_files = [f for f in files if f.lower().endswith('.srt')]
        mp3_files = [f for f in files if f.lower().endswith('.mp3')]
        
        self.atv_status_info.setText(f"📂 경로: {os.path.basename(path)} | MP3: {len(mp3_files)}개 | SRT: {len(srt_files)}개 (✅ 준비 완료)")
        self.atv_status_info.setStyleSheet("color: #4CAF50; font-weight: bold;")

        if not srt_files: return

        # 첫 번째 SRT 파일 파싱
        srt_path = os.path.join(path, srt_files[0])
        segments = parse_srt_robust(srt_path)

        # 씬 매칭 및 그룹화 로직
        current_scene = None
        last_match = None

        for seg in segments:
            index = seg['index']
            # 배경 매칭 시도
            match_found = None
            for ext in ['.jpg', '.jpeg', '.png', '.mp4']:
                tmp = f"{index}{ext}"
                if tmp in files:
                    match_found = tmp
                    break
            
            # 만약 현재 세그먼트에 전용 파일이 없고 이전 파일이 있다면 이전 파일 유지 (Hold)
            if not match_found and last_match:
                match_found = last_match
            
            if match_found: last_match = match_found
            
            # 현재 씬과 동일한 배경이면 텍스트 합치기 및 범위 확장
            if current_scene and current_scene['bg_file'] == match_found:
                current_scene['end'] = seg['end']
                current_scene['text'] += " | " + seg['text']
                current_scene['last_index'] = index
            else:
                # 새로운 씬 시작
                if current_scene:
                    self.atv_scenes_data.append(current_scene)
                    self.add_atv_scene_card(current_scene)
                
                current_scene = {
                    'index': index,
                    'last_index': index,
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': seg['text'],
                    'bg_file': match_found,
                    'overlay_file': None,
                    'speed': 1.0
                }
        
        # 마지막 씬 추가 및 하단 여백용 Stretch
        if current_scene:
            self.atv_scenes_data.append(current_scene)
            self.add_atv_scene_card(current_scene)
        
        self.atv_scene_layout.addStretch()

    def add_atv_scene_card(self, item):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame { background-color: #1E1E1E; border-radius: 10px; border: 1px solid #333; margin-bottom: 8px; }
            QFrame:hover { border: 1px solid #4CAF50; background-color: #252525; }
        """)
        card_layout = QHBoxLayout()
        card_layout.setContentsMargins(15, 15, 15, 15)
        card.setLayout(card_layout)

        # 1. Preview
        prev_container = QVBoxLayout()
        lbl_prev = QLabel()
        lbl_prev.setFixedSize(180, 102) # 16:9 ratio
        lbl_prev.setStyleSheet("background-color: #000; border-radius: 8px; border: 1px solid #444;")
        lbl_prev.setAlignment(Qt.AlignCenter)
        
        is_video = False
        bg_path = ""
        if item['bg_file']:
            bg_path = os.path.join(self.atv_dir.text(), item['bg_file'])
            if item['bg_file'].lower().endswith('.mp4'):
                is_video = True
                # 비디오 썸네일 추출 시도 (캐시 활용)
                thumb = self.get_video_thumbnail_sync(bg_path)
                if thumb and os.path.exists(thumb):
                    pix = QPixmap(thumb)
                    if not pix.isNull():
                        lbl_prev.setPixmap(pix.scaled(180, 102, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    lbl_prev.setText("🎥 VIDEO")
                    lbl_prev.setStyleSheet("background-color: #0d47a1; color: white; font-weight: bold; border-radius: 8px;")
            else:
                pix = QPixmap(bg_path)
                if not pix.isNull():
                    lbl_prev.setPixmap(pix.scaled(180, 102, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        type_label = QLabel("📷 IMAGE" if not is_video else "🎥 VIDEO")
        type_label.setAlignment(Qt.AlignCenter)
        type_label.setFixedHeight(22)
        type_label.setFixedWidth(70)
        type_label.setStyleSheet(f"background-color: {'#FFC107' if not is_video else '#2196F3'}; color: black; font-weight: bold; font-size: 10px; border-radius: 4px;")
        
        prev_container.addWidget(lbl_prev)
        prev_container.addWidget(type_label, 0, Qt.AlignCenter)
        card_layout.addLayout(prev_container)

        # 2. Info Content
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        
        header = QHBoxLayout()
        scene_range = f"{item['index']}~{item['last_index']}" if item['index'] != item['last_index'] else f"{item['index']}"
        title = QLabel(f"🎬 Scene {scene_range}")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #FFF;")
        
        time_range = QLabel(f"⏱️ {self.format_time_atv(item['start'])} ~ {self.format_time_atv(item['end'])}")
        time_range.setStyleSheet("color: #9E9E9E; font-family: 'Consolas'; font-size: 12px;")
        
        dur = item['end'] - item['start']
        duration_label = QLabel(f"● {dur:.1f}s")
        duration_label.setStyleSheet("color: #FFD54F; font-weight: bold; font-size: 12px;")

        header.addWidget(title)
        header.addSpacing(15)
        header.addWidget(time_range)
        header.addStretch()
        header.addWidget(duration_label)
        info_layout.addLayout(header)

        # Subtitle Text (Single Line version)
        raw_text = item['text'].replace('\n', ' ')
        # 텍스트가 너무 길면 '...'으로 표시 (QLabel의 한계로 수동 절단 대신 텍스트 조정)
        display_text = raw_text if len(raw_text) < 55 else raw_text[:52] + "..."
        content = QLabel(display_text)
        content.setWordWrap(False)
        content.setFixedHeight(22)
        content.setStyleSheet("color: #E0E0E0; font-size: 13px; font-weight: 400;")
        info_layout.addWidget(content)

        # Settings Grid
        settings_grid = QGridLayout()
        settings_grid.setColumnStretch(1, 1)
        
        # Background Settings
        settings_grid.addWidget(QLabel("🖼️ 배경:"), 0, 0)
        edit_bg = QLineEdit(item['bg_file'] or "파일 없음")
        edit_bg.setReadOnly(True)
        edit_bg.setMaximumWidth(400) # 너비 제한으로 가로 스크롤 방지
        edit_bg.setStyleSheet("background-color: #252525; border: 1px solid #333; color: #757575; padding: 3px;")
        btn_bg = QPushButton("변경")
        btn_bg.setFixedWidth(75) # 너비 상향 (60 -> 75)
        btn_bg.setStyleSheet("background-color: #424242; color: #EEE; font-weight: bold;")
        btn_bg.clicked.connect(lambda: self.change_scene_bg(item, edit_bg, lbl_prev, type_label))
        settings_grid.addWidget(edit_bg, 0, 1)
        settings_grid.addWidget(btn_bg, 0, 2)

        # Overlay Settings
        settings_grid.addWidget(QLabel("🔷 오버레이:"), 1, 0)
        edit_ov = QLineEdit(item['overlay_file'] or "이미지/영상 PiP 전용...")
        edit_ov.setReadOnly(True)
        edit_ov.setMaximumWidth(400) # 너비 제한으로 가로 스크롤 방지
        edit_ov.setStyleSheet("background-color: #252525; border: 1px solid #333; color: #616161; padding: 3px;")
        btn_ov = QPushButton("선택")
        btn_ov.setFixedWidth(65) # 너비 상향 (50 -> 65)
        btn_ov.setStyleSheet("background-color: #424242; color: #EEE; font-weight: bold;")
        btn_ov.clicked.connect(lambda: self.change_scene_ov(item, edit_ov))
        btn_ov_del = QPushButton("X")
        btn_ov_del.setFixedWidth(35) # 너비 상향 (30 -> 35)
        btn_ov_del.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold;")
        btn_ov_del.clicked.connect(lambda: self.clear_scene_ov(item, edit_ov))
        
        settings_grid.addWidget(edit_ov, 1, 1)
        ov_btns = QHBoxLayout()
        ov_btns.addWidget(btn_ov)
        ov_btns.addWidget(btn_ov_del)
        settings_grid.addLayout(ov_btns, 1, 2)

        if is_video:
            speed_h = QHBoxLayout()
            speed_label = QLabel("⏳ 영상 속도:")
            speed_label.setStyleSheet("font-size: 11px; color: #FFA000;")
            speed_h.addWidget(speed_label)
            combo_speed = QComboBox()
            combo_speed.addItems(["0.5x", "0.8x", "1.0x (기본)", "1.2x", "1.5x", "2.0x"])
            combo_speed.setCurrentIndex(2)
            combo_speed.setFixedWidth(100)
            combo_speed.currentTextChanged.connect(lambda v: self.set_scene_speed(item, v))
            speed_h.addWidget(combo_speed)
            speed_h.addStretch()
            info_layout.addLayout(speed_h)

        info_layout.addLayout(settings_grid)
        card_layout.addLayout(info_layout, 1)
        
        self.atv_scene_layout.addWidget(card)

    def format_time_atv(self, seconds):
        m, s = divmod(seconds, 60)
        return f"{int(m):02d}:{s:05.2f}"

    def get_video_thumbnail_sync(self, video_path):
        import hashlib
        h = hashlib.md5(video_path.encode()).hexdigest()
        temp_dir = os.path.join(os.environ.get('TEMP', os.environ.get('TMP', 'C:/Windows/Temp')), "youtube_creator_thumbs")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir, exist_ok=True)
        thumb_path = os.path.join(temp_dir, f"thumb_{h}.jpg")
        
        if os.path.exists(thumb_path):
            return thumb_path
            
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except:
            ffmpeg_exe = "ffmpeg"
            
        # 첫 번째 1초 지점의 프레임을 16:9 비율로 추출
        cmd = [
            ffmpeg_exe, "-y", "-i", video_path, 
            "-ss", "00:00:01", "-vframes", "1", 
            "-vf", "scale=180:102:force_original_aspect_ratio=decrease,pad=180:102:(ow-iw)/2:(oh-ih)/2", 
            thumb_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000, timeout=2)
            return thumb_path
        except:
            return None

    def change_scene_bg(self, item, edit_field, lbl_prev, type_lbl):
        path, _ = QFileDialog.getOpenFileName(self, "배경 파일 선택", self.atv_dir.text(), "Media Files (*.jpg *.png *.mp4)")
        if path:
            fname = os.path.basename(path)
            item['bg_file'] = fname
            edit_field.setText(fname)
            if fname.lower().endswith('.mp4'):
                lbl_prev.setText("🎥 VIDEO")
                lbl_prev.setPixmap(QPixmap())
                lbl_prev.setStyleSheet("background-color: #0d47a1; color: white; font-weight: bold; border-radius: 5px;")
                type_lbl.setText("🎥 VIDEO")
                type_lbl.setStyleSheet("background-color: #2196F3; color: black; font-weight: bold; font-size: 10px; border-radius: 3px; max-height: 18px;")
            else:
                pix = QPixmap(path)
                lbl_prev.setPixmap(pix.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                lbl_prev.setStyleSheet("background-color: #000; border-radius: 5px;")
                type_lbl.setText("📷 IMAGE")
                type_lbl.setStyleSheet("background-color: #FFC107; color: black; font-weight: bold; font-size: 10px; border-radius: 3px; max-height: 18px;")

    def change_scene_ov(self, item, edit_field):
        path, _ = QFileDialog.getOpenFileName(self, "오버레이 파일 선택", self.atv_dir.text(), "Media Files (*.jpg *.png *.mp4)")
        if path:
            fname = os.path.basename(path)
            item['overlay_file'] = fname
            edit_field.setText(fname)
            edit_field.setStyleSheet("background-color: #121212; border: 1px solid #4CAF50; color: #FFF;")

    def clear_scene_ov(self, item, edit_field):
        item['overlay_file'] = None
        edit_field.setText("이미지/영상 PiP 전용...")
        edit_field.setStyleSheet("background-color: #121212; border: 1px solid #444; color: #555;")

    def set_scene_speed(self, item, val):
        try:
            speed = float(val.replace('x', '').replace('(기본)', '').strip())
            item['speed'] = speed
        except:
            item['speed'] = 1.0

    def browse_save_path(self, line_edit, filter_str="Video Files (*.mp4)"):
        path, _ = QFileDialog.getSaveFileName(self, "파일 저장 위치 지정", line_edit.text() or "", filter_str)
        if path:
            line_edit.setText(path)

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
                            self.font_path_map[fam] = font_path
        
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
        
        # 4. 드롭다운 목록 업데이트 (메인 탭, ATV 탭, Thumbnail 탭)
        combos = [self.combo_font]
        if hasattr(self, 'atv_combo_font'):
            combos.append(self.atv_combo_font)
            # 영상생성 탭 폰트 변경 시 썸네일 폰트 자동 동기화 연결
            try:
                self.atv_combo_font.currentIndexChanged.disconnect(self.sync_thumbnail_fonts)
            except: pass
            self.atv_combo_font.currentIndexChanged.connect(self.sync_thumbnail_fonts)
        
        # 썸네일 탭의 각 줄 콤보박스 찾기
        if hasattr(self, 'thumb_lines'):
            for line_data in self.thumb_lines:
                if 'font' in line_data: # 수정: 'font_combo' -> 'font'
                    combos.append(line_data['font'])
        
        
        # 시스템 폰트 경로 보강 (한글 깨짐 방지용)
        sys_fonts = {
            "Malgun Gothic": r"C:\Windows\Fonts\malgun.ttf",
            "맑은 고딕": r"C:\Windows\Fonts\malgun.ttf",
            "NanumGothic": r"C:\Windows\Fonts\NanumGothic.ttf",
            "Batang": r"C:\Windows\Fonts\batang.ttc",
            "Gulim": r"C:\Windows\Fonts\gulim.ttc"
        }
        for fam, p in sys_fonts.items():
            if fam not in self.font_path_map and os.path.exists(p):
                self.font_path_map[fam] = p

        for cb in combos:
            cb.blockSignals(True) # 무한 루프 방지
            cb.clear()
            if matched_families:
                final_list = sorted(list(matched_families))
                cb.addItems(final_list)
                
                # 영상생성 탭 폰트 개수 정보 업데이트
                if hasattr(self, 'lbl_atv_font_info'):
                    self.lbl_atv_font_info.setText(f"폰트 로드 완료: {len(final_list)}개")

                # 우선순위 설정: Gmarket Sans TTF Bold 최우선
                target_set = False
                # 1순위: Gmarket Sans TTF Bold (정확한 매칭 시도)
                for i in range(cb.count()):
                    text = cb.itemText(i)
                    if "Gmarket" in text and "Bold" in text:
                        cb.setCurrentIndex(i)
                        target_set = True
                        break
                
                # 2순위: Gmarket Sans
                if not target_set:
                    for i in range(cb.count()):
                        if "Gmarket" in cb.itemText(i):
                            cb.setCurrentIndex(i); target_set = True; break
                
                # 3순위: Nanum
                if not target_set:
                    for i in range(cb.count()):
                        if "Nanum" in cb.itemText(i):
                            cb.setCurrentIndex(i); target_set = True; break
                            
                # 4순위: Malgun
                if not target_set:
                    for i in range(cb.count()):
                        if "Malgun" in cb.itemText(i) or "맑은" in cb.itemText(i):
                            cb.setCurrentIndex(i); break
            else:
                fallback_fonts = ["Malgun Gothic", "맑은 고딕", "Arial"]
                available_fallbacks = [f for f in fallback_fonts if f in all_families]
                cb.addItems(available_fallbacks if available_fallbacks else ["Arial"])
            cb.blockSignals(False)

    def sync_thumbnail_fonts(self, index):
        """영상생성(ATV) 탭의 폰트 변경 시 모든 썸네일 줄의 폰트를 동일하게 변경"""
        if not hasattr(self, 'atv_combo_font') or not hasattr(self, 'thumb_lines'):
            return
            
        selected_font = self.atv_combo_font.currentText()
        for line_data in self.thumb_lines:
            if 'font' in line_data:
                cb = line_data['font']
                idx = cb.findText(selected_font)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                    
        # 인트로 탭 폰트 동기화
        if hasattr(self, 'combo_intro_font'):
            idx = self.combo_intro_font.findText(selected_font)
            if idx >= 0:
                self.combo_intro_font.setCurrentIndex(idx)

        # 소설 썸네일 탭 폰트 동기화
        if hasattr(self, 'novel_thumb_lines'):
            for line_data in self.novel_thumb_lines:
                if 'font' in line_data:
                    idx = line_data['font'].findText(selected_font)
                    if idx >= 0:
                        line_data['font'].setCurrentIndex(idx)
                        
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
        do_merge = self.chk_merge_mp3_json.isChecked()

        # 파싱 로직: 그룹별로 텍스트 묶기 (Strict Validation)
        # N.{} N-M 원본: ... TTS: ... 형식을 엄격하게 검증
        blocks = re.split(r'(\d+)\.\s*\{.*?\}', text)
        if len(blocks) < 3:
            self.tts_log.append("❌ 형식이 올바르지 않습니다. '1.{} 1-1 원본: ... TTS: ...' 형식이 필요하며, 'N.{}' 항목이 누락되었습니다.")
            return

        if blocks[0].strip():
            self.tts_log.append(f"❌ '{blocks[0].strip()[:20]}...' 부분은 올바른 형식이 아닙니다. '1.{{}}' 형식으로 시작해야 합니다.")
            return

        subs_map = collections.defaultdict(list)
        for i in range(1, len(blocks), 2):
            major_id = blocks[i]
            block_content = blocks[i+1].strip()
            
            if not block_content:
                self.tts_log.append(f"❌ {major_id}.{{}} 하위에 내용이 없습니다.")
                return
            
            # 해당 블록 내에서 "N-M 원본: ... TTS: ..." 패턴을 찾습니다.
            # re.DOTALL: .이 개행문자 포함, re.IGNORECASE: 대소문자 무시
            item_pattern = rf'(?:^|\s|\n)({major_id}-\d+)\s*원본:(.*?)\s*TTS:(.*?)(?=(?:^|\s|\n){major_id}-\d+|$)'
            matches = list(re.finditer(item_pattern, block_content, re.DOTALL | re.IGNORECASE))
            
            if not matches:
                self.tts_log.append(f"❌ {major_id}.{{}} 하위에 '{major_id}-1 원본: ... TTS: ...' 형식이 없습니다.")
                return
            
            for m in matches:
                original_text = m.group(2).strip()
                tts_text = m.group(3).strip()
                
                # 끝부분의 콤마 제거 로직 유지
                if original_text.endswith(','): original_text = original_text[:-1].strip()
                if tts_text.endswith(','): tts_text = tts_text[:-1].strip()
                
                subs_map[major_id].append({
                    "original": original_text,
                    "tts": tts_text
                })

        tasks = []
        for major_id, items in subs_map.items():
            combined_tts = " ".join([item['tts'] for item in items])
            if combined_tts:
                filename = f"{major_id}.mp3"
                tasks.append((combined_tts, filename, items))
        
        if not tasks:
            self.tts_log.append("❌ 추출된 유효한 데이터가 없습니다.")
            return

        self.tts_log.append(f"📋 배치 모드 감지: {len(tasks)}개의 파일 생성 예정")

        self.btn_generate_tts.setEnabled(False)
        self.btn_stop_tts.setEnabled(True)
        self.tts_log.append("⏳ 생성 시작...")

        # 스레드로 실행 (tasks 리스트 전달)
        audio_target = self.audio_path_edit.text().strip()
        threading.Thread(target=self._run_tts_thread, args=(tasks, voice_id, model_id, stability, similarity, style, speed, volume, audio_target, trim_end, do_merge), daemon=True).start()

    def _run_tts_thread(self, tasks, voice_id, model_id, stability, similarity, style, speed, volume, custom_dir, trim_end=0.0, do_merge=True):
        success_count = 0
        request_ids = []
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
                    # previous_request_ids를 전달하여 자연스러운 연결 보장 (프롬프트 제거)
                    save_path, current_rid = self.tts_client.generate_audio(
                        text=text_chunk, 
                        voice_id=voice_id, 
                        model_id=model_id,
                        stability=stability,
                        similarity_boost=similarity,
                        style=style,
                        speed=speed,
                        volume=volume,
                        filename=filename,
                        custom_dir=custom_dir,
                        sub_segments=sub_segments,
                        previous_request_ids=request_ids[-3:] if request_ids else None # 연속성 로직: 최근 3개만 유지
                    )
                    
                    if current_rid:
                        request_ids.append(current_rid)
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
            
            # --- 병합 로직 ---
            if success_count == len(tasks) and not self.stop_tts_flag:
                if do_merge:
                    # 단일 파일이라도 병합 체크 시 merge.mp3, merge.srt 생성을 위해 실행
                    self._merge_audio_files_thread(tasks, custom_dir)
                else:
                    self.log_signal.emit("ℹ️ 옵션에 따라 병합을 건너뜁니다.")

        except Exception as e:
            self.error_signal.emit(f"❌ 치명적 오류: {e}")
        finally:
            self.enable_button_signal.emit(True)

    def merge_existing_audio(self):
        custom_dir = self.audio_path_edit.text().strip()
        if not os.path.isdir(custom_dir):
             self.tts_log.append("❌ 유효한 저장 폴더가 아닙니다.")
             return
             
        files = []
        try:
            for f in os.listdir(custom_dir):
                if f.lower().endswith(".mp3") and f[:-4].isdigit():
                    files.append(f)
            
            if len(files) < 2:
                self.tts_log.append("❌ 병합할 파일이 충분하지 않습니다 (2개 이상 필요).")
                return
                
            files.sort(key=lambda x: int(x[:-4]))
            tasks = [(None, f, None) for f in files]
            
            self.tts_log.append(f"🔍 {len(files)}개의 파일 검색됨. 병합 시작...")
            threading.Thread(target=self._merge_audio_files_thread, args=(tasks, custom_dir), daemon=True).start()
            
        except Exception as e:
            self.tts_log.append(f"❌ 파일 검색 중 오류: {e}")

    def _merge_audio_files_thread(self, tasks, custom_dir):
        try:
            self.log_signal.emit("🔗 오디오 및 데이터 병합 시작...")
            clips = []
            valid_files = True
            
            for task in tasks:
                filename = task[1]
                file_path = os.path.join(custom_dir, filename)
                if os.path.exists(file_path):
                    try:
                        clip = mpe.AudioFileClip(file_path)
                        clips.append(clip)
                    except Exception as ce:
                        self.log_signal.emit(f"   ⚠️ 오디오 로드 실패 ({filename}): {ce}")
                        valid_files = False
                        break
                else:
                     valid_files = False
                     break
            
            if valid_files and clips:
                # 1. MP3 병합
                output_path = os.path.join(custom_dir, "merge.mp3")
                try:
                    final_clip = mpe.concatenate_audioclips(clips)
                    final_clip.write_audiofile(output_path, logger=None, bitrate="192k")
                    self.log_signal.emit(f"✅ 오디오 병합 성공: {output_path}")
                    
                    # 2. JSON/SRT 병합
                    self.log_signal.emit("🔗 JSON 데이터 병합 시작 (merge.json)...")
                    merged_json = {
                        "characters": [],
                        "character_start_times_seconds": [],
                        "character_end_times_seconds": [],
                        "sub_segments": []
                    }
                    current_time_offset = 0.0
                    
                    for i, clip in enumerate(clips):
                        task = tasks[i]
                        filename = task[1]
                        base_name = os.path.splitext(filename)[0]
                        json_path = os.path.join(custom_dir, base_name + ".json")
                        
                        if os.path.exists(json_path):
                            try:
                                with open(json_path, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                if "characters" in data: merged_json["characters"].extend(data["characters"])
                                if "character_start_times_seconds" in data:
                                    merged_json["character_start_times_seconds"].extend([t + current_time_offset for t in data["character_start_times_seconds"]])
                                if "character_end_times_seconds" in data:
                                    merged_json["character_end_times_seconds"].extend([t + current_time_offset for t in data["character_end_times_seconds"]])
                                if "sub_segments" in data: merged_json["sub_segments"].extend(data["sub_segments"])
                            except Exception as e_json:
                                self.log_signal.emit(f"   ⚠️ JSON 병합 실패 ({base_name}.json): {e_json}")
                        
                        current_time_offset += clip.duration
                    
                    merged_json_path = os.path.join(custom_dir, "merge.json")
                    with open(merged_json_path, "w", encoding="utf-8") as f:
                        json.dump(merged_json, f, ensure_ascii=False, indent=4)
                    self.log_signal.emit(f"✅ JSON 병합 완료")
                    
                    # 3. SRT 생성
                    def format_srt_time(seconds):
                        millis = int((seconds - int(seconds)) * 1000)
                        seconds = int(seconds)
                        minutes, seconds = divmod(seconds, 60)
                        hours, minutes = divmod(minutes, 60)
                        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

                    srt_path = os.path.join(custom_dir, "merge.srt")
                    with open(srt_path, "w", encoding="utf-8") as srt_file:
                        srt_idx = 1
                        all_chars = merged_json.get("characters", [])
                        all_starts = merged_json.get("character_start_times_seconds", [])
                        all_ends = merged_json.get("character_end_times_seconds", [])
                        char_idx = 0
                        
                        for segment in merged_json.get("sub_segments", []):
                            original_text = segment.get("original", "").strip()
                            tts_text = segment.get("tts", "")
                            if not tts_text: continue
                            
                            segment_start = None
                            segment_end = None
                            
                            target_chars = [c for c in tts_text if not c.isspace()]
                            if not target_chars: continue
                            
                            temp_char_idx = char_idx
                            first_match = False
                            
                            for t_char in target_chars:
                                while temp_char_idx < len(all_chars):
                                    if temp_char_idx >= len(all_chars): break
                                    if all_chars[temp_char_idx].isspace():
                                        temp_char_idx += 1
                                        continue
                                    if all_chars[temp_char_idx] == t_char:
                                        if not first_match:
                                            if temp_char_idx < len(all_starts): segment_start = all_starts[temp_char_idx]
                                            first_match = True
                                        if temp_char_idx < len(all_ends): segment_end = all_ends[temp_char_idx]
                                        temp_char_idx += 1
                                        break
                                    temp_char_idx += 1
                            
                            char_idx = temp_char_idx
                            if segment_start is not None and segment_end is not None:
                                srt_file.write(f"{srt_idx}\n{format_srt_time(segment_start)} --> {format_srt_time(segment_end)}\n{original_text}\n\n")
                                srt_idx += 1
                    self.log_signal.emit(f"✅ SRT 생성 완료: {srt_path}")
                
                except Exception as e:
                    self.log_signal.emit(f"❌ 병합 중 오류: {e}")
                finally:
                    if 'final_clip' in locals(): 
                        try: final_clip.close() 
                        except: pass
                    for c in clips: 
                        try: c.close() 
                        except: pass
            else:
                self.log_signal.emit("❌ 유효한 파일이 없거나 로드할 수 없습니다.")
                for c in clips: 
                    try: c.close() 
                    except: pass
        except Exception as e:
            self.error_signal.emit(f"❌ 스레드 오류: {e}")
            
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

    def launch_whisk_browser(self):
        self.btn_whisk_prepare.setEnabled(False)
        self.whisk_status_label.setText("1단계: Whisk 브라우저 실행 중...")
        
        self.browser_worker = BrowserLauncherWorker('whisk')
        self.browser_worker.log_signal.connect(self.whisk_log_display.append)
        self.browser_worker.finished.connect(self.on_whisk_browser_launch_finished)
        self.browser_worker.start()

    def on_whisk_browser_launch_finished(self, result):
        driver, error = result
        self.btn_whisk_prepare.setEnabled(True)
        
        if driver:
            self.driver = driver
            window_count = len(self.driver.window_handles)
            self.whisk_log_display.append(f"✅ Whisk 브라우저 연결 성공. 현재 탭 수: {window_count}")
            self.whisk_status_label.setText("2단계: 프롬프트 입력 후 시작 버튼을 누르세요.")
        else:
            self.whisk_log_display.append(f"❌ Whisk 브라우저 실패: {error}")
            self.whisk_status_label.setText("오류 발생 (로그 확인)")

    def start_whisk_automation(self):
        if not self.driver:
            self.whisk_log_display.append("❌ 브라우저가 준비되지 않았습니다.")
            return
        
        text = self.whisk_image_prompt_input.toPlainText().strip()
        if not text:
            self.whisk_log_display.append("❌ 입력된 프롬프트가 없습니다.")
            return

        self.loaded_items = re.findall(r'(\d+)\s*\.\s*\{(.*?)\}', text, re.DOTALL)
        if not self.loaded_items:
             self.whisk_log_display.append("❌ 프롬프트 형식이 올바르지 않습니다 (예: 1. {프롬프트})")
             return

        self.btn_whisk_start.setEnabled(False)
        self.btn_whisk_stop.setEnabled(True)
        self.start_time_gen = time.time()
        if not self.ui_timer.isActive():
            self.ui_timer.start(1000) 
        
        self.current_file_path = "whisk_input_" + time.strftime("%H%M%S")
        image_target = self.whisk_image_path_edit.text().strip()
        
        self.whisk_worker = WhiskMultiTabWorker(self.current_file_path, self.loaded_items, self.driver, custom_target_dir=image_target)
        self.whisk_worker.progress.connect(self.whisk_status_label.setText)
        self.whisk_worker.log_signal.connect(lambda m: self.whisk_log_display.append(m))
        self.whisk_worker.finished.connect(self.on_whisk_success)
        self.whisk_worker.error.connect(self.on_whisk_error)
        self.whisk_worker.start()

    def stop_whisk_automation(self):
        if hasattr(self, 'whisk_worker'):
            self.whisk_worker.stop()
            self.whisk_log_display.append("🛑 중지 요청 중...")

    def on_whisk_success(self, msg, elapsed):
        self.start_time_gen = 0
        self.ui_timer.stop()
        self.btn_whisk_start.setEnabled(True)
        self.btn_whisk_stop.setEnabled(False)
        self.whisk_log_display.append(f"🏁 {msg}")
        
        if hasattr(self, 'whisk_worker') and self.whisk_worker.target_dir:
            self.whisk_log_display.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
            self.compress_images(dir_path=self.whisk_worker.target_dir)

    def on_whisk_error(self, err):
        self.start_time_gen = 0
        self.ui_timer.stop()
        self.btn_whisk_start.setEnabled(True)
        self.btn_whisk_stop.setEnabled(False)
        self.whisk_log_display.append(f"❌ 오류: {err}")


    # Removed ImageFX and Gemini API methods

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
            
            if hasattr(self, 'whisk_timer_label'):
                self.whisk_timer_label.setText(f"소요 시간: {h:02d}:{m:02d}:{s:02d}")


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




    def initTab7(self):
        layout = QVBoxLayout()

        # 1. Filter Group
        filter_layout = QGridLayout()
        
        # API Key
        self.combo_yt_key = QComboBox()
        # Load keys from DB (using tts_client if available)
        self.yt_keys = []
        if hasattr(self, 'tts_client') and self.tts_client:
            try:
                self.yt_keys = self.tts_client.get_youtube_keys()
                for k in self.yt_keys:
                    self.combo_yt_key.addItem(k['name'], k['api_key'])
            except Exception as e:
                print(f"YouTube 키 로드 실패 (DB 접속 오류 등): {e}")
        
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
        self.edit_yt_query.setPlaceholderText("검색어 입력 (채널명 포함)")
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
        self.table_youtube.setColumnCount(14)
        self.table_youtube.setHorizontalHeaderLabels([
            "번호", "썸네일", "채널명", "카테고리", "제목", "조회수", "구독자", "조회수/구독자", "영상길이", "영상수", "기본언어", "오디오언어", "채널국가", "업로드날짜"
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

            # 3: Category (Center) [New]
            self.table_youtube.setItem(r, 3, make_item(row.get('category', '-'), Qt.AlignCenter))
            
            # 4: Title (Left)
            self.table_youtube.setItem(r, 4, make_item(row['title'], Qt.AlignLeft | Qt.AlignVCenter))
            
            # 5: Views (Right) - Numeric
            self.table_youtube.setItem(r, 5, make_numeric_item(f"{row['view_count']:,}", Qt.AlignRight | Qt.AlignVCenter))
            
            # 6: Subs (Right) - Numeric
            self.table_youtube.setItem(r, 6, make_numeric_item(f"{row['subscriber_count']:,}", Qt.AlignRight | Qt.AlignVCenter))
            
            # 7: Ratio (Right) [New] - Numeric
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
                 
            self.table_youtube.setItem(r, 7, make_numeric_item(ratio_text, Qt.AlignRight | Qt.AlignVCenter, ratio_color, ratio_font))

            # 8: Duration (Center) - Moved here
            self.table_youtube.setItem(r, 8, make_item(row.get('duration_str', '-'), Qt.AlignCenter))

            # 9: Video Total (Center) - Numeric
            self.table_youtube.setItem(r, 9, make_numeric_item(f"{row['video_total']:,}", Qt.AlignCenter))
            
            # 10: Lang (Center)
            self.table_youtube.setItem(r, 10, make_item(row['lang'], Qt.AlignCenter))
            
            # 11: Audio Lang (Center)
            self.table_youtube.setItem(r, 11, make_item(row['audio_lang'], Qt.AlignCenter))
            
            # 12: Country (Center)
            self.table_youtube.setItem(r, 12, make_item(row['country'], Qt.AlignCenter))
            
            # 13: Date (Center)
            date_str = row['published_at'].replace("T", " ").replace("Z", "")
            self.table_youtube.setItem(r, 13, make_item(date_str, Qt.AlignCenter))
            
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
        # output_dir = self.eff_output_dir.text().strip() (Removed)
        
        if not input_dir or not os.path.exists(input_dir):
            QMessageBox.warning(self, "경고", "입력 폴더가 존재하지 않습니다.")
            return

        # [Auto] ../output 경로 설정
        output_dir = os.path.abspath(os.path.join(input_dir, "..", "output"))
        self.eff_output_dir.setText(output_dir) # UI 표시

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                QMessageBox.warning(self, "경고", "출력 폴더(output)를 생성할 수 없습니다.")
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
        # 메인 레이아웃: 가로 (Sidebar + Timeline)
        main_layout = QHBoxLayout()
        self.tab_audio_video.setLayout(main_layout)

        # --- 좌측 사이드바 (설정 영역) ---
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(380)
        sidebar_layout = QVBoxLayout()
        sidebar_widget.setLayout(sidebar_layout)
        sidebar_layout.setContentsMargins(0, 0, 10, 0)

        # 1. 사용법 및 폴더 선택
        usage_label = QLabel("💡 사용법:\n1. 1.mp3, 1.srt 및 배경 파일(1.jpg, 2.mp4...)이 있는 폴더를 선택하세요.\n2. 폰트와 배경음악을 설정한 후 '생성 시작'을 누르세요.")
        usage_label.setWordWrap(True)
        usage_label.setStyleSheet("color: #FFD54F; font-size: 11px; margin-bottom: 5px;")
        sidebar_layout.addWidget(usage_label)

        dir_group = QGroupBox("📁 경로 설정")
        dir_vbox = QVBoxLayout()
        self.atv_dir = QLineEdit()
        self.atv_dir.setPlaceholderText("작업 폴더 경로")
        self.atv_dir.setReadOnly(True)
        btn_dir = QPushButton("작업 폴더 선택")
        btn_dir.setFixedHeight(45)
        btn_dir.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; font-size: 14px;")
        btn_dir.clicked.connect(self.browse_atv_folder)
        
        dir_vbox.addWidget(self.atv_dir)
        dir_vbox.addWidget(btn_dir)
        dir_group.setLayout(dir_vbox)
        sidebar_layout.addWidget(dir_group)

        # 2. 스타일 및 음악
        style_group = QGroupBox("⚙️ 스타일 및 음악")
        style_grid = QGridLayout()
        
        # 폰트
        self.atv_combo_font = QComboBox()
        self.atv_spin_font_size = QSpinBox()
        self.atv_spin_font_size.setRange(10, 200)
        self.atv_spin_font_size.setValue(75)
        style_grid.addWidget(QLabel("폰트:"), 0, 0)
        style_grid.addWidget(self.atv_combo_font, 0, 1)
        style_grid.addWidget(QLabel("크기:"), 0, 2)
        style_grid.addWidget(self.atv_spin_font_size, 0, 3)

        # BGM
        self.atv_bgm_path = QLineEdit()
        self.atv_bgm_path.setPlaceholderText("배경음악 선택 (필수X)")
        btn_bgm = QPushButton("찾기")
        btn_bgm.clicked.connect(lambda: self.browse_single_file(self.atv_bgm_path, "Audio Files (*.mp3 *.wav)"))
        style_grid.addWidget(QLabel("BGM:"), 1, 0)
        style_grid.addWidget(self.atv_bgm_path, 1, 1, 1, 2)
        style_grid.addWidget(btn_bgm, 1, 3)

        # 볼륨 슬라이더
        self.atv_bgm_volume = QSlider(Qt.Horizontal)
        self.atv_bgm_volume.setRange(0, 100)
        self.atv_bgm_volume.setValue(10)
        self.atv_lbl_volume = QLabel("0.10")
        self.atv_bgm_volume.valueChanged.connect(lambda v: self.atv_lbl_volume.setText(f"{v/100:.2f}"))
        style_grid.addWidget(QLabel("볼륨:"), 2, 0)
        style_grid.addWidget(self.atv_bgm_volume, 2, 1, 1, 2)
        style_grid.addWidget(self.atv_lbl_volume, 2, 3)

        style_group.setLayout(style_grid)
        sidebar_layout.addWidget(style_group)

        # 3. 하단 버튼 및 정보
        self.btn_atv_start = QPushButton("🎬 영상 생성 시작")
        self.btn_atv_start.setFixedHeight(55)
        self.btn_atv_start.setStyleSheet("background-color: #6200EA; color: white; font-weight: bold; font-size: 16px; border-radius: 8px;")
        self.btn_atv_start.clicked.connect(self.start_audio_to_video)
        sidebar_layout.addWidget(self.btn_atv_start)

        self.atv_status_info = QLabel("📂 경로: - | MP3: 0개 | SRT: 0개")
        self.atv_status_info.setStyleSheet("color: #FF5252; font-weight: bold; margin-top: 5px;")
        sidebar_layout.addWidget(self.atv_status_info)

        # 4. 기존 스타일 설정 그룹 복구 (유저 요청: 기존 형태 유지)
        style_group_ext = QGroupBox("📌 자막 상세 스타일 (기존)")
        style_layout_ext = QGridLayout()

        # 폰트 폴더 고정 (UI 제거)
        self.atv_font_folder_path = QLineEdit(r"D:\youtube\fonts")
        self.atv_font_folder_path.setVisible(False)

        # 색상 초기화
        self.atv_color_text = "black"
        self.atv_color_outline = "white"
        self.atv_color_bg = "Transparent"

        # 글자색 및 테두리색 버튼 폭 조정
        self.atv_btn_text_color = QPushButton("글자색")
        self.atv_btn_text_color.setFixedWidth(85)
        self.atv_btn_text_color.clicked.connect(lambda: self.pick_color('atv_text'))
        self.atv_ind_text_color = QLabel()
        self.atv_ind_text_color.setFixedSize(20, 20)
        
        self.atv_btn_outline_color = QPushButton("테두리색")
        self.atv_btn_outline_color.setFixedWidth(85)
        self.atv_btn_outline_color.clicked.connect(lambda: self.pick_color('atv_outline'))
        self.atv_ind_outline_color = QLabel()
        self.atv_ind_outline_color.setFixedSize(20, 20)

        self.atv_checkbox_use_outline = QCheckBox("테두리 사용")
        self.atv_checkbox_use_outline.setChecked(True)
        self.atv_checkbox_use_outline.stateChanged.connect(self.update_color_indicators)

        # 1행 배치
        row1_h = QHBoxLayout()
        row1_h.addWidget(self.atv_btn_text_color)
        row1_h.addWidget(self.atv_ind_text_color)
        row1_h.addSpacing(10)
        row1_h.addWidget(self.atv_btn_outline_color)
        row1_h.addWidget(self.atv_ind_outline_color)
        row1_h.addSpacing(10)
        row1_h.addWidget(self.atv_checkbox_use_outline)
        row1_h.addStretch()
        style_layout_ext.addLayout(row1_h, 1, 0, 1, 5)

        # 배경색 설정
        self.atv_checkbox_use_bg = QCheckBox("배경색 사용")
        self.atv_checkbox_use_bg.stateChanged.connect(self.update_color_indicators)
        self.atv_btn_bg_color = QPushButton("배경색")
        self.atv_btn_bg_color.setFixedWidth(85)
        self.atv_btn_bg_color.clicked.connect(lambda: self.pick_color('atv_bg'))
        self.atv_ind_bg_color = QLabel()
        self.atv_ind_bg_color.setFixedSize(20, 20)

        # 2행 배치
        row2_h = QHBoxLayout()
        row2_h.addWidget(self.atv_checkbox_use_bg)
        row2_h.addSpacing(10)
        row2_h.addWidget(self.atv_btn_bg_color)
        row2_h.addWidget(self.atv_ind_bg_color)
        row2_h.addStretch()
        style_layout_ext.addLayout(row2_h, 2, 0, 1, 5)

        # 투명도
        style_layout_ext.addWidget(QLabel("배경 투명도:"), 3, 0)
        self.atv_slider_bg_opacity = QSlider(Qt.Horizontal)
        self.atv_slider_bg_opacity.setRange(0, 100)
        self.atv_slider_bg_opacity.setValue(80)
        self.atv_lbl_bg_opacity = QLabel("80%")
        self.atv_slider_bg_opacity.valueChanged.connect(self.update_color_indicators)
        self.atv_slider_bg_opacity.valueChanged.connect(lambda v: self.atv_lbl_bg_opacity.setText(f"{v}%"))
        
        style_layout_ext.addWidget(self.atv_slider_bg_opacity, 3, 1, 1, 2)
        style_layout_ext.addWidget(self.atv_lbl_bg_opacity, 3, 3)

        # 줌팬 방지
        self.atv_chk_fix_first_img = QCheckBox("1번 이미지 고정 (줌/팬 방지)")
        self.atv_chk_fix_first_img.setChecked(True)
        style_layout_ext.addWidget(self.atv_chk_fix_first_img, 4, 0, 1, 2)

        style_group_ext.setLayout(style_layout_ext)
        sidebar_layout.addWidget(style_group_ext)

        # 로그창 복구 (기존 UI 유지)
        self.atv_log = QTextEdit()
        self.atv_log.setReadOnly(True)
        self.atv_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        sidebar_layout.addWidget(self.atv_log, 1) # stretch factor 1 부여

        main_layout.addWidget(sidebar_widget)

        # --- 우측 타임라인 영역 ---
        timeline_container = QWidget()
        timeline_layout = QVBoxLayout()
        timeline_container.setLayout(timeline_layout)
        
        header_layout = QHBoxLayout()
        header_title = QLabel("≡ 타임라인 미리보기 (SRT 매칭)")
        header_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFF;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        timeline_layout.addLayout(header_layout)

        # 스크롤 영역
        self.atv_scroll_area = QScrollArea()
        self.atv_scroll_area.setWidgetResizable(True)
        self.atv_scroll_area.setStyleSheet("background-color: #121212; border: none;")
        
        self.atv_scroll_content = QWidget()
        self.atv_scene_layout = QVBoxLayout()
        self.atv_scene_layout.setAlignment(Qt.AlignTop)
        self.atv_scene_layout.setContentsMargins(10, 10, 10, 30) # 하단 여백 추가 (30px)
        self.atv_scroll_content.setLayout(self.atv_scene_layout)
        self.atv_scroll_area.setWidget(self.atv_scroll_content)
        
        timeline_layout.addWidget(self.atv_scroll_area)
        main_layout.addWidget(timeline_container, 1)
        
        # 데이터 관리용
        self.atv_scenes_data = [] # [{index, start, end, text, bg_file, overlay_file, speed}, ...]
        self.atv_color_text = "black"
        self.atv_color_outline = "white"
        self.atv_color_bg = "Transparent"
        
        # 초기 컬러 인디케이터 갱신
        self.update_color_indicators()

    def start_audio_to_video(self):
        target_dir = self.atv_dir.text().strip()
        if not target_dir or not os.path.exists(target_dir):
            QMessageBox.warning(self, "경고", "올바른 작업 폴더를 선택해주세요.")
            return

        # 스타일 설정 읽기 (이 탭 전 전용 컨트롤 사용)
        style = {
            'font_family': self.atv_combo_font.currentText(),
            'font_size': self.atv_spin_font_size.value(),
            'text_color': self.atv_color_text,
            'outline_color': self.atv_color_outline,
            'bg_color': self.atv_color_bg,
            'bg_opacity': int(self.atv_slider_bg_opacity.value() * 2.55),
            'use_bg': self.atv_checkbox_use_bg.isChecked(),
            'font_folder': self.atv_font_folder_path.text().strip() if hasattr(self, 'atv_font_folder_path') else '',
            'fix_first_img': self.atv_chk_fix_first_img.isChecked() if hasattr(self, 'atv_chk_fix_first_img') else True,
            'bgm_path': self.atv_bgm_path.text().strip(),
            'bgm_volume': self.atv_bgm_volume.value() / 100.0
        }
        
        self.atv_log_append_custom(f"🚀 작업 시작: {target_dir}")
        self.btn_atv_start.setEnabled(False)
        
        # 결과 파일명을 기본값(final_video.mp4)으로 설정
        out_path = os.path.join(target_dir, "final_video.mp4")
            
        self.atv_worker = AudioToVideoWorker(target_dir, style, out_path, self.atv_scenes_data)
        self.atv_worker.log_signal.connect(self.atv_log_append_custom) # 사이드바 로그가 없으므로 커스텀 로그 함수 필요
        self.atv_worker.finished.connect(self.on_atv_finished)
        self.atv_worker.error.connect(self.on_atv_error)
        self.atv_worker.start()

    def atv_log_append_custom(self, msg):
        # 1. 상태바 업데이트
        if "완료" in msg or "시작" in msg or "실패" in msg or "오류" in msg:
            self.atv_status_info.setText(f"ℹ️ {msg}")
        
        # 2. 로그창 업데이트
        if hasattr(self, 'atv_log'):
            self.atv_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            # 스크롤 최하단으로
            self.atv_log.ensureCursorVisible()
        
    def on_atv_finished(self, msg, elapsed):
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        time_str = f" ({h:02d}:{m:02d}:{s:02d})"
        
        self.atv_log_append_custom(f"🏁 {msg}{time_str}")
        self.btn_atv_start.setEnabled(True)
        
    def on_atv_error(self, err):
        self.atv_log_append_custom(f"❌ 오류: {err}")
        self.btn_atv_start.setEnabled(True)

    def on_batch_eff_finished(self, msg, elapsed):
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        time_str = f" ({h:02d}:{m:02d}:{s:02d})"
        self.single_log.append(f"🏁 {msg}{time_str}")
        self.btn_start_single.setEnabled(True)

    # ==========================================
    # Tab Grok Generation (New)
    # ==========================================
    def initTabGrokGen(self):
        layout = QVBoxLayout()

        self.grok_status_label = QLabel("1단계: Grok 브라우저 준비 (2개 탭)")
        self.grok_status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.grok_status_label)

        # 폴더 선택
        path_layout = QHBoxLayout()
        self.grok_input_dir = QLineEdit()
        self.grok_input_dir.setPlaceholderText("이미지(1.jpg, 2.jpg...)가 있는 폴더")
        btn_browse_grok = QPushButton("폴더 선택")
        btn_browse_grok.clicked.connect(lambda: self.browse_folder(self.grok_input_dir))
        
        path_layout.addWidget(QLabel("이미지 폴더:"))
        path_layout.addWidget(self.grok_input_dir)
        path_layout.addWidget(btn_browse_grok)
        layout.addLayout(path_layout)

        # 브라우저 준비 버튼
        self.btn_grok_prepare = QPushButton("🌐 1. Grok 브라우저 준비 (2 Tabs)")
        self.btn_grok_prepare.setStyleSheet("height: 40px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_grok_prepare.clicked.connect(self.launch_browser_grok_gen)
        layout.addWidget(self.btn_grok_prepare)

        # 시작 버튼
        btn_h_layout = QHBoxLayout()
        self.btn_grok_start = QPushButton("🚀 2. Grok 자동 생성 시작")
        self.btn_grok_start.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_grok_start.clicked.connect(self.start_grok_generation)
        
        self.btn_grok_stop = QPushButton("🛑 중지")
        self.btn_grok_stop.setEnabled(False)
        self.btn_grok_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_grok_stop.clicked.connect(self.stop_grok_generation)

        btn_h_layout.addWidget(self.btn_grok_start)
        btn_h_layout.addWidget(self.btn_grok_stop)
        layout.addLayout(btn_h_layout)

        # 로그창
        self.grok_log_display = QTextEdit()
        self.grok_log_display.setReadOnly(True)
        self.grok_log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        layout.addWidget(self.grok_log_display)

        self.tab_grok_gen.setLayout(layout)

    def launch_browser_grok_gen(self):
        try:
             # 브라우저 실행 (Grok 모드)
             # 기존 BrowserLauncherWorker는 port 9222/9223를 씀.
             # Grok도 9222(기본)을 쓸지, 9223(FX)를 쓸지, 아니면 새로운 9224?
             # 보통 Genspark랑 같이 쓸 일 없으므로 9222(기본) 써도 됨.
             # 하지만 LauncherWorker에 Type을 'grok'으로 넘겨서 URL을 바꿔줘야 함.
             
             if not hasattr(self, 'browser_launcher_grok'):
                 self.browser_launcher_grok = BrowserLauncherWorker('grok')
                 self.browser_launcher_grok.log_signal.connect(self.grok_log_display.append)
                 self.browser_launcher_grok.finished.connect(self.on_grok_browser_launch_finished)
                 
             self.browser_launcher_grok.start()
        except Exception as e:
             QMessageBox.critical(self, "오류", f"브라우저 실행 오류: {e}")

    def on_grok_browser_launch_finished(self, result):
        driver, error = result
        if driver:
            self.driver = driver
            self.grok_log_display.append("✅ Grok 브라우저 준비 완료!")
            
            # 2개 탭 만들기 (이미 1개 열려있음)
            try:
                # wait for load
                time.sleep(2)
                current = len(driver.window_handles)
                needed = 2 - current
                for _ in range(needed):
                    driver.execute_script("window.open('https://grok.com/imagine');")
                    time.sleep(0.5)
                
                self.grok_log_display.append(f"ℹ️ 탭 {len(driver.window_handles)}개 준비됨.")
                
            except Exception as e:
                self.grok_log_display.append(f"⚠️ 탭 추가 중 오류: {e}")
                
        else:
            QMessageBox.critical(self, "오류", f"브라우저 실행 실패: {error}")

    def start_grok_generation(self):
        input_dir = self.grok_input_dir.text().strip()
        if not input_dir or not os.path.exists(input_dir):
            QMessageBox.warning(self, "경로 오류", "이미지 폴더 경로가 올바르지 않습니다.")
            return
            
        if not self.driver:
             QMessageBox.warning(self, "브라우저 오류", "먼저 브라우저를 준비해주세요 (1단계).")
             return
             
        self.btn_grok_start.setEnabled(False)
        self.btn_grok_stop.setEnabled(True)
        self.grok_log_display.clear()
        self.grok_log_display.append("🚀 Grok 자동생성 시작...")
        
        self.grok_worker = GrokMultiTabWorker(input_dir, self.driver)
        self.grok_worker.progress.connect(lambda s: self.grok_log_display.append(f"[{datetime.now().strftime('%H:%M:%S')}] {s}"))
        self.grok_worker.log_signal.connect(lambda s: self.grok_log_display.append(f"[{datetime.now().strftime('%H:%M:%S')}] {s}"))
        self.grok_worker.finished.connect(self.on_grok_gen_finished)
        self.grok_worker.error.connect(lambda s: self.grok_log_display.append(f"ERROR: {s}"))
        self.grok_worker.start()

    def stop_grok_generation(self):
        if hasattr(self, 'grok_worker') and self.grok_worker.isRunning():
            self.grok_worker.stop()
            self.grok_log_display.append("🛑 중지 요청됨...")

    def on_grok_gen_finished(self, msg, elapsed):
        self.btn_grok_start.setEnabled(True)
        self.btn_grok_stop.setEnabled(False)
        self.grok_log_display.append(f"🏁 작업 완료: {msg} (소요시간: {elapsed:.2f}초)")
        QMessageBox.information(self, "완료", f"Grok 생성 작업 완료\n{msg}")
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
        
        conv_in_group = QGroupBox("WAV 폴더 선택 (WAV -> MP3)")
        conv_in_layout = QHBoxLayout()
        self.at_wav_folder = QLineEdit()
        self.at_wav_folder.setPlaceholderText("폴더를 선택하세요. (해당 폴더의 모든 WAV 변환)")
        btn_wav = QPushButton("폴더 찾기")
        btn_wav.clicked.connect(lambda: self.browse_folder(self.at_wav_folder))
        conv_in_layout.addWidget(self.at_wav_folder)
        conv_in_layout.addWidget(btn_wav)
        conv_in_group.setLayout(conv_in_layout)
        

        l_conv.addWidget(conv_in_group)
        
        # 합치기 옵션 추가
        self.chk_merge_mp3 = QCheckBox("변환 후 MP3 파일 하나로 합치기 (영상 파일은 순서대로 정렬됨 1,2,3...)")
        self.chk_merge_mp3.setChecked(True)
        l_conv.addWidget(self.chk_merge_mp3)
        
        self.btn_at_convert = QPushButton("1. WAV -> MP3 변환 시작 (폴더 전체)")
        self.btn_at_convert.setStyleSheet("background-color: #009688; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_convert.clicked.connect(lambda: self.start_audio_transcribe("convert"))
        l_conv.addWidget(self.btn_at_convert)
        l_conv.addStretch()
        
        tab_conv.setLayout(l_conv)
        sub_tabs.addTab(tab_conv, "1. Convert MP3")
        
        # SubTab 2: MP3 -> SRT
        tab_srt = QWidget()
        l_srt = QVBoxLayout()
        
        srt_in_group = QGroupBox("MP3/MP4 파일 선택")
        srt_in_layout = QHBoxLayout()
        self.at_mp3_files = QLineEdit()
        self.at_mp3_files.setPlaceholderText("선택된 파일이 없습니다.")
        btn_mp3 = QPushButton("파일 찾기")
        btn_mp3.clicked.connect(lambda: self.browse_files(self.at_mp3_files, "Media Files (*.mp3 *.mp4)"))
        srt_in_layout.addWidget(self.at_mp3_files)
        srt_in_layout.addWidget(btn_mp3)
        srt_in_group.setLayout(srt_in_layout)
        
        l_srt.addWidget(srt_in_group)
        
        self.btn_at_transcribe = QPushButton("2. MP3/MP4 -> SRT 자막 생성 시작 (선택 파일)")
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

        # SubTab 4: Merge Audio/SRT
        tab_merge = QWidget()
        l_merge = QVBoxLayout()
        
        merge_in_group = QGroupBox("파일 폴더 선택 (1.mp3, 1.srt ... 들이 있는 폴더)")
        merge_in_layout = QHBoxLayout()
        self.at_merge_folder = QLineEdit()
        self.at_merge_folder.setPlaceholderText("폴더를 선택하세요.")
        btn_merge = QPushButton("폴더 찾기")
        btn_merge.clicked.connect(lambda: self.browse_folder(self.at_merge_folder))
        merge_in_layout.addWidget(self.at_merge_folder)
        merge_in_layout.addWidget(btn_merge)
        merge_in_group.setLayout(merge_in_layout)
        
        l_merge.addWidget(merge_in_group)
        l_merge.addWidget(QLabel("ℹ️ 폴더 내의 1.mp3, 2.mp3 등 숫자 순서대로 오디오와 SRT를 하나로 합칩니다."))
        
        self.btn_at_merge = QPushButton("4. MP3 + SRT 합치기 실행")
        self.btn_at_merge.setStyleSheet("background-color: #FF9800; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_merge.clicked.connect(self.start_audio_srt_merge)
        l_merge.addWidget(self.btn_at_merge)
        l_merge.addStretch()
        
        tab_merge.setLayout(l_merge)
        sub_tabs.addTab(tab_merge, "4. Merge Audio/SRT")
        
        # SubTab 5: Compress MP3
        tab_compress = QWidget()
        l_compress = QVBoxLayout()
        
        comp_in_group = QGroupBox("MP3 파일 선택 (용량 줄이기)")
        comp_in_layout = QHBoxLayout()
        self.at_comp_files = QLineEdit()
        self.at_comp_files.setPlaceholderText("선택된 파일이 없습니다.")
        btn_comp = QPushButton("파일 찾기")
        btn_comp.clicked.connect(lambda: self.browse_files(self.at_comp_files, "Audio Files (*.mp3 *.wav *.m4a)"))
        comp_in_layout.addWidget(self.at_comp_files)
        comp_in_layout.addWidget(btn_comp)
        comp_in_group.setLayout(comp_in_layout)
        
        l_compress.addWidget(comp_in_group)
        
        bitrate_layout = QHBoxLayout()
        bitrate_layout.addWidget(QLabel("압축 비트레이트:"))
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["16k", "32k", "64k", "128k"])
        self.combo_bitrate.setCurrentText("64k") # Whisper용으로 64k면 충분
        bitrate_layout.addWidget(self.combo_bitrate)
        bitrate_layout.addWidget(QLabel(" (비트레이트가 낮을수록 용량이 작아집니다.)"))
        bitrate_layout.addStretch()
        l_compress.addLayout(bitrate_layout)
        
        self.btn_at_compress = QPushButton("5. MP3 용량 줄이기 시작")
        self.btn_at_compress.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.btn_at_compress.clicked.connect(lambda: self.start_audio_transcribe("compress"))
        l_compress.addWidget(self.btn_at_compress)
        l_compress.addStretch()
        
        tab_compress.setLayout(l_compress)
        sub_tabs.addTab(tab_compress, "5. Compress MP3")
        
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
            folder_path = self.at_wav_folder.text().strip()
            if not folder_path or not os.path.isdir(folder_path):
                QMessageBox.warning(self, "경고", "유효한 폴더 경로가 아닙니다.")
                return
            
            # 폴더 내 wav 파일 검색
            files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.wav')]
            
            # WAV가 없더라도 병합 옵션이 켜져있고 MP3가 있다면 진행
            if not files and self.chk_merge_mp3.isChecked():
                mp3_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.mp3')]
                if mp3_files:
                    files = mp3_files # MP3 파일들을 타겟으로 설정하여 워커에 경로 전달
            
            if not files:
                 QMessageBox.warning(self, "경고", "해당 폴더에 WAV (또는 병합할 MP3) 파일이 없습니다.")
                 return
            target_files = files
            
        elif mode == "transcribe":
            raw_text = self.at_mp3_files.text().strip()
            if not raw_text:
                QMessageBox.warning(self, "경고", "선택된 파일이 없습니다.")
                return
            target_files = [f.strip() for f in raw_text.split(";") if f.strip()]
            
        elif mode == "all":
            raw_text = self.at_all_files.text().strip()
            if not raw_text:
                 QMessageBox.warning(self, "경고", "선택된 파일이 없습니다.")
                 return
            target_files = [f.strip() for f in raw_text.split(";") if f.strip()]
            
        elif mode == "compress":
            raw_text = self.at_comp_files.text().strip()
            if not raw_text:
                 QMessageBox.warning(self, "경고", "선택된 파일이 없습니다.")
                 return
            target_files = [f.strip() for f in raw_text.split(";") if f.strip()]
            
        if not target_files:
            QMessageBox.warning(self, "경고", "처리할 파일 목록이 없습니다.")
            return

        model_name = self.combo_whisper_model.currentText()
        if mode == "compress":
            model_name = self.combo_bitrate.currentText() # 비트레이트를 model_name 대신 전달
            
        merge_mp3 = self.chk_merge_mp3.isChecked() if mode == "convert" else False
        
        self.at_log.append(f"🚀 작업 시작: {mode} (Model/Bitrate: {model_name}, Merge: {merge_mp3})")
        self.at_log.append(f"📂 대상: {len(target_files)}개 파일")
        
        # Disable buttons
        self.btn_at_convert.setEnabled(False)
        self.btn_at_transcribe.setEnabled(False)
        self.btn_at_all.setEnabled(False)
        self.btn_at_merge.setEnabled(False)
        if hasattr(self, 'btn_at_compress'):
            self.btn_at_compress.setEnabled(False)
        
        self.at_worker = AudioTranscriberWorker(target_files, mode, model_name, merge_mp3)
        self.at_worker.log_signal.connect(self.at_log.append)
        self.at_worker.finished.connect(self.on_at_finished)
        self.at_worker.error.connect(self.on_at_error)
        self.at_worker.start()

    def start_audio_srt_merge(self):
        folder_path = self.at_merge_folder.text().strip()
        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "경고", "유효한 폴더 경로가 아닙니다.")
            return

        self.btn_at_convert.setEnabled(False)
        self.btn_at_transcribe.setEnabled(False)
        self.btn_at_all.setEnabled(False)
        self.btn_at_merge.setEnabled(False)
        if hasattr(self, 'btn_at_compress'):
            self.btn_at_compress.setEnabled(False)

        self.at_log.append(f"🚀 MP3/SRT 합치기 작업 시작: {folder_path}")
        
        self.merge_worker = AudioSrtMergerWorker(folder_path)
        self.merge_worker.log_signal.connect(self.at_log.append)
        self.merge_worker.finished.connect(self.on_at_finished)
        self.merge_worker.error.connect(self.on_at_error)
        self.merge_worker.start()
        
    def on_at_finished(self, msg):
        self.btn_at_convert.setEnabled(True)
        self.btn_at_transcribe.setEnabled(True)
        self.btn_at_all.setEnabled(True)
        self.btn_at_merge.setEnabled(True)
        if hasattr(self, 'btn_at_compress'):
            self.btn_at_compress.setEnabled(True)
        self.at_log.append(f"🏁 {msg}")
        
    def on_at_error(self, err):
        self.at_log.append(f"❌ 오류: {err}")
        self.btn_at_convert.setEnabled(True)
        self.btn_at_transcribe.setEnabled(True)
        self.btn_at_all.setEnabled(True)
        self.btn_at_merge.setEnabled(True)
        if hasattr(self, 'btn_at_compress'):
            self.btn_at_compress.setEnabled(True)

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

    def initTabScriptSplit(self):
        layout = QVBoxLayout()
        
        # 설명 레이블
        layout.addWidget(QLabel("📖 대본을 일정 글자 수 단위로 자릅니다. (마침표 기준)"))
        
        # 설정 레이아웃
        config_layout = QHBoxLayout()
        self.spin_split_limit = QSpinBox()
        self.spin_split_limit.setRange(100, 5000)
        self.spin_split_limit.setValue(800)
        self.spin_split_limit.setSuffix(" 자")
        config_layout.addWidget(QLabel("기준 글자 수:"))
        config_layout.addWidget(self.spin_split_limit)
        config_layout.addStretch()
        layout.addLayout(config_layout)
        
        # 입력 영역
        layout.addWidget(QLabel("입력 대본:"))
        self.txt_split_input = QTextEdit()
        self.txt_split_input.setPlaceholderText("여기에 긴 대본을 붙여넣으세요...")
        layout.addWidget(self.txt_split_input)
        
        # 실행 버튼
        self.btn_run_split = QPushButton("✂️ 대본 자르기 실행")
        self.btn_run_split.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_run_split.clicked.connect(self.split_script)
        layout.addWidget(self.btn_run_split)
        
        # 출력 영역
        layout.addWidget(QLabel("분할 결과:"))
        self.txt_split_output = QTextEdit()
        self.txt_split_output.setReadOnly(True)
        layout.addWidget(self.txt_split_output)

        # 복사 버튼
        self.btn_copy_split = QPushButton("📋 결과 전체 복사")
        self.btn_copy_split.clicked.connect(lambda: self.copy_to_clipboard(self.txt_split_output))
        layout.addWidget(self.btn_copy_split)
        
        self.tab_script_split.setLayout(layout)

    def split_script(self):
        text = self.txt_split_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "알림", "대본을 입력해주세요.")
            return
            
        limit = self.spin_split_limit.value()
        max_limit = limit + 50 # 800~850자(공백 제외) 허용
        
        def get_idx_by_non_space_count(s, target):
            count = 0
            for i, char in enumerate(s):
                if not char.isspace():
                    count += 1
                if count >= target:
                    return i
            return len(s) - 1

        def is_safe_dot(s, idx):
            # 숫자 사이의 마침표(소수점)인지 확인
            if 0 < idx < len(s) - 1:
                if s[idx-1].isdigit() and s[idx+1].isdigit():
                    return False
            return True

        segments = []
        remaining = text
        
        while remaining:
            # 남은 텍스트의 공백 제외 글자 수 확인
            non_space_len = len([c for c in remaining if not c.isspace()])
            
            if non_space_len <= max_limit:
                segments.append(remaining)
                break
            
            # 기준 인덱스 찾기
            limit_idx = get_idx_by_non_space_count(remaining, limit)
            max_limit_idx = get_idx_by_non_space_count(remaining, max_limit)
            
            # 1. limit_idx ~ max_limit_idx 사이에서 '안전한' 마침표 찾기
            found_idx = -1
            for i in range(limit_idx, max_limit_idx + 1):
                if i < len(remaining) and remaining[i] == "." and is_safe_dot(remaining, i):
                    found_idx = i
                    break
            
            if found_idx == -1:
                # 2. 범위 내에 없으면 limit_idx 이전에서 가장 가까운 '안전한' 마침표 찾기
                for i in range(limit_idx, -1, -1):
                    if remaining[i] == "." and is_safe_dot(remaining, i):
                        found_idx = i
                        break
                
                if found_idx == -1:
                    # 3. 마침표가 전혀 없으면 그냥 limit_idx에서 자름
                    found_idx = limit_idx
            
            # 자르기 (마침표 포함)
            cut_point = found_idx + 1
            segment = remaining[:cut_point].strip()
            segments.append(segment)
            remaining = remaining[cut_point:].strip()
            
        # 결과 표시
        result_text = ""
        for i, seg in enumerate(segments, 1):
            result_text += f"{i}. {seg}\n\n"
            
        self.txt_split_output.setPlainText(result_text.strip())
        self.log_signal.emit(f"✅ 대본이 {len(segments)}개로 분활되었습니다. (공백 미포함 기준)")

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

        # Filter Channel
        self.combo_video_filter_channel = QComboBox()
        self.combo_video_filter_channel.setMinimumWidth(150)
        self.combo_video_filter_channel.currentIndexChanged.connect(self.load_video_list)
        btn_layout.addWidget(QLabel("채널 필터:"))
        btn_layout.addWidget(self.combo_video_filter_channel)
        
        btn_layout.addStretch()
        
        self.btn_new_video = QPushButton("➕ 신규 등록 (New)")
        self.btn_new_video.setFixedWidth(150)
        self.btn_new_video.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_new_video.clicked.connect(lambda: self.switch_to_form_view(None))
        
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
        # ID Display
        self.lbl_id_display = QLabel("신규")
        self.lbl_id_display.setStyleSheet("font-weight: bold; color: #00bcd4; font-size: 14px;")

        input_layout.addWidget(QLabel("ID:"), 0, 0)
        input_layout.addWidget(self.lbl_id_display, 0, 1)

        input_layout.addWidget(QLabel("채널:"), 1, 0)
        input_layout.addWidget(self.combo_channel, 1, 1)

        input_layout.addWidget(QLabel("제목:"), 2, 0)
        input_layout.addWidget(self.input_title, 2, 1)
        
        input_layout.addWidget(QLabel("대본:"), 3, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_script, 3, 1)
        
        input_layout.addWidget(QLabel("TTS 텍스트:"), 4, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_tts_text, 4, 1)

        input_layout.addWidget(QLabel("이미지 스크립트:"), 5, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_img_script, 5, 1)

        input_layout.addWidget(QLabel("설명:"), 6, 0, Qt.AlignTop)
        input_layout.addWidget(self.input_description, 6, 1)
        
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
        
        self.btn_delete_video = QPushButton("삭제")
        self.btn_delete_video.setFixedSize(120, 30)
        self.btn_delete_video.setStyleSheet("font-weight: bold; background-color: #dc3545; color: white; border-radius: 5px;")
        self.btn_delete_video.clicked.connect(self.delete_video_data)
        self.btn_delete_video.setVisible(False) # 기본은 숨김 (신규 등록 시)

        btn_form_layout.addWidget(self.btn_delete_video)
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
        self.current_channel_id = None
        self.current_page = 1
        self.items_per_page = 15
        self.total_pages = 1
        
        # Init Load
        # Init Load
        QTimer.singleShot(500, self.load_video_filter_channels)
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

    def load_video_filter_channels(self):
        try:
            self.combo_video_filter_channel.blockSignals(True)
            self.combo_video_filter_channel.clear()
            self.combo_video_filter_channel.addItem("전체 채널", None)
            
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT channel_id, channel_name FROM channel WHERE state='1' ORDER BY channel_id ASC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            for row in rows:
                self.combo_video_filter_channel.addItem(row['channel_name'], row['channel_id'])
                
            self.combo_video_filter_channel.blockSignals(False)
        except Exception as e:
            self.log_signal.emit(f"필터 채널 로드 오류: {e}")

    def switch_to_form_view(self, video_id=None, channel_id=None):
        self.current_video_id = video_id
        self.current_channel_id = channel_id
        
        # Load Channels first
        self.load_channels()
        
        # Clear fields
        self.input_title.clear()
        self.input_script.clear()
        self.input_img_script.clear()
        self.input_tts_text.clear()
        self.input_description.clear()
        self.lbl_id_display.setText("신규")
        
        if video_id is None:
            # Create Mode
            self.btn_save_video.setText("저장")
            self.btn_delete_video.setVisible(False)
        else:
            # Edit Mode - Fetch Data
            self.btn_save_video.setText("수정")
            self.btn_delete_video.setVisible(True)
            self.load_video_detail(video_id, channel_id)
            
        self.video_list_stack.setCurrentIndex(1)

    def load_video_detail(self, video_id, channel_id):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM video WHERE id = %s AND channel_id = %s", (video_id, channel_id))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                self.lbl_id_display.setText(str(row['id']))
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
        item_ch = self.video_table.item(row, 1)
        if item and item_ch:
            video_id = item.text()
            channel_id = item_ch.data(Qt.UserRole)
            self.switch_to_form_view(video_id, channel_id)

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
                # 1. Get Max ID for this channel
                cursor.execute("SELECT IFNULL(MAX(id), 0) + 1 FROM video WHERE channel_id = %s", (channel_id,))
                new_id = cursor.fetchone()[0]

                query = """
                    INSERT INTO video (channel_id, id, title, script, img_script, tts_text, description, use_yn)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Y')
                """
                cursor.execute(query, (channel_id, new_id, title, script, img_script, tts_text, description))
                msg = "새로운 영상 데이터가 등록되었습니다."
            else:
                # UPDATE
                # channel_id 변경 시 단순히 값만 업데이트 (move channel)
                query = """
                    UPDATE video 
                    SET channel_id=%s, title=%s, script=%s, img_script=%s, tts_text=%s, description=%s
                    WHERE channel_id=%s AND id=%s
                """
                cursor.execute(query, (channel_id, title, script, img_script, tts_text, description, self.current_channel_id, self.current_video_id))
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

    def delete_video_data(self):
        if not self.current_video_id:
            return

        reply = QMessageBox.question(self, '삭제 확인', 
                                     f"정말로 삭제하시겠습니까? (ID: {self.current_video_id})", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                if not getattr(self, 'tts_client', None):
                     self.tts_client = ElevenLabsClient()
                conn = self.tts_client.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM video WHERE channel_id = %s AND id = %s", (self.current_channel_id, self.current_video_id))
                conn.commit()
                cursor.close()
                conn.close()
                
                QMessageBox.information(self, "삭제 완료", "삭제되었습니다.")
                self.show_list_view()
                
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류 발생: {e}")

    def load_video_list(self):
        try:
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # 1. Get Total Count (Only state='1' channels)
            filter_channel_id = self.combo_video_filter_channel.currentData()
            
            where_clause = "WHERE c.state = '1'"
            params = []
            
            if filter_channel_id is not None:
                where_clause += " AND v.channel_id = %s"
                params.append(filter_channel_id)
            
            count_query = f"SELECT COUNT(*) as cnt FROM video v JOIN channel c ON v.channel_id = c.channel_id {where_clause}"
            cursor.execute(count_query, tuple(params))
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
            # Sort by created_at DESC to show newest first
            query = f"""
                SELECT v.*, c.channel_name 
                FROM video v 
                JOIN channel c ON v.channel_id = c.channel_id 
                {where_clause}
                ORDER BY v.created_at DESC, v.id DESC
                LIMIT {self.items_per_page} OFFSET {offset}
            """
            cursor.execute(query, tuple(params))
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
                item_ch = QTableWidgetItem(str(row['channel_name'] or ''))
                item_ch.setData(Qt.UserRole, row['channel_id'])
                self.video_table.setItem(row_idx, 1, item_ch)
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
        
        self.combo_prompt_filter_type.currentIndexChanged.connect(lambda: self.change_prompt_page(0)) # Reset to page 1 on filter
        
        # Channel Filter Combo
        self.combo_prompt_filter_channel = QComboBox()
        self.combo_prompt_filter_channel.setFixedWidth(150)
        self.combo_prompt_filter_channel.currentIndexChanged.connect(lambda: self.change_prompt_page(0))
        
        self.btn_new_prompt = QPushButton("➕ 신규 등록 (New)")
        self.btn_new_prompt.setFixedWidth(150)
        self.btn_new_prompt.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_new_prompt.clicked.connect(lambda: self.switch_to_prompt_form(None))
        
        btn_layout.addWidget(QLabel("구분 필터:"))
        btn_layout.addWidget(self.combo_prompt_filter_type)
        btn_layout.addWidget(QLabel("채널명:"))
        btn_layout.addWidget(self.combo_prompt_filter_channel)
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

        # Load channels for filter
        QTimer.singleShot(1000, self.load_prompt_filter_channels)
        
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

    def load_prompt_filter_channels(self):
        try:
            self.combo_prompt_filter_channel.clear()
            self.combo_prompt_filter_channel.addItem("전체", None)
            
            if not getattr(self, 'tts_client', None):
                 self.tts_client = ElevenLabsClient()
            
            conn = self.tts_client.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT channel_id, channel_name FROM channel WHERE state='1' ORDER BY channel_id ASC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            for row in rows:
                self.combo_prompt_filter_channel.addItem(row['channel_name'], row['channel_id'])
                
        except Exception as e:
            self.log_signal.emit(f"필터 채널 로드 오류: {e}")

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
            where_clause = "WHERE c.state = '1' AND (p.use_yn = 'Y' OR p.use_yn IS NULL)"
            params = []
            
            if filter_type != '전체':
                where_clause += " AND p.prompt_type = %s"
                params.append(filter_type)

            filter_channel_id = self.combo_prompt_filter_channel.currentData()
            if filter_channel_id is not None:
                where_clause += " AND c.channel_id = %s"
                params.append(filter_channel_id)
            
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

    def initTabShorts(self):
        layout = QVBoxLayout()

        # 1. 안내 문구
        layout.addWidget(QLabel("📢 배경 동영상 + 오디오(MP3/SRT) + 금시세 정보를 합성하여 숏츠를 생성합니다."))
        
        # 2. 파일/폴더 설정
        file_group = QGroupBox("파일 및 폴더 설정")
        file_layout = QGridLayout()

        # 배경 동영상
        self.shorts_bg_video = QLineEdit()
        self.shorts_bg_video.setPlaceholderText("배경으로 사용할 동영상 파일(.mp4)")
        btn_browse_bg = QPushButton("배경 영상 선택")
        btn_browse_bg.clicked.connect(lambda: self.browse_single_file(self.shorts_bg_video, "Video Files (*.mp4 *.mov *.avi)"))
        
        file_layout.addWidget(QLabel("배경 동영상:"), 0, 0)
        file_layout.addWidget(self.shorts_bg_video, 0, 1)
        file_layout.addWidget(btn_browse_bg, 0, 2)

        # 배경 음악 (NEW)
        self.shorts_bg_music = QLineEdit()
        self.shorts_bg_music.setPlaceholderText("배경 음악 파일(.mp3) - 선택 사항")
        btn_browse_music = QPushButton("배경 음악 선택")
        btn_browse_music.clicked.connect(lambda: self.browse_single_file(self.shorts_bg_music, "Audio Files (*.mp3 *.wav)"))
        
        file_layout.addWidget(QLabel("배경 음악:"), 1, 0)
        file_layout.addWidget(self.shorts_bg_music, 1, 1)
        file_layout.addWidget(btn_browse_music, 1, 2)
        
        # 배경 음악 볼륨
        self.shorts_music_volume = QSlider(Qt.Horizontal)
        self.shorts_music_volume.setRange(0, 100)
        self.shorts_music_volume.setValue(20) # Default 20%
        self.lbl_music_vol = QLabel("20%")
        self.shorts_music_volume.valueChanged.connect(lambda v: self.lbl_music_vol.setText(f"{v}%"))
        
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(self.shorts_music_volume)
        vol_layout.addWidget(self.lbl_music_vol)
        
        file_layout.addWidget(QLabel("음악 볼륨:"), 2, 0)
        file_layout.addLayout(vol_layout, 2, 1, 1, 2)

        # 오디오/자막 폴더
        self.shorts_audio_dir = QLineEdit()
        self.shorts_audio_dir.setPlaceholderText("MP3와 SRT 파일이 있는 폴더")
        btn_browse_audio = QPushButton("MP3/SRT 폴더")
        btn_browse_audio.clicked.connect(lambda: self.browse_folder(self.shorts_audio_dir))
        
        file_layout.addWidget(QLabel("MP3/SRT 폴더:"), 3, 0)
        file_layout.addWidget(self.shorts_audio_dir, 3, 1)
        file_layout.addWidget(btn_browse_audio, 3, 2)
        
        # 출력 폴더
        self.shorts_output_dir = QLineEdit()
        self.shorts_output_dir.setPlaceholderText("결과물 저장 폴더")
        btn_browse_out = QPushButton("저장 폴더 선택")
        btn_browse_out.clicked.connect(lambda: self.browse_folder(self.shorts_output_dir))
        
        file_layout.addWidget(QLabel("저장 폴더:"), 4, 0)
        file_layout.addWidget(self.shorts_output_dir, 4, 1)
        file_layout.addWidget(btn_browse_out, 4, 2)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 3. 금시세 정보 입력
        info_group = QGroupBox("금시세 정보 입력")
        info_layout = QVBoxLayout()
        
        self.shorts_gold_info = QTextEdit()
        self.shorts_gold_info.setPlaceholderText("""예시:
🌎 국제 시세 (SDBullion/Widget) - 2026.02.06 14:39 기준
  💰 Gold: $4,864.68 (어제: $4,782.47)
  🥈 Silver: $74.05 (어제: $71.35)

🌎 국내 시세  - 2026.02.06 기준
🏷️ 순금
  🔻 팔때: 845,000원 (▼ 20,000)
  🔺 살때: 994,000원 (▼ 16,000)
------------------------------
🏷️ 18k
  🔻 팔때: 623,000원 (▼ 15,000)
  🔺 살때: 제품시세 적용원
...""")
        info_layout.addWidget(self.shorts_gold_info)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 4. 실행 버튼
        self.btn_start_shorts = QPushButton("✨ 금시세 숏츠 일괄 생성 시작")
        self.btn_start_shorts.setStyleSheet("height: 50px; font-weight: bold; background-color: #E91E63; color: white; border-radius: 8px; margin-top: 10px;")
        self.btn_start_shorts.clicked.connect(self.start_batch_shorts)
        layout.addWidget(self.btn_start_shorts)

        # 5. 로그창
        self.shorts_log = QTextEdit()
        self.shorts_log.setReadOnly(True)
        self.shorts_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        self.shorts_log.setMaximumHeight(150)
        layout.addWidget(self.shorts_log)

        self.tab_shorts.setLayout(layout)

    def start_batch_shorts(self):
        bg_video = self.shorts_bg_video.text().strip()
        bg_music = self.shorts_bg_music.text().strip()
        music_vol = self.shorts_music_volume.value() / 100.0 # 0.0 ~ 1.0
        
        audio_dir = self.shorts_audio_dir.text().strip()
        out_dir = self.shorts_output_dir.text().strip()
        gold_text = self.shorts_gold_info.toPlainText().strip()
        
        if not os.path.exists(bg_video):
            QMessageBox.warning(self, "경고", "배경 동영상 파일이 없습니다.")
            return
            
        if not os.path.exists(audio_dir):
            QMessageBox.warning(self, "경고", "오디오 폴더가 없습니다.")
            return
            
        if not gold_text:
            QMessageBox.warning(self, "경고", "금시세 정보를 입력해주세요.")
            return
            
        if not out_dir:
            out_dir = os.path.join(audio_dir, "shorts_output")
            
        self.btn_start_shorts.setEnabled(False)
        self.shorts_log.append("🚀 금시세 숏츠 생성을 시작합니다...")
        
        # Worker 실행
        from youtube_worker_video import GoldShortsWorker
        self.shorts_worker = GoldShortsWorker(bg_video, audio_dir, gold_text, out_dir, bg_music, music_vol)
        
        self.shorts_worker.log_signal.connect(self.shorts_log.append)
        self.shorts_worker.finished.connect(lambda msg, t: [self.shorts_log.append(f"🏁 {msg}"), self.btn_start_shorts.setEnabled(True)])
        self.shorts_worker.error.connect(lambda err: [self.shorts_log.append(f"❌ {err}"), self.btn_start_shorts.setEnabled(True)])
        
        self.shorts_worker.start()

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
                
                # --- Font Loading ---
                font_path = r"D:\youtube\fonts\GmarketSansTTFBold.ttf"
                target_family = "Malgun Gothic" # Default Fallback
                
                if os.path.exists(font_path):
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        loaded_families = QFontDatabase.applicationFontFamilies(font_id)
                        if loaded_families:
                            target_family = loaded_families[0]
                            # self.log_signal.emit(f"✅ 폰트 로드 성공: {target_family}")
                else:
                    self.log_signal.emit(f"⚠️ 폰트 파일 없음: {font_path} (맑은 고딕 사용)")

                # --- Helper: Draw Text with Outline/Shadow ---
                def draw_text_with_effect(rect, alignment, text, font, color, outline_color=QColor(0,0,0,180), outline_width=2):
                    painter.setFont(font)
                    
                    # 1. Shadow/Outline (Draw offset/stroke)
                    painter.setPen(outline_color)
                    # Simple shadow effect
                    shadow_offset = 3 
                    shadow_rect = rect.translated(shadow_offset, shadow_offset)
                    painter.drawText(shadow_rect, alignment, text)
                    
                    # 2. Main Text
                    painter.setPen(color)
                    painter.drawText(rect, alignment, text)

                # --- Layout Config ---
                top_bg_h = 280 
                
                # Bottom Panel
                rows_count = len(self.gold_data['rows'])
                header_h = 75
                row_h = 80 # Reduced from 90
                gap = 2    # Reduced from 6
                bottom_padding = 50
                date_area_h = 60
                
                total_table_h = date_area_h + header_h + 10 + (rows_count * (row_h + gap)) + bottom_padding
                
                bottom_bg_start = H - total_table_h - 220 # Lift up 100px from base 120
                bottom_bg_h = total_table_h
                
                # Background Colors
                bg_color = QColor(0, 0, 0, 160) 

                # Draw Top Background 
                painter.setBrush(bg_color)
                painter.setPen(Qt.NoPen)
                painter.drawRect(0, 0, W, top_bg_h)
                
                # --- 1. Top Content ---
                # Line 1: "오늘의 금시세"
                font_title = QFont(target_family, 75, QFont.Bold)
                draw_text_with_effect(QRect(0, 30, W, 110), Qt.AlignCenter, "오늘의 금시세", font_title, QColor("#FFD700")) # Gold

                # Line 2: International Spot Prices
                if 'international' in self.gold_data:
                    intl = self.gold_data['international']
                    if intl['gold'] != '-':
                        font_label = QFont(target_family, 42, QFont.Bold)
                        painter.setFont(font_label)
                        fm = QFontMetrics(font_label)
                        
                        txt_label = "국제  "
                        txt_gold = f"Gold ${intl['gold']}  "
                        txt_silver = f"Silver ${intl['silver']}"
                        
                        w_label = fm.width(txt_label)
                        w_gold = fm.width(txt_gold)
                        w_silver = fm.width(txt_silver)
                        
                        total_w = w_label + w_gold + w_silver
                        start_x = (W - total_w) // 2
                        
                        y_pos = 160 
                        h_height = 80
                        
                        draw_text_with_effect(QRect(start_x, y_pos, w_label, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_label, font_label, QColor("#FFD700"))
                        draw_text_with_effect(QRect(start_x + w_label, y_pos, w_gold, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_gold, font_label, QColor("#FFD700"))
                        draw_text_with_effect(QRect(start_x + w_label + w_gold, y_pos, w_silver, h_height), Qt.AlignLeft|Qt.AlignVCenter, txt_silver, font_label, QColor("#FFFFE0")) 
                        

                # Draw Bottom Background Here
                painter.setBrush(bg_color)
                painter.setPen(Qt.NoPen)
                painter.drawRect(0, bottom_bg_start, W, bottom_bg_h)
                
                # --- Helper for glass boxes ---
                def draw_glass_rect(rect, radius=15):
                    painter.setBrush(QColor(60, 60, 60, 180)) 
                    painter.setPen(QPen(QColor(150, 150, 150, 80), 2))
                    painter.drawRoundedRect(rect, radius, radius)
                
                curr_y = bottom_bg_start + 20
                
                # Column Config
                mx = 30
                grid_w = W - (mx * 2)
                col1_w = int(grid_w * 0.28)
                col2_w = int(grid_w * 0.36)
                col3_w = int(grid_w * 0.36)
                
                col1_x = mx
                col2_x = mx + col1_w
                col3_x = mx + col1_w + col2_w

                # --- Date & Time ---
                date_str = self.gold_data['date'] 
                time_str = ""
                if 'international' in self.gold_data:
                    intl_t = self.gold_data['international'].get('time', '')
                    if ' ' in intl_t: time_str = intl_t.split(' ')[1]
                if not time_str: time_str = datetime.now().strftime("%H:%M")

                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    date_display = dt.strftime("%Y.%m.%d")
                except:
                    date_display = date_str
                
                full_date_str = f"{date_display} {time_str} 기준"
                
                font_date = QFont(target_family, 32, QFont.Bold)
                # Left align
                date_rect = QRect(mx, curr_y, grid_w, date_area_h)
                draw_text_with_effect(date_rect, Qt.AlignLeft | Qt.AlignVCenter, full_date_str, font_date, QColor("#DDDDDD"))
                
                curr_y += date_area_h 
                
                # A. Table Headers
                h_name = QRect(col1_x, curr_y, col1_w, header_h)
                h_sell = QRect(col2_x, curr_y, col2_w, header_h)
                h_buy  = QRect(col3_x, curr_y, col3_w, header_h)
                
                font_header = QFont(target_family, 36, QFont.Bold) 
                draw_text_with_effect(h_name, Qt.AlignCenter, "품목", font_header, QColor("#CCCCCC"))
                draw_text_with_effect(h_sell, Qt.AlignCenter, "파실때", font_header, QColor("#CCCCCC"))
                draw_text_with_effect(h_buy, Qt.AlignCenter, "사실때", font_header, QColor("#CCCCCC"))
                
                curr_y += header_h + 10
                
                # B. Data Rows
                font_name = QFont(target_family, 34, QFont.Bold) 
                font_price = QFont(target_family, 40, QFont.Bold) 
                
                for row in self.gold_data['rows']:
                    # Rects
                    r_name = QRect(col1_x, curr_y, col1_w, row_h)
                    r_sell = QRect(col2_x, curr_y, col2_w, row_h)
                    r_buy  = QRect(col3_x, curr_y, col3_w, row_h)
                    
                    # Bg
                    draw_glass_rect(r_name, 12)
                    draw_glass_rect(r_sell, 12)
                    draw_glass_rect(r_buy, 12)
                    
                    # Name
                    name = row['name']
                    if "돈" not in name: name += "(1돈)"
                    draw_text_with_effect(r_name, Qt.AlignCenter, name, font_name, QColor("#F0F0F0"))
                    
                    # Prices
                    draw_text_with_effect(r_sell, Qt.AlignCenter, f"{row['sell_price']}", font_price, QColor("#FFFFFF"))
                    draw_text_with_effect(r_buy, Qt.AlignCenter, f"{row['buy_price']}", font_price, QColor("#FFD700"))
                    
                    curr_y += row_h + gap
                
                for row in self.gold_data['rows']:
                    # Rects
                    r_name = QRect(col1_x, curr_y, col1_w, row_h)
                    r_sell = QRect(col2_x, curr_y, col2_w, row_h)
                    r_buy  = QRect(col3_x, curr_y, col3_w, row_h)
                    
                    # Bg
                    draw_glass_rect(r_name, 12)
                    draw_glass_rect(r_sell, 12)
                    draw_glass_rect(r_buy, 12)
                    
                    # Name
                    name = row['name']
                    if "돈" not in name: name += "(1돈)"
                    draw_text_with_effect(r_name, Qt.AlignCenter, name, font_name, QColor("#F0F0F0"))
                    
                    # Prices
                    # Middle (User Sells / Shop Buys)
                    draw_text_with_effect(r_sell, Qt.AlignCenter, f"{row['sell_price']}", font_price, QColor("#FFFFFF"))
                    
                    # Right (User Buys / Shop Sells)
                    draw_text_with_effect(r_buy, Qt.AlignCenter, f"{row['buy_price']}", font_price, QColor("#FFD700"))
                    
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
        
        # 설정값 수집 (자막 스타일 탭 설정 공유)
        style = {
            'font_family': self.combo_font.currentText(),
            'font_size': self.spin_font_size.value(),
            'text_color': self.color_text,
            'outline_color': self.color_outline,
            'bg_color': self.color_bg,
            'bg_opacity': int(self.slider_bg_opacity.value() * 2.55),
            'use_bg': self.checkbox_use_bg.isChecked(),
            'use_outline': self.checkbox_use_outline.isChecked(),
            'font_folder': self.font_folder_path.text().strip()
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

    def initTabThumbnail(self):
        layout = QVBoxLayout()
        
        # 0. Background Image
        bg_layout = QHBoxLayout()
        self.thumb_bg_path = QLineEdit()
        self.thumb_bg_path.setPlaceholderText("배경 이미지 경로 (비어있으면 검은색 1280x720)")
        btn_bg = QPushButton("배경 선택")
        btn_bg.clicked.connect(lambda: self.browse_single_file(self.thumb_bg_path, "Images (*.png *.jpg *.jpeg)"))
        bg_layout.addWidget(QLabel("배경:"))
        bg_layout.addWidget(self.thumb_bg_path)
        bg_layout.addWidget(btn_bg)
        
        # Gradient Checkbox
        self.chk_thumb_gradient = QCheckBox("하단 그라데이션")
        self.chk_thumb_gradient.setChecked(True)
        self.chk_thumb_gradient.setStyleSheet("color: white; font-weight: bold;")
        bg_layout.addWidget(self.chk_thumb_gradient)
        
        layout.addLayout(bg_layout)

        # Lines Group
        self.thumb_lines = []
        
        # Default Settings per line (Size, Y-Pos, ColorHex)
        defaults = [
            (50, 49, "#FFFF00"),  # Line 1: Yellow
            (140, 63, "#FFFFFF"), # Line 2: White
            (140, 83, "#FF0000")  # Line 3: Red
        ]
        
        for i in range(3):
            # i=0: Title (Top), i=1: Sub (Middle), i=2: Sub2 (Bottom)
            group = QGroupBox(f"줄 {i+1}")
            g_layout = QHBoxLayout()
            
            text_edit = QLineEdit()
            text_edit.setPlaceholderText(f"내용 입력 {i+1}")
            
            font_combo = QComboBox()
            font_combo.setMinimumWidth(150)
            
            # Copy items & Set Default Font from ATV Tab
            target_font = "Gmarket Sans TTF Bold"
            target_idx = 0
            
            # ATV 탭 콤보박스가 있으면 거기서 복사 (사용자 요청: 영상생성 폰트 따라가기)
            source_combo = None
            if hasattr(self, 'atv_combo_font'):
                source_combo = self.atv_combo_font
            elif hasattr(self, 'combo_font'):
                source_combo = self.combo_font
                
            if source_combo and source_combo.count() > 0:
                for j in range(source_combo.count()):
                    f_text = source_combo.itemText(j)
                    font_combo.addItem(f_text)
                
                # 현재 영상생성 탭에서 선택된 인덱스로 초기값 설정
                font_combo.setCurrentIndex(source_combo.currentIndex())
            else:
                font_combo.addItem("Arial")
            
            # Apply Defaults
            def_size, def_y, def_color = defaults[i]
            
            size_spin = QSpinBox()
            size_spin.setRange(10, 500)
            size_spin.setValue(def_size)
            size_spin.setSuffix(" px")

            # Color Button
            color_btn = QPushButton("색상")
            color_btn.current_color = def_color
            
            # Contrast Text Color for Button
            bg_c = QColor(def_color)
            text_c = 'black' if bg_c.lightness() > 128 else 'white'
            color_btn.setStyleSheet(f"background-color: {def_color}; color: {text_c}; font-weight: bold; border: 1px solid #555;")
            
            color_btn.clicked.connect(lambda checked, b=color_btn: self.pick_color_btn(b))
            
            # Y Position (Percentage)
            y_spin = QSpinBox()
            y_spin.setRange(0, 100)
            y_spin.setValue(def_y)
            y_spin.setSuffix(" %")

            g_layout.addWidget(QLabel("텍스트:"))
            g_layout.addWidget(text_edit, 3)
            g_layout.addWidget(QLabel("폰트:"))
            g_layout.addWidget(font_combo, 2)
            g_layout.addWidget(QLabel("크기:"))
            g_layout.addWidget(size_spin, 1)
            g_layout.addWidget(color_btn, 1)
            g_layout.addWidget(QLabel("Y위치:"))
            g_layout.addWidget(y_spin, 1)
            
            group.setLayout(g_layout)
            layout.addWidget(group)
            
            self.thumb_lines.append({
                'text': text_edit,
                'font': font_combo,
                'size': size_spin,
                'color_btn': color_btn,
                'y_pos': y_spin
            })
            
        # Preview & Action
        btn_layout = QHBoxLayout()
        btn_gen = QPushButton("🔄 미리보기/생성")
        btn_gen.clicked.connect(self.generate_thumbnail)
        btn_gen.setStyleSheet("height: 40px; background-color: #673AB7; color: white; font-weight: bold;")
        
        btn_save = QPushButton("💾 저장")
        btn_save.clicked.connect(self.save_thumbnail)
        btn_save.setStyleSheet("height: 40px; background-color: #28a745; color: white; font-weight: bold;")
        
        btn_layout.addWidget(btn_gen)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        
        # Preview Label
        self.thumb_preview_label = QLabel()
        self.thumb_preview_label.setAlignment(Qt.AlignCenter)
        self.thumb_preview_label.setStyleSheet("border: 2px dashed #555; background-color: #222;")
        self.thumb_preview_label.setMinimumHeight(400)
        self.thumb_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.thumb_preview_label)
        
        # Keep reference to current image
        self.current_thumb_image = None
        
        self.tab_thumbnail.setLayout(layout)

    def pick_color_btn(self, btn):
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            btn.current_color = hex_color
            # Contrast text color
            text_c = 'black' if color.lightness() > 128 else 'white'
            btn.setStyleSheet(f"background-color: {hex_color}; color: {text_c}; font-weight: bold; border: 1px solid #555;")

    def generate_thumbnail(self):
        # 1. Background
        bg_path = self.thumb_bg_path.text().strip()
        width, height = 1280, 720
        
        try:
            if bg_path and os.path.exists(bg_path):
                base_img = Image.open(bg_path).convert("RGBA")
                base_img = base_img.resize((width, height), Image.LANCZOS)
            else:
                base_img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
            
            # Apply Bottom Gradient if Checked
            if hasattr(self, 'chk_thumb_gradient') and self.chk_thumb_gradient.isChecked():
                # Gradient parameters
                grad_height = int(height * 0.65) # Bottom 65% height
                
                # Create alpha mask for gradient (Transparent -> Opaque)
                # Use PIL to draw gradient
                alpha_mask = Image.new('L', (1, grad_height), 0)
                for y in range(grad_height):
                    # Linear gradient: 0 to 255
                    alpha = int(255 * (y / grad_height))
                    alpha_mask.putpixel((0, y), alpha)
                
                # Resize to full width
                alpha_mask = alpha_mask.resize((width, grad_height))
                
                # Create black layer with this alpha
                black_layer = Image.new("RGBA", (width, grad_height), "black")
                black_layer.putalpha(alpha_mask)
                
                # Paste onto a full size transparent layer to composite correctly
                overlay = Image.new("RGBA", (width, height), (0,0,0,0))
                overlay.paste(black_layer, (0, height - grad_height))
                
                # Composite
                base_img = Image.alpha_composite(base_img, overlay)

            draw = ImageDraw.Draw(base_img)
            
            # 2. Draw Lines
            for item in self.thumb_lines:
                text = item['text'].text().strip()
                if not text: continue
                
                font_name = item['font'].currentText()
                font_size = item['size'].value()
                color_hex = item['color_btn'].current_color
                y_percent = item['y_pos'].value()
                
                # Load Font
                font = None
                if font_name in self.font_path_map:
                    try:
                        font = ImageFont.truetype(self.font_path_map[font_name], font_size)
                    except:
                        pass
                
                if font is None:
                    # 1순위 폴백: 맑은 고딕 (한글 깨짐 방지용)
                    try:
                        font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", font_size)
                    except:
                        # 2순위: Arial
                        try:
                            font = ImageFont.truetype("arial.ttf", font_size)
                        except:
                            font = ImageFont.load_default()
                
                # Calculate Position
                # Centered Horizontally, Y based on percentage
                try:
                    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
                    text_w = right - left
                    text_h = bottom - top
                except:
                    text_w, text_h = draw.textsize(text, font=font)
                
                x_pos = (width - text_w) / 2
                y_pos = (height * (y_percent / 100.0)) - (text_h / 2)
                
                # Outline
                stroke_width = max(1, int(font_size / 20))
                stroke_color = "black" if color_hex.lower() != "#000000" else "white"
                
                draw.text((x_pos, y_pos), text, font=font, fill=color_hex, stroke_width=stroke_width, stroke_fill=stroke_color)
                
            self.current_thumb_image = base_img
            
            # 3. Show Preview
            # Convert RGBA to QImage
            data = base_img.tobytes("raw", "RGBA")
            qim = QImage(data, width, height, QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qim)
            
            # Scale to fit label
            scaled_pixmap = pixmap.scaled(self.thumb_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_preview_label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"썸네일 생성 중 오류: {e}")
            traceback.print_exc()

    def save_thumbnail(self):
        if self.current_thumb_image is None:
            QMessageBox.warning(self, "경고", "먼저 썸네일을 생성해주세요.")
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "썸네일 저장", "", "PNG Files (*.png);;JPG Files (*.jpg)")
        if path:
            try:
                self.current_thumb_image.save(path)
                QMessageBox.information(self, "완료", f"저장되었습니다:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패: {e}")







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




class AudioTranscriberWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, target_files, mode, model_name, merge_mp3=False):
        super().__init__()
        self.target_files = target_files # List of absolute file paths
        self.mode = mode # 'convert', 'transcribe', 'all', 'compress'
        self.model_name = model_name # Acts as bitrate if mode is 'compress'
        self.merge_mp3 = merge_mp3

    def run(self):
        job_start_time = time.time()
        
        # Capture processing directory early (needed for merge, even if source files are deleted)
        target_dir = None
        if self.target_files:
            target_dir = os.path.dirname(self.target_files[0])

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
            
            # --- Audio (M4A/WAV) -> MP3 ---
            if self.mode in ["convert", "all"]:
                # Filter Audio files from the selected list
                audio_files = [f for f in self.target_files if f.lower().endswith(('.m4a', '.wav'))]

                if not audio_files:
                    self.log_signal.emit("⚠️ 선택된 파일 중 MP3로 변환할 파일(WAV/M4A)이 없습니다.")
                else:
                    self.log_signal.emit(f"🔄 Audio -> MP3 변환 시작 (총 {len(audio_files)}개)")
                    creation_flags = 0x08000000 if os.name == 'nt' else 0
                    
                    for in_path in audio_files:
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
                            # WAV 파일인 경우 변환 후 삭제
                            if in_path.lower().endswith('.wav'):
                                try:
                                    os.remove(in_path)
                                    self.log_signal.emit(f"   🗑️ 원본 삭제됨: {f_name}")
                                except Exception as del_err:
                                    self.log_signal.emit(f"   ⚠️ 삭제 실패: {del_err}")
                        except Exception as e:
                            self.log_signal.emit(f"   ❌ 변환 실패 ({f_name}): {e}")
            
            # --- Merge MP3s (New Feature) ---
            if self.mode == "convert" and self.merge_mp3:
                # Use the target_dir captured at start
                if target_dir and os.path.isdir(target_dir):
                    # Sleep briefly to ensure file system sync
                    time.sleep(1.0)
                    
                    mp3s = [f for f in os.listdir(target_dir) if f.lower().endswith('.mp3')]
                    
                    # Sort naturally (1, 2, ... 10)
                    # Extract numbers from filename for robust sorting
                    def natural_sort_key(s):
                        return [int(text) if text.isdigit() else text.lower()
                                for text in re.split('([0-9]+)', s)]
                    
                    mp3s.sort(key=natural_sort_key)
                    
                    if len(mp3s) > 1:
                        self.log_signal.emit(f"🔄 MP3 합치기 시작 ({len(mp3s)}개 파일)...")
                        
                        # Create file list for ffmpeg concat
                        list_path = os.path.join(target_dir, "file_list.txt")
                        output_mp3 = os.path.join(target_dir, f"merged_audio_{int(time.time())}.mp3")
                        
                        try:
                            with open(list_path, "w", encoding='utf-8') as f:
                                for mp3 in mp3s:
                                    if "merged_audio" not in mp3: # avoid including previously merged files
                                        f.write(f"file '{mp3}'\n")
                            
                            cmd_merge = [
                                ffmpeg_exe, "-y", "-f", "concat", "-safe", "0",
                                "-i", list_path, "-c", "copy", output_mp3
                            ]
                            
                            creation_flags = 0x08000000 if os.name == 'nt' else 0
                            subprocess.run(
                                cmd_merge, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True, creationflags=creation_flags
                            )
                            self.log_signal.emit(f"   ✅ 합치기 완료: {os.path.basename(output_mp3)}")
                            
                            # Clean up list file
                            if os.path.exists(list_path):
                                os.remove(list_path)
                                
                        except Exception as e:
                            self.log_signal.emit(f"   ❌ 합치기 실패: {e}")
                    else:
                        self.log_signal.emit("   ℹ️ 합칠 MP3 파일이 부족합니다 (2개 미만).")
                else:
                    self.log_signal.emit("   ⚠️ 폴더 경로를 찾을 수 없어 합치기를 건너뜁니다.")

            # --- MP3 Compression ---
            if self.mode == "compress":
                self.log_signal.emit(f"📉 MP3 용량 줄이기 시작 (총 {len(self.target_files)}개)")
                creation_flags = 0x08000000 if os.name == 'nt' else 0
                
                # bitrate selection from model_name parameter
                bitrate = self.model_name if "k" in str(self.model_name) else "64k"

                for in_path in self.target_files:
                    if not os.path.exists(in_path):
                        continue
                    if not in_path.lower().endswith(('.mp3', '.wav', '.m4a', '.mp4')):
                        continue
                        
                    in_dir = os.path.dirname(in_path)
                    base, ext = os.path.splitext(os.path.basename(in_path))
                    out_path = os.path.join(in_dir, f"{base}_compressed.mp3")
                    f_name = os.path.basename(in_path)
                    
                    self.log_signal.emit(f"   압축 중: {f_name} -> {bitrate} (Mono, 16kHz) ...")
                    
                    # Command to reduce size: lower bitrate, mono, and lower sample rate
                    # -ac 1 (mono) reduces size dramatically for stereo sources
                    # -ar 16000 is optimized for speech/Whisper
                    cmd = [
                        ffmpeg_exe, "-y", "-i", in_path,
                        "-c:a", "libmp3lame", "-b:a", bitrate, 
                        "-ac", "1", "-ar", "16000",
                        out_path
                    ]
                    try:
                        subprocess.run(
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, creationflags=creation_flags
                        )
                        self.log_signal.emit(f"   ✅ 압축 완료: {os.path.basename(out_path)}")
                    except Exception as e:
                        self.log_signal.emit(f"   ❌ 압축 실패 ({f_name}): {e}")

            # --- MP3 -> SRT ---
            if self.mode in ["transcribe", "all"]:
                mp3_files = []
                
                if self.mode == "all":
                    # In 'all' mode, we infer mp3 paths from the input m4a files
                    audio_files = [f for f in self.target_files if f.lower().endswith(('.m4a', '.wav'))]
                    for aud in audio_files:
                        base = os.path.splitext(aud)[0]
                        mp3_files.append(base + ".mp3")
                else:
                     # In 'transcribe' mode, use the selected mp3/mp4 files
                     mp3_files = [f for f in self.target_files if f.lower().endswith(('.mp3', '.mp4'))]
                
                # Filter out non-existent mp3s (e.g. if conversion failed)
                mp3_files = [f for f in mp3_files if os.path.exists(f)]

                if not mp3_files:
                    self.log_signal.emit("⚠️ MP3/MP4 파일이 없습니다 (변환이 실패했거나 선택되지 않음).")
                else:
                    self.log_signal.emit(f"📝 MP3/MP4 -> SRT 작업 시작 (총 {len(mp3_files)}개)")
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
    
    def __init__(self, target_dir, style, output_path, scenes_data=None):
        super().__init__()
        self.target_dir = target_dir
        self.style = style # Dictionary of style settings
        self.output_path = output_path
        self.scenes_data = scenes_data
        self.temp_sub_dir = os.path.join(self.target_dir, "temp_subs")

    def run(self):
        import shutil
        import time
        import re
        import random
        start_time = time.time()
        try:
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except:
                ffmpeg_exe = "ffmpeg"
            
            creation_flags = 0x08000000 if os.name == 'nt' else 0
                
            # 2. 파일 목록 및 SRT 로드
            files = os.listdir(self.target_dir)
            mp3_files = [f for f in files if f.lower().endswith('.mp3')]
            srt_files = [f for f in files if f.lower().endswith('.srt')]
            
            if not mp3_files or not srt_files:
                self.error.emit("MP3 또는 SRT 파일이 폴더에 없습니다.")
                return

            # 가장 적절한 쌍 선택 (첫 번째 mp3와 첫 번째 srt)
            mp3_path = os.path.join(self.target_dir, mp3_files[0])
            srt_path = os.path.join(self.target_dir, srt_files[0])
            base_name = os.path.splitext(mp3_files[0])[0]
            out_path = self.output_path

            self.log_signal.emit(f"🚀 작업 시작: {mp3_files[0]} + {srt_files[0]}")

            # 3. 오디오 길이 확인
            duration = get_audio_duration(ffmpeg_exe, mp3_path)
            if duration == 0:
                self.error.emit("오디오 길이를 측정할 수 없습니다.")
                return

            if self.scenes_data:
                segments = []
                for s in self.scenes_data:
                    segments.append({
                        'index': s['index'],
                        'start': s['start'],
                        'end': s['end'],
                        'text': s['text'],
                        'source': os.path.join(self.target_dir, s['bg_file']) if s['bg_file'] else None,
                        'overlay': os.path.join(self.target_dir, s['overlay_file']) if s['overlay_file'] else None,
                        'speed': s.get('speed', 1.0)
                    })
                self.log_signal.emit(f"📊 타임라인 데이터 로드 완료: {len(segments)}개 씬")
            else:
                # 4. SRT 파싱 (정규식 기반으로 개선하여 누락 방지)
                segments = parse_srt_robust(srt_path)
                self.log_signal.emit(f"📊 SRT 파싱 완료: {len(segments)}개 트랙 발견")

                # 5. 모든 세그먼트에 대해 배경 파일 매핑 (Hold 로직 강화)
                self.log_signal.emit("🔍 파일 매칭 및 배경 유지 로직 가동...")
                
                # 기본 배경 (검정 화면 생성)
                if not os.path.exists(self.temp_sub_dir): os.makedirs(self.temp_sub_dir, exist_ok=True)
                black_p = os.path.join(self.temp_sub_dir, "black_start.png")
                Image.new('RGB', (1920, 1080), (0,0,0)).save(black_p)
                
                last_found_file = black_p
                for seg in segments:
                    idx = seg['index']
                    match_found = None
                    # 파일명 시작이 "번호." 또는 "번호 " 또는 "번호_" 인 것 찾기
                    pattern = re.compile(rf"^{idx}[.\s_].*")
                    for f_name in files:
                        if pattern.match(f_name.lower()):
                            match_found = os.path.join(self.target_dir, f_name)
                            break
                    
                    if match_found:
                        seg['source'] = match_found
                        last_found_file = match_found
                    else:
                        seg['source'] = last_found_file # 이전 파일 유지 (Hold)
                    seg['overlay'] = None
                    seg['speed'] = 1.0

            if os.path.exists(self.temp_sub_dir):
                shutil.rmtree(self.temp_sub_dir, ignore_errors=True)
            os.makedirs(self.temp_sub_dir, exist_ok=True)

            # 6. 비디오 조각 생성 (영상 vs 이미지 분기 처리)
            unified_video_dir = os.path.join(self.temp_sub_dir, "chunks")
            if not os.path.exists(unified_video_dir): os.makedirs(unified_video_dir)
            
            # 체크포인트 추출 (설정이 바뀌는 시점만)
            checkpoints = []
            if segments:
                curr_state = None
                for seg in segments:
                    state = (seg['source'], seg['overlay'], seg['speed'])
                    if state != curr_state:
                        checkpoints.append({
                            'start': seg['start'], 
                            'source': seg['source'],
                            'overlay': seg['overlay'],
                            'speed': seg['speed']
                        })
                        curr_state = state
                # 첫 시작점 보정
                checkpoints[0]['start'] = 0.0

            # 조각 생성 루프 (병렬 처리 적용)
            from concurrent.futures import ThreadPoolExecutor
            ts_list = [None] * len(checkpoints)
            FPS_OUT = 30
            # [Optimization] CPU 환경에 맞춰 해상도 최적화 (2560 -> 2240)
            UW, UH = 2240, 1260 # 줌용 해상도
            VW, VH = 1920, 1080 # 최종 출력
            
            # GPU 가속은 사용하지 않음 (사용자 요청)
            use_nvenc = False

            def create_chunk(idx, cp):
                start_t = cp['start']
                end_t = checkpoints[idx+1]['start'] if idx < len(checkpoints)-1 else duration
                if end_t <= start_t: return None
                
                dur = end_t - start_t
                ts_path = os.path.join(unified_video_dir, f"chunk_{idx}.ts")
                src = cp['source']
                overlay_src = cp.get('overlay')
                speed = cp.get('speed', 1.0)
                is_vid = src.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv'))
                
                # 영상 속도 적용 (PTS 조절)
                setpts = f"setpts=PTS/{speed}" if is_vid and speed != 1.0 else "setpts=PTS"

                # 메인 필터 구성
                if is_vid:
                    # 영상 배경
                    vf_main = f"scale={VW}:{VH}:force_original_aspect_ratio=decrease,pad={VW}:{VH}:(ow-iw)/2:(oh-ih)/2,setsar=1,{setpts},format=yuv420p"
                else:
                    # 이미지 배경 (줌팬)
                    is_special_img = False
                    base_src = os.path.basename(src).lower()
                    if base_src.startswith("1.") or base_src == "black_start.png":
                        is_special_img = True
                    
                    do_fix = self.style.get('fix_first_img', True)
                    if is_special_img and do_fix:
                        z_expr, x_expr, y_expr = "1", "0", "0"
                    else:
                        z_speed, p_speed = 0.00015, 0.2
                        effect_idx = random.randint(0, 2)
                        if effect_idx == 0:
                            z_expr, x_expr, y_expr = f"zoom+{z_speed}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
                        elif effect_idx == 1:
                            z_expr, x_expr, y_expr = "1.1", f"min(on*{p_speed}, iw-iw/zoom)", "ih/2-(ih/zoom/2)"
                        else:
                            z_expr, x_expr, y_expr = "1.1", f"max((iw-iw/zoom)-(on*{p_speed}), 0)", "ih/2-(ih/zoom/2)"
                    
                    FPS_INTERNAL = 60
                    vf_main = (
                        f"scale={UW}:{UH}:force_original_aspect_ratio=increase,crop={UW}:{UH},format=yuv444p,"
                        f"zoompan=z='{z_expr}':x='trunc({x_expr})':y='trunc({y_expr})':d={int(dur*FPS_INTERNAL)}:s={UW}x{UH}:fps={FPS_INTERNAL},"
                        f"scale={VW}:{VH}:flags=lanczos,format=yuv420p,fps={FPS_OUT}"
                    )
                
                # 오버레이 (PiP) 처리
                cmd = [ffmpeg_exe, "-y", "-threads", "1"]
                if is_vid:
                    cmd.extend(["-stream_loop", "-1", "-i", src])
                else:
                    cmd.extend(["-loop", "1", "-i", src])

                if overlay_src and os.path.exists(overlay_src):
                    is_ov_vid = overlay_src.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv'))
                    if is_ov_vid:
                        cmd.extend(["-stream_loop", "-1", "-i", overlay_src])
                    else:
                        cmd.extend(["-loop", "1", "-i", overlay_src])
                    
                    # 오버레이 위치 및 크기 (가운데 PiP로 예시, 추후 필요시 조정)
                    ov_w, ov_h = int(VW * 0.4), int(VH * 0.4)
                    vf_final = f"[0:v]{vf_main}[bg];[1:v]scale={ov_w}:{ov_h}:force_original_aspect_ratio=decrease,pad={ov_w}:{ov_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[ov];[bg][ov]overlay=(W-w)/2:(H-h)/2"
                else:
                    vf_final = vf_main

                # 엔코더 선택 (CPU 전용)
                v_codec = "libx264"
                preset = "ultrafast"
                
                cmd.extend([
                    "-t", f"{dur:.3f}",
                    "-filter_complex", vf_final,
                    "-c:v", v_codec, "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(FPS_OUT),
                    "-an", ts_path
                ])
                
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, creationflags=creation_flags)
                return ts_path

            # 최대 코어 수 고려 병렬 실행
            max_w = min(os.cpu_count() or 4, 8)
            self.log_signal.emit(f"⚙️ 조각 병렬 생성 시작 (스케줄: {max_w}개)...")
            
            with ThreadPoolExecutor(max_workers=max_w) as exp:
                futures = [exp.submit(create_chunk, i, cp) for i, cp in enumerate(checkpoints)]
                for i, fut in enumerate(futures):
                    res_path = fut.result()
                    if res_path:
                        ts_list[i] = res_path
                        self.log_signal.emit(f"  ∟ 조각 {i+1}/{len(checkpoints)} 완료")
            
            ts_list = [t for t in ts_list if t is not None]

            # 7. 최종 합성 (비디오 조각 + 오디오 + 자막 필터)
            concat_list_p = os.path.join(self.temp_sub_dir, "concat.txt")
            with open(concat_list_p, "w", encoding='utf-8') as f:
                for ts in ts_list:
                    f.write(f"file '{ts.replace('\\', '/')}'\n")

            self.log_signal.emit("🎬 최종 인코딩 및 자막 필터 합성 중...")
            
            # 자막 필터 설정을 위한 윈도우 경로 및 스타일 처리
            safe_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")
            f_family = self.style.get('font_family', 'Malgun Gothic')
            f_size = self.style.get('font_size', 70)
            f_folder = self.style.get('font_folder', '').replace("\\", "/").replace(":", "\\:")
            
            # CSS 컬러(명칭/Hex) -> ASS 컬러(&HBBGGRR) 변환 함수
            def to_ass_color(c):
                if not c: return "&HFFFFFF"
                # 기본 색상 명칭 대응
                named_colors = {
                    'white': '#FFFFFF', 'black': '#000000', 'red': '#0000FF', 
                    'green': '#00FF00', 'blue': '#FF0000', 'yellow': '#00FFFF',
                    'Transparent': '#FFFFFF' # 투명은 기본 흰색으로 (ASS에서 별도 처리 가능하나 일단 기본값)
                }
                if c in named_colors: c = named_colors[c]
                
                if c.startswith('#'):
                    rgb = c.lstrip('#')
                    if len(rgb) == 6:
                        return f"&H{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"
                return "&HFFFFFF"

            p_color = to_ass_color(self.style.get('text_color', '#FFFFFF'))
            o_color = to_ass_color(self.style.get('outline_color', '#000000'))
            
            # FFmpeg subtitles 필터는 기본 스크립트 해상도가 288이므로 1080p 기준으로 스케일링 필요
            # UI에서 70은 1080p에서의 70px을 의미함.
            f_size_v = int(f_size * (288 / 1080))
            if f_size_v < 1: f_size_v = 1
            
            # 테두리 두께 및 여백도 스케일링
            # MarginV를 25에서 65로 변경 (자막 위치를 위로 올림)
            # 테두리 두께를 2 올림 (2 -> 4)
            outline_val = (4 if self.style.get('use_outline', True) else 0) * (288 / 1080)
            margin_v = 65 * (288 / 1080)

            # 자막 배경 및 스타일 설정
            use_bg = self.style.get('use_bg', False)
            bg_color_css = self.style.get('bg_color', 'Transparent')
            bg_opacity = self.style.get('bg_opacity', 200) # 기본 투명도
            
            # ASS 색상 형식: &HAABBGGRR (AA는 투명도, 00이 불투명, FF가 투명)
            ass_alpha = 255 - int(bg_opacity)
            if ass_alpha < 0: ass_alpha = 0
            if ass_alpha > 255: ass_alpha = 255
            
            b_color_base = to_ass_color(bg_color_css).replace("&H", "")
            b_color = f"&H{ass_alpha:02X}{b_color_base}"
            
            # BorderStyle: 1(테두리), 3(불투명 배경 박스)
            border_style = 3 if use_bg else 1
            
            force_style = (
                f"FontName={f_family},FontSize={f_size_v},"
                f"PrimaryColour={p_color},OutlineColour={o_color},"
                f"BackColour={b_color},BorderStyle={border_style},"
                f"Outline={outline_val:.1f},Shadow=0,Alignment=2,MarginV={margin_v:.1f},Bold=1"
            )
            
            # fontsdir 적용 (사용자 정의 폰트 폴더 인식)
            sub_filter = f"subtitles='{safe_srt_path}'"
            if f_folder:
                sub_filter += f":fontsdir='{f_folder}'"
            sub_filter += f":force_style='{force_style}'"

            # 최종 인코더 및 프리셋 설정 (CPU 전용 최적화)
            v_codec_final = "libx264"
            final_preset = "superfast" 
            
            # 8. BGM 및 최종 합성
            bgm_path = self.style.get('bgm_path')
            bgm_volume = self.style.get('bgm_volume', 0.1)
            
            cmd_final = [
                ffmpeg_exe, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_list_p,
                "-i", mp3_path
            ]
            
            filter_str = sub_filter # 기본 자막 필터
            
            if bgm_path and os.path.exists(bgm_path):
                cmd_final.extend(["-stream_loop", "-1", "-i", bgm_path])
                # 오디오 믹싱: [1:a]는 메인 음성, [2:a]는 BGM
                # amix: inputs=2, duration=first (메인 음성 길이에 맞춤)
                filter_str = f"[0:v]{sub_filter}[v_out];[2:a]volume={bgm_volume}[bgm];[1:a][bgm]amix=inputs=2:duration=first[a_out]"
                map_args = ["-map", "[v_out]", "-map", "[a_out]"]
            else:
                filter_str = f"[0:v]{sub_filter}[v_out]"
                map_args = ["-map", "[v_out]", "-map", "1:a"]

            cmd_final.extend([
                "-filter_complex", filter_str
            ])
            cmd_final.extend(map_args)
            cmd_final.extend([
                "-c:v", v_codec_final, "-preset", final_preset, "-crf", "30",
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                out_path
            ])
            
            subprocess.run(cmd_final, check=True, creationflags=creation_flags)

            elapsed = time.time() - start_time
            self.finished.emit(f"✅ 영상 제작 완료! (파일명: {os.path.basename(self.output_path)})", elapsed)

        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {str(e)}")
        finally:
            if os.path.exists(self.temp_sub_dir):
                try: shutil.rmtree(self.temp_sub_dir)
                except: pass

# --- 공용 유틸리티 함수 ---
def parse_time(t):
    t = t.replace(',', '.').replace(' ', '')
    p = t.split(':')
    if len(p) == 3:
        return float(p[0])*3600 + float(p[1])*60 + float(p[2])
    return 0.0

def get_audio_duration(exe, p):
    r = subprocess.run([exe, "-i", p], stderr=subprocess.PIPE, stdout=subprocess.PIPE, creationflags=0x08000000)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr.decode('utf-8', errors='ignore'))
    return float(m.group(1))*3600 + float(m.group(2))*60 + float(m.group(3)) if m else 0.0

def parse_srt_robust(path):
    import re
    segments = []
    try:
        with open(path, 'r', encoding='utf-8-sig') as f: content = f.read()
    except:
        with open(path, 'r', encoding='cp949', errors='ignore') as f: content = f.read()
    content = content.replace('\r\n', '\n').strip()
    # 사용자가 제공한 정밀 정규식 적용 (구조 누락 방지)
    pattern = re.compile(r"(\d+)\s+(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*(.*?)(?=\n\d+\s+\d{2}:\d{2}:\d{2}[.,]\d{3}|\Z)", re.DOTALL)
    
    matches = pattern.finditer(content)
    for m in matches:
        segments.append({
            'index': int(m.group(1)),
            'start': parse_time(m.group(2)),
            'end': parse_time(m.group(3)),
            'text': m.group(4).strip()
        })
    return sorted(segments, key=lambda x: x['start'])





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