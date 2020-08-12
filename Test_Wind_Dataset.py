#LIBRARIES:
#Tensors:
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as utils


#E(2)-steerable CNNs - librar"y:
from e2cnn import gspaces                                          
from e2cnn import nn as G_CNN   
#import e2cnn

#Plotting in 2d/3d:
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.patches import Ellipse
from matplotlib.colors import Normalize
import matplotlib.cm as cm

#Tools:
import datetime
import sys

#Own files:
import Kernel_and_GP_tools as GP
import My_Tools
import Steerable_CNP_Models as My_Models
import Training
import Tasks.Dataset as Dataset
import Tasks.GP_div_free_small.loader as GP_loader

#HYPERPARAMETERS:
torch.set_default_dtype(torch.float)

PATH_TO_FOLDER="Tasks/ERA5/ERA5_US/Data/Single_Files_Wind/"
GRID_FILE="Grid_df.pickle"
FILE_WITHOUT_TIME="_ERA5_US_Wind.pickle"

Min_n_cont=20
Max_n_cont=100
n_total=None
min_year=1980
max_year=2018
months=[1,2,12]
BATCH_SIZE=2
N_ITERAT=1

Wind_Dataset=Dataset.ERA5WindDataset(PATH_TO_FOLDER,GRID_FILE,FILE_WITHOUT_TIME,Min_n_cont,Max_n_cont,
n_total,min_year,max_year,months)
start=datetime.datetime.today()
for i in range(N_ITERAT):
    X_c,Y_c,X_t,Y_t=Wind_Dataset.get_rand_batch(batch_size=60)

elapsed_time=datetime.datetime.today()-start
print("Elapsed time for Wind Dataset: ", elapsed_time)





GP_DATASET=GP_loader.give_GP_div_free_data_set(Min_n_cont=5,Max_n_cont=50,n_total=None,data_set='train')
DATA_IDENTIFIER="GP_data_small"
GP_PARAMETERS={'l_scale':0.5,
'sigma_var': 2., 
'kernel_type':"div_free",
'obs_noise':1e-4}
print(GP_DATASET.X_data.shape)
start=datetime.datetime.today()
for i in range(N_ITERAT):
    X_c,Y_c,X_t,Y_t=GP_DATASET.get_rand_batch(batch_size=60)

elapsed_time=datetime.datetime.today()-start
print("Elapsed time for GP dataset: ", elapsed_time)