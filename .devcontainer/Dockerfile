FROM ros:jazzy
ARG USERNAME=USERNAME
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN if id -u $USER_UID ; then userdel `id -un $USER_UID` ; fi

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y python3-pip
RUN apt-get install -y vim
RUN apt-get install -y libgl1-mesa-dri libglx-mesa0 libegl-mesa0 libgbm1 mesa-vulkan-drivers mesa-utils vulkan-tools libva-drm2 libva-x11-2

ENV SHELL=/bin/bash

# --- Tools needed by the PX4 setup script and QGroundControl ---
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get install -y --no-install-recommends \
        git ca-certificates curl wget lsb-release gnupg \
        build-essential cmake ninja-build \
    # QGroundControl runtime deps
        libfuse2 \
        gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl \
        libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0 \
        libgl1 libegl1 libpulse0 \
    # ModemManager interferes with serial/MAVLink devices
    && apt-get remove -y modemmanager || true \
    && usermod -aG dialout,video $USERNAME \
    && rm -rf /var/lib/apt/lists/*

# --- QGroundControl AppImage (extracted, since FUSE isn't available in containers) ---
RUN mkdir -p /opt/qgroundcontrol \
    && wget -q -O /opt/qgroundcontrol/QGroundControl.AppImage https://d176tv9ibo4jno.cloudfront.net/latest/QGroundControl-x86_64.AppImage \
    && chmod 755 /opt/qgroundcontrol/QGroundControl.AppImage \
    && printf '#!/bin/sh\nexec /opt/qgroundcontrol/QGroundControl.AppImage --appimage-extract-and-run "$@"\n' > /usr/local/bin/qgroundcontrol \
    && chmod +x /usr/local/bin/qgroundcontrol

RUN echo "source /opt/ros/jazzy/setup.bash" >> /home/$USERNAME/.bashrc

USER $USERNAME

# --- PX4 SITL quickstart ---
WORKDIR /home/$USERNAME
RUN git clone --recursive https://github.com/PX4/PX4-Autopilot.git \
    && bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx \
    && sudo rm -rf /var/lib/apt/lists/*

# Pre-build SITL so the first run is fast (comment out to shorten the image build)
RUN cd PX4-Autopilot && make px4_sitl

# Optional: Micro XRCE-DDS Agent for the PX4 <-> ROS 2 bridge
# RUN git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git \
#     && cd Micro-XRCE-DDS-Agent && mkdir build && cd build \
#     && cmake .. && make -j$(nproc) && sudo make install && sudo ldconfig

CMD ["/bin/bash"]