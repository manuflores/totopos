import torch
import time 
from ripser import ripser 
import oineus as oin
import numpy as np 
from typing import Tuple
from ..utils.ph_utils import min_enclosing_radius_torch, get_lifetimes
from ..utils.utils import randomized_pca_torch, differentiable_distance_matrix_torch

def topological_gene_scores_via_simplification(
    data:np.ndarray, n_threads:int=2, hom_dim:int=1, n_topo_feats:int=1, max_distance:float=None,
    verbose:bool = False, pca:bool = False, n_pcs:int=30, target_strategy:str="birth-birth"
    )->np.ndarray:
    """
    Returns gene scores via topological simplification, i.e. reducing the topological noise from a persistent diagram.
    """
    assert target_strategy in ["birth-birth", "death-death", "midpoint"]

    if target_strategy=="birth-birth": # decrease death time
        strategy=oin.DenoiseStrategy.BirthBirth
    elif target_strategy=="death-death": # increase birth time
        strategy = oin.DenoiseStrategy.DeathDeath
    else: 
        strategy=oin.DenoiseStrategy.Midway

    pts = torch.Tensor(data)
    pts.requires_grad_(True);

    if pca:
        if verbose:print("Calculating SVD...") 
        pcs = randomized_pca_torch(pts, n_pcs)
        pts1 = pcs.unsqueeze(1)
        pts2 = pcs.unsqueeze(0)
        if verbose:print("Finished SVD calculation.") 
    else:
        pts1 = pts.unsqueeze(1)
        pts2 = pts.unsqueeze(0)

    if verbose:print("Calculating distances...") 
    #dists = differentiable_distance_matrix_torch(pts)
    epsilon = 1e-8
    sq_dists = torch.sum((pts1 - pts2) ** 2, dim=2)
    dists = torch.sqrt(sq_dists + epsilon)
    if verbose:print("Finished differentiable distance calculation.") 

    if verbose:print("Calculating Vietoris-Rips filtration...")
    max_distance = 2*min_enclosing_radius_torch(dists) if max_distance is None else max_distance + .2
    vr_filtration = oin.diff.vietoris_rips_pwdists(
        dists, 
        max_dim=hom_dim+1, #need the k+1 skeleton for k-homology
        max_radius=max_distance, # max_radius in oineus is really max_distance... 
        n_threads=n_threads
    )
    if verbose:print(f"Finished filtration {vr_filtration}.")

    top_opt = oin.diff.TopologyOptimizer(vr_filtration)
    
    if verbose:print("Computing persistent homology...")
    dgm = top_opt.compute_diagram(include_inf_points=False)
    if verbose:print("Finished persistent homology calculation.")
    largest_hom_persistence = top_opt.get_nth_persistence(hom_dim, n_topo_feats)
    
    if verbose:print("Calculating gene scores...")
    # Get critical spx indices of homology classes in persistence diagram to move 
    # and values correspond to their new value in the persistence diagram
    # each pair (idx, target_values)
    indices, target_values_in_pers_dgm = top_opt.simplify(largest_hom_persistence, strategy, hom_dim)
    
    # critical_sets is a list where elements are 
    # (filtration_value, spx_ids) where spx_ids are the indices of the simplices in the critical set 
    critical_sets = top_opt.singletons(indices, target_values_in_pers_dgm) 
    crit_indices, crit_values = top_opt.combine_loss(critical_sets, oin.ConflictStrategy.Max) # Resolve strategies
    crit_indices = np.array(crit_indices, dtype=np.int32)
    crit_values = torch.Tensor(crit_values)
    top_loss = torch.norm(vr_filtration.values[crit_indices] - crit_values)
    top_loss.backward()
    if verbose:print("Finished gene score calculation succesfully.")
    gradient = pts.grad

    return torch.norm(gradient, dim = 0).numpy(), [dgm[i] for i in range(hom_dim+1)]

def topology_layer_perturbation(
    pts:torch.Tensor, hom_dim:int=1, max_distance:float=None,
    n_threads:int=16, pca:bool=False, n_pcs:int=20, verbose:bool=False, dualize:bool = True
)->Tuple[torch.tensor, list]:
    """
    Returns topological loss and persistent diagrams for perturbation approach.
    TODO: Handle `n_top_feats`

    Params
    ------
    pts : Input dataset. Needs to have the `requires_grad` param active.

    Usage
    -----
    lr = 1e-2
    topo_loss, dgms = topology_layer_perturbation(pts)
    topo_loss.backward()
    grad = pts.grad 
    pts = pts - lr * grad # perturb points 

    TODO: add possibility of calculating via subset. 
    """
    if pca:
        if verbose:print("Calculating SVD...") 
        pts_ = pts - pts.mean(dim=0) # mean center data
        U, s, Vt = torch.svd_lowrank(pts_, q = n_pcs + 50, niter = 2)
        pcs = U[:, :n_pcs] *  s[:n_pcs]
        pts1 = pcs.unsqueeze(1)
        pts2 = pcs.unsqueeze(0)
        if verbose:print("Finished SVD computation.") 
    else:
        pts1 = pts.unsqueeze(1)
        pts2 = pts.unsqueeze(0)
    
    if verbose:print("Calculating distances...") 
    epsilon = 1e-8
    sq_dists = torch.sum((pts1 - pts2) ** 2, dim=2)
    dists = torch.sqrt(sq_dists + epsilon)
    if verbose:print("Finished differentiable distance calculation.")
    
    # max_dist = dists.max()
    dists_np = dists.detach().numpy().astype(np.float64)
    if verbose:print("Calculating Vietoris-Rips filtration...")
    max_distance = 2 * min_enclosing_radius_torch(dists) + .1 if max_distance is None else max_distance + .2
    fil, longest_edges = oin.get_vr_filtration_and_critical_edges_from_pwdists(
        dists_np, max_dim=2, max_radius = max_distance, n_threads=n_threads # max_radius in oineus is really max_distance... 
    )
    if verbose:print(f"Finished filtration {fil}.")

    if verbose:print("Computing persistent homology...")
    dualize = False # no cohomology
    dcmp = oin.Decomposition(fil, dualize) # create VRU decomposition object, does not perform reduction yet

    rp = oin.ReductionParams()
    rp.compute_u = False # U matrix cannot be computed in parallel mode
    rp.compute_v = True
    rp.n_threads = 16
    dcmp.reduce(rp) # perform PH reduction
    if verbose:print("Finished persistent homology calculation.")

    if verbose:print("Calculating gene scores...")
    dgms = dcmp.diagram(fil, include_inf_points=False)
    dgms = [dgms[0], dgms[1]]
    lifetimes = dgms[1][:, 1] - dgms[1][:, 0]
    ix_largest_lifetime = np.argsort(lifetimes)[-1]

    indices_dgm = dcmp.diagram(fil).index_diagram_in_dimension(hom_dim)
    birth_simplex_sorted_ix, death_simplex_sorted_ix = indices_dgm[ix_largest_lifetime, :]
    
    tgt_val = dgms[hom_dim][ix_largest_lifetime].sum()/2 # send ph class to diag
    indices = [birth_simplex_sorted_ix, death_simplex_sorted_ix]
    values = [tgt_val, tgt_val]

    opt = oin.TopologyOptimizer(fil)
    critical_sets = opt.singletons(indices, values)
    crit_indices, target_crit_values = opt.combine_loss(critical_sets, oin.ConflictStrategy.Max)
    crit_edges = longest_edges[crit_indices, :]
    crit_edges_x, crit_edges_y = crit_edges[:, 0], crit_edges[:, 1]
    target_crit_values = torch.Tensor(target_crit_values)
    init_crit_values = torch.sum((pts[crit_edges_x, :] - pts[crit_edges_y, :])**2, axis=1) # distance of largest edges in critical simplices
    topo_loss = torch.norm(target_crit_values - init_crit_values)
    if verbose:print("Finished gene score calculation succesfully.")

    return topo_loss, [dgms[i] for i in range(hom_dim+1)]

def topological_gene_scores_via_perturbation(
    data:np.ndarray, n_threads:int=2, hom_dim:int=1, n_topo_feats:int=1, max_distance:float=None,
    verbose:bool = False, epochs:int= 1, pca:bool=False, n_pcs:int=20, dualize:bool = False
)->Tuple[np.ndarray,list]:
    """
    Returns gene scores and persistent diagrams via a perturbation approach. 
    In particular, this method calculates the norm of the gradients w.r.t. 
    a perturbation of the input points to send the largest persistent homology class to the diagonal.
    """

    pts = torch.Tensor(data)
    pts.requires_grad_(True)
    topo_loss, dgms = topology_layer_perturbation(pts, hom_dim, max_distance, n_threads, pca, n_pcs, verbose, dualize=dualize)
    topo_loss.backward()
    grad = pts.grad
    return grad.norm(dim=0).numpy(), [dgms[i] for i in range(hom_dim+1)]

def topological_gene_scores_via_perturbation_ripser(
    data:np.ndarray, n_pts:int=None, n_threads:int=2, hom_dim:int=1, n_topo_feats:int=1, max_distance:float=None,
    verbose:bool = False, pca:bool = False, n_pcs:int=30, target_strategy:str="death-death"
    )->Tuple[list, np.ndarray]:
    """
    Returns gene scores using a modification of the perturbation method.
    Largest homology class gets mapped from (b,d) to (d,d) in pers diagram. 
    """
    pts = torch.Tensor(data)
    pts.requires_grad_(True);
    if pca:
        if verbose:print("Calculating SVD...") 
        pts_ = pts - pts.mean(dim=0) # mean center data
        U, s, Vt = torch.svd_lowrank(pts_, q = n_pcs + 50, niter = 2)
        pcs = U[:, :n_pcs] *  s[:n_pcs]
        pts1 = pcs.unsqueeze(1)
        pts2 = pcs.unsqueeze(0)
        if verbose:print("Finished SVD computation.") 
    else:
        pts1 = pts.unsqueeze(1)
        pts2 = pts.unsqueeze(0)
    
    if verbose:print("Calculating distances...") 
    epsilon = 1e-8
    sq_dists = torch.sum((pts1 - pts2) ** 2, dim=2)
    dists = torch.sqrt(sq_dists + epsilon)
    if verbose:print("Finished differentiable distance calculation.")

    t_init=time.time()
    ph = ripser(
        pcs.detach().numpy() if pca else data,
        do_cocycles=True, 
        thresh=np.inf if max_distance is None else max_distance*1.1
    )
    t_end=time.time()
    t_tot = t_end-t_init
    if verbose:print(f"PH took {t_tot/60:.2f} mins.")

    cocycles=ph["cocycles"]
    dgms=ph["dgms"]
    lifetimes = get_lifetimes(dgms[1])
    ix_largest = np.argsort(lifetimes)[-1]
    cocycle_edges_largest_hom_class = cocycles[1][ix_largest][:, :2] # first two entries are edges 
    cocycle_edges_largest_hom_class = cocycle_edges_largest_hom_class[:, ::-1] # get edges in lexicographic order 
    death_time = dgms[1][ix_largest][1]

    if verbose:print("Calculating Oineus Vietoris-Rips filtration...")
    
    max_distance = 2*min_enclosing_radius_torch(dists) if max_distance is None else max_distance + .2
    
    vr_filtration = oin.diff.vietoris_rips_pwdists(
        dists, 
        max_dim=hom_dim+1, #need the k+1 skeleton for k-homology
        max_radius=death_time*1.2, # max_radius in oineus is really max_distance... 
        n_threads=n_threads
    )

    if verbose:print("Computing topological scores")
    simplices = [spx.vertices for spx in vr_filtration.cells()]
    crit_indices = [simplices.index(list(spx)) for spx in cocycle_edges_largest_hom_class]
    crit_values = torch.repeat_interleave(torch.Tensor([death_time]), repeats=len(crit_indices))
    top_loss = torch.norm(vr_filtration.values[crit_indices] - crit_values)
    top_loss.backward()
    gradient = pts.grad
    if verbose:print("Finished.")
    return gradient.norm(dim=0).numpy()