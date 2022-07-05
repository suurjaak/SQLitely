# Run SQLitely in a container. Building the image:
#
#     docker build . -t sqlitely
#
# and running afterwards:
#
#     xhost +
#     docker run -it --rm --mount source=/,target=/mnt/host,type=bind -e DISPLAY -v /tmp/.X11-unix/:/tmp/.X11-unix/ sqlitely
#
# Add 'sudo' before docker commands if not running as root user and not in docker-users group.
#
# Add '--mount source="path to host directory",target=/etc/sqlitely' after 'docker run'
# to retain SQLitely configuration in a host directory between runs,
# e.g. '--mount source=~/.config/sqlitely,target=/etc/sqlitely'.
#
# Host filesystem is made available under /mnt/host.

FROM ubuntu:20.04

RUN apt-get update

RUN DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true \
 apt-get update \
 && apt-get install --assume-yes --no-install-recommends \
    libgtk-3-0 \
    libsm6 \
    libsdl2-2.0 \
    libwebkit2gtk-4.0-37 \
    libxtst6 \
    python3 \
    python3-pip \
 && rm -rf /var/lib/apt/lists/*

ENV LC_ALL   en_US.UTF-8
ENV LANG     en_US.UTF-8
ENV LANGUAGE en_US.UTF-8

RUN pip install wxPython==4.1.1 --no-cache-dir \
    --find-links https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-20.04

RUN pip install sqlitely --no-cache-dir

VOLUME /etc/sqlitely

CMD /usr/local/bin/sqlitely --config-file /etc/sqlitely/sqlitely.ini
