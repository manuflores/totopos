import torch 
from ripser import ripser 
import numpy as np 
from .genes.perturb_ripser import compute_topological_scores_perturbation
from .genes.iterative import compute_topological_scores_iterative
from .cells.critical import critical_edge_method
from .topology.neighborhood import neighborhood_subsample
from .utils.ph_utils import min_enclosing_radius_torch, get_lifetimes
from .utils.utils import randomized_pca_torch
import anndata as ad

class Totopos():
    def __init__(self, adata: ad.AnnData, ph: dict = None, n_pcs: int = 20, verbose: bool = False):
        """
        Initialize the totopos class.
        TODO: handle the use of subsampling.

        Parameters
        ----------
        adata (AnnData): Annotated data matrix.
        n_pcs (int, optional): Number of principal components to use. Defaults to 20.
        """
        data = adata.X.A
        pts = torch.Tensor(data)
        pts.requires_grad_(True);
        self.data = pts
        self.n_pcs = n_pcs
        #self.max_distance = max_distance
        self.compute_pca()

        if ph==None:
            self.compute_cohomology(verbose)
        else:
            self.ph = ph

    def compute_cohomology(self, verbose=False,prime_coeff:int=47): 
        if verbose: print("Computing persistent homology...")
        self.ph = ripser(self.pcs.detach().numpy(),do_cocycles=True, coeff=prime_coeff)
        self.cocycles = self.ph["cocycles"]
        self.dgms = self.ph["dgms"]
    
    def compute_pca(self, transform = False):
        """
        Compute PCA on the data using torch.
        """
        self.pcs = randomized_pca_torch(self.data, self.n_pcs)
        if transform:
            return self.pcs
    
    def compute_topological_scores_and_gradients_perturb(self, ix_top_class: int = 1):
        """
        Compute topological ranking scores and gradients based on ablating a persistent cohomology class, 
        by default, the most persistent class. 

        Params
        ------ 
        ix_top_class (int, optional): Index (from the top) of the persistent cohomology class to analyze. 
            Defaults to 1 (the most persistent class).

        Returns
        -------
        Tuple[np.ndarray, torch.Tensor]: 
            - topological_ranking_scores: Feature-wise ranking scores derived from gradient norms.
            - gradients: Raw gradients of the data with respect to the topological loss.
        """
        topological_ranking_scores, gradients = compute_topological_scores_perturbation(self.data, self.pcs, self.ph, ix_top_class)
        return topological_ranking_scores, gradients
    
    def compute_topological_scores_and_gradients_iterative(self, ix_top_class:int=1): 
        "TODO:use topocell ixs to compute iterative scores."
        return None
    
    def get_topogenes_ixs(self, index_top_class:int=1, n_topogenes:int=500, method="perturb"):
        "Return the indices of the topoGenes corresponding to the i-th most persistent class"
        if method=="perturb":
            topological_scores, _ = self.compute_topological_scores_and_gradients_perturb(ix_top_class=index_top_class)
        else: 
            topological_scores, _ = self.compute_topological_scores_and_gradients_iterative(ix_top_class=index_top_class)
        isort_tpgs = np.argsort(topological_scores)[::-1]
        topogenes_ids = isort_tpgs[:n_topogenes]
        return topogenes_ids
    
    def compute_topocells(self, n_loops:int = 1, verbose: bool = False, method:str = "ripser"):
        """
        Runs the Critical edge algorithm (see  `totopos.genes.perturb_ripser`)
        """
        self.homology_data = critical_edge_method(
            self.pcs.detach().numpy(), self.ph, n_loops, verbose, method, compute_topocells=True
        )
    
    def get_topocell_ixs(self): 
        "TODO: return the indices of the topoCells corresponding to the i-th most persistent class"
        return None