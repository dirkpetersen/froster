# Use an official Ubuntu runtime as a parent image
FROM ubuntu:latest

# Update the system
RUN apt-get update -y

# Install dependencies
RUN apt-get  install -y vim curl pip git gcc lib32gcc-s1 unzip fuse3

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y pipx

RUN cd /home
RUN python3 -m venv /home/.venv
RUN . /home/.venv/bin/activate

# # Install python packages needed for build and deploy
RUN /home/.venv/bin/pip install twine setuptools wheel

# ensure path
ENV PATH="/root/.local/bin:${PATH}"

# Set the working directory in the container to /app
WORKDIR /home/ubuntu
