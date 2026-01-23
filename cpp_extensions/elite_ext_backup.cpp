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

namespace py = pybind11;
using namespace ELITE;

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
             py::arg("log_callback"), py::arg("capture_callback"), py::arg("get_pose_callback"));
}
