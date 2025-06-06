import numpy as np 
from sklearn.metrics import pairwise_distances

def min_enclosing_radius_torch(D):
    return D.max(1).values.min()

def min_enclosing_radius_subset_torch(D, subset_size=1000):
    if D.shape[0]>subset_size:
        randixs=np.random.choice(D.shape[0], size=subset_size,replace=False)
        return D[randixs].max(1).values.min()
    else:
        return D.max(1).values.min()

def get_lifetimes(dgm):
    """Returns lifetimes given a persistence diagram with format (n,2) array of birth-death pairs"""
    return dgm[:, 1]- dgm[:, 0]

def greedy_farthest_point_sampling(X, n_points=1000,ix_start=None): 
    """
    Returns
    -------
    ixs (np.ndarray)
        Indices of the selected points.
    hausdorff_distance (float)
    """
    ixs=np.zeros(n_points,dtype=int)
    ixs[0]=ix_start if ix_start is not None else np.random.randint(0,high=len(X))
    
    # D keeps track of min distance to any selected point so far
    D = pairwise_distances(X, X[ixs[0], np.newaxis]).flatten()

    for i in range(1, n_points):
        ixs[i] = np.argmax(D)  # Select the farthest point from current subset
        d = pairwise_distances(X, X[ixs[i], np.newaxis]).flatten()
        D = np.minimum(D, d)   # Update distances to the closest selected point

    hausdorff_distance = D.max()  # max over all x ∈ X of min_s∈S ||x - s||
    return ixs, hausdorff_distance


def remap_indices(arr, mapping): 
    remap = np.vectorize(mapping.get)
    return remap(arr)


def reindex_ripser_landmark_cocycles(ph, dim=1):
    """
    Remaps the indices of the persistent cohomology output from Ripser in landmark mode.
    """
    cocycles = ph["cocycles"][dim]
    mapping = dict(zip(ph["idx_perm"], np.arange(len(ph["idx_perm"]))))
    new_cocycles = []
    for i, c in enumerate(cocycles):
        l = len(c)
        reindexed_cocyc = remap_indices(c[:, :dim+1], mapping)
        new_cocycles.append(
            np.concatenate((reindexed_cocyc, np.ones((l, 1), dtype=int)), axis=1)
        )
    ph["cocycles"][dim] = new_cocycles
    return ph