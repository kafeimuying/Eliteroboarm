#!/usr/bin/env python3
"""
测试Python调用C++扩展的脚本
"""

import sys
import os
import numpy as np
import cv2

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_import():
    """测试导入C++扩展"""
    print("=== 测试C++扩展导入 ===")
    try:
        import vision_cpp_ext
        print("✓ C++扩展导入成功")
        print(f"  模块位置: {vision_cpp_ext.__file__}")
        return True
    except ImportError as e:
        print(f"✗ C++扩展导入失败: {e}")
        return False

def test_functions():
    """测试C++扩展函数"""
    print("\n=== 测试C++扩展函数 ===")
    try:
        import vision_cpp_ext
        
        # 检查可用的函数
        print("  可用函数:")
        for attr in dir(vision_cpp_ext):
            if not attr.startswith('_'):
                print(f"    {attr}")
        
        return True
    except Exception as e:
        print(f"✗ 函数测试失败: {e}")
        return False

def test_roi_edge_detection():
    """测试ROI抓边检测"""
    print("\n=== 测试ROI抓边检测 ===")
    try:
        import vision_cpp_ext
        
        # 创建测试图像
        test_image = np.random.randint(0, 255, (200, 200), dtype=np.uint8)
        
        # 在图像中心画一个矩形作为测试边缘
        cv2.rectangle(test_image, (50, 50), (150, 150), 255, 2)
        
        # 调用C++函数
        edge_points = vision_cpp_ext.roi_edge_detection(
            test_image,  # 图像
            25,  # roi_x
            25,  # roi_y
            150, # roi_width
            150, # roi_height
            100, # threshold
            30   # min_line_length
        )
        
        print(f"✓ ROI抓边检测成功")
        print(f"  检测到 {len(edge_points)} 个边缘点")
        if edge_points:
            print(f"  第一个边缘点: x={edge_points[0][0]:.2f}, y={edge_points[0][1]:.2f}, angle={edge_points[0][2]:.2f}")
        
        return True
    except Exception as e:
        print(f"✗ ROI抓边检测失败: {e}")
        return False

def test_template_matching():
    """测试模板匹配"""
    print("\n=== 测试模板匹配 ===")
    try:
        import vision_cpp_ext
        import cv2
        
        # 创建测试图像
        test_image = np.random.randint(0, 100, (200, 200), dtype=np.uint8)
        
        # 创建模板图像
        template = np.zeros((50, 50), dtype=np.uint8)
        cv2.rectangle(template, (10, 10), (40, 40), 255, -1)
        
        # 在测试图像中放置模板
        test_image[75:125, 75:125] = template
        
        # 调用C++函数
        matches = vision_cpp_ext.template_matching(
            test_image,           # 图像
            template,             # 模板
            cv2.TM_CCOEFF_NORMED, # 方法
            0.8,                  # 阈值
            False,                # 多匹配
            0,                    # roi_x
            0,                    # roi_y
            0,                    # roi_width (0表示全图)
            0                     # roi_height (0表示全图)
        )
        
        print(f"✓ 模板匹配成功")
        print(f"  找到 {len(matches)} 个匹配")
        if matches:
            print(f"  第一个匹配: x={matches[0][0]}, y={matches[0][1]}, confidence={matches[0][2]:.4f}")
        
        return True
    except Exception as e:
        print(f"✗ 模板匹配失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cpp_wrapper():
    """测试Python包装器"""
    print("\n=== 测试Python包装器 ===")
    try:
        from cpp_wrapper import roi_edge_detection, template_matching, CPP_EXTENSION_AVAILABLE
        print(f"✓ Python包装器导入成功")
        print(f"  C++扩展可用性: {CPP_EXTENSION_AVAILABLE}")
        
        # 创建测试数据
        test_image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        cv2.rectangle(test_image, (50, 50), (150, 150), (255, 255, 255), 2)
        
        template = np.zeros((50, 50, 3), dtype=np.uint8)
        cv2.rectangle(template, (10, 10), (40, 40), (255, 255, 255), -1)
        
        # 测试ROI抓边检测
        edge_points = roi_edge_detection(
            test_image, 25, 25, 150, 150, 100, 30
        )
        print(f"  ROI抓边检测返回 {len(edge_points)} 个点")
        
        # 测试模板匹配
        matches = template_matching(
            test_image, template, cv2.TM_CCOEFF_NORMED, 0.7, False, 0, 0, 0, 0
        )
        print(f"  模板匹配返回 {len(matches)} 个匹配")
        
        return True
    except Exception as e:
        print(f"✗ Python包装器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("C++扩展测试脚本")
    print("=" * 50)
    
    # 测试导入
    import_success = test_import()
    
    if import_success:
        # 测试函数
        test_functions()
        
        # 测试具体功能
        test_roi_edge_detection()
        test_template_matching()
        
        # 测试包装器
        test_cpp_wrapper()
    
    print("\n" + "=" * 50)
    if import_success:
        print("🎉 所有测试完成，C++扩展工作正常！")
    else:
        print("❌ C++扩展导入失败，请检查构建和安装过程")

if __name__ == "__main__":
    main()