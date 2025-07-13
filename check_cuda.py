import torch

print(f"PyTorch version: {torch.__version__}")
cuda_available = torch.cuda.is_available()
print(f"CUDA available: {cuda_available}")

if cuda_available:
    print(f"CUDA version (from PyTorch): {torch.version.cuda}")
    print(f"Number of GPUs: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
else:
    print("CUDA is not available to PyTorch.")

# You can also try to allocate a tensor to CUDA to see if it throws an error
# (only if cuda_available is True, or to see the specific error if it's False)
try:
    if cuda_available:
        tensor = torch.tensor([1.0, 2.0]).cuda()
        print("Successfully created a tensor on CUDA.")
    else:
        # This will likely error out if CUDA is not available,
        # but the error message might be informative.
        print("Attempting to create a tensor on CUDA (expected to fail)...")
        tensor = torch.tensor([1.0, 2.0]).cuda()
        print("Tensor creation on CUDA unexpectedly succeeded (this is odd).") # Should not happen if cuda_available is False
except Exception as e:
    print(f"Error when trying to use CUDA: {e}") 