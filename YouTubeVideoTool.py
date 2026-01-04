import sys
import requests
import subprocess
import os
import collections
import base64
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
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QRect, QRectF
from PyQt5.QtGui import (QPalette, QColor, QFont, QImage, QPainter, QPen, QBrush, QPixmap, QFontDatabase, QFontInfo, 
                         QPainterPath, QTextDocument, QAbstractTextDocumentLayout)
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

class GenSparkMultiTabWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str) 
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def copy_to_clipboard(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            # Fallback to pure python or just send_keys if failed (not ideal for korean)
            pass

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

            self.is_running = True
            while processed_count < total and self.is_running:
                for tab in tabs:
                    if not self.is_running: break
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
                
                time.sleep(1) # 루프 주기 단축 (반응성 향상)

            if not self.is_running:
                 self.log_signal.emit("🛑 작업이 중지되었습니다.")
                 
            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})" if self.is_running else "중지됨"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.is_running = False

    def check_image_once(self, driver, old_srcs):
        script = """
        try {
            var old_srcs = arguments[0];
            var imgs = Array.from(document.querySelectorAll('img'));
            
            // 제외 키워드
            var exclude = ['flaticon', 'logo', 'icon', 'svg', 'profile', 'avatar'];
            
            for (var i = 0; i < imgs.length; i++) {
                var img = imgs[i];
                var src = img.src;
                
                if (!src || src.startsWith('data:image/gif')) continue;
                if (img.width < 200 || img.height < 200) continue; 
                
                if (exclude.some(k => src.includes(k))) continue;

                if (!old_srcs.includes(src)) {
                    var canvas = document.createElement("canvas");
                    // 화면에 보이는 크기가 아닌 원본 해상도 사용
                    canvas.width = img.naturalWidth || img.width;
                    canvas.height = img.naturalHeight || img.height;
                    var ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL("image/png").replace(/^data:image\\/(png|jpg);base64,/, "");
                }
            }
            return null;
        } catch (e) {
            return null;
        }
        """
        try:
            return driver.execute_script(script, old_srcs)
        except:
            return None

class NanoBananaMultiTabWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str) 
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def copy_to_clipboard(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            pass

    def __init__(self, file_path, items, driver, custom_target_dir=None):
        super().__init__()
        self.file_path = file_path
        self.items = items
        self.driver = driver
        
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

            dumped = False

            self.is_running = True
            while processed_count < total and self.is_running:
                for tab in tabs:
                    if not self.is_running: break
                    self.driver.switch_to.window(tab)
                    
                    # 디버깅: 페이지 소스 저장 (최초 1회)
                    if not dumped:
                        try:
                            with open(r"d:\python\youtube\gemini_debug.html", "w", encoding="utf-8") as f:
                                f.write(self.driver.page_source)
                            self.log_signal.emit("🐛 디버깅용 페이지 소스가 저장되었습니다 (gemini_debug.html)")
                            dumped = True
                        except Exception as e:
                            print(f"Dump failed: {e}")
                    if not self.is_running: break
                    self.driver.switch_to.window(tab)
                    
                    if tab_status[tab] is None and item_idx < total:
                        current_item = self.items[item_idx]
                        num, prompt = current_item
                        self.log_signal.emit(f"▶ [탭 {tabs.index(tab)+1}] {num}번 생성 시작...")
                        
                        tab_old_srcs[tab] = self.driver.execute_script("return Array.from(document.querySelectorAll('img')).map(img => img.src);")
                        
                        # NanoBanana (Gemini) Input Handling
                        # Target rich-textarea editor
                        try:
                            # 1. Try finding the contenteditable div directly
                            input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.ql-editor, div[contenteditable='true']")))
                            input_box.click()
                            time.sleep(0.5)
                            
                            # Clear existing text (Ctrl+A -> Delete)
                            input_box.send_keys(Keys.CONTROL + "a")
                            input_box.send_keys(Keys.DELETE)
                            
                            # Send Prompt
                            # For rich text editors, sending keys usually works best.
                            # Splitting lines might help if it's finicky, but standard send_keys usually fine.
                            input_box.send_keys(prompt.strip())
                            time.sleep(1)
                            
                            # Send Enter
                            input_box.send_keys(Keys.ENTER)
                            
                        except Exception as e:
                            self.log_signal.emit(f"  ⚠️ 입력창 찾기 실패 (재시도 중): {e}")
                            # Fallback: JS injection (less reliable for rich text but worth a shot)
                            try:
                                js_script = """
                                var editor = document.querySelector('div.ql-editor');
                                if(editor) {
                                    editor.innerText = arguments[0];
                                    editor.dispatchEvent(new Event('input', { bubbles: true }));
                                    // Enter trigger might need specific key events
                                }
                                """
                                self.driver.execute_script(js_script, prompt.strip())
                                time.sleep(1)
                                input_box.send_keys(Keys.ENTER) 
                            except:
                                pass

                        
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
                        
                        elif time.time() - tab_status[tab]["start_time"] > 220:
                            self.log_signal.emit(f"  ❌ [탭 {tabs.index(tab)+1}] {target_num}번 타임아웃")
                            failed_items.append(tab_status[tab]["item"])
                            tab_status[tab] = None
                            processed_count += 1
                
                time.sleep(1)

            if not self.is_running:
                 self.log_signal.emit("🛑 작업이 중지되었습니다.")
                 
            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})" if self.is_running else "중지됨"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.is_running = False

    def check_image_once(self, driver, old_srcs):
        # Initialize failure tracking
        if not hasattr(self, 'failed_srcs'):
            self.failed_srcs = set()

        try:
            images = driver.find_elements(By.TAG_NAME, 'img')
            
            exclude = ['icon', 'svg', 'profile', 'avatar', 'btn', 'button', 'logo', 'gstatic.com', 'googleusercontent.com/gadgets']

            # Search in reverse (newest first)
            for img in reversed(images):
                try:
                    src = img.get_attribute('src')
                    if not src: continue
                    
                    if src in old_srcs or src in self.failed_srcs:
                        continue
                        
                    if any(k in src for k in exclude):
                        continue

                    # Scroll thumbnail into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
                    time.sleep(0.5) 

                    # 1. Thumbnail Size Check
                    size = img.size
                    w, h = size['width'], size['height']
                    
                    if w < 200 or h < 200:
                        continue
                        
                    # aspect ratio check
                    ratio = w / h if h > 0 else 0
                    if ratio > 3.0 or ratio < 0.3:
                        continue

                    # ** Try to open Lightbox (High-Res) **
                    try:
                        driver.execute_script("arguments[0].click();", img)
                        
                        best_img = None
                        max_area = 0
                        
                        # Polling for high-res load (up to 10 seconds)
                        for _ in range(10):
                            time.sleep(1.0)
                            
                            current_imgs = driver.find_elements(By.TAG_NAME, 'img')
                            best_img_candidate = None
                            max_area_candidate = 0
                            
                            for m_img in current_imgs:
                                try:
                                    mw = int(m_img.get_attribute('naturalWidth') or 0)
                                    mh = int(m_img.get_attribute('naturalHeight') or 0)
                                    
                                    if mw > 600 and (mw * mh > max_area_candidate):
                                        max_area_candidate = mw * mh
                                        best_img_candidate = m_img
                                except:
                                    continue
                            
                            
                            if best_img_candidate:
                                best_img = best_img_candidate
                                max_area = max_area_candidate
                                if best_img.is_displayed():
                                    break
                                else:
                                    best_img = None
                        
                        result_data = None
                        
                        if best_img:
                            src = best_img.get_attribute('src')
                            
                            # 1. Python Requests로 직접 다운로드 (가장 강력함 - 원본 파일 그대로 저장)
                            if not result_data:
                                try:
                                    session = requests.Session()
                                    # Selenium 쿠키 복사
                                    cookies = driver.get_cookies()
                                    for cookie in cookies:
                                        session.cookies.set(cookie['name'], cookie['value'])
                                    
                                    headers = {
                                        "User-Agent": driver.execute_script("return navigator.userAgent;")
                                    }
                                    
                                    resp = session.get(src, headers=headers, timeout=15)
                                    if resp.status_code == 200:
                                        result_data = base64.b64encode(resp.content).decode('utf-8')
                                        self.log_signal.emit("  📸 Requests로 원본 다운로드 성공")
                                except Exception as e:
                                    # self.log_signal.emit(f"  ⚠️ Requests 실패: {e}")
                                    pass

                            # 2. Fetch API (JS) 백업
                            if not result_data:
                                try:
                                    script = """
                                    var callback = arguments[arguments.length - 1];
                                    var img = arguments[0];
                                    var src = img.src;
                                    
                                    fetch(src)
                                        .then(response => response.blob())
                                        .then(blob => {
                                            var reader = new FileReader();
                                            reader.onloadend = function() {
                                                callback(reader.result.split(',')[1]);
                                            }
                                            reader.readAsDataURL(blob);
                                        })
                                        .catch(err => {
                                            callback(null);
                                        });
                                    """
                                    result_data = driver.execute_async_script(script, best_img)
                                    if result_data:
                                        self.log_signal.emit("  📸 Fetch API로 원본 다운로드 성공")
                                except:
                                    pass
                            
                            # 3. 새 탭 열기 백업
                            if not result_data:
                                try:
                                    current_handle = driver.current_window_handle
                                    driver.execute_script("window.open(arguments[0], '_blank');", src)
                                    time.sleep(2.0)
                                    driver.switch_to.window(driver.window_handles[-1])
                                    full_img = driver.find_element(By.TAG_NAME, 'img')
                                    result_data = full_img.screenshot_as_base64
                                    driver.close()
                                    driver.switch_to.window(current_handle)
                                    self.log_signal.emit("  📸 새 탭 열기로 캡처 성공")
                                except:
                                    try:
                                        if len(driver.window_handles) > 2: driver.close()
                                        driver.switch_to.window(current_handle)
                                    except: pass
                        
                        # 4. 고해상도 실패 시 썸네일이라도 저장 (Fallback)
                        if not result_data:
                            self.log_signal.emit(f"  ⚠️ 고해상도 실패 -> 썸네일 안전 캡처 시도")
                            # 썸네일이 화면 밖으로 나가지 않게 스타일 강제 조정
                            try:
                                driver.execute_script("""
                                    arguments[0].style.position = 'fixed';
                                    arguments[0].style.top = '50%';
                                    arguments[0].style.left = '50%';
                                    arguments[0].style.transform = 'translate(-50%, -50%)';
                                    arguments[0].style.maxWidth = '90vw';
                                    arguments[0].style.maxHeight = '90vh';
                                    arguments[0].style.objectFit = 'contain';
                                    arguments[0].style.zIndex = '99999';
                                    arguments[0].style.backgroundColor = 'black';
                                """, img)
                                time.sleep(0.5)
                                result_data = img.screenshot_as_base64
                            except:
                                result_data = img.screenshot_as_base64 # 진짜 최후의 수단
                        
                        # Close Lightbox (ESC)
                        try:
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        except:
                            pass
                        time.sleep(0.5)
                        
                        if result_data:
                            return result_data
                        else:
                            self.failed_srcs.add(src)
                            
                    except Exception:
                        self.failed_srcs.add(src)
                        pass
                    
                except Exception:
                    continue
                    
            return None
            
        except Exception:
            return None


class ImageFXMultiTabWorker(GenSparkMultiTabWorker):
    def run(self):
        start_timestamp = time.time()
        try:
            if len(self.driver.window_handles) < 1:
                self.error.emit("❌ 오류: 브라우저 탭이 없습니다.")
                return

            tabs = self.driver.window_handles[:2] # 최대 2개 탭 활용
            wait = WebDriverWait(self.driver, 20)

            total = len(self.items)
            tab_status = {tab: None for tab in tabs}
            tab_old_srcs = {tab: [] for tab in tabs}
            
            processed_count = 0
            item_idx = 0
            failed_items = []

            self.is_running = True
            while processed_count < total and self.is_running:
                for tab in tabs:
                    if not self.is_running: break
                    self.driver.switch_to.window(tab)
                    
                    if tab_status[tab] is None and item_idx < total:
                        current_item = self.items[item_idx]
                        num, prompt = current_item
                        self.log_signal.emit(f"▶ [탭 {tabs.index(tab)+1}] {num}번 생성 시작 (ImageFX)...")
                        
                        tab_old_srcs[tab] = self.driver.execute_script("return Array.from(document.querySelectorAll('img')).map(img => img.src);")
                        
                        # ImageFX 입력창 찾기 (Genspark와 비슷하게 textarea 시도)
                        # ImageFX 입력창 찾기 및 초기화
                        # ImageFX 입력창 찾기 및 초기화 (최종: ActionChains + Clipboard)
                        input_box = None
                        try:
                            # 1. JS로 Shadow DOM 깊숙한 곳의 textarea 찾기
                            script_find_input = """
                            function findInput(root) {
                                if (!root) return null;
                                // 텍스트 영역 우선 탐색
                                var el = root.querySelector('textarea, [contenteditable="true"], input[type="text"]');
                                if (el) return el;
                                // Shadow Root 탐색
                                var walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                                while(walker.nextNode()) {
                                    if (walker.currentNode.shadowRoot) {
                                        var res = findInput(walker.currentNode.shadowRoot);
                                        if (res) return res;
                                    }
                                }
                                return null;
                            }
                            return findInput(document);
                            """
                            input_box = self.driver.execute_script(script_find_input)
                            
                            # 못 찾았으면 body부터 시작
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(self.driver)
                            
                            if input_box:
                                # 찾았으면 해당 요소로 이동 후 클릭
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_box)
                                    time.sleep(0.5)
                                    actions.move_to_element(input_box).click().perform()
                                except:
                                    self.driver.execute_script("arguments[0].click();", input_box)
                            else:
                                # 못 찾았으면 화면 중앙 클릭 후 탭 키 연타 시도
                                self.log_signal.emit("⚠️ 입력창 자동 감지 실패. TAB 키 탐색 시도...")
                                body = self.driver.find_element(By.TAG_NAME, 'body')
                                actions.move_to_element(body).click().perform()
                                time.sleep(0.2)
                                # 탭 키 5번 정도 눌러보며 active element 확인 (생략하고 그냥 바로 붙여넣기 시도할 수도 있음)
                                # 일단 탭 몇 번 누르고 붙여넣기 시도
                                actions.send_keys(Keys.TAB * 3).perform() 

                            time.sleep(0.5)
                            
                        except Exception as e:
                            self.log_signal.emit(f"⚠️ 초기화 오류 재시도... ({e})")
                            continue
                        
                        # 프롬프트 입력 (무조건 클립보드 붙여넣기 - 가장 확실)
                        p_text = prompt.strip()
                        
                        try:
                            import pyperclip
                            pyperclip.copy(p_text)
                            
                            # ActionChains로 Ctrl+A -> Del -> Ctrl+V 수행
                            # input_box가 있으면 거기로, 없으면 현재 포커스된 곳에
                            actions = ActionChains(self.driver)
                            
                            if input_box:
                                actions.move_to_element(input_box)
                                actions.click()
                            
                            # 기존 내용 지우기 (Ctrl+A, Del)
                            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).pause(0.1).send_keys(Keys.DELETE).pause(0.2)
                            
                            # 붙여넣기 (Ctrl+V)
                            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).pause(0.5)
                            actions.perform()
                            
                        except Exception as e:
                            self.log_signal.emit(f"⚠️ 입력 실패: {e}")
                            # 최후의 수단: JS 값 주입
                            if input_box:
                                self.driver.execute_script("arguments[0].innerText = arguments[1];", input_box, p_text)

                        time.sleep(1)
                        
                        # 엔터 입력 (생성 시작)
                        ActionChains(self.driver).send_keys(Keys.RETURN).perform()
                        time.sleep(1)
                        
                        # 명시적으로 '만들기' 버튼 찾아서 클릭
                        try:
                            script_submit = """
                            var buttons = Array.from(document.querySelectorAll('button'));
                            var target = buttons.find(b => {
                                var txt = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
                                return txt.includes('create') || txt.includes('generate') || txt.includes('만들기') || txt.includes('run');
                            });
                            
                            if (!target) {
                                // 아이콘 fallback
                                var icons = document.querySelectorAll('.material-symbols-outlined, .material-icons, svg');
                                for(var icon of icons) {
                                    var itxt = (icon.innerText || '').toLowerCase();
                                    if(itxt.includes('send') || itxt.includes('arrow_up') || itxt.includes('spark')) {
                                        target = icon.closest('button');
                                        break;
                                    }
                                }
                            }

                            if (target) {
                                target.click();
                                return true;
                            }
                            return false;
                            """
                            driver_res = self.driver.execute_script(script_submit)
                            
                            if not driver_res:
                                # 엔터 한번 더
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        except:
                            pass
                        
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
                        
                        elif time.time() - tab_status[tab]["start_time"] > 250: # ImageFX는 조금 더 느릴 수 있음
                            self.log_signal.emit(f"  ❌ [탭 {tabs.index(tab)+1}] {target_num}번 타임아웃")
                            failed_items.append(tab_status[tab]["item"])
                            tab_status[tab] = None
                            processed_count += 1
                
                time.sleep(1)

            if not self.is_running:
                 self.log_signal.emit("🛑 ImageFX 작업이 중지되었습니다.")
                 
            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})" if self.is_running else "중지됨"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))

class VideoMergerWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, image_dir, audio_dir, output_dir, subtitles=None, style=None, volume=1.0, trim_end=0.0, use_random_effects=False):
        super().__init__()
        self.image_dir = image_dir
        self.audio_dir = audio_dir
        self.output_dir = output_dir
        self.subtitles = subtitles
        self.style = style
        self.volume = volume
        self.trim_end = trim_end
        self.use_random_effects = use_random_effects
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
                
                if not img_path:
                    self.log_signal.emit(f"⚠️ 이미지 없음 스킵: {base_name} (오디오 기준 처리 중)")
                    continue
                
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
            max_workers = min(3, multiprocessing.cpu_count()) # 시스템 부담을 고려해 최대 3개로 제한
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
                audio_clip = mpe.AudioFileClip(audio_path)
                original_duration = audio_clip.duration
                audio_clip.close()

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

            if os.path.exists(meta_path):
                sub_timing_list = self.get_timing_from_metadata(meta_path, sub_list)
                if sub_timing_list:
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
            # [Fix] 자막은 최종 영상 해상도(1920x1080) 기준으로 생성해야 오버레이 좌표가 맞음
            TARGET_W, TARGET_H = 1920, 1080
            w, h = TARGET_W, TARGET_H
            # img = Image.open(img_path)
            # w, h = img.size
            # if w % 2 != 0: w -= 1
            # if h % 2 != 0: h -= 1
            
            # 자막 PNG 생성
            if sub_timing_list:
                temp_dir = os.path.join(os.path.dirname(output_path), "temp_subs")
                os.makedirs(temp_dir, exist_ok=True)
                
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

            # 4. FFmpeg 명령어 구성
            command = [ffmpeg_exe]
            
            # [Input 0] 배경 이미지 (Loop)
            command.extend(["-loop", "1", "-t", f"{final_duration:.6f}", "-i", img_path])
            
            # [Input 1] 오디오
            command.extend(["-i", audio_path])
            
            # [Input 2~N] 자막 PNG들
            for s_path, _, _ in subtitle_inputs:
                command.extend(["-i", s_path])
                
            filter_complex = ""
            
            # ========== Video Filter ==========
            # ========== Video Filter ==========
            # 전처리: Image Input [0:v] -> Scale/Padded to 1920x1080 (or 1280x720)
            # 사용자 요청에 따라 "유튜브 영상 제작 해상도" -> FHD (1920x1080) 권장
            # TARGET_W, TARGET_H = 1920, 1080 (Moved up)
            FPS = 30
            
            # 1. Base Image Processing (Scale & Pad)
            # 원본 이미지를 타겟 해상도 비율에 맞게 조정 (Fit)
            
            # Effect Config 확인
            # 1. Task 별 개별 설정 (랜덤 효과 등) 우선
            # 2. 클래스 속성 (Single Video 등) 차선
            effect_config = task_effect_config if task_effect_config else getattr(self, 'effect_config', None)
            effect_type = effect_config.get('type', 0) if effect_config else 0
            
            # Debugging Effect Config
            if effect_config:
                self.log_signal.emit(f"   [Debug] Effect Type: {effect_type}")
                self.log_signal.emit(f"   [Debug] Config: {effect_config}")
            else:
                pass # self.log_signal.emit("   [Debug] No effect config found.")
            
            zoom_expr = ""
            # Zoom/Pan Logic (Java Reference Style)
            # zoompan filter needs input to be sufficiently large or handled carefully.
            # Java: scale=3840:2160 -> zoompan -> scale=1280:720
            # We will use explicit logic:
            
            # A) 이미지 [0:v]를 고화질로 뻥튀기 (Zoom 대비, Lanczos)
            #    최대 줌(예: 1.5배) 고려하여 넉넉하게 1.5배 or 4K로 업스케일
            #    [Fix] fps=30 명시하여 zoompan의 d=1 설정과 프레임 수 동기화 (기존 25fps -> 30fps 불일치로 시간 단축 문제 해결)
            filter_complex += f"[0:v]scale=3840:2160:flags=lanczos,setsar=1:1,fps={FPS}[v_high];"
            
            # B) Zoom/Pan Expression
            # Default (No Effect): z=1
            start_scale = effect_config.get('start_scale', 1.0) if effect_config else 1.0
            end_scale = effect_config.get('end_scale', 1.0) if effect_config else 1.0
            
            # duration (total frames)
            total_frames = int(final_duration * FPS)
            if total_frames <= 0: total_frames = 1
            
            if effect_type == 1: # Zoom (Unified)
                # Linear Interpolation: start + (end-start) * on/duration
                # [Fix] total_frames-1 로 나누어 마지막 프레임에서 정확히 end_scale 도달
                denom = total_frames - 1 if total_frames > 1 else 1
                z_expr = f"{start_scale}+({end_scale}-{start_scale})*on/{denom}"
                x_expr = "iw/2-(iw/2/zoom)"
                y_expr = "ih/2-(ih/2/zoom)"

            elif effect_type == 2: # Pan Left -> Right
                # Camera moves Left to Right -> Viewport moves Right to Left relative to image?
                # Usually "Pan Left to Right" means we see the left side first, then pan to the right side.
                # Left Side (x=0) -> Right Side (x=max)
                # [Correction] User says it's reversed. So current implementation (0->max) is what they think is "Right -> Left"?
                # Let's SWAP them.
                
                # New Logic for Type 2 (Left->Right label):
                # Start: x=max (Right side of image) -> End: x=0 (Left side of image)?
                # Wait, "Pan Left to Right" typically means "Move camera to right".
                # If camera moves right, the image frame moves left.
                # Let's simply SWAP the formulas as requested.
                
                pan_z = max(start_scale, 1.05)
                p_speed = effect_config.get('pan_speed', 1.0)
                z_expr = f"{pan_z}"
                
                # Swapped to (max -> 0)
                denom = total_frames - 1 if total_frames > 1 else 1
                progress_expr = f"(on*{p_speed}/{denom})"
                x_expr = f"(iw-iw/zoom)*(1-min(1,{progress_expr}))"
                y_expr = "ih/2-(ih/2/zoom)"
                
            elif effect_type == 3: # Pan Right -> Left
                # Swapped to (0 -> max)
                pan_z = max(start_scale, 1.05)
                p_speed = effect_config.get('pan_speed', 1.0)
                z_expr = f"{pan_z}"

                denom = total_frames - 1 if total_frames > 1 else 1
                progress_expr = f"(on*{p_speed}/{denom})"
                x_expr = f"(iw-iw/zoom)*min(1,{progress_expr})"
                y_expr = "ih/2-(ih/2/zoom)"
            else:
                z_expr = "1"
                x_expr = "0"
                y_expr = "0"
                
            # C) Apply Zoompan
            # [Fix] zoompan은 기본적으로 입력 프레임 하나당 1프레임을 출력하려 함.
            # 하지만 우리는 이미지를 loop쳐서 영상 스트림으로 만들었음 (-loop 1 -t duration ...)
            # 따라서 입력 스트림은 이미 total_frames 만큼의 길이를 가짐.
            # 이 경우 d=1 (input duration 1 frame -> output 1 frame)로 설정하면 1:1 매핑되어
            # on (output frame number)이 0부터 total_frames까지 증가하며 애니메이션이 적용됨.
            
            # 단, 만약 입력이 단일 이미지(1프레임)였다면 d=total_frames 가 되어야 함.
            # 현재 코드는 [0:v]가 -loop 1 로 들어오므로 비디오 스트림임. -> d=1 이 맞음.
            
            # [Check] z_expr에서 'on' 변수가 제대로 증가하는지 확인 필요.
            # zoompan 필터에서 on은 'current input frame'이 아니라 'current output frame of the zoompan instance'임.
            # 입력이 동영상 스트림일 때 d=1이면 on도 매 프레임 증가함.
            
            # 혹시 모르니 s=WxH를 명시하고, fps도 명시.
            filter_complex += (f"[v_high]zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
                               f"d=1:s=3840x2160:fps={FPS}[v_zoomed];")
            
            # D) Downscale to Target (FHD) & Pad
            filter_complex += (f"[v_zoomed]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                               f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1:1[v_bg];")
            
            # ========== Subtitle Filters ==========
            last_v_label = "[v_bg]"
            
            # Apply overlays
            # Input index for subs starts at 2
            for i, (_, start_t, end_t) in enumerate(subtitle_inputs):
                sub_idx = i + 2
                next_v_label = f"[v_sub{i}]"
                # enable='between(t, start, end)' -> Inclusive both sides -> Possible overlap flash
                # Use 'gte(t,start)*lt(t,end)' for exclusive end -> Seamless transition
                
                # Check if this is the last one or separate to ensure coverage
                # gte(t, S) * lt(t, E)
                filter_complex += f"{last_v_label}[{sub_idx}:v]overlay=enable='gte(t,{start_t:.3f})*lt(t,{end_t:.3f})'[v_sub{i}];"
                last_v_label = next_v_label
            
            final_v_label = last_v_label
            
            # ========== Audio Filter ==========
            # Volume + Trim + Resample(48k) + Fadeout
            # [1:a] -> ... -> [a_out]
            # atrim: duration 제한
            
            fade_duration = 0.05
            fade_start = max(0, final_duration - fade_duration)
            
            # vol filter -> aresample -> afade
            # vol: volume=1.5
            vol_val = self.volume
            
            filter_complex += (f"[1:a]volume={vol_val},"
                               f"atrim=duration={final_duration},"
                               f"aresample=48000:async=1,"
                               f"afade=t=out:st={fade_start}:d={fade_duration}[a_out]")
            
            # ========== Final Assembly ==========
            command.extend(["-filter_complex", filter_complex])
            command.extend(["-map", final_v_label, "-map", "[a_out]"])
            
            # Encoding Options
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            command.extend(["-y", output_path])
            
            # log
            # self.log_signal.emit(f"   Command: {' '.join(command)}")
            print(f"[Debug] Filter Complex: {filter_complex}")
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
                out, err = process.communicate(timeout=final_duration*5 + 60) # 타임아웃 넉넉히
                if process.returncode != 0:
                    raise Exception(f"FFmpeg Error: {err}")
            except subprocess.TimeoutExpired:
                process.kill()
                raise Exception("FFmpeg Timeout")

            # Cleanup Temp Files
            for tmp in temp_files:
                try: os.remove(tmp)
                except: pass
            
            # temp_subs 폴더 삭제
            try:
                temp_subs_dir = os.path.join(os.path.dirname(output_path), "temp_subs")
                if os.path.exists(temp_subs_dir):
                    os.rmdir(temp_subs_dir)
            except:
                pass
            
            return True

        except Exception as e:
            print(f"Error processing {base_name}: {e}")
            import traceback
            traceback.print_exc()
            # Cleanup on error
            for tmp in temp_files:
                try: os.remove(tmp)
                except: pass
            return False

    def get_timing_from_metadata(self, meta_path, sub_list=None):
        """JSON 메타데이터를 사용하여 텍스트 세그먼트들과 싱크 매칭
        sub_list가 없으면 JSON 내의 sub_segments 정보를 사용함.
        """
        import json
        try:
            if not os.path.exists(meta_path):
                return []
                
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            chars = data["characters"]
            starts = data["character_start_times_seconds"]
            ends = data["character_end_times_seconds"]
            
            # sub_list가 전달되지 않았으면 JSON에 저장된 sub_segments 사용
            if sub_list is None:
                sub_list = data.get("sub_segments", [])
                
            if not sub_list:
                return []

            results = []
            current_char_idx = 0
            
            for item in sub_list:
                # item can be a string (old format) or dict (new format)
                if isinstance(item, dict):
                    original_text = item.get("original", "")
                    tts_text = item.get("tts", "")
                else:
                    original_text = item
                    tts_text = item

                # [Robust Match] 공백 및 특수문자 제거 후 매칭
                # (ElevenLabs가 마침표를 생략하거나 다르게 줄 수 있음)
                text_clean = re.sub(r'[^\w]', '', tts_text)
                if not text_clean: continue
                
                seg_start_time = None
                seg_end_time = None
                
                temp_match = ""
                match_start_idx = -1
                
                search_idx = current_char_idx
                while search_idx < len(chars):
                    # 공백/특수문자 제외 문자 매칭
                    c_char = chars[search_idx]
                    c_clean = re.sub(r'[^\w]', '', c_char)
                    
                    if c_clean:
                        if match_start_idx == -1: match_start_idx = search_idx
                        temp_match += chars[search_idx]
                    
                    # 현재 문장이 매칭되었는지 확인
                    if text_clean in temp_match:
                        seg_start_time = starts[match_start_idx]
                        
                        # [Safety Fix] end_times 배열이 characters 보다 짧은 경우 방어
                        if search_idx < len(ends):
                            seg_end_time = ends[search_idx]
                        else:
                            # 끝 시간이 없으면 시작 시간과 동일하게 처리하거나 임의값 부여
                            # 여기서는 안전하게 마지막 유효 시간 또는 시작 시간 사용
                            seg_end_time = starts[search_idx] if search_idx < len(starts) else seg_start_time

                        current_char_idx = search_idx + 1 # 다음 문장은 여기서부터 검색
                        break
                    search_idx += 1
                
                if seg_start_time is not None:
                    # 결과에는 '원본' 텍스트를 담아 리턴
                    results.append((seg_start_time, seg_end_time, original_text))
            
            return results
        except Exception as e:
            print(f"매칭 오류 ({meta_path}): {e}")
            return []

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
        font_family = self.style['font_family']
        base_font_size = self.style['font_size']
        
        # 해상도 반응형 폰트 크기 계산 (기준: 최소 변의 길이 1024px)
        # 세로 영상(Portrait)과 가로 영상(Landscape) 모두에서 일관된 텍스트 크기를 유지하기 위해 width/height 중 작은 값을 기준으로 함
        min_dim = min(width, height)
        scale_factor = min_dim / 1024.0
        
        # 글자 크기가 과도하게 커지는 것을 방지 (User Feedback: Video Composite와 Dubbing 간 차이 발생 이유 추정)
        # 보수적인 스케일링 적용 
        
        scaled_font_size = int(base_font_size * scale_factor)
        
        font = QFont(font_family)
        font.setPixelSize(scaled_font_size)
        
        if not any(kw in font_family.lower() for kw in ['bold', 'heavy', 'black', 'eb', 'b']):
            font.setBold(True)
        else:
            font.setBold(False)
            
        painter.setFont(font)
        
        
        # 로그 출력 (디버깅용)
        try:
            print(f"[TextGen] Res: {width}x{height}, Scale: {scale_factor:.2f}, Font: {base_font_size} -> {scaled_font_size}px")
        except: pass
        
        # 텍스트 크기 계산
        # 좌우 여백도 스케일링
        margin_lr = int(40 * scale_factor)
        max_rect = QRect(margin_lr, 0, width - (margin_lr * 2), height) 
        text_rect = painter.boundingRect(max_rect, Qt.AlignCenter | Qt.TextWordWrap, text)
        
        # 1. 전체 위치 하단으로 더 내림 (7% -> 5% 여백)
        margin_bottom = int(height * 0.05)
        
        
        # 2. 배경 박스 크기 및 위치 결정 (User Feedback: 상하 줄이고 좌우 넉넉히, 둥근 모서리)
        padding_h = int(40 * scale_factor) # 좌우 패딩 넉넉히
        padding_v = int(12 * scale_factor) # 상하 패딩 축소 (30 -> 12)
        
        bg_rect = text_rect.adjusted(-padding_h, -padding_v, padding_h, padding_v)
        
        # 배경 박스가 화면 아래쪽 중앙에 위치하도록 조정
        # 텍스트 박스의 높이
        box_h = bg_rect.height()
        # 바닥에서 margin_bottom 만큼 띄운 위치
        target_bottom = height - margin_bottom
        target_top = target_bottom - box_h
        
        # 이동량 계산 (현재 bg_rect.top()에서 target_top으로)
        dy = target_top - bg_rect.top()
        bg_rect.translate(0, dy)
        text_rect.translate(0, dy)

        # 1. 배경박스 (체크박스가 켜져 있을 때만)
        if self.style.get('use_bg', True) and self.style['bg_color'] != "Transparent":
            # 투명도 적용
            color = QColor(self.style['bg_color'])
            opacity = self.style.get('bg_opacity', 255)
            color.setAlpha(opacity)
            
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            # 둥근 모서리 적용 (Rounded Rect) - 반지름 15 정도
            radius = int(15 * scale_factor)
            painter.drawRoundedRect(bg_rect, radius, radius)

        # 텍스트 그리기 위치 (6px 내림 보정)
        text_draw_area = bg_rect.translated(0, 6)

        # 텍스트 그리기 위치 (센터 정렬을 위해 rect 조정 불필요, text_rect 사용)
        # 하지만 기존 로직에서 bg_rect 기준 정렬을 했으므로 text_rect 위치를 그대로 사용하면 됨
        
        # 3. 텍스트 (QPainterPath를 이용한 고품질 외곽선 + 채우기)
        path = QPainterPath()
        
        # QPainterPath에 텍스트 추가
        # drawText는 rect 안에 알아서 정렬해서 그리지만, addText는 기준점(baseline)이 필요함.
        # 따라서 drawText와 동일한 배치를 위해 painter의 레이아웃 로직을 흉내내거나, 
        # 단순히 drawTextUnformatted가 아닌 정렬 기능을 써야 하는데 path에는 그런게 없음.
        # 가장 쉬운 방법: QPainterPath.addText는 한 줄 씩 좌표를 잡아야 해서 복잡함.
        # 대안: QPainter.strokePath 사용 불가 (path가 없으면).
        
        # 해결책: 텍스트 레이아웃을 위해 stroke용 path를 생성하는 쉬운 방법 -> QPainterPath.addText 대신
        # 단순히 텍스트를 그리는 위치를 정확히 잡아서 path로 변환해야 함.
        # 하지만 word-wrap이 포함되어 있어서 직접 구현은 까다로움.
        
        # -> Qt의 그리기 순서 변경:
        # 1. Stroke (외곽선)
        # 2. Fill (채우기)
        # Stroke를 하려면 Path가 필요한데, Word Wrapping된 텍스트의 Path를 얻기는 쉽지 않음.
        
        # 차선책: QPainter.drawText로 Stroke 효과를 내는 StrokePath 방식 말고,
        # 그냥 겹쳐 그리기를 하되, loop 방식(블러) 대신 8방향+4방향 (총 12~16회) 정도만 하거나
        # ★ 정석: QTextLayout 사용.
        
        # 이번에는 빠르고 확실한 개선을 위해 "outline layer"를 별도로 그리지 않고
        # Path를 생성해서 Stroking 하는 방식을 시도.
        # Word Wrapping을 지원하는 drawText의 Path 버전이 없으므로,
        # 간단히 text_rect 안에서 줄바꿈 처리를 직접 하거나... 너무 복잡.
        
        # 다시 쉬운 길: "QPainterPath"를 쓰되, 폰트 생성시 setStyleStrategy로 아웃라인? 아님.
        
        # 가장 현실적인 "깔끔한 아웃라인" 방법:
        # path.addText는 줄바꿈을 안해줌.
        # 텍스트가 길지 않거나, 우리가 줄바꿈을 직접 'split' 해서 넣으면 됨.
        # text_rect를 구할 때 이미 wrapping된 높이를 구했음 -> 하지만 어디서 끊겼는지는 모름.
        
        # User가 "1번(Composite)처럼 나와야 한다"고 함.
        # Composite의 코드가 이 loop 방식이라면? -> Composite 이미지가 1024px이라서 loop 10px이 티가 덜 났을 수도.
        # 하지만 Dubbing은 1080p+ 라서 티가 확 남.
        
        # 개선된 Loop 방식 (miter limit 문제 피하기 위해):
        # 10px 두께면 loop range(-10, 11)은 너무 많음.
        # 두께를 scaled_factor에 맞춤.
        outline_width = int(6 * scale_factor) # 기본 6px로 조정하고 스케일링
        
        if self.style.get('use_outline', True) and self.style['outline_color'] and self.style['outline_color'].lower() != "none":
            # 외곽선 그리기 (Circular Stroke Algorithm)
            # QTextDocument를 쓰면 쓰레드 충돌(QPaintDevice Crash)이나 NameError 등 불안정할 수 있음.
            # 대신 drawText를 원형으로 여러 번 찍어서 외곽선을 표현함.
            # 기존의 "사각형 채우기 Loop"는 수백 번 그려서 흐려졌으나, 
            # "원형 라인 Loop"는 횟수가 적고(16~32회) 경계가 명확하여 훨씬 선명함.

            painter.setPen(QColor(self.style['outline_color']))
            
            # 외곽선 두께
            outline_width = int(6 * scale_factor)
            if outline_width < 2: outline_width = 2
            
            # 각도 단계 (두께에 따라 유동적으로 조절하거나 고정)
            # 15도 간격 = 24 steps -> 충분히 부드러움
            steps = 24 
            import math
            
            # 1. 외곽선 그리기 (Main Stroke)
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                dx = int(round(outline_width * math.cos(angle)))
                dy = int(round(outline_width * math.sin(angle)))
                painter.drawText(text_draw_area.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, text)
            
            # 2. 두께가 두꺼울 경우 내부 빈틈 메우기 (Inner Stroke)
            # 두께가 4px 이상이면 중간에 하나 더 그려줌
            if outline_width > 3:
                inner_width = outline_width / 2.0
                for i in range(steps):
                    angle = 2 * math.pi * i / steps
                    dx = int(round(inner_width * math.cos(angle)))
                    dy = int(round(inner_width * math.sin(angle)))
                    painter.drawText(text_draw_area.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, text)

        # 3. 텍스트 본문 (맨 위에 덮어쓰기)
        painter.setPen(QColor(self.style['text_color']))
        painter.drawText(text_draw_area, Qt.AlignCenter | Qt.TextWordWrap, text)
        
        painter.end()
        
        # Numpy 변환 및 캐싱
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        import numpy as np
        arr = np.frombuffer(ptr, np.uint8).copy().reshape((height, width, 4))
        
        if len(self._text_cache) > 50:
            self._text_cache.clear()
        self._text_cache[cache_key] = arr
        return arr

class SingleVideoWorker(VideoMergerWorker):
    def __init__(self, img_path, audio_path, output_path, subtitles=None, style=None, volume=1.0, trim_end=0.0, effect_config=None):
        # 상위 클래스의 인스턴스 변수들을 초기화하기 위해 부모 생성자 호출 (디렉토리는 더미로 전달)
        super().__init__(os.path.dirname(img_path), os.path.dirname(audio_path), os.path.dirname(output_path), 
                         subtitles=None, style=style, volume=volume, trim_end=trim_end)
        self.single_img = img_path
        self.single_audio = audio_path
        self.single_output = output_path
        self.single_subtitles = subtitles # list of items
        self.effect_config = effect_config # Store effect config

    def run(self):
        start_time = time.time()
        try:
            base_name = os.path.splitext(os.path.basename(self.single_audio))[0]
            # 개별 자막 리스트를 부모 클래스가 인식할 수 있는 맵 형식으로 변환
            if self.single_subtitles:
                self.subtitles = {base_name: self.single_subtitles}
            else:
                self.subtitles = None
            
            # SingleVideoWorker의 경우 task tuple에 effect_config를 None으로 추가해야 함 (부모 클래스 init을 따랐다면) 
            # 하지만 SingleVideoWorker는 부모 process_single_video를 호출함.
            # 부모가 task 언패킹을 5개로 바꿨으므로 맞춰줘야 함.
            
            # Single Video는 effect_config를 self.effect_config에 저장해둠.
            # task에는 None을 넘기고 process_single_video 내부에서 getattr(self) fallback을 이용하도록 유도.
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
        # 부모 생성자 호출
        super().__init__(os.path.dirname(video_path) if video_path else "", 
                         os.path.dirname(audio_path) if audio_path else "", 
                         os.path.dirname(output_path) if output_path else "", 
                         subtitles=None, style=style, volume=volume)
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.subtitle_data = subtitles # list of strings (manual input) or None
        
    def run(self):
        start_time = time.time()
        try:
            self.log_signal.emit(f"🎬 동영상 더빙 작업 시작: {os.path.basename(self.video_path)}...")
            self.log_signal.emit(f"   오디오: {os.path.basename(self.audio_path)}")
            
            # 0. FFmpeg 바이너리 확보
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                try:
                    import moviepy.config
                    ffmpeg_exe = moviepy.config.get_setting("FFMPEG_BINARY")
                except:
                    ffmpeg_exe = "ffmpeg"
            
            # 1. 오디오 정보 확인 (길이)
            if not os.path.exists(self.audio_path):
                self.error.emit(f"❌ 오디오 파일 없음: {self.audio_path}")
                return
            
            # soundfile로 오디오 길이 측정 (정확도 향상)
            try:
                import soundfile as sf
                f = sf.SoundFile(self.audio_path)
                audio_duration = len(f) / f.samplerate
                f.close()
            except ImportError:
                # Fallback to moviepy
                clip = mpe.AudioFileClip(self.audio_path)
                audio_duration = clip.duration
                clip.close()
                
            self.log_signal.emit(f"   오디오 길이: {audio_duration:.2f}초")
            
            # 2. 비디오 길이 확인
            # ffprobe or moviepy used just for duration check
            # For simplicity, we can use mpe for metadata reading or ffprobe if implemented.
            # Let's use mpe for metadata safe read
            v_clip = mpe.VideoFileClip(self.video_path)
            video_duration = v_clip.duration
            v_clip.close()
            
            self.log_signal.emit(f"   원본 비디오 길이: {video_duration:.2f}초")
            
            # 3. 자막 준비 (Generate PNGs)
            # VideoMergerWorker와 유사한 로직
            # 메타데이터 로드
            # Case-insensitive replacement
            base, ext = os.path.splitext(self.audio_path)
            meta_path = base + ".json"
            self.log_signal.emit(f"   ℹ️ 자막 JSON 경로 확인: {meta_path}")
            sub_timing_list = []
            
            if os.path.exists(meta_path):
                # self.subtitles (manual input) vs JSON
                # Priority: JSON if exists
                # But parent class get_timing_from_metadata logic handles sub_list as help
                # Manual input is stored in self.subtitle_data (list of strings)
                
                # SingleVideoWorker's logic for parsing manual subs:
                # In Dubbing, we usually rely on JSON or manual input mapped to list
                
                # Try to use parent's method if possible, but we need to adapt arguments
                # For now, let's just use the robust JSON loader here
                import json
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # data is list of {"start":.., "end":.., "text":..}
                    # JSON 구조 확인: ElevenLabs의 경우 {"characters": [], "character_start_times_seconds": [], ...} 형태일 수 있음
                    # 또는 우리가 저장한 {"saved_sub_segments": [...]} 형태일 수 있음.
                    # TTSWorker에서 저장하는 방식: 
                    # 1) alignment (characters, start_times, durations)
                    # 2) sub_segments (우리가 만든 문장 단위: start, end, text) - 이것이 가장 확실함.
                    
                    keys = list(data.keys()) if isinstance(data, dict) else "List"
                    self.log_signal.emit(f"   ℹ️ JSON 키 확인: {keys}")

                    if "saved_sub_segments" in data:
                        # 우리가 가공해둔 문장 단위 데이터
                        for item in data["saved_sub_segments"]:
                             s = float(item['start'])
                             e = float(item['end'])
                             t = item['text']
                             sub_timing_list.append((s, e, t))
                    elif "sub_segments" in data:
                        # Fallback for alternative key
                        # Case A: sub_segments has timing (dict with start/end or list)
                        # Case B: sub_segments has ONLY text, and timing is in 'characters' (User Case)
                        
                        has_timing_in_segments = True
                        temp_list = []
                        
                        # Check first item to decide
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
                                     # Saved as [start, end, text]
                                     s = float(item[0])
                                     e = float(item[1])
                                     t = item[2]
                                 else:
                                     continue
                                 sub_timing_list.append((s, e, t))
                        else:
                            # Mapping 'sub_segments' text strings to 'characters' timing
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
                                    
                                    # Length of text to match
                                    seg_len = len(text)
                                    
                                    if current_char_idx + seg_len > total_chars:
                                        # Out of bounds? Try best effort or just break
                                        if current_char_idx < total_chars:
                                            # Partial match?
                                            seg_len = total_chars - current_char_idx
                                        else:
                                            break
                                            
                                    s = all_starts[current_char_idx]
                                    # End of this segment is the end of the last character
                                    e = all_ends[current_char_idx + seg_len - 1]
                                    
                                    sub_timing_list.append((s, e, text))
                                    current_char_idx += seg_len
                                    
                                self.log_signal.emit(f"   ℹ️ 문자 정렬 데이터로 자막 {len(sub_timing_list)}개 매핑 성공")
                            else:
                                self.log_signal.emit("   ⚠️ sub_segments에 시간 정보가 없고 characters 데이터도 없습니다.")
                    elif "characters" in data and "character_start_times_seconds" in data:
                        # Raw Character Alignment Data -> Reconstruct sentences
                        # ElevenLabs returns character-level timestamps. We need to group them.
                        # Simple logic: Group characters until a pause > 0.5s or simple length limits?
                        # Or just use the full duration as one subtitle if it's short?
                        # Better: Use the raw text and split by punctuation, mapping times.
                        # Complexity High. Fallback: Create one single subtitle/segment for now?
                        # Or try to group by ~3-5 seconds blocks.
                        
                        chars = data["characters"]
                        starts = data["character_start_times_seconds"]
                        ends = data["character_end_times_seconds"] if "character_end_times_seconds" in data else starts[1:] + [starts[-1]+0.1]
                        
                        # Very simple grouping strategy:
                        # accumulate text until duration > 3s or pause > 0.5s
                        current_text = ""
                        current_start = starts[0] if starts else 0
                        last_end = 0
                        
                        for i, char in enumerate(chars):
                            t_start = starts[i]
                            t_end = ends[i]
                            
                            # If gap from last_end is big, start new segment (unless it's space)
                            if last_end > 0 and (t_start - last_end) > 0.5 and current_text.strip():
                                sub_timing_list.append((current_start, last_end, current_text.strip()))
                                current_text = ""
                                current_start = t_start
                            
                            current_text += char
                            last_end = t_end
                            
                            # If text gets too long (~50 chars), split at next space
                            if len(current_text) > 50 and char == ' ':
                                sub_timing_list.append((current_start, t_end, current_text.strip()))
                                current_text = ""
                                current_start = t_end

                        # Append remaining
                        if current_text.strip():
                            sub_timing_list.append((current_start, last_end, current_text.strip()))
                            
                        self.log_signal.emit(f"   ℹ️ 문자 데이터에서 자막 {len(sub_timing_list)}개 재구성됨")
                    elif isinstance(data, list):
                         # 혹시 리스트 형태라면?
                         for item in data:
                             if isinstance(item, dict):
                                 s = float(item.get('start', 0))
                                 e = float(item.get('end', 0))
                                 t = item.get('text', "")
                                 sub_timing_list.append((s, e, t))
                    else:
                        self.log_signal.emit("   ⚠️ 알 수 없는 JSON 구조")

                    self.log_signal.emit(f"   ℹ️ JSON 자막 로드 성공 ({len(sub_timing_list)}개)")
                except Exception as e:
                    self.log_signal.emit(f"   ⚠️ JSON 로드 실패: {e}")
            
            # If JSON failed or empty, try manual/auto split?
            # Dubbing mode implies strict syncing, so usually JSON is key.
            # If no JSON, maybe manual subtitles spread evenly? 
            if not sub_timing_list and self.subtitle_data:
                # Spread available subtitles over audio duration
                count = len(self.subtitle_data)
                seg_len = audio_duration / count
                for i, txt in enumerate(self.subtitle_data):
                    s = i * seg_len
                    e = (i+1) * seg_len
                    sub_timing_list.append((s, e, txt))
            
            # Generate PNGs
            temp_files = []
            subtitle_inputs = [] # (path, start, end)
            TARGET_W, TARGET_H = 1920, 1080 # Dubbing outputs also standardized to FHD? Yes recommended.
            
            if sub_timing_list:
                temp_dir = os.path.join(os.path.dirname(self.output_path), "temp_subs_dub")
                os.makedirs(temp_dir, exist_ok=True)
                
                from PIL import Image
                for idx, (start_t, end_t, text) in enumerate(sub_timing_list):
                    if start_t >= audio_duration: continue
                    real_end = min(end_t, audio_duration)
                    
                    # [Fix] 타임스탬프 데이터 오류(3.04로 고정 등)로 길이가 0인 경우 강제 보정
                    if real_end <= start_t:
                        real_end = min(start_t + 3.0, audio_duration)
                        
                    if real_end <= start_t: continue

                    # [Gap Filling Logic]
                    if idx < len(sub_timing_list) - 1:
                        next_start = sub_timing_list[idx+1][0]
                        if 0 < (next_start - real_end) < 0.5:
                            real_end = next_start
                    else:
                        # 마지막 자막은 끝까지 유지
                        real_end = audio_duration
                    
                    # 텍스트 이미지 생성 (numpy array)
                    rgba_arr = self.create_text_image(text, (TARGET_W, TARGET_H))
                    
                    # PNG로 저장
                    sub_filename = f"dub_sub_{idx}.png"
                    sub_path = os.path.join(temp_dir, sub_filename)
                    
                    result_img = Image.fromarray(rgba_arr, 'RGBA')
                    result_img.save(sub_path)
                    
                    temp_files.append(sub_path)
                    subtitle_inputs.append((sub_path, start_t, real_end))

                self.log_signal.emit(f"   📝 자막 이미지 {len(subtitle_inputs)}장 생성 완료")
            else:
                self.log_signal.emit("   ℹ️ 적용할 자막이 없습니다.")

            # 4. FFmpeg Command Construction
            command = [ffmpeg_exe]
            command.append("-y")
            
            # Input 0: Video (Infinite Loop for Background)
            # MUST be before -i
            command.extend(["-stream_loop", "-1"])
            command.extend(["-i", self.video_path]) # [0:v]
            
            # Input 1: Audio
            command.extend(["-i", self.audio_path]) # [1:a]
            
            # Input 2..N: Subtitles
            for s_path, _, _ in subtitle_inputs:
                command.extend(["-i", s_path])
                
            # Filter Complex
            filter_complex = ""
            
            # 1. Process Video [0:v]
            # scale, pad, fps, setsar
            # No trim here, we rely on -shortest
            filter_complex += f"[0:v]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=30[v_bg];"
            
            # 2. Subtitle Overlays
            last_v = "[v_bg]"
            for i, (_, start_t, end_t) in enumerate(subtitle_inputs):
                sub_idx = i + 2
                next_v = f"[v_sub{i}]"
                # Check bounds
                filter_complex += f"{last_v}[{sub_idx}:v]overlay=enable='gte(t,{start_t:.3f})*lt(t,{end_t:.3f})'{next_v};"
                last_v = next_v
            
            # 3. Audio Processing
            # [1:a] -> Volume -> Resample
            vol_val = self.volume
            filter_complex += f"[1:a]volume={vol_val},aresample=48000:async=1[a_out]"
            
            command.extend(["-filter_complex", filter_complex])
            command.extend(["-map", last_v, "-map", "[a_out]"])
            
            # Output Options
            # Explicitly set duration to match audio based on measured duration
            command.extend(["-t", f"{audio_duration:.3f}"])
            
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            # [Fix] Input과 Output이 같으면 FFmpeg 에러 발생하므로 임시 파일 사용
            # (사용자 피드백: 글씨가 안 나오는 이유는 인코딩 자체가 실패했기 때문임)
            temp_output = self.output_path + f".temp_{int(time.time())}.mp4"
            command.extend([temp_output])
            
            self.log_signal.emit(f"💾 최종 인코딩 시작 (Native FFmpeg)...")
            
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
            
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.error.emit(f"❌ FFmpeg 오류: {stderr}")
                if os.path.exists(temp_output):
                    try: os.remove(temp_output)
                    except: pass
                return
            
            # 성공 시 원본 교체
            try:
                if os.path.exists(self.output_path):
                    os.remove(self.output_path)
                os.rename(temp_output, self.output_path)
                self.log_signal.emit(f"✅ 파일 덮어쓰기 완료: {os.path.basename(self.output_path)}")
            except Exception as e:
                self.error.emit(f"❌ 파일 교체 실패: {e}")
                return
            
            # Clean up temp subs
            for path in temp_files:
                try: os.remove(path)
                except: pass
            try:
                 if temp_files: os.rmdir(os.path.dirname(temp_files[0]))
            except: pass

            elapsed = time.time() - start_time
            self.finished.emit(f"✅ 작업 완료: {os.path.basename(self.output_path)}", elapsed)
            
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()

# [참고] 기존 방식(VideoConcatenatorWorkerOld)은 각 파일마다 scale, pad 등 필터 문자열이 약 300자씩 추가되어
# 130개 파일 기준 명령줄 길이가 40,000자를 초과하게 됩니다. (Windows 제한 32,767자)
# 사용자의 파일 경로만 합치면 6,000자여도 필터 옵션 때문에 초과됩니다.
# 따라서 Concat Demuxer 방식으로 변경하여 이 문제를 해결했습니다.
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
            # 0. FFmpeg 바이너리 확보
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                # Fallback: 시스템 PATH에 있길 기대하거나, moviepy config 확인
                try:
                    import moviepy.config
                    ffmpeg_exe = moviepy.config.get_setting("FFMPEG_BINARY")
                except:
                    ffmpeg_exe = "ffmpeg"

            # 1. 파일 목록 및 정렬
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
            
            # 2. FFmpeg 명령어 구성
            command = [ffmpeg_exe]
            
            # Inputs
            # [0] ~ [N-1]: Video Files
            for f in files:
                path = os.path.join(self.video_dir, f).replace("\\", "/") # FFmpeg는 / 경로 선호
                command.extend(["-i", path])
            
            # [N]: Watermark (if exists)
            watermark_idx = -1
            if self.watermark_path and os.path.exists(self.watermark_path):
                command.extend(["-i", self.watermark_path])
                watermark_idx = len(files)

            filter_complex = ""
            
            # Filter Construction
            # 1920x1080, 30fps, 48kHz (High Quality Standard)
            for i in range(len(files)):
                # Video Filter: Scale fit to 1920x1080, Pad if needed, SetSAR 1:1, FPS 30
                # force_original_aspect_ratio=decrease: 원본 비율 유지하며 1920x1080 안에 맞춤
                # pad: 중앙 정렬하여 나머지 검은색 채움
                filter_complex += (f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                                   f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=30[v{i}];")
                
                # Audio Filter: Resample to 48000Hz (Java code used 44100, but we agreed on 48000 for HQ)
                # async=1: Timestamp correction
                filter_complex += f"[{i}:a]aresample=48000:async=1[a{i}];"
                
            # Concat Filter with Gaps
            # 영상 사이 0.2초 정지 화면(Freeze Frame) 및 무음(Silence) 추가 전략
            
            gap_duration = 0.2
            concat_inputs = []
            
            for i in range(len(files)):
                v_source = f"[v{i}]"
                a_source = f"[a{i}]"
                
                if i < len(files) - 1:
                     # 중간 영상들: 0.2초 Padding (tpad, apad)
                     # tpad: stop_mode=clone (마지막 프레임 복제)
                     pad_v_label = f"[v{i}_pad]"
                     pad_a_label = f"[a{i}_pad]"
                     
                     filter_complex += (f"{v_source}tpad=stop_mode=clone:stop_duration={gap_duration}{pad_v_label};"
                                        f"{a_source}apad=pad_dur={gap_duration}{pad_a_label};")
                     
                     concat_inputs.append(pad_v_label)
                     concat_inputs.append(pad_a_label)
                else:
                     # 마지막 영상: Padding 없음
                     concat_inputs.append(v_source)
                     concat_inputs.append(a_source)
            
            # Append input labels for concat
            for label in concat_inputs:
                filter_complex += label
            
            filter_complex += f"concat=n={len(files)}:v=1:a=1[v_concat][out_a];"
            
            # Watermark Overlay
            final_v_label = "[v_concat]"
            if watermark_idx != -1:
                # Scale watermark to width 100 (half of previous 200) -> [wm]
                # Overlay at 20:20
                filter_complex += f"[{watermark_idx}:v]scale=100:-1[wm];"
                filter_complex += f"[v_concat][wm]overlay=20:20[v_final]"
                final_v_label = "[v_final]"
            
            # Remove trailing semicolon if overlay not used (but we added ';' above safely?)
            # Actually scale/concat output labels are internal, map expects final label.
            # If no watermark, we map [v_concat]. If yes, [v_final]
            # Semicolons between filters are needed.
            
            # Clean up filter string logic slightly
            if filter_complex.endswith(";"): 
                filter_complex = filter_complex[:-1] # Remove last ; if any

            command.extend(["-filter_complex", filter_complex])
            command.extend(["-map", final_v_label, "-map", "[out_a]"])
            
            # Encoding Settings
            # Video: libx264, preset medium (balanced speed/compression), pixel format yuv420p (compatibility)
            # CRF 23 used by default (good quality). To match "High Quality" feeling, maybe use CRF 21 or rely on default.
            # Java used ultrafast (fast but big file). We use medium.
            command.extend(["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"])
            
            # Audio: AAC, 192k (High Quality)
            command.extend(["-c:a", "aac", "-b:a", "192k"])
            
            # Overwrite output
            command.extend(["-y", self.output_file])
            
            self.log_signal.emit(f"   FFmpeg 프로세스 실행 중... (시간이 조금 걸릴 수 있습니다)")
            
            # 3. 실행 (subprocess)
            # creationflags=0x08000000 (CREATE_NO_WINDOW) to hide console on Windows
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
            
            # 대기 및 결과 확인
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.error.emit(f"❌ FFmpeg 오류: {stderr}")
                return

            elapsed = time.time() - start_time
            self.finished.emit(f"✅ 최종 영상 합치기 완료: {os.path.basename(self.output_file)} (Native)", elapsed)

        except Exception as e:
            self.error.emit(f"❌ 합치기 오류: {e}")
            import traceback
            traceback.print_exc()

class AudioNormalWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str) # msg
    error = pyqtSignal(str)

    def __init__(self, input_dir, output_dir):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir

    def run(self):
        try:
            # 0. FFmpeg 준비
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = "ffmpeg"

            if not os.path.exists(self.input_dir):
                self.error.emit(f"❌ 입력 폴더 없음: {self.input_dir}")
                return
                
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir, exist_ok=True)

            files = [f for f in os.listdir(self.input_dir) if f.lower().endswith('.mp3')]
            if not files:
                self.error.emit("❌ MP3 파일이 없습니다.")
                return

            total = len(files)
            self.log_signal.emit(f"🔊 오디오 평준화(Normalization) 시작... 총 {total}개")
            
            success_count = 0
            
            # Windows creation flags
            creation_flags = 0x08000000 if os.name == 'nt' else 0

            for i, filename in enumerate(files):
                in_path = os.path.join(self.input_dir, filename)
                out_path = os.path.join(self.output_dir, filename)
                
                self.log_signal.emit(f"[{i+1}/{total}] 처리 중: {filename}")
                
                # loudnorm filter
                cmd = [
                    ffmpeg_exe, "-y", "-i", in_path,
                    "-filter:a", "loudnorm,aresample=48000",
                    "-c:a", "libmp3lame", "-q:a", "2",
                    out_path
                ]
                
                try:
                    subprocess.run(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        check=True,
                        creationflags=creation_flags
                    )
                    success_count += 1
                except subprocess.CalledProcessError as e:
                    self.log_signal.emit(f"   ❌ 실패: {e.stderr.decode('utf-8') if e.stderr else 'Unknown Error'}")
                except Exception as ex:
                    self.log_signal.emit(f"   ❌ 오류: {ex}")

            self.finished.emit(f"작업 완료 (성공 {success_count}/{total})")

        except Exception as e:
            self.error.emit(f"치명적 오류: {e}")

class MainApp(QWidget):
    # Signals must be class variables
    log_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    enable_button_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.driver = None
        self.start_time_gen = 0
        self.start_time_nano = 0
        self.start_time_fx = 0
        self.loaded_items = []
        self.current_file_path = ""
        self.initUI()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_timer_display)

    def initUI(self):
        self.setWindowTitle("YouTube Video Creator Master")
        self.setGeometry(200, 100, 900, 850)
        layout = QVBoxLayout()

        # 메인 레이아웃을 탭 위젯으로 변경
        self.tabs = QTabWidget()
        self.tabs.setElideMode(Qt.ElideNone) # 텍스트 잘림 방지
        self.tabs.setUsesScrollButtons(True) # 탭이 많으면 스크롤 버튼 사용
        self.tabs.tabBar().setExpanding(False) # 탭이 강제로 늘어나지 않고 글자 크기에 맞게 설정

        # 탭 스타일 개선
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; top: -1px; }
            QTabBar::tab {
                background: #2b2b2b;
                color: #b1b1b1;
                border: 1px solid #444;
                padding: 8px 15px;      /* 좌우 패딩 유지 */
                font-size: 13px;
                font-family: 'Malgun Gothic';
                min-width: 110px;       /* 핵심: 탭의 최소 너비를 지정하여 글자 잘림 방지 */
            }
            QTabBar::tab:selected {
                background: #444444;
                color: #ffffff;
                border-bottom-color: #444444;
            }
        """)
        
        layout.addWidget(self.tabs)

        # 탭 1: GenSpark Image
        self.tab1 = QWidget()
        self.initTab1()
        self.tabs.addTab(self.tab1, "GenSpark Image")

        # 탭 1-3: NanoBanana Image (Added next to GenSpark)
        self.tab_nano = QWidget()
        self.initTabNanoBanana()
        self.tabs.addTab(self.tab_nano, "NanoBanana Image")

        # 탭 1-2: ImageFX Image
        self.tab_fx = QWidget()
        self.initTabImageFX()
        self.tabs.addTab(self.tab_fx, "ImageFX Image")

        # 탭 2: ElevenLabs TTS
        self.tab2 = QWidget()
        self.initTab2()
        self.tabs.addTab(self.tab2, "ElevenLabs TTS")

        # 탭 3: Video Composite
        self.tab3 = QWidget()
        self.initTab3()
        self.tabs.addTab(self.tab3, "Video Composite")

        # 탭 4: Video Concat
        self.tab4 = QWidget()
        self.initTab4()
        self.tabs.addTab(self.tab4, "Video Concat")
        
        # 탭 5: Single Video
        self.tab5 = QWidget()
        self.initTab5()
        self.tabs.addTab(self.tab5, "Video Effects")

        # 탭 6: Video Dubbing
        self.tab6 = QWidget()
        self.initTab6()
        self.tabs.addTab(self.tab6, "Video Dubbing")

        # 탭 6-2: Audio Normalization
        self.tab_audio_normal = QWidget()
        self.initTabAudioNormal()
        self.tabs.addTab(self.tab_audio_normal, "Audio Normal")

        # 탭 7: YouTube Analysis
        self.tab7 = QWidget()
        self.initTab7()
        self.tabs.addTab(self.tab7, "YouTube 분석")


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

    def initTabNanoBanana(self):
        layout = QVBoxLayout()

        self.nano_status_label = QLabel("1단계: NanoBanana 브라우저를 먼저 준비해 주세요.")
        self.nano_status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #D4D4D4;")
        layout.addWidget(self.nano_status_label)

        self.nano_timer_label = QLabel("소요 시간: 00:00:00")
        layout.addWidget(self.nano_timer_label)

        # 저장 경로 설정
        path_layout = QHBoxLayout()
        self.nano_image_path_edit = QLineEdit(r"D:\youtube")
        self.nano_image_path_edit.setStyleSheet("background-color: #2D2D2D; color: #D4D4D4; height: 25px;")
        btn_browse_image = QPushButton("찾아보기")
        btn_browse_image.clicked.connect(lambda: self.browse_image_path_custom(self.nano_image_path_edit))
        path_layout.addWidget(QLabel("저장 폴더:"))
        path_layout.addWidget(self.nano_image_path_edit)
        path_layout.addWidget(btn_browse_image)
        layout.addLayout(path_layout)

        # 버튼들
        self.btn_nano_prepare = QPushButton("🌐 1. NanoBanana 브라우저 및 탭 준비")
        self.btn_nano_prepare.setStyleSheet("height: 50px; font-weight: bold; background-color: #673AB7; color: white; border-radius: 8px;")
        self.btn_nano_prepare.clicked.connect(self.launch_browser_nanobanana)
        layout.addWidget(self.btn_nano_prepare)

        # 텍스트 입력창 추가
        layout.addWidget(QLabel("이미지 프롬프트 입력:"))
        self.nano_prompt_input = QTextEdit()
        self.nano_prompt_input.setPlaceholderText("프롬프트 내용을 입력하세요.\n1. 프롬프트1\n2. 프롬프트2")
        self.nano_prompt_input.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.nano_prompt_input)

        btn_h_layout = QHBoxLayout()
        self.btn_nano_start = QPushButton("🚀 2. NanoBanana 이미지 생성 시작")
        self.btn_nano_start.setEnabled(True)
        self.btn_nano_start.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #28a745; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_nano_start.clicked.connect(self.start_automation_nanobanana)
        
        self.btn_nano_stop = QPushButton("🛑 중지")
        self.btn_nano_stop.setEnabled(False)
        self.btn_nano_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.btn_nano_stop.clicked.connect(self.stop_automation_nanobanana)

        btn_h_layout.addWidget(self.btn_nano_start)
        btn_h_layout.addWidget(self.btn_nano_stop)
        layout.addLayout(btn_h_layout)

        # 압축 버튼 추가
        self.btn_nano_compress = QPushButton("🗜️ 3. 이미지 압축 (용량 줄이기)")
        self.btn_nano_compress.setStyleSheet("height: 50px; font-weight: bold; background-color: #FF9800; color: white; border-radius: 8px; margin-top: 5px;")
        self.btn_nano_compress.clicked.connect(lambda: self.compress_images_custom(self.nano_image_path_edit, self.nano_log_display))
        layout.addWidget(self.btn_nano_compress)

        # 로그 디스플레이
        self.nano_log_display = QTextEdit()
        self.nano_log_display.setReadOnly(True)
        self.nano_log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', 'Malgun Gothic';")
        self.nano_log_display.setMaximumHeight(150)
        layout.addWidget(self.nano_log_display)

        self.tab_nano.setLayout(layout)

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

        self.btn_fx_stop = QPushButton("🛑 중지")
        self.btn_fx_stop.setEnabled(False)
        self.btn_fx_stop.setStyleSheet("""
            QPushButton { height: 50px; font-weight: bold; background-color: #dc3545; color: white; border-radius: 8px; }
            QPushButton:disabled { background-color: #6c757d; }
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


        # 합치기 버튼
        self.btn_start_concat = QPushButton("🎞️ 영상 하나로 합치기 (Combine Videos)")
        self.btn_start_concat.setStyleSheet("height: 50px; font-weight: bold; background-color: #ff5722; color: white; border-radius: 8px;")
        self.btn_start_concat.clicked.connect(self.start_video_concat)
        layout.addWidget(self.btn_start_concat)

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
        share_label = QLabel("ℹ️ 상단 Video Composite 탭의 스타일 설정(폰트, 색상, 소리 볼륨 등)이 공유됩니다.")
        share_label.setStyleSheet("color: #008CBA; font-style: italic; margin-bottom: 5px;")
        layout.addWidget(share_label)

        # 생성 버튼
        self.btn_start_single = QPushButton("🎬 영상 효과 적용 일괄 시작 (Batch Effect)")
        self.btn_start_single.setStyleSheet("height: 50px; font-weight: bold; background-color: #008CBA; color: white; border-radius: 8px;")
        self.btn_start_single.clicked.connect(self.start_batch_video_effect)
        layout.addWidget(self.btn_start_single)

        # 로그
        self.single_log = QTextEdit()
        self.single_log.setReadOnly(True)
        self.single_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.single_log)

        self.tab5.setLayout(layout)

    def initTab6(self):
        layout = QVBoxLayout()
        
        # 파일 선택 그룹
        file_group = QGroupBox("파일 선택")
        file_layout = QGridLayout()

        # 동영상 선택
        self.dub_video_path = QLineEdit()
        btn_browse_vid = QPushButton("배경 동영상 선택")
        btn_browse_vid.clicked.connect(lambda: self.browse_single_file(self.dub_video_path, "Video Files (*.mp4 *.avi *.mkv *.mov)"))
        file_layout.addWidget(QLabel("배경 동영상:"), 0, 0)
        file_layout.addWidget(self.dub_video_path, 0, 1)
        file_layout.addWidget(btn_browse_vid, 0, 2)

        # 오디오 선택
        self.dub_audio_path = QLineEdit()
        btn_browse_aud = QPushButton("음성(오디오) 선택")
        btn_browse_aud.clicked.connect(lambda: self.browse_single_file(self.dub_audio_path, "Audio (*.mp3 *.wav)"))
        file_layout.addWidget(QLabel("음성 파일:"), 1, 0)
        file_layout.addWidget(self.dub_audio_path, 1, 1)
        file_layout.addWidget(btn_browse_aud, 1, 2)

        # 출력 선택
        self.dub_output_path = QLineEdit()
        btn_browse_out = QPushButton("저장 경로")
        btn_browse_out.clicked.connect(lambda: self.browse_single_save_file(self.dub_output_path))
        file_layout.addWidget(QLabel("출력 파일:"), 2, 0)
        file_layout.addWidget(self.dub_output_path, 2, 1)
        file_layout.addWidget(btn_browse_out, 2, 2)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 자막 관련 안내
        note_label = QLabel("ℹ️ 자막은 오디오 파일(MP3)과 같은 이름의 .json 파일에서 자동으로 불러옵니다.\n   (ElevenLabs JSON 형식 지원)")
        note_label.setStyleSheet("color: #008CBA; font-weight: bold; padding: 5px;")
        layout.addWidget(note_label)
        
        # 스타일 안내
        layout.addWidget(QLabel("ℹ️ 자막 스타일(폰트, 크기, 색상)은 'Video Composite' 탭의 설정을 따릅니다."))

        # 시작 버튼
        self.btn_start_dubbing = QPushButton("🎬 동영상 합치기 및 자막 생성 (Start Dubbing)")
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
        v_path = self.dub_video_path.text().strip()
        a_path = self.dub_audio_path.text().strip()
        o_path = self.dub_output_path.text().strip()
        
        if not os.path.exists(v_path) or not os.path.exists(a_path):
            QMessageBox.warning(self, "경고", "동영상 또는 오디오 파일이 존재하지 않습니다.")
            return
            
        if not o_path:
            QMessageBox.warning(self, "경고", "출력 경로를 지정해주세요.")
            return

        # 자막: None으로 설정하여 Worker가 JSON에서 자동으로 찾게 함
        subtitles = None
                    
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
        self.dub_log.append("⏳ 작업 시작...")
        self.dub_log.append(f"⚙️ 적용 스타일: 폰트[{style['font_family']}] 크기[{style['font_size']}] 색상[{style['text_color']}]")
        self.dub_log.append(f"   (폰트 크기가 너무 크거나 작으면 'Video Composite' 탭에서 조절하세요.)")
        
        self.dub_worker = VideoDubbingWorker(v_path, a_path, o_path, subtitles, style, volume)
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
        self.concat_log.append("⏳ 영상 합치기 작업을 시작합니다...")

        self.concat_worker = VideoConcatenatorWorker(in_dir, out_file, wm_path) # Pass wm_path
        self.concat_worker.log_signal.connect(self.concat_log.append)
        self.concat_worker.finished.connect(self.on_video_concat_finished)
        self.concat_worker.error.connect(lambda e: self.concat_log.append(f"❌ 오류: {e}"))
        self.concat_worker.start()

    def on_video_concat_finished(self, msg, elapsed):
        self.btn_start_concat.setEnabled(True)
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
        target_keywords = ["Gmarket", "Nanum", "Malgun"]
        
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
        self.tts_log.append("⏳ 생성 시작...")

        # 스레드로 실행 (tasks 리스트 전달)
        audio_target = self.audio_path_edit.text().strip()
        threading.Thread(target=self._run_tts_thread, args=(tasks, voice_id, model_id, stability, similarity, style, speed, volume, audio_target, trim_end), daemon=True).start()

    def _run_tts_thread(self, tasks, voice_id, model_id, stability, similarity, style, speed, volume, custom_dir, trim_end=0.0):
        success_count = 0
        try:
            for task in tasks:
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

    def browse_image_path(self):
        path = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if path:
            self.image_path_edit.setText(path)

    def browse_image_path_custom(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if path:
            line_edit.setText(path)

    def launch_browser_and_tabs(self):
        try:
            self.log_display.append("🌐 브라우저를 실행합니다...")
            chrome_cmd = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            user_data = r'C:\sel_chrome'
            target_url = "https://www.genspark.ai/agents?type=moa_generate_image" 
            
            if not os.path.exists(user_data):
                os.makedirs(user_data)
                
            subprocess.Popen([chrome_cmd, '--remote-debugging-port=9222', f'--user-data-dir={user_data}', target_url])
            
            # Wait for browser to open
            time.sleep(3)
            
            opt = Options()
            opt.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
            
            # Ensure 2 tabs
            if len(self.driver.window_handles) < 2:
                self.driver.execute_script(f"window.open('{target_url}');")
                
            self.log_display.append("✅ 브라우저 연결 성공. 두 개의 탭을 확인하세요.")
            self.status_label.setText("2단계: 프롬프트 입력 후 시작 버튼을 누르세요.")
            
        except Exception as e:
            self.log_display.append(f"❌ 브라우저 실행 오류: {e}")
            self.status_label.setText("오류 발생 (로그 확인)")

    def launch_browser_nanobanana(self):
        try:
            self.nano_log_display.append("🌐 NanoBanana 브라우저를 실행합니다...")
            chrome_cmd = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            user_data = r'C:\sel_chrome_nano'
            target_url = "https://gemini.google.com/app?hl=ko" 
            
            if not os.path.exists(user_data):
                os.makedirs(user_data)
                
            subprocess.Popen([chrome_cmd, '--remote-debugging-port=9224', f'--user-data-dir={user_data}', target_url])
            
            # Wait for browser to open
            time.sleep(3)
            
            opt = Options()
            opt.add_experimental_option("debuggerAddress", "127.0.0.1:9224")
            self.driver_nano = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
            
            # Ensure 2 tabs
            if len(self.driver_nano.window_handles) < 2:
                self.driver_nano.execute_script(f"window.open('{target_url}');")
                
            self.nano_log_display.append("✅ NanoBanana 브라우저 연결 성공. 두 개의 탭을 확인하세요.")
            self.nano_status_label.setText("2단계: 프롬프트 입력 후 시작 버튼을 누르세요.")
            
        except Exception as e:
            self.nano_log_display.append(f"❌ 브라우저 실행 오류: {e}")
            self.nano_status_label.setText("오류 발생 (로그 확인)")

    def launch_browser_imagefx(self):
        try:
            self.fx_log_display.append("🌐 ImageFX용 브라우저를 실행합니다...")
            chrome_cmd = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            user_data = r'C:\sel_chrome_fx'
            target_url = "https://labs.google/fx/ko/tools/image-fx"
            if not os.path.exists(user_data): os.makedirs(user_data)
            subprocess.Popen([chrome_cmd, '--remote-debugging-port=9223', f'--user-data-dir={user_data}', target_url])
            
            time.sleep(3)
            opt = Options()
            opt.add_experimental_option("debuggerAddress", "127.0.0.1:9223")
            self.driver_fx = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
            
            # 2번째 탭
            if len(self.driver_fx.window_handles) < 2:
                self.driver_fx.execute_script(f"window.open('{target_url}');")
            
            self.fx_log_display.append("✅ ImageFX 준비됨. 로그인 후 시작 버튼을 누르세요.")
            self.fx_status_label.setText("상태: 브라우저 준비됨.")
        except Exception as e:
            self.fx_log_display.append(f"❌ 오류: {e}")

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

        # NanoBanana Timer
        if hasattr(self, 'start_time_nano') and self.start_time_nano > 0:
            elapsed = int(now - self.start_time_nano)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            if hasattr(self, 'nano_timer_label'):
                self.nano_timer_label.setText(f"소요 시간: {h:02d}:{m:02d}:{s:02d}")

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

    def start_automation_nanobanana(self):
        if not hasattr(self, 'driver_nano') or not self.driver_nano:
            self.nano_log_display.append("❌ 브라우저가 준비되지 않았습니다.")
            return
        
        text = self.nano_prompt_input.toPlainText().strip()
        if not text:
            self.nano_log_display.append("❌ 입력된 프롬프트가 없습니다.")
            return

        # 프롬프트 파싱: (\d+)\s*\.\s*\{(.*?)\}
        loaded_items = re.findall(r'(\d+)\s*\.\s*\{(.*?)\}', text, re.DOTALL)
        
        if not loaded_items:
            # Fallback for old format
            loaded_items = []
            for line in text.split('\n'):
                match = re.match(r'^(\d+(?:-\d+)?)\.?\s*(.*)', line.strip())
                if match:
                    loaded_items.append((match.group(1), match.group(2)))

        if not loaded_items:
            self.nano_log_display.append("❌ 프롬프트 형식이 올바르지 않습니다 (예: 1. {프롬프트})")
            return

        self.btn_nano_start.setEnabled(False)
        self.btn_nano_stop.setEnabled(True)
        self.start_time_nano = time.time()
        if not self.ui_timer.isActive():
            self.ui_timer.start(1000) 
        
        file_path = "nano_" + time.strftime("%H%M%S")
        image_target = self.nano_image_path_edit.text().strip()
        
        self.worker_nano = NanoBananaMultiTabWorker(file_path, loaded_items, self.driver_nano, custom_target_dir=image_target)
        self.worker_nano.progress.connect(self.nano_status_label.setText)
        self.worker_nano.log_signal.connect(lambda m: self.nano_log_display.append(m))
        self.worker_nano.finished.connect(self.on_success_nano)
        self.worker_nano.error.connect(self.on_error_nano)
        self.worker_nano.start()

    def on_success_nano(self, msg, elapsed):
        self.start_time_nano = 0
        if self.start_time_gen == 0 and self.start_time_fx == 0:
            self.ui_timer.stop()
            
        self.btn_nano_start.setEnabled(True)
        self.btn_nano_stop.setEnabled(False)
        self.nano_log_display.append(f"🏁 {msg}")
        
        # 생성 완료 후 자동 압축 실행
        if hasattr(self, 'worker_nano') and self.worker_nano.target_dir:
            self.nano_log_display.append("🔄 생성 완료: 자동 압축(JPG 변환)을 시작합니다...")
            self.compress_images(dir_path=self.worker_nano.target_dir)

    def on_error_nano(self, err):
        self.start_time_nano = 0
        if self.start_time_gen == 0 and self.start_time_fx == 0:
            self.ui_timer.stop()
            
        self.btn_nano_start.setEnabled(True)
        self.btn_nano_stop.setEnabled(False)
        self.nano_log_display.append(f"❗ 오류: {err}")

    def stop_automation_nanobanana(self):
        if hasattr(self, 'worker_nano') and self.worker_nano.isRunning():
            self.worker_nano.stop()
            self.nano_log_display.append("🛑 중지 요청 중... (현재 작업 완료 후 중단됩니다)")
            self.btn_nano_stop.setEnabled(False)

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

    def initTabAudioNormal(self):
        layout = QVBoxLayout()
        
        # 안내
        layout.addWidget(QLabel("📢 MP3 오디오 파일의 볼륨을 일정하게 평준화(Normalization) 합니다."))
        layout.addWidget(QLabel("   (ElevenLabs 자막 싱크(Duration)에 영향을 주지 않으므로 안심하고 사용하세요.)"))

        # 폴더 선택 그룹
        dir_group = QGroupBox("폴더 선택")
        dir_layout = QGridLayout()
        
        self.an_input_dir = QLineEdit(r"D:\youtube")
        btn_in = QPushButton("입력 폴더")
        btn_in.clicked.connect(lambda: self.browse_folder(self.an_input_dir))
        
        self.an_output_dir = QLineEdit(r"D:\youtube\normalized")
        btn_out = QPushButton("출력 폴더")
        btn_out.clicked.connect(lambda: self.browse_folder(self.an_output_dir))
        
        dir_layout.addWidget(QLabel("입력(원본) 폴더:"), 0, 0)
        dir_layout.addWidget(self.an_input_dir, 0, 1)
        dir_layout.addWidget(btn_in, 0, 2)
        
        dir_layout.addWidget(QLabel("출력(저장) 폴더:"), 1, 0)
        dir_layout.addWidget(self.an_output_dir, 1, 1)
        dir_layout.addWidget(btn_out, 1, 2)
        
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # 시작 버튼
        self.btn_start_an = QPushButton("🔊 오디오 평준화 시작 (Start Normalization)")
        self.btn_start_an.setStyleSheet("height: 50px; font-weight: bold; background-color: #009688; color: white; border-radius: 8px;")
        self.btn_start_an.clicked.connect(self.start_audio_normal)
        layout.addWidget(self.btn_start_an)
        
        # 로그
        self.an_log = QTextEdit()
        self.an_log.setReadOnly(True)
        self.an_log.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.an_log)
        
        self.tab_audio_normal.setLayout(layout)

    def start_audio_normal(self):
        i_path = self.an_input_dir.text().strip()
        o_path = self.an_output_dir.text().strip()
        
        if not os.path.exists(i_path):
            QMessageBox.warning(self, "경고", "입력 폴더가 존재하지 않습니다.")
            return

        self.btn_start_an.setEnabled(False)
        self.an_log.append("⏳ 작업 시작...")
        
        self.an_worker = AudioNormalWorker(i_path, o_path)
        self.an_worker.log_signal.connect(self.an_log.append)
        self.an_worker.finished.connect(lambda m: [self.an_log.append(f"🏁 {m}"), self.btn_start_an.setEnabled(True)])
        self.an_worker.error.connect(lambda e: [self.an_log.append(f"❌ {e}"), self.btn_start_an.setEnabled(True)])
        self.an_worker.start()

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
        self.single_log.append(f"⏳ 일괄 작업 시작: {input_dir}")
        self.single_log.append(f"   출력 대상: {output_dir}")

        self.batch_eff_worker = BatchVideoEffectWorker(
            input_dir, output_dir, style, volume, trim_end, effect_config
        )
        self.batch_eff_worker.log_signal.connect(self.single_log.append)
        self.batch_eff_worker.finished.connect(lambda m, t: [self.single_log.append(f"🏁 {m}"), self.btn_start_single.setEnabled(True)])
        self.batch_eff_worker.error.connect(lambda e: [self.single_log.append(f"❌ {e}"), self.btn_start_single.setEnabled(True)])
        self.batch_eff_worker.start()

class BatchVideoEffectWorker(VideoMergerWorker):
    def __init__(self, input_dir, output_dir, style=None, volume=1.0, trim_end=0.0, effect_config=None):
        # 부모 생성자 호출 (경로는 input_dir로 설정)
        super().__init__(input_dir, input_dir, output_dir, subtitles=None, style=style, volume=volume, trim_end=trim_end)
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.effect_config = effect_config # 부모 process_single_video가 이 속성을 참조하여 효과 적용
        
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
            
            for idx, mp3 in enumerate(mp3_files):
                base_name = os.path.splitext(mp3)[0]
                audio_path = os.path.join(self.input_dir, mp3)
                output_path = os.path.join(self.output_dir, f"{base_name}.mp4")
                
                # 이미지 찾기 (같은 폴더 내)
                img_path = None
                for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                    check = os.path.join(self.input_dir, base_name + ext)
                    if os.path.exists(check):
                        img_path = check
                        break
                        
                if not img_path:
                    self.log_signal.emit(f"⚠️ [{idx+1}/{total}] 이미지 없음, 건너뜀: {base_name}")
                    continue
                
                self.log_signal.emit(f"🎬 [{idx+1}/{total}] 처리 중: {base_name}")
                
                # [NEW] 랜덤 효과 로직
                if self.effect_config and self.effect_config.get('random'):
                    import random
                    new_type = random.randint(1, 3) # 1~3 (Zoom, PanLR, PanRL)
                    self.effect_config['type'] = new_type
                    
                    eff_names = ["None", "Zoom", "Pan(L->R)", "Pan(R->L)"]
                    if 0 <= new_type < len(eff_names):
                        self.log_signal.emit(f"   🎲 랜덤 효과 적용: {eff_names[new_type]}")
                
                # 자막 자동 로드 (부모 클래스가 JSON 자동 로드함)
                # Task 준비 (img, audio, output, base_name, manual_subs=None)
                task = (img_path, audio_path, output_path, base_name, None)
                
                # process_single_video 호출
                res = self.process_single_video(task)
                if res:
                    success_count += 1
            
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