import boto3

# Set the S3 bucket and key of the file to restore

bucket_name = 'posix-dp'
object_key = 'deep_archive/awscliv2.zip'
#object_key = 'default/awscliv2.zip'


# Set the S3 storage class for the file to restore
#storage_class = 'GLACIER'
storage_class = 'DEEP_ARCHIVE'
storge_class = 'INTELLIGENT_TIERING'

# Set the number of days to keep the restored data available
restore_days = 30

# Create an S3 client
s3 = boto3.client('s3')

# Retrieve the size of the file
response = s3.head_object(Bucket=bucket_name, Key=object_key)
file_size = response['ContentLength']

# Retrieve the lifecycle configuration for the bucket
response = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
rules = response['Rules']

# Find the rule that applies to the file and specifies the storage class
for rule in rules:
    print('rules:',rules)
    if 'Filter' in rule and 'Prefix' in rule['Filter']:
        prefix = rule['Filter']['Prefix']
        print('prefix:',prefix)
        if object_key.startswith(prefix) and 'StorageClass' in rule['Transitions'][0] and rule['Transitions'][0]['StorageClass'] == storage_class:
            storage_cost = rule['Transitions'][0]['StoragePerUnit']
            print('storage_cost:',storage_cost)
            break

# Calculate the cost of restoring the file
restore_cost = file_size / (1024 * 1024 * 1024) * restore_days * storage_cost / 30

# Print the estimated cost of restoring the file
print(f"The estimated cost of restoring {object_key} from {storage_class} for {restore_days} days is ${restore_cost:.2f}")






