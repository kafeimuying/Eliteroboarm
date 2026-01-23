import sys
import os
import time

# Add the extension directory to path
ext_dir = os.path.abspath(r"W:\CATL\Roboarm\cpp_extensions\extensions\Release")
if ext_dir not in sys.path:
    sys.path.append(ext_dir)

try:
    import elite_ext
    print("Module 'elite_ext' imported successfully.")
except ImportError as e:
    print(f"Failed to import elite_ext: {e}")
    print(f"Please ensure 'elite-cs-series-sdk.dll' is in {ext_dir} or in your PATH.")
    sys.exit(1)

def main():
    print("Testing EliteRobotController...")
    
    # Instantiate the controller
    try:
        robot = elite_ext.EliteRobotController()
        print("Controller instantiated.")
    except Exception as e:
        print(f"Failed to instantiate controller: {e}")
        return

    # Connection details
    ip = "192.168.1.200" # Update as needed
    recipe_dir = os.path.abspath("W:/CATL/Roboarm") # Assuming input/output recipes are here
    
    print(f"Attempting to connect to {ip}...")
    # Uncomment to actually connect if hardware is available
    # connected = robot.connect(ip, recipe_dir)
    # print(f"Connection result: {connected}")
    
    # if connected:
    #     pos = robot.getPosition()
    #     print(f"Position: {pos}")
    #     robot.disconnect()

if __name__ == "__main__":
    main()
