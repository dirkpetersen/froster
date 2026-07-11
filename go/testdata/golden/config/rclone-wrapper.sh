#!/bin/bash
export RCLONE_S3_UPLOAD_CUTOFF=0
exec "/home/dp/gh/froster/.venv/bin/rclone" "$@"
