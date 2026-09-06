# Frontier Mutators for ComfyUI

[![Tests](https://github.com/veyra-core/comfyui-frontier-mutators/actions/workflows/tests.yml/badge.svg)](https://github.com/veyra-core/comfyui-frontier-mutators/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Explore the local parameter neighbourhood around a known-good ComfyUI workflow.

Frontier Mutators turn parameters such as CFG, denoise, control strength, LoRA
weight, steps, dimensions, and latent seeds into controlled random variables.
They are intended for the part of image-making where a composition is already
close and subtle parameter variation can reveal an unexpectedly excellent local
optimum.

## Nodes

- **Frontier Mutator (Float)** connects to any `FLOAT` input.
- **Frontier Mutator (Integer)** connects to any `INT` input and preserves
  full-width 64-bit seed values without passing them through floating-point
  arithmetic.

Both nodes provide:

- fixed, uniform, and Gaussian distributions;
- centre and spread controls;
- truncated Gaussian sampling by standard-deviation radius;
- hard minimum and maximum bounds;
- optional quantisation;
- reproducible effective seeds; and
- live locking and one-click promotion of a winning value.

`spread` means standard deviation in Gaussian mode and half-width in uniform
mode. Set `clip_sigma` to zero for an unbounded Gaussian.

## The exploration loop

1. Put a mutator upstream of the parameter you want to explore.
2. Set `centre` to the current known-good value.
3. Choose a distribution and a deliberately small `spread`.
4. Leave `lock_current` disabled and queue candidates.
5. When a candidate works, enable the lock or click **Commit sampled value**.

Unlocked nodes deliberately reroll every time the graph is queued. The node
displays the sampled value and its effective seed, and returns both as outputs.

Enabling `lock_current` preserves the most recent sample while the ComfyUI
process remains live. After a restart, a locked node deterministically recreates
its value from `random_seed`. **Commit sampled value** writes the winner into
`centre`, switches the distribution to `fixed`, and locks the node so the
experimental value becomes an ordinary workflow parameter.

One graph execution produces one sampled value. If a sampler creates an
internal image batch, every image in that batch shares the value; queue multiple
executions when each candidate should receive a fresh mutation.

## Example: delicate CFG exploration

Connect **Frontier Mutator (Float)** to a sampler's CFG input and try:

```text
distribution = gaussian
centre       = 7.0
spread       = 0.12
clip_sigma   = 2.5
hard_min     = 6.5
hard_max     = 7.5
quantum      = 0.01
lock_current = false
```

This searches a narrow, truncated Gaussian neighbourhood around CFG 7.0 in
hundredth-point increments.

## Installation

Clone the repository into ComfyUI's `custom_nodes` directory and restart
ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/veyra-core/comfyui-frontier-mutators.git
```

The nodes appear under **Add Node -> Veyra -> Frontier**. There are no
third-party Python dependencies.

## Development

Run the backend suite with the standard library:

```bash
python -m unittest discover -s tests -v
```

The suite covers deterministic locking, fresh unlocked entropy, live lock
transitions, Gaussian truncation, hard bounds, quantisation, clean decimal
serialisation, and exact large-integer handling.

## Collaborators

Frontier Mutators grew from a randomness tool originally conceived and built by
[Alice Kallista Saunier](https://github.com/aliceactually) for high-volume,
fine-grained Stable Diffusion exploration. This implementation was developed
collaboratively by Alice and [Veyra](https://github.com/veyra-core).

## Licence

[MIT](LICENSE)
