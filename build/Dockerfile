# Run SQLitely in a container. Building the image:
#
#     docker build . -t sqlitely
#
# and running afterwards:
#
#     xhost +
#     docker run -it --rm --mount src=/,target=/mnt/host,type=bind -e DISPLAY -v /tmp/.X11-unix/:/tmp/.X11-unix/ sqlitely
#
# Add 'sudo' before docker commands if not running as root user.
#
# Add '--mount src="path to host directory",target=/etc/sqlitely' after 'docker run'
# to retain SQLitely configuration in a host directory between runs.
#
# Host filesystem is made available under /mnt/host.

FROM ubuntu:18.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      apt-utils \
      locales-all \
      python2.7 \
      python-pip \
      python-dbus \
      python-gobject \
      python-setuptools \
      python-wheel \
      python-wxgtk3.0 \
      dbus-x11 \
      libsdl2-2.0 \
      libxtst6

ENV LC_ALL   en_US.UTF-8
ENV LANG     en_US.UTF-8
ENV LANGUAGE en_US.UTF-8

RUN pip install --upgrade pip

RUN pip install --ignore-installed --find-links \
    https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-18.04 \
    wxPython==4.1.0 --no-cache-dir --no-python-version-warning

RUN pip install sqlitely --no-python-version-warning

RUN printf '\nConfigFile = "/etc/sqlitely/sqlitely.ini"\n' \
    >> /usr/local/lib/python2.7/dist-packages/sqlitely/conf.py

VOLUME /etc/sqlitely


CMD /usr/local/bin/sqlitely
