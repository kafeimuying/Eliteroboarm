import ctypes
import os
import sys
from typing import Optional

class EliteSDK:
    def __init__(self, dll_path: str):
        self.lib = None
        try:
            # Load the DLL
            # Note: On Windows, we might need to add the DLL directory to PATH or use os.add_dll_directory
            dll_dir = os.path.dirname(dll_path)
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(dll_dir)
            
            self.lib = ctypes.CDLL(dll_path)
            
            # Define function signatures
            
            # EliteDriverHandle Elite_Create(const char* robot_ip)
            self.lib.Elite_Create.argtypes = [ctypes.c_char_p]
            self.lib.Elite_Create.restype = ctypes.c_void_p
            
            # void Elite_Destroy(EliteDriverHandle handle)
            self.lib.Elite_Destroy.argtypes = [ctypes.c_void_p]
            self.lib.Elite_Destroy.restype = None
            
            # bool Elite_IsConnected(EliteDriverHandle handle)
            self.lib.Elite_IsConnected.argtypes = [ctypes.c_void_p]
            self.lib.Elite_IsConnected.restype = ctypes.c_bool
            
            # bool Elite_SendScript(EliteDriverHandle handle, const char* script)
            self.lib.Elite_SendScript.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            self.lib.Elite_SendScript.restype = ctypes.c_bool

            # bool Elite_GetPose(EliteDriverHandle handle, double* pose)
            self.lib.Elite_GetPose.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
            self.lib.Elite_GetPose.restype = ctypes.c_bool
            
        except Exception as e:
            print(f"Failed to load Elite Wrapper DLL: {e}")
            self.lib = None

    def create_driver(self, ip: str):
        if not self.lib: return None
        ip_bytes = ip.encode('utf-8')
        return self.lib.Elite_Create(ip_bytes)

    def destroy_driver(self, handle):
        if not self.lib or not handle: return
        self.lib.Elite_Destroy(handle)

    def is_connected(self, handle) -> bool:
        if not self.lib or not handle: return False
        return self.lib.Elite_IsConnected(handle)

    def send_script(self, handle, script: str) -> bool:
        if not self.lib or not handle: return False
        script_bytes = script.encode('utf-8')
        return self.lib.Elite_SendScript(handle, script_bytes)

    def get_pose(self, handle):
        if not self.lib or not handle: return None
        pose_array = (ctypes.c_double * 6)()
        if self.lib.Elite_GetPose(handle, pose_array):
            return list(pose_array)
        return None
