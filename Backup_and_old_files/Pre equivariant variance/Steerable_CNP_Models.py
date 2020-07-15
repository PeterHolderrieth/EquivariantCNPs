#!/usr/bin/env python
# coding: utf-8 


#LIBRARIES:
#Tensors:
import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as utils

#E(2)-steerable CNNs - library:
from e2cnn import gspaces                                          
from e2cnn import nn as G_CNN   

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



#HYPERPARAMETERS:
torch.set_default_dtype(torch.float)
quiver_scale=15



class Steerable_Encoder(nn.Module):
    def __init__(self, x_range,y_range=None,n_x_axis=10,n_y_axis=None,kernel_dict={'kernel_type':"rbf"},l_scale=1.,normalize=True):
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
        self.l_scale=nn.Parameter(torch.tensor(l_scale,dtype=torch.get_default_dtype()),requires_grad=True)
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
        self.grid=My_Tools.Give_2d_Grid(min_x=self.x_range[0],max_x=self.x_range[1],
                               min_y=self.y_range[1],max_y=self.y_range[0],
                               n_x_axis=self.n_x_axis,n_y_axis=self.n_y_axis,flatten=True)
        
        self.normalize=normalize
        
    #This is the function y->(1,y,y^2,y^3,...,y^n) in the ConvCNP paper - for now it just adding a one to every y: y->(1,y):
    #since we assume multiplicity one:
    def Psi(self,Y):
        '''
        Input: Y - torch.tensor - shape (n,2)
        Output: torch.tensor -shape (n,3) - added a column of ones to Y (at the start) Y[i,j<--[1,Y[i,j]]
        '''
        return(torch.cat((torch.ones((Y.size(0),1)),Y),dim=1))
        
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
        Gram=GP.Gram_matrix(self.grid,X,l_scale=self.l_scale,**self.kernel_dict,B=torch.ones((1)))
        
        #Compute feature expansion:
        Expand_Y=self.Psi(Y)
        
        #Compute feature map - get shape (n_x_axis*n_y_axis,3)
        Feature_Map=torch.mm(Gram,Expand_Y)
        #If wanted, normalize the weights for the channel which is not the density channel:
        if self.normalize:
            #Normalize the functional representation:
            Norm_Feature_Map=torch.empty(Feature_Map.size())
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
    def __init__(self,feat_types,kernel_sizes):
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
            layers_list.append(G_CNN.ReLU(feat_types[i+1]))
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
      
# In[4]:
#A class which defines a ConvCNP:
class Steerable_CNP(nn.Module):
    def __init__(self,feature_in, G_act, encoder,decoder,
                 kernel_dict_out={'kernel_type':"rbf"},l_scale=1.,normalize_output=True):
        '''
        Inputs:
            encoder - instance of ConvCNP_Enoder 
            decoder - nn.Module - with input and output size the same as the grid of the encoder 
            kernel_dict_out - gives parameters for kernel smoother of output
            normalize_output  - Boolean - indicates whether kernel smoothing is performed with normalizing
        '''

        super(Steerable_CNP, self).__init__()
        #Initialse the encoder:
        self.encoder=encoder
        #Decoder: For now: A standard CNN whose parameters are arbitrary for now:
        self.decoder=decoder
        #Get the parameters for kernel smoother (after the decoder):
        self.l_scale_out=nn.Parameter(torch.tensor(l_scale,dtype=torch.get_default_dtype()),requires_grad=True)
        self.kernel_dict_out=kernel_dict_out
        if 'l_scale' in kernel_dict_out:
            sys.exit("l scale if variable and not fixed")
        #Save whether output is normalized:
        self.normalize_output=normalize_output
        
        #Save the group and the feature types for the input, the embedding (output type = input type for now):
        self.G_act=G_act
        self.feature_in=feature_in
        self.feature_emb=G_CNN.FieldType(G_act, [G_act.trivial_repr,G_act.irrep(1)])
        self.feature_out=G_CNN.FieldType(G_act, [G_act.irrep(1),G_act.trivial_repr,G_act.trivial_repr])
        
        
    #Define the function taking the output of the decoder and creating
    #predictions on the target set based on kernel smoothing (so it takes predictions on the 
    #grid an makes predictions on the target set out of it):
    def target_smoother(self,X_target,Final_Feature_Map):
        '''
        Input: X_target - torch.tensor- shape (n_target,2)
               Final_Feature_Map- torch.tensor - shape (4,self.encoder.n_y_axis,self.encoder.n_x_axis)
        Output: Predictions on X_target - Means_target - torch.tensor - shape (n_target,2)
                Sqrt(Variances) on X_target - Sigmas_target - torch.tensor - shape (n_target,2)
        '''
        #Split into mean and sd and "make sd positive" with softplus:
        Means_grid=Final_Feature_Map[:2]
        #This non-linearity is not equivariant:
        Sigmas_grid=torch.log(1+torch.exp(Final_Feature_Map[2:]))
        
        #Reshape from (2,n_y_axis,n_x_axis) to (n_x_axis*n_y_axis,2) 
        Means_grid=Means_grid.permute(dims=(2,1,0))
        Means_grid=Means_grid.reshape(self.encoder.n_x_axis*self.encoder.n_y_axis,2)
        Sigmas_grid=Sigmas_grid.permute(dims=(2,1,0))
        Sigmas_grid=Sigmas_grid.reshape(self.encoder.n_x_axis*self.encoder.n_y_axis,2)
        
        #3.Feature Map -> Predictions on Target Set (via Kernel smoothing):
        Means_target=GP.Kernel_Smoother_2d(X_Context=self.encoder.grid,Y_Context=Means_grid,
                                           X_Target=X_target,normalize=self.normalize_output,
                                           l_scale=self.l_scale_out,**self.kernel_dict_out)
        Sigmas_target=GP.Kernel_Smoother_2d(X_Context=self.encoder.grid,Y_Context=Sigmas_grid,
                                          X_Target=X_target,normalize=self.normalize_output,
                                          l_scale=self.l_scale_out,**self.kernel_dict_out)
        return(Means_target, Sigmas_target)
    
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

    def plot_Context_Target(self,X_Context,Y_Context,X_Target,Y_Target=None):
        '''
            Inputs: X_Context, Y_Context, X_Target: torch.tensor - see self.forward
                    Y_Target: torch.tensor - shape (n_context_points,2) - ground truth
            Output: None - plots predictions
        
        '''
        #Get predictions:
        Means,Sigmas=self.forward(X_Context,Y_Context,X_Target)
        #Plot predictions against ground truth:
        My_Tools.Plot_Inference_2d(X_Context,Y_Context,X_Target,Y_Target,Predict=Means.detach(),Cov_Mat=Sigmas.detach()**2)
    
    def loss(self,Y_Target,Predict,Sigmas):
        '''
            Inputs: X_Target,Y_Target: torch.tensor - shape (n,2) - Target set locations and vectors
                    Predict: torch.tensor - shape (n,2) - Predictions of Y_Target at X_Target
            Output: -log_ll: log_ll is the log-likelihood at Y_Target given the parameters Predict as means and Sigma**2 as variances
        '''
        dist_tuple=torch.distributions.normal.Normal(loc=Predict,scale=Sigmas)
        log_ll=dist_tuple.log_prob(Y_Target).mean()
        return(-log_ll)



class Steerable_CNP_Operator(nn.Module):
    def __init__(self,Steerable_CNP,train_data_loader,test_data_loader,Max_n_context_points,n_epochs=10,
                 learning_rate=1e-3,n_prints=None, n_plots=None,weight_decay=0.0,n_iterat_per_epoch=10):
        super(Steerable_CNP_Operator, self).__init__()
        '''
        Input: 
          Steerable_CNP: Steerable_CNP Module (see above)

          data_loader: torch.utils.data.DataLoader
                       every minibatch is a list of length 2 with 
                       1st element: data features - torch.tensor - shape (minibatch_size,n,2)
                       2nd element: data labels   - torch.tensor - shape (minibatch_size,n,2)
          epochs: int -number of epochs for training
          learning_rate: float-learning rate for optimizer
          weight_decay: float- weight_decay for optimizer
          n_prints: int - total number of printed losses during training
          n_plots:  if int: total number of plots during training
                    if None: no plots during training
        '''

        self.Steerable_CNP=Steerable_CNP
        self.n_epochs=n_epochs
        self.learning_rate=learning_rate
        if n_prints is None:
            self.n_prints=n_epochs
        else:
            self.n_prints=n_prints

        self.n_plots=n_plots
        self.weight_decay=weight_decay
        self.Max_n_context_points=Max_n_context_points
        self.test_data_loader=test_data_loader
        self.train_data_loader=train_data_loader
        self.minibatch_size=train_data_loader.batch_size
        self.n_train_points=len(train_data_loader.dataset)
        self.n_grid_points=train_data_loader.dataset[0][0].size(0)
        self.log_ll_memory=None
        self.trained=False
        self.n_iterat_per_epoch=n_iterat_per_epoch
        self.saved_to=None
                
    def train(self,filename=None,plot_loss=True):
        '''
        Input: filename - string - name of file - if given, there the model is saved
        Output:
          self.Steerable_CNP is trained (inplace)
          log_ll_vec: torch.tensor
                      Shape (n_epochs)
                      mean log likelihood over one epoch

        Prints:
          Prints self.n_prints-times the mean loss (per minibatch) of the last epoch
        
        Plots (if n_plots is not None):
          We choose a random function and random context before training and plot the development
          of the predictions (mean of the distributions) over the training
        '''
        #Save the number of iterations the optimizer used per epoch:
        n_iterat_per_epoch=self.n_train_points//self.minibatch_size+self.train_data_loader.drop_last

        #Define the optimizer and add a weight decay term:
        optimizer=torch.optim.Adam(self.Steerable_CNP.parameters(),lr=self.learning_rate,weight_decay=self.weight_decay)

        #Track the mean loss of every epoch:
        loss_vector=torch.zeros(self.n_epochs)
        #Print the loss every "track_every" iteration:
        track_every=self.n_epochs//self.n_prints        
        
        #Show plots or not? 
        show_plots=(self.n_plots is not None)
        
        #If yes: pick a random function from the data loader and choose a random subset
        #of context points by saving their indices:
        if show_plots:
            plot_every=max(self.n_epochs//self.n_plots,1)

            #Get a random function:
            Plot_X,Plot_Y=next(iter(self.train_data_loader))
            #Number of context points is expected number of context points:
            n_context_points=self.Max_n_context_points//2
            
            #Split:
            Plot_x_context,Plot_y_context,Plot_x_target,Plot_y_target=My_Tools.Rand_Target_Context_Splitter(Plot_X[0],
                                                                                   Plot_Y[0],
                                                                                   n_context_points)
        
        for epoch in range(self.n_epochs):
            loss_epoch_mean=0.0
            for i in range(self.n_iterat_per_epoch):
                features, labels=next(iter(self.train_data_loader))
                #Set the loss to zero:
                loss=torch.tensor(0.0)
                #loss_vec=torch.empty(self.minibatch_size) 
                for i in range(self.minibatch_size):
                    #Sample the number of context points uniformly: 
                    n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
                    
                    x_context,y_context,x_target,y_target=My_Tools.Rand_Target_Context_Splitter(features[i],
                                                                                       labels[i],
                                                                                       n_context_points)
                    #The target set includes the context set here:
                    Means,Sigmas=self.Steerable_CNP(x_context,y_context,features[i]) #Otherwise:Means,Sigmas=self.Steerable_CNP(x_context,y_context,x_target)
                    loss+=self.Steerable_CNP.loss(labels[i],Means,Sigmas)            #Otherwise:loss+=self.Steerable_CNP.loss(y_target,Means,Sigmas)
                #Set gradients to zero:
                optimizer.zero_grad()
                #Compute gradients:
                loss.backward()

                #Perform optimization step:
                optimizer.step()
                loss_epoch_mean=loss_epoch_mean+loss.detach().item()/n_iterat_per_epoch
            #Track the loss:
            if (epoch%track_every==0):
                print("Epoch: ",epoch," | Loss: ", loss_epoch_mean)
            
            if show_plots:
                if (epoch%plot_every==0):
                    self.Steerable_CNP.plot_Context_Target(Plot_x_context,Plot_y_context,Plot_x_target,Plot_y_target)
            
            #Save loss and compute gradients:
            loss_vector[epoch]=loss_epoch_mean
        
        self.log_ll_memory=-loss_vector.detach().numpy()
        
        #Set trained to True:
        self.trained=True
        #If a filename is given: save the model and add the date and time to the filename:
        if filename is not None:
            complete_filename="Trained_Models/"+filename+'_'+datetime.datetime.today().strftime('%Y_%m_%d_%H_%M')
            torch.save(self.state_dict(),complete_filename)
            self.saved_to=complete_filename
        #Return the mean log-likelihood:
        return(self.log_ll_memory)
    
    def plot_log_ll_memory(self):
        plt.plot(self.log_ll_memory)
        plt.xlabel("Iteration")
        plt.ylabel("Log-likelihood")
    
    #A function which tests the ConvCNP by plotting the predictions:
    def plot_test(self,x_context,y_context,x_target=None,y_target=None,GP_parameters=None):
            plt.figure(plt.gcf().number+1)
            #plt.title(filename + "Trained model")
            self.Steerable_CNP.plot_Context_Target(x_context,y_context,x_target,y_target)
            if GP_parameters is not None:
                plt.figure(plt.gcf().number+1)
                Means_GP,Cov_Mat_GP,Var_GP=GP.GP_inference(x_context,y_context,x_target, **GP_parameters)
                Cov_Mat_GP=My_Tools.Get_Block_Diagonal(Cov_Mat_GP,size=2)
                My_Tools.Plot_Inference_2d(x_context,y_context,x_target,y_target,Predict=Means_GP,Cov_Mat=Cov_Mat_GP)
    
    def plot_test_random(self,n_samples=4,GP_parameters=None):
        for i in range(n_samples):
            X,Y=next(iter(self.test_data_loader))
            n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
            x_context,y_context,x_target,y_target=My_Tools.Rand_Target_Context_Splitter(X[0],Y[0],n_context_points)
            self.plot_test(x_context,y_context,x_target,y_target,GP_parameters=GP_parameters)
    
    def test_equivariance_encoder(self,n_samples=1,plot=True,inner_circle=True):
        '''
        Input: n_samples - int - number of context, target samples to consider
               plot - Boolean - indicates whether plots are generated for every group transformation
        Output: For every group element, it computes the "group equivariance error" of the encoder, i.e.
                the difference between the embedding of the transformed context set and the transformed 
                embedding of the non-transformed context set.
                returns: loss - float - mean aggregrated loss per sample
        '''
        #Loss summation:
        loss=torch.tensor(0.0)
        for i in range(n_samples):
            #Get random mini batch:
            X,Y=next(iter(self.test_data_loader))
            #Get random number context points:
            n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
            #Get random split in context and target set:
            x_context,y_context,_,_=My_Tools.Rand_Target_Context_Splitter(X[0],Y[0],n_context_points)
            #Get embedding:
            Embedding=self.Steerable_CNP.encoder(x_context,y_context)
            #Get geometric version of embedding:
            geom_Embedding=G_CNN.GeometricTensor(Embedding,self.Steerable_CNP.feature_emb)
            #Go over all (test) group elements:
            for g in self.Steerable_CNP.G_act.testing_elements:
                #Get matrix representation of g:
                M=torch.tensor(self.Steerable_CNP.feature_in.representation(g),dtype=torch.get_default_dtype())
                #Transform the context set:
                trans_x_context=torch.matmul(x_context,M.t())
                trans_y_context=torch.matmul(y_context,M.t())
                #Get embedding of transformed context:
                Embedding_trans=self.Steerable_CNP.encoder(trans_x_context,trans_y_context)
                #Get transformed embedding (of non-transformed context set)
                trans_Embedding=geom_Embedding.transform(g).tensor
                #Get distance/error between the two (in theory, it should be zero)
                loss_it=torch.norm(Embedding_trans-trans_Embedding)
                #If wanted, control difference only on the inner cycle:
                if inner_circle:
                    n=Embedding_trans.size(3)
                    ind=My_Tools.get_outer_circle_indices(n)
                    for i,j in ind:
                        Embedding_trans[0,:,i,j]=0
                        trans_Embedding[0,:,i,j]=0
                #Get distance/error between the two (in theory, it should be zero)
                loss_it=torch.norm(Embedding_trans-trans_Embedding)
                #Plot the embedding if wanted:
                if plot:
                    #Get the title:
                    title="Embedding of transformed context| Group: "+self.Steerable_CNP.G_act.name+ "  |  Element: "+str(g)+" | loss: "+str(loss_it.item())
                    self.Steerable_CNP.encoder.plot_embedding(Embedding_trans,trans_x_context,trans_y_context,title=title)
                    title="Transformed Embedding of orig. context| Group: "+self.Steerable_CNP.G_act.name+ "  |  Element: "+str(g)+" | loss: "+str(loss_it.item())
                    self.Steerable_CNP.encoder.plot_embedding(trans_Embedding,trans_x_context,trans_y_context,title=title)
                #Add to aggregated loss:
                loss=loss+loss_it
        #Divide aggregated loss by the number of samples:
        return(loss/n_samples)
            
    def test_equivariance_decoder(self,n_samples=1,plot=True,inner_circle=True):
        '''
        Input: n_samples - int - number of context, target samples to consider
        Output: For every group element, it computes the "group equivariance error" of the decoder, i.e.
                the difference between the decoder output of the transformed embedding and the transformed 
                decoder output of the non-transformed embedding.
                returns: loss - float - mean aggregrated loss per sample
        '''
        #Hyperparameter for size of plots:
        size_scale=1
        
        #Float to save mean aggregrated loss:
        loss=torch.tensor(0.0)
        for i in range(n_samples):
            #Get random mini batch:
            X,Y=next(iter(self.test_data_loader))
            #Get random number context points:
            n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
            #Get random split in context and target set:
            x_context,y_context,_,_=My_Tools.Rand_Target_Context_Splitter(X[0],Y[0],n_context_points)
            
            #Get embedding and version:
            Emb = self.Steerable_CNP.encoder(x_context,y_context)
            geom_Emb = G_CNN.GeometricTensor(Emb, self.Steerable_CNP.feature_emb)
            
            #Get output from decoder and geometric version:
            Out=self.Steerable_CNP.decoder(Emb)
            geom_Out = G_CNN.GeometricTensor(Out, self.Steerable_CNP.feature_out)
            
            #Get grid of encoder:
            grid=self.Steerable_CNP.encoder.grid
            
            #Go over all group (testing) elements:
            for g in self.Steerable_CNP.G_act.testing_elements:
                
                #Transform embedding:
                geom_Emb_transformed= geom_Emb.transform(g)
                Emb_transformed=geom_Emb_transformed.tensor
                
                #Get output of transformed embedding and geometric version:
                Out_transformed = self.Steerable_CNP.decoder(Emb_transformed)
                
                #Get transformed output:
                transformed_Out= geom_Out.transform(g).tensor
                #Set difference to zero out of the inner circle:
                if inner_circle:
                    n=Out_transformed.size(3)
                    ind=My_Tools.get_outer_circle_indices(n)
                    for i,j in ind:
                        transformed_Out[0,:,i,j]=0
                        Out_transformed[0,:,i,j]=0
                
                #Get the difference:        
                Diff=transformed_Out-Out_transformed
                normalizer=torch.norm(Out_transformed)
                #Get iteration loss and add:
                loss_it=torch.norm(Diff)/normalizer
                loss=loss+loss_it
                #If wanted, plot mean rotations:
                if plot:
                    Means_transformed=Out_transformed.squeeze()[:2].permute(dims=(2,1,0)).reshape(-1,2)
                    fig, ax = plt.subplots(nrows=1,ncols=1,figsize=(size_scale*10,size_scale*5))
                    plt.gca().set_aspect('equal', adjustable='box')
                    ax.quiver(grid[:,0],grid[:,1],Means_transformed[:,0].detach(),Means_transformed[:,1].detach(),scale=quiver_scale)
                    #Get the title:
                    title="Decoder Output | Group: "+self.Steerable_CNP.G_act.name+ "  |  Element: "+str(g)+" | loss: "+str(loss_it.item())
                    ax.set_title(title)
        #Get mean aggregrated loss:
        return(loss/n_samples)
        
    def test_equivariance_target_smoother(self,n_samples=1):
        '''
        Input: n_samples - int - number of context, target samples to consider
        Output: For every group element, it computes the "group equivariance error" of the target smoother, i.e.
                the difference between the target smoothing of the transformed decoder output and the transformed target 
                and the target smoothing of the decoder output and the transformed target 
                returns: loss - float - mean aggregrated loss per sample
                NOTE: THIS FUNCTION ONLY CONTROLS EQUIVARIANCE OF THE MEANS, NOT OF THE VARIANCE (since the prediction of variances is not equivariant)
        '''
        loss_Means=torch.tensor(0.0)
        loss_Sigmas=torch.tensor(0.0)
        for i in range(n_samples):
            #Get random mini batch:
            X,Y=next(iter(self.test_data_loader))
            #Get random number context points:
            n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
            #Get random split in context and target set:
            x_context,y_context,x_target,_=My_Tools.Rand_Target_Context_Splitter(X[0],Y[0],n_context_points)
            #Get embedding:
            Emb = self.Steerable_CNP.encoder(x_context,y_context)
            #Get output of embedding and geometric version:
            Out=self.Steerable_CNP.decoder(Emb)
            geom_Out=G_CNN.GeometricTensor(Out, self.Steerable_CNP.feature_out)
            
            #Get smoothed means on target:
            Means,_=self.Steerable_CNP.target_smoother(x_target,Out.squeeze())
            
            normalizer=torch.norm(Means)
            
            for g in self.Steerable_CNP.G_act.testing_elements:
                #Get representation on the output:
                M=torch.tensor(self.Steerable_CNP.feature_in.representation(g),dtype=torch.get_default_dtype())
                #Transform means, target and output:
                trans_Means=torch.matmul(Means,M.t())
                trans_x_target=torch.matmul(x_target,M.t())
                trans_geom_Out=geom_Out.transform(g)
                
                #Get means on transformed target and Output:
                Means_trans,_=self.Steerable_CNP.target_smoother(trans_x_target,
                                                           trans_geom_Out.tensor.squeeze())
                #Get current loss and add it to the aggregrated loss:
                loss_it=torch.norm(Means_trans-trans_Means)
                loss_Means=loss_Means+loss_it
        #Get mean aggregrated loss:
        return(loss_Means/n_samples,loss_Sigmas/n_samples)
    
    def test_equivariance_model(self,n_samples=1,plot=True):
        '''
        Input: n_samples - int - number of context, target samples to consider
        Output: For every group element, it computes the "group equivariance error" of the model, i.e.
                the difference between the model output of the transformed context and target set and the transformed 
                model output of the non-transformed context and target set.
                returns: loss - float - mean aggregrated loss per sample
        '''
        #Get loss:
        loss=torch.tensor(0.0)
        for i in range(n_samples):
            #Get random mini batch:
            X,Y=next(iter(self.test_data_loader))
            #Get random number context points:
            n_context_points=torch.randint(size=[],low=2,high=self.Max_n_context_points)
            #Get random split in context and target set:
            x_context,y_context,x_target,_=My_Tools.Rand_Target_Context_Splitter(X[0],Y[0],n_context_points)
            #Get means and variances:
            Means,Sigmas=self.Steerable_CNP.forward(x_context,y_context,x_target)
            #Go over all group (testing) elements:
            for g in self.Steerable_CNP.G_act.testing_elements:
                #Get input representation of g and transform context:
                M_in=torch.tensor(self.Steerable_CNP.feature_in.representation(g),dtype=torch.get_default_dtype())
                trans_x_context=torch.matmul(x_context,M_in.t())
                trans_y_context=torch.matmul(y_context,M_in.t())
                #Get output representation of g and transform target (here output representation on means is same as input):
                M_out=torch.tensor(self.Steerable_CNP.feature_in.representation(g),dtype=torch.get_default_dtype())
                trans_x_target=torch.matmul(x_target,M_out.t())
                
                #Get means and variances of transformed context and transformed target:
                Means_trans,_=self.Steerable_CNP.forward(trans_x_context,trans_y_context,trans_x_target)
                #Get transformed  means and variances:
                trans_Means=torch.matmul(Means,M_out.t())
                #Compute the error and add to aggregrated loss:
                it_loss=torch.norm(Means_trans-trans_Means)
                loss=loss+it_loss
                #If wanted plot the inference:
                if plot:
                    title="Group: "+self.Steerable_CNP.G_act.name+ "  |  Element: "+str(g)+"| Loss "+str(it_loss.detach().item())
                    My_Tools.Plot_Inference_2d(trans_x_context,trans_y_context,trans_x_target,
                                           Y_Target=None,Predict=Means_trans.detach(),Cov_Mat=None,title=title)
        #Get mean aggregrated loss:
        return(loss/n_samples)
