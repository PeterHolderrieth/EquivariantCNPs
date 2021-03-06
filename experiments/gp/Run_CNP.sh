#Get the number of iterations, epochs and tests needed!
epochs=30
it=10000
n_val=100
track=True
n_test=15


for seed in 1 2 3 4 5 
do
    python experiment_gp.py -lr 1e-4 -epochs $epochs -A thin -it $it -track $track -G CNP -n_test $n_test -n_val $n_val -l 3. -batch 60  -seed $seed -data rbf > results/CNP/CNP_rbf_${seed}.txt
done 

for seed in 1 2 3 4 5 
do
    python experiment_gp.py -lr 1e-4 -epochs $epochs -A thin -it $it -track $track -G CNP -n_test $n_test -n_val $n_val -l 3. -batch 60  -seed $seed -data div_free > results/CNP/CNP_div_free_${seed}.txt
done 

for seed in 1 2 3 4 5 
do
    python experiment_gp.py -lr 1e-4 -epochs $epochs -A thin -it $it -track $track -G CNP -n_test $n_test -n_val $n_val -l 3. -batch 60  -seed $seed -data curl_free > results/CNP/CNP_curl_free_${seed}.txt
done 

