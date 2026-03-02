import sys
import os
import time
import base64
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

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


    # [NEW] Multi-Image Check
    def check_images_multiple(self, driver, old_srcs):
        try:
            # 1. 문서 내 모든 이미지 수집
            # 2. old_srcs에 없는거 필터링
            # 3. base64인지 확인
            # 4. 리스트 반환
            
            script = """
            var old_srcs = arguments[0];
            var imgs = Array.from(document.querySelectorAll('img'));
            var new_data = [];
            
            for (var img of imgs) {
                var src = img.src;
                if (!src) continue;
                if (src.startsWith('data:image/svg')) continue; // 아이콘 제외
                if (src.length < 5000) continue; // 썸네일/아이콘 제외
                
                // Old Srcs에 포함되어 있는지 확인
                // (완전 일치 혹은 일부 일치? 완전 일치로 충분할듯)
                if (old_srcs.includes(src)) continue;
                
                // Base64 데이터 추출
                if (src.startsWith('data:image')) {
                     var b64 = src.split(',')[1];
                     if (b64) new_data.push(b64);
                }
            }
            return new_data;
            """
            result = driver.execute_script(script, old_srcs)
            return result if result else []
            
        except Exception:
            return []

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
                            # from selenium.webdriver.common.action_chains import ActionChains (imported at top)
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
                            # [CHANGED] 다시 타이핑 방식으로 변경 (JS 주입 실패 피드백 반영)
                            actions = ActionChains(self.driver)
                            if input_box:
                                actions.move_to_element(input_box).click()
                                
                                # Clear (Ctrl+A -> Del)
                                actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).pause(0.1).send_keys(Keys.DELETE).pause(0.1)
                                
                                # Typing directly (타이핑 하듯이 입력)
                                actions.send_keys(p_text)
                                
                                # Activate Button (Trigger: Space -> Backspace)
                                actions.pause(0.5).send_keys(" ").pause(0.1).send_keys(Keys.BACKSPACE).perform()
                                
                            else:
                                # InputBox 못 찾았을 경우 fallback
                                actions.send_keys(p_text).pause(0.2)
                                actions.send_keys(" ").pause(0.1).send_keys(Keys.BACKSPACE).perform()
                            
                        except Exception as e:
                            self.log_signal.emit(f"⚠️ 입력 실패: {e}")
                            # 최후의 수단: JS 값 주입 및 이벤트 강제 발생
                            if input_box:
                                self.driver.execute_script("""
                                    arguments[0].innerText = arguments[1];
                                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                """, input_box, p_text)

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
                        
                        # [Modified] 상태 정보에 'saved_count' 추가 (4장 저장 목표)
                        tab_status[tab] = {"item": current_item, "start_time": time.time(), "saved_count": 0, "found_srcs": []}
                        item_idx += 1
                        self.progress.emit(f"진행: {processed_count}/{total}")

                    elif tab_status[tab] is not None:
                        target_num = tab_status[tab]["item"][0]
                        # [NEW] 다중 이미지 확인 로직
                        new_images = self.check_images_multiple(self.driver, tab_old_srcs[tab])
                        
                        # 이미 저장한 이미지는 제외
                        current_found = tab_status[tab]["found_srcs"]
                        cnt = tab_status[tab]["saved_count"]
                        
                        # 새로 발견된 이미지 중 아직 처리 안 한 것만 필터링 (Base64 앞부분 비교 등은 너무 기니까, JS에서 중복 걸러주긴 함)
                        # 하지만 JS는 'old_srcs'(생성 전)와 비교함.
                        # 여기서는 이번 생성 턴에서 이미 저장한 것과 중복 방지가 필요할 수 있으나, 
                        # check_images_multiple이 매번 '새로운 것'을 다 리턴해주면 리스트가 계속 커짐.
                        # -> JS 로직을 수정하거나, 여기서 관리.
                        # JS는 "old_srcs에 없는 모든 것"을 리턴함. 즉, 이번 턴에 생긴 1,2,3,4가 계속 리턴됨.
                        
                        saved_in_this_loop = 0
                        for img_b64 in new_images:
                            # 간단한 중복 체크 (해시값 혹은 길이+앞부분)
                            img_sig = str(len(img_b64)) + img_b64[:30]
                            if img_sig in current_found:
                                continue
                                
                            current_found.append(img_sig)
                            cnt += 1
                            
                            # 파일명: 1-1.png, 1-2.png ...
                            save_name = f"{target_num}-{cnt}.png"
                            save_path = os.path.join(self.target_dir, save_name)
                            
                            try:
                                with open(save_path, "wb") as f:
                                    f.write(base64.b64decode(img_b64))
                                self.log_signal.emit(f"  ✅ [탭 {tabs.index(tab)+1}] {save_name} 저장 완료")
                                saved_in_this_loop += 1
                            except Exception as e:
                                self.log_signal.emit(f"  ❌ 저장 실패 ({save_name}): {e}")

                        tab_status[tab]["saved_count"] = cnt
                        
                        # 종료 조건: 4장 이상 저장했거나, 시간 초과되었는데 1장이라도 건졌거나
                        is_timeout = (time.time() - tab_status[tab]["start_time"] > 60) # 4장 다 나오는데 보통 30초 내외
                        if cnt >= 4:
                            tab_status[tab] = None
                            processed_count += 1
                        elif is_timeout:
                            if cnt > 0:
                                self.log_signal.emit(f"  ⚠️ [탭 {tabs.index(tab)+1}] {target_num}번: {cnt}장 저장 후 이동 (타임아웃)")
                                tab_status[tab] = None # 부분 성공 처리
                                processed_count += 1
                            else:
                                # 진짜 타임아웃 (0장) -> Max Timeout (250s)까지 대기해야 할까?
                                # 위 60초는 "4장 모으기"를 위한 소프트 타임아웃. 
                                # 아예 생성이 안된거면 더 기다려야 함.
                                real_timeout = 250
                                if time.time() - tab_status[tab]["start_time"] > real_timeout:
                                    self.log_signal.emit(f"  ❌ [탭 {tabs.index(tab)+1}] {target_num}번 실패 (타임아웃)")
                                    failed_items.append(tab_status[tab]["item"])
                                    tab_status[tab] = None
                                    processed_count += 1
                            processed_count += 1
                
                time.sleep(1)

            if not self.is_running:
                 self.log_signal.emit("🛑 ImageFX 작업이 중지되었습니다.")
                 
            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})" if self.is_running else "중지됨"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))


class GeminiAPIImageWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, items, api_key, model_name, target_dir):
        super().__init__()
        self.items = items
        self.api_key = api_key
        self.model_name = model_name
        self.target_dir = target_dir
        self.is_running = True
        os.makedirs(self.target_dir, exist_ok=True)
    
    def process_item(self, item):
        """개별 아이템 처리 (Thread Pool에서 실행됨)"""
        if not self.is_running: return (False, "중지됨", item)

        num, prompt = item
        try:
            # API Call
            base64_img = self.call_gemini_api(prompt)
            
            if base64_img and self.is_running:
                save_path = os.path.join(self.target_dir, f"{num}.jpg")
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(base64_img))
                return (True, f"{num}번 저장 완료", item)
            else:
                return (False, f"{num}번 생성 실패 (API 응답 없음)", item)
        except Exception as e:
            return (False, f"{num}번 에러: {e}", item)

    def run(self):
        import concurrent.futures
        start_timestamp = time.time()
        success_count = 0
        failed_items = []
        total = len(self.items)
        
        # 병렬 스레드 수 (Rate Limit 고려하여 4개 정도로 설정)
        MAX_WORKERS = 4
        self.log_signal.emit(f"🚀 Gemini API 비동기 이미지 생성 시작 (병렬 {MAX_WORKERS}) - 총 {total}장")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_item = {executor.submit(self.process_item, item): item for item in self.items}
            
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_item):
                if not self.is_running:
                    # 중지 시 남은 작업 취소 시도
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                item = future_to_item[future]
                completed_count += 1
                
                try:
                    success, msg, _ = future.result()
                    if success:
                        success_count += 1
                        self.log_signal.emit(f"  ✅ {msg}")
                    else:
                        failed_items.append(item)
                        self.log_signal.emit(f"  ❌ {msg}")
                except Exception as e:
                    failed_items.append(item)
                    self.log_signal.emit(f"  ❌ 처리 중 예외: {e}")
                
                self.progress.emit(f"진행: {completed_count}/{total}")

        if not self.is_running:
             self.log_signal.emit("🛑 작업이 중지되었습니다.")

        elapsed_time = time.time() - start_timestamp
        result_msg = f"완료 (성공 {success_count} / 실패 {len(failed_items)})"
        self.finished.emit(result_msg, elapsed_time)

    def stop(self):
        self.is_running = False

    def call_gemini_api(self, prompt):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        full_text = prompt + " . Ensure the Korean text is rendered clearly. Aspect ratio is 16:9."
        
        payload = {
            "contents": [{
                "parts": [{"text": full_text}]
            }],
            "generationConfig": {
                "image_config": {
                    "aspect_ratio": "16:9"
                }
            }
        }
        
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                self.log_signal.emit(f"   ⚠️ API Error {response.status_code}: {response.text}")
                return None
                
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates: 
                self.log_signal.emit("   ⚠️ No candidates returned")
                return None
            
            candidate = candidates[0]
            if candidate.get("finishReason") == "SAFETY":
                 self.log_signal.emit(f"   ⚠️ Safety Check Blocked")
                 return None
                 
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData")
                if inline_data:
                    return inline_data.get("data") # Base64 String
            
            return None
            
        except Exception as e:
            self.log_signal.emit(f"   ⚠️ Request Exception: {e}")
            return None

class GrokMultiTabWorker(QThread):
    progress = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, input_dir, driver):
        super().__init__()
        self.input_dir = input_dir
        self.driver = driver
        self.target_dir = input_dir # 다운로드도 같은 폴더에
        self.is_running = True

    def run(self):
        start_timestamp = time.time()
        try:
            # 1. 대상 이미지 파일 찾기 (1.jpg, 2.jpg ...)
            files = []
            if os.path.exists(self.input_dir):
                for f in os.listdir(self.input_dir):
                    if f.lower().endswith(('.jpg', '.png', '.jpeg')):
                        # 숫자로 된 파일만 대상
                        name_no_ext = os.path.splitext(f)[0]
                        if name_no_ext.isdigit():
                            files.append(os.path.join(self.input_dir, f))
            
            # 숫자 기준 정렬
            files.sort(key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
            
            if not files:
                self.error.emit("❌ 해당 폴더에 숫자 이름의 이미지(1.jpg 등)가 없습니다.")
                return

            self.log_signal.emit(f"📂 총 {len(files)}개의 이미지를 발견했습니다.")

            # 2. 탭 확인 (2개 사용)
            while len(self.driver.window_handles) < 2:
                 self.driver.execute_script("window.open('https://grok.com/imagine');")
                 time.sleep(1)
            
            tabs = self.driver.window_handles[:2]
            
            success_count = 0
            final_failed_items = []
            
            # 작업 대상 목록 초기화
            remaining_files = files[:] 
            
            self.is_running = True
            
            # [Added] 2단계 재시도 로직: 1차 생성 -> 실패분 모아서 최종 재시도
            for pass_num in [1, 2]:
                if not remaining_files or not self.is_running:
                    break
                
                phase_name = "1차" if pass_num == 1 else "최종 재시도"
                self.log_signal.emit(f"\n🚀 {phase_name} 작업을 시작합니다. (대상: {len(remaining_files)}개)")
                
                if pass_num == 2:
                    # 탭 새로고침하여 깨끗한 상태로 시작
                    for tab in tabs:
                        try:
                            self.driver.switch_to.window(tab)
                            self.driver.get('https://grok.com/imagine')
                        except: pass
                    time.sleep(5)

                current_pass_files = remaining_files[:]
                remaining_files = [] # 이번 회차 실패분을 담기 위해 초기화
                
                total = len(current_pass_files)
                processed_count = 0
                file_idx = 0
                tab_status = {t: None for t in tabs}
                tab_old_videos = {t: [] for t in tabs}
                
                while processed_count < total and self.is_running:
                    for tab in tabs:
                        if not self.is_running: break
                        
                        try:
                            self.driver.switch_to.window(tab)
                        except:
                            continue # 탭이 닫혔을 경우

                        # 1) 작업 할당
                        if tab_status[tab] is None and file_idx < total:
                            current_file = current_pass_files[file_idx]
                            fname = os.path.basename(current_file)
                            
                            self.log_signal.emit(f"▶ [{phase_name}][탭 {tabs.index(tab)+1}] {fname} 업로드 시작...")
                            
                            # 업로드 전 기존 영상 목록 저장
                            tab_old_videos[tab] = self.driver.execute_script("return Array.from(document.querySelectorAll('video')).map(v => v.src);")
                            
                            # 업로드 로직
                            if self.upload_image(current_file):
                                tab_status[tab] = {
                                    "file": current_file, 
                                    "start_time": time.time(),
                                    "step": "generating"
                                }
                                file_idx += 1
                                self.progress.emit(f"진행({phase_name}): {processed_count}/{total}")
                            else:
                                self.log_signal.emit(f"❌ {fname} 업로드 실패")
                                if pass_num == 1:
                                    remaining_files.append(current_file)
                                else:
                                    final_failed_items.append(current_file)
                                processed_count += 1
                                file_idx += 1

                        # 2) 진행 상태 확인 및 다운로드
                        elif tab_status[tab] is not None:
                            curr = tab_status[tab]
                            file_path = curr['file']
                            fname = os.path.basename(file_path)
                            
                            # 타임아웃 체크 (5분)
                            if time.time() - curr['start_time'] > 300:
                                self.log_signal.emit(f"❌ {fname} 시간 초과 (5분)")
                                if pass_num == 1:
                                    remaining_files.append(file_path)
                                else:
                                    final_failed_items.append(file_path)
                                    
                                tab_status[tab] = None
                                processed_count += 1
                                self.driver.refresh()
                                time.sleep(2)
                                continue

                            # 에러 메시지 확인 ("Server failed to respond")
                            if self.check_error_on_page():
                                 self.log_signal.emit(f"⚠️ {fname} 서버 오류 감지 -> 30초 대기 후 재시도")
                                 # 즉시 동일 회차 내에서 재시도 (항목을 다시 뒤로 보냄)
                                 current_pass_files.insert(file_idx, file_path)
                                 total += 1
                                 
                                 tab_status[tab] = None
                                 time.sleep(30)
                                 self.driver.refresh()
                                 time.sleep(5)
                                 continue

                            # 다운로드 확인
                            video_url = self.check_video_generated(tab_old_videos[tab])
                            if video_url:
                                # 다운로드 수행
                                save_name = os.path.splitext(fname)[0] + ".mp4"
                                save_path = os.path.join(self.target_dir, save_name)
                                
                                self.log_signal.emit(f"📥 {fname} 영상 발견! 다운로드 중...")
                                if self.download_video(video_url, save_path):
                                    self.log_signal.emit(f"✅ {save_name} 저장 완료")
                                    success_count += 1
                                else:
                                    self.log_signal.emit(f"❌ {save_name} 다운로드 실패")
                                    if pass_num == 1:
                                        remaining_files.append(file_path)
                                    else:
                                        final_failed_items.append(file_path)
                                
                                # 작업 완료 -> 초기화
                                self.driver.get('https://grok.com/imagine')
                                time.sleep(3)
                                
                                tab_status[tab] = None
                                processed_count += 1
                    
                    time.sleep(1)

            if not self.is_running:
                 self.log_signal.emit("🛑 Grok 작업이 중지되었습니다.")

            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {success_count} / 최종 실패 {len(final_failed_items)})"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.is_running = False

    def upload_image(self, file_path):
        """grok의 파일 인풋을 찾아 업로드"""
        try:
            # 0. 혹시 열려있을지 모르는 모달 닫기
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1.5) # 대기 시간 상향

            # 1. Input File 찾기 (여러 개 있을 경우 대비)
            file_input = None
            for _ in range(3): # 최대 3초 대기하며 찾기
                inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if inputs:
                    # 가장 마지막에 생성된 input이 현재 활성 상태일 가능성이 높음
                    file_input = inputs[-1]
                    break
                time.sleep(1)

            if not file_input:
                self.log_signal.emit("  ⚠️ input[type='file'] 요소를 찾을 수 없습니다.")
                return False
            
            # 파일 경로 전송
            file_input.send_keys(file_path)
            self.log_signal.emit(f"  ⏳ 이미지 업로드 처리 대기: {os.path.basename(file_path)}")
            time.sleep(6) # 업로드 처리 대기 (약간 상향)
            
            # 2. 텍스트 입력의 필요성 (이미지만으로는 버튼 활성화 안될 수도 있음)
            try:
                ta = self.driver.find_element(By.TAG_NAME, 'textarea')
                if ta:
                    ta.click()
                    time.sleep(0.5)
                    # 트리거 텍스트 입력 (아무것도 없으면 전송 안될 수 있음)
                    ta.send_keys("Animate this") 
                    time.sleep(1)
            except:
                pass
            
            # 3. 전송 버튼 클릭 시도
            # 전략 A: 엔터키 (가장 흔함)
            # ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            # time.sleep(1)
            
            # 전략 B: JS로 전송 버튼 찾아서 클릭 (화살표 모양, Send, Generate 등)
            script_click = """
            try {
                var target = null;
                
                // 0. (Best) aria-label="동영상 만들기" 직접 탐색
                var byLabel = document.querySelector('button[aria-label="동영상 만들기"]');
                if (byLabel && !byLabel.disabled) {
                    target = byLabel;
                    console.log("Found by aria-label exact match");
                }
                
                // 0-1. text content "동영상 만들기" check
                if (!target) {
                    var buttons = Array.from(document.querySelectorAll('button'));
                    target = buttons.find(b => {
                        return !b.disabled && (b.innerText || '').includes('동영상 만들기');
                    });
                }

                if (!target) {
                    var buttons = Array.from(document.querySelectorAll('button'));
                    target = buttons.find(b => {
                        var label = (b.getAttribute('aria-label') || '').toLowerCase();
                        return !b.disabled && (label.includes('동영상 만들기') || label.includes('video')); 
                    });
                }
                
                // 1. 기존 aria-label 탐색 (Send/Generate) - Fallback
                if (!target) {
                    var buttons = Array.from(document.querySelectorAll('button'));
                    target = buttons.find(b => {
                        var label = (b.getAttribute('aria-label') || '').toLowerCase();
                        return !b.disabled && (label.includes('send') || label.includes('generate') || label.includes('submit'));
                    });
                }
                
                // 2. TextArea 근처 탐색
                if (!target) {
                    var ta = document.querySelector('textarea');
                    if (ta) {
                        var sibling = ta.nextElementSibling;
                        while(sibling) {
                            if (sibling.tagName === 'BUTTON' && !sibling.disabled) {
                                target = sibling;
                                break;
                            }
                            var innerBtn = sibling.querySelector('button');
                            if (innerBtn && !innerBtn.disabled) {
                                target = innerBtn;
                                break;
                            }
                            sibling = sibling.nextElementSibling;
                        }
                        if (!target && ta.parentElement) {
                            var pBtns = ta.parentElement.querySelectorAll('button');
                            if (pBtns.length > 0) {
                                target = pBtns[pBtns.length - 1];
                            }
                        }
                    }
                }
                
                // 3. SVG Path 탐색
                if (!target) {
                    var allSvgs = document.querySelectorAll('svg');
                    for(var i=0; i<allSvgs.length; i++) {
                        var svg = allSvgs[i];
                        var path = svg.querySelector('path[d^="M12 4C14.4853 4"]'); 
                        if (path) {
                             var btn = svg.closest('button');
                             if (btn && !btn.disabled) {
                                 target = btn;
                                 console.log("Found submit button via MakeVideo SVG Path!");
                                 break;
                             }
                        }
                    }
                }

                if (target) {
                    target.click();
                    return true;
                }
                return false;
            } catch(e) {
                console.error(e);
                return false;
            }
            """
            clicked = self.driver.execute_script(script_click)
            if clicked:
                self.log_signal.emit("  🖱️ '동영상 만들기' 버튼 클릭 성공")
            else:
                self.log_signal.emit("  ⚠️ 전송 버튼을 찾지 못해 엔터키만 입력했습니다.")
                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                
            return True
        except Exception as e:
            self.log_signal.emit(f"  ⚠️ 업로드 예외: {e}")
            return False

    def check_video_generated(self, old_urls):
        """비디오 태그가 생겼는지 확인하고, 이전과 다른 src만 반환"""
        try:
            # 비디오 태그 검색
            videos = self.driver.find_elements(By.TAG_NAME, "video")
            for v in videos:
                src = v.get_attribute("src")
                if src and src.startswith("http") and not "blob:" in src: 
                    # 이전 목록에 없는 새로운 URL인지 확인
                    if src not in old_urls:
                        return src
                # Blob URL인 경우
                if src and "blob:" in src:
                    if src not in old_urls:
                        return src
            return None
        except:
            return None
            
    def download_video(self, url, save_path):
        try:
            if url.startswith("blob:"):
                # Blob URL 다운로드 - Selenium Async Script 활용
                self.log_signal.emit(f"  ℹ️ Blob URL 감지: {url[:30]}...")
                
                # Base64로 변환하여 Python으로 가져오는 스크립트
                script = """
                    var blobUrl = arguments[0];
                    var callback = arguments[1];
                    
                    fetch(blobUrl)
                        .then(response => response.blob())
                        .then(blob => {
                            var reader = new FileReader();
                            reader.readAsDataURL(blob); 
                            reader.onloadend = function() {
                                var base64data = reader.result;                
                                callback(base64data);
                            }
                        })
                        .catch(error => {
                            console.error(error);
                            callback(null);
                        });
                """
                
                # 비동기 스크립트 실행 (타임아웃 설정)
                self.driver.set_script_timeout(60) # 60초 대기
                result = self.driver.execute_async_script(script, url)
                
                if result:
                    # header 제거 ("data:video/mp4;base64,...")
                    try:
                        header, encoded = result.split(",", 1)
                        data = base64.b64decode(encoded)
                        
                        with open(save_path, "wb") as f:
                            f.write(data)
                            
                        self.log_signal.emit(f"  ✅ Blob 비디오 저장 완료: {os.path.basename(save_path)}")
                        return True
                    except Exception as e:
                        self.log_signal.emit(f"  ⚠️ Base64 디코딩 실패: {e}")
                        return False
                else:
                    self.log_signal.emit("  ⚠️ Blob 데이터 가져오기 실패 (Result is None)")
                    return False

            else:
                # 일반 HTTP URL
                # User Request: Selenium fetch 실패하므로 시도하지 말고 바로 버튼 클릭으로 진행
                # self.log_signal.emit(f"  ℹ️ HTTP URL (Selenium 다운로드 시도): {url[:30]}...")
                self.log_signal.emit("  ℹ️ HTTP URL 감지 -> '다운로드' 버튼 클릭으로 진행")
                
                # --- Fallback: Click Download Button ---
                
                # --- Fallback: Click Download Button ---
                self.log_signal.emit("  ⚠️ 직접 다운로드 실패 -> '다운로드' 버튼 클릭 시도 (최후의 수단)")
                
                current_handle = self.driver.current_window_handle
                old_handles = self.driver.window_handles
                
                try:
                    # div 안에 있는 버튼 등 구조 고려
                    # User provided: <button aria-label="다운로드">
                    dl_btn = self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="다운로드"]')
                    if not dl_btn:
                        dl_btn = self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Download"]')
                    
                    if dl_btn:
                        dl_btn[0].click()
                        time.sleep(3) # 새 탭 열림 대기
                        
                        new_handles = self.driver.window_handles
                        if len(new_handles) > len(old_handles):
                            # 새 탭이 열린 경우 (동영상 재생 화면)
                            self.log_signal.emit("  ℹ️ 새 탭 감지 -> 새 탭에서 다운로드 시도")
                            new_tab = [h for h in new_handles if h not in old_handles][0]
                            self.driver.switch_to.window(new_tab)
                            time.sleep(1) # 페이지 로딩 대기
                            
                            video_url_new_tab = self.driver.current_url
                            
                            # 새 탭에서 Fetch 시도 (Local Context)
                            script_new_tab = """
                                var url = arguments[0];
                                var callback = arguments[1];
                                fetch(url).then(res => res.blob()).then(blob => {
                                    var reader = new FileReader();
                                    reader.readAsDataURL(blob);
                                    reader.onloadend = () => callback(reader.result);
                                }).catch(e => callback(null));
                            """
                            self.driver.set_script_timeout(120)
                            result_new = self.driver.execute_async_script(script_new_tab, video_url_new_tab)
                            
                            download_success = False
                            if result_new:
                                try:
                                    header, encoded = result_new.split(",", 1)
                                    data = base64.b64decode(encoded)
                                    with open(save_path, "wb") as f:
                                        f.write(data)
                                    self.log_signal.emit(f"  ✅ 새 탭에서 Blob 비디오 저장 완료!")
                                    download_success = True
                                except Exception as e:
                                    self.log_signal.emit(f"  ❌ 새 탭 다운로드 처리 실패: {e}")
                            else:
                                self.log_signal.emit("  ❌ 새 탭에서도 다운로드 실패")
                                
                            # 탭 닫기 및 복귀
                            self.driver.close()
                            self.driver.switch_to.window(current_handle)
                            return download_success
                            
                        else:
                            self.log_signal.emit(f"  ✅ '다운로드' 버튼 클릭 완료. (파일 이동 시도)")
                            
                            # 1. 다운로드 폴더 설정 (User specified: D:\downloads)
                            # 경로가 존재하는지 확인
                            download_dirs = [r"D:\downloads", r"D:\Downloads", os.path.join(os.path.expanduser("~"), "Downloads")]
                            target_download_dir = None
                            
                            for d in download_dirs:
                                if os.path.exists(d):
                                    target_download_dir = d
                                    break
                            
                            if not target_download_dir:
                                target_download_dir = download_dirs[0] # Default to D:\downloads even if checked fail?
                                # Just use D:\downloads as user said
                                target_download_dir = r"D:\downloads"

                            # 2. 가장 최근에 생성된 파일 모니터링
                            target_filename = os.path.basename(save_path)
                            self.log_signal.emit(f"  📂 다운로드 폴더 감시: {target_download_dir}")
                            
                            found_file = None
                            for _ in range(20): # 20초 대기
                                time.sleep(1)
                                try:
                                    if not os.path.exists(target_download_dir): continue
                                    
                                    files = [os.path.join(target_download_dir, f) for f in os.listdir(target_download_dir) if f.endswith(".mp4")]
                                    if not files: continue
                                    latest_file = max(files, key=os.path.getmtime)
                                    
                                    # 최근 1분 이내 생성된 파일
                                    if time.time() - os.path.getmtime(latest_file) < 60:
                                        if os.path.getsize(latest_file) > 1000:
                                            found_file = latest_file
                                            break
                                except:
                                    pass
                                    
                            if found_file:
                                try:
                                    import shutil
                                    # 대상 파일이 이미 존재하면 삭제
                                    if os.path.exists(save_path):
                                        os.remove(save_path)
                                        
                                    shutil.move(found_file, save_path)
                                    self.log_signal.emit(f"  📦 파일 이동 완료: {os.path.basename(found_file)} -> {target_filename}")
                                    return True
                                except Exception as mv_err:
                                     self.log_signal.emit(f"  ⚠️ 파일 이동 실패: {mv_err}")
                                     return True 
                            else:
                                 self.log_signal.emit("  ⚠️ 다운로드된 파일을 찾을 수 없습니다. (폴더 경로 확인 필요)")
                                 return True 

                            return True
                except Exception as ex:
                    self.log_signal.emit(f"  ❌ 버튼 클릭 중 오류: {ex}")
                    # 혹시나 탭 이동 후 에러나면 복귀 시도
                    if self.driver.current_window_handle != current_handle:
                         try:
                             self.driver.close()
                             self.driver.switch_to.window(current_handle)
                         except:
                             pass
                    
                return False
        except Exception as e:
            self.log_signal.emit(f"  ⚠️ 다운로드 중 에러: {e}")
            return False
    def check_error_on_page(self):
        """페이지 내 에러 메시지 감지"""
        try:
            # 1. 텍스트 "Server failed" or "Error" or "Something went wrong"
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = body.text
            
            error_keywords = [
                "Server failed to respond", 
                "Something went wrong", 
                "Internal server error", 
                "Error code 500", 
                "network error",
                "일시적인 오류"
            ]
            
            if any(k in body_text for k in error_keywords):
                return True
            
            # 2. 특정 에러 요소 (Toast, Alert)
            # 보통 role='alert' 또는 class에 error 포함
            alerts = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Server failed')]")
            if alerts:
                return True
            
            # 3. 500 페이지 타이틀 확인
            if "500" in self.driver.title or "Error" in self.driver.title:
                return True
                
            return False
        except:
            return False
class WhiskMultiTabWorker(GenSparkMultiTabWorker):
    def run(self):
        start_timestamp = time.time()
        try:
            if len(self.driver.window_handles) < 2:
                self.error.emit("❌ 오류: 브라우저 탭이 2개 미만입니다. Whisk 탭을 2개 이상 준비해주세요.")
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
                        self.log_signal.emit(f"▶ [탭 {tabs.index(tab)+1}] {num}번 생성 시작 (Whisk)...")
                        
                        tab_old_srcs[tab] = self.driver.execute_script("return Array.from(document.querySelectorAll('img')).map(img => img.src);")
                        
                        # Whisk는 구글 랩스 UI이므로 입력창을 신중히 찾음
                        try:
                            # 1. textarea 시도
                            input_box = wait.until(EC.element_to_be_clickable((By.TAG_NAME, "textarea")))
                        except:
                            # 2. contenteditable 시도
                            input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[contenteditable="true"]')))
                            
                        input_box.click()
                        time.sleep(0.5)
                        
                        # 내용 지우기 및 입력
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE).perform()
                        
                        input_box.send_keys(prompt.strip())
                        time.sleep(1)
                        
                        # 엔터 입력 (혹은 전송 버튼 클릭)
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
                        
                        elif time.time() - tab_status[tab]["start_time"] > 180:
                            self.log_signal.emit(f"  ❌ [탭 {tabs.index(tab)+1}] {target_num}번 타임아웃")
                            failed_items.append(tab_status[tab]["item"])
                            tab_status[tab] = None
                            processed_count += 1
                
                time.sleep(1)

            elapsed_time = time.time() - start_timestamp
            result_msg = f"완료 (성공 {total - len(failed_items)} / 실패 {len(failed_items)})" if self.is_running else "중지됨"
            self.finished.emit(result_msg, elapsed_time)

        except Exception as e:
            self.error.emit(str(e))
