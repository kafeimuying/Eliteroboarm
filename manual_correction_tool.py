import json
import numpy as np
import cv2
import math
import os
from scipy.spatial.transform import Rotation as R

# ================= 配置路径 =================
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_EYE_FILE = os.path.join(WORKSPACE_DIR, "T_eye_in_hand_chessboard.json")
# INTRINSICS_FILE = os.path.join(WORKSPACE_DIR, "intrinsics.json") # 暂时用不到
# DISTORTION_FILE = os.path.join(WORKSPACE_DIR, "distCoeffs.json") # 暂时用不到

def load_json_matrix(filepath, key="T"):
    """读取JSON文件中的矩阵"""
    try:
        if not os.path.exists(filepath):
            print(f"[警告] 找不到标定文件: {filepath}，将使用单位矩阵代替进行测试。")
            return np.eye(4)
            
        with open(filepath, 'r') as f:
            data = json.load(f)
            return np.array(data[key])
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return np.eye(4)

def elite_pose_to_matrix(pose_vec, is_degree=True):
    """
    将Elite机器人位姿向量 [x, y, z, rx, ry, rz] 转换为 4x4 齐次矩阵
    【修改版】检测到此机器人使用 Euler XYZ 欧拉角 (RX, RY, RZ)，而非旋转向量。
    
    Args:
        pose_vec: [x, y, z, rx, ry, rz]
                  rx, ry, rz 被视为 Euler XYZ 角度。
        is_degree: 如果 True，表示输入角度是度数。
                   如果 False，表示是弧度。
    """
    x, y, z, rx, ry, rz = pose_vec
    
    # 1. 处理位置
    
    # 2. 处理旋转 (Euler XYZ)
    angles = np.array([rx, ry, rz], dtype=np.float64)
    # R.from_euler 需要弧度 (如果 is_degree=False) 或 度数 (如果 degrees=True)
    # 但 scipy 的 degrees 参数只影响输入理解。
    # 为了统一处理，我们先确保 input 是度数或弧度传给 scipy
    
    r = R.from_euler('xyz', angles, degrees=is_degree)
    R_matrix = r.as_matrix()
    
    T = np.eye(4)
    T[:3, :3] = R_matrix
    T[:3, 3] = [x, y, z]
    return T

def matrix_to_elite_pose(matrix, is_degree=True):
    """
    将 4x4 齐次矩阵 转换回 Elite机器人位姿向量 [x, y, z, rx, ry, rz]
    【修改版】使用 Euler XYZ
    """
    x, y, z = matrix[:3, 3]
    
    R_matrix = matrix[:3, :3]
    
    # 旋转矩阵 -> Euler XYZ
    r = R.from_matrix(R_matrix)
    euler = r.as_euler('xyz', degrees=is_degree) # 返回度数或弧度
    
    return [x, y, z, euler[0], euler[1], euler[2]]

def calculate_correction(current_pose, deviation, hand_eye_matrix, is_degree=True):
    """
    核心算法：计算纠偏后的目标位姿
    
    使用完整齐次矩阵链处理旋转-平移耦合：
      T_B_F_new = T_B_F_cur @ T_F_C @ T_dev @ T_F_C_inv
    
    重要数学背景：
    ─────────────────────────────────────────────
    scipy from_euler('xyz', [rx,ry,rz]) 产生矩阵: R = Rz(rz) · Ry(ry) · Rx(rx)
    
    这意味着：
    - 修改 RX → 绕工具/body X轴旋转 (rightmost, post-multiply)
    - 修改 RZ → 绕基座/space Z轴旋转 (leftmost, pre-multiply)
    - 绕工具Z轴旋转 = post-multiply Rz(d) = 需要同时改变 RX/RY/RZ 三个角
    
    当 RY ≈ ±90° 时处于万向节锁区域，小的物理旋转会导致
    RX/RZ 值出现大幅变化。这是数学表示的固有特性，不是计算错误。
    机器人控制器内部会正确还原旋转矩阵，运动是平滑的。
    ─────────────────────────────────────────────
    """
    dx, dy, dtheta_deg = deviation
    
    # 1. 构造偏差矩阵 T_dev (相机坐标系下的移动)
    dtheta_rad = math.radians(dtheta_deg)
    cos_t = math.cos(dtheta_rad)
    sin_t = math.sin(dtheta_rad)
    
    T_dev = np.eye(4)
    # 绕相机Z轴旋转
    T_dev[0, 0] = cos_t
    T_dev[0, 1] = -sin_t
    T_dev[1, 0] = sin_t
    T_dev[1, 1] = cos_t
    # 平移 (相机XY平面)
    T_dev[0, 3] = dx
    T_dev[1, 3] = dy
    
    # 2. 完整矩阵链 (正确处理旋转与平移的耦合效应)
    # 物理含义：相机需要在自身坐标系移动 T_dev，
    # 通过手眼标定转换为法兰运动
    T_B_F_cur = elite_pose_to_matrix(current_pose, is_degree=is_degree)
    T_F_C = hand_eye_matrix
    T_F_C_inv = np.linalg.inv(T_F_C)
    
    T_B_F_new = T_B_F_cur @ T_F_C @ T_dev @ T_F_C_inv
    
    # 3. 提取新位姿 (Euler分解)
    new_pose_vec = matrix_to_elite_pose(T_B_F_new, is_degree=is_degree)
    
    # 4. 约束：锁定高度 (X轴 = 此机器人的竖直方向)
    # 矩阵链可能在X方向产生小量偏移(~2mm)来自旋转耦合，
    # 为保持安全高度，锁定X不变
    new_pose_vec[0] = current_pose[0]
    
    # 注意：不锁定任何旋转角 (RX/RY/RZ)！
    # 在 R = Rz(rz)·Ry(ry)·Rx(rx) 约定下，绕工具Z旋转需要
    # 三个Euler角同时变化。锁定任一角度都会破坏正确姿态。
    # 在 RY ≈ -90° 区域，RX和RZ会出现"大"变化(±10°级别)，
    # 这是万向节锁附近的正常现象，不影响物理运动的正确性。
    
    return new_pose_vec

# ================= 主程序测试 =================

if __name__ == "__main__":
    print("-" * 50)
    print(" Elite Robot 视觉伺服自动计算工具 (Euler兼容版)")
    print("-" * 50)
    
    # 1. 加载标定数据
    T_hand_eye = load_json_matrix(HAND_EYE_FILE, "T")
    
    # 2. 当前机器人位姿 (强烈建议使用 robot_control.py 读取的 rad 模式数据)
    # 格式: [x, y, z, rx(rad), ry(rad), rz(rad)]
    # 请填入您从上位机软件读取到的、单位为 rad 的数据
    current_robot_pose = [97.2, 298.7, 810.7, 2.070, -1.548, 1.091] # 示例数据，请替换为您实际读取的值
    
    print(f"\n1. 当前位姿 (Rad): {current_robot_pose}")
    
    # 3. 输入视觉偏差
    # 场景: 图像上物体向左移动了 50mm -> 相机需要向左追 -> dx = -50
    # 这里的 -50 必须是物理距离 (mm)，不是像素
    default_dev = [-50.0, 0.0, 0.0]
    
    print("\n2. 请输入视觉偏差 (直接回车将使用默认值: x=-50mm, y=0, r=0)")
    try:
        in_x = input("   X 偏差 (mm): ").strip()
        dev_x = float(in_x) if in_x else default_dev[0]
        
        in_y = input("   Y 偏差 (mm): ").strip()
        dev_y = float(in_y) if in_y else default_dev[1]
        
        in_r = input("   R 偏差 (deg): ").strip()
        dev_r = float(in_r) if in_r else default_dev[2]
    except ValueError:
        print("   输入无效，使用默认值。")
        dev_x, dev_y, dev_r = default_dev

    deviation = [dev_x, dev_y, dev_r]
    print(f"   -> 使用偏差: {deviation}")
    
    # 4. 计算
    # is_degree=False 表示我们从输入到输出全程使用弧度制旋转向量
    target_pose = calculate_correction(current_robot_pose, deviation, T_hand_eye, is_degree=False)
    
    # 5. 输出结果
    print("\n" + "="*40)
    print(" 计算结果 (单位: rad, 可直接用于 movel)")
    print("="*40)
    
    # 格式化输出，保留4位小数 (弧度需要更高精度)
    def fmt(p): return [round(x, 4) for x in p]
    
    print(f"原始: {fmt(current_robot_pose)}")
    print(f"目标: {fmt(target_pose)}")
    
    # 计算差异
    diff = np.array(target_pose) - np.array(current_robot_pose)
    print("\n[变化量确认]")
    print(f"XYZ 移动: {fmt(diff[:3])} mm")
    print(f"旋转向量变化: {fmt(diff[3:])} rad (模长变化: {round(np.linalg.norm(diff[3:]), 4)})")
    
    print("\n提示:")
    print("1. 请检查 '角度变化' 是否接近 0 (仅平移纠偏时，角度应基本不变)。")
    print("2. 只有当 XYZ 移动量符合预期 (约 50mm) 时，再上机运行。")