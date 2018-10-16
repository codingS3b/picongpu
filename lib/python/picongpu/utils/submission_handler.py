import os
import subprocess
import itertools

from .misc import get_all_scans, get_all_sims, get_running_id
from .param_parser import read_range_file, write_range_file


class SubmissionHandler(object):
    """
    Class that is responsible for building and running picongpu with the
    user specified parameter values.
    """

    def __init__(self, user_path, parameters):
        """
        Parameters
        ----------
        user_path: string
            full path for storing scan data.
        parameters: list
            a list of Parameter objects
        """
        self.path = user_path
        self.param_filename = "params.json"

        self.parameters = parameters

    def _scan_existing_experiments(self, param_values):
        """
        Scans all experimental folders (starting with 'exp_') in "user_path"
        for a params.json file and compares their values to the ones of
        param_values

        Parameters
        ----------
        param_values: dict
            Maps parameter names to their value on PIC scale.

        Returns
        -------
        If a match occurs, the full path to the experiment with matching
        parameter values. None otherwise.
        """
        # get all scans
        for scan in get_all_scans(self.path):
            scan_dir = os.path.join(self.path, scan)
            for sim in get_all_sims(scan_dir):
                # read the param_set
                f = os.path.join(scan_dir, sim, self.param_filename)
                param_config_from_file = read_range_file(f)
                if param_config_from_file == param_values:
                    return os.path.join(scan_dir, sim)

        # did not find a simulation that matches user_params exactly
        return None

    def submit_scan(self, ranges):
        """
        Submit a whole parameter scan to the cluster,
        i.e. lots of single simulation runs for the cross product
        of all parameters values.

        Parameters
        ----------
        ranges: dict
            dictionary with parameter names mapping to a list of their values.

        Returns
        -------
        The name of the newly created scan directory
        """

        # 1) create a new scan directory
        all_scans = get_all_scans(self.path)
        last_scan_id = get_running_id(all_scans)
        scan_dir = os.path.join(
            self.path,
            "scan_{number:0>#4d}".format(number=last_scan_id + 1))
        os.mkdir(scan_dir)

        # 2) write out a scan_ranges.json inside the scan directory
        scan_file = os.path.join(scan_dir, "scan_ranges.json")
        write_range_file(ranges, self.parameters, scan_file)

        # 3) for each combination of parameters, submit a single simulation
        # but check if that simulation has run before in a different scan.
        # if this is the case, create symlink to that scan if necessary

        # the order of each output tuple is guaranteed to be the same as
        # was passed into the itertools.product() function
        param_names = list(ranges.keys())
        range_lists = list(ranges.values())
        all_combinations = itertools.product(*range_lists)
        for comb in all_combinations:
            # combine names of the parameters with their values
            # to make it the same format as the ranges, use
            # list of one element as value
            comb = [[val] for val in comb]
            p_dict = dict(zip(param_names, comb))

            existing_sim = self.submit_job(scan_dir, p_dict)
            if existing_sim is None:
                # a new simulation was started since the configuration of
                # parameters does not exist yet
                print("submitted simulation\n", p_dict)
            else:
                # The parameter configuration already existed, so no new
                # simulation was started.
                # Therefore we get the name of the matching simulation and
                # create a symlink

                print("Did not submit simulation\n", p_dict,
                      "\nsince it already exists at ", existing_sim,
                      ". Creating symlink instead!")
                # now create a symlink to that file
                # create correct name of the simulation
                all_sims = get_all_sims(scan_dir)
                last_sim_id = get_running_id(all_sims)
                sim = "sim_{number:0>#4d}".format(number=last_sim_id + 1)
                sim_name = os.path.join(scan_dir, sim)
                # symlink src=location to point to, dst=location and name of the link
                os.symlink(src=existing_sim, dst=sim_name)

        return os.path.basename(scan_dir)

    def submit_job(self, scan_dir, param_values):
        """
        Scans all existing user experiments for the same parameter
        configuration to avoid running the same experiment more than
        once.
        If no existing experiment is found, new compile and run jobs to
        hypnos cluster are submitted.

        Parameters
        ----------
        scan_dir: string
            The full path to the the scan directory where a new simulation
            should be added
        param_values: dict
            Dictionary with keys = names of the parameters and values their
            PIC values which will be passed to the simulation

        Returns
        -------
        None if a new job was submitted.
        The full path to the simulation directory for a matching simulation in a different
        scan directory otherwise.
        """
        # check if new run is necessary or there is an already existing
        # experiment with the exact same parameter configuration in
        # any of the scans

        existing_exp = self._scan_existing_experiments(param_values)

        if existing_exp is not None:
            return existing_exp

        # get the values from the parameters and store them in "params.json" file
        all_sims = get_all_sims(scan_dir)
        last_num = get_running_id(all_sims)
        # this assumes simulation folders are labeled something like sim_1, sim_2 where the number goes after the last _
        # in the filename!
        # name for the current experiments directory
        sim_dir = "sim_{number:0>#4d}".format(number=last_num + 1)
        sim_path = os.path.join(scan_dir, sim_dir)
        os.mkdir(sim_path)

        # create the params.json file for the current experiments parameters
        sim_file = os.path.join(sim_path, "params.json")
        write_range_file(param_values, self.parameters, sim_file)

        self._execute_submit(sim_path)

    def _execute_submit(self, sim_path):
        # compile job and run job submitted via tbg
        # TODO: how to get rid of the two members?
        proc = subprocess.Popen([
            "tbg",
            "-s", "--force",
            '-c', os.path.join(self.eupraxia_base_dir,
                               "etc/picongpu/compile.cfg"),
            '-t', os.path.join(self.eupraxia_base_dir,
                               "etc/picongpu/hypnos-hzdr/compile_laser.tpl"),
            '-o', "TBG_job_src=" + self.job_src,
            sim_path],
            stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        proc.wait()
        stderr = proc.stderr.read()

        if stderr:
            msg = "A possible error in TBG occured while submitting compile job. "
            msg += str(stderr)
            raise RuntimeError(msg)

    def _get_job_id(self, path_to_sim, status):
        """
        Returns a dictionary with the batch systems job id
        for the selected simulation.

        The job id is created from some magic within our picongpu.profile:
            function qsubWrapper {
                @TORQUE_BASE_DIR@/bin/qsub $@ >> "$TBG_dstPath"/jobid
                return $?
            }
            export -f qsubWrapper
            export TBG_SUBMIT="qsubWrapper"

        Parameters
        ----------
        path_to_sim: str
            full path to a simulation directory
        status: str
            specify which job id should be returned.
            Should be either "running" or "compiling"

        Returns
        -------
        None when reading the job_file failed or the status requested
        was neither 'compiling' nor 'running'.
        Otherwise, return the job id
        """
        job_id_file = None
        if status == "compiling":
            job_id_file = os.path.join(path_to_sim, 'jobid')
        elif status == "running":
            job_id_file = os.path.join(path_to_sim, 'run', 'jobid')
        else:
            # for finished simulations we dont' need to return
            # a valid id
            return None

        # check that job has already been submitted and has an id
        try:
            with open(job_id_file, 'r') as f:
                return f.read().strip()
        except:
            return None

    def abort_scan(self, scan_to_abort):
        """
        Cancels all jobs that have not finished yet for the
        selected scan.

        Parameters
        ----------
        scan_to_abort: str
            the name of the scan directory that should be aborted
        """
        # when NEW_SCAN is selected, we do nothing
        if not scan_to_abort.startswith("scan_"):
            return

        # TODO: how to deal with the CMAKE defines like TORQUE_BASE_DIR?
        qdelPath = os.path.join(os.environ['TORQUE_BASE_DIR'], "bin/qdel")
        path_to_scan = os.path.join(self.path, scan_to_abort)
        # get the job ids of all the simulations of
        # the scan that have not finished yet
        sims = get_all_sims(path_to_scan)
        all_sim_paths = [os.path.join(path_to_scan, sim) for sim in sims]
        for path_to_sim in all_sim_paths:
            # check if the run job was started and try deleting
            job_id = self._get_job_id(path_to_sim, 'running')
            if job_id is not None:
                ret_val = subprocess.call(
                    ["ssh", "hypnos4", qdelPath, str(job_id)])
                if ret_val > 0:
                    # deleting running job failed
                    # that means we are finished with this job
                    print(os.path.basename(path_to_sim),
                          "has already finished and can't be aborted")
                    continue

                else:
                    print("deleted running job ", job_id)
            else:
                # we did not get a valid job_id for the 'run' job
                # so now we test if the compile job is there
                job_id = self._get_job_id(path_to_sim, 'compiling')
                if job_id is not None:
                    ret_val = subprocess.call(
                        ["ssh", "hypnos4", qdelPath, str(job_id)])
                    if ret_val > 0:
                        # deleting the compile job failed
                        # this means: compile job meanwhile has finished and
                        # run job has started, so try deleting that again

                        # TODO: this can also happen if we aborted jobs and try to abort them
                        # again: prevent this maybe by adding another status 'aborted'
                        job_id = self._get_job_id(path_to_sim, 'running')
                        # this runs asynchronously, does not wait for completion
                        subprocess.Popen(
                            ["ssh", "hypnos4", qdelPath, str(job_id)])
                        print("deleting running job ", job_id)
                    else:
                        print("deleted compile job ", job_id)
                        # TODO: when we were still compiling, we don't have data yet
                        # so we could remove those simulations from the users path
                else:
                    # the compile job has not been submitted yet
                    pass
