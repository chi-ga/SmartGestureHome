#include <ESP32Servo.h>

// --- 引脚定义 ---
const int pinLight  = 25;  // 黄灯 (模拟灯光) -> D25
const int pinAC     = 26;  // 绿灯 (模拟空调) -> D26
const int pinTV     = 27;  // 红灯 (模拟电视) -> D27
const int pinAudio  = 33;  // 黄灯2 (模拟音响) -> D33

const int servoPin  = 13;  // 舵机 (模拟窗帘) -> D13
const int fanPin    = 32;  // 风扇 -> D32

// --- 创建对象 ---
Servo myServo;

void setup() {
  // 1. 【最优先】先配置风扇引脚并强制拉低
  // 防止其他初始化代码耗时导致风扇多转哪怕一毫秒
  pinMode(fanPin, OUTPUT);
  digitalWrite(fanPin, LOW);

  Serial.begin(9600);

  // 2. 初始化四路独立 LED
  pinMode(pinLight, OUTPUT);
  pinMode(pinTV, OUTPUT);
  pinMode(pinAC, OUTPUT);
  pinMode(pinAudio, OUTPUT);
  digitalWrite(pinLight, LOW);
  digitalWrite(pinTV, LOW);
  digitalWrite(pinAC, LOW);
  digitalWrite(pinAudio, LOW);

  // 3. 初始化舵机
  // 注意：Servo attach 有时会引起抖动，放在最后
  myServo.setPeriodHertz(50);
  myServo.attach(servoPin, 500, 2400);
  myServo.write(0);

  // 4. 再次确保风扇关闭 (PWM 通道初始化)
  analogWrite(fanPin, 0);
  Serial.println("System Ready: 4-Device Independent Mode");
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == '\n' || cmd == '\r') return;

    switch (cmd) {
      // --- 灯光控制 (黄灯 D25) ---
      case 'A':
        digitalWrite(pinLight, HIGH);
        Serial.println("Action: Light ON");
        break;
      case 'B':
        digitalWrite(pinLight, LOW);
        Serial.println("Action: Light OFF");
        break;

      // --- 窗帘控制 (舵机 D13) ---
      case 'C':
        myServo.write(180);
        Serial.println("Action: Curtain OPEN");
        break;
      case 'D':
        myServo.write(0);
        Serial.println("Action: Curtain CLOSE");
        break;

      // --- 风扇控制 (L9110 D32) ---
      case 'E':
        analogWrite(fanPin, 100); // 顺时针旋转，速度100
        Serial.println("Action: Fan ON (CW)");
        break;
      case 'F':
        analogWrite(fanPin, 0);   // 停止
        Serial.println("Action: Fan OFF");
        break;

      // --- 电视控制 (红灯 D27) ---
      case 'G':
        digitalWrite(pinTV, HIGH);
        Serial.println("Action: TV ON");
        break;
      case 'H':
        digitalWrite(pinTV, LOW);
        Serial.println("Action: TV OFF");
        break;

      // --- 空调控制 (绿灯 D26) ---
      case 'I':
        digitalWrite(pinAC, HIGH);
        Serial.println("Action: AC ON");
        break;
      case 'J':
        digitalWrite(pinAC, LOW);
        Serial.println("Action: AC OFF");
        break;

      // --- 音响控制 (黄灯2 D33) ---
      case 'K':
        digitalWrite(pinAudio, HIGH);
        Serial.println("Action: Audio ON");
        break;
      case 'L':
        digitalWrite(pinAudio, LOW);
        Serial.println("Action: Audio OFF");
        break;
    }
  }
}
