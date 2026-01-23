#ifndef ELITE_ROBOT_CONTROLLER_HPP
#define ELITE_ROBOT_CONTROLLER_HPP

#include <Elite/DashboardClient.hpp>
#include <Elite/PrimaryPortInterface.hpp>
#include <Elite/RtsiIOInterface.hpp>
#include <Elite/DataType.hpp>
#include <vector>
#include <string>
#include <memory>
#include <iostream>

namespace ELITE_EXTENSION
{

    class EliteRobotController
    {
    public:
        EliteRobotController();
        ~EliteRobotController();

        // 1. Connection Management
        bool connect(const std::string &ip, const std::string &recipe_dir = "config");
        void disconnect();
        bool isConnected() const;

        // 2. State & Position
        // Returns [x, y, z, rx, ry, rz] in mm and degrees (rx, ry, rz are rotation vector in degrees)
        std::vector<double> getPosition();
        std::string getRobotState();

        // 3. Motion Control
        void setSpeed(double percent);

        // Jog: axis (0=X, 1=Y, 2=Z, 3=RX, 4=RY, 5=RZ), direction (+1/-1), distance (mm)
        bool jog(int axis, int direction, double distance_mm);

        // MoveTo: x,y,z (mm), rx,ry,rz (deg, rotation vector)
        bool moveTo(double x, double y, double z, double rx, double ry, double rz);

        bool stop();

    private:
        std::string robot_ip;
        std::unique_ptr<ELITE::DashboardClient> dashboard;
        std::unique_ptr<ELITE::PrimaryPortInterface> primary;
        std::unique_ptr<ELITE::RtsiIOInterface> rtsi;
        bool is_connected;
        double global_speed; // 0.0 - 1.0 (percent / 100)
    };

} // namespace ELITE_EXTENSION

#endif // ELITE_ROBOT_CONTROLLER_HPP
