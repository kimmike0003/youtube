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
