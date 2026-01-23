#include "EliteRobotController.hpp"

#include <cmath>
#include <thread>
#include <sstream>
#include <algorithm>
#include <iomanip>

namespace ELITE_EXTENSION
{

    EliteRobotController::EliteRobotController() : is_connected(false), global_speed(0.5) {}

    EliteRobotController::~EliteRobotController()
    {
        disconnect();
    }

    bool EliteRobotController::connect(const std::string &ip, const std::string &recipe_dir)
    {
        robot_ip = ip;
        // Construct paths for recipe files
        // If running from source, these might need to be absolute, but here we assume relative or handled by caller
        std::string out_recipe = recipe_dir + "/output_recipe.txt";
        std::string in_recipe = recipe_dir + "/input_recipe.txt";

        try
        {
            dashboard = std::make_unique<ELITE::DashboardClient>();
            primary = std::make_unique<ELITE::PrimaryPortInterface>();
            // Update rtsi to use the correct recipe paths (frequency 250Hz)
            rtsi = std::make_unique<ELITE::RtsiIOInterface>(out_recipe, in_recipe, 250);

            bool db_ok = dashboard->connect(ip);
            bool pri_ok = primary->connect(ip);
            bool rtsi_ok = rtsi->connect(ip);

            // We consider connection successful if at least Dashboard and Primary interfaces are connected.
            // RTSI is strictly speaking optional for basic control but needed for getPosition.
            if (db_ok && pri_ok)
            {
                is_connected = true;
                // Init Robot: Power On and Release Brake
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

    void EliteRobotController::disconnect()
    {
        if (primary)
            primary->disconnect();
        if (rtsi)
            rtsi->disconnect();
        if (dashboard)
            dashboard->disconnect();
        is_connected = false;
    }

    bool EliteRobotController::isConnected() const
    {
        return is_connected;
    }

    std::vector<double> EliteRobotController::getPosition()
    {
        if (!rtsi || !rtsi->isConnected())
            return {};

        // RTSI returns position in Meters and Rad (Rotation Vector)
        auto pose = rtsi->getActualTCPPose();
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

    std::string EliteRobotController::getRobotState()
    {
        if (!dashboard)
            return "Unknown";
        return is_connected ? "Connected" : "Disconnected";
    }

    void EliteRobotController::setSpeed(double percent)
    {
        global_speed = std::max(0.01, std::min(1.0, percent / 100.0));
        // Send speed scaling command to Dashboard
        if (dashboard)
        {
            dashboard->setSpeedScaling((int)percent);
        }
    }

    bool EliteRobotController::jog(int axis, int direction, double distance_mm)
    {
        if (!is_connected || !primary)
            return false;

        // We assume jogging is relative to Base Frame (pose_add on actual TCP pose)
        // axis: 0=X, 1=Y, 2=Z, 3=Rx, 4=Ry, 5=Rz

        double dist_m = distance_mm / 1000.0;
        double speed_val = global_speed;

        double offsets[6] = {0, 0, 0, 0, 0, 0};
        if (axis >= 0 && axis < 6)
        {
            offsets[axis] = direction * dist_m;
        }

        std::stringstream ss;
        // Note: p[...] creates a pose/point in Elite script, but [...] list syntax avoids potential scope issues with 'p' in some contexts
        // For pose_add, the second argument should be a pose. p[x,y,z,rx,ry,rz] is standard.
        // However, recent fix showed using list [...] works better in some environments to avoid "builtin_function_or_method" errors if 'p' is misinterpreted.
        ss << "movel(pose_add(get_actual_tcp_pose(), [";
        for (int i = 0; i < 6; ++i)
            ss << offsets[i] << (i < 5 ? "," : "");
        ss << "]), a=0.5, v=" << speed_val << ")";

        return primary->sendScript(ss.str());
    }

    bool EliteRobotController::moveTo(double x, double y, double z, double rx, double ry, double rz)
    {
        if (!is_connected || !primary)
            return false;

        // x,y,z in m; rx,ry,rz in rad
        std::stringstream ss;
        ss << "movel(["
           << x / 1000.0 << "," << y / 1000.0 << "," << z / 1000.0 << ","
           << rx / 57.29578 << "," << ry / 57.29578 << "," << rz / 57.29578
           << "], a=0.5, v=" << global_speed << ")";

        return primary->sendScript(ss.str());
    }

    bool EliteRobotController::stop()
    {
        if (!primary)
            return false;
        return primary->sendScript("stopj(2.0)");
    }

} // namespace ELITE_EXTENSION
