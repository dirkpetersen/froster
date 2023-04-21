import os
import boto3
from configparser import ConfigParser

def list_profiles():
    config = ConfigParser()
    
    # Read the AWS config file
    aws_config_path = os.path.expanduser("~/.aws/config")
    if os.path.exists(aws_config_path):
        config.read(aws_config_path)
    
    # Read the AWS credentials file
    aws_credentials_path = os.path.expanduser("~/.aws/credentials")
    if os.path.exists(aws_credentials_path):
        config.read(aws_credentials_path)
    
    # Get the list of profiles
    profiles = []
    for section in config.sections():
        profile_name = section.replace("profile ", "").replace("default", "default")
        profiles.append(profile_name)
    
    return profiles

if __name__ == "__main__":
    profiles = list_profiles()
    print("Profiles in AWS configuration:")
    for profile in profiles:
        print(f"- {profile}")
