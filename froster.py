#! /usr/bin/env python3

"""
Froster (almost) automates the challening task of 
archiving many Terabytes of data 
"""

import sys, os, argparse, json

__app__ = 'Froster command line archiving tool'

VAR = os.getenv('MYVAR', 'default value')
HOMEDIR = os.path.expanduser("~")

def main():

    #test config manager 
    cfg = ConfigManager()
    # Write an entry
    cfg.write('general', 'username', 'JohnDoe')
    mylist = ['folder1', 'folder2', 'folder3']
    mydict = {}
    mydict['folder1']="43"
    mydict['folder2']="42"

    cfg.write('general', 'mylist', mylist)
    cfg.write('general', 'mydict', mydict)

    # Read an entry
    username = cfg.read('general', 'username')
    print(username)  # Output: JohnDoe
    print(cfg.read('general', 'mylist'))
    print(cfg.read('general', 'mydict'))
    # Delete an entry
    #cfg.delete('application', 'username')
    # Delete a section
    #config.delete_section('application')   

    arch = Archiver(args.debug, "test")
    if args.subcmd == 'config':
        print ("config")
        arch.config("one", "two")
        print(args.folders)
    elif args.subcmd == 'index':
        print ("index:",args.cores, args.noslurm, args.pwalkcsv, args.folders)
        arch.index("one", "two")
    elif args.subcmd == 'archive':
        print ("archive:",args.cores, args.noslurm, args.md5sum, args.folders)
    elif args.subcmd == 'restore':
        print ("restore:",args.cores, args.noslurm, args.folders)
    elif args.subcmd == 'delete':
        print ("delete:",args.folders)

    #if args:
    #   arch.queryByProject(args.projects)

class Archiver:
    def __init__(self, verbose, active):
        self.verbose = verbose
        self.active = active
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.grants = []

    def config(self, var1, var2):
        return var1

    def index(self, var1, var2):    
        return var1

    def something(self, var1, var2):    
        return var1


def parse_arguments():
    """
    Gather command-line arguments.
    """       
    parser = argparse.ArgumentParser(prog='froster ',
        description='a tool for archiving large scale data ' + \
                    'after finding it')
    parser.add_argument( '--debug', '-g', dest='debug', action='store_true', default=False,
        help="verbose output for all commands")

    subparsers = parser.add_subparsers(dest="subcmd", help='sub-command help')
    # ***
    parser_config = subparsers.add_parser('config', aliases=['cnf'], 
        help='edit configuration interactively')
    # ***
    parser_index = subparsers.add_parser('index', aliases=['idx'], 
        help='create a database of sub-folders to select from.')
    parser_index.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=True,
        help="do not submit a Slurm job, execute index directly")
    parser_index.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the index. (default=4) ')
    parser_index.add_argument('--pwalk-csv', '-p', dest='pwalkcsv', action='store', default='', 
        help='If someone else has already created csv files using pwalk ' +
             'you can enter that folder here and do not require to run ' +
             'the time consuming pwalk. \n' +
             'You can also pass a specific CSV file instead of a folder' +
             '')
    parser_index.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to index (separated by space), ' +
                'using thepwalk file system crawler ')
    # ***
    parser_archive = subparsers.add_parser('archive', aliases=['arc'], 
        help='archive folder to object store')
    parser_archive.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_archive.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')                                
    parser_archive.add_argument( '--md5sum', '-m', dest='md5sum', action='store_true', default=False,
        help="show the technical contact / owner of the machine")
    parser_archive.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to archive (separated by space), ' +
                'the last folder in this list is the target   ')
    # ***
    parser_restore = subparsers.add_parser('restore', aliases=['rst'], 
        help='restore folder from object store')
    parser_restore.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_restore.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')                                
    parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to to restore (separated by space), ' +
                'the last folder in this list is the target  ')
    # ***
    parser_delete = subparsers.add_parser('delete', aliases=['del'],
        help='Select folders to delete after they have been archived')
    parser_delete.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to delete (separated by space), ' +
               'you can only delete folders that are archived')

    return parser.parse_args()

class ConfigManager:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries 
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as 
    # multi-line files and dictionaries which are written to json

    def __init__(self):
        self.config_dir = os.path.expanduser('~/.config/froster')

    def _get_section_path(self, section):
        return os.path.join(self.config_dir, section)

    def _get_entry_path(self, section, entry):
        section_path = self._get_section_path(section)
        return os.path.join(section_path, entry)

    def write(self, section, entry, value):
        entry_path = self._get_entry_path(section, entry)

        os.makedirs(os.path.dirname(entry_path), exist_ok=True)
        
        with open(entry_path, 'w') as entry_file:
            if isinstance(value, list):
                for item in value:
                    entry_file.write(f"{item}\n")
            elif isinstance(value, dict):
                json.dump(value, entry_file)
            else:
                entry_file.write(value)

    def read(self, section, entry):
        entry_path = self._get_entry_path(section, entry)

        if not os.path.exists(entry_path):
            raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')
 
        with open(entry_path, 'r') as entry_file:
            try:
                return json.load(entry_file)                
            except json.JSONDecodeError:
                pass
            except:
                print('Error in ConfigManager.read()')

        with open(entry_path, 'r') as entry_file:
                content = entry_file.read().splitlines()
                if len(content) == 1:
                    return content[0].strip()
                else:
                    return content

    def delete(self, section, entry):
        entry_path = self._get_entry_path(section, entry)

        if not os.path.exists(entry_path):
            raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')

        os.remove(entry_path)

    def delete_section(self, section):
        section_path = self._get_section_path(section)

        if not os.path.exists(section_path):
            raise FileNotFoundError(f'Config section "{section}" not found.')

        for entry in os.listdir(section_path):
            os.remove(os.path.join(section_path, entry))
        os.rmdir(section_path)

if __name__ == "__main__":
    try:
        args = parse_arguments()        
        main()
    except KeyboardInterrupt:
        print('Exit !')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
