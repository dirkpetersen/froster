import os
import hashlib
import concurrent.futures


def md5sum(file_path):
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

def gen_md5sums(directory, hash_file, num_workers, exclude_subdirs=True):
    for root, dirs, files in os.walk(directory):
        if exclude_subdirs and root != directory:
            break

        with open(os.path.join(root, hash_file), "w") as out_f:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                tasks = {}
                for filen in files:
                    file_path = os.path.join(root, filen)
                    if os.path.isfile(file_path) and filen != os.path.basename(hash_file):
                        task = executor.submit(md5sum, file_path)
                        tasks[task] = file_path

                for future in concurrent.futures.as_completed(tasks):
                    filen = os.path.basename(tasks[future])
                    md5 = future.result()
                    out_f.write(f"{md5}  {filen}\n")





# Example usage:
gen_md5sums("./tests", ".md5sums.froster", num_workers=4, exclude_subdirs=True)


