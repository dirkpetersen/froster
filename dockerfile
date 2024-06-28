# Use an official Ubuntu runtime as a parent image
FROM ubuntu:latest

# Update the system
RUN apt update -y

# Install dependencies
RUN apt install -y curl python3 python3-pip python3-venv python3-dev gcc lib32gcc-s1 unzip fuse3

# Set the working directory in the container to /app
WORKDIR /home/ubuntu
