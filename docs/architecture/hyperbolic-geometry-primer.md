# Hyperbolic geometry in AI — a primer

> Background for the `{7,3}` hyperbolic kernel in
> [`swarm_core/hyperbolic_kernel.py`](../../packages/swarm-core/src/swarm_core/hyperbolic_kernel.py)
> and the curvature-depth mechanics of the terminal (`/chamber`, `/observe pattern`).
> This is context, not a spec — nothing here has to be read to change kernel code.

Hyperbolic geometry shows up in AI because many datasets are tree-like:
taxonomies, knowledge graphs, parse trees, social networks, and concept
hierarchies. Euclidean space wastes capacity on those structures. Hyperbolic
space does not.

Hyperbolic geometry is the geometry of constant **negative curvature**.
Distances and areas grow exponentially as you move away from a point, instead of
polynomially as in Euclidean space. That single fact is why it keeps showing up
in AI.

## Why trees fit hyperbolic space

A rooted tree with branching factor *b* has about *b^d* nodes at depth *d*.
Euclidean volume of a ball of radius *r* grows like *r^n*. Hyperbolic volume
grows like *sinh^(n-1) r*, i.e. exponentially in *r*.

So a tree embeds into a low-dimensional hyperbolic space with little distortion.
The same tree in Euclidean space either needs many dimensions or gets crushed.
Nickel and Kiela's 2017 Poincaré embeddings made this practical: WordNet-style
hierarchies reconstruct far better in a 5-D Poincaré ball than in a 200-D
Euclidean space.

Intuition:
- the **origin** is the root / most general concept
- **radius** encodes depth / specificity
- **angular separation** encodes which branch you are on
- nearby leaves of different branches can still sit far apart in geodesic distance

## Models used in code

The two workhorses are isometric; pick one for numerics.

**Poincaré ball** (the open unit ball with a metric that blows up near the
boundary). Distances look Euclidean near the center and stretch near the rim.
Nice for visualization and conformal operations.

**Lorentz / hyperboloid** (a sheet of *x0^2 - ||x||^2 = 1/c* in Minkowski
space). Often more stable for optimization than naïve Poincaré implementations,
though high-dimensional exp/log maps can still be fragile.

Points live on the manifold. Neural nets therefore use:
- **exponential / logarithmic maps** to jump to the tangent space, apply a
  Euclidean layer, then map back
- **Möbius addition** instead of vector addition
- **Riemannian SGD / Adam** so steps follow geodesics instead of straight
  Euclidean lines

If you ignore that and treat coordinates as ordinary vectors, curvature is
wasted and training can explode near the boundary.

## Where it is used

**Graphs and knowledge bases.** Hyperbolic GNNs and GCNs beat Euclidean ones on
hierarchical or scale-free graphs: citation networks, ontologies, fraud graphs,
some biological networks. Message passing happens along geodesics; aggregation
respects negative curvature.

**Language.** Taxonomies, entailment, multi-scale semantics. Recent work puts
parts of LLMs or their latents into hyperbolic space (exp/log wrappers,
hyperbolic fine-tuning, or fully hyperbolic layers) to help hierarchical
reasoning and parameter efficiency. Mixed-curvature transformers also exist:
some subspaces Euclidean, some hyperbolic.

**Vision and multimodal.** Class hierarchies (ImageNet-style), few-shot
prototypes, and aligning image–text spaces so "animal → dog → husky" is a radial
path rather than a scrambled cluster.

**Generative models.** Graph generators on the Poincaré ball (e.g. HVQ-VAE +
Riemannian flow matching) preserve degree distributions and community hierarchy
better than Euclidean generators.

**Sparsity / architecture.** Embedding nodes in hyperbolic space and decaying
connections by geodesic distance gives input-dependent sparse connectivity that
still respects hierarchy, an alternative to dense attention.

## What it is *not*

It is not a free lunch for every dataset. Flat, cyclic, or densely clustered
data often prefer Euclidean or spherical geometry. Curvature can be learned
(product manifolds *E × H × S*) when you do not know the structure in advance.

Numerics matter: points hugging the Poincaré boundary have huge gradients;
Lorentz models have their own overflow issues. In practice people clip radii,
use gyrovector ops carefully, or keep only a few hyperbolic layers.

## Geometric picture in one sentence

Euclidean embeddings treat "cat" and "animal" as two points of similar status.
Hyperbolic embeddings put "animal" near the center and "cat" farther out on a
branch, so *is-a* is literally a direction toward the origin, and the whole
taxonomy can live in a handful of dimensions without folding over itself.
