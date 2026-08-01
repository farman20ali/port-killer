"""
Benchmark script for kport inspectors: PsutilInspector vs FallbackInspector.

Measures latency of listing listening ports across available inspectors on this system.
Usage:
    python -m benchmarks.bench_list
"""

import time
from kport.inspectors.system_impl import FallbackInspector
from kport.inspectors import _psutil_accessible

def run_benchmark(iterations: int = 50):
    print("=" * 60)
    print(" kport Inspector Benchmark: list_listening() ")
    print("=" * 60)
    
    # 1. FallbackInspector (Native/Subprocess)
    fallback = FallbackInspector()
    start = time.perf_counter()
    for _ in range(iterations):
        fallback_results = fallback.list_listening()
    fallback_time = (time.perf_counter() - start) / iterations * 1000  # in ms
    print(f"FallbackInspector (system native): {fallback_time:.2f} ms / call ({len(fallback_results)} ports found)")
    
    # 2. PsutilInspector (if accessible)
    if _psutil_accessible():
        from kport.inspectors.psutil_impl import PsutilInspector
        psutil_insp = PsutilInspector()
        start = time.perf_counter()
        for _ in range(iterations):
            psutil_results = psutil_insp.list_listening()
        psutil_time = (time.perf_counter() - start) / iterations * 1000  # in ms
        print(f"PsutilInspector (psutil backend): {psutil_time:.2f} ms / call ({len(psutil_results)} ports found)")
        
        speedup = fallback_time / psutil_time if psutil_time > 0 else 1.0
        print(f"\nSpeedup with psutil: {speedup:.2f}x")
    else:
        print("PsutilInspector: Not accessible / not installed on this system.")
    print("=" * 60)

if __name__ == "__main__":
    run_benchmark()
