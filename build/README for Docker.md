Running in Docker
=================

Pre-requisites:

- [Docker](https://www.docker.com/)

Download the [Dockerfile](Dockerfile) for SQLitely,
build and run the Docker image:

```
    wget https://raw.githubusercontent.com/suurjaak/SQLitely/master/build/Dockerfile
    docker build . -t sqlitely

    xhost +
    docker run -it --rm --mount src=/,target=/mnt/host,type=bind -e DISPLAY -v /tmp/.X11-unix/:/tmp/.X11-unix/ sqlitely
```

`docker build . -t sqlitely` will prepare an Ubuntu 18.04 Docker image
and install SQLitely and its dependencies within the container.

`xhost +` will allow the container to access the X Window System display.

Add `sudo` before docker commands if not running as root user.

Add `--mount src="path to host directory",target=/etc/sqlitely` after `docker run`
to retain SQLitely configuration in a host directory between runs.

Host filesystem is made available under `/mnt/host`.
