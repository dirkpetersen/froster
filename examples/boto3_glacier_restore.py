#! /usr/bin/env python3

import boto3, botocore

def main():
    bucket_name = 'froster'  # Replace with your actual bucket name
    prefix = 'deep_archive/home/dp/gh/froster/tests/'  # Replace with your actual prefix
    restore_days = 1
    retrieval_option = 'Bulk'  # or 'Expedited', 'Bulk'

    initiate_restore(bucket_name, prefix, restore_days, retrieval_option)

def initiate_restore(bucket_name, prefix, restore_days, retrieval_option):
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    for page in pages:
        for obj in page['Contents']:
            object_key = obj['Key']

            # Check if there are additional slashes after the prefix,
            # indicating that the object is in a subfolder.
            remaining_path = object_key[len(prefix):]
            if '/' not in remaining_path:
                try:
                    s3.restore_object(
                        Bucket=bucket_name,
                        Key=object_key,
                        RestoreRequest={
                            'Days': restore_days,
                            'GlacierJobParameters': {
                                'Tier': retrieval_option
                            }
                        }
                    )
                    print(f'Restore request initiated for {object_key} using {retrieval_option} retrieval.')
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
                        print(f'Restore is already in progress for {object_key}. Skipping...')
                    else:
                        print(f'Error occurred for {object_key}: {e}')                    
                except:
                    print(f'Restore for {object_key} already in progress')

                return False

if __name__ == "__main__":
    main()    
