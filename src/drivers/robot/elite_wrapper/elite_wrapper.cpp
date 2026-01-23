#define _CRT_SECURE_NO_WARNINGS
#include <Elite/EliteDriver.hpp>
#include <Elite/RtsiIOInterface.hpp>
#include <cstring>
#include <iostream>
#include <memory>
#include <vector>

// Define a macro for export
#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

// Wrapper struct to hold both Driver and RTSI
struct EliteContext
{
    std::unique_ptr<ELITE::EliteDriver> driver;
    std::unique_ptr<ELITE::RtsiIOInterface> rtsi;
    std::string ip;
};

extern "C"
{

    // Opaque pointer to hold the EliteContext instance
    typedef void *EliteDriverHandle;

    // Create the driver instance
    EXPORT EliteDriverHandle Elite_Create(const char *robot_ip)
    {
        try
        {
            auto ctx = new EliteContext();
            ctx->ip = std::string(robot_ip);

            // Initialize Driver
            try
            {
                ELITE::EliteDriverConfig config;
                config.robot_ip = ctx->ip;
                // The SDK requires a script file path, even if we don't use it for simple moves.
                // We can point it to a dummy file or the existing external_control.script if available.
                // Or we can try to disable the check if possible, but the error suggests it's mandatory.
                // Let's try to set it to "external_control.script" which should be in the bin dir.
                config.script_file_path = "external_control.script";

                ctx->driver = std::make_unique<ELITE::EliteDriver>(config);
            }
            catch (const std::exception &e)
            {
                std::cerr << "[EliteWrapper] Driver initialization failed: " << e.what() << std::endl;
                delete ctx;
                return nullptr;
            }
            catch (...)
            {
                std::cerr << "[EliteWrapper] Driver initialization failed with unknown error." << std::endl;
                delete ctx;
                return nullptr;
            }

            // Initialize RTSI for data reading
            try
            {
                // Check if recipe files exist
                FILE *f_out = fopen("output_recipe.txt", "r");
                FILE *f_in = fopen("input_recipe.txt", "r");

                if (f_out && f_in)
                {
                    fclose(f_out);
                    fclose(f_in);
                    ctx->rtsi = std::make_unique<ELITE::RtsiIOInterface>("output_recipe.txt", "input_recipe.txt", 250);
                    if (ctx->rtsi)
                    {
                        bool connected = ctx->rtsi->connect(ctx->ip);
                        if (!connected)
                        {
                            std::cerr << "[EliteWrapper] RTSI connect returned false." << std::endl;
                        }
                    }
                }
                else
                {
                    std::cerr << "[EliteWrapper] Recipe files not found in current directory." << std::endl;
                    if (f_out)
                        fclose(f_out);
                    if (f_in)
                        fclose(f_in);
                }
            }
            catch (const std::exception &e)
            {
                std::cerr << "[EliteWrapper] RTSI initialization failed: " << e.what() << std::endl;
                // Continue without RTSI
            }
            catch (...)
            {
                std::cerr << "[EliteWrapper] RTSI initialization failed with unknown error." << std::endl;
                // Continue without RTSI
            }

            return ctx;
        }
        catch (...)
        {
            return nullptr;
        }
    }

    // Destroy the driver instance
    EXPORT void Elite_Destroy(EliteDriverHandle handle)
    {
        if (handle)
        {
            auto ctx = static_cast<EliteContext *>(handle);
            if (ctx->rtsi)
                ctx->rtsi->disconnect();
            if (ctx->driver)
                ctx->driver->stopControl();
            delete ctx;
        }
    }

    // Check connection
    EXPORT bool Elite_IsConnected(EliteDriverHandle handle)
    {
        if (!handle)
            return false;
        auto ctx = static_cast<EliteContext *>(handle);
        // Check both driver and RTSI? Or just driver?
        bool driver_connected = ctx->driver && ctx->driver->isRobotConnected();
        bool rtsi_connected = ctx->rtsi && ctx->rtsi->isConnected();
        return driver_connected; // Return driver status primarily
    }

    // Send script
    EXPORT bool Elite_SendScript(EliteDriverHandle handle, const char *script)
    {
        if (!handle)
            return false;
        auto ctx = static_cast<EliteContext *>(handle);
        if (!ctx->driver)
            return false;
        return ctx->driver->sendScript(std::string(script));
    }

    // Get TCP Pose
    // Returns true if successful, false otherwise.
    // pose array must be at least size 6 [x, y, z, rx, ry, rz]
    EXPORT bool Elite_GetPose(EliteDriverHandle handle, double *pose)
    {
        if (!handle || !pose)
            return false;

        try
        {
            auto ctx = static_cast<EliteContext *>(handle);
            if (!ctx || !ctx->rtsi)
                return false;

            // Ensure RTSI is connected
            if (!ctx->rtsi->isConnected())
            {
                // Try to reconnect, but don't block or crash
                // ctx->rtsi->connect(ctx->ip);
                // if (!ctx->rtsi->isConnected())
                //    return false;
                return false;
            }

            auto vec = ctx->rtsi->getActualTCPPose();
            if (vec.size() >= 6)
            {
                for (int i = 0; i < 6; ++i)
                {
                    pose[i] = vec[i];
                }
                return true;
            }
        }
        catch (...)
        {
            return false;
        }
        return false;
    }

    // Let's expose move functions
    EXPORT bool Elite_MoveLinear(EliteDriverHandle handle, double x, double y, double z, double rx, double ry, double rz, float speed)
    {
        if (!handle)
            return false;
        return false;
    }

    // Disconnect RTSI explicitly
    EXPORT bool Elite_DisconnectRTSI(EliteDriverHandle handle)
    {
        if (!handle)
            return false;
        auto ctx = static_cast<EliteContext *>(handle);
        if (ctx->rtsi)
        {
            ctx->rtsi->disconnect();
            return true;
        }
        return false;
    }

    // Connect RTSI explicitly
    EXPORT bool Elite_ConnectRTSI(EliteDriverHandle handle)
    {
        if (!handle)
            return false;
        auto ctx = static_cast<EliteContext *>(handle);
        if (ctx->rtsi)
        {
            return ctx->rtsi->connect(ctx->ip);
        }
        return false;
    }
}
