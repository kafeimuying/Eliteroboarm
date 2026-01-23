cmake_minimum_required(VERSION 3.10)
project(elite_wrapper)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)

# Define paths (Hardcoded based on user environment for now)
set(ELITE_SDK_PATH "W:/CATL/Elite/Elite-main/Elite-main")
set(ELITE_INCLUDE_DIR "${ELITE_SDK_PATH}/include")
set(ELITE_LIB_DIR "${ELITE_SDK_PATH}/Debug") # Using Debug libs

include_directories(${ELITE_INCLUDE_DIR})
link_directories(${ELITE_LIB_DIR})

# Create shared library
add_library(elite_wrapper SHARED elite_wrapper.cpp)

# Link against Elite SDK
# Note: The lib name is elite-cs-series-sdk.lib
target_link_libraries(elite_wrapper elite-cs-series-sdk)

# Copy dependency DLL to output directory
add_custom_command(TARGET elite_wrapper POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${ELITE_LIB_DIR}/elite-cs-series-sdk.dll"
    $<TARGET_FILE_DIR:elite_wrapper>/elite-cs-series-sdk.dll)

# Output directory
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../bin)
