"""
RealSense相机驱动测试脚本
用于验证RealSense相机是否能正常工作
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from drivers.camera.realsense import RealSenseCamera
from core.services.camera_factory import CameraFactory

def test_realsense_import():
    """测试RealSense驱动导入"""
    print("=" * 60)
    print("测试1: RealSense驱动导入")
    print("=" * 60)
    try:
        camera = RealSenseCamera()
        print("✓ RealSenseCamera类创建成功")
        return True
    except Exception as e:
        print(f"✗ RealSenseCamera类创建失败: {e}")
        return False

def test_camera_factory():
    """测试相机工厂能否创建RealSense相机"""
    print("\n" + "=" * 60)
    print("测试2: 通过CameraFactory创建RealSense相机")
    print("=" * 60)
    
    config = {
        'name': 'Test RealSense',
        'brand': 'realsense',
        'connection_type': 'usb',
        'width': 640,
        'height': 480,
        'fps': 30
    }
    
    try:
        camera = CameraFactory.create_camera(config)
        if camera:
            print("✓ CameraFactory成功创建RealSenseCamera实例")
            print(f"  相机类型: {type(camera).__name__}")
            return True
        else:
            print("✗ CameraFactory返回None")
            return False
    except Exception as e:
        print(f"✗ CameraFactory创建失败: {e}")
        return False

def test_supported_brands():
    """测试RealSense是否在支持的品牌列表中"""
    print("\n" + "=" * 60)
    print("测试3: 验证RealSense在支持品牌列表中")
    print("=" * 60)
    
    supported = CameraFactory.get_supported_brands()
    print(f"支持的品牌: {list(supported.keys())}")
    
    if 'realsense' in supported:
        print(f"✓ RealSense已注册，支持的连接类型: {supported['realsense']}")
        return True
    else:
        print("✗ RealSense未在支持品牌列表中")
        return False

def test_config_validation():
    """测试配置验证"""
    print("\n" + "=" * 60)
    print("测试4: 配置验证")
    print("=" * 60)
    
    config = {
        'name': 'Test RealSense',
        'brand': 'realsense',
        'connection_type': 'usb'
    }
    
    is_supported = CameraFactory.is_config_supported(config)
    if is_supported:
        print("✓ RealSense USB配置验证通过")
        return True
    else:
        print("✗ RealSense USB配置验证失败")
        return False

def test_hardware_config():
    """测试hardware_config.json中的配置"""
    print("\n" + "=" * 60)
    print("测试5: 验证hardware_config.json配置")
    print("=" * 60)
    
    import json
    config_file = 'config/hardware_config.json'
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        realsense_cameras = [
            cam for cam in config.get('cameras', [])
            if cam.get('brand', '').lower() == 'realsense'
        ]
        
        if realsense_cameras:
            print(f"✓ 找到 {len(realsense_cameras)} 个RealSense相机配置:")
            for cam in realsense_cameras:
                print(f"  - {cam.get('name', 'Unknown')} (ID: {cam.get('id', 'Unknown')})")
            return True
        else:
            print("✗ 未找到RealSense相机配置")
            return False
    except Exception as e:
        print(f"✗ 读取配置文件失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("RealSense相机驱动集成测试")
    print("=" * 60)
    
    tests = [
        test_realsense_import,
        test_camera_factory,
        test_supported_brands,
        test_config_validation,
        test_hardware_config
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n✓ 所有测试通过！RealSense相机驱动集成成功！")
        print("\n使用说明:")
        print("1. 在相机管理界面中可以看到'RealSense深度相机'")
        print("2. 双击相机名称可以连接相机")
        print("3. 连接成功后，点击'开始预览'可以看到实时画面")
        print("4. 点击'拍照'可以捕获图像")
        print("5. RealSense相机使用固定焦距，不支持自动对焦功能")
    else:
        print(f"\n✗ {total - passed} 个测试失败，请检查错误信息")
    
    return passed == total

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
