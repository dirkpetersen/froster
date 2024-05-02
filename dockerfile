# Use an official Ubuntu runtime as a parent image
FROM ubuntu:latest

# Update the system
RUN apt-get update -y

# Install dependencies
RUN apt-get install -y curl pipx git gcc lib32gcc-s1 unzip

# ensure path
ENV PATH="/root/.local/bin:${PATH}"

#Install nox
RUN pipx install nox

# Set the working directory in the container to /app
WORKDIR /home
