import sys
import os

# ==========================================
# 用户配置区
# ==========================================
SINGLE_GRID_SIDE_MM = 10.0 
# 面积过滤：新图比较清晰，格子应该很明显
MIN_AREA_THRESHOLD = 500.0  
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
    """找到矩形4个点中，距离(0,0)最近的那个作为'左上角'"""
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
    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

def detect_tape_robust(img, vis_img):
    """
    V11 增强版胶带检测：
    1. 放宽红色阈值 (适应暗光)
    2. 聚合所有红色块 (解决L形断裂)
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 1. 放宽的红色范围 (S, V 下限降至 40)
    # 区间1: 0-15 (红)
    lower_red1 = np.array([0, 40, 40])
    upper_red1 = np.array([15, 255, 255])
    # 区间2: 165-180 (紫红)
    lower_red2 = np.array([165, 40, 40])
    upper_red2 = np.array([180, 255, 255])
    
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = mask1 + mask2
    
    # 2. 强力闭运算 (把L形断裂处连起来)
    # 使用 15x15 的核，只要断缝小于 15px 都会被填上
    kernel_large = np.ones((15,15), np.uint8)
    mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_CLOSE, kernel_large)
    
    # 3. 开运算 (去掉细小的噪点)
    kernel_small = np.ones((5,5), np.uint8)
    mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_OPEN, kernel_small)
    
    if DEBUG_MODE:
        # 保存红胶带的二值化掩膜，方便排查
        debug_path = "debug_tape_mask.png"
        cv2.imwrite(debug_path, mask_red)
        print(f"   -> [Debug] Tape Mask saved to {debug_path}")
    
    contours, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    valid_contours = []
    for c in contours:
        # 面积过滤：胶带通常很大，至少 > 2000
        # 过滤掉螺丝孔、反光点
        if cv2.contourArea(c) > 2000:
            valid_contours.append(c)
            
    if valid_contours:
        # 4. 聚合策略：
        # 不再只找“最大”的一个，而是把所有大的红色块都合起来算一个整体
        # 这样即使 L 形断成两半，也会被算在一起
        all_points = np.vstack(valid_contours)
        
        # 计算凸包或最小矩形
        hull = cv2.convexHull(all_points)
        rect = cv2.minAreaRect(hull)
        box = np.int32(cv2.boxPoints(rect))
        
        anchor = get_top_left_corner(box)
        angle = rect[2]
        
        # 绘图
        cv2.drawContours(vis_img, [box], 0, (0, 0, 255), 3)
        cv2.circle(vis_img, tuple(anchor), 12, (0, 0, 255), -1)
        print(f"   -> Red Tape Found (Merged): {anchor}")
        return anchor, angle
    else:
        print("   -> [WARNING] Red Tape NOT found (Area too small or threshold issue). Check 'debug_tape_mask.png'")
        return None, 0.0

def run_detection():
    print(f"STEP 1: Start Detection (V11 - Robust Tape Fix)")
    
    # 修改为你的新图片
    img_path = r"W:\CATL\Eliteroboarm\workspace\captures\image_286447.jpg"
    
    if not os.path.exists(img_path):
        # 自动回退逻辑，方便你不用每次改代码
        import glob
        # 找最新的jpg
        files = glob.glob(r"W:\CATL\Eliteroboarm\workspace\captures\*.jpg")
        if files:
            # 按时间排序取最新的
            files.sort(key=os.path.getmtime)
            img_path = files[-1]
            print(f"   -> Using latest image: {os.path.basename(img_path)}")
        else:
            print("   -> No images found.")
            return

    img = cv2.imread(img_path)
    if img is None: return
    
    vis_img = img.copy()
    print(f"STEP 2: Image Loaded.")

    # --- 阶段 1: 找基准 (V11 增强版) ---
    ref_anchor, ref_angle = detect_tape_robust(img, vis_img)

    # --- 阶段 2: 找格子 (V9 逻辑保持不变) ---
    print("STEP 3: Detecting Grid Squares...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((3,3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    raw_candidates = []
    
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA_THRESHOLD: continue
        if area > 50000: continue
        
        rect = cv2.minAreaRect(c)
        w, h = rect[1]
        if w == 0 or h == 0: continue
        aspect_ratio = min(w, h) / max(w, h)
        if aspect_ratio < 0.6: continue 
        
        hull = cv2.convexHull(c)
        solidity = area / cv2.contourArea(hull)
        if solidity < 0.7: continue
        
        raw_candidates.append(c)

    final_squares = []
    if len(raw_candidates) > 0:
        widths = [max(cv2.minAreaRect(c)[1]) for c in raw_candidates]
        avg_width = np.median(widths)
        search_radius = avg_width * 3.0
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

    # 聚合
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
        
        print(f"   -> Grid Scale: {mm_per_pixel:.5f} mm/px")
        
        cv2.drawContours(vis_img, [box_pack], 0, (0, 255, 0), 3)
        cv2.circle(vis_img, tuple(pack_anchor), 10, (0, 255, 0), -1)
    else:
        print("   -> [WARNING] Not enough squares found.")

    # --- 阶段 3: 结果计算 ---
    if ref_anchor is not None and pack_anchor is not None:
        dx_px = float(pack_anchor[0] - ref_anchor[0])
        dy_px = float(pack_anchor[1] - ref_anchor[1])
        
        dx_mm = dx_px * mm_per_pixel
        dy_mm = dy_px * mm_per_pixel
        da_deg = smart_angle_diff(pack_angle, ref_angle)
        
        print("\n" + "="*45)
        print(f"【 机械臂补偿数据 (V11) 】")
        print(f"X : {dx_mm:.2f} mm")
        print(f"Y : {dy_mm:.2f} mm")
        print(f"R : {da_deg:.2f} °")
        print("="*45 + "\n")

        cv2.putText(vis_img, f"dX: {dx_mm:.1f}mm", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.putText(vis_img, f"dY: {dy_mm:.1f}mm", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.putText(vis_img, f"dR: {da_deg:.1f}deg", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    
    out_path = img_path.replace(".jpg", "_result_final_v11.png")
    cv2.imwrite(out_path, vis_img)
    print(f"STEP 4: Saved result to {out_path}")

if __name__ == "__main__":
    run_detection()