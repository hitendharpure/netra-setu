// Author: Hiten Dharpure
// Project Netra-Setu: Live Autonomous OCR Translation (Master Edition)
// Features: RPC Linux Bridge, Hardware Speed UI, Calibration Matrix, LED Visualizer
// Created: June 2026

#include <Arduino_RouterBridge.h> // Native RPC link to App Lab container
#include <ArduinoGraphics.h>      // Graphics engine 
#include <Arduino_LED_Matrix.h>   // LED Hardware driver

// Instantiate the Uno Q LED Matrix object
Arduino_LED_Matrix matrix;

const int SERVO_PINS[6] = {2, 4, 6, 3, 5, 7}; 
const int POT_PIN = A0; // Hardware Speed Control Dial

// --- PER-PIN CALIBRATION MATRIX ---
const int ACTIVE_PULSES[6] = {1400, 1400, 1400, 1800, 1800, 1650}; 
const int REST_PULSES[6] =   {1600, 1600, 1600, 1500, 1500, 1400}; 

const int CYCLE_PERIOD_US = 20000; 

String serialBuffer = "";

const uint8_t brailleAlphabet[26] = {
  0x01, 0x03, 0x09, 0x19, 0x11, 0x0B, 0x1B, 0x13, 0x0A, 0x1A, // A - J
  0x05, 0x07, 0x0D, 0x1D, 0x15, 0x0F, 0x1F, 0x17, 0x0E, 0x1E, // K - T
  0x25, 0x27, 0x3A, 0x2D, 0x3D, 0x35                          // U - Z
};

// --- RPC CALLBACK HANDLER ---
// Automatically receives characters sent from the Python app container
void send_char(String c) {
  if (c.length() > 0) {
    char incomingChar = c[0];
    serialBuffer += incomingChar;
  }
}

void setup() {
  // 1. Open standard USB channel for local laptop testing
  Serial.begin(115200);
  
  // 2. Initialize the background communication bridge to the Linux core
  Bridge.begin();
  Bridge.provide("send_char", send_char);
  
  // 3. Initialize the onboard 13x8 LED Matrix
  matrix.begin();
  matrix.beginDraw();
  matrix.clear();
  matrix.endDraw();
  
  for (int i = 0; i < 6; i++) {
    pinMode(SERVO_PINS[i], OUTPUT);
  }
  
  pinMode(POT_PIN, INPUT);
  
  clearCell(2000); 
  Serial.println("SYSTEM READY: RPC Bridge & LED Visualizer Initialized.");
}

void loop() {
  // Keep the background RPC router listening for AI camera data
  Bridge.update(); 

  // Keep the standard Serial listening for local laptop testing
  while (Serial.available() > 0) {
    char incomingChar = Serial.read();
    if(incomingChar != '\n' && incomingChar != '\r') {
      serialBuffer += incomingChar;
    }
  }

  // --- PROCESSING THE BUFFER ---
  if (serialBuffer.length() > 0) {
    char targetChar = serialBuffer[0];
    
    // Dynamic Hardware Speed Control
    int potValue = analogRead(POT_PIN); 
    int readingDuration = map(potValue, 0, 1023, 500, 3000);
    int pauseDuration = readingDuration / 3; 
    
    Serial.print("Actuating: ");
    Serial.print(targetChar);
    Serial.print(" | Speed: ");
    Serial.print(readingDuration);
    Serial.println(" ms");

    // --- 1. DRAW CHARACTER ON LED MATRIX ---
    matrix.beginDraw();
    matrix.clear();
    matrix.stroke(0xFFFFFFFF);
    matrix.textFont(Font_5x7);
    matrix.beginText(4, 0, 0xFFFFFF); 
    matrix.print(targetChar);
    matrix.endText();
    matrix.endDraw();
    
    // Pass the physical dial's timing down to the servo multiplexer
    actuateBrailleCell(targetChar, readingDuration); 

    // --- 2. CLEAR LED MATRIX DURING CELL PAUSE ---
    matrix.beginDraw();
    matrix.clear();
    matrix.endDraw();
    
    clearCell(pauseDuration); 
    
    serialBuffer.remove(0, 1);
    
    if(serialBuffer.length() == 0) {
        Serial.println("Matrix clear. Waiting for next input...");
    }
  } else {
    clearCell(20); 
  }
}

// --- DYNAMIC SOFTWARE PWM ENGINE ---
void actuateBrailleCell(char c, int duration_ms) {
  c = toupper(c);
  uint8_t mask = 0x00; 
  
  if (c >= 'A' && c <= 'Z') {
    mask = brailleAlphabet[c - 'A'];
  }
  
  int targetPulses[6];
  int maxPulse = 0; 
  
  for (int i = 0; i < 6; i++) {
    bool isActive = (mask & (1 << i));
    targetPulses[i] = isActive ? ACTIVE_PULSES[i] : REST_PULSES[i];
    
    if (targetPulses[i] > maxPulse) {
      maxPulse = targetPulses[i];
    }
  }

  unsigned long startTime = millis();

  while (millis() - startTime < duration_ms) {
    bool pinActive[6] = {true, true, true, true, true, true};
    unsigned long frameStart = micros();
    
    for (int i = 0; i < 6; i++) digitalWrite(SERVO_PINS[i], HIGH);
    
    while (micros() - frameStart < maxPulse) {
      unsigned long elapsed = micros() - frameStart;
      for (int i = 0; i < 6; i++) {
        if (pinActive[i] && elapsed >= targetPulses[i]) {
          digitalWrite(SERVO_PINS[i], LOW);
          pinActive[i] = false; 
        }
      }
    }
    
    for (int i = 0; i < 6; i++) digitalWrite(SERVO_PINS[i], LOW);
    
    int remainder_us = CYCLE_PERIOD_US - maxPulse;
    delay(remainder_us / 1000);             
    delayMicroseconds(remainder_us % 1000); 
  }
}

void clearCell(int duration_ms) {
  actuateBrailleCell(' ', duration_ms);
}