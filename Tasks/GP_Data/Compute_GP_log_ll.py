import torch
import torch.utils.data as utils
import torch.nn.functional as F
import numpy as np

import sys
sys.path.append('../..')

import My_Tools
import Kernel_and_GP_tools as GP
import Tasks.GP_Data.GP_div_free_circle.loader as GP_load_data

if torch.cuda.is_available():
    DEVICE = torch.device("cuda:0")  
    print("Running on the GPU")
else:
    DEVICE = torch.device("cpu")
    print("Running on the CPU")


def Compute_GP_log_ll(GP_parameters,val_dataset,device,n_samples=400,batch_size=1,n_data_passes=1):
        with torch.no_grad():
            n_obs=val_dataset.n_obs
            n_samples_max=min(n_samples,n_obs)
            n_iterat=max(n_samples_max//batch_size,1)
            log_ll=torch.tensor(0.0, device=device)

            for j in range(n_data_passes):
                ind_list=torch.randperm(n_obs)[:n_samples_max]
                batch_ind_list=[ind_list[j*batch_size:(j+1)*batch_size] for j in range(n_iterat)]

                for it in range(n_iterat):
                    #Get random minibatch:
                    x_context,y_context,x_target,y_target=val_dataset.get_batch(inds=batch_ind_list[it],cont_in_target=False)
                    
                    #Load data to device:
                    x_context=x_context.to(device)
                    y_context=y_context.to(device)
                    x_target=x_target.to(device)
                    y_target=y_target.to(device)

                    #The target set includes the context set here:
                    Means_list=[]
                    Sigmas_list=[]
                    for b in range(batch_size):
                        Means,Sigmas,_=GP.GP_inference(x_context[b],y_context[b],x_target[b],**GP_parameters)
                        Means_list.append(Means)
                        Sigmas=My_Tools.Get_Block_Diagonal(Sigmas,size=2)
                        Sigmas_list.append(Sigmas)
                    Means=torch.stack(Means_list,dim=0)
                    Sigmas=torch.stack(Sigmas_list,dim=0)
                    log_ll_it=My_Tools.batch_multivar_log_ll(Means,Sigmas,y_target)
                    log_ll+=log_ll_it.mean()/n_iterat
                                        
        return(log_ll.item()/n_data_passes)

DATASET=GP_load_data.give_GP_div_free_data_set(2,50,data_set='train',file_path='GP_div_free_circle/')
N_SAMPLES=100
BATCH_SIZE=10
N_DATA_PASSES=1
GP_PARAMETERS={'l_scale':5.,
'sigma_var': 10., 
'kernel_type':"div_free",
'obs_noise':0.02}

log_ll=Compute_GP_log_ll(GP_PARAMETERS,DATASET,DEVICE,N_SAMPLES,BATCH_SIZE,N_DATA_PASSES)

print("Mean log-likelihood on validation data set:")
print(log_ll)