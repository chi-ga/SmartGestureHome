import cv2
import mediapipe as mp
import math
from collections import deque, Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def put_chinese_text(img, text, position, color, font_size=40, stroke_width=2, stroke_fill=(0, 0, 0)):
    """
    使用 PIL 在 OpenCV 图像上绘制中文。
    支持描边以提高清晰度。
    """
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    
    # 尝试加载中文字体，如果失败则回退到默认字体
    try:
        font = ImageFont.truetype("msyh.ttc", font_size, encoding="utf-8")
    except IOError:
        try:
            font = ImageFont.truetype("simhei.ttf", font_size, encoding="utf-8")
        except IOError:
            # 如果找不到中文字体，使用默认字体
            font = ImageFont.load_default()
            
    # 绘制描边 (如果 stroke_width > 0)
    if stroke_width > 0:
        draw.text(position, text, font=font, fill=stroke_fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        
    draw.text(position, text, font=font, fill=color, stroke_width=0)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def calculate_distance(point1, point2):
    """
    计算两个关键点之间的欧氏距离（基于图像像素坐标）。
    """
    return math.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)

class GestureSmoother:
    """
    手势平滑器，用于减少识别抖动。
    维护一个固定长度的历史手势队列 (gesture_buffer)。
    只有当某个手势在最近 N 帧中出现的次数超过阈值时，才更新稳定结果。
    """
    def __init__(self, history_length=10, threshold=8):
        self.history = deque(maxlen=history_length)
        self.threshold = threshold
        self.stable_gesture = "None"

    def update(self, gesture):
        self.history.append(gesture)
        
        counts = Counter(self.history)
        if not counts:
            return self.stable_gesture
            
        most_common_gesture, count = counts.most_common(1)[0]
        
        # 只有当出现次数超过阈值 (> 8) 时，才更新最终判定
        if count > self.threshold:
            self.stable_gesture = most_common_gesture
            
        return self.stable_gesture

def is_finger_up(landmarks, finger_name, img_shape):
    """
    判断手指是否伸直。
    """
    h, w, _ = img_shape
    
    # 获取关键点坐标 (像素)
    def get_landmark_px(idx):
        return (int(landmarks[idx].x * w), int(landmarks[idx].y * h))
    
    wrist = get_landmark_px(0)
    
    # 关键点索引定义
    finger_indices = {
        'Thumb': [1, 2, 3, 4],    # CMC, MCP, IP, TIP
        'Index': [5, 6, 7, 8],    # MCP, PIP, DIP, TIP
        'Middle': [9, 10, 11, 12],
        'Ring': [13, 14, 15, 16],
        'Pinky': [17, 18, 19, 20]
    }
    
    indices = finger_indices[finger_name]
    tip = get_landmark_px(indices[3])
    
    if finger_name == 'Thumb':
        # 大拇指逻辑优化：
        # 为了区分 Fist (握拳) 和 Thumbs Up (点赞)，我们需要更严格的判断。
        # 1. 比较 指尖到食指MCP 的距离 vs IP到食指MCP 的距离 (原有逻辑)
        # 2. 比较 指尖到小指MCP 的距离 vs IP到小指MCP 的距离 (辅助逻辑：大拇指伸直时应远离手掌另一侧)
        
        ip = get_landmark_px(indices[2])
        index_mcp = get_landmark_px(5)
        pinky_mcp = get_landmark_px(17)
        
        dist_tip_index = calculate_distance(tip, index_mcp)
        dist_ip_index = calculate_distance(ip, index_mcp)
        
        dist_tip_pinky = calculate_distance(tip, pinky_mcp)
        dist_ip_pinky = calculate_distance(ip, pinky_mcp)
        
        # 综合判断：两个条件都满足，或者主条件显著满足
        # 握拳时，大拇指紧贴手指，tip 距离 index_mcp 较近。
        # 点赞时，大拇指翘起，tip 距离 index_mcp 较远。
        
        check1 = dist_tip_index > dist_ip_index
        check2 = dist_tip_pinky > dist_ip_pinky
        
        return check1 and check2
        
    else:
        # 其他四指：比较指尖和PIP关节与手腕的欧氏距离
        pip = get_landmark_px(indices[1])
        
        dist_tip_wrist = calculate_distance(tip, wrist)
        dist_pip_wrist = calculate_distance(pip, wrist)
        
        # 添加一个小的阈值缓冲，防止临界状态抖动
        return dist_tip_wrist > (dist_pip_wrist * 1.1)

def get_gesture(landmarks, img_shape):
    """
    根据手指状态识别手势。
    """
    h, w, _ = img_shape
    
    # 检测每根手指的状态
    fingers = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
    finger_states = {f: is_finger_up(landmarks, f, img_shape) for f in fingers}
    
    # 获取关键点坐标用于 OK 手势判断
    thumb_tip = (int(landmarks[4].x * w), int(landmarks[4].y * h))
    index_tip = (int(landmarks[8].x * w), int(landmarks[8].y * h))
    
    # 统计伸直的手指数量 (不含大拇指)
    # 用于辅助判断
    four_fingers = ['Index', 'Middle', 'Ring', 'Pinky']
    num_four_fingers_up = sum(1 for f in four_fingers if finger_states[f])
    
    thumb_up = finger_states['Thumb']
    
    # 1. OK 手势判断
    # 距离阈值放宽一点点，防止误判
    dist_thumb_index = calculate_distance(thumb_tip, index_tip)
    if dist_thumb_index < 40 and \
       finger_states['Middle'] and finger_states['Ring'] and finger_states['Pinky'] and \
       not finger_states['Index']: # OK手势中，食指通常是弯曲成圈的，但也可能被检测为伸直? 
       # 不，OK手势食指指尖碰到大拇指，通常意味着食指是弯曲的(指尖靠近手掌中心区域)。
       # 但 is_finger_up 比较的是距离手腕。
       # 当做OK手势时，食指指尖距离手腕 可能会比 PIP距离手腕近? 或者差不多。
       # 为了稳健，我们主要看 "其他三指伸直" + "接触"。
       # 忽略食指和大拇指的 is_finger_up 状态，只看距离。
        return "OK"
    
    # 修正 OK 逻辑：如果食指伸直，但距离很近，可能是捏合。
    # 如果三指伸直 + 食指大拇指接触 -> OK
    if dist_thumb_index < 40 and \
       finger_states['Middle'] and finger_states['Ring'] and finger_states['Pinky']:
       return "OK"

    # 2. Palm Open: 5根手指全部伸直
    if num_four_fingers_up == 4 and thumb_up:
        return "Palm Open"
        
    # 3. Fist: 5根手指全部弯曲
    # 严格要求：所有手指弯曲
    if num_four_fingers_up == 0 and not thumb_up:
        return "Fist"
    
    # 4. Thumbs Up: 仅大拇指伸直
    # 严格要求：大拇指伸直 + 其他4指弯曲
    if thumb_up and num_four_fingers_up == 0:
        return "Thumbs Up"
        
    # 5. Victory: 食指、中指伸直，其余2指弯曲 (无名指、小指)
    # 忽略大拇指
    if finger_states['Index'] and finger_states['Middle'] and \
       not finger_states['Ring'] and not finger_states['Pinky']:
        return "Victory"
        
    # 6. One Finger: 仅食指伸直，其余3指弯曲 (中指、无名指、小指)
    # 忽略大拇指
    if finger_states['Index'] and \
       not finger_states['Middle'] and not finger_states['Ring'] and not finger_states['Pinky']:
        return "One Finger"
        
    # 7. Three Fingers: 仅食指、中指、无名指伸直
    if not thumb_up and finger_states['Index'] and finger_states['Middle'] and finger_states['Ring'] and not finger_states['Pinky']:
        return "Three Fingers"

    # 8. Four Fingers: 除拇指外，其余 4 指均伸直
    if not thumb_up and finger_states['Index'] and finger_states['Middle'] and finger_states['Ring'] and finger_states['Pinky']:
        return "Four Fingers"

    # 9. Rock: 仅拇指、食指、小指伸直
    if thumb_up and finger_states['Index'] and not finger_states['Middle'] and not finger_states['Ring'] and finger_states['Pinky']:
        return "Rock"

    # 10. Pinky: 仅小指伸直
    if not thumb_up and not finger_states['Index'] and not finger_states['Middle'] and not finger_states['Ring'] and finger_states['Pinky']:
        return "Pinky"

    # 11. Call Me: 仅拇指、小指伸直
    if thumb_up and not finger_states['Index'] and not finger_states['Middle'] and not finger_states['Ring'] and finger_states['Pinky']:
        return "Call Me"

    # 12. Middle Finger: 仅中指伸直
    if not thumb_up and not finger_states['Index'] and finger_states['Middle'] and not finger_states['Ring'] and not finger_states['Pinky']:
        return "Middle Finger"

    return "None"

def draw_analysis_overlay(img, landmarks, gesture_name):
    """
    专门用于画“论文原理图”的函数。
    根据不同的手势名称，在图片上画出特定的高亮线条和文字标注。
    """
    h, w, _ = img.shape
    
    # 辅助函数：获取关键点像素坐标
    def get_pt(idx):
        return (int(landmarks[idx].x * w), int(landmarks[idx].y * h))
    
    # 定义醒目颜色 (BGR) 和 RGB (用于 PIL)
    COLOR_HIGHLIGHT = (0, 255, 255) # 黄色 BGR
    COLOR_SUB = (255, 255, 0)       # 青色 BGR
    # PIL 使用 RGB
    COLOR_TEXT_RGB = (255, 255, 0)  # 黄色 RGB (BGR: 0, 255, 255 -> RGB: 255, 255, 0)
    
    THICKNESS = 2
    
    # 统一文字显示位置 (Top Area)
    TEXT_POS_X = 10
    TEXT_POS_Y = 130 # 位于 "Stable" 文字下方
    
    wrist = get_pt(0)
    
    analysis_text = ""

    if gesture_name == "Palm Open":
        # 画线：从手腕(0)分别连接到5个指尖(4,8,12,16,20)
        tips = [4, 8, 12, 16, 20]
        for tip_idx in tips:
            pt = get_pt(tip_idx)
            cv2.line(img, wrist, pt, COLOR_HIGHLIGHT, THICKNESS, cv2.LINE_AA)
            
        analysis_text = "特征: 五指伸直 (All Extended)"
        
    elif gesture_name == "Fist":
        # 画线：连接5个指尖与手腕，或者在手掌中心画一个圆圈框住指尖
        tips = [4, 8, 12, 16, 20]
        pts = [get_pt(i) for i in tips]
        center_x = sum(p[0] for p in pts) // 5
        center_y = sum(p[1] for p in pts) // 5
        
        # 估算半径
        radius = 0
        for p in pts:
            d = math.sqrt((p[0]-center_x)**2 + (p[1]-center_y)**2)
            if d > radius:
                radius = d
        radius = int(radius + 20)
        
        cv2.circle(img, (center_x, center_y), radius, COLOR_HIGHLIGHT, THICKNESS)
        
        analysis_text = "特征: 五指弯曲 (All Folded)"
        
    elif gesture_name == "Victory":
        # 画线：高亮连接手腕(0)到食指尖(8)、手腕(0)到中指尖(12)
        idx_tip = get_pt(8)
        mid_tip = get_pt(12)
        
        cv2.line(img, wrist, idx_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        cv2.line(img, wrist, mid_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        
        analysis_text = "特征: V字形 (Victory Shape)"
        
    elif gesture_name == "One Finger":
        # 画线：高亮手腕(0)到食指尖(8)（实线）
        idx_tip = get_pt(8)
        cv2.line(img, wrist, idx_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        
        # 对比画出手腕(0)到中指尖(12)（细线/示意虚线）
        mid_tip = get_pt(12)
        cv2.line(img, wrist, mid_tip, COLOR_SUB, 1, cv2.LINE_AA)
        
        analysis_text = "特征: 单指伸直 (Index Only)"
        
    elif gesture_name == "OK":
        # 重点：高亮连接大拇指尖(4)和食指尖(8)
        thumb_tip = get_pt(4)
        idx_tip = get_pt(8)
        
        cv2.line(img, thumb_tip, idx_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        
        # 辅助：对其他三指画出伸直示意线
        other_tips = [12, 16, 20]
        for i in other_tips:
            pt = get_pt(i)
            cv2.line(img, wrist, pt, COLOR_SUB, 1, cv2.LINE_AA)

        analysis_text = "特征: 拇指食指接触 (Dist < 40px)"
            
    elif gesture_name == "Thumbs Up":
        # 重点：连接大拇指尖(4)与食指掌指关节(5, MCP)
        thumb_tip = get_pt(4)
        idx_mcp = get_pt(5)
        
        cv2.line(img, thumb_tip, idx_mcp, COLOR_HIGHLIGHT, 3, cv2.LINE_AA)
        
        analysis_text = "特征: 拇指检测 (Thumb Check)"
    
    elif gesture_name == "Three Fingers":
        # 画线：高亮手腕(0)到食指(8)、中指(12)、无名指(16)
        tips = [8, 12, 16]
        for tip_idx in tips:
            pt = get_pt(tip_idx)
            cv2.line(img, wrist, pt, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 食中无名指伸直 (Three up)"

    elif gesture_name == "Four Fingers":
        # 画线：高亮手腕(0)到食指(8)、中指(12)、无名指(16)、小指(20)
        tips = [8, 12, 16, 20]
        for tip_idx in tips:
            pt = get_pt(tip_idx)
            cv2.line(img, wrist, pt, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 除拇指外四指伸直 (Four up)"

    elif gesture_name == "Rock":
        # 画线：高亮手腕(0)到拇指(4)、食指(8)、小指(20)
        tips = [4, 8, 20]
        for tip_idx in tips:
            pt = get_pt(tip_idx)
            cv2.line(img, wrist, pt, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 摇滚手势 (Rock shape)"

    elif gesture_name == "Pinky":
        # 画线：高亮手腕(0)到小指(20)
        pinky_tip = get_pt(20)
        cv2.line(img, wrist, pinky_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 仅小指伸直 (Pinky only)"

    elif gesture_name == "Call Me":
        # 画线：高亮手腕(0)到拇指(4)、小指(20)
        tips = [4, 20]
        for tip_idx in tips:
            pt = get_pt(tip_idx)
            cv2.line(img, wrist, pt, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 拇指小指伸直 (6 shape)"

    elif gesture_name == "Middle Finger":
        # 画线：高亮手腕(0)到中指(12)
        mid_tip = get_pt(12)
        cv2.line(img, wrist, mid_tip, COLOR_HIGHLIGHT, 4, cv2.LINE_AA)
        analysis_text = "特征: 仅中指伸直 (Middle only)"
        
    # 统一在上方绘制高清晰度文字
    if analysis_text:
        img = put_chinese_text(
            img,
            analysis_text,
            (TEXT_POS_X, TEXT_POS_Y),
            COLOR_TEXT_RGB,
            font_size=36,
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )
        
    return img

def main():
    """
    主函数：初始化 MediaPipe Hands，处理视频流并实时识别手势。
    """
    # 初始化 MediaPipe Hands
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5
    )
    mp_draw = mp.solutions.drawing_utils

    # 初始化手势平滑器 (10帧历史，>8次阈值)
    smoother = GestureSmoother(history_length=10, threshold=8)

    # 打开默认摄像头
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    print("Press 'q' to exit.")
    print("Press 's' to toggle auto-save mode (saves to images_data/).")

    # 自动保存模式标志
    is_saving_mode = False
    last_saved_gesture = "None"  # 记录上次保存的手势，防止重复保存
    import time
    import os

    # 确保保存目录存在
    save_dir = "images_data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    while True:
        success, img = cap.read()
        if not success:
            print("Ignoring empty camera frame.")
            continue

        # 镜像翻转图像
        img = cv2.flip(img, 1)

        # 将图像转换为 RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 处理图像
        results = hands.process(img_rgb)

        raw_gesture = "None"
        stable_gesture = "None"

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # 绘制骨架
                mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                # 识别当前帧手势
                raw_gesture = get_gesture(hand_landmarks.landmark, img.shape)
                
                # 平滑处理
                stable_gesture = smoother.update(raw_gesture)
                
        else:
            # 如果没有检测到手，也更新平滑器（或者重置? 这里选择更新为None）
            stable_gesture = smoother.update("None")

        # 根据手势设置颜色 (BGR)
        gesture_colors = {
            "None": (0, 0, 255),       # Red
            "Fist": (255, 105, 180),   # HotPink
            "Palm Open": (0, 255, 255), # Yellow
            "Victory": (255, 0, 255),  # Magenta
            "One Finger": (0, 165, 255), # Orange
            "Thumbs Up": (255, 255, 0), # Cyan
            "OK": (0, 255, 0),         # Green
            "Three Fingers": (128, 0, 128), # Purple
            "Four Fingers": (0, 128, 255),  # Light Blue
            "Rock": (0, 0, 0),         # Black
            "Pinky": (203, 192, 255),  # Pink
            "Call Me": (255, 255, 255),# White
            "Middle Finger": (0, 0, 255)     # Red
        }
        
        color = gesture_colors.get(stable_gesture, (255, 255, 255))
        
        # 中文名称映射
        gesture_names_cn = {
            "None": "未识别 (None)",
            "Fist": "握拳 (Fist)",
            "Palm Open": "张开手掌 (Palm Open)",
            "Victory": "剪刀手 (Victory)",
            "One Finger": "单指 (One Finger)",
            "Thumbs Up": "点赞 (Thumbs Up)",
            "OK": "OK (OK)",
            "Three Fingers": "三指 (Three Fingers)",
            "Four Fingers": "四指 (Four Fingers)",
            "Rock": "摇滚 (Rock)",
            "Pinky": "小指 (Pinky)",
            "Call Me": "打电话 (Call Me)",
            "Middle Finger": "竖中指 (Middle Finger)"
        }
        
        display_name = gesture_names_cn.get(stable_gesture, stable_gesture)
        
        # 转换颜色为 RGB (PIL 使用 RGB)
        # color 是 BGR，需要转为 RGB
        color_rgb = (color[2], color[1], color[0])

        # 显示实时识别结果 (Raw)
        # 实时结果也可以用中文，或者保持英文
        # 这里为了简洁，实时结果保持英文，只在稳定结果显示中文
        # 使用 put_chinese_text 统一风格并添加描边
        img = put_chinese_text(
            img,
            f"Raw: {raw_gesture}",
            (10, 40),
            (200, 200, 200), # 灰色
            font_size=30, # 稍微小一点
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

        # 显示滤波后判定 (Stable) - 使用 PIL 绘制中文
        img = put_chinese_text(
            img,
            f"Stable: {display_name}",
            (10, 80),
            color_rgb,
            font_size=40,
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

        # 显示图像
        cv2.imshow('Smart Home Gesture Control', img)

        # 按 'q' 键退出 或 点击窗口关闭按钮
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        
        # 监听 s 键切换自动保存模式
        if key == ord('s'):
            is_saving_mode = not is_saving_mode
            if is_saving_mode:
                print(">>> 开始自动保存 (Auto-Save Started) <<<")
                last_saved_gesture = "None" # 开启时重置状态
            else:
                print(">>> 停止自动保存 (Auto-Save Stopped) <<<")

        # 自动保存逻辑
        if is_saving_mode:
            if stable_gesture != "None":
                # 只有当当前手势与上次保存的不同时才保存 (单次触发)
                if stable_gesture != last_saved_gesture:
                    # 复制当前帧（以免影响实时画面）
                    analysis_img = img.copy()
                    
                    if results.multi_hand_landmarks:
                        # 取第一只手的 landmarks
                        last_landmarks = results.multi_hand_landmarks[0].landmark
                        
                        # 调用绘图函数
                        analysis_img = draw_analysis_overlay(analysis_img, last_landmarks, stable_gesture)
                        
                        # 生成文件名
                        timestamp = int(time.time() * 1000) # 使用毫秒级时间戳避免重名
                        filename = os.path.join(save_dir, f"analysis_{stable_gesture}_{timestamp}.jpg")
                        
                        # 保存图片
                        try:
                            cv2.imwrite(filename, analysis_img)
                            print(f"Saved: {filename}") 
                            # 更新上次保存的手势
                            last_saved_gesture = stable_gesture
                        except Exception as e:
                            print(f"Save Failed: {e}")
            else:
                # 如果没有识别到手势，重置上次保存状态，以便下次识别到相同手势时能再次保存
                # 例如：Fist -> None -> Fist (会保存两次)
                last_saved_gesture = "None"
            
        if cv2.getWindowProperty('Smart Home Gesture Control', cv2.WND_PROP_VISIBLE) < 1:
            break

    # 释放资源
    cap.release()
    cv2.destroyAllWindows()
    hands.close()

if __name__ == "__main__":
    main()
