#!/bin/bash
#SBATCH --partition=batch
#SBATCH --job-name=dwiprep-%j
#SBATCH --output=dwiprep-%A_%a.out 
#SBATCH --error=dwiprep-%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4  # Limit each job to 4 CPUs
#SBATCH --mem=4G
#SBATCH --array=1-1  # Run 2 jobs in parallel. NOTE: Need to adjust the range based on the number of subjects to process (eg 1-x number of subjects)

# module load fsl/6.0.4

# Run this for fsl 5.0.6
export FSLDIR="/vol/software/fsl"
export PATH="$FSLDIR/bin:$PATH"
export FSLOUTPUTTYPE=NIFTI_GZ
source "$FSLDIR/etc/fslconf/fsl.sh"

# Obtain the corresponding subject
SUBJECTS_LIST="./subjects.txt"
SUBJECT=$(sed -n "${SLURM_ARRAY_TASK_ID}p" $SUBJECTS_LIST | tr -d '\n')

if [ -z "$SUBJECT" ]; then
    echo "Error: No subject found in $SUBJECTS_LIST for line ${SLURM_ARRAY_TASK_ID}"
    exit 1
fi

# Execute script for the selected subject
printf "Starting at %s\n" "$(date)"
printf "Processing subject: %s\n" "$SUBJECT"
./dti_script.sh "$SUBJECT"
printf "Finished processing subject: %s\n" "$SUBJECT"
printf "Ending at %s\n" "$(date)"