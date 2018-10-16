import os


def get_all_dirs_with_prefix(path, prefix):
    """
    Returns all directories starting with a given prefix within the given
    path
    """
    dirs = [d for d in os.listdir(
        path) if os.path.isdir(os.path.join(path, d))]

    prefix_filtered = [d for d in dirs if d.startswith(prefix)]
    return sorted(prefix_filtered)


def get_all_scans(path):
    """
    """
    return get_all_dirs_with_prefix(path, "scan_")


def get_all_sims(path):
    """
    """
    return get_all_dirs_with_prefix(path, "sim_")


def get_running_id(filtered_dirs):
    """
    From a list of string names (scans or simulations)
    that follow the schema 'sim_<id>', where id is a running integer, returns
    the maximum number.
    """

    return max(
        [int(os.path.basename(d).split("_")[1]) for d in filtered_dirs],
        default=0)