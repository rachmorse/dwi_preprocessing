#!/bin/bash
#SBATCH --partition=batch
#SBATCH --job-name=dwiprep-%j
#SBATCH --output=dwiprep-%A_%a.out 
#SBATCH --error=dwiprep-%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4  # Limit each job to 4 CPUs
#SBATCH --mem=4G
#SBATCH --array=1-3%2  # Run 2 jobs in parallel. NOTE: Need to adjust the range based on the number of subjects to process (eg 1-x number of subjects)

module load fsl/6.0.4

# Obtain the corresponding subject
SUBJECTS_LIST="/psiquiatria/home/oriol/Desktop/DWI_preproc/subjects.txt"
SUBJECT=$(sed -n "${SLURM_ARRAY_TASK_ID}p" $SUBJECTS_LIST | tr -d '\n')

# Execute script for the selected subject
/psiquiatria/home/oriol/Desktop/scripts/UTF-8DWI_preproc/DWI_preproc/DTI_script.sh "$SUBJECT"