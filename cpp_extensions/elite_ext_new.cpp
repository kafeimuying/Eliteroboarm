#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "EliteRobotController.hpp"

namespace py = pybind11;
using namespace ELITE_EXTENSION;

// PyBind Module definition remains here, bridging Python to our C++ Class
PYBIND11_MODULE(elite_ext, m)
{
    m.doc() = "Elite Robot C++ Extensions with Unified Interface";

    // Bind the Unified Controller Class
    // Note: Function names exposed to Python are snake_case to be Pythonic,
    // mapping to the C++ camelCase methods.
    py::class_<EliteRobotController>(m, "EliteRobotController")
        .def(py::init<>())
        .def("connect", &EliteRobotController::connect, "Connect to robot", py::arg("ip"), py::arg("recipe_dir") = "config")
        .def("disconnect", &EliteRobotController::disconnect, "Disconnect from robot")
        .def("is_connected", &EliteRobotController::isConnected, "Check connection status")
        .def("get_position", &EliteRobotController::getPosition, "Get current position [x,y,z,rx,ry,rz] (mm, deg)")
        .def("get_robot_state", &EliteRobotController::getRobotState, "Get robot state string")
        .def("set_speed", &EliteRobotController::setSpeed, "Set global speed percent (0-100)")
        .def("jog", &EliteRobotController::jog, "Jog robot axis", py::arg("axis"), py::arg("direction"), py::arg("distance_mm"))
        .def("move_to", &EliteRobotController::moveTo, "Move to target pose (mm, deg)")
        .def("stop", &EliteRobotController::stop, "Emergency stop");
}
