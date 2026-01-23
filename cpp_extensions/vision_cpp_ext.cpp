#include <opencv2/opencv.hpp>
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <vector>
#include <cmath>
#include <tuple>
#include <algorithm>

namespace py = pybind11;

// ROI Edge Detection Function
py::tuple roi_edge_detection(
    py::array_t<uint8_t> image,
    int roi_x, int roi_y, int roi_width, int roi_height,
    int threshold, int min_line_length)
{

    // Get image info
    py::buffer_info buf = image.request();
    // Assuming 8-bit single channel image

    // Safety check for dimensions
    if (buf.ndim != 2 && buf.ndim != 3)
    {
        throw std::runtime_error("Number of dimensions must be two or three");
    }

    cv::Mat img(buf.shape[0], buf.shape[1], CV_8UC1, (uint8_t *)buf.ptr);

    // Clamp ROI
    roi_x = std::max(0, std::min(roi_x, img.cols - 1));
    roi_y = std::max(0, std::min(roi_y, img.rows - 1));
    roi_width = std::min(roi_width, img.cols - roi_x);
    roi_height = std::min(roi_height, img.rows - roi_y);

    // Extract ROI
    cv::Rect roi(roi_x, roi_y, roi_width, roi_height);
    cv::Mat roi_img = img(roi);

    // Gaussian Blur
    cv::Mat blurred;
    cv::GaussianBlur(roi_img, blurred, cv::Size(5, 5), 0);

    // Canny Edge Detection
    cv::Mat edges;
    cv::Canny(blurred, edges, threshold, threshold * 2);

    // Morphology
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::morphologyEx(edges, edges, cv::MORPH_CLOSE, kernel);

    // Hough Lines
    std::vector<cv::Vec4i> lines;
    cv::HoughLinesP(edges, lines, 1, CV_PI / 180, 50, min_line_length, 10);

    // Prepare results
    std::vector<std::tuple<float, float, float>> edge_points;

    for (const auto &line : lines)
    {
        int x1 = line[0];
        int y1 = line[1];
        int x2 = line[2];
        int y2 = line[3];

        // Midpoint
        float mid_x = (x1 + x2) / 2.0f;
        float mid_y = (y1 + y2) / 2.0f;

        // Angle
        float angle = std::atan2((float)(y2 - y1), (float)(x2 - x1)) * 180.0f / (float)CV_PI;

        // Adjust to global coordinates
        mid_x += roi_x;
        mid_y += roi_y;

        edge_points.emplace_back(mid_x, mid_y, angle);
    }

    return py::cast(edge_points);
}

// Template Matching Function
py::tuple template_matching(
    py::array_t<uint8_t> image,
    py::array_t<uint8_t> template_img,
    int method, float threshold, bool multiple_matches,
    int roi_x, int roi_y, int roi_width, int roi_height)
{

    py::buffer_info img_buf = image.request();
    cv::Mat img(img_buf.shape[0], img_buf.shape[1], CV_8UC1, (uint8_t *)img_buf.ptr);

    py::buffer_info tmpl_buf = template_img.request();
    cv::Mat tmpl(tmpl_buf.shape[0], tmpl_buf.shape[1], CV_8UC1, (uint8_t *)tmpl_buf.ptr);

    int img_rows = img.rows;
    int img_cols = img.cols;

    if (roi_width <= 0 || roi_height <= 0)
    {
        roi_x = 0;
        roi_y = 0;
        roi_width = img_cols;
        roi_height = img_rows;
    }
    else
    {
        roi_x = std::max(0, std::min(roi_x, img_cols - 1));
        roi_y = std::max(0, std::min(roi_y, img_rows - 1));
        roi_width = std::min(roi_width, img_cols - roi_x);
        roi_height = std::min(roi_height, img_rows - roi_y);
    }

    cv::Rect roi(roi_x, roi_y, roi_width, roi_height);
    cv::Mat roi_img = img(roi);

    // Match
    cv::Mat result;
    cv::matchTemplate(roi_img, tmpl, result, method);

    std::vector<std::tuple<int, int, float>> matches;

    if (multiple_matches)
    {
        for (int y = 0; y < result.rows; y++)
        {
            for (int x = 0; x < result.cols; x++)
            {
                float val = result.at<float>(y, x);
                bool match_found = false;

                if (method == cv::TM_SQDIFF || method == cv::TM_SQDIFF_NORMED)
                {
                    if (val <= (1.0f - threshold))
                        match_found = true;
                }
                else
                {
                    if (val >= threshold)
                        match_found = true;
                }

                if (match_found)
                {
                    matches.emplace_back(x + roi_x, y + roi_y, val);
                }
            }
        }
    }
    else
    {
        double min_val, max_val;
        cv::Point min_loc, max_loc;
        cv::minMaxLoc(result, &min_val, &max_val, &min_loc, &max_loc);

        float confidence = (float)((method == cv::TM_SQDIFF || method == cv::TM_SQDIFF_NORMED) ? (1.0 - min_val) : max_val);

        if (confidence >= threshold)
        {
            int abs_x = min_loc.x + roi_x;
            int abs_y = min_loc.y + roi_y;

            if (!(method == cv::TM_SQDIFF || method == cv::TM_SQDIFF_NORMED))
            {
                abs_x = max_loc.x + roi_x;
                abs_y = max_loc.y + roi_y;
            }
            matches.emplace_back(abs_x, abs_y, confidence);
        }
    }

    return py::cast(matches);
}

PYBIND11_MODULE(vision_cpp_ext, m)
{
    m.doc() = "High Performance Vision Utils";

    m.def("roi_edge_detection", &roi_edge_detection,
          "ROI Edge Detection",
          py::arg("image"), py::arg("roi_x"), py::arg("roi_y"),
          py::arg("roi_width"), py::arg("roi_height"),
          py::arg("threshold"), py::arg("min_line_length"));

    m.def("template_matching", &template_matching,
          "Template Matching",
          py::arg("image"), py::arg("template_img"), py::arg("method"),
          py::arg("threshold"), py::arg("multiple_matches"),
          py::arg("roi_x"), py::arg("roi_y"), py::arg("roi_width"), py::arg("roi_height"));

    m.attr("TM_CCOEFF") = (int)cv::TM_CCOEFF;
    m.attr("TM_CCOEFF_NORMED") = (int)cv::TM_CCOEFF_NORMED;
    m.attr("TM_CCORR") = (int)cv::TM_CCORR;
    m.attr("TM_CCORR_NORMED") = (int)cv::TM_CCORR_NORMED;
    m.attr("TM_SQDIFF") = (int)cv::TM_SQDIFF;
    m.attr("TM_SQDIFF_NORMED") = (int)cv::TM_SQDIFF_NORMED;
}
