import sys
import os

# ==========================================
# 用户配置区 (USER CONFIG)
# ==========================================
SINGLE_GRID_SIDE_MM = 10.0 

# 【关键修改】最小面积阈值
# 估算：如果格子边长约45像素，面积就是2025。
# 设为 1000 可以安全滤掉绝大多数反光噪点，同时保留真格子。
MIN_AREA_THRESHOLD = 1000.0 

DEBUG_MODE = True
# ==========================================

try:
    import cv2
    import numpy as np
    import math
except Exception as e:
    print(f"FATAL ERROR: Missing libraries. {e}")
    sys.exit(1)

def get_top_left_corner(box_points):
    sums = box_points[:, 0] + box_points[:, 1]
    return box_points[np.argmin(sums)]

def smart_angle_diff(angle_pack, angle_ref):
    diff = angle_pack - angle_ref
    while diff > 180: diff -= 360
    while diff < -180: diff += 360
    if diff > 45: diff -= 90
    elif diff < -45: diff += 90
    return diff

def get_contour_center(c):
    M = cv2.moments(c)
    if M["m00"] == 0: return (0,0)
    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    return (cX, cY)

def run_detection():
    print(f"STEP 1: Start Detection (V9 - Area Filter > {MIN_AREA_THRESHOLD})")
    
    img_path = r"W:\CATL\Eliteroboarm\workspace\captures\Top_Camera_(ME2C)_20260205_102437.jpg"
    
    if not os.path.exists(img_path):
        img_path = r"W:\CATL\Eliteroboarm\workspace\captures\20260204154716_28_51.png"
        if not os.path.exists(img_path): return

    img = cv2.imread(img_path)
    if img is None: return
    
    vis_img = img.copy()
    print(f"STEP 2: Image Loaded.")

    # --- 阶段 1: 找蓝胶带 ---
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask_blue = cv2.inRange(hsv, np.array([80, 100, 100]), np.array([130, 255, 255]))
    mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, np.ones((7,7), np.uint8))
    contours_blue, _ = cv2.findContours(mask_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    ref_anchor = None
    ref_angle = 0.0
    
    if contours_blue:
        c_blue = max(contours_blue, key=cv2.contourArea)
        rect_blue = cv2.minAreaRect(c_blue)
        box_blue = np.int32(cv2.boxPoints(rect_blue))
        ref_anchor = get_top_left_corner(box_blue)
        ref_angle = rect_blue[2]
        cv2.drawContours(vis_img, [box_blue], 0, (0, 255, 255), 2)
        cv2.circle(vis_img, tuple(ref_anchor), 8, (0, 0, 255), -1)
        print(f"   -> Tape Found: {ref_anchor}")
    else:
        print("   -> [WARNING] Tape NOT found.")

    # --- 阶段 2: 找格子 (面积过滤 + 聚类) ---
    print("STEP 3: Detecting Grid Squares...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # 全局二值化
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 形态学去噪 (稍微加强一点开运算，把小的噪点腐蚀掉)
    kernel = np.ones((3,3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    raw_candidates = []
    dropped_by_area = 0
    
    # 1. 严格筛选 (面积)
    for c in contours:
        area = cv2.contourArea(c)
        
        # 【关键】面积过滤
        if area < MIN_AREA_THRESHOLD: 
            dropped_by_area += 1
            continue
        if area > 50000: continue
        
        # 形状过滤 (矩形度)
        rect = cv2.minAreaRect(c)
        w, h = rect[1]
        if w == 0 or h == 0: continue
        aspect_ratio = min(w, h) / max(w, h)
        if aspect_ratio < 0.6: continue 
        
        # 实心度过滤
        hull = cv2.convexHull(c)
        solidity = area / cv2.contourArea(hull)
        if solidity < 0.6: continue
        
        raw_candidates.append(c)

    print(f"   -> Found {len(raw_candidates)} candidates (Dropped {dropped_by_area} small noise items).")

    # 2. 邻居聚类过滤 (Proximity Filter)
    final_squares = []
    rejected_squares = []
    
    if len(raw_candidates) > 0:
        widths = [max(cv2.minAreaRect(c)[1]) for c in raw_candidates]
        avg_width = np.median(widths)
        search_radius = avg_width * 3.5
        centers = [get_contour_center(c) for c in raw_candidates]
        
        for i, c in enumerate(raw_candidates):
            my_center = centers[i]
            neighbors = 0
            for j, other_center in enumerate(centers):
                if i == j: continue
                dist = math.hypot(my_center[0] - other_center[0], my_center[1] - other_center[1])
                if dist < search_radius:
                    neighbors += 1
            
            if neighbors >= 2:
                final_squares.append(c)
            else:
                rejected_squares.append(c)
                
    if DEBUG_MODE:
        debug_img = img.copy()
        cv2.drawContours(debug_img, rejected_squares, -1, (0, 0, 255), 2) # 红：孤立的
        cv2.drawContours(debug_img, final_squares, -1, (0, 255, 0), 2)    # 绿：最终保留的
        cv2.imwrite(img_path.replace(".jpg", "_debug_filtered.png"), debug_img)
        print(f"   -> Filtered Result: {len(final_squares)} kept, {len(rejected_squares)} rejected.")

    # 3. 聚合计算
    pack_anchor = None
    pack_angle = 0.0
    
    if len(final_squares) > 10:
        all_points_concat = np.vstack(final_squares)
        rect_pack = cv2.minAreaRect(all_points_concat)
        box_pack = np.int32(cv2.boxPoints(rect_pack))
        
        pack_anchor = get_top_left_corner(box_pack)
        pack_angle = rect_pack[2]
        
        widths = [max(cv2.minAreaRect(c)[1]) for c in final_squares]
        median_pixel_width = np.median(widths)
        mm_per_pixel = SINGLE_GRID_SIDE_MM / median_pixel_width
        
        print(f"   -> Median Grid Area: {np.median([cv2.contourArea(c) for c in final_squares]):.1f} px^2")
        print(f"   -> Scale: {mm_per_pixel:.5f} mm/px")
        
        cv2.drawContours(vis_img, [box_pack], 0, (0, 255, 0), 3)
        cv2.circle(vis_img, tuple(pack_anchor), 10, (0, 255, 0), -1)
    else:
        print("   -> [WARNING] Not enough squares.")
        return

    # --- 阶段 3: 物理计算 ---
    if ref_anchor is not None and pack_anchor is not None:
        dx_px = float(pack_anchor[0] - ref_anchor[0])
        dy_px = float(pack_anchor[1] - ref_anchor[1])
        
        dx_mm = dx_px * mm_per_pixel
        dy_mm = dy_px * mm_per_pixel
        da_deg = smart_angle_diff(pack_angle, ref_angle)
        
        print("\n" + "="*45)
        print(f"【 机械臂补偿数据 (Area Filtered) 】")
        print(f"X : {dx_mm:.2f} mm")
        print(f"Y : {dy_mm:.2f} mm")
        print(f"R : {da_deg:.2f} °")
        print("="*45 + "\n")

        cv2.putText(vis_img, f"dX: {dx_mm:.1f}mm", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
        cv2.putText(vis_img, f"dY: {dy_mm:.1f}mm", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
        cv2.putText(vis_img, f"dR: {da_deg:.1f}deg", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
    
    out_path = img_path.replace(".jpg", "_result_final_v9.png")
    cv2.imwrite(out_path, vis_img)
    print(f"STEP 4: Saved result to {out_path}")

if __name__ == "__main__":
    run_detection()