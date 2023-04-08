import csv

def parse_mountinfo(file_path='/proc/self/mountinfo', fs_types=None):
    if fs_types is None:
        fs_types = {'nfs', 'nfs4', 'cifs', 'smb', 'afs', 'ncp', 'ncpfs', 'glusterfs', 'ceph', 'beegfs', 'lustre', 'orangefs', 'wekafs', 'gpfs'}

    mountinfo_list = []

    with open(file_path, 'r') as f:
        for line in f:
            fields = line.strip().split(' ')

            _, _, _, _, mount_point, _ = fields[:6]

            for field in fields[6:]:
                if field == '-':
                    break

            fs_type, mount_source, _ = fields[-3:]
            mount_source_folder = mount_source.split(':')[-1] if ':' in mount_source else ''

            if fs_type in fs_types:
                mountinfo_list.append({
                    'mount_source_folder': mount_source_folder,
                    'mount_point': mount_point,
                    'fs_type': fs_type,
                    'mount_source': mount_source,
                })

    print(mountinfo_list)
    return mountinfo_list

def write_csv(network_fs_list, output_file='network_fs.csv'):
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['mount_point', 'fs_type', 'mount_source', 'mount_source_folder']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for fs in network_fs_list:
            writer.writerow(fs)

if __name__ == '__main__':
    network_fs_list = parse_mountinfo()
    write_csv(network_fs_list)

