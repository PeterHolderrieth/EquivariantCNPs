epochs=30
it=1500
n_test_US=20
n_test_China=20
n_val=100

for seed in 1 2 3 4 5
do 
	python experiment_era5.py -lr 1e-4 -epochs $epochs -it $it -track True -G CNN -A big -n_val $n_val -l 3. -cov 4 -batch 5 -seed $seed -data big  -n_test_US $n_test_US -n_test_China $n_test_China > results/ConvCNP/ConvCNP_${seed}.txt
done


