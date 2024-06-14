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

    # Base folder
    base_dir = create_folder('froster_')

    # Folders that does not contain hotspots
    no_hotspots = create_folder('_no_hotspots', base_dir)
    
    # Subfolder with 1 tree level
    no_hotspots_1_tree = create_folder('_no_hotspots_sub_1', no_hotspots)
    create_file('small_1_' + random_string(),
                1, no_hotspots_1_tree, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1,
                no_hotspots_1_tree, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(), 1100,
                no_hotspots_1_tree, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(), 1100,
                no_hotspots_1_tree, '1000 days ago')  # 1.1KB

    # Subfolder with 2 tree levels
    no_hotspots_2_tree = create_folder('_no_hotspots_2_tree', no_hotspots)
    create_file('small_1_' + random_string(),
                1, no_hotspots_2_tree, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1,
                no_hotspots_2_tree, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, no_hotspots_2_tree, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, no_hotspots_2_tree, '1000 days ago')  # 1.1KB


    no_hotspots_2_tree_1_tree = create_folder(
        '_no_hotspots_2_tree_1_tree', no_hotspots_2_tree)
    create_file('small_1_' + random_string(),
                1, no_hotspots_2_tree_1_tree, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1,
                no_hotspots_2_tree_1_tree, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, no_hotspots_2_tree_1_tree, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, no_hotspots_2_tree_1_tree, '1000 days ago')  # 1.1KB


    # Empty folder
    empty = create_folder('_empty', base_dir)

    # Folders that contain hotspots
    hotspots = create_folder('_hotspots', base_dir)


    # Subfolder with 1 tree level and 1 hotspot
    hotspots_1_tree_1_hp = create_folder('_hotspots_1_tree_1_hp', hotspots)
    create_file('small_1_' + random_string(),
                1, hotspots_1_tree_1_hp, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_1_tree_1_hp, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_1_tree_1_hp, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_1_tree_1_hp, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_1_tree_1_hp, '10 days ago')  # 1.1GB


    # Subfolder with 1 tree levels and 2 hotspot
    hotspots_1_tree_2_hp = create_folder('_hotspots_1_tree_2_hp', hotspots)
    create_file('small_1_' + random_string(),
                1, hotspots_1_tree_2_hp, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_1_tree_2_hp, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_1_tree_2_hp, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_1_tree_2_hp, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_1_tree_2_hp, '10 days ago')  # 1.1GB
    create_file('large_2_' + random_string(), 1100000000,
                hotspots_1_tree_2_hp, '100 days ago')  # 1.1GB


    # Subfolder with 2 tree levels and 1 hotspot each
    hotspots_2_tree_1_hp_each = create_folder(
        '_hotspots_2_tree_1_hp_each', hotspots)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_each, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_each, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_each, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_each, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_2_tree_1_hp_each, '10 days ago')  # 1.1GB


    hotspots_2_tree_1_hp_each_sub_1 = create_folder(
        '_hotspots_2_tree_1_hp_each_sub_1', hotspots_2_tree_1_hp_each)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_each_sub_1, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_each_sub_1, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_each_sub_1, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_each_sub_1, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_2_tree_1_hp_each_sub_1, '10 days ago')  # 1.1GB


    
    # Subfolder with 2 tree levels and 1 hotspot in the first level
    hotspots_2_tree_1_hp_first = create_folder(
        'hotspots_2_tree_1_hp_first', hotspots)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_first, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_first, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_first, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_first, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_2_tree_1_hp_first, '10 days ago')  # 1.1GB

    hotspots_2_tree_1_hp_first_sub_1 = create_folder(
        'hotspots_2_tree_1_hp_first_sub_1', hotspots_2_tree_1_hp_first)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_first_sub_1, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_first_sub_1, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_first_sub_1, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_first_sub_1, '1000 days ago')  # 1.1KB
    
    # Subfolder with 2 tree levels and 1 hotspot in the last level
    hotspots_2_tree_1_hp_last = create_folder(
        'hotspots_2_tree_1_hp_last', hotspots)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_last, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_last, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_last, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_last, '1000 days ago')  # 1.1KB


    hotspots_2_tree_1_hp_last_sub_1 = create_folder(
        'hotspots_2_tree_1_hp_last_sub_1', hotspots_2_tree_1_hp_last)
    create_file('small_1_' + random_string(),
                1, hotspots_2_tree_1_hp_last_sub_1, '1 days ago')  # 1B
    create_file('small_2_' + random_string(), 1, hotspots_2_tree_1_hp_last_sub_1, '10 days ago')  # 1B
    create_file('medium_1_' + random_string(),
                1100, hotspots_2_tree_1_hp_last_sub_1, '100 days ago')  # 1.1KB
    create_file('medium_2_' + random_string(),
                1100, hotspots_2_tree_1_hp_last_sub_1, '1000 days ago')  # 1.1KB
    create_file('large_1_' + random_string(), 1100000000,
                hotspots_2_tree_1_hp_last_sub_1, '10 days ago')  # 1.1GB

    print(f"Test data folder: {base_dir}")

    return base_dir

def main():
    return generate_test_data()


if __name__ == "__main__":
    main()
