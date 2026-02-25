
import cv2
import numpy as np
import json
import os
import sys

# Add AprilTagInterface to path
sys.path.append(r'w:\CATL\Eliteroboarm')
from AprilTagInterface.src.detector import AprilTagDetector

def load_intrinsics(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return np.array(data['intrinsics'])

def main():
    root_dir = r"w:\CATL\Eliteroboarm"
    captures_dir = os.path.join(root_dir, "workspace", "paths", "captures")
    intrinsics_file = os.path.join(root_dir, "intrinsics.json")
    
    file_std = os.path.join(captures_dir, "std_point_20260211_113354.jpg")
    file_cur = os.path.join(captures_dir, "follow_result_20260211_113417.jpg")
    
    print(f"Loading intrinsics from {intrinsics_file}")
    if os.path.exists(intrinsics_file):
        K = load_intrinsics(intrinsics_file)
    else:
        print("Intrinsics file not found, using default.")
        K = np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], dtype=np.float32)
        
    print(f"Camera Matrix:\n{K}")
    
    # Initialize detector
    detector = AprilTagDetector(tag_size_m=0.033, camera_matrix=K)
    # Note: User didn't specify tag size, usually it's small if it's calibrated with checksboard or custom tag. 
    # But wait, earlier log said "Distance: 0.506m".
    # Log: "Tag ID: 0", "Pos (Cam): [-0.01 0.004 0.506]"
    # If tag_size is wrong, distance acts linearly. 
    # Let's try to infer tag size or just use a standard one. 
    # The user didn't provide tag size. 
    # Looking at camera_control.py: "self.at_detector = AprilTagDetector(tag_size_m=0.1, ...)"
    # So I will use 0.1
    detector = AprilTagDetector(tag_size_m=0.1, camera_matrix=K)
    
    # Read images
    img_std = cv2.imread(file_std)
    img_cur = cv2.imread(file_cur)
    
    if img_std is None:
        print(f"Failed to load standard image: {file_std}")
        return
    if img_cur is None:
        print(f"Failed to load current image: {file_cur}")
        return
        
    print("Detecting tags...")
    res_std = detector.detect(img_std)
    res_cur = detector.detect(img_cur)
    
    target_id = 0 # Assuming ID 0 based on logs
    
    tag_std = next((r for r in res_std if r['id'] == target_id), None)
    tag_cur = next((r for r in res_cur if r['id'] == target_id), None)
    
    if not tag_std:
        print(f"Tag {target_id} not found in Standard Image")
        print(f"Found IDs: {[r['id'] for r in res_std]}")
        return
    if not tag_cur:
        print(f"Tag {target_id} not found in Current Image")
        print(f"Found IDs: {[r['id'] for r in res_cur]}")
        return
        
    print(f"Standard Tag Pose (Cam): {np.round(tag_std['tvec'], 4)}")
    print(f"Current Tag Pose (Cam):  {np.round(tag_cur['tvec'], 4)}")
    
    # Calculate Deviation
    tvec_std = tag_std['tvec']
    tvec_cur = tag_cur['tvec']
    
    dx_mm = (tvec_cur[0] - tvec_std[0]) * 1000.0
    dy_mm = (tvec_cur[1] - tvec_std[1]) * 1000.0
    dz_mm = (tvec_cur[2] - tvec_std[2]) * 1000.0
    
    # Euler Z deviation
    yaw_std = tag_std['euler'][2]
    yaw_cur = tag_cur['euler'][2]
    dr_deg = yaw_cur - yaw_std
    
    print("\n" + "="*40)
    print(" 计算结果 ")
    print("="*40)
    print(f"DX: {dx_mm:.2f} mm")
    print(f"DY: {dy_mm:.2f} mm")
    print(f"DZ: {dz_mm:.2f} mm")
    print(f"DR: {dr_deg:.2f} deg")
    
if __name__ == "__main__":
    main()
