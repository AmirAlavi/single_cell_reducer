#!/bin/bash

#SBATCH --job-name=scrna_retrieval_array
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=16Gb
#SBATCH --mail-type FAIL

mapfile -t job_commands < retrieval_commands.list

${job_commands[$SLURM_ARRAY_TASK_ID]}
