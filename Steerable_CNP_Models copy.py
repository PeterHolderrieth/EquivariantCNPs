#!/usr/bin/env python
# coding: utf-8 


#LIBRARIES:
#Tensors:
import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as utils

#E(2)-steerable CNNs - librar"y:
from e2cnn import gspaces    
from e2cnn import nn as G_CNN   
import e2cnn

#Plotting in 2d/3d:
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.patches import Ellipse
from matplotlib.colors import Normalize
import matplotlib.cm as cm

#Tools:
import datetime
import sys
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

#Own files:
import Kernel_and_GP_tools as GP
import My_Tools



#HYPERPARAMETERS:
torch.set_default_dtype(torch.float)
quiver_scale=15



class Steerable_Encoder(nn.Module):
    def __init__(self, x_range,y_range=None,n_x_axis=10,n_y_axis=None,kernel_dict={'kernel_type':"rbf"},
                 l_scale=1.,normalize=True):
        super(Steerable_Encoder, self).__init__()
        '''
        Inputs:
            dim_X: int - dimension of state space
            x_range,y_range: float lists of size 2 - give range of grid points at x-axis/y-axis
            kernel_par: dictionary - parameters for function mat_kernel (kernel function)
                        Required: The matrix B cannot be given in this case
            n_x_axis: int - number of grid points along the x-axis
            n_y_axis: int - number of grid points along the y-axis
            normalize: boolean - indicates whether feature channels is divided by density channel
        '''
        #So far, we only allow for two-dimensional outputs:
        self.dim_Y=2
        self.kernel_type=kernel_dict['kernel_type']
        self.log_l_scale=nn.Parameter(torch.log(torch.tensor(l_scale,dtype=torch.get_default_dtype())),requires_grad=False)
        self.kernel_dict=kernel_dict
        
        if 'B' in kernel_dict or 'l_scale' in kernel_dict:
            sys.exit("So far, we do not allow for a multi-dimensional kernel in the embedding and no l_scale is allowed")
        self.x_range=x_range
        self.n_x_axis=n_x_axis

        #If y_range is None set to the same as x_range:
        if y_range is not None:
            self.y_range=y_range
        else:
            self.y_range=x_range
        #If n_y_axis is None set to the same as n_y_axis:
           
        if n_y_axis is not None:
            self.n_y_axis=n_y_axis
        else:
            self.n_y_axis=n_x_axis
            
        #Create a flattened grid: Periodic grid is y-axis - repetitive grid is x-axis
        #i.e. self.grid[k*n_y_axis+j] corresponds to unflattended Grid[k][j]
        #NOTE: The counter will go BACKWARDS IN THE Y-AXIS - this is because
        #if we look at a (m,n)-matrix as a matrix with pixels, then the higher 
        #the row index, the lower its y-axis value, i.e. the y-axis is counted 
        #mirrored.
        self.grid=nn.Parameter(My_Tools.Give_2d_Grid(min_x=self.x_range[0],max_x=self.x_range[1],
                               min_y=self.y_range[1],max_y=self.y_range[0],
                               n_x_axis=self.n_x_axis,n_y_axis=self.n_y_axis,flatten=True),requires_grad=False)
        
        self.normalize=normalize
        
    #This is the function y->(1,y,y^2,y^3,...,y^n) in the ConvCNP paper - for now it just adding a one to every y: y->(1,y):
    #since we assume multiplicity one:
    def Psi(self,Y):
        '''
        Input: Y - torch.tensor - shape (n,2)
        Output: torch.tensor -shape (n,3) - added a column of ones to Y (at the start) Y[i,j<--[1,Y[i,j]]
        '''
        return(torch.cat((torch.ones((Y.size(0),1),device=Y.device),Y),dim=1))
        
    def forward(self,X,Y):
        '''
        Inputs:
            X: torch.tensor - shape (n,2)
            Y: torch.tensor - shape (n,self.dim_Y)
            x_range: List of floats - size 2 - x_range[0] gives minimum x-grid, x_range[1] - gives maximum x-grid
            y_range: List of floats - size 2 - y_range[0] gives minimum y-grid, y_range[1] - gives maximum y-grid
                     if None: x_range is taken
            n_grid_points: int - number of grid points per dimension 
        Outputs:
            torch.tensor - shape (self.dim_Y+1,n_y_axis,n_axis) 
        '''
        #Compute for every grid-point x' the value k(x',x_i) for all x_i in the data 
        #-->shape (n_x_axis*n_y_axis,n)
        if self.grid.device!=X.device:
            print("Grid and X are on different devices.")
            self.grid=self.grid.to(X.device)
        
        l_scale=torch.exp(torch.clamp(self.log_l_scale,max=5.,min=-5.))
        Gram=GP.Gram_matrix(self.grid,X,l_scale=l_scale,**self.kernel_dict,B=torch.ones((1),device=X.device))
        
        #Compute feature expansion:
        Expand_Y=self.Psi(Y)
        
        #Compute feature map - get shape (n_x_axis*n_y_axis,3)
        Feature_Map=torch.mm(Gram,Expand_Y)
        #If wanted, normalize the weights for the channel which is not the density channel:
        if self.normalize:
            #Normalize the functional representation:
            Norm_Feature_Map=torch.empty(Feature_Map.size(),device=Feature_Map.device)
            Norm_Feature_Map[:,1:]=Feature_Map[:,1:]/Feature_Map[:,0].unsqueeze(1)
            Norm_Feature_Map[:,0]=Feature_Map[:,0]
            #Reshape the Feature Map to the form (1,n_channels=3,n_y_axis,n_x_axis) (because this is the form required for a CNN):
            return(Norm_Feature_Map.reshape(self.n_x_axis,self.n_y_axis,Expand_Y.size(1)).permute(dims=(2,1,0)).unsqueeze(0))        
        #Reshape the Feature Map to the form (1,n_channels=3,n_y_axis,n_x_axis) (because this is the form required for a CNN):
        else:   
            return(Feature_Map.reshape(self.n_x_axis,self.n_y_axis,Expand_Y.size(1)).permute(dims=(2,1,0)).unsqueeze(0))
    
    def plot_embedding(self,Embedding,X_context=None,Y_context=None,title=""):
        '''
        Input: 
               Embedding - torch.tensor - shape (1,n_grid_points,3) - Embedding obtained from self.forward (usually  from X_context,Y_context)
                                                                      where (n_grid_poinst,0) is the density channel
                                                                      and (n_grid_points,1:2) is the smoothing channel
               X_context,Y_context - torch.tensor - shape (n,2) - context locations and vectors
               title - string 
        Plots locations X_context with vectors Y_context attached to it
        and on top plots the kernel smoothed version (i.e. channel 2,3 of the embedding)
        Moreover, it plots a density plot (channel 1 of the embedding)
        '''
        #Hyperparameter for function for plotting in notebook:
        size_scale=2

        #Create figures, set title and adjust space:
        fig, ax = plt.subplots(nrows=1,ncols=2,figsize=(size_scale*10,size_scale*5))
        plt.gca().set_aspect('equal', adjustable='box')
        fig.suptitle(title)
        fig.subplots_adjust(wspace=0.2)
        #Set titles for subplots:
        ax[0].set_title("Smoothing channel")
        ax[1].set_title("Density channel")
        
        if X_context is not None and Y_context is not None:
            #Plot context set in black:
            ax[0].scatter(X_context[:,0],X_context[:,1],color='black')
            ax[0].quiver(X_context[:,0],X_context[:,1],Y_context[:,0],Y_context[:,1],
              color='black',pivot='mid',label='Context set',scale=quiver_scale)

        #Get embedding of the form (3,self.n_y_axis,self.n_x_axis)
        Embedding=Embedding.squeeze()
        #Get density channel --> shape (self.n_y_axis,self.n_x_axis)
        Density=Embedding[0]
        #Get Smoothed channel -->shape (self.n_x_axis*self.n_y_axis,2)
        Smoothed=Embedding[1:].permute(dims=(2,1,0)).reshape(-1,2)
        #Plot the kernel smoothing:
        ax[0].quiver(self.grid[:,0],self.grid[:,1],Smoothed[:,0],Smoothed[:,1],color='red',pivot='mid',label='Embedding',scale=quiver_scale)
        #Get Y values of grid:
        Y=self.grid[:self.n_y_axis,1]
        #Get X values of grid:
        X=self.grid.view(self.n_x_axis,self.n_y_axis,2).permute(dims=(1,0,2))[0,:self.n_x_axis,0]  
        #Set X and Y range to the same as for the first plot:
        ax[1].set_xlim(ax[0].get_xlim())
        ax[1].set_ylim(ax[0].get_ylim())
        #Plot a contour plot of the density channel:
        ax[1].set_title("Density channel")
        ax[1].contour(X,Y, Density, levels=14, linewidths=0.5, colors='k')
        #Add legend to first plot:
        leg = ax[0].legend()

class Steerable_Decoder(nn.Module):
    def __init__(self,feat_types,kernel_sizes,non_linearity="ReLU"):
        super(Steerable_Decoder, self).__init__()
        #Save kernel sizes:
        self.kernel_sizes=kernel_sizes
        self.feature_in=feat_types[0]
        
        #Create a list of layers based on the kernel sizes. Compute the padding such
        #that the height h and width w of a tensor with shape (batch_size,n_channels,h,w) does not change
        #while being passed through the decoder:
        self.n_layers=len(feat_types)
        layers_list=[G_CNN.R2Conv(feat_types[0],feat_types[1],kernel_size=kernel_sizes[0],padding=(kernel_sizes[0]-1)//2)]
        for i in range(self.n_layers-2):
            if non_linearity=="ReLU":
                layers_list.append(G_CNN.ReLU(feat_types[i+1]))
            else:
                layers_list.append(G_CNN.NormNonLinearity(feat_types[i+1]))
            layers_list.append(G_CNN.R2Conv(feat_types[i+1],feat_types[i+2],kernel_size=kernel_sizes[i],padding=(kernel_sizes[i]-1)//2))
        
        #Create a steerable decoder out of the layers list:
        
        self.decoder=G_CNN.SequentialModule(*layers_list)
        #Control that all kernel sizes are odd (otherwise output shape is not correct):
        if any([j%2-1 for j in kernel_sizes]):
            sys.exit("All kernels need to have odd sizes")
        
    def forward(self,X):
        '''
        X - torch.tensor - shape (batch_size,n_channels,m,n)
        '''
        #Convert X into a geometric tensor:
        X=G_CNN.GeometricTensor(X, self.feature_in)
        #Send it through the decoder:
        Out=self.decoder(X)
        #Return the resulting tensor:
        return(Out.tensor)
      
#A class which defines a ConvCNP:
class Steerable_CNP(nn.Module):
    def __init__(self,G_act,feature_in, encoder,decoder, dim_cov_est,
                         kernel_dict_out={'kernel_type':"rbf"},l_scale=1.,normalize_output=True):
        '''
        Inputs:
            G_act - gspaces.r2.general_r2.GeneralOnR2 - the underlying group under whose equivariance the models is built/tested
            feature_in  - G_CNN.FieldType - feature type of input (on the data)
            feature_out -G_CNN.FieldType - feature type of output of the decoder
            encoder - instance of ConvCNP_Enoder 
            decoder - nn.Module - takes input (batch_size,3,height,width) and gives (batch_size,5,height,width) or (batch_size,3,height,width) 
                                  as output
            kernel_dict_out - gives parameters for kernel smoother of output
            l_scale - float - gives initialisation for learnable length parameter
            normalize_output  - Boolean - indicates whether kernel smoothing is performed with normalizing
        '''

        super(Steerable_CNP, self).__init__()
        #Initialse the encoder:
        self.encoder=encoder
        #Decoder: For now: A standard CNN whose parameters are arbitrary for now:
        self.decoder=decoder
        #Get the parameters for kernel smoother for the target set:
        self.log_l_scale_out=nn.Parameter(torch.log(torch.tensor(l_scale,dtype=torch.get_default_dtype())),requires_grad=True)
        #Get the other kernel parameters for the kernel smoother for the target set (others are fixed):
        self.kernel_dict_out=kernel_dict_out
        #Save whether output is normalized (i.e. kernel smoothing is performed with normalizing):
        self.normalize_output=normalize_output
        #Save the dimension of the covariance estimator of the last layer:
        self.dim_cov_est=dim_cov_est



        
        #Control that there is no variable l_scale in the the kernel dictionary:
        if 'l_scale' in kernel_dict_out:
            sys.exit("l scale is variable and not fixed")
        
        #Save the group and the feature types for the input, the embedding (output type = input type for now):
        self.G_act=G_act
        self.feature_in=feature_in
        self.feature_emb=G_CNN.FieldType(G_act, [G_act.trivial_repr,feature_in.representation])
        
        #--------------------CONTROL WHETHER ALL PARAMETERS ARE CORRECT--------------------------
        #Save the dimension of the covariance estimator of the last layer:
        self.dim_cov_est=dim_cov_est
        if (self.dim_cov_est!=1) and (self.dim_cov_est!=3):
            sys.exit("The number of output channels of the decoder must be either 3 or 5")
        
        #Define the feature type on output which depending dim_cov_est either 3 or 5-dimensional
        if self.dim_cov_est==1:
            self.feature_out=G_CNN.FieldType(G_act, [feature_in.representation,G_act.trivial_repr])
        else:
            self.feature_out=G_CNN.FieldType(G_act, [feature_in.representation,My_Tools.get_pre_psd_rep(G_act)[0]])
            
    #Define the function taking the output of the decoder and creating
    #predictions on the target set based on kernel smoothing (so it takes predictions on the 
    #grid an makes predictions on the target set out of it):
    def target_smoother(self,X_target,Final_Feature_Map):
        '''
        Input: X_target - torch.tensor- shape (n_target,2)
               Final_Feature_Map- torch.tensor - shape (4,self.encoder.n_y_axis,self.encoder.n_x_axis)
        Output: Predictions on X_target - Means_target - torch.tensor - shape (n_target,2)
                Covariances on X_target - Covs_target - torch.tensor - shape (n_target,2,2)
        '''
        #Split into mean and parameters for covariance (pre-activation) and send it through the activation function:
        Means_grid=Final_Feature_Map[:2]
        Pre_Activ_Covs_grid=Final_Feature_Map[2:]
        
        #Reshape from (2,n_y_axis,n_x_axis) to (n_x_axis*n_y_axis,2) 
        Means_grid=Means_grid.permute(dims=(2,1,0))
        Means_grid=Means_grid.reshape(self.encoder.n_x_axis*self.encoder.n_y_axis,2)
        #Reshape from (2,n_y_axis,n_x_axis) to (n_x_axis*n_y_axis,self.dim_cov_est): 
        Pre_Activ_Covs_grid=Pre_Activ_Covs_grid.permute(dims=(2,1,0))
        Pre_Activ_Covs_grid=Pre_Activ_Covs_grid.reshape(self.encoder.n_x_axis*self.encoder.n_y_axis,
                                                        self.dim_cov_est)
        #Apply activation function on (co)variances -->shape (n_x_axis*n_y_axis,2,2):
        if self.dim_cov_est==1:
            #Apply softplus (add noise such that variance does not become (close to) zero):
            Covs_grid=1e-4+F.softplus(Pre_Activ_Covs_grid).repeat(1,2)
            Covs_grid=Covs_grid.diag_embed()
        else:
            Covs_grid=My_Tools.stable_cov_activation_function(Pre_Activ_Covs_grid)
      
        #Create flattened version for target smoother:
        Covs_grid_flat=Covs_grid.view(self.encoder.n_x_axis*self.encoder.n_y_axis,-1)
        
        #Set the lenght scale:
        l_scale=torch.exp(torch.clamp(self.log_l_scale_out,max=5.,min=-5.))

        #3.Means on Target Set (via Kernel smoothing) --> shape (n_x_axis*n_y_axis,2):
        Means_target=GP.Kernel_Smoother_2d(X_Context=self.encoder.grid,Y_Context=Means_grid,
                                           X_Target=X_target,normalize=self.normalize_output,
                                           l_scale=l_scale,**self.kernel_dict_out)
        #3.Covariances on Target Set (via Kernel smoothing) --> shape (n_x_axis*n_y_axis,4):
        Covs_target_flat=GP.Kernel_Smoother_2d(X_Context=self.encoder.grid,Y_Context=Covs_grid_flat,
                                          X_Target=X_target,normalize=self.normalize_output,
                                          l_scale=l_scale,**self.kernel_dict_out)
        #Reshape covariance matrices to proper matrices --> shape (n_target,2,2):
        Covs_target=Covs_target_flat.view(X_target.size(0),2,2)
        return(Means_target, Covs_target)
 
    #Define the forward pass of ConvCNP: 
    def forward(self,X_context,Y_context,X_target):
        '''
        Inputs:
            X_context: torch.tensor - shape (n_context,2)
            Y_context: torch.tensor - shape (n_context,2)
            X_target: torch.tensor - shape (n_target,2)
        Outputs:
            Means_target: torch.tensor - shape (n_target,2) - mean of predictions
            Sigmas_target: torch.tensor -shape (n_target,2) - scale of predictions
        '''
        #1.Context Set -> Embedding (via Encoder) --> shape (3,self.encoder.n_y_axis,self.encoder.n_x_axis):
        Embedding=self.encoder(X_context,Y_context)
        #2.Embedding ->Feature Map (via CNN) --> shape (4,self.encoder.n_y_axis,self.encoder.n_x_axis):
        Final_Feature_Map=self.decoder(Embedding).squeeze()
        #Smooth the output:
        return(self.target_smoother(X_target,Final_Feature_Map))

    def plot_Context_Target(self,X_Context,Y_Context,X_Target,Y_Target=None,title=""):
        '''
            Inputs: X_Context, Y_Context, X_Target: torch.tensor - see self.forward
                    Y_Target: torch.tensor - shape (n_context_points,2) - ground truth
            Output: None - plots predictions
        
        '''
        #Get predictions:
        Means,Covs=self.forward(X_Context,Y_Context,X_Target)
        #Plot predictions against ground truth:
        My_Tools.Plot_Inference_2d(X_Context,Y_Context,X_Target,Y_Target,Predict=Means.detach(),Cov_Mat=Covs.detach(),title=title)
    
    def loss(self,Y_Target,Predict,Covs,shape_reg=None):
        '''
            Inputs: X_Target,Y_Target: torch.tensor - shape (n,2) - Target set locations and vectors
                    Predict: torch.tensor - shape (n,2) - Predictions of Y_Target at X_Target
                    Covs: torch.tensor - shape (n,2,2) - covariance matrices of Y_Target at X_Target
            Output: -log_ll: log_ll is the log-likelihood at Y_Target given the parameters Predict  and Covs
        '''
        log_ll_vec=My_Tools.batch_multivar_log_ll(Means=Predict,Covs=Covs,Data=Y_Target)
        log_ll=log_ll_vec.mean()
        if shape_reg is not None:
            return(-log_ll+shape_reg*My_Tools.shape_regularizer(Y_1=Y_Target,Y_2=Predict))
        else:
            return(-log_ll)

