import os
import sys
import logging
import argparse
import datetime
import dti_utils
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def prepare_topup_files(folder, dti_ref_ap_file, dti_ref_pa_file, sbref_appa_file, env):
    """Merges SBREF AP-PA and creates acqparams.txt.
    
    Args:
        folder (str): Path to the output folder.
        dti_ref_ap_file (str): Path to the AP reference file.
        dti_ref_pa_file (str): Path to the PA reference file.
        sbref_appa_file (str): Path to the SBREF AP-PA file.
        env (dict): Environment variables.
    """
    # Merge SBREF AP-PA
    dti_utils.run_command(['fslmerge', '-t', os.path.join(folder, sbref_appa_file), dti_ref_ap_file, dti_ref_pa_file], env=env)
    
    # Create acqparams.txt
    # 0.001 * 0.69 * (140-1) = 0.09591
    acqparams_content = "0 -1 0 0.09591\n0 1 0 0.09591"
    with open(os.path.join(folder, 'acqparams.txt'), 'w') as f:
        f.write(acqparams_content)


def run_topup(folder, sbref_appa_file, env):
    """Runs topup.
    
    Args:
        folder (str): Path to the output folder.
        sbref_appa_file (str): Path to the SBREF AP-PA file.
        env (dict): Environment variables.
    """
    dti_utils.run_command([
        'topup',
        f'--imain={os.path.join(folder, sbref_appa_file)}',
        f'--datain={os.path.join(folder, "acqparams.txt")}',
        '--config=b02b0.cnf',
        f'--out={os.path.join(folder, "topup_results")}',
        f'--iout={os.path.join(folder, "hifi_b0")}'
    ], env=env)


def prepare_eddy_files(folder, dti_ap_file, dti_pa_file, dti_appa_file, bvec_ap, bvec_pa, bval_ap, bval_pa, env):
    """Prepares files for eddy: mean/bet, merge dwi, index, bvals/bvecs.
    
    Args:
        folder (str): Path to the output folder.
        dti_ap_file (str): Path to the AP DTI file.
        dti_pa_file (str): Path to the PA DTI file.
        dti_appa_file (str): Path to the AP-PA DTI file.
        bvec_ap (str): Path to the AP bvec file.
        bvec_pa (str): Path to the PA bvec file.
        bval_ap (str): Path to the AP bval file.
        bval_pa (str): Path to the PA bval file.
        env (dict): Environment variables.
    """
    # Mean and Bet
    dti_utils.run_command(['fslmaths', os.path.join(folder, 'hifi_b0'), '-Tmean', os.path.join(folder, 'mean_hifi_b0')], env=env)
    dti_utils.run_command(['bet', os.path.join(folder, 'mean_hifi_b0'), os.path.join(folder, 'mean_hifi_b0_brain'), '-f', '0.7', '-m'], env=env)
    
    # Concatenate DTI (multiband) AP-PA
    dti_utils.run_command(['fslmerge', '-t', os.path.join(folder, dti_appa_file), dti_ap_file, dti_pa_file], env=env)
    
    # Create index.txt
    index_content = " ".join(["1"] * 100 + ["2"] * 100)
    with open(os.path.join(folder, 'index.txt'), 'w') as f:
        f.write(index_content)
        
    # Concatenate bvals and bvecs
    dti_utils.run_command(f"paste -d ' ' {bvec_ap} {bvec_pa} > {os.path.join(folder, 'BVEC_concat_APPA.bvec')}", env=env, shell=True)
    dti_utils.run_command(f"paste -d ' ' {bval_ap} {bval_pa} > {os.path.join(folder, 'BVAL_concat_APPA.bval')}", env=env, shell=True)


def run_eddy(folder, dti_appa_file, env):
    """Runs eddy_openmp.
    
    Args:
        folder (str): Path to the output folder.
        dti_appa_file (str): Path to the AP-PA DTI file.
        env (dict): Environment variables.
    """
    dti_utils.run_command([
        'eddy_openmp',
        f'--imain={os.path.join(folder, dti_appa_file)}',
        f'--mask={os.path.join(folder, "mean_hifi_b0_brain_mask")}',
        f'--acqp={os.path.join(folder, "acqparams.txt")}',
        f'--index={os.path.join(folder, "index.txt")}',
        f'--bvecs={os.path.join(folder, "BVEC_concat_APPA.bvec")}',
        f'--bvals={os.path.join(folder, "BVAL_concat_APPA.bval")}',
        f'--topup={os.path.join(folder, "topup_results")}',
        '--repol', # instructs eddy to remove any slices deemed outliers and replace them with predictions made by the Gaussian Process
        f'--out={os.path.join(folder, "eddy_corrected_data")}'
    ], env=env)


def process_t1_mask(folder, t1, env):
    """Makes brain mask from T1w and expands it.
    
    Args:
        folder (str): Path to the output folder.
        t1 (str): Path to the T1w file.
        env (dict): Environment variables.
    """
    dti_utils.run_command(['flirt', '-ref', os.path.join(folder, 'mean_hifi_b0'), '-in', t1, '-omat', os.path.join(folder, 'T1w2SBdMRI')], env=env)
    dti_utils.run_command(['bet', t1, os.path.join(folder, 'T1w_brain'), '-f', '0.15', '-m', '-R', '-B'], env=env)
    dti_utils.run_command([
        'flirt', '-in', os.path.join(folder, 'T1w_brain_mask'),
        '-ref', os.path.join(folder, 'mean_hifi_b0'),
        '-applyxfm', '-init', os.path.join(folder, 'T1w2SBdMRI'),
        '-out', os.path.join(folder, 'T1w_brain_mask_dMRIres')
    ], env=env)
    
    # Expansion
    dti_utils.run_command([
        'fslmaths', os.path.join(folder, 'T1w_brain_mask_dMRIres'),
        '-dilD', '-kernel', '3D',
        os.path.join(folder, 'T1w_brain_mask_dMRIres_exp')
    ], env=env)


def run_dtifit(folder, env):
    """Runs dtifit.
    
    Args:
        folder (str): Path to the output folder.
        env (dict): Environment variables.
    """
    dti_utils.run_command([
        'dtifit',
        '-k', os.path.join(folder, 'eddy_corrected_data'),
        '-o', os.path.join(folder, 'dti_fit_data'),
        '-m', os.path.join(folder, 'T1w_brain_mask_dMRIres_exp'),
        '-r', os.path.join(folder, 'eddy_corrected_data.eddy_rotated_bvecs'),
        '-b', os.path.join(folder, 'BVAL_concat_APPA.bval')
    ], env=env)


def process_subject(args):
    """Processes a single subject.
    
    Args:
        args (tuple): Tuple containing subject and config.
    """
    subject, config = args
    
    # Unpack config
    bids_dir = config['bids_dir']
    output_dir = config['output_dir']
    session = config['session']
    fsl_dir = config['fsl_dir']
    remote_host = config.get('remote_host')
    force_remote = config.get('force_remote', False)

    env = dti_utils.setup_fsl_environment(fsl_dir)
    
    logger.info(f"Starting processing for subject: {subject}")
    
    try:
        # Define paths
        folder_in = os.path.join(bids_dir, subject, session, 'dwi')
        folder_in_ref = os.path.join(bids_dir, subject, session, 'fmap')
        folder_in_t1 = os.path.join(bids_dir, subject, session, 'anat')
        
        dti_ref_ap_file = os.path.join(folder_in_ref, f"{subject}_{session}_acq-dwisefm_dir-ap_run-01_epi.nii.gz")
        dti_ref_pa_file = os.path.join(folder_in_ref, f"{subject}_{session}_acq-dwisefm_dir-pa_run-01_epi.nii.gz")
        dti_ap_file = os.path.join(folder_in, f"{subject}_{session}_dir-ap_run-01_dwi.nii.gz")
        dti_pa_file = os.path.join(folder_in, f"{subject}_{session}_dir-pa_run-01_dwi.nii.gz")
        
        bval_ap = os.path.join(folder_in, f"{subject}_{session}_dir-ap_run-01_dwi.bval")
        bval_pa = os.path.join(folder_in, f"{subject}_{session}_dir-pa_run-01_dwi.bval")
        bvec_ap = os.path.join(folder_in, f"{subject}_{session}_dir-ap_run-01_dwi.bvec")
        bvec_pa = os.path.join(folder_in, f"{subject}_{session}_dir-pa_run-01_dwi.bvec")
        
        t1 = os.path.join(folder_in_t1, f"{subject}_{session}_run-01_T1w.nii.gz")
        
        # Create output folder
        folder = os.path.join(output_dir, f"{subject}_{session}")
        os.makedirs(folder, exist_ok=True)
        
        # Create temp input folder if fetching from remote
        # This is for if were running on cluster and the files are on workstation
        temp_input_dir = None
        if remote_host:
            temp_input_dir = os.path.join(folder, "temp_BIDS")
            os.makedirs(temp_input_dir, exist_ok=True)
            
            # Update local paths to point to temp dir
            dti_ref_ap_file_local = os.path.join(temp_input_dir, os.path.basename(dti_ref_ap_file))
            dti_ref_pa_file_local = os.path.join(temp_input_dir, os.path.basename(dti_ref_pa_file))
            dti_ap_file_local = os.path.join(temp_input_dir, os.path.basename(dti_ap_file))
            dti_pa_file_local = os.path.join(temp_input_dir, os.path.basename(dti_pa_file))
            bval_ap_local = os.path.join(temp_input_dir, os.path.basename(bval_ap))
            bval_pa_local = os.path.join(temp_input_dir, os.path.basename(bval_pa))
            bvec_ap_local = os.path.join(temp_input_dir, os.path.basename(bvec_ap))
            bvec_pa_local = os.path.join(temp_input_dir, os.path.basename(bvec_pa))
            t1_local = os.path.join(temp_input_dir, os.path.basename(t1))

            # Fetch files to temp dir
            dti_utils.ensure_remote_file(dti_ref_ap_file_local, remote_host, dti_ref_ap_file, force=force_remote)
            dti_utils.ensure_remote_file(dti_ref_pa_file_local, remote_host, dti_ref_pa_file, force=force_remote)
            dti_utils.ensure_remote_file(dti_ap_file_local, remote_host, dti_ap_file, force=force_remote)
            dti_utils.ensure_remote_file(dti_pa_file_local, remote_host, dti_pa_file, force=force_remote)
            dti_utils.ensure_remote_file(bval_ap_local, remote_host, bval_ap, force=force_remote)
            dti_utils.ensure_remote_file(bval_pa_local, remote_host, bval_pa, force=force_remote)
            dti_utils.ensure_remote_file(bvec_ap_local, remote_host, bvec_ap, force=force_remote)
            dti_utils.ensure_remote_file(bvec_pa_local, remote_host, bvec_pa, force=force_remote)
            dti_utils.ensure_remote_file(t1_local, remote_host, t1, force=force_remote)
            
            # Update variables to use local temp paths
            dti_ref_ap_file = dti_ref_ap_file_local
            dti_ref_pa_file = dti_ref_pa_file_local
            dti_ap_file = dti_ap_file_local
            dti_pa_file = dti_pa_file_local
            bval_ap = bval_ap_local
            bval_pa = bval_pa_local
            bvec_ap = bvec_ap_local
            bvec_pa = bvec_pa_local
            t1 = t1_local

        # Check if input files exist (either local or remotely) using one key file as a proxy
        if not os.path.exists(dti_ap_file):
             logger.warning(f"DWI file not found for {subject}: {dti_ap_file}")
             return False

        sbref_appa_file = 'sbref_APPA'
        dti_appa_file = 'alldirections_APPA'
        
        # Execute steps        
        logger.info(f"[{subject}] Preparing topup files")
        prepare_topup_files(folder, dti_ref_ap_file, dti_ref_pa_file, sbref_appa_file, env)
        
        logger.info(f"[{subject}] Running topup")
        run_topup(folder, sbref_appa_file, env)
        
        logger.info(f"[{subject}] Preparing eddy files")
        prepare_eddy_files(folder, dti_ap_file, dti_pa_file, dti_appa_file, bvec_ap, bvec_pa, bval_ap, bval_pa, env)
        
        logger.info(f"[{subject}] Running eddy")
        try:
            run_eddy(folder, dti_appa_file, env)
        except Exception:
            logger.warning(f"[{subject}] Eddy failed. This might be because the data has fewer volumes than the expected 100 per direction. Check if the sub has two runs.")
            raise
        
        logger.info(f"[{subject}] Processing T1 mask")
        process_t1_mask(folder, t1, env)
        
        logger.info(f"[{subject}] Running DTI fit")
        run_dtifit(folder, env)
        
        logger.info(f"[{subject}] Processing complete.")
        return True

    except Exception as e:
        logger.error(f"[{subject}] Error processing subject: {e}")
        return False
    finally:
        # Cleanup temp input dir
        if 'temp_input_dir' in locals() and temp_input_dir and os.path.exists(temp_input_dir):
            logger.info(f"[{subject}] Cleaning up temp input directory: {temp_input_dir}")
            import shutil
            shutil.rmtree(temp_input_dir)


def main():
    parser = argparse.ArgumentParser(description="Parallel DTI Preprocessing Pipeline (SLURM)")
    parser.add_argument('--worker', action='store_true', help='Run in worker mode (called by SLURM)')
    parser.add_argument('--report', action='store_true', help='Run in report mode (called by SLURM)')
    parser.add_argument('--subjects_list', help='Path to subjects list file (required for worker/report)')
    parser.add_argument('--force_remote', action='store_true', help='Force fetching files from remote even if they exist locally')
    args = parser.parse_args()

    # Configuration 
    COHORT = 'bbhi senior'
    SESSION = 'ses-01'
    TIMEPOINT = int(SESSION.split('-')[1])    

    if COHORT == 'bbhi':
        BIDS_DIR = '/pool/guttmann/institut/BBHI/MRI/BIDS'
        OUTPUT_DIR = '/psiquiatria/home/oriol/Desktop/dwi_preprocessing_6_0_4/bbhi'
        if SESSION == 'ses-01':
            SHARED_OUTPUT_DIR = '/pool/guttmann/institut/BBHI/MRI/processed_data/dtifit_ses-01_fsl-604'
        else:
            SHARED_OUTPUT_DIR = '/pool/guttmann/institut/BBHI/MRI/processed_data/dtifit_ses-02_fsl-604'
    else:
        BIDS_DIR = '/pool/guttmann/institut/UB/Superagers/MRI/BIDS'
        OUTPUT_DIR = '/psiquiatria/home/oriol/Desktop/dwi_preprocessing_6_0_4/bbhi_senior'
        if SESSION == 'ses-01':
            SHARED_OUTPUT_DIR = '/pool/guttmann/institut/UB/Superagers/MRI/dtifit_ses-01_fsl-604'
        else:
            SHARED_OUTPUT_DIR = '/pool/guttmann/institut/UB/Superagers/MRI/dtifit_ses-02_fsl-604'
    
    FSL_DIR = f'/global/software/fsl_6_0_4'
    REMOTE_HOST = 'oriol@161.116.166.234'
    FORCE_REMOTE = True # Set to True to always fetch remote files
    # NOTE that the total cores used is MAX_PARALLEL_JOBS * N_PROCS
    N_PROCS = 4 # CPUs per task in SLURM
    MAX_PARALLEL_JOBS = 9 # Limit number of simultaneous jobs
    
    # Ensure output directory exists
    print(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    force_remote = args.force_remote or FORCE_REMOTE
        
    # Prepare arguments for worker function
    config = {
        'bids_dir': BIDS_DIR,
        'output_dir': OUTPUT_DIR,
        'session': SESSION,
        'fsl_dir': FSL_DIR,
        'n_procs': N_PROCS,
        'max_parallel_jobs': MAX_PARALLEL_JOBS,
        'remote_host': REMOTE_HOST,
        'force_remote': force_remote
    }

    if args.worker:
        # WORKER MODE - runs the process_subject function for a single subject
        if not args.subjects_list:
            logger.error("Worker mode requires --subjects_list")
            sys.exit(1)
            
        task_id = os.environ.get('SLURM_ARRAY_TASK_ID')
        if not task_id:
            logger.error("SLURM_ARRAY_TASK_ID not found")
            sys.exit(1)
            
        try:
            idx = int(task_id) - 1 # SLURM is 1-indexed
            with open(args.subjects_list, 'r') as f:
                subjects = [line.strip() for line in f if line.strip()]
                
            if 0 <= idx < len(subjects):
                subject = subjects[idx]
                logger.info(f"Worker processing subject {idx+1}/{len(subjects)}: {subject}")
                success = process_subject((subject, config))
                
                # Create a success marker file
                if success:
                    marker_dir = os.path.join(OUTPUT_DIR, "status")
                    os.makedirs(marker_dir, exist_ok=True)
                    with open(os.path.join(marker_dir, f"{subject}.done"), 'w') as f:
                        f.write(datetime.datetime.now().isoformat())
            else:
                logger.error(f"Task ID {task_id} out of range")
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"Worker failed: {e}")
            sys.exit(1)

    elif args.report:
        # REPORT MODE - checks if all subjects have been processed
        if not args.subjects_list:
            logger.error("Report mode requires --subjects_list")
            sys.exit(1)
            
        try:
            with open(args.subjects_list, 'r') as f:
                subjects = [line.strip() for line in f if line.strip()]
            
            marker_dir = os.path.join(OUTPUT_DIR, "status")
            successful_subjects = []
            
            for sub in subjects:
                if os.path.exists(os.path.join(marker_dir, f"{sub}.done")):
                    successful_subjects.append(sub)
            
            logger.info(f"Reporting: {len(successful_subjects)}/{len(subjects)} subjects successful.")
            dti_utils.create_dataset_description(OUTPUT_DIR, FSL_DIR, successful_subjects, SESSION)
            
            # Cleanup marker dir
            shutil.rmtree(marker_dir)
            
            # Cleanup submission files
            try:
                basename = os.path.basename(args.subjects_list)
                if basename.startswith("subjects_to_process_") and basename.endswith(".txt"):
                    timestamp = basename[len("subjects_to_process_"):-4]
                    
                    submit_report_file = f"submit_report_{timestamp}.sh"
                    submit_array_file = f"submit_array_{timestamp}.sh"
                    
                    if os.path.exists(submit_report_file):
                        os.remove(submit_report_file)
                        
                    if os.path.exists(submit_array_file):
                        os.remove(submit_array_file)
                        
                    if os.path.exists(args.subjects_list):
                        os.remove(args.subjects_list)
            except Exception as e:
                logger.warning(f"Failed to cleanup submission files: {e}")
            
        except Exception as e:
            logger.error(f"Report failed: {e}")
            sys.exit(1)

    else:
        # SUBMITTER MODE - submits the SLURM workflow
        subjects = dti_utils.get_subjects_to_process(BIDS_DIR, SHARED_OUTPUT_DIR, SESSION, remote_host=REMOTE_HOST)

        # Optionally set a specific list of subs for processing
        # subjects = ["sub-3010", "sub-3018", "sub-3035", "sub-2003"]

        if not subjects:
            logger.info("No subjects found to process.")
            sys.exit(0)
            
        logger.info(f"Found {len(subjects)} subjects to process.")
        
        script_path = os.path.abspath(__file__)
        dti_utils.submit_slurm_workflow(subjects, config, script_path)


if __name__ == "__main__":
    main()
