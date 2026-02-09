@echo off
echo ============================================
echo 编译 elite_ext.cpp
echo ============================================

REM 设置VS环境
call "W:\visual studio\VC\Auxiliary\Build\vcvars64.bat"

REM 设置Python路径
set PYTHON_PATH=W:\anaconda\envs\roboarm
set PYTHON_INCLUDE=%PYTHON_PATH%\include
set PYTHON_LIBS=%PYTHON_PATH%\libs
set PYBIND11_INCLUDE=%PYTHON_PATH%\Lib\site-packages\pybind11\include

REM 设置Elite SDK路径
set ELITE_SDK=W:\CATL\Eliteroboarm\Elite_CPP_Interface
set ELITE_INCLUDE=%ELITE_SDK%\include
set ELITE_LIB=%ELITE_SDK%\lib

echo.
echo Python Include: %PYTHON_INCLUDE%
echo Pybind11 Include: %PYBIND11_INCLUDE%
echo Elite Include: %ELITE_INCLUDE%
echo.

REM 编译命令
cl.exe /LD /O2 /std:c++17 ^
    /I"%PYTHON_INCLUDE%" ^
    /I"%PYBIND11_INCLUDE%" ^
    /I"%ELITE_INCLUDE%" ^
    /D_USE_MATH_DEFINES ^
    /DWIN32 /D_WINDOWS /DNDEBUG ^
    /EHsc /MD ^
    elite_ext.cpp ^
    /link ^
    /LIBPATH:"%PYTHON_LIBS%" ^
    /LIBPATH:"%ELITE_LIB%" ^
    python311.lib ^
    elite-cs-series-sdk.lib ^
    /OUT:elite_ext.cp311-win_amd64.pyd

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo 编译成功！
    echo ============================================
    echo 输出文件: elite_ext.cp311-win_amd64.pyd
) else (
    echo.
    echo ============================================
    echo 编译失败，错误代码: %ERRORLEVEL%
    echo ============================================
)

pause
