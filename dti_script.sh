#!/bin/bash

# Constants MB-dMRI & SB-dMRI
# EPI_FACTOR=140
# ECHO_SPACING=0.69
# DWELL_TIME=(140*0.69/1000)=0.0966

export FSLSUB_PARALLEL=4

SUBJECT=$1
FOLDER_OUT='/psiquiatria/home/oriol/Desktop/DWI_preproc'
SES='ses-02' # edit session number

# Variables
FOLDER_IN=${FOLDER_OUT}/${SUBJECT}_${SES}/dwi
FOLDER_IN_REF=${FOLDER_OUT}/${SUBJECT}_${SES}/fmap
FOLDER_IN_T1=${FOLDER_OUT}/${SUBJECT}_${SES}/anat
DTI_REF_AP_FILE=${FOLDER_IN_REF}/${SUBJECT}_${SES}_acq-dwisefm_dir-ap_run-01_epi.nii.gz
DTI_REF_PA_FILE=${FOLDER_IN_REF}/${SUBJECT}_${SES}_acq-dwisefm_dir-pa_run-01_epi.nii.gz
DTI_AP_FILE=${FOLDER_IN}/${SUBJECT}_${SES}_dir-ap_run-01_dwi.nii.gz 		
DTI_PA_FILE=${FOLDER_IN}/${SUBJECT}_${SES}_dir-pa_run-01_dwi.nii.gz
BVAL_AP=${FOLDER_IN}/${SUBJECT}_${SES}_dir-ap_run-01_dwi.bval		
BVAL_PA=${FOLDER_IN}/${SUBJECT}_${SES}_dir-pa_run-01_dwi.bval
BVEC_AP=${FOLDER_IN}/${SUBJECT}_${SES}_dir-ap_run-01_dwi.bvec			
BVEC_PA=${FOLDER_IN}/${SUBJECT}_${SES}_dir-pa_run-01_dwi.bvec		
T1=${FOLDER_IN_T1}/${SUBJECT}_${SES}_run-01_T1w.nii.gz

SBREF_APPA_FILE='sbref_APPA'
DTI_APPA_FILE='alldirections_APPA'	

# Creates folder
FOLDER=$FOLDER_OUT/${SUBJECT}_${SES}
mkdir $FOLDER -p


if [ ! -d $FOLDER_IN ]; then
    mkdir $FOLDER_IN -p
fi
if [ ! -d $FOLDER_IN_REF ]; then
    mkdir $FOLDER_IN_REF -p
fi
if [ ! -d $FOLDER_IN_T1 ]; then
    mkdir $FOLDER_IN_T1 -p
fi
if [ ! -f $DTI_REF_AP_FILE ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/fmap/${SUBJECT}_${SES}_acq-dwisefm_dir-ap_run-01_epi.nii.gz $DTI_REF_AP_FILE
fi
if [ ! -f $DTI_REF_PA_FILE ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/fmap/${SUBJECT}_${SES}_acq-dwisefm_dir-pa_run-01_epi.nii.gz $DTI_REF_PA_FILE
fi
if [ ! -f $DTI_AP_FILE ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-ap_run-01_dwi.nii.gz $DTI_AP_FILE
fi
if [ ! -f $DTI_PA_FILE ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-pa_run-01_dwi.nii.gz $DTI_PA_FILE
fi
if [ ! -f $BVAL_AP ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-ap_run-01_dwi.bval $BVAL_AP
fi
if [ ! -f $BVAL_PA ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-pa_run-01_dwi.bval $BVAL_PA
fi
if [ ! -f $BVEC_AP ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-ap_run-01_dwi.bvec $BVEC_AP
fi
if [ ! -f $BVEC_PA ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/dwi/${SUBJECT}_${SES}_dir-pa_run-01_dwi.bvec $BVEC_PA
fi
if [ ! -f $T1 ]; then
    scp oriol@161.116.166.234:/pool/guttmann/institut/UB/Superagers/MRI/BIDS/${SUBJECT}/${SES}/anat/${SUBJECT}_${SES}_run-01_T1w.nii.gz $T1
fi

# For topup and eddycurrent fsl algorithms: https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/eddy

echo 'Preparing files for topup'
echo "fslmerge -t ${FOLDER}/$SBREF_APPA_FILE $DTI_REF_AP_FILE $DTI_REF_PA_FILE"

# Merge SBREF AP-PA
fslmerge -t ${FOLDER}/$SBREF_APPA_FILE $DTI_REF_AP_FILE $DTI_REF_PA_FILE

# Create .txt file with acquisition parameters (AP and PA)
# 0.001*(echo space (ms)*(EPI factor-1) --> 0.001 * 0.69 * (140-1)
printf "0 -1 0 0.09591\n0 1 0 0.09591" > ${FOLDER}/acqparams.txt

echo 'Running topup'
# Run top-up
topup --imain=${FOLDER}/$SBREF_APPA_FILE --datain=${FOLDER}/acqparams.txt --config=b02b0.cnf --out=${FOLDER}/topup_results --iout=${FOLDER}/hifi_b0

echo 'Preparing files for eddy'
# Creating masks on the unwarped (distortion corrected space)-> t_mean of AP and PA corrected singleband b0 volumes
fslmaths ${FOLDER}/hifi_b0 -Tmean ${FOLDER}/mean_hifi_b0
bet ${FOLDER}/mean_hifi_b0 ${FOLDER}/mean_hifi_b0_brain -f 0.7 -m

# Concatenates DTI (multiband) AP-PA
fslmerge -t ${FOLDER}/$DTI_APPA_FILE ${DTI_AP_FILE} ${DTI_PA_FILE}

# Concatenation order 1->AP and 2->PA
indx=""
for ((i=1; i<=100; i+=1)); do indx="$indx 1"; done
for ((i=1; i<=100; i+=1)); do indx="$indx 2"; done
echo $indx > ${FOLDER}/index.txt

# Concatenates bvals and bvecs AP-PA overwriting the concatenated file to avoid appending more than once
paste -d ' ' "${BVEC_AP}" "${BVEC_PA}" > "${FOLDER}/BVEC_concat_APPA.bvec"
paste -d ' ' "${BVAL_AP}" "${BVAL_PA}" > "${FOLDER}/BVAL_concat_APPA.bval"

# Run eddy
echo 'Starting eddy correction'
eddy_openmp --imain=${FOLDER}/$DTI_APPA_FILE --mask=${FOLDER}/mean_hifi_b0_brain_mask --acqp=${FOLDER}/acqparams.txt --index=${FOLDER}/index.txt --bvecs=${FOLDER}/BVEC_concat_APPA.bvec --bvals=${FOLDER}/BVAL_concat_APPA.bval --topup=${FOLDER}/topup_results --repol --out=${FOLDER}/eddy_corrected_data
#--repol -> instructs eddy to remove any slices deemed as outliers and replace them with predictions made by the Gaussian Process

# Makes brain mask from T1w
flirt -ref ${FOLDER}/mean_hifi_b0 -in $T1 -omat ${FOLDER}/T1w2SBdMRI
bet $T1 ${FOLDER}/T1w_brain -f 0.15 -m -R -B
flirt -in ${FOLDER}/T1w_brain_mask -ref ${FOLDER}/mean_hifi_b0 -applyxfm -init ${FOLDER}/T1w2SBdMRI -out ${FOLDER}/T1w_brain_mask_dMRIres

# T1_brain_mask expansion
fslmaths ${FOLDER}/T1w_brain_mask_dMRIres -dilD -kernel 3D ${FOLDER}/T1w_brain_mask_dMRIres_exp

# Run dtifit
echo 'DTI fit'
dtifit -k ${FOLDER}/eddy_corrected_data -o ${FOLDER}/dti_fit_data -m ${FOLDER}/T1w_brain_mask_dMRIres_exp -r ${FOLDER}/eddy_corrected_data.eddy_rotated_bvecs -b ${FOLDER}/BVAL_concat_APPA.bval

if [ -f ${FOLDER}/T1w_brain_mask_dMRIres_exp.nii.gz ]; then

    rm -r $FOLDER_IN
    rm -r $FOLDER_IN_REF
    rm -r $FOLDER_IN_T1

fi