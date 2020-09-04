import torch
import argparse
import sys
import datetime
sys.path.append("../../")


import Training
import EquivCNP
import CNP.CNP_Model as CNP_Model
import Tasks.GP_Data.GP_div_free_circle.loader as DataLoader


if torch.cuda.is_available():
    DEVICE = torch.device("cuda:0")  
    print("Running on the GPU")
else:
    DEVICE = torch.device("cpu")
    print("Running on the CPU")

ap = argparse.ArgumentParser()
ap.set_defaults(
    TYPE='EquivCNP',
    N_DATA_PASSES=1,
    BATCH_SIZE=30)

#Arguments for architecture:
ap.add_argument("-file", "--FILE", required=True, type=str)
ap.add_argument("-batch", "--BATCH", required=False,type=int)
ap.add_argument("-p", "--N_DATA_PASSES", required=False,type=int)
ap.add_argument("-type", "--TYPE", required=False,type=str)

#Pass arguments:
ARGS = vars(ap.parse_args())

train_dict=torch.load(ARGS['FILE'],map_location=torch.device('cpu'))

if ARGS['TYPE']=="EquivCNP":
    CNP=EquivCNP.EquivCNP.create_model_from_dict(train_dict['CNP_dict'])
else:
    CNP=CNP_Model.ConditionalNeuralProcess.create_model_from_dict(train_dict['CNP_dict'])

CNP=CNP.to(DEVICE)


MIN_N_CONT=2
MAX_N_CONT=50
FILEPATH="../../Tasks/GP_Data/GP_div_free_circle/"
test_dataset=DataLoader.give_GP_div_free_data_set(MIN_N_CONT,MAX_N_CONT,'test',file_path=FILEPATH)

log_ll=Training.test_CNP(CNP,test_dataset,DEVICE,n_samples=test_dataset.n_obs,batch_size=ARGS['BATCH_SIZE'],n_data_passes=ARGS['N_DATA_PASSES'])
print("Filename: ", ARGS['FILE'])
print("Time: ", datetime.datetime.today())
print("Test log-likelihood: ", log_ll)
print("Number of samples: ", ARGS['N_DATA_PASSES'])