#ifndef AUTOSBD_RIKEN_NVCC_COMPAT_H
#define AUTOSBD_RIKEN_NVCC_COMPAT_H

// RIKEN SBD v1.3.0 calls CUDA's device-only __popcll intrinsic from a
// __host__ __device__ function. Load CUDA declarations first, then narrowly
// remap those four calls to the equivalent compiler builtin so nvcc can emit
// both host and device variants. This header is forced into only the pinned
// RIKEN GPU build; upstream source remains unmodified.
#include <cuda_runtime.h>
#define __popcll(value) __builtin_popcountll(value)

#endif
