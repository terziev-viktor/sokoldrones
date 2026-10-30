#include <awnn_lib.h>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/float32_multi_array.hpp>
#include <std_msgs/msg/float64.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace
{

class AwnnSession
{
public:
  explicit AwnnSession(const std::string & model_path)
  {
    if (!std::filesystem::is_regular_file(model_path)) {
      throw std::runtime_error("NBG model file does not exist: " + model_path);
    }

    awnn_init();
    context_ = awnn_create(model_path.c_str());
    if (context_ == nullptr) {
      awnn_uninit();
      throw std::runtime_error("AWNN could not load NBG model: " + model_path);
    }
  }

  ~AwnnSession()
  {
    if (context_ != nullptr) {
      awnn_destroy(context_);
      awnn_uninit();
    }
  }

  AwnnSession(const AwnnSession &) = delete;
  AwnnSession & operator=(const AwnnSession &) = delete;

  void run(std::vector<std::uint8_t> & input)
  {
    void * input_buffers[] = {input.data()};
    awnn_set_input_buffers(context_, input_buffers);
    awnn_run(context_);
  }

  float * output(int index) const
  {
    return static_cast<float *>(awnn_get_output_buffer(context_, index));
  }

private:
  Awnn_Context_t * context_{nullptr};
};

class NpuCameraInference : public rclcpp::Node
{
public:
  NpuCameraInference()
  : Node("npu_camera_inference")
  {
    const auto model_path = declare_parameter<std::string>("model_path", "");
    const auto camera_topic = declare_parameter<std::string>(
      "camera_topic", "/camera/image_raw");
    input_width_ = declare_parameter<int>("input_width", 640);
    input_height_ = declare_parameter<int>("input_height", 640);
    input_channels_ = declare_parameter<int>("input_channels", 3);
    input_layout_ = declare_parameter<std::string>("input_layout", "NCHW");
    color_order_ = declare_parameter<std::string>("color_order", "RGB");
    const auto output_element_counts =
      declare_parameter<std::vector<std::int64_t>>("output_element_counts", {});

    if (model_path.empty()) {
      throw std::invalid_argument("Set the required model_path parameter to an A733 NBG file.");
    }
    if (input_width_ <= 0 || input_height_ <= 0 ||
      (input_channels_ != 1 && input_channels_ != 3))
    {
      throw std::invalid_argument("input_width/height must be positive and input_channels must be 1 or 3.");
    }
    if (input_layout_ != "NCHW" && input_layout_ != "NHWC") {
      throw std::invalid_argument("input_layout must be NCHW or NHWC.");
    }
    if (color_order_ != "RGB" && color_order_ != "BGR") {
      throw std::invalid_argument("color_order must be RGB or BGR.");
    }
    if (output_element_counts.empty() ||
      std::any_of(output_element_counts.begin(), output_element_counts.end(),
      [](std::int64_t count) {
        return count <= 0 ||
               static_cast<std::uint64_t>(count) > std::numeric_limits<std::uint32_t>::max();
      }))
    {
      throw std::invalid_argument(
              "output_element_counts is required; set one positive element count per NBG output.");
    }

    const auto width = static_cast<std::size_t>(input_width_);
    const auto height = static_cast<std::size_t>(input_height_);
    const auto channels = static_cast<std::size_t>(input_channels_);
    const auto max_size = std::numeric_limits<std::size_t>::max();
    if (width > max_size / height || width * height > max_size / channels) {
      throw std::invalid_argument("Configured model input dimensions are too large.");
    }
    input_buffer_.resize(
      width * height * channels);
    session_ = std::make_unique<AwnnSession>(model_path);

    for (std::size_t index = 0; index < output_element_counts.size(); ++index) {
      const auto topic = "output_" + std::to_string(index);
      output_sizes_.push_back(static_cast<std::size_t>(output_element_counts[index]));
      output_publishers_.push_back(
        create_publisher<std_msgs::msg::Float32MultiArray>(topic, rclcpp::QoS(1)));
    }
    latency_publisher_ = create_publisher<std_msgs::msg::Float64>("inference_latency_ms", 10);
    auto image_qos = rclcpp::SensorDataQoS();
    image_qos.keep_last(1);
    image_subscription_ = create_subscription<sensor_msgs::msg::Image>(
      camera_topic, image_qos,
      std::bind(&NpuCameraInference::on_image, this, std::placeholders::_1));

    RCLCPP_INFO(
      get_logger(), "Loaded A733 NBG model '%s'; subscribing to %s",
      model_path.c_str(), camera_topic.c_str());
  }

private:
  void pack_input(const sensor_msgs::msg::Image & image)
  {
    std::size_t source_channels = 0;
    const bool source_is_bgr = image.encoding == sensor_msgs::image_encodings::BGR8;
    if (image.encoding == sensor_msgs::image_encodings::RGB8 ||
      source_is_bgr)
    {
      source_channels = 3;
    } else if (image.encoding == sensor_msgs::image_encodings::MONO8) {
      source_channels = 1;
    } else {
      throw std::invalid_argument(
              "Unsupported camera encoding '" + image.encoding +
              "'; expected rgb8, bgr8, or mono8.");
    }

    const auto source_width = static_cast<std::size_t>(image.width);
    const auto source_height = static_cast<std::size_t>(image.height);
    const auto minimum_step = source_width * source_channels;
    if (source_width == 0 || source_height == 0 || image.step < minimum_step ||
      image.data.size() < static_cast<std::size_t>(image.step) * source_height)
    {
      throw std::invalid_argument("Camera image dimensions, step, or data size are invalid.");
    }

    const auto plane_size = static_cast<std::size_t>(input_width_) * input_height_;
    for (int y = 0; y < input_height_; ++y) {
      const auto source_y = std::clamp(
        (static_cast<double>(y) + 0.5) * source_height / input_height_ - 0.5,
        0.0, static_cast<double>(source_height - 1));
      const auto y0 = static_cast<std::size_t>(source_y);
      const auto y1 = std::min(y0 + 1, source_height - 1);
      const auto fy = source_y - y0;
      for (int x = 0; x < input_width_; ++x) {
        const auto source_x = std::clamp(
          (static_cast<double>(x) + 0.5) * source_width / input_width_ - 0.5,
          0.0, static_cast<double>(source_width - 1));
        const auto x0 = static_cast<std::size_t>(source_x);
        const auto x1 = std::min(x0 + 1, source_width - 1);
        const auto fx = source_x - x0;
        const auto pixel_index = static_cast<std::size_t>(y) * input_width_ + x;
        std::uint8_t rgb[3]{};
        const auto source_pixel = [&](std::size_t source_x_index, std::size_t source_y_index,
            int channel) {
            const auto offset =
              source_y_index * image.step + source_x_index * source_channels;
            if (source_channels == 1) {
              return image.data[offset];
            }
            const auto source_channel = source_is_bgr ? 2 - channel : channel;
            return image.data[offset + static_cast<std::size_t>(source_channel)];
          };
        for (int channel = 0; channel < 3; ++channel) {
          const auto top_left = source_pixel(x0, y0, channel);
          const auto top_right = source_pixel(x1, y0, channel);
          const auto bottom_left = source_pixel(x0, y1, channel);
          const auto bottom_right = source_pixel(x1, y1, channel);
          const auto top = top_left * (1.0 - fx) + top_right * fx;
          const auto bottom = bottom_left * (1.0 - fx) + bottom_right * fx;
          rgb[channel] = static_cast<std::uint8_t>(std::clamp(
            std::lround(top * (1.0 - fy) + bottom * fy), 0L, 255L));
        }

        if (input_channels_ == 1) {
          const auto gray = static_cast<std::uint8_t>(std::clamp(
            std::lround(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]), 0L, 255L));
          input_buffer_[pixel_index] = gray;
        } else {
          for (int channel = 0; channel < input_channels_; ++channel) {
            const auto source_channel = color_order_ == "BGR" ? 2 - channel : channel;
            const auto source_index =
              pixel_index * input_channels_ + static_cast<std::size_t>(channel);
            const auto target_index = input_layout_ == "NCHW" ?
              static_cast<std::size_t>(channel) * plane_size + pixel_index : source_index;
            input_buffer_[target_index] = rgb[source_channel];
          }
        }
      }
    }
  }

  void on_image(const sensor_msgs::msg::Image::ConstSharedPtr message)
  {
    try {
      pack_input(*message);

      const auto start = std::chrono::steady_clock::now();
      session_->run(input_buffer_);
      const auto stop = std::chrono::steady_clock::now();
      const auto elapsed_ms =
        std::chrono::duration<double, std::milli>(stop - start).count();

      for (std::size_t index = 0; index < output_sizes_.size(); ++index) {
        const auto * output = session_->output(static_cast<int>(index));
        if (output == nullptr) {
          RCLCPP_ERROR(get_logger(), "AWNN returned a null output buffer at index %zu", index);
          return;
        }

        std_msgs::msg::Float32MultiArray result;
        result.layout.dim.resize(1);
        result.layout.dim[0].label = "flat_output";
        result.layout.dim[0].size = static_cast<std::uint32_t>(output_sizes_[index]);
        result.layout.dim[0].stride = static_cast<std::uint32_t>(output_sizes_[index]);
        result.data.assign(output, output + output_sizes_[index]);
        output_publishers_[index]->publish(std::move(result));
      }

      std_msgs::msg::Float64 latency;
      latency.data = elapsed_ms;
      latency_publisher_->publish(latency);
    } catch (const std::invalid_argument & error) {
      RCLCPP_ERROR(get_logger(), "Invalid camera frame: %s", error.what());
    }
  }

  int input_width_{};
  int input_height_{};
  int input_channels_{};
  std::string input_layout_;
  std::string color_order_;
  std::vector<std::uint8_t> input_buffer_;
  std::vector<std::size_t> output_sizes_;
  std::unique_ptr<AwnnSession> session_;
  std::vector<rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr>
  output_publishers_;
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr latency_publisher_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_subscription_;
};

}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try {
    rclcpp::spin(std::make_shared<NpuCameraInference>());
  } catch (const std::exception & error) {
    RCLCPP_FATAL(rclcpp::get_logger("npu_camera_inference"), "%s", error.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
