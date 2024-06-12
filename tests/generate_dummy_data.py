import os
import random
import string
import subprocess
import tempfile


def random_string(length=3):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def create_folder(name=None, path=None):
    if name is None:
        name = random_string()

    if path is None:
        folder_path = tempfile.mkdtemp(prefix=name)
    else:
        folder_path = os.path.join(path, name)
        os.makedirs(folder_path)

    return folder_path


def create_file(filename, size, path, age):
    if filename is None or size is None or path is None or age is None:
        raise ValueError("name, size, path and age must be provided")

    file_path = os.path.join(path, filename)

    with open(file_path, 'wb') as f:
        f.truncate(size)

    subprocess.run(['touch', '-d', age, file_path])


def generate_test_data():

    base_dir = create_folder('froster.')
    subdir1 = create_folder('_' + random_string() + '_subdir', base_dir)
    subdir2 = create_folder('_' + random_string() + '_subdir', subdir1)

    print(f"Test data folder: {base_dir}")

    # Create files in the base directory
    for dir in [base_dir, subdir1, subdir2]:
        create_file('small_1_' + random_string(), 1, dir, '1 days ago')
        create_file('small_2_' + random_string(), 1, dir, '10 days ago')
        create_file('medium_1_' + random_string(), 1100, dir, '100 days ago')
        create_file('medium_2_' + random_string(), 1100, dir, '1000 days ago')
        create_file('large_1_' + random_string(), 1100000, dir, '10 days ago')
        create_file('large_2_' + random_string(), 1100000, dir, '1000 days ago')

    return base_dir

def main():
    return generate_test_data()


if __name__ == "__main__":
    main()
