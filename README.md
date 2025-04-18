# totopos
Trajectory outlining for topological loops in single cell data


### Installation 

1. Create conda environment

```
conda env create -f environment.yml 
```

2. Activate environment

```
conda activate totopos
```

3. Install `pytorch` depending on your setup, see [here](https://pytorch.org/get-started/locally/).


4. Install [`oineus`](https://github.com/anigmetov/oineus/) by following the instructions in their Github.
Afterwards, run the following command in the repo's root directory: 

```
python setup.py install
```

5. Install `totopos` module

```
pip install -e . #run in the repo's root directory
```

5. Optional : install [`dionysus`](https://mrzv.org/software/dionysus2/#get-build-install)
