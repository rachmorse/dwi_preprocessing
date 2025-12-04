import os
import sys
import subprocess
import logging
import json
import datetime
import socket


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_command(cmd, env=None, shell=False, log_command=True):
    """Runs a shell command and logs output.
    
    Args:
        cmd (list or str): Command to run.
        env (dict, optional): Environment variables to use. Defaults to None.
        shell (bool, optional): Whether to run the command in a shell. Defaults to False.
        log_command (bool, optional): Whether to log the command itself. Defaults to True.
    
    Returns:
        str: Command output.
    """
    if log_command:
        logger.info(f"Running command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        result = subprocess.run(
            cmd,
            env=env,
            shell=shell,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.cmd}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        raise


def setup_fsl_environment(fsl_dir):
    """Sets up FSL environment variables to ensure using the correct version of FSL.
    
    Args:
        fsl_dir (str): Path to the FSL installation directory.
    
    Returns:
        dict: Environment variables with FSL paths set.
    """
    env = os.environ.copy()
    env["FSLDIR"] = fsl_dir
    env["PATH"] = f"{fsl_dir}/bin:" + env.get("PATH", "")
    env["FSLOUTPUTTYPE"] = "NIFTI_GZ"
    return env


def get_subjects_from_remote(remote_host, bids_dir, output_dir, session):
    """Scans remote BIDS directory for valid subjects using SSH.
    Also checks if output already exists on remote.
    
    Args:
        remote_host (str): Remote host (user@ip).
        bids_dir (str): Path to BIDS directory on remote.
        output_dir (str): Path to output directory on remote.
        session (str): Session identifier.
        
    Returns:
        list: List of subject IDs to process.
    """
    logger.info(f"Scanning remote host {remote_host} for subjects in {bids_dir}...")
    
    remote_cmd = f"""
    for s_dir in {bids_dir}/sub-*; do
        [ -d "$s_dir" ] || continue
        subject=$(basename "$s_dir")
        
        folder_in="$s_dir/{session}/dwi"
        folder_in_ref="$s_dir/{session}/fmap"
        folder_in_t1="$s_dir/{session}/anat"
        
        dti_ap="$folder_in/${{subject}}_{session}_dir-ap_run-01_dwi.nii.gz"
        dti_pa="$folder_in/${{subject}}_{session}_dir-pa_run-01_dwi.nii.gz"
        fmap_ap="$folder_in_ref/${{subject}}_{session}_acq-dwisefm_dir-ap_run-01_epi.nii.gz"
        fmap_pa="$folder_in_ref/${{subject}}_{session}_acq-dwisefm_dir-pa_run-01_epi.nii.gz"
        t1w="$folder_in_t1/${{subject}}_{session}_run-01_T1w.nii.gz"
        
        missing=""
        missing_count=0
        
        [ ! -f "$dti_ap" ] && missing="$missing 'DWI AP'" && missing_count=$((missing_count+1))
        [ ! -f "$dti_pa" ] && missing="$missing 'DWI PA'" && missing_count=$((missing_count+1))
        [ ! -f "$fmap_ap" ] && missing="$missing 'FMAP AP'" && missing_count=$((missing_count+1))
        [ ! -f "$fmap_pa" ] && missing="$missing 'FMAP PA'" && missing_count=$((missing_count+1))
        [ ! -f "$t1w" ] && missing="$missing 'T1w'" && missing_count=$((missing_count+1))
        
        if [ "$missing_count" -eq 0 ]; then
            # All files present
            # Check if output exists remotely
            final_output="{output_dir}/${{subject}}_{session}/dti_fit_data_FA.nii.gz"
            if [ ! -f "$final_output" ]; then
                echo "FOUND:$subject"
            else
                echo "EXIST:$subject"
            fi
        elif [ "$missing_count" -eq 5 ]; then
            # All files missing - skip silently (or debug)
            echo "SKIP_ALL:$subject"
        else
            # Some files missing - report
            echo "MISSING:$subject:$missing"
        fi
    done
    """
    
    try:
        # Run the command via SSH
        cmd = ['ssh', remote_host, remote_cmd]
        output = run_command(cmd, log_command=False)
        
        subjects = []
        for line in output.splitlines():
            line = line.strip()
            if not line: continue
            
            if line.startswith("FOUND:"):
                subjects.append(line.split(":")[1])
            elif line.startswith("MISSING:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    sub = parts[1]
                    missing = parts[2].strip()
                    logger.info(f"Skipping {sub}: Missing inputs [{missing}]")
            elif line.startswith("EXIST:"):
                sub = line.split(":")[1]
                logger.debug(f"Skipping {sub}: Output already exists on remote")
            elif line.startswith("SKIP_ALL:"):
                sub = line.split(":")[1]
                logger.debug(f"Skipping {sub}: Missing all data")
                
        logger.info(f"Found {len(subjects)} subjects on remote (excluding existing outputs).")
        return subjects
    except Exception as e:
        logger.error(f"Failed to scan remote subjects: {e}")
        return []


def get_subjects_to_process(bids_dir, output_dir, session, remote_host=None):
    """Generate a list of subjects to process based on whether they have the necessary
    input files and don't already have the final output.

    Args:
        bids_dir (str): Path to the BIDS directory.
        output_dir (str): Path to the output directory.
        session (str): Timepoint (e.g., 'ses-01').
        remote_host (str, optional): Remote host to scan if local BIDS dir is missing.

    Returns:
        list: List of subjects to process.
    """
    subjects_to_process = []
    
    # Check if BIDS directory exists locally
    if not os.path.exists(bids_dir):
        if remote_host:
            logger.info(f"BIDS directory {bids_dir} not found locally. Trying remote scan...")
            # If not found locally, try remote
            all_subjects = get_subjects_from_remote(remote_host, bids_dir, output_dir, session)
            return all_subjects
        else:
            logger.error(f"BIDS directory {bids_dir} not found and no remote host provided.")
            return []

    # If not remote, scan local BIDS directory
    try:
        all_subjects = [d for d in os.listdir(bids_dir) if d.startswith('sub-') and os.path.isdir(os.path.join(bids_dir, d))]
    except OSError as e:
        logger.error(f"Error accessing BIDS directory: {e}")
        return []

    logger.info(f"Scanning {len(all_subjects)} subjects in {bids_dir}...")

    for subject in all_subjects:
        # Define expected input paths
        folder_in = os.path.join(bids_dir, subject, session, 'dwi')
        folder_in_ref = os.path.join(bids_dir, subject, session, 'fmap')
        folder_in_t1 = os.path.join(bids_dir, subject, session, 'anat')
        
        # Check for essential input files
        # We need AP/PA DWI, AP/PA SBRef (fmap), and T1w
        dti_ap = os.path.join(folder_in, f"{subject}_{session}_dir-ap_run-01_dwi.nii.gz")
        dti_pa = os.path.join(folder_in, f"{subject}_{session}_dir-pa_run-01_dwi.nii.gz")
        fmap_ap = os.path.join(folder_in_ref, f"{subject}_{session}_acq-dwisefm_dir-ap_run-01_epi.nii.gz")
        fmap_pa = os.path.join(folder_in_ref, f"{subject}_{session}_acq-dwisefm_dir-pa_run-01_epi.nii.gz")
        t1w = os.path.join(folder_in_t1, f"{subject}_{session}_run-01_T1w.nii.gz")
        
        missing_inputs = []
        if not os.path.exists(dti_ap): missing_inputs.append("DWI AP")
        if not os.path.exists(dti_pa): missing_inputs.append("DWI PA")
        if not os.path.exists(fmap_ap): missing_inputs.append("FMAP AP")
        if not os.path.exists(fmap_pa): missing_inputs.append("FMAP PA")
        if not os.path.exists(t1w): missing_inputs.append("T1w")
        
        # If sub missing all inputs tp2 data missing
        if len(missing_inputs) == 5:
            logger.debug(f"Skipping {subject}: Missing {session} data.")
            continue
        if len(missing_inputs) < 5 and len(missing_inputs) > 0:
            logger.info(f"Skipping {subject}: Missing inputs {missing_inputs}")
            continue
            
        # Check if output already exists
        final_output = os.path.join(output_dir, f"{subject}_{session}", "dti_fit_data_FA.nii.gz")
        if os.path.exists(final_output):
            logger.debug(f"Skipping {subject}: Output already exists")
            continue
            
        subjects_to_process.append(subject)
        
    logger.info(f"Found {len(subjects_to_process)} subjects ready for processing.")
    return subjects_to_process


def ensure_remote_file(local_path, remote_host, remote_path, force=False):
    """Checks if local file exists, if not (or if forced) scp from remote.
    scp is used to copy files from remote to local.
    
    Args:
        local_path (str): Path to the local file.
        remote_host (str): Remote host.
        remote_path (str): Path to the remote file.
        force (bool): If True, fetch even if local file exists.
    """
    if force or not os.path.exists(local_path):
        logger.info(f"Fetching {local_path} from {remote_host} (Force={force})...")
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            cmd = ['scp', f'{remote_host}:{remote_path}', local_path]
            run_command(cmd)
        except Exception as e:
            logger.error(f"Failed to fetch {local_path}: {e}")


def create_dataset_description(output_dir, fsl_dir, successful_subjects):
    """Creates BIDS compliant dataset_description.json.
    
    Args:
        output_dir (str): Path to the output directory.
        fsl_dir (str): Path to the FSL installation directory.
        successful_subjects (list): List of successfully processed subject IDs.
    """
    try:
        fsl_version_file = os.path.join(fsl_dir, "etc", "fslversion")
        with open(fsl_version_file, 'r') as f:
            fsl_version = f.read().strip()
    except FileNotFoundError:
        fsl_version = "unknown"
        
    hostname = socket.gethostname()
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        user = os.getlogin()
    except OSError:
        user = "unknown"
    
    dataset_description = {
        "Name": f"dMRI Preprocessing Output {date_str}",
        "BIDSVersion": "1.10.1",
        "PipelineDescription": {
            "Name": "dMRI Preprocessing Pipeline",
            "Version": "1.1",
            "RunOnMachine": hostname,
            "RunByUser": user,
            "Software": [
                {
                    "Name": "FSL",
                    "Version": fsl_version
                }
            ],
            "SubjectsProcessed": successful_subjects,
        }
    }
    
    output_file = os.path.join(output_dir, f"dataset_description_{date_str}.json")
    try:
        with open(output_file, 'w') as f:
            json.dump(dataset_description, f, indent=2)
        logger.info(f"Created dataset description at {output_file}")
    except IOError as e:
        logger.error(f"Failed to write dataset description: {e}")


def submit_slurm_workflow(subjects, config, script_path):
    """Submits SLURM job array and a dependent reporting job.
    
    Args:
        subjects (list): List of subjects to process.
        config (dict): Configuration dictionary.
        script_path (str): Path to the script to submit.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    subjects_file = f"subjects_to_process_{timestamp}.txt"
    
    # Write subjects to file
    with open(subjects_file, 'w') as f:
        for sub in subjects:
            f.write(f"{sub}\n")
    logger.info(f"Created subjects file: {subjects_file}")
    
    # 1. Submit Job Array (Worker)
    job_name = "dwiprep"
    
    # Create logs directory
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    output_log = os.path.join(logs_dir, "dwiprep-%A_%a.log")
    
    # Create a temporary submission script for the array
    array_script = f"submit_array_{timestamp}.sh"
    with open(array_script, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(f"#SBATCH --job-name={job_name}\n")
        f.write(f"#SBATCH --output={output_log}\n") # Combines stdout and stderr
        f.write(f"#SBATCH --partition=batch\n")
        f.write(f"#SBATCH --nodes=1\n")
        f.write(f"#SBATCH --ntasks=1\n")
        f.write(f"#SBATCH --cpus-per-task={config['n_procs']}\n")
        f.write(f"#SBATCH --mem=4G\n")
        f.write(f"#SBATCH --array=1-{len(subjects)}%{config['max_parallel_jobs']}\n")
        f.write(f"\n")
        cmd = f"{sys.executable} {script_path} --worker --subjects_list {subjects_file}"
        if config.get('force_remote'):
            cmd += " --force_remote"
        f.write(f"{cmd}\n")
        
    logger.info("Submitting SLURM job array...")
    # Capture the output to get the job ID
    try:
        output = run_command(['sbatch', array_script])
        job_id = output.strip().split()[-1]
        logger.info(f"Submitted Array Job ID: {job_id}")
    except Exception as e:
        logger.error(f"Failed to submit array job: {e}")
        return

    # 2. Submit Reporting Job (Dependent) for after array completion
    report_script = f"submit_report_{timestamp}.sh"
    with open(report_script, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(f"#SBATCH --job-name=dwiprep_report\n")
        f.write(f"#SBATCH --output={os.path.join(logs_dir, 'dwiprep_report-%j.log')}\n")
        f.write(f"#SBATCH --partition=batch\n")
        f.write(f"#SBATCH --nodes=1\n")
        f.write(f"#SBATCH --ntasks=1\n")
        f.write(f"#SBATCH --cpus-per-task=1\n")
        f.write(f"#SBATCH --mem=1G\n")
        f.write(f"#SBATCH --dependency=afterany:{job_id}\n") # Run even if some array jobs fail
        f.write(f"\n")
        f.write(f"python3 {script_path} --report --subjects_list {subjects_file}\n")
        
    logger.info("Submitting SLURM reporting job...")
    run_command(['sbatch', report_script])
