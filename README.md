# SmartGestureHome

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/OpenCV-4.x-green?logo=opencv&logoColor=white" />
  <img src="https://img.shields.io/badge/MediaPipe-0.10.11-orange?logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/PyQt5-5.15.11-blue" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" />
</p>

<p align="center">
  基于 MediaPipe + ESP32 的智能家居手势控制系统 — 摄像头识别 12 种手势，串口控制 6 种模拟家电
</p>

<p align="center">
  <img src="assets/screenshot.png" width="800" alt="GUI界面截图" />
</p>

---

## 目录

- [功能特性](#功能特性)
- [手势映射](#手势映射)
- [硬件清单](#硬件清单)
- [软件环境](#软件环境)
- [核心算法](#核心算法)
- [硬件接线](#硬件接线)
- [安装](#安装)
- [运行](#运行)
- [项目结构](#项目结构)
- [贡献](#贡献)
- [许可证](#许可证)

## 功能特性

- **12 种手势识别** — 张手、握拳、剪刀手、单指、OK、点赞、三指、四指、摇滚、小指、打电话、竖中指
- **实时摄像头预览** — MediaPipe 手部追踪 + 骨架绘制
- **手势去抖动** — 10 帧滑动窗口 + 多数表决机制，彻底消除识别跳变
- **串口通信** — 自动搜索 ESP32 串口，发送控制指令
- **智能家居 GUI** — PyQt5 深色主题界面，实时显示设备状态和系统日志
- **断线自动重连** — 串口断开后自动尝试重新连接

## 手势映射

| 手势名称 | 串口指令 | 控制设备 | MediaPipe 判定逻辑 |
|:---------|:--------:|:---------|:-------------------|
| 张手 (Palm Open) | `A` | 灯光 ON | 5 指全伸直 |
| 握拳 (Fist) | `B` | 灯光 OFF | 5 指全弯曲 |
| 剪刀手 (Victory) | `C` | 窗帘 OPEN | 食指与中指伸直，其余折叠 |
| 单指 (One Finger) | `D` | 窗帘 CLOSE | 仅食指伸直 |
| OK | `E` | 风扇 ON | 食指与拇指捏合，其余 3 指伸直 |
| 点赞 (Thumbs Up) | `F` | 风扇 OFF | 仅拇指伸直 |
| 三指 (Three Fingers) | `G` | 电视 ON | 仅食指、中指、无名指伸直 |
| 四指 (Four Fingers) | `H` | 电视 OFF | 除拇指外，其余 4 指均伸直 |
| 摇滚 (Rock) | `I` | 空调 ON | 仅拇指、食指、小指伸直 |
| 小指 (Pinky) | `J` | 空调 OFF | 仅小指伸直 |
| 打电话 (Call Me) | `K` | 音响 ON | 仅拇指、小指伸直 |
| 竖中指 (Middle Finger) | `L` | 音响 OFF | 仅中指伸直 |

## 硬件清单

| 类别 | 组件 | 说明 |
|:-----|:-----|:-----|
| 核心控制器 | ESP32 开发板 | Type-C 接口 / FT232 串口芯片 |
| 执行器 | SG90 舵机 | 模拟窗帘控制（棕色→GND，红色→5V，黄色→信号） |
| 执行器 | 5V 风扇模块 | 带 L9110 驱动电路 |
| 执行器 | 5mm LED 基础包 | 红、绿、黄灯珠 + 220Ω 电阻 |
| 连接件 | 830 孔面包板 | — |
| 连接件 | 杜邦线套装 | 公对公/公对母/母对母各 40 根 |
| 连接件 | USB 数据线 | 连接 ESP32 与电脑 |

## 软件环境

| 项目 | 版本 |
|:-----|:-----|
| Python | 3.9.25 |
| MediaPipe | 0.10.11 |
| OpenCV | 4.13.0.90 |
| PyQt5 | 5.15.11 |
| 虚拟环境 | conda `smart_home` |

**ESP32 开发环境**：Arduino IDE 2.3.7 + `ESP32Servo` 库

## 核心算法

系统基于 MediaPipe 提供的 **21 个手部关键点**，采用以下逻辑进行判定：

- **几何判别**：通过计算关键点间的欧氏距离确定手指弯曲状态

  $$D = \sqrt{(x_1-x_2)^2 + (y_1-y_2)^2}$$

- **拇指增强检测**：针对大拇指结构，引入多参考点（食指与小指 MCP 关节）距离对比，解决"点赞"与"握拳"在投影面上的相似性问题

- **稳定性优化**：`GestureSmoother` 类采用 **10 帧滑动窗口 (deque)** 与 **多数表决机制**（频率阈值 > 8），彻底消除识别跳变

## 硬件接线

### 引脚分配表

| 硬件模块 | 信号引脚 (GPIO) | 电源 (VCC) | 接地 (GND) | 备注 |
|:---------|:---------------|:-----------|:-----------|:-----|
| SG90 舵机 | D13 (GPIO 13) | 5V (红色轨) | GND (蓝色轨) | 模拟窗帘控制 |
| L9110 风扇 | D32 (GPIO 32) | 5V (红色轨) | GND (蓝色轨) | INB 接 D32，INA 接 GND |
| 黄色 LED | D25 (GPIO 25) | - | 串联电阻 → GND | 模拟环境灯光 |
| 红色 LED | D27 (GPIO 27) | - | 串联电阻 → GND | 模拟智能电视 |
| 绿色 LED | D26 (GPIO 26) | - | 串联电阻 → GND | 模拟空调系统 |
| 黄色 LED2 | D33 (GPIO 33) | - | 串联电阻 → GND | 模拟家庭音响 |

### 面包板布局

采用 **"靠右侧插法"**：

- ESP32 开发板右侧排针插入面包板最右侧 J 列
- 左侧 A-E 列留作跳线连接区域
- ESP32 GND 连接面包板蓝色电源轨（-），VIN (5V) 连接红色电源轨（+）
- 所有外设供电直接从电源轨获取

### 接线细节

**LED 模块**：正极接对应 GPIO 引脚，负极串联 220Ω 电阻接 GND

**舵机模块**：橙色线（信号）→ D13，红色线 → 5V 电源轨，棕色线 → GND 电源轨

**风扇驱动 (L9110)**：VCC → 5V 电源轨，GND → GND 电源轨，INA → GND，INB → D32

## 安装

```bash
# 克隆仓库
git clone https://github.com/chi-ga/SmartGestureHome.git
cd SmartGestureHome

# 创建 conda 环境
conda create -n smart_home python=3.9.25
conda activate smart_home

# 安装依赖
pip install -r requirements.txt
```

## 运行

```bash
# 主程序（GUI + 视频流 + 串口）
python system_main.py

# GUI 独立演示
python main_gui.py
```

| 按键 | 功能 |
|:-----|:-----|
| `S` | 切换自动截图模式 |
| `Q` | 退出程序 |

## 项目结构

```
SmartGestureHome/
├── system_main.py        # 主程序：GUI + 视频流 + 串口通信
├── hand_gesture_logic.py # 手势识别算法（MediaPipe + 去抖）
├── main_gui.py           # GUI 独立演示
├── esp32.ino             # ESP32 下位机代码（Arduino）
├── protocol.txt          # 串口通信协议定义
├── requirements.txt      # Python 依赖
└── README.md             # 项目说明
```

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建你的分支 (`git checkout -b feature/xxx`)
3. 提交改动 (`git commit -m 'add: xxx功能'`)
4. 推送到分支 (`git push origin feature/xxx`)
5. 提交 Pull Request

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
