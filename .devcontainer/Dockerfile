ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}
ARG ROS_DISTRO
ARG USERNAME=USERNAME
ARG USER_UID=1000
ARG USER_GID=$USER_UID
# Only used to fetch PX4's dependency installer. Keep it close to the version in your repo.
ARG PX4_VERSION=v1.15.4
ARG DEBIAN_FRONTEND=noninteractive

RUN if id -u $USER_UID ; then userdel `id -un $USER_UID` ; fi

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y python3-pip vim
ENV SHELL=/bin/bash

# Newer Mesa for Meteor Lake / recent GPUs. Only needed on Ubuntu 22.04 (Humble);
# Ubuntu 24.04 (Jazzy) already ships a recent enough Mesa.
RUN . /etc/os-release && if [ "$VERSION_ID" = "22.04" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends software-properties-common gnupg \
        && add-apt-repository -y ppa:kisak/kisak-mesa \
        && apt-get dist-upgrade -y; \
    fi

# Build tools, GPU drivers, QGroundControl runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl wget lsb-release gnupg \
        build-essential cmake ninja-build ccache \
        libgl1-mesa-dri libglx-mesa0 libegl-mesa0 libgbm1 \
        mesa-vulkan-drivers mesa-utils vulkan-tools \
        libva-drm2 libva-x11-2 \
        libfuse2 \
        gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl \
        libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0 \
        libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1 \
        libgl1 libegl1 libpulse0 \
    && apt-get remove -y modemmanager || true \
    && usermod -aG dialout,video $USERNAME \
    && rm -rf /var/lib/apt/lists/*


# PX4 build dependencies, installed with the script from your own checkout
COPY PX4-Autopilot/Tools/setup/ubuntu.sh PX4-Autopilot/Tools/setup/requirements.txt /tmp/px4-setup/Tools/setup/
RUN PIP_IGNORE_INSTALLED=1 PIP_BREAK_SYSTEM_PACKAGES=1 \
    bash /tmp/px4-setup/Tools/setup/ubuntu.sh --no-nuttx \
    && rm -rf /tmp/px4-setup /var/lib/apt/lists/*

# QGroundControl AppImage (extracted, since FUSE isn't available in containers by default)
RUN mkdir -p /opt/qgroundcontrol && cd /opt/qgroundcontrol \
    && wget -q https://d176tv9ibo4jno.cloudfront.net/latest/QGroundControl-x86_64.AppImage \
    && mv QGroundControl-x86_64.AppImage QGroundControl.AppImage \
    && chmod +x QGroundControl.AppImage \
    && ./QGroundControl.AppImage --appimage-extract >/dev/null \
    && rm QGroundControl.AppImage \
    && chmod -R a+rX /opt/qgroundcontrol \
    && printf '#!/bin/sh\nexec /opt/qgroundcontrol/squashfs-root/AppRun "$@"\n' > /usr/local/bin/qgroundcontrol \
    && chmod +x /usr/local/bin/qgroundcontrol

RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /home/$USERNAME/.bashrc

USER $USERNAME
WORKDIR /home/ws
CMD ["/bin/bash"]