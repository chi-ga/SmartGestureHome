import sys
import cv2
import numpy as np
import datetime
import time
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QTextEdit, 
                             QVBoxLayout, QHBoxLayout, QGridLayout, QFrame)
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer
import mediapipe as mp
import serial
import serial.tools.list_ports

# 导入逻辑库
try:
    from hand_gesture_logic import get_gesture as detect_gesture, GestureSmoother
except ImportError:
    print("Warning: hand_gesture_logic.py not found or import failed.")
    sys.exit(1)

# --- Modern Tech Theme Stylesheet ---
Stylesheet = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 10pt;
}

/* Header */
QFrame#HeaderFrame {
    background-color: #1e1e2e;
    border-bottom: 1px solid #45475a;
}
QLabel#HeaderTitle {
    color: #ffffff;
    font-size: 18pt;
    font-weight: bold;
}
QLabel#HeaderTime {
    color: #a6adc8;
    font-size: 12pt;
    font-family: "Consolas", monospace;
}

/* Common Card Styles */
QFrame#ContentCard {
    background-color: #313244;
    border-radius: 12px;
    border: 1px solid #45475a;
}

/* Video Section */
QLabel#SectionTitle {
    color: #89b4fa;
    font-weight: bold;
    font-size: 11pt;
    padding-bottom: 5px;
}
QLabel#VideoDisplay {
    border: 2px solid #89b4fa;
    border-radius: 8px;
    background-color: #000000;
}

/* Device Cards (Base Style) */
QFrame.DeviceCard {
    background-color: #313244;
    border-radius: 12px;
    border: 1px solid #45475a;
}
QLabel.DeviceIcon {
    font-size: 36pt;
    background: transparent;
}
QLabel.DeviceName {
    font-size: 12pt;
    font-weight: bold;
    color: #cdd6f4;
}
QLabel.StatusBadge {
    background-color: #45475a;
    color: #bac2de;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 9pt;
    font-weight: bold;
}

/* Terminal Log */
QTextEdit#SystemLog {
    background-color: #11111b;
    color: #a6e3a1;
    font-family: "Consolas", monospace;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 10px;
}
"""

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    gesture_signal = pyqtSignal(str)
    fps_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        # 初始化摄像头
        cap = cv2.VideoCapture(0)
        
        # 初始化 MediaPipe Hands
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        mp_draw = mp.solutions.drawing_utils

        # 实例化去抖动类
        smoother = GestureSmoother()
        
        prev_time = 0

        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                # 计算 FPS
                curr_time = time.time()
                fps = 1 / (curr_time - prev_time) if prev_time != 0 else 0
                prev_time = curr_time
                self.fps_signal.emit(f"FPS: {int(fps)}")

                # 镜像翻转并转换颜色
                cv_img = cv2.flip(cv_img, 1)
                img_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                
                # MediaPipe 处理
                results = hands.process(img_rgb)
                
                stable_gesture = "None"
                
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        # 绘制骨架
                        mp_draw.draw_landmarks(cv_img, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                        
                        # 获取原始手势
                        raw_gesture = detect_gesture(hand_landmarks.landmark, cv_img.shape)
                        
                        # 获取稳定手势
                        stable_gesture = smoother.update(raw_gesture)
                else:
                    # 未检测到手时，也需要更新平滑器状态
                    stable_gesture = smoother.update("None")

                # 发送信号
                self.change_pixmap_signal.emit(cv_img)
                self.gesture_signal.emit(stable_gesture)
            else:
                self.msleep(10)

        # 释放资源
        cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()


class SmartHomeSystem(QWidget):
    def __init__(self):
        super().__init__()
        self.last_gesture = "None" 
        
        # 自动截图相关变量初始化
        self.auto_save_mode = False
        self.last_saved_gesture = "None"
        self.last_save_time = 0
        if not os.path.exists("images_data"):
            os.makedirs("images_data")
        
        # 存储 UI 引用
        self.device_cards = {}   # 存储 QFrame 卡片
        self.device_badges = {}  # 存储状态 Label

        # 串口通信初始化变量
        self.ser = None
        
        # 手势与串口指令映射
        self.serial_map = {
            "Palm Open":  b'A',
            "Fist":       b'B',
            "Victory":    b'C',
            "One Finger": b'D',
            "OK":         b'E',
            "Thumbs Up":  b'F',
            "Three Fingers": b'G',
            "Four Fingers": b'H',
            "Rock":       b'I',
            "Pinky":      b'J',
            "Call Me":    b'K',
            "Middle Finger": b'L'
        }

        self.initUI()
        
        # UI 初始化完成后再尝试连接串口，以便日志可以正常输出
        self.init_serial()
        
        # 应用样式表
        self.setStyleSheet(Stylesheet)
        
        # 定时器：更新时间
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000) # 每秒更新一次
        
        # 创建并启动视频线程
        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.gesture_signal.connect(self.handle_gesture)
        self.thread.fps_signal.connect(self.update_fps)
        self.thread.start()

    def initUI(self):
        """
        初始化用户界面布局和组件，包括顶部导航、视频监控区域及设备仪表盘。
        """
        self.setWindowTitle('智能家居手势控制系统 - Lovelace Edition')
        self.resize(1200, 800)

        # 根布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)

        # === A. 顶部导航栏 (Header) ===
        header_frame = QFrame()
        header_frame.setObjectName("HeaderFrame")
        header_frame.setFixedHeight(80)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(30, 0, 30, 0)
        
        # 左侧标题
        title_label = QLabel("🏠 SMART HOME CONTROL")
        title_label.setObjectName("HeaderTitle")
        
        # 右侧时间与 FPS
        self.header_time_label = QLabel("Loading...")
        self.header_time_label.setObjectName("HeaderTime")
        self.header_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.header_time_label)
        
        main_layout.addWidget(header_frame)

        # === 主要内容区域 ===
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(30)
        main_layout.addLayout(content_layout)

        # === B. 左侧：视频监控卡片 ===
        video_card = QFrame()
        video_card.setObjectName("ContentCard")
        video_layout = QVBoxLayout(video_card)
        video_layout.setContentsMargins(20, 20, 20, 20)
        
        video_title = QLabel("📹 实时监控 (LIVE FEED)")
        video_title.setObjectName("SectionTitle")
        
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self.video_label.setObjectName("VideoDisplay")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("Waiting for Camera...")
        
        video_layout.addWidget(video_title)
        video_layout.addWidget(self.video_label)
        video_layout.addStretch()
        
        content_layout.addWidget(video_card)

        # === C. 右侧：仪表盘 (Dashboard) ===
        dashboard_layout = QVBoxLayout()
        dashboard_layout.setSpacing(30)
        content_layout.addLayout(dashboard_layout)

        # 1. 上方 - 设备控制网格 (Device Grid)
        device_grid = QGridLayout()
        device_grid.setSpacing(20)

        # 设备数据
        devices = [
            ("light", "灯光", "💡", "OFF"),
            ("curtain", "窗帘", "🪟", "CLOSE"),
            ("fan", "风扇", "🌀", "OFF"),
            ("tv", "电视", "📺", "OFF"),
            ("ac", "空调", "❄️", "OFF"),
            ("audio", "音响", "🔊", "OFF")
        ]

        # 手势提示映射
        gesture_hints = {
            "light": "✋ / ✊",
            "curtain": "✌️ / ☝️",
            "fan": "👌 / 👍",
            "ac": "🤘 / pinky",
            "audio": "🤙 / 🖕",
            "tv": "3 / 4 fingers"
        }
        
        # 默认关闭样式
        initial_card_style = """
            QFrame {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 12px;
            }
        """
        initial_badge_style = """
            QLabel {
                background-color: #313244;
                color: #f38ba8; /* Danger Red */
                border-radius: 10px;
                font-weight: bold;
                padding: 4px 12px;
                border: 1px solid #f38ba8;
            }
        """

        # 动态创建卡片
        for idx, (key, name, icon, initial_status) in enumerate(devices):
            card = QFrame()
            card.setProperty("class", "DeviceCard") # 用于 QSS 选择器
            card.setObjectName(f"Card_{key}") # 唯一 ID
            
            # 应用初始关闭样式
            card.setStyleSheet(initial_card_style)
            
            card_layout = QVBoxLayout(card)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setSpacing(10)
            
            # 图标
            icon_label = QLabel(icon)
            icon_label.setProperty("class", "DeviceIcon")
            icon_label.setAlignment(Qt.AlignCenter)
            
            # 名称
            name_label = QLabel(name)
            name_label.setProperty("class", "DeviceName")
            name_label.setAlignment(Qt.AlignCenter)
            
            # 状态 Badge
            badge_label = QLabel(initial_status)
            badge_label.setProperty("class", "StatusBadge")
            badge_label.setAlignment(Qt.AlignCenter)
            badge_label.setFixedSize(80, 30)
            # 应用初始关闭样式
            badge_label.setStyleSheet(initial_badge_style)
            
            card_layout.addWidget(icon_label)
            card_layout.addWidget(name_label)
            card_layout.addWidget(badge_label)
            
            # 手势提示标签
            hint_label = QLabel(gesture_hints.get(key, "N/A"))
            hint_label.setAlignment(Qt.AlignCenter)
            hint_label.setFont(QFont("Segoe UI", 10))
            hint_label.setStyleSheet("color: #a6adc8; font-family: \"Segoe UI Emoji\", \"Segoe UI\", sans-serif;")
            card_layout.addWidget(hint_label)
            
            row = idx // 3
            col = idx % 3
            device_grid.addWidget(card, row, col)
            
            # 存储引用
            self.device_cards[key] = card
            self.device_badges[key] = badge_label

        dashboard_layout.addLayout(device_grid)

        # 2. 下方 - 系统日志 (System Log)
        log_frame = QFrame()
        log_frame.setObjectName("ContentCard")
        log_layout = QVBoxLayout(log_frame)
        
        log_title = QLabel("💻 系统终端 (SYSTEM LOG)")
        log_title.setObjectName("SectionTitle")
        
        self.log_text = QTextEdit()
        self.log_text.setObjectName("SystemLog")
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("System initialized. Waiting for gestures...")
        
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_text)
        
        dashboard_layout.addWidget(log_frame, stretch=1)

        # 初始化时间
        self.update_time()

    def keyPressEvent(self, event):
        """监听键盘按键"""
        if event.key() == Qt.Key_S:
            self.auto_save_mode = not self.auto_save_mode
            status_msg = "ON" if self.auto_save_mode else "OFF"
            print(f"Auto Save Mode: {status_msg}")
            self.log_message(f"自动截图模式已切换: {status_msg}")

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """接收 OpenCV 图像并在 QLabel 上显示"""
        if self.auto_save_mode:
            cv2.putText(cv_img, "AUTO SAVE: ON", (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        qt_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = qt_img.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(qt_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        p = convert_to_Qt_format.scaled(640, 480, Qt.KeepAspectRatio)
        self.video_label.setPixmap(QPixmap.fromImage(p))

    @pyqtSlot(str)
    def update_fps(self, fps_str):
        # 将 FPS 更新到 Header 的时间标签中（合并显示）
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.header_time_label.setText(f"{fps_str} | {current_time}")

    def update_time(self):
        # 由 update_fps 统一驱动刷新，或者这里仅作备用
        # 但由于 VideoThread 频率较高，update_fps 会覆盖这里
        # 为了保证没有视频时时间也能走，还是保留逻辑，但只更新时间部分
        pass 

    @pyqtSlot(str)
    def handle_gesture(self, gesture_name):
        if gesture_name == "None":
            return

        if gesture_name != self.last_gesture:
            self.last_gesture = gesture_name
            self.log_message(f"识别到手势：{gesture_name}")
            
            # 发送串口指令
            if gesture_name in self.serial_map:
                self.send_serial_command(self.serial_map[gesture_name])

            self.update_device_status(gesture_name)

        if self.auto_save_mode and gesture_name != "Unknown":
            current_time = time.time()
            if (gesture_name != self.last_saved_gesture) or (current_time - self.last_save_time > 3):
                self.trigger_auto_save(gesture_name)
                self.last_saved_gesture = gesture_name
                self.last_save_time = current_time

    def trigger_auto_save(self, gesture_name):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"images_data/{timestamp}_{gesture_name}.jpg"
        
        screen = QApplication.primaryScreen()
        screenshot = self.grab()
        screenshot.save(filename, 'jpg')
        
        self.log_message(f"截图已保存: {filename}")

    def log_message(self, msg):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"> [{timestamp}] {msg}")
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def update_device_status(self, gesture):
        """
        根据手势动态改变卡片样式
        """
        # 动作映射: (DeviceKey, StatusText, IsActive)
        actions = {
            "Palm Open":  ("light", "ON", True),
            "Fist":       ("light", "OFF", False),
            "Victory":    ("curtain", "OPEN", True),
            "One Finger": ("curtain", "CLOSE", False),
            "OK":         ("fan", "ON", True),
            "Thumbs Up":  ("fan", "OFF", False),
            "Three Fingers": ("tv", "ON", True),
            "Four Fingers": ("tv", "OFF", False),
            "Rock":       ("ac", "ON", True),
            "Pinky":      ("ac", "OFF", False),
            "Call Me":    ("audio", "ON", True),
            "Middle Finger": ("audio", "OFF", False)
        }

        if gesture not in actions:
            return

        device_key, status_text, is_active = actions[gesture]
        
        if device_key in self.device_cards:
            card = self.device_cards[device_key]
            badge = self.device_badges[device_key]
            
            # 更新文本
            badge.setText(status_text)
            
            # 动态样式生成
            if is_active:
                # 开启状态样式 (Success / Blue Theme)
                # 使用 replace 确保 ID 选择器仍然生效 (尽管这里是直接对对象 setStyleSheet)
                # 注意：对单个部件 setStyleSheet 会覆盖全局 CSS 中针对该部件 ID/Class 的样式
                # 所以我们需要重写完整的样式，或者利用 Qt 的级联特性（较难控制），这里选择重写该组件样式。
                
                # 区分颜色：窗帘用蓝色，其他用绿色
                if device_key == "curtain":
                     # Blue Gradient
                    bg_gradient = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #313244, stop:1 #45475a)"
                    border_color = "#89b4fa" # Blue
                    badge_bg = "#89b4fa"
                    badge_color = "#1e1e2e"
                else:
                    # Green Gradient
                    bg_gradient = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #313244, stop:1 #45475a)"
                    border_color = "#a6e3a1" # Green
                    badge_bg = "#a6e3a1"
                    badge_color = "#1e1e2e"

                card_style = f"""
                    QFrame {{
                        background-color: {bg_gradient};
                        border: 2px solid {border_color};
                        border-radius: 12px;
                    }}
                """
                badge_style = f"""
                    QLabel {{
                        background-color: {badge_bg};
                        color: {badge_color};
                        border-radius: 10px;
                        font-weight: bold;
                        padding: 4px 12px;
                    }}
                """
            else:
                # 关闭状态样式 (Default / Dark)
                card_style = """
                    QFrame {
                        background-color: #181825;
                        border: 1px solid #313244;
                        border-radius: 12px;
                    }
                """
                badge_style = """
                    QLabel {
                        background-color: #313244;
                        color: #f38ba8; /* Danger Red */
                        border-radius: 10px;
                        font-weight: bold;
                        padding: 4px 12px;
                        border: 1px solid #f38ba8;
                    }
                """

            # 应用样式
            card.setStyleSheet(card_style)
            badge.setStyleSheet(badge_style)

    def init_serial(self):
        """初始化串口连接 - 自动搜索端口 (防复位修正版)"""
        port_list = list(serial.tools.list_ports.comports())
        target_port = None
        
        # 1. 自动寻找可能的端口
        if len(port_list) == 0:
            self.log_message("未发现串口设备，请检查 USB 连接！")
            return
            
        # 优先寻找包含 'USB', 'CH340', 'CP210' 字眼的端口
        for p in port_list:
            print(f"Found port: {p.device} - {p.description}")
            if "USB" in p.description or "CH340" in p.description or "CP210" in p.description:
                target_port = p.device
                break
        
        # 没找到特征端口则取第一个非 COM1
        if target_port is None:
            for p in port_list:
                if p.device != "COM1":
                    target_port = p.device
                    break

        if target_port is None:
            self.log_message("未找到合适的 ESP32 端口。")
            return

        # 2. 尝试连接 (关键修改：严格控制打开顺序)
        try:
            # 第一步：实例化但不打开 (port=None)
            self.ser = serial.Serial()
            self.ser.port = target_port      # 设置端口
            self.ser.baudrate = 9600
            self.ser.dsrdtr = False          # 禁用流控
            self.ser.rtscts = False
            self.ser.timeout = 1
            
            # 第二步：先设置 DTR/RTS 为低电平 (防止 ESP32 复位)
            self.ser.dtr = 0
            self.ser.rts = 0
            
            # 第三步：最后才打开串口
            self.ser.open()
            
            if self.ser.is_open:
                self.log_message(f"✅ 串口初始化成功: {target_port}")
                print(f"Connected to {target_port}")

        except Exception as e:
            self.log_message(f"❌ 串口连接失败 ({target_port}): {e}")
            self.ser = None

    def reconnect_serial(self):
        """断线重连"""
        self.log_message("尝试重新连接串口...")
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.init_serial()

    def send_serial_command(self, command_bytes):
        """发送串口指令，断线时自动重连"""
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(command_bytes)
                try:
                    cmd_str = command_bytes.decode('utf-8')
                except Exception:
                    cmd_str = str(command_bytes)
                self.log_message(f"串口发送: {cmd_str}")
            except Exception as e:
                self.log_message(f"串口发送异常: {e}，尝试重连...")
                self.reconnect_serial()
        else:
            self.reconnect_serial()

    def closeEvent(self, event):
        self.thread.stop()
        if self.ser and self.ser.is_open:
            try:
                # 退出前发送关闭指令: F(关风扇), B(关灯)
                self.ser.write(b'F')
                self.ser.flush()
                time.sleep(0.1)
                
                self.ser.write(b'B')
                self.ser.flush()
                time.sleep(0.1)
                
                # 关闭前再次确保 DTR/RTS 状态
                self.ser.dtr = False
                self.ser.rts = False
            except Exception as e:
                print(f"Error sending exit commands: {e}")
                
            self.ser.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SmartHomeSystem()
    window.show()
    sys.exit(app.exec_())
