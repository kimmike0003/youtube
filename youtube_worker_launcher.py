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
                port = 9223
            elif self.browser_type == 'whisk':
                self.log_signal.emit("🌐 Whisk AI용 브라우저를 실행합니다...")
                user_data = r'C:\sel_chrome_whisk'
                target_url = "https://labs.google/fx/tools/whisk/project"
                port = 9224
            elif self.browser_type == 'grok':
                self.log_signal.emit("🌐 Grok용 브라우저를 실행합니다...")
                target_url = "https://grok.com/imagine"
            else:
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
            
                # 2. 탭 개수 조정 (정확하게 2개로 유지)
                current_handles = driver.window_handles
                self.log_signal.emit(f"   🔍 탭 개수 조정 중... (전체 {len(current_handles)}개)")

                # 2-1. 2개보다 많으면 초과분 제거 (안전하게 첫 번째 탭에 포커스 고정 후 실행)
                while len(driver.window_handles) > 2:
                    h_to_close = driver.window_handles[-1]
                    driver.switch_to.window(h_to_close)
                    driver.close()
                    # 닫은 후 즉시 남은 첫 번째 탭으로 복구
                    driver.switch_to.window(driver.window_handles[0])
                    time.sleep(0.5)

                # 2-2. 2개보다 부족하면 채우기
                while len(driver.window_handles) < 2:
                    driver.switch_to.new_window('tab')
                    driver.get(target_url)
                    time.sleep(1)

                # 3. 모든 탭이 목표 URL인지 확인 및 이동
                final_handles = driver.window_handles
                for i, h in enumerate(final_handles):
                    try:
                        driver.switch_to.window(h)
                        curr_url = driver.current_url.lower()
                        # 도메인 기반 체크
                        if not any(d in curr_url for d in ["grok.com", "labs.google", "genspark.ai"]):
                            self.log_signal.emit(f"   🌐 [탭 {i+1}] 목표 URL 이동...")
                            driver.get(target_url)
                            time.sleep(1)
                    except:
                        pass
                
                # 포커스를 0번으로 고정하고 마무리
                driver.switch_to.window(driver.window_handles[0])
                self.log_signal.emit(f"   ✅ 최종 작업 탭 {len(driver.window_handles)}개 확보 완료.")

            except Exception as e:
                self.log_signal.emit(f"   ⚠️ 탭 세팅 중 알림: {e}")
            
            self.finished.emit((driver, None))

        except Exception as e:
            self.finished.emit((None, str(e)))
