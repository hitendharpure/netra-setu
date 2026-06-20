#!/usr/bin/env python3
# ==============================================================================
# Title: Autonomous Edge-AI Vision Pipeline for Real-Time Optical Character Recognition and Tensor Alignment
# Author: Hiten Dharpure
# Created: June 2026
# Copyright (c) 2026 Hiten Dharpure. All Rights Reserved.
#
# This software and its underlying algorithms are the proprietary intellectual 
# property of the author. Unauthorized copying, modification, distribution, 
# or use of this file, via any medium, is strictly prohibited.
# ==============================================================================
# Project Netra-Setu: Headless Autonomous Vision Pipeline (Phase 1 Live)

# pyrefly: ignore [missing-import]
import cv2
import time
import os
import sys

# --- PATH EQUALIZATION ---
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'python'))

# Apply App Lab mocks and environment configurations
from python.utils.mock_dependencies import apply_mocks
apply_mocks()

import web_inference
# pyrefly: ignore [missing-import]
from arduino.app_utils import Bridge

# ==============================================================================
# --- DYNAMIC TENSOR ALIGNMENT PATCH ---
# Intercepts the Edge Impulse tensor and dynamically auto-scales the class matrix
# to prevent strict shape mismatch crashes when dictionaries are auto-generated.
# ==============================================================================
def patched_parse(pred_resp, dictionary):
    result = pred_resp.get('result', {})
    freeform = result.get('freeform')
    if not freeform or len(freeform) == 0:
        return None

    tensor = freeform[0]
    tensor_len = len(tensor)

    # Auto-detect sequence length (80, 120, 160, 240) to find exact AI vocab size
    step = None
    for seq_len in [80, 120, 240, 160, 40]:
        if tensor_len % seq_len == 0:
            step = tensor_len // seq_len
            break

    if step is None:
        step = len(dictionary) + 1

    reshaped = []
    for ix in range(0, tensor_len, step):
        reshaped.append(tensor[ix:ix + step])

    all_confidences = 0.0
    predicted_chars_length = 0
    output = ''

    # Pad our dictionary with blanks to perfectly match the model's unknown vocab size
    safe_dict = dictionary.copy()
    while len(safe_dict) < step:
        safe_dict.append('')  

    for col in reshaped:
        hi_val = 0.0
        hi_ix = -1
        for ix, v in enumerate(col):
            if v > hi_val:
                hi_val = float(v)
                hi_ix = ix

        if hi_ix != 0: # 0 is the CTC blank space
            char_idx = hi_ix - 1
            if 0 <= char_idx < len(safe_dict):
                char = safe_dict[char_idx]
                if char:  # Ignore padded out-of-bounds characters silently
                    output += char
                    all_confidences += hi_val
                    predicted_chars_length += 1

    if predicted_chars_length == 0:
        return None

    return {
        'output': output,
        'avgConfidence': all_confidences / predicted_chars_length,
    }

# Inject the patch directly into the web_inference engine
web_inference.parse_paddle_ocr_predictor = patched_parse
# ==============================================================================

def ensure_dictionary(project_root, detected_models):
    """Auto-heals the missing dictionary by extracting it from the model or generating it."""
    dict_path = os.path.join(project_root, 'models', 'rec_en_dict.txt')
    if detected_models.get('dict_file') and os.path.exists(detected_models['dict_file']):
        return detected_models
        
    print("Dictionary NOT FOUND! Attempting to extract exact AI labels...")
    try:
        from edge_impulse_linux.image import ImageImpulseRunner
        runner = ImageImpulseRunner(detected_models['predict_file'])
        model_info = runner.init(debug=False)
        labels = model_info.get('model_parameters', {}).get('labels', [])
        runner.stop()
        
        if labels and len(labels) > 10:
            os.makedirs(os.path.dirname(dict_path), exist_ok=True)
            with open(dict_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(labels))
            print(f"Successfully extracted {len(labels)} character dictionary.")
            detected_models['dict_file'] = dict_path
            return detected_models
    except Exception as e:
        pass
        
    print("Auto-generating standard English OCR dictionary...")
    os.makedirs(os.path.dirname(dict_path), exist_ok=True)
    standard_chars = list("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ ")
    with open(dict_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(standard_chars))
        
    detected_models['dict_file'] = dict_path
    return detected_models

def start_autonomous_pipeline():
    print("Initializing AI Vision Core...")
    
    detected_models = web_inference.auto_detect_models(project_root)
    if not detected_models.get('detect_file') or not detected_models.get('predict_file'):
        print("FATAL ERROR: Could not find .eim model files.")
        return

    detected_models = ensure_dictionary(project_root, detected_models)

    engine = web_inference.OCREngine(
        detect_file=detected_models['detect_file'],
        predict_file=detected_models['predict_file'],
        dict_file=detected_models['dict_file'],
        debug=False
    )
    print("Loading AI Models into memory...")
    engine.load_models()

    print("\nScanning for Match 1080p Webcam...")
    started = False
    for index in [0, 1, 2, 3, 4]:
        print(f"Testing camera connection on index {index}...")
        res = engine.start(camera_device=index)
        if res.get('success'):
            print(f"--> SUCCESS: Successfully connected to Webcam at index {index}!")
            started = True
            break
            
    if not started:
        print("FATAL ERROR: Webcam not found or cannot read frames. Check OTG link.")
        return

    print("\n==================================================")
    print("SYSTEM LIVE: Place text in front of Netra-Setu camera.")
    print("==================================================")

    last_detected_text = ""

    try:
        while engine.is_running():
            status = engine.get_status()
            results = status.get('results', [])
            
            if results:
                detected_word = " ".join([r['text'] for r in results]).strip().upper()
                
                if detected_word and detected_word != last_detected_text:
                    print(f"\n[AI OCR Detected]: {detected_word}")
                    last_detected_text = detected_word
                    
                    for char in detected_word:
                        if char.isalpha() or char.isspace():
                            Bridge.notify("send_char", char)
                            print(f"Sending character to STM32: {char}")
                    
                    time.sleep(len(detected_word) * 2.0)
                    
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\nShutting down vision pipeline...")
    finally:
        engine.shutdown()

if __name__ == '__main__':
    start_autonomous_pipeline()
