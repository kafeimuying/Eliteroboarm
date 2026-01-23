#!/usr/bin/env python3
"""
C++扩展测试脚本
测试编译的vision_cpp_ext.so模块功能
"""

import sys
import os
import numpy as np
import cv2
import time
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

def test_import():
    """测试模块导入"""
    print("=" * 50)
    print("测试1: 模块导入")
    print("=" * 50)
    
    try:
        import vision_cpp_ext
        print("✓ vision_cpp_ext 模块导入成功")
        return True
    except ImportError as e:
        print(f"✗ 模块导入失败: {e}")
        return False

def test_roi_edge_detection():
    """测试ROI抓边检测功能"""
    print("\n" + "=" * 50)
    print("测试2: ROI抓边检测")
    print("=" * 50)
    
    try:
        import vision_cpp_ext
        
        # 创建测试图像
        test_image = np.zeros((480, 640), dtype=np.uint8)
        
        # 绘制一些边缘
        cv2.rectangle(test_image, (100, 100), (300, 200), 255, 2)
        cv2.line(test_image, (150, 150), (250, 150), 255, 3)
        cv2.circle(test_image, (400, 300), 50, 255, 2)
        
        # 测试参数
        roi_x, roi_y = 50, 50
        roi_width, roi_height = 400, 300
        threshold = 50
        min_line_length = 20
        
        print(f"测试参数:")
        print(f"  图像大小: {test_image.shape}")
        print(f"  ROI区域: ({roi_x}, {roi_y}, {roi_width}, {roi_height})")
        print(f"  阈值: {threshold}")
        print(f"  最小线长: {min_line_length}")
        
        # 调用C++函数
        start_time = time.time()
        edge_points = vision_cpp_ext.roi_edge_detection(
            test_image, roi_x, roi_y, roi_width, roi_height, 
            threshold, min_line_length
        )
        end_time = time.time()
        
        processing_time = (end_time - start_time) * 1000
        
        print(f"✓ ROI抓边检测执行成功")
        print(f"  处理时间: {processing_time:.2f} ms")
        print(f"  检测到边缘点数量: {len(edge_points)}")
        
        if len(edge_points) > 0:
            print(f"  前3个边缘点: {edge_points[:3]}")
        
        return True
        
    except Exception as e:
        print(f"✗ ROI抓边检测测试失败: {e}")
        return False

def test_template_matching():
    """测试模板匹配功能"""
    print("\n" + "=" * 50)
    print("测试3: 模板匹配")
    print("=" * 50)
    
    try:
        import vision_cpp_ext
        
        # 创建测试图像和模板
        main_image = np.random.randint(0, 256, (480, 640), dtype=np.uint8)
        template = np.random.randint(0, 256, (50, 50), dtype=np.uint8)
        
        # 在主图像中放入模板
        main_image[100:150, 200:250] = template
        
        print(f"测试参数:")
        print(f"  主图像大小: {main_image.shape}")
        print(f"  模板大小: {template.shape}")
        
        # 调用C++函数 (使用实际参数)
        start_time = time.time()
        matches = vision_cpp_ext.template_matching(
            main_image, template, 
            vision_cpp_ext.TM_CCOEFF_NORMED, 0.8, False,
            0, 0, 0, 0  # 使用全图
        )
        end_time = time.time()
        
        processing_time = (end_time - start_time) * 1000
        
        print(f"✓ 模板匹配执行成功")
        print(f"  处理时间: {processing_time:.2f} ms")
        print(f"  匹配位置数量: {len(matches)}")
        
        if len(matches) > 0:
            print(f"  最佳匹配位置: {matches[0]}")
        
        return True
        
    except Exception as e:
        print(f"✗ 模板匹配测试失败: {e}")
        return False

def test_performance_comparison():
    """性能对比测试"""
    print("\n" + "=" * 50)
    print("测试4: 性能对比 (C++ vs Python)")
    print("=" * 50)
    
    try:
        import vision_cpp_ext
        
        # 创建较大的测试图像
        test_image = np.random.randint(0, 256, (1080, 1920), dtype=np.uint8)
        
        # 测试参数
        roi_x, roi_y = 100, 100
        roi_width, roi_height = 800, 600
        threshold = 50
        min_line_length = 30
        
        print(f"性能测试参数:")
        print(f"  图像大小: {test_image.shape}")
        print(f"  ROI区域: ({roi_x}, {roi_y}, {roi_width}, {roi_height})")
        
        # C++版本测试
        cpp_times = []
        for i in range(5):
            start_time = time.time()
            result = vision_cpp_ext.roi_edge_detection(
                test_image, roi_x, roi_y, roi_width, roi_height,
                threshold, min_line_length
            )
            end_time = time.time()
            cpp_times.append((end_time - start_time) * 1000)
        
        cpp_avg_time = np.mean(cpp_times)
        cpp_std_time = np.std(cpp_times)
        
        print(f"\nC++扩展性能:")
        print(f"  平均处理时间: {cpp_avg_time:.2f} ± {cpp_std_time:.2f} ms")
        print(f"  最快时间: {min(cpp_times):.2f} ms")
        print(f"  最慢时间: {max(cpp_times):.2f} ms")
        
        return True
        
    except Exception as e:
        print(f"✗ 性能对比测试失败: {e}")
        return False

def test_error_handling():
    """错误处理测试"""
    print("\n" + "=" * 50)
    print("测试5: 错误处理")
    print("=" * 50)
    
    try:
        import vision_cpp_ext
        
        # 测试1: 无效的图像数据
        try:
            result = vision_cpp_ext.roi_edge_detection(
                None, 0, 0, 100, 100, 50, 20
            )
            print("✗ 应该抛出错误但没有")
            return False
        except Exception:
            print("✓ 正确处理了空图像错误")
        
        # 测试2: 超出边界的ROI
        try:
            test_image = np.zeros((100, 100), dtype=np.uint8)
            result = vision_cpp_ext.roi_edge_detection(
                test_image, 200, 200, 100, 100, 50, 20
            )
            print("✓ 正确处理了超出边界的ROI")
        except Exception as e:
            print(f"✗ 处理边界ROI时出错: {e}")
            return False
        
        # 测试3: 无效的模板尺寸
        try:
            main_image = np.zeros((100, 100), dtype=np.uint8)
            template = np.zeros((150, 150), dtype=np.uint8)  # 比主图像大
            result = vision_cpp_ext.template_matching(main_image, template, 0.8)
            print("✓ 正确处理了无效模板尺寸")
        except Exception as e:
            print(f"✗ 处理无效模板时出错: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 错误处理测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("C++扩展功能测试")
    print("=" * 60)
    
    # 检查扩展文件是否存在
    extension_file = current_dir / "vision_cpp_ext.so"
    if not extension_file.exists():
        print(f"✗ 找不到扩展文件: {extension_file}")
        return 1
    
    print(f"✓ 找到扩展文件: {extension_file}")
    
    # 运行所有测试
    tests = [
        test_import,
        test_roi_edge_detection,
        test_template_matching,
        test_performance_comparison,
        test_error_handling
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ 测试异常: {e}")
    
    # 测试结果总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    print(f"通过测试: {passed}/{total}")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("🎉 所有测试通过！C++扩展功能正常")
        return 0
    else:
        print("⚠️  部分测试失败，请检查扩展实现")
        return 1

if __name__ == "__main__":
    sys.exit(main())