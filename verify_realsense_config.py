"""
验证RealSense相机配置
"""
import json

with open('config/hardware_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

cameras = [c for c in config['cameras'] if c.get('brand') == 'realsense']

print('=' * 60)
print('RealSense相机配置验证')
print('=' * 60)
print(f'\n找到 {len(cameras)} 个RealSense相机配置:\n')

for cam in cameras:
    print(f"  名称: {cam['name']}")
    print(f"  ID: {cam['id']}")
    print(f"  型号: {cam.get('model', 'N/A')}")
    print(f"  连接类型: {cam.get('connection_type', 'N/A')}")
    print(f"  分辨率: {cam.get('resolution', 'N/A')}")
    print(f"  帧率: {cam.get('fps', 'N/A')}")
    print(f"  启用深度: {cam.get('enable_depth', 'N/A')}")
    print()

print('✓ RealSense相机配置验证完成')
