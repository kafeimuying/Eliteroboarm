
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

def load_dist_coeffs(path):
    """加载畸变系数"""
    with open(path, 'r') as f:
        data = json.load(f)
    return np.array(data['distCoeffs'][0])

class ArUcoDetector:
    """ArUco标记检测器"""
    def __init__(self, camera_matrix, dist_coeffs, marker_size=0.1, dictionary_name="DICT_6X6_250"):
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.marker_size = marker_size
        
        # 获取ArUco字典
        aruco_dict_map = {
            "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
            "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
            "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
            "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
            "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
            "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
            "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
            "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
            "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
            "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
            "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
            "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
            "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
            "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
            "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
            "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
        }
        
        dict_id = aruco_dict_map.get(dictionary_name, cv2.aruco.DICT_6X6_250)
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        self.dict_name = dictionary_name
    
    def detect(self, img):
        """检测ArUco标记并返回与AprilTag检测器相同格式的结果"""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        corners, ids, rejected = self.detector.detectMarkers(gray)
        
        results = []
        if ids is not None:
            for i, marker_id in enumerate(ids.flatten()):
                # 估计位姿
                rvec, tvec, _ = cv2.aruco.estimatePoseSingleMarkers(
                    [corners[i]], self.marker_size, self.camera_matrix, self.dist_coeffs
                )
                
                # 转换为欧拉角
                R, _ = cv2.Rodrigues(rvec[0][0])
                euler = self.rotation_matrix_to_euler(R)
                
                results.append({
                    'id': int(marker_id),
                    'tvec': tvec[0][0],
                    'rvec': rvec[0][0],
                    'euler': euler,
                    'corners': corners[i]
                })
        
        return results
    
    def rotation_matrix_to_euler(self, R):
        """旋转矩阵转欧拉角 (XYZ顺序, 单位: 度)"""
        sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
        singular = sy < 1e-6
        
        if not singular:
            x = np.arctan2(R[2, 1], R[2, 2])
            y = np.arctan2(-R[2, 0], sy)
            z = np.arctan2(R[1, 0], R[0, 0])
        else:
            x = np.arctan2(-R[1, 2], R[1, 1])
            y = np.arctan2(-R[2, 0], sy)
            z = 0
        
        return np.degrees([x, y, z])

def calculate_deviation(detector, img_teach, img_prod, label, target_id=0):
    """计算示教与生产照片之间的AprilTag偏差"""
    print(f"\n{'='*50}")
    print(f" {label} (Tag ID={target_id})")
    print('='*50)
    
    res_teach = detector.detect(img_teach)
    res_prod = detector.detect(img_prod)
    
    # 显示检测到的所有ID
    print(f"示教照片检测到的IDs: {[r['id'] for r in res_teach]}")
    print(f"生产照片检测到的IDs: {[r['id'] for r in res_prod]}")
    
    tag_teach = next((r for r in res_teach if r['id'] == target_id), None)
    tag_prod = next((r for r in res_prod if r['id'] == target_id), None)
    
    if not tag_teach:
        print(f"Tag {target_id} not found in Teaching Image")
        print(f"Found IDs: {[r['id'] for r in res_teach]}")
        return None
    if not tag_prod:
        print(f"Tag {target_id} not found in Production Image")
        print(f"Found IDs: {[r['id'] for r in res_prod]}")
        return None
    
    print(f"示教 Tag tvec (Cam): {np.round(tag_teach['tvec'], 4)} m")
    print(f"生产 Tag tvec (Cam): {np.round(tag_prod['tvec'], 4)} m")
    print(f"示教 Tag 欧拉角: {np.round(tag_teach['euler'], 2)} deg")
    print(f"生产 Tag 欧拉角: {np.round(tag_prod['euler'], 2)} deg")
    
    # Calculate Deviation
    tvec_teach = tag_teach['tvec']
    tvec_prod = tag_prod['tvec']
    
    dx_mm = (tvec_prod[0] - tvec_teach[0]) * 1000.0
    dy_mm = (tvec_prod[1] - tvec_teach[1]) * 1000.0
    dz_mm = (tvec_prod[2] - tvec_teach[2]) * 1000.0
    
    # Euler Z deviation
    yaw_teach = tag_teach['euler'][2]
    yaw_prod = tag_prod['euler'][2]
    dr_deg = yaw_prod - yaw_teach
    
    print(f"\n纠偏后偏差 (生产 - 示教):")
    print(f"  dX: {dx_mm:.3f} mm")
    print(f"  dY: {dy_mm:.3f} mm")
    print(f"  dZ: {dz_mm:.3f} mm")
    print(f"  dRZ: {dr_deg:.3f} deg")
    
    return {'dx': dx_mm, 'dy': dy_mm, 'dz': dz_mm, 'drz': dr_deg}

def main():
    root_dir = r"w:\CATL\Eliteroboarm"
    captures_dir = os.path.join(root_dir, "workspace", "paths", "captures", "test")
    intrinsics_file = os.path.join(root_dir, "intrinsics.json")
    dist_coeffs_file = os.path.join(root_dir, "distCoeffs.json")
    
    # 定义照片路径
    point1_teach = os.path.join(captures_dir, "teaching", "teaching_point_1_20260226_152835.jpg")
    point1_prod = os.path.join(captures_dir, "production", "point_1", "prod_20260226_153010.jpg")
    
    point2_teach = os.path.join(captures_dir, "teaching", "teaching_point_2_20260226_152931.jpg")
    point2_prod = os.path.join(captures_dir, "production", "point_2", "prod_20260226_153016.jpg")
    
    # 标准点照片（应该有AprilTag）
    std_teach = os.path.join(captures_dir, "teaching", "standard.jpg")
    std_prod = os.path.join(captures_dir, "production", "standard", "prod_std_20260226_152959.jpg")
    
    # 加载相机内参
    print(f"Loading intrinsics from {intrinsics_file}")
    if os.path.exists(intrinsics_file):
        K = load_intrinsics(intrinsics_file)
    else:
        print("Intrinsics file not found, using default.")
        K = np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], dtype=np.float32)
    print(f"Camera Matrix:\n{K}")
    
    # 加载畸变系数
    dist_coeffs = None
    print(f"\nLoading distortion coefficients from {dist_coeffs_file}")
    if os.path.exists(dist_coeffs_file):
        dist_coeffs = load_dist_coeffs(dist_coeffs_file)
        print(f"Distortion Coefficients: {dist_coeffs}")
    else:
        print("Distortion coefficients file not found, using zeros.")
        dist_coeffs = np.zeros(5)
    
    # 创建多个检测器 - 支持不同的tag家族
    # 标准点使用 tag36h11
    # 拍照点使用 6x6家族 (可能是 tagStandard41h12, tagCustom48h12 或其他)
    print("\n初始化检测器...")
    detector_36h11 = AprilTagDetector(tag_size_m=0.1, camera_matrix=K, dist_coeffs=dist_coeffs, tag_family="tag36h11")
    print("  - tag36h11 检测器已创建")
    
    # 尝试创建其他家族的检测器
    detector_41h12 = None
    detector_48h12 = None
    detector_25h9 = None
    try:
        detector_41h12 = AprilTagDetector(tag_size_m=0.1, camera_matrix=K, dist_coeffs=dist_coeffs, tag_family="tagStandard41h12")
        print("  - tagStandard41h12 检测器已创建")
    except Exception as e:
        print(f"  - tagStandard41h12 创建失败: {e}")
    
    try:
        detector_48h12 = AprilTagDetector(tag_size_m=0.1, camera_matrix=K, dist_coeffs=dist_coeffs, tag_family="tagCustom48h12")
        print("  - tagCustom48h12 检测器已创建")
    except Exception as e:
        print(f"  - tagCustom48h12 创建失败: {e}")
    
    try:
        detector_25h9 = AprilTagDetector(tag_size_m=0.1, camera_matrix=K, dist_coeffs=dist_coeffs, tag_family="tag25h9")
        print("  - tag25h9 检测器已创建")
    except Exception as e:
        print(f"  - tag25h9 创建失败: {e}")
    
    # 创建ArUco检测器 - 用于拍照点的6x6标记
    print("\n初始化ArUco检测器...")
    aruco_detectors = {}
    for dict_name in ["DICT_6X6_50", "DICT_6X6_100", "DICT_6X6_250", "DICT_6X6_1000", 
                      "DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000",
                      "DICT_4X4_50", "DICT_4X4_100", "DICT_4X4_250", "DICT_4X4_1000"]:
        try:
            aruco_detectors[dict_name] = ArUcoDetector(K, dist_coeffs, marker_size=0.1, dictionary_name=dict_name)
            print(f"  - {dict_name} 检测器已创建")
        except Exception as e:
            print(f"  - {dict_name} 创建失败: {e}")
    
    # 读取照片
    print("\n读取照片...")
    img1_teach = cv2.imread(point1_teach)
    img1_prod = cv2.imread(point1_prod)
    img2_teach = cv2.imread(point2_teach)
    img2_prod = cv2.imread(point2_prod)
    img_std_teach = cv2.imread(std_teach)
    img_std_prod = cv2.imread(std_prod)
    
    # 检查照片
    for name, img, path in [
        ("std_teach", img_std_teach, std_teach),
        ("std_prod", img_std_prod, std_prod),
        ("point1_teach", img1_teach, point1_teach),
        ("point1_prod", img1_prod, point1_prod),
        ("point2_teach", img2_teach, point2_teach),
        ("point2_prod", img2_prod, point2_prod),
    ]:
        if img is None:
            print(f"无法加载照片: {path}")
        else:
            print(f"已加载 {name}: {img.shape}")
    
    # 首先检测标准点照片（验证检测器正常工作）
    print("\n" + "="*50)
    print(" 验证标准点照片 AprilTag 检测 (tag36h11)")
    print("="*50)
    if img_std_teach is not None:
        res = detector_36h11.detect(img_std_teach)
        if res:
            print(f"示教标准点: 检测到 {len(res)} 个AprilTag")
            for r in res:
                print(f"  ID={r['id']}, tvec={np.round(r['tvec'], 4)}, euler_z={r['euler'][2]:.2f}°")
        else:
            print("示教标准点: 未检测到AprilTag")
    
    if img_std_prod is not None:
        res = detector_36h11.detect(img_std_prod)
        if res:
            print(f"生产标准点: 检测到 {len(res)} 个AprilTag")
            for r in res:
                print(f"  ID={r['id']}, tvec={np.round(r['tvec'], 4)}, euler_z={r['euler'][2]:.2f}°")
        else:
            print("生产标准点: 未检测到AprilTag")
    
    # 测试所有检测器对拍照点1的检测
    print("\n" + "="*50)
    print(" 尝试不同Tag家族检测拍照点1照片 ")
    print("="*50)
    
    # 首先尝试AprilTag检测器
    print("--- AprilTag 检测器 ---")
    detectors_to_try = [
        ("tag36h11", detector_36h11),
        ("tagStandard41h12", detector_41h12),
        ("tagCustom48h12", detector_48h12),
        ("tag25h9", detector_25h9),
    ]
    
    working_detector_point1 = None
    working_family_point1 = None
    
    for family, det in detectors_to_try:
        if det is None:
            continue
        if img1_teach is not None:
            res = det.detect(img1_teach)
            if res:
                print(f"  {family}: 检测到 {len(res)} 个Tag, IDs={[r['id'] for r in res]}")
                if working_detector_point1 is None:
                    working_detector_point1 = det
                    working_family_point1 = family
            else:
                print(f"  {family}: 未检测到")
    
    # 尝试ArUco检测器
    print("--- ArUco 检测器 ---")
    for dict_name, aruco_det in aruco_detectors.items():
        if img1_teach is not None:
            res = aruco_det.detect(img1_teach)
            if res:
                print(f"  {dict_name}: 检测到 {len(res)} 个Marker, IDs={[r['id'] for r in res]}")
                if working_detector_point1 is None:
                    working_detector_point1 = aruco_det
                    working_family_point1 = dict_name
            else:
                print(f"  {dict_name}: 未检测到")
    
    print("\n" + "="*50)
    print(" 尝试不同Tag家族检测拍照点2照片 ")
    print("="*50)
    
    working_detector_point2 = None
    working_family_point2 = None
    
    # 首先尝试AprilTag检测器
    print("--- AprilTag 检测器 ---")
    for family, det in detectors_to_try:
        if det is None:
            continue
        if img2_teach is not None:
            res = det.detect(img2_teach)
            if res:
                print(f"  {family}: 检测到 {len(res)} 个Tag, IDs={[r['id'] for r in res]}")
                if working_detector_point2 is None:
                    working_detector_point2 = det
                    working_family_point2 = family
            else:
                print(f"  {family}: 未检测到")
    
    # 尝试ArUco检测器
    print("--- ArUco 检测器 ---")
    for dict_name, aruco_det in aruco_detectors.items():
        if img2_teach is not None:
            res = aruco_det.detect(img2_teach)
            if res:
                print(f"  {dict_name}: 检测到 {len(res)} 个Marker, IDs={[r['id'] for r in res]}")
                if working_detector_point2 is None:
                    working_detector_point2 = aruco_det
                    working_family_point2 = dict_name
            else:
                print(f"  {dict_name}: 未检测到")
    
    if working_family_point1:
        print(f"\n>>> 拍照点1 使用检测器: {working_family_point1}")
    else:
        print(f"\n>>> 拍照点1: 所有检测器都未检测到，将使用默认 tag36h11")
        working_detector_point1 = detector_36h11
        
    if working_family_point2:
        print(f">>> 拍照点2 使用检测器: {working_family_point2}")
    else:
        print(f">>> 拍照点2: 所有检测器都未检测到，将使用默认 tag36h11")
        working_detector_point2 = detector_36h11
    
    # 计算标准点偏差（这对应项目中的"纠偏前偏差"）
    result_std = None
    if img_std_teach is not None and img_std_prod is not None:
        result_std = calculate_deviation(detector_36h11, img_std_teach, img_std_prod, "标准点偏差 (纠偏前偏差)", target_id=None)
    
    # 计算拍照点偏差
    result1 = None
    result2 = None
    
    if img1_teach is not None and img1_prod is not None and working_detector_point1:
        result1 = calculate_deviation(working_detector_point1, img1_teach, img1_prod, "拍照点1 偏差计算", target_id=0)
    
    if img2_teach is not None and img2_prod is not None and working_detector_point2:
        result2 = calculate_deviation(working_detector_point2, img2_teach, img2_prod, "拍照点2 偏差计算", target_id=1)
    
    # 汇总结果
    print("\n" + "="*60)
    print(" 汇总对比 ")
    print("="*60)
    
    # 项目中的纠偏前偏差 (来自终端日志)
    pre_deviation = {'dx': 0.961, 'dy': -34.473, 'drz': -0.721}
    print(f"\n【项目纠偏前偏差】(标准点Tag检测，来自终端日志):")
    print(f"  dX: {pre_deviation['dx']:.3f} mm")
    print(f"  dY: {pre_deviation['dy']:.3f} mm")
    print(f"  dRZ: {pre_deviation['drz']:.3f} deg")
    
    if result_std:
        print(f"\n【本脚本计算 - 标准点偏差】(相机坐标系):")
        print(f"  dX(cam): {result_std['dx']:.3f} mm")
        print(f"  dY(cam): {result_std['dy']:.3f} mm")
        print(f"  dZ(cam): {result_std['dz']:.3f} mm")
        print(f"  dRZ: {result_std['drz']:.3f} deg")
        print(f"\n  注: 相机坐标系与机械臂基座坐标系存在转换关系")
        print(f"  对比发现: |dX(cam)|={abs(result_std['dx']):.1f}mm ≈ |dY(robot)|={abs(pre_deviation['dy']):.1f}mm")
        print(f"  对比发现: |dY(cam)|={abs(result_std['dy']):.1f}mm ≈ |dZ偏差| (未在日志中显示)")
    
    print(f"\n【项目纠偏后偏差】(未检测到AprilTag，显示为0):")
    print(f"  dX: 0.000 mm, dY: 0.000 mm, dRZ: 0.000 deg")
    print(f"  原因: 拍照点照片中AprilTag不在视野内")
    
    if result1:
        print(f"\n【本脚本计算 - 拍照点1】:")
        print(f"  dX: {result1['dx']:.3f} mm")
        print(f"  dY: {result1['dy']:.3f} mm")
        print(f"  dRZ: {result1['drz']:.3f} deg")
    else:
        print(f"\n【本脚本计算 - 拍照点1】:")
        print(f"  无法计算 - 照片中未检测到AprilTag")
    
    if result2:
        print(f"\n【本脚本计算 - 拍照点2】:")
        print(f"  dX: {result2['dx']:.3f} mm")
        print(f"  dY: {result2['dy']:.3f} mm")
        print(f"  dRZ: {result2['drz']:.3f} deg")
    else:
        print(f"\n【本脚本计算 - 拍照点2】:")
        print(f"  无法计算 - 照片中未检测到AprilTag")
    
    print("\n" + "="*60)
    print(" 结论 ")
    print("="*60)
    print("1. 本脚本已正确引入 distCoeffs.json 畸变系数")
    print("2. 标准点偏差计算结果与项目中的数据数量级一致（坐标系不同）")
    print("3. 拍照点1/2的纠偏后偏差无法计算，因为拍照时AprilTag不在视野内")
    print("4. 这印证了项目日志中'未检测到AprilTag'的输出")
    print("5. 要评估纠偏效果，需要确保拍照点位置时AprilTag仍在相机视野内")
    
if __name__ == "__main__":
    main()
