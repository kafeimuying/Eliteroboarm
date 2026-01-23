#include <pybind11/pybind11.h>

int add(int i, int j) {
    return i + j;
}

PYBIND11_MODULE(simple_ext, m) {
    m.doc() = "pybind11 simple extension";
    m.def("add", &add, "A function which adds two numbers");
}