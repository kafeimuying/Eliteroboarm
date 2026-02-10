import json
import numpy as np
import cv2
import math
import os

# ================= 配置路径 =================
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_EYE_FILE = os.path.join(WORKSPACE_DIR, "T_eye_in_hand_chessboard.json")
INTRINSICS_FILE = os.path.join(WORKSPACE_DIR, "intrinsics.json")
DISTORTION_FILE = os.path.join(WORKSPACE_DIR, "distCoeffs.json")

def load_json_matrix(filepath, key="T"):
    """读取JSON文件中的矩阵"""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            return np.array(data[key])
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def pose_to_matrix(pose_vec):
    """
    将Elite机器人位姿向量 [x, y, z, rx, ry, rz] 转换为 4x4 齐次矩阵
    假设 rx, ry, rz 为旋转向量 (Rotation Vector) 格式 (单位: 弧度)
    如果 Elite使用的是欧拉角(RPY)，需要修改此处。通常工业机器人由于奇异性问题常用轴角/旋转向量。
    """
    x, y, z, rx, ry, rz = pose_vec
    # 旋转向量 -> 旋转矩阵
    R_matrix, _ = cv2.Rodrigues(np.array([rx, ry, rz]))
    
    T = np.eye(4)
    T[:3, :3] = R_matrix
    T[:3, 3] = [x, y, z]
    return T

def matrix_to_pose(matrix):
    """
    将 4x4 齐次矩阵 转换回 Elite机器人位姿向量 [x, y, z, rx, ry, rz]
    """
    x, y, z = matrix[:3, 3]
    R_matrix = matrix[:3, :3]
    # 旋转矩阵 -> 旋转向量
    rvec, _ = cv2.Rodrigues(R_matrix)
    rx, ry, rz = rvec.flatten()
    return [x, y, z, rx, ry, rz]

def calculate_correction(current_pose, deviation, hand_eye_matrix):
    """
    核心算法：计算纠偏后的目标位姿
    
    Args:
        current_pose: 当前机械臂位姿 [x, y, z, rx, ry, rz]
                      注意：XYZ单位为 mm 还是 m，需与 hand_eye_matrix 保持一致。
                      通常 Elite 使用 mm (需确认), 你的标定文件 T 看起来像 mm (平移约50).
        deviation:    视觉检测到的偏差 [dx_cam, dy_cam, d_theta_cam]
                      dx, dy 单位: mm (在相机坐标系下)
                      d_theta 单位: 度 (degree) (在相机图像平面内的旋转)
        hand_eye_matrix: 手眼标定矩阵 T_Flange_Camera
        
    Returns:
        target_pose:  新的机械臂位姿 [x, y, z, rx, ry, rz]
    """
    dx, dy, dtheta_deg = deviation
    
    # 1. 构造偏差矩阵 T_dev (相机坐标系下的移动)
    # 假设相机坐标系：Z轴向前(深度)，X轴向右，Y轴向下
    # 图像平面的旋转是绕相机Z轴旋转
    dtheta_rad = math.radians(dtheta_deg)
    
    # 构造绕Z轴旋转的矩阵
    cos_t = math.cos(dtheta_rad)
    sin_t = math.sin(dtheta_rad)
    
    # T_dev 表示：想要消除偏差，相机需要在自己的坐标系内移动多少
    # 如果工件在图像里偏右(+x)，相机也要向右移动(+x)去追它。
    T_dev = np.eye(4)
    T_dev[0, 0] = cos_t
    T_dev[0, 1] = -sin_t
    T_dev[1, 0] = sin_t
    T_dev[1, 1] = cos_t
    T_dev[0, 3] = dx
    T_dev[1, 3] = dy
    # Z轴保持不变 (假设是2D纠偏)
    
    # 2. 获取当前 T_Base_Flange
    T_B_F_curr = pose_to_matrix(current_pose)
    
    # 3. 计算链
    # T_Base_Flange_New = T_Base_Flange_Curr * T_Flange_Cam * T_Cam_Dev * T_Flange_Cam_Inv
    T_F_C = hand_eye_matrix
    T_F_C_inv = np.linalg.inv(T_F_C)
    
    T_B_F_new = T_B_F_curr @ T_F_C @ T_dev @ T_F_C_inv
    
    # 4. 转回向量
    return matrix_to_pose(T_B_F_new)

# ================= 辅助工具：像素转毫米 (含畸变校正) =================

def pixel_to_mm_ratio_calculator(measured_pixel_len, known_mm_len):
    """简单比例计算"""
    if measured_pixel_len == 0: return 0
    return known_mm_len / measured_pixel_len

def undistort_point(px, py, intrinsics, dist_coeffs):
    """
    对单个像素点进行去畸变
    intrinsics: 3x3 array
    dist_coeffs: 1x5 array
    """
    # cv2.undistortPoints 需要 shape (N, 1, 2)
    src = np.array([[[px, py]]], dtype=np.float64)
    dst = cv2.undistortPoints(src, intrinsics, dist_coeffs, P=intrinsics)
    return dst[0][0]

# ================= 主程序测试 =================

if __name__ == "__main__":
    print("-" * 50)
    print(" Elite Robot 视觉伺服手动计算工具")
    print("-" * 50)
    
    # 1. 加载标定数据
    T_hand_eye = load_json_matrix(HAND_EYE_FILE, "T")
    if T_hand_eye is None:
        print("错误：无法加载手眼标定矩阵，使用单位矩阵模拟。")
        T_hand_eye = np.eye(4)
    else:
        print("已加载手眼标定矩阵 T_Flange_Camera")
        
    # 2. 模拟/输入当前机器人位姿
    # 这里你需要填入示教器上读到的当前数值
    # 假设位姿格式: [x, y, z, rx, ry, rz] 单位 mm, rad
    # 提示：如果示教器主要显示角度(deg)，请先转为弧度
    # 示例值：
    current_robot_pose = [500.0, -300.0, 400.0, 3.14, 0.0, 0.0] 
    
    print(f"\n当前模拟位姿: {current_robot_pose}")
    print("(注意：确保单位一致，此处假设 x,y,z 为 mm，rx,ry,rz 为 旋转向量/弧度)")
    
    # 3. 手动输入视觉偏差
    print("\n--- 请输入视觉偏差 (相对于相机视野) ---")
    try:
        dev_x = float(input("请输入 X 方向偏差 (mm, 向右为正): ") or 0)
        dev_y = float(input("请输入 Y 方向偏差 (mm, 向下为正): ") or 0)
        dev_r = float(input("请输入 旋转 偏差 (度, 顺时针为正): ") or 0)
    except ValueError:
        print("输入无效，使用 0 偏差")
        dev_x, dev_y, dev_r = 0, 0, 0
        
    # 4. 计算
    target_pose = calculate_correction(current_robot_pose, [dev_x, dev_y, dev_r], T_hand_eye)
    
    # 5. 输出
    print("\n" + "="*30)
    print(" 计算结果 (Target Pose)")
    print("="*30)
    print(f"原始位姿: {[round(x, 4) for x in current_robot_pose]}")
    print(f"目标位姿: {[round(x, 4) for x in target_pose]}")
    
    print("\n增量变化:")
    delta = np.array(target_pose) - np.array(current_robot_pose)
    print(f"d_XYZ: {[round(x, 3) for x in delta[:3]]}")
    
    print("\n您可以将 '目标位姿' 输入到机器人的 movel 指令中进行测试。")
    print("提示：如果机器人实际移动方向相反，请尝试反转输入的偏差符号。")
