### Diffusion Weighted Imaging (DWI) Preprocessing
- **Purpose:** Runs preprocessing of DWI data using FSL’s topup, eddy, and dtifit, including file retrieval, distortion correction, motion correction, and tensor fitting.
- **Scripts:**     
    - `dwi_script.sh`: Processes a single subject’s DWI data.
    - `batch_dwi_script.sh`: SLURM job script to run `dwi_script.sh` in parallel for multiple subjects.