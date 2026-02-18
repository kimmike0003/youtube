import os
import time
import subprocess
import socket
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
                target_url = "https://labs.google/fx/ko/tools/image-fx"
                port = 9223
            elif self.browser_type == 'grok':
                self.log_signal.emit("🌐 Grok용 브라우저를 실행합니다...")
                target_url = "https://grok.com/imagine"
            else:
                self.log_signal.emit("🌐 브라우저를 실행합니다...")
                self.log_signal.emit("🌐 브라우저를 실행합니다...")

            if not os.path.exists(user_data):
                os.makedirs(user_data)
                
            if not os.path.exists(chrome_cmd):
                self.log_signal.emit(f"⚠️ Chrome 실행 파일을 찾을 수 없습니다: {chrome_cmd}")

            # Kill existing chrome instances for this user_data to ensure clean state
            self.log_signal.emit(f"   🧹 기존 프로세스 정리 중 ({user_data})...")
            try:
                # PowerShell command to find and kill chrome processes with specific user-data-dir
                ps_script = f"""
                Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | 
                Where-Object {{ $_.CommandLine -like "*{user_data}*" }} | 
                ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}
                """
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                time.sleep(1)
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 프로세스 정리 실패 (무시됨): {e}")

            # [Fix] Prevent "Restore pages?" popup by modifying Preferences
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

            cmd = [
                chrome_cmd, 
                f'--remote-debugging-port={port}', 
                f'--user-data-dir={user_data}', 
                '--remote-allow-origins=*',
                '--disable-popup-blocking',
                '--start-maximized',
                '--ignore-certificate-errors',
                target_url
            ]
            
            self.log_signal.emit(f"   🚀 크롬 실행 시도 (Port: {port})...")
            # Always try to launch. Chrome handles single-instance logic.
            proc = subprocess.Popen(cmd)
            
            # Allow some time for launch
            self.log_signal.emit("   ⏳ 실행 대기 중 (5초)...")
            time.sleep(5)
            
            # Check if process is still alive
            if proc.poll() is not None:
                self.log_signal.emit(f"   ❌ Chrome이 즉시 종료되었습니다. Exit Code: {proc.poll()}")
                self.finished.emit((None, f"Chrome crashed with exit code {proc.poll()}"))
                return

            # Check if port is listening
            import requests
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
                if resp.status_code == 200:
                    self.log_signal.emit("   ✅ 디버깅 포트 응답 확인됨.")
                else:
                    self.log_signal.emit(f"   ⚠️ 디버깅 포트 응답 이상: {resp.status_code}")
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 디버깅 포트 접속 불가: {e}")
                self.log_signal.emit("   (방화벽이나 보안 프로그램이 차단했을 수 있습니다.)")
            
            # Connect
            opt = Options()
            opt.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            opt.page_load_strategy = 'none' # Do not block on page load
            
            try:
                self.log_signal.emit("   📥 드라이버 확인 중 (ChromeDriverManager)...")
                # driver_path = ChromeDriverManager().install() # Sometimes hangs?
                # Use a specific version or cached if possible. For now, log it.
                driver_path = ChromeDriverManager().install() 
                self.log_signal.emit(f"   🚗 드라이버 경로: {driver_path}")
                
                service = Service(driver_path)
                
                self.log_signal.emit("   🔗 브라우저에 연결 시도...")
                driver = webdriver.Chrome(service=service, options=opt)
            except Exception as e:
                self.log_signal.emit(f"   ❌ 드라이버 연결 실패: {e}")
                self.finished.emit((None, str(e)))
                return
            
            # Ensure 2 tabs - Robust Method
            try:
                # Set a page load timeout
                driver.set_page_load_timeout(10)
                
                # Initial Check
                current_tabs = len(driver.window_handles)
                self.log_signal.emit(f"   ℹ️ 초기 탭 수: {current_tabs}")

                if current_tabs < 2:
                    self.log_signal.emit("   ➕ 2번째 탭 생성 시도...")
                    try:
                        # Method 1: Selenium 4 Built-in
                        driver.switch_to.new_window('tab')
                        driver.get(target_url)
                    except Exception as e1:
                        self.log_signal.emit(f"   ⚠️ Method 1 실패 ({e1}), Method 2 시도...")
                        # Method 2: JavaScript
                        driver.execute_script(f"window.open('{target_url}', '_blank');")
                        time.sleep(1)
                    
                    time.sleep(1)
                    
                    # Re-check
                    if len(driver.window_handles) < 2:
                         self.log_signal.emit("   ⚠️ 2번째 탭 감지 실패 -> 강제 생성 (빈 탭)")
                         driver.execute_script("window.open('');")
                         time.sleep(1)
                         # Navigate last tab
                         if len(driver.window_handles) >= 2:
                             driver.switch_to.window(driver.window_handles[-1])
                             try:
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
