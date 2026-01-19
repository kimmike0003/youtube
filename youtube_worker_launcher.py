import os
import time
import subprocess
import socket
import requests  # Ensure requests is installed
from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

class BrowserLauncherWorker(QThread):
    finished = pyqtSignal(object) # Returns (driver, None) or (None, error_msg)
    log_signal = pyqtSignal(str)

    def __init__(self, browser_type):
        super().__init__()
        self.browser_type = browser_type

    def run(self):
        try:
            port = 9222
            user_data = r'C:\sel_chrome'
            target_url = "https://www.genspark.ai/agents?type=moa_generate_image"
            chrome_cmd = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            
            if self.browser_type == 'imagefx':
                self.log_signal.emit("🌐 ImageFX용 브라우저를 실행합니다...")
                user_data = r'C:\sel_chrome_fx'
                target_url = "https://labs.google/fx/ko/tools/image-fx"
                port = 9223
            else:
                self.log_signal.emit("🌐 브라우저를 실행합니다...")

            if not os.path.exists(user_data):
                os.makedirs(user_data)
                
            if not os.path.exists(chrome_cmd):
                self.log_signal.emit(f"⚠️ Chrome 실행 파일을 찾을 수 없습니다: {chrome_cmd}")
                raise FileNotFoundError(f"Chrome not found at {chrome_cmd}")

            # 1. Kill existing chrome instances for this user_data
            self.log_signal.emit(f"   🧹 기존 프로세스 정리 중 ({user_data})...")
            try:
                ps_script = f"""
                Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | 
                Where-Object {{ $_.CommandLine -like "*{user_data}*" }} | 
                ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}
                """
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                time.sleep(1)
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 프로세스 정리 실패 (무시됨): {e}")

            # 2. Prevent "Restore pages?" popup by modifying Preferences
            try:
                pref_file = os.path.join(user_data, "Default", "Preferences")
                if os.path.exists(pref_file):
                    import json
                    with open(pref_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    changed = False
                    if "profile" in data:
                        if data["profile"].get("exit_type") != "Normal":
                            data["profile"]["exit_type"] = "Normal"
                            changed = True
                        if data["profile"].get("exited_cleanly") is not True:
                            data["profile"]["exited_cleanly"] = True
                            changed = True
                    
                    if changed:
                        self.log_signal.emit("   🔧 비정상 종료 기록 수정 (복구 팝업 방지)")
                        with open(pref_file, "w", encoding="utf-8") as f:
                            json.dump(data, f)
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 기본 설정 수정 실패 (무시됨): {e}")

            # 3. Launch Chrome
            cmd = [
                chrome_cmd, 
                f'--remote-debugging-port={port}', 
                f'--user-data-dir={user_data}', 
                '--remote-allow-origins=*',
                '--disable-popup-blocking',
                '--start-maximized',
                target_url
            ]
            
            self.log_signal.emit(f"   🚀 크롬 실행 시도 (Port: {port})...")
            proc = subprocess.Popen(cmd)
            
            # 4. Wait & Check
            self.log_signal.emit("   ⏳ 실행 대기 중 (5초)...")
            time.sleep(5)
            
            if proc.poll() is not None:
                self.log_signal.emit(f"   ❌ Chrome이 즉시 종료되었습니다. Exit Code: {proc.poll()}")
                self.finished.emit((None, f"Chrome crashed with exit code {proc.poll()}"))
                return

            # 5. Port Check
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
                if resp.status_code == 200:
                    self.log_signal.emit("   ✅ 디버깅 포트 응답 확인됨.")
                else:
                    self.log_signal.emit(f"   ⚠️ 디버깅 포트 응답 이상: {resp.status_code}")
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 디버깅 포트 접속 불가: {e}")
                self.log_signal.emit("   (방화벽이나 보안 프로그램이 차단했을 수 있습니다.)")
            
            # 6. Connecting Driver
            opt = Options()
            opt.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            opt.page_load_strategy = 'none' # Critical for non-blocking
            
            try:
                self.log_signal.emit("   📥 드라이버 확인 및 설치 중...")
                driver_path = ChromeDriverManager().install() 
                self.log_signal.emit(f"   🚗 드라이버 경로: {driver_path}")
                
                service = Service(driver_path)
                
                self.log_signal.emit("   🔗 브라우저에 연결 시도...")
                driver = webdriver.Chrome(service=service, options=opt)
            except Exception as e:
                self.log_signal.emit(f"   ❌ 드라이버 연결 실패: {e}")
                self.finished.emit((None, str(e)))
                return
            
            # 7. Ensure 2 Tabs
            try:
                driver.set_page_load_timeout(10)
                current_tabs = len(driver.window_handles)
                self.log_signal.emit(f"   ℹ️ 초기 탭 수: {current_tabs}")

                if current_tabs < 2:
                    self.log_signal.emit("   ➕ 2번째 탭 생성 시도...")
                    try:
                        driver.switch_to.new_window('tab')
                        driver.get(target_url)
                    except Exception as e1:
                        self.log_signal.emit(f"   ⚠️ SwitchTo 방식 실패({e1}), JS 방식 시도...")
                        driver.execute_script(f"window.open('{target_url}', '_blank');")
                        time.sleep(1)
                    
                    time.sleep(2)
                    
                    if len(driver.window_handles) < 2:
                         self.log_signal.emit("   ⚠️ 탭 생성 재시도 (빈 탭)...")
                         driver.execute_script("window.open('');")
                         time.sleep(1)
                         if len(driver.window_handles) >= 2:
                             try:
                                 driver.switch_to.window(driver.window_handles[-1])
                                 driver.get(target_url)
                             except:
                                 pass

                final_count = len(driver.window_handles)
                self.log_signal.emit(f"   ✅ 최종 탭 수: {final_count}")
                
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 탭 확인 중 경고 (무시 가능): {e}")
            
            self.finished.emit((driver, None))

        except Exception as e:
            self.finished.emit((None, str(e)))
