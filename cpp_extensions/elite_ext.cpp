#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <Elite/DashboardClient.hpp>
#include <Elite/PrimaryPortInterface.hpp>
#include <Elite/RtsiIOInterface.hpp>
#include <Elite/DataType.hpp>
#include <iostream>
#include <fstream>
#include <thread>
#include <vector>
#include <cmath>
#include <string>
#include <sstream>
#include <iomanip>
#include <array>

namespace py = pybind11;
using namespace ELITE;

// ==========================================
// Minimal 3D Math Helpers for Rotation Logic
// ==========================================
struct Vec3
{
    double x, y, z;
    Vec3 operator+(const Vec3 &o) const { return {x + o.x, y + o.y, z + o.z}; }
    Vec3 operator-(const Vec3 &o) const { return {x - o.x, y - o.y, z - o.z}; }
    Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
    double dot(const Vec3 &o) const { return x * o.x + y * o.y + z * o.z; }
    Vec3 cross(const Vec3 &o) const { return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x}; }
    double length() const { return std::sqrt(x * x + y * y + z * z); }
    Vec3 normalize() const
    {
        double l = length();
        if (l < 1e-9)
            return {0, 0, 1};
        return {x / l, y / l, z / l};
    }
};

// Convert Rotation Matrix (column major or orthonormal vectors) to Axis-Angle Vector (Rx, Ry, Rz)
// R = [Xx Yx Zx]
//     [Xy Yy Zy]
//     [Xz Yz Zz]
std::vector<double> matrixToRotVec(const Vec3 &X, const Vec3 &Y, const Vec3 &Z)
{
    // Rotation Matrix elements
    double r11 = X.x, r12 = Y.x, r13 = Z.x;
    double r21 = X.y, r22 = Y.y, r23 = Z.y;
    double r31 = X.z, r32 = Y.z, r33 = Z.z;

    double trace = r11 + r22 + r33;
    double theta = 0.0;
    Vec3 axis = {0, 0, 0};

    if (trace >= 3.0 - 1e-6)
    {
        // Identity
        return {0, 0, 0};
    }
    else if (trace <= -1.0 + 1e-6)
    {
        // 180 degree rotation singularity
        theta = 3.141592653589793;
        if (r11 > r22 && r11 > r33)
            axis = {std::sqrt((r11 + 1) / 2), (r12 + r21) / (2 * std::sqrt((r11 + 1) / 2)), (r13 + r31) / (2 * std::sqrt((r11 + 1) / 2))};
        else if (r22 > r33)
            axis = {(r12 + r21) / (2 * std::sqrt((r22 + 1) / 2)), std::sqrt((r22 + 1) / 2), (r23 + r32) / (2 * std::sqrt((r22 + 1) / 2))};
        else
            axis = {(r13 + r31) / (2 * std::sqrt((r33 + 1) / 2)), (r23 + r32) / (2 * std::sqrt((r33 + 1) / 2)), std::sqrt((r33 + 1) / 2)};
    }
    else
    {
        theta = std::acos((trace - 1.0) / 2.0);
        double s = 2.0 * std::sin(theta);
        axis.x = (r32 - r23) / s;
        axis.y = (r13 - r31) / s;
        axis.z = (r21 - r12) / s;
    }

    axis = axis.normalize();
    return {axis.x * theta, axis.y * theta, axis.z * theta};
}

// Convert Axis-Angle (Rx, Ry, Rz) to Matrix (X, Y, Z vectors)
void rotVecToMatrix(double rx, double ry, double rz, Vec3 &X, Vec3 &Y, Vec3 &Z)
{
    double theta = std::sqrt(rx * rx + ry * ry + rz * rz);
    if (theta < 1e-6)
    {
        X = {1, 0, 0};
        Y = {0, 1, 0};
        Z = {0, 0, 1};
        return;
    }

    double kx = rx / theta;
    double ky = ry / theta;
    double kz = rz / theta;

    double c = std::cos(theta);
    double s = std::sin(theta);
    double v = 1 - c;

    X = {kx * kx * v + c, kx * ky * v - kz * s, kx * kz * v + ky * s};
    Y = {kx * ky * v + kz * s, ky * ky * v + c, ky * kz * v - kx * s};
    Z = {kx * kz * v - ky * s, ky * kz * v + kx * s, kz * kz * v + c};
}
// ==========================================

// 9-Point Grid Configuration
const double GRID_STEP = 0.05; // 50mm spacing
const double MOVE_SPEED = 0.2; // m/s
const double MOVE_ACCEL = 0.5; // m/s^2

// Unified Robot Interface Class
class EliteRobotController
{
private:
    std::string robot_ip;
    std::unique_ptr<DashboardClient> dashboard;
    std::unique_ptr<PrimaryPortInterface> primary;
    std::unique_ptr<RtsiIOInterface> rtsi;
    bool is_connected = false;
    double global_speed = 0.5; // 0.0 - 1.0

public:
    EliteRobotController() {}

    ~EliteRobotController()
    {
        disconnect();
    }

    // 1. Connection Management
    bool connect(const std::string &ip, const std::string &recipe_dir)
    {
        robot_ip = ip;
        // Construct paths for recipe files
        std::string out_recipe = recipe_dir + "/output_recipe.txt";
        std::string in_recipe = recipe_dir + "/input_recipe.txt";

        try
        {
            dashboard = std::make_unique<DashboardClient>();
            primary = std::make_unique<PrimaryPortInterface>();
            // Update rtsi to use the correct recipe paths if needed, here assuming files exist
            rtsi = std::make_unique<RtsiIOInterface>(out_recipe, in_recipe, 250);

            bool db_ok = dashboard->connect(ip);
            bool pri_ok = primary->connect(ip);
            bool rtsi_ok = rtsi->connect(ip);

            if (db_ok && pri_ok)
            { // RTSI might be optional or retryable
                is_connected = true;
                // Init Robot
                dashboard->powerOn();
                std::this_thread::sleep_for(std::chrono::seconds(2));
                dashboard->brakeRelease();
                return true;
            }
        }
        catch (...)
        {
            return false;
        }
        return false;
    }

    void disconnect()
    {
        if (primary)
            primary->disconnect();
        if (rtsi)
            rtsi->disconnect();
        if (dashboard)
            dashboard->disconnect();
        is_connected = false;
    }

    bool isConnected() const { return is_connected; }

    // 2. State & Position
    // Returns [x, y, z, rx, ry, rz] in mm and degrees
    std::vector<double> getPosition()
    {
        if (!rtsi || !rtsi->isConnected())
            return {};

        auto pose = rtsi->getActualTCPPose(); // Returns m, rad
        if (pose.size() < 6)
            return {};

        std::vector<double> ret(6);
        ret[0] = pose[0] * 1000.0; // m -> mm
        ret[1] = pose[1] * 1000.0;
        ret[2] = pose[2] * 1000.0;
        ret[3] = pose[3] * 57.29578; // rad -> deg
        ret[4] = pose[4] * 57.29578;
        ret[5] = pose[5] * 57.29578;
        return ret;
    }

    std::string getRobotState()
    {
        if (!dashboard)
            return "Unknown";
        // This is a simplification; authentic state would query robot status
        return is_connected ? "Connected" : "Disconnected";
    }

    // 3. Motion Control
    void setSpeed(double percent)
    {
        global_speed = std::max(0.01, std::min(1.0, percent / 100.0));
        // Also send speed command to dashboard if supported
        if (dashboard)
        {
            dashboard->setSpeedScaling((int)percent);
        }
    }

    // Jog: axis (0=X, 1=Y...), direction (+1/-1), distance (mm)
    bool jog(int axis, int direction, double distance_mm)
    {
        if (!is_connected || !primary)
            return false;

        // Current Pose
        auto current_pose = rtsi->getActualTCPPose();
        if (current_pose.size() < 6)
            return false;

        // Calculate Target in Base Frame (Simplified logic)
        // Note: Real jogging might need 'pose_trans' or 'pose_add' based on tool/base frame
        // Here we assume Base Frame jogging for simplicity or use script command

        double dist_m = distance_mm / 1000.0;
        double speed_val = global_speed;

        // Generating Script
        // movel(pose_add(get_actual_tcp_pose(), p[dx, dy, dz, 0, 0, 0]), ...)

        double offsets[6] = {0, 0, 0, 0, 0, 0};
        if (axis >= 0 && axis < 3)
        {
            offsets[axis] = direction * dist_m;
        }

        std::stringstream ss;
        ss << "movel(pose_add(get_actual_tcp_pose(), [";
        for (int i = 0; i < 6; ++i)
            ss << offsets[i] << (i < 5 ? "," : "");
        ss << "]), a=0.5, v=" << speed_val << ")";

        return primary->sendScript(ss.str());
    }

    // MoveTo: x,y,z (mm), rx,ry,rz (deg)
    bool moveTo(double x, double y, double z, double rx, double ry, double rz)
    {
        if (!is_connected || !primary)
            return false;

        std::stringstream ss;
        // Use list [...] instead of p[...] to avoid builtin_function subscript error
        ss << "movel(["
           << x / 1000.0 << "," << y / 1000.0 << "," << z / 1000.0 << ","
           << rx / 57.29578 << "," << ry / 57.29578 << "," << rz / 57.29578
           << "], a=0.5, v=" << global_speed << ")";

        return primary->sendScript(ss.str());
    }

    bool stop()
    {
        if (!primary)
            return false;
        return primary->sendScript("stopj(2.0)");
    }

    // 4. Calibration (Example)
    bool runCalibrationStep(int point_id)
    {
        // Logic for moving to calibration point 'point_id'
        return true;
    }
};

class EliteCalibration
{
public:
    EliteCalibration() {}
    EliteRobotController controller; // Reuse the controller logic if needed or keep separate

    // Helper: Convert vector to string for script
    std::string vecToString(const vector6d_t &vec)
    {
        std::stringstream ss;
        ss << "[";
        for (int i = 0; i < 6; ++i)
        {
            ss << vec[i] << (i < 5 ? "," : "");
        }
        ss << "]";
        return ss.str();
    }

    bool connect(const std::string &ip, const std::string &recipe_dir)
    {
        robot_ip = ip;
        // Construct paths for recipe files
        std::string out_recipe = recipe_dir + "/output_recipe.txt";
        std::string in_recipe = recipe_dir + "/input_recipe.txt";

        // Dashboard and Primary only (No RTSI)
        dashboard = std::make_unique<DashboardClient>();
        primary = std::make_unique<PrimaryPortInterface>();

        bool db_connected = dashboard->connect(ip);
        bool pri_connected = primary->connect(ip);

        return db_connected && pri_connected;
    }

    void disconnect()
    {
        if (primary)
            primary->disconnect();
        if (dashboard)
            dashboard->disconnect();
    }

    void run_calibration(const std::function<void(std::string)> &log_callback,
                         const std::function<void(int)> &capture_callback,
                         const std::function<std::vector<double>()> &get_pose_callback)
    {
        auto log = [&](const std::string &msg)
        {
            if (log_callback)
                log_callback(msg);
            else
                std::cout << msg << std::endl;
        };

        if (!dashboard || !primary)
        {
            log("Error: Not connected (nullptr check)");
            return;
        }

        // Helper to get current pose in Meters/Radians from Python
        auto get_current_pose_m_rad = [&]() -> vector6d_t
        {
            if (!get_pose_callback)
                return {0, 0, 0, 0, 0, 0};

            // Call into Python (GIL re-acquired automatically)
            std::vector<double> p = get_pose_callback();

            if (p.size() < 6)
                return {0, 0, 0, 0, 0, 0};
            vector6d_t ret;
            // Convert mm -> m, deg -> rad
            ret[0] = p[0] / 1000.0;
            ret[1] = p[1] / 1000.0;
            ret[2] = p[2] / 1000.0;
            ret[3] = p[3] / 57.29578;
            ret[4] = p[4] / 57.29578;
            ret[5] = p[5] / 57.29578;
            return ret;
        };

        // Ensure Robot is Ready
        if (!dashboard->powerOn())
        {
            log("Failed to power on");
            return;
        }
        if (!dashboard->brakeRelease())
        {
            log("Failed to release brake");
            return;
        }

        log("[C++] Starting 9-Point Calibration (YOZ Plane, Lens X+)...");
        log("Using External Pose Data from Python (RTSI Bypass)");

        // Get center point (Current Pose)
        vector6d_t center_pose = get_current_pose_m_rad();
        double cx = center_pose[0];
        double cy = center_pose[1];
        double cz = center_pose[2];

        std::vector<vector6d_t> points;
        std::vector<std::string> data_lines;

        std::vector<double> steps = {-GRID_STEP, 0, GRID_STEP};

        for (double dz : steps)
        {
            for (double dy : steps)
            {
                vector6d_t p = center_pose;
                p[1] = cy + dy;
                p[2] = cz + dz;
                points.push_back(p);
            }
        }

        for (size_t i = 0; i < points.size(); ++i)
        {
            int point_idx = i + 1;
            std::stringstream ss;
            ss << "Moving to Point " << point_idx;
            log(ss.str());

            std::string script = "movel(" + vecToString(points[i]) + ", a=" + std::to_string(MOVE_ACCEL) + ", v=" + std::to_string(MOVE_SPEED) + ")\n";
            primary->sendScript(script);

            // Wait for arrival
            int timeout = 100; // 10 seconds
            while (timeout > 0)
            {
                vector6d_t cur = get_current_pose_m_rad();
                double dist_sq = 0;
                for (int k = 0; k < 3; ++k)
                    dist_sq += std::pow(cur[k] - points[i][k], 2);

                if (std::sqrt(dist_sq) < 0.002)
                    break;

                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                timeout--;
            }

            if (timeout <= 0)
            {
                log("Timeout waiting for robot to reach point");
                break;
            }

            // Wait for stability
            std::this_thread::sleep_for(std::chrono::milliseconds(500));

            auto current_pose = get_current_pose_m_rad();

            std::stringstream data_ss;
            data_ss << point_idx << ", "
                    << std::fixed << std::setprecision(6) << current_pose[0] << ", "
                    << current_pose[1] << ", " << current_pose[2] << ", "
                    << current_pose[3] << ", " << current_pose[4] << ", " << current_pose[5];

            data_lines.push_back(data_ss.str());
            log("Point " + std::to_string(point_idx) + " Data: " + data_ss.str());

            log("Triggering Camera Capture (Callback)...");
            if (capture_callback)
            {
                try
                {
                    capture_callback(point_idx);
                }
                catch (const std::exception &e)
                {
                    log(std::string("Capture callback error: ") + e.what());
                }
            }
            log("Capture Done.");
        }

        // Save Data to File
        std::string filename = "workspace/calibration_data.txt";
        std::ofstream outfile(filename);
        if (outfile.is_open())
        {
            outfile << "PointID, X, Y, Z, Rx, Ry, Rz\n";
            for (const auto &line : data_lines)
                outfile << line << "\n";
            outfile.close();
            log("Calibration data saved to: " + filename);
        }
        else
        {
            log("Failed to open file for writing: " + filename);
        }

        log("Calibration finished. Returning to center...");
        std::string script_home = "movel(" + vecToString(center_pose) + ", a=0.5, v=0.2)\n";
        primary->sendScript(script_home);
    }

    void run_3d_calibration(int layers,
                            double base_width, double top_width, double height, double tilt_angle,
                            std::string direction,
                            const std::function<void(std::string)> &log_callback,
                            const std::function<void(int)> &capture_callback,
                            const std::function<std::vector<double>()> &get_pose_callback)
    {
        // Simple Logger Wrapper
        auto log = [&](const std::string &msg)
        {
            if (log_callback)
                log_callback(msg);
            else
                std::cout << msg << std::endl;
        };

        if (!dashboard || !primary)
        {
            log("Error: Not connected (nullptr check)");
            return;
        }

        // Helper to get current pose in Meters/Radians from Python
        auto get_current_pose_m_rad = [&]() -> vector6d_t
        {
            if (!get_pose_callback)
                return {0, 0, 0, 0, 0, 0};

            // Call into Python (GIL re-acquired automatically)
            std::vector<double> p = get_pose_callback();

            if (p.size() < 6)
                return {0, 0, 0, 0, 0, 0};
            vector6d_t ret;
            // Convert mm -> m, deg -> rad
            ret[0] = p[0] / 1000.0;
            ret[1] = p[1] / 1000.0;
            ret[2] = p[2] / 1000.0;
            ret[3] = p[3] / 57.29578; // 180 / PI approx
            ret[4] = p[4] / 57.29578;
            ret[5] = p[5] / 57.29578;
            return ret;
        };

        // Ensure Robot is Ready
        if (!dashboard->powerOn())
        {
            log("Failed to power on");
            return;
        }
        if (!dashboard->brakeRelease())
        {
            log("Failed to release brake");
            return;
        }

        log("[C++] Starting 3D Pyramid Calibration...");
        std::stringstream info_ss;
        info_ss << "Layers: " << layers << ", Base: " << base_width << ", Top: " << top_width
                << ", Height: " << height << ", Tilt: " << tilt_angle << ", Dir: " << direction;
        log(info_ss.str());

        // Get center point (Current Pose)
        vector6d_t center_pose = get_current_pose_m_rad();

        std::vector<vector6d_t> points;
        std::vector<std::string> data_lines;

        // Convert inputs mm -> m, deg -> rad
        double base_width_m = base_width / 1000.0;
        double top_width_m = top_width / 1000.0;
        double height_m = height / 1000.0;
        double tilt_rad = tilt_angle / 57.29578;

        // Direction Logic Configuration
        int ax_h = 2;  // Height Axis (Default Z)
        int ax_w1 = 0; // Width 1 Axis (Default X)
        int ax_w2 = 1; // Width 2 Axis (Default Y)
        int ax_r1 = 3; // Rotation 1 Axis (RX) - Changed by w2
        int ax_r2 = 4; // Rotation 2 Axis (RY) - Changed by w1
        double h_sign = 1.0;

        if (direction == "Z+")
        {
            ax_h = 2;
            ax_w1 = 0;
            ax_w2 = 1;
            ax_r1 = 3;
            ax_r2 = 4;
            h_sign = 1.0;
        }
        else if (direction == "Z-")
        {
            ax_h = 2;
            ax_w1 = 0;
            ax_w2 = 1;
            ax_r1 = 3;
            ax_r2 = 4;
            h_sign = -1.0;
        }
        else if (direction == "Y+")
        {
            ax_h = 1;
            ax_w1 = 0;
            ax_w2 = 2;
            ax_r1 = 3;
            ax_r2 = 5;
            h_sign = 1.0; // Base: XZ. Rot: RX, RZ
        }
        else if (direction == "Y-")
        {
            ax_h = 1;
            ax_w1 = 0;
            ax_w2 = 2;
            ax_r1 = 3;
            ax_r2 = 5;
            h_sign = -1.0;
        }
        else if (direction == "X+")
        {
            ax_h = 0;
            ax_w1 = 1;
            ax_w2 = 2;
            ax_r1 = 4;
            ax_r2 = 5;
            h_sign = 1.0; // Base: YZ. Rot: RY, RZ
        }
        else if (direction == "X-")
        {
            ax_h = 0;
            ax_w1 = 1;
            ax_w2 = 2;
            ax_r1 = 4;
            ax_r2 = 5;
            h_sign = -1.0;
        }

        // Corner signs for [w1, w2]
        // 修正遍历顺序：左下、左上、右上、右下
        double corner_signs[4][2] = {
            {-1.0, -1.0}, // corner 0: 左下
            {-1.0, 1.0},  // corner 1: 左上（修正）
            {1.0, 1.0},   // corner 2: 右上
            {1.0, -1.0}}; // corner 3: 右下（修正）

        std::vector<vector6d_t> targets;

        // Simpler Implementation: No Rotation Logic
        // We do NOT use LookAt or Tilt.
        // Orientation is kept identical to center_pose.

        for (int i = 0; i < layers; ++i)
        {
            double ratio = 0.0;
            if (layers > 1)
                ratio = (double)i / (double)(layers - 1);

            double layer_z_offset = height_m * ratio * h_sign;
            double current_width = base_width_m - (base_width_m - top_width_m) * ratio;
            double half_w = current_width / 2.0;

            for (int k = 0; k < 4; ++k)
            {
                vector6d_t p = center_pose;

                // Apply Height
                p[ax_h] += layer_z_offset;

                // Apply Widths
                double d_w1 = corner_signs[k][0] * half_w;
                double d_w2 = corner_signs[k][1] * half_w;
                p[ax_w1] += d_w1;
                p[ax_w2] += d_w2;

                // Fixed Orientation (No rotation changes)
                p[3] = center_pose[3];
                p[4] = center_pose[4];
                p[5] = center_pose[5];

                targets.push_back(p);
            }
        }

        // Execute Motion
        for (size_t i = 0; i < targets.size(); ++i)
        {
            int point_idx = i + 1;
            std::stringstream ss;
            ss << "Processing Point " << point_idx << " (" << (i + 1) << "/" << targets.size() << ")";
            log(ss.str());

            // 1. Move to Base Point (Grid Position, Fixed Orientation)
            std::string script = "movel(" + vecToString(targets[i]) + ", a=" + std::to_string(MOVE_ACCEL) + ", v=" + std::to_string(MOVE_SPEED) + ")\n";
            primary->sendScript(script);

            // Wait for Base Arrival
            int timeout = 200;
            while (timeout > 0)
            {
                vector6d_t cur = get_current_pose_m_rad();
                double dist_sq = 0;
                for (int k = 0; k < 3; ++k)
                    dist_sq += std::pow(cur[k] - targets[i][k], 2);
                if (std::sqrt(dist_sq) < 0.002)
                    break;
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                timeout--;
            }

            // 2. Apply Inward Tilt (法兰盘向心倾斜)
            // 计算当前点在金字塔中的位置
            int layer_idx = i / 4;  // 哪一层 (0, 1, 2, ...)
            int corner_idx = i % 4; // 哪个角 (0=左下, 1=右下, 2=右上, 3=左上)

            vector6d_t p_dither = targets[i];

            // 倾斜幅度：底层倾斜大，顶层倾斜小（因为顶层更接近中心）
            double ratio = (layers > 1) ? (double)layer_idx / (double)(layers - 1) : 0.0;
            double tilt_magnitude = (tilt_angle / 57.29578) * (1.0 - ratio * 0.6); // 使用UI设置的角度，顶层减少60%

            // 获取角点在base平面的相对位置符号
            double sign_w1 = corner_signs[corner_idx][0]; // -1 (左) or +1 (右)
            double sign_w2 = corner_signs[corner_idx][1]; // -1 (下) or +1 (上)

            // 向心倾斜逻辑：
            // - w1方向 (X轴): 影响 ax_r2 (RY旋转)
            // - w2方向 (Y轴): 影响 ax_r1 (RX旋转)
            // 符号规则：负方向的点需要正向倾斜才能指向中心
            // 修正：corner 1和3需要反向倾斜
            double sign_modifier = (corner_idx == 1 || corner_idx == 3) ? -1.0 : 1.0;
            p_dither[ax_r1] += -sign_w2 * tilt_magnitude * sign_modifier; // Y轴位置影响RX倾斜
            p_dither[ax_r2] += -sign_w1 * tilt_magnitude * sign_modifier; // X轴位置影响RY倾斜

            // 添加微小RZ扰动以增加姿态多样性（可选）
            p_dither[ax_r2 + 1] += (corner_idx % 2 == 0 ? 2.0 : -2.0) * (1.0 / 57.29578); // ±2度RZ扰动

            // Tiny Z shift to help MoveL interpolation
            p_dither[2] += 0.0001;

            log(" - Adjusting Orientation...");
            std::string script_dither = "movel(" + vecToString(p_dither) + ", a=0.5, v=0.1)\n"; // Slower for adjustment
            primary->sendScript(script_dither);

            // Wait for Dither Arrival (Check Rotation too)
            timeout = 50;
            while (timeout > 0)
            {
                vector6d_t cur = get_current_pose_m_rad();
                double dist_sq = 0;
                // Check XYZ
                for (int k = 0; k < 3; ++k)
                    dist_sq += std::pow(cur[k] - p_dither[k], 2);
                // Check Rot (approx)
                double rot_sq = 0;
                for (int k = 3; k < 6; ++k)
                    rot_sq += std::pow(cur[k] - p_dither[k], 2);

                if (std::sqrt(dist_sq) < 0.002 && std::sqrt(rot_sq) < 0.05)
                    break;

                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                timeout--;
            }

            // Stabilization before Capture (统一1.5秒)
            std::this_thread::sleep_for(std::chrono::milliseconds(1500));

            // 3. Capture (At Dithered Pose)
            auto current_pose = get_current_pose_m_rad();
            std::stringstream data_ss;
            data_ss << point_idx << ", "
                    << std::fixed << std::setprecision(6) << current_pose[0] << ", "
                    << current_pose[1] << ", " << current_pose[2] << ", "
                    << current_pose[3] << ", " << current_pose[4] << ", " << current_pose[5];

            data_lines.push_back(data_ss.str());
            log("Point " + std::to_string(point_idx) + " Data: " + data_ss.str());

            log("Triggering Capture...");
            if (capture_callback)
            {
                try
                {
                    capture_callback(point_idx);
                }
                catch (const std::exception &e)
                {
                    log(std::string("Capture error: ") + e.what());
                }
            }

            // 4. Restore to Base (Optional, but user requested "Restore")
            log(" - Restoring...");
            primary->sendScript(script); // Reuse base script

            // Wait for Restore
            timeout = 50;
            while (timeout > 0)
            {
                vector6d_t cur = get_current_pose_m_rad();
                double dist_sq = 0;
                for (int k = 0; k < 3; ++k)
                    dist_sq += std::pow(cur[k] - targets[i][k], 2);
                if (std::sqrt(dist_sq) < 0.002)
                    break;
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                timeout--;
            }
        }

        // Save Data
        std::string filename = "workspace/calibration_3d_data.txt";
        std::ofstream outfile(filename);
        if (outfile.is_open())
        {
            outfile << "PointID, X, Y, Z, Rx, Ry, Rz\n";
            for (const auto &line : data_lines)
                outfile << line << "\n";
            outfile.close();
            log("3D Calibration data saved to: " + filename);
        }
        else
        {
            log("Failed to open file: " + filename);
        }

        log("Calibration finished. Returning to center...");
        std::string script_home = "movel(" + vecToString(center_pose) + ", a=0.5, v=0.2)\n";
        primary->sendScript(script_home);
    }

private:
    std::string robot_ip;
    std::unique_ptr<DashboardClient> dashboard;
    std::unique_ptr<PrimaryPortInterface> primary;
    // RTSI removed
};

PYBIND11_MODULE(elite_ext, m)
{
    m.doc() = "Elite Robot C++ Extensions with Unified Interface";

    // Bind the Unified Controller Class
    py::class_<EliteRobotController>(m, "EliteRobotController")
        .def(py::init<>())
        .def("connect", &EliteRobotController::connect, "Connect to robot", py::arg("ip"), py::arg("recipe_dir") = "config")
        .def("disconnect", &EliteRobotController::disconnect, "Disconnect from robot")
        .def("is_connected", &EliteRobotController::isConnected, "Check connection status")
        .def("get_position", &EliteRobotController::getPosition, "Get current position [x,y,z,rx,ry,rz] (mm, deg)")
        .def("set_speed", &EliteRobotController::setSpeed, "Set global speed percent (0-100)")
        .def("jog", &EliteRobotController::jog, "Jog robot axis", py::arg("axis"), py::arg("direction"), py::arg("distance_mm"))
        .def("move_to", &EliteRobotController::moveTo, "Move to target pose (mm, deg)")
        .def("stop", &EliteRobotController::stop, "Emergency stop");

    py::class_<EliteCalibration>(m, "EliteCalibration")
        .def(py::init<>())
        .def("connect", &EliteCalibration::connect)
        .def("disconnect", &EliteCalibration::disconnect)
        .def("run_calibration", &EliteCalibration::run_calibration,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("log_callback"), py::arg("capture_callback"), py::arg("get_pose_callback"))
        .def("run_3d_calibration", &EliteCalibration::run_3d_calibration,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("layers") = 2,
             py::arg("base_width") = 100.0,
             py::arg("top_width") = 50.0,
             py::arg("height") = 50.0,
             py::arg("tilt_angle") = 0.0,
             py::arg("direction") = "Z+",
             py::arg("log_callback"), py::arg("capture_callback"), py::arg("get_pose_callback"));
}
