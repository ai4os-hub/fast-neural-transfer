# Dockerfile may have following Arguments:
# tag - tag for the Base image, (e.g. 1.14.0-py3 for tensorflow)
# branch - user repository branch to clone (default: master, another option: test)
# jlab - if to insall JupyterLab (true) or not (false, default)
#
# To build the image:
# $ docker build -t <dockerhub_user>/<dockerhub_repo> --build-arg arg=value .
# or using default args:
# $ docker build -t <dockerhub_user>/<dockerhub_repo> .
#
# Be Aware! For the Jenkins CI/CD pipeline, 
# input args are defined inside the Jenkinsfile, not here!
#

ARG tag=1.2-cuda10.0-cudnn7-runtime

# Base image, e.g. tensorflow/tensorflow:1.14.0-py3
FROM pytorch/pytorch:${tag}

LABEL maintainer='Silke Donayre (KIT)'
LABEL version='0.0.1'
# A module to apply neural transfer in pytorch.

# What user branch to clone [!]
ARG branch=main

# Install ubuntu updates and python related stuff
# link python3 to python, pip3 to pip, if needed
# Remember: DEEP API V2 only works with python 3.6 [!]
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y --no-install-recommends \
         git \
         curl \
         wget \
         python3-setuptools \
         python3-pip \
         python3-wheel && \
         unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    python --version && \
    pip --version

# Update python packages
# [!] Remember: DEEP API V2 only works with python>=3.6
RUN python3 --version && \
    pip3 install --no-cache-dir --upgrade pip "setuptools<60.0.0" wheel

# Set LANG environment
ENV LANG C.UTF-8

# Set the working directory
WORKDIR /srv

# Install rclone
RUN wget https://downloads.rclone.org/rclone-current-linux-amd64.deb && \
    dpkg -i rclone-current-linux-amd64.deb && \
    apt install -f && \
    mkdir /srv/.rclone/ && touch /srv/.rclone/rclone.conf && \
    rm rclone-current-linux-amd64.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /root/.cache/pip/* && \
    rm -rf /tmp/*

ENV RCLONE_CONFIG=/srv/.rclone/rclone.conf

# Disable FLAAT authentication by default
ENV DISABLE_AUTHENTICATION_AND_ASSUME_AUTHENTICATED_USER yes

# Initialization scripts
# deep-start can install JupyterLab or VSCode if requested
RUN git clone https://github.com/ai4os/deep-start /srv/.deep-start && \
    ln -s /srv/.deep-start/deep-start.sh /usr/local/bin/deep-start

# Necessary for the Jupyter Lab terminal
ENV SHELL /bin/bash

# Install user app:
RUN git clone -b $branch https://github.com/ai4os-hub/fast-neural-transfer && \
    cd  fast-neural-transfer && \
    pip install --no-cache-dir -e . && \
    rm -rf /root/.cache/pip/* && \
    rm -rf /tmp/* && \
    cd ..

# Download weights
# use original weights from https://github.com/pytorch/examples/tree/main/fast_neural_style
RUN cd /srv/fast-neural-transfer/models && \
    curl -L https://www.dropbox.com/s/lrvwfehqdcxoza8/saved_models.zip?dl=1 --output saved_models.zip && \
    unzip -jo saved_models.zip && \
    rm saved_models.zip && \
    cd /srv

# Open ports (deepaas, monitoring, ide)
EXPOSE 5000 6006 8888

# Launch deepaas
CMD ["deepaas-run", "--listen-ip", "0.0.0.0", "--listen-port", "5000"]

